"""FastAPI app for the psychology suite."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agents import generate_soap_note
from .config import load_settings
from .data_store import SQLALCHEMY_AVAILABLE, bootstrap
from .schemas import (
    ConsentRequest,
    LoginRequest,
    PatientCreateRequest,
    PatientUpdateRequest,
    RetentionRequest,
    SessionCreateRequest,
    SessionNoteUpdateRequest,
    SessionUpdateRequest,
    SummarizeRequest,
    TranscriptConfirmRequest,
    TranscriptionResponse,
)
from .security import hash_password, new_session_id, session_expiry, verify_password
from .storage import delete_audio, store_audio
from .transcription import transcribe_file


settings = load_settings()
bootstrap()

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Psychology Suite", version="0.1.0")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _current_user(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail="Missing session")

    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .models import Psychologist
        from .repositories import get_active_session

        with session_scope() as session:
            auth = get_active_session(session, session_id)
            if not auth:
                raise HTTPException(status_code=401, detail="Invalid session")
            psychologist = session.get(Psychologist, auth.psychologist_id)
            if not psychologist or not psychologist.active:
                raise HTTPException(status_code=403, detail="Account inactive")
            return {"id": psychologist.id, "name": psychologist.name, "email": psychologist.email}

    from .lite_store import get_active_session as lite_active_session, get_user

    auth = lite_active_session(session_id)
    if not auth:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = get_user(auth["psychologist_id"])
    if not user or not user.get("active"):
        raise HTTPException(status_code=403, detail="Account inactive")
    return user


def _validate_transcript(text: str) -> None:
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty.")
    if len(text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Transcript is too short for summarization.")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/app", include_in_schema=False)
def app_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "profile.html")


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/profile", include_in_schema=False)
def profile_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "profile.html")


@app.get("/patient", include_in_schema=False)
def patient_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "patient.html")


@app.get("/session", include_in_schema=False)
def session_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "session.html")


@app.post("/auth/login")
def login(body: LoginRequest) -> JSONResponse:
    email = body.email.strip().lower()
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .models import AuthSession
        from .repositories import get_psychologist_by_email, write_audit

        with session_scope() as session:
            user = get_psychologist_by_email(session, email)
            if not user or not verify_password(body.password, user.password_hash):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            session_id = new_session_id()
            auth = AuthSession(id=session_id, psychologist_id=user.id, expires_at=session_expiry())
            session.add(auth)
            write_audit(session, psychologist_id=user.id, action="login", entity_type="psychologist", entity_id=user.id)

            response = JSONResponse({"message": "ok"})
            response.set_cookie(
                key=settings.session_cookie_name,
                value=session_id,
                httponly=True,
                samesite="lax",
                secure=False,
            )
            return response

    from .lite_store import create_auth_session, get_user_by_email

    user = get_user_by_email(email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session_id = create_auth_session(user["id"], session_expiry().isoformat())
    response = JSONResponse({"message": "ok"})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@app.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        if SQLALCHEMY_AVAILABLE:
            from .db import session_scope
            from .repositories import revoke_session

            with session_scope() as session:
                revoke_session(session, session_id)
        else:
            from .lite_store import revoke_auth_session

            revoke_auth_session(session_id)
    response = JSONResponse({"message": "ok"})
    response.delete_cookie(settings.session_cookie_name)
    return response


@app.get("/me")
def me(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    return {"id": user["id"], "name": user["name"], "email": user["email"]}


@app.get("/patients")
def patients(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import list_patients

        with session_scope() as session:
            rows = list_patients(session, user["id"])
            return {
                "patients": [
                    {
                        "id": item.id,
                        "display_name": item.display_name,
                        "date_of_birth": item.date_of_birth,
                        "contact_email": item.contact_email,
                        "contact_phone": item.contact_phone,
                        "notes": item.notes,
                        "active": item.active,
                        "updated_at": item.updated_at.isoformat(),
                    }
                    for item in rows
                ]
            }

    from .lite_store import list_patients

    return {"patients": list_patients(user["id"])}


@app.post("/patients", status_code=201)
def patient_create(request: Request, body: PatientCreateRequest) -> dict[str, Any]:
    user = _current_user(request)
    payload = body.model_dump()
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .models import Patient
        from .repositories import write_audit

        with session_scope() as session:
            item = Patient(
                psychologist_id=user["id"],
                display_name=body.display_name.strip(),
                date_of_birth=body.date_of_birth,
                contact_email=body.contact_email,
                contact_phone=body.contact_phone,
                notes=body.notes,
            )
            session.add(item)
            session.flush()
            write_audit(session, psychologist_id=user["id"], action="create", entity_type="patient", entity_id=item.id)
            return {"patient": {"id": item.id}}

    from .lite_store import create_patient

    item = create_patient(user["id"], payload)
    return {"patient": {"id": item["id"]}}


@app.get("/patients/{patient_id}")
def patient_get(request: Request, patient_id: str) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_patient

        with session_scope() as session:
            item = ensure_patient(session, user["id"], patient_id)
            return {
                "patient": {
                    "id": item.id,
                    "display_name": item.display_name,
                    "date_of_birth": item.date_of_birth,
                    "contact_email": item.contact_email,
                    "contact_phone": item.contact_phone,
                    "notes": item.notes,
                    "active": item.active,
                    "updated_at": item.updated_at.isoformat(),
                }
            }

    from .lite_store import get_patient

    item = get_patient(user["id"], patient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"patient": item}


@app.put("/patients/{patient_id}")
def patient_update(request: Request, patient_id: str, body: PatientUpdateRequest) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_patient, write_audit

        with session_scope() as session:
            item = ensure_patient(session, user["id"], patient_id)
            if body.display_name is not None:
                item.display_name = body.display_name
            if body.date_of_birth is not None:
                item.date_of_birth = body.date_of_birth
            if body.contact_email is not None:
                item.contact_email = body.contact_email
            if body.contact_phone is not None:
                item.contact_phone = body.contact_phone
            if body.notes is not None:
                item.notes = body.notes
            if body.active is not None:
                item.active = body.active
            write_audit(session, psychologist_id=user["id"], action="update", entity_type="patient", entity_id=item.id)
            return {"patient": {"id": item.id}}

    from .lite_store import update_patient

    updates = body.model_dump()
    item = update_patient(user["id"], patient_id, updates)
    if not item:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"patient": {"id": item["id"]}}


@app.delete("/patients/{patient_id}")
def patient_delete(request: Request, patient_id: str) -> dict[str, Any]:
    user = _current_user(request)
    audio_paths = []
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import delete_patient, ensure_patient, write_audit

        with session_scope() as session:
            item = ensure_patient(session, user["id"], patient_id)
            audio_paths = [session_item.audio_path for session_item in item.sessions if session_item.audio_path]
            delete_patient(session, user["id"], patient_id)
            write_audit(session, psychologist_id=user["id"], action="delete", entity_type="patient", entity_id=patient_id)
    else:
        from .lite_store import delete_patient as lite_delete_patient

        audio_paths = lite_delete_patient(user["id"], patient_id)
    for path in audio_paths:
        delete_audio(path)
    return {"message": "deleted"}


@app.get("/sessions")
def sessions(request: Request, patient_id: str | None = None) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import list_sessions

        with session_scope() as session:
            rows = list_sessions(session, user["id"], patient_id=patient_id)
            return {
                "sessions": [
                    {
                        "id": item.id,
                        "patient_id": item.patient_id,
                        "status": item.status,
                        "note_format": item.note_format,
                        "transcript_text": item.transcript_text,
                        "note_text": item.note_text,
                        "low_confidence": item.low_confidence,
                        "transcript_confirmed": item.transcript_confirmed,
                        "started_at": item.started_at.isoformat(),
                    }
                    for item in rows
                ]
            }

    from .lite_store import list_sessions

    return {"sessions": list_sessions(user["id"], patient_id=patient_id)}


@app.get("/sessions/{session_id}")
def session_get(request: Request, session_id: str) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_session

        with session_scope() as session:
            item = ensure_session(session, user["id"], session_id)
            return {
                "session": {
                    "id": item.id,
                    "patient_id": item.patient_id,
                    "status": item.status,
                    "note_format": item.note_format,
                    "transcript_text": item.transcript_text,
                    "note_text": item.note_text,
                    "low_confidence": item.low_confidence,
                    "transcript_confirmed": item.transcript_confirmed,
                    "started_at": item.started_at.isoformat(),
                    "audio_path": item.audio_path,
                }
            }

    from .lite_store import get_session

    item = get_session(user["id"], session_id)
    if not item:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": item}


@app.post("/sessions", status_code=201)
def session_create(request: Request, body: SessionCreateRequest) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .models import Session as PsychSession
        from .repositories import ensure_patient, write_audit

        with session_scope() as session:
            ensure_patient(session, user["id"], body.patient_id)
            item = PsychSession(
                psychologist_id=user["id"],
                patient_id=body.patient_id,
                note_format=body.note_format,
            )
            session.add(item)
            session.flush()
            write_audit(session, psychologist_id=user["id"], action="create", entity_type="session", entity_id=item.id)
            return {"session": {"id": item.id}}

    from .lite_store import create_session, get_patient

    patient = get_patient(user["id"], body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    item = create_session(user["id"], body.model_dump())
    return {"session": {"id": item["id"]}}


@app.put("/sessions/{session_id}")
def session_update(request: Request, session_id: str, body: SessionUpdateRequest) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_session, write_audit

        with session_scope() as session:
            item = ensure_session(session, user["id"], session_id)
            if body.status is not None:
                item.status = body.status
            if body.note_text is not None:
                item.note_text = body.note_text
            if body.note_format is not None:
                item.note_format = body.note_format
            write_audit(session, psychologist_id=user["id"], action="update", entity_type="session", entity_id=item.id)
            return {"session": {"id": item.id}}

    from .lite_store import update_session

    item = update_session(user["id"], session_id, body.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": {"id": item["id"]}}


@app.delete("/sessions/{session_id}")
def session_delete(request: Request, session_id: str) -> dict[str, Any]:
    user = _current_user(request)
    audio_path = None
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import delete_session, ensure_session, write_audit

        with session_scope() as session:
            item = ensure_session(session, user["id"], session_id)
            audio_path = item.audio_path
            delete_session(session, user["id"], session_id)
            write_audit(session, psychologist_id=user["id"], action="delete", entity_type="session", entity_id=session_id)
    else:
        from .lite_store import delete_session as lite_delete_session

        audio_path = lite_delete_session(user["id"], session_id)
    if audio_path:
        delete_audio(audio_path)
    return {"message": "deleted"}


@app.post("/sessions/{session_id}/consent", status_code=201)
def session_consent(request: Request, session_id: str, body: ConsentRequest) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_session, set_consents, write_audit

        with session_scope() as session:
            item = ensure_session(session, user["id"], session_id)
            consent = set_consents(session, item.id, body.consent_text_version)
            write_audit(session, psychologist_id=user["id"], action="consent", entity_type="session", entity_id=item.id)
            return {"consent": {"id": consent.id}}

    from .lite_store import set_consent

    consent = set_consent(session_id, body.consent_text_version)
    return {"consent": {"id": consent["id"]}}


@app.post("/sessions/{session_id}/confirm-transcript")
def confirm_transcript(request: Request, session_id: str, body: TranscriptConfirmRequest) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_session, write_audit

        with session_scope() as session:
            item = ensure_session(session, user["id"], session_id)
            item.transcript_confirmed = body.confirmed
            write_audit(session, psychologist_id=user["id"], action="confirm_transcript", entity_type="session", entity_id=item.id)
            return {"session": {"id": item.id, "transcript_confirmed": item.transcript_confirmed}}

    from .lite_store import update_session

    item = update_session(user["id"], session_id, {"transcript_confirmed": body.confirmed})
    if not item:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": {"id": item["id"], "transcript_confirmed": item["transcript_confirmed"]}}


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(request: Request, audio: UploadFile = File(...), session_id: str | None = None):
    user = _current_user(request)
    suffix = Path(audio.filename).suffix if audio.filename else ".webm"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content = await audio.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail="File too large")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = transcribe_file(tmp_path)
    finally:
        os.unlink(tmp_path)

    if session_id:
        if SQLALCHEMY_AVAILABLE:
            from .db import session_scope
            from .repositories import ensure_session, write_audit

            with session_scope() as session:
                item = ensure_session(session, user["id"], session_id)
                stored = store_audio(content, f"{item.id}{suffix}")
                item.audio_path = stored.relative_path
                item.transcript_text = result.transcript
                item.low_confidence = result.low_confidence
                item.transcript_meta = json.dumps(result.meta)
                item.transcript_confirmed = False
                write_audit(session, psychologist_id=user["id"], action="transcribe", entity_type="session", entity_id=item.id)
        else:
            from .lite_store import update_session

            stored = store_audio(content, f"{session_id}{suffix}")
            update_session(
                user["id"],
                session_id,
                {
                    "audio_path": stored.relative_path,
                    "transcript_text": result.transcript,
                    "low_confidence": result.low_confidence,
                    "transcript_meta": json.dumps(result.meta),
                    "transcript_confirmed": False,
                },
            )

    return TranscriptionResponse(
        transcript=result.transcript,
        low_confidence=result.low_confidence,
        meta=result.meta,
    )


@app.post("/api/summarize")
def summarize(request: Request, body: SummarizeRequest) -> dict[str, Any]:
    user = _current_user(request)
    transcript = body.transcript
    session_id = body.session_id
    if session_id:
        if SQLALCHEMY_AVAILABLE:
            from .db import session_scope
            from .repositories import ensure_session

            with session_scope() as session:
                item = ensure_session(session, user["id"], session_id)
                transcript = item.transcript_text
                if item.low_confidence and not item.transcript_confirmed:
                    raise HTTPException(status_code=400, detail="Confirm transcript before summarizing.")
                if item.transcript_confirmed is False and item.low_confidence is False:
                    item.transcript_confirmed = True
        else:
            from .lite_store import get_session, update_session

            item = get_session(user["id"], session_id)
            if not item:
                raise HTTPException(status_code=404, detail="Session not found")
            transcript = item.get("transcript_text")
            if item.get("low_confidence") and not item.get("transcript_confirmed"):
                raise HTTPException(status_code=400, detail="Confirm transcript before summarizing.")
            if item.get("transcript_confirmed") is False and not item.get("low_confidence"):
                update_session(user["id"], session_id, {"transcript_confirmed": True})

    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript required")

    _validate_transcript(transcript)
    try:
        note = generate_soap_note(transcript)
    except Exception as exc:  # pragma: no cover - runtime LLM dependency
        text = str(exc)
        if "Connection refused" in text or "ConnectError" in text:
            raise HTTPException(
                status_code=503,
                detail=(
                    "LLM server unavailable. Start Ollama (ollama serve) and ensure the model is pulled, "
                    "or set PSYCH_SUITE_OLLAMA_BASE_URL to the correct endpoint."
                ),
            ) from exc
        raise

    if session_id:
        if SQLALCHEMY_AVAILABLE:
            from .db import session_scope
            from .repositories import ensure_session, write_audit

            with session_scope() as session:
                item = ensure_session(session, user["id"], session_id)
                item.note_text = note
                item.status = "draft"
                write_audit(session, psychologist_id=user["id"], action="summarize", entity_type="session", entity_id=item.id)
        else:
            from .lite_store import update_session

            update_session(user["id"], session_id, {"note_text": note, "status": "draft"})

    return {"final_note": note}


@app.post("/api/sessions/{session_id}/note")
def update_note(request: Request, session_id: str, body: SessionNoteUpdateRequest) -> dict[str, Any]:
    user = _current_user(request)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .repositories import ensure_session, write_audit

        with session_scope() as session:
            item = ensure_session(session, user["id"], session_id)
            item.note_text = body.note_text
            if body.status:
                item.status = body.status
            write_audit(session, psychologist_id=user["id"], action="update_note", entity_type="session", entity_id=item.id)
            return {"session": {"id": item.id}}

    from .lite_store import update_session

    item = update_session(user["id"], session_id, {"note_text": body.note_text, "status": body.status})
    if not item:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": {"id": item["id"]}}


@app.post("/api/retention")
def retention_cleanup(request: Request, body: RetentionRequest) -> dict[str, Any]:
    user = _current_user(request)
    retention_days = body.retention_days or settings.retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    if SQLALCHEMY_AVAILABLE:
        from .db import session_scope
        from .models import Session as PsychSession
        from .repositories import write_audit

        with session_scope() as session:
            if body.dry_run:
                count = session.query(PsychSession).filter(PsychSession.started_at < cutoff).count()
                return {"dry_run": True, "eligible_sessions": count}
            targets = session.query(PsychSession).filter(PsychSession.started_at < cutoff).all()
            audio_paths = [item.audio_path for item in targets if item.audio_path]
            for item in targets:
                session.delete(item)
            write_audit(session, psychologist_id=user["id"], action="retention_cleanup", entity_type="session", entity_id="batch")
        for path in audio_paths:
            delete_audio(path)
        return {"deleted_sessions": len(targets)}

    from .lite_store import purge_sessions_before

    if body.dry_run:
        from .lite_store import list_sessions

        eligible = [
            item
            for item in list_sessions(user["id"])
            if datetime.fromisoformat(item["started_at"]) < cutoff
        ]
        return {"dry_run": True, "eligible_sessions": len(eligible)}
    audio_paths = purge_sessions_before(user["id"], cutoff)
    for path in audio_paths:
        delete_audio(path)
    return {"deleted_sessions": len(audio_paths)}
