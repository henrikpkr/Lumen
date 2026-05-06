"""Additive documentation MVP services."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .models import (
    DocumentationSession,
    DocumentationSessionNote,
    DocumentationSessionText,
    Patient,
    Referral,
    Therapist,
    User,
)
from .repositories import iso_or_none, json_safe, utc_now
from .seed import DEMO_TENANT_ID


NOTE_VERSION = "session_note_v0.1"
DEFAULT_HF_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_HF_MODEL = "meta-llama/Llama-3.1-70B-Instruct"
NOTE_KEYS = {
    "version",
    "summary",
    "source_basis",
    "presenting_topics",
    "subjective",
    "objective_observations",
    "interventions",
    "patient_response",
    "risk_or_safety",
    "plan",
    "uncertainty_flags",
}
LIST_KEYS = [
    "presenting_topics",
    "subjective",
    "objective_observations",
    "interventions",
    "patient_response",
    "plan",
    "uncertainty_flags",
]


def create_documentation_session(
    session: Session,
    *,
    tenant_id: str | None = DEMO_TENANT_ID,
    title: str = "",
    referral_id: str | None = None,
    patient_id: str | None = None,
    patient_label: str | None = None,
    therapist_id: str | None = None,
    therapist_label: str | None = None,
) -> dict[str, Any]:
    _ensure_documentation_label_columns(session)
    clean_tenant_id = tenant_id or DEMO_TENANT_ID
    referral = session.get(Referral, referral_id) if referral_id else None
    if referral_id and referral is None:
        raise KeyError(f"Unknown referral: {referral_id}")
    if referral is not None:
        clean_tenant_id = referral.tenant_id
        patient_id = patient_id or referral.patient_id
        patient_label = patient_label or referral.patient_name

    patient = session.get(Patient, patient_id) if patient_id else None
    if patient_id and patient is None:
        raise KeyError(f"Unknown patient: {patient_id}")
    if patient is not None and patient.tenant_id != clean_tenant_id:
        raise ValueError("Patient and documentation session tenants do not match.")
    if patient is not None:
        patient_label = patient_label or patient.display_name

    therapist = session.get(Therapist, therapist_id) if therapist_id else None
    if therapist_id and therapist is None:
        raise KeyError(f"Unknown therapist: {therapist_id}")
    if therapist is not None and therapist.tenant_id != clean_tenant_id:
        raise ValueError("Therapist and documentation session tenants do not match.")
    if therapist is not None:
        therapist_label = therapist_label or therapist.name

    item = DocumentationSession(
        tenant_id=clean_tenant_id,
        patient_id=patient_id or None,
        referral_id=referral_id or None,
        therapist_id=therapist_id or None,
        title=title.strip() or "Documentation session",
        patient_label=(patient_label or "").strip() or None,
        therapist_label=(therapist_label or "").strip() or None,
        status="active",
    )
    session.add(item)
    session.flush()
    return documentation_session_to_dict(item)


def list_documentation_sessions(session: Session, tenant_id: str | None = DEMO_TENANT_ID) -> list[dict[str, Any]]:
    _ensure_documentation_label_columns(session)
    query = select(DocumentationSession).order_by(DocumentationSession.updated_at.desc())
    if tenant_id:
        query = query.where(DocumentationSession.tenant_id == tenant_id)
    return [documentation_session_to_dict(item) for item in session.scalars(query)]


def list_documentation_patients(session: Session, tenant_id: str | None = DEMO_TENANT_ID) -> list[dict[str, Any]]:
    _ensure_documentation_label_columns(session)
    query = select(DocumentationSession).order_by(DocumentationSession.created_at.desc())
    if tenant_id:
        query = query.where(DocumentationSession.tenant_id == tenant_id)
    grouped: dict[str, dict[str, Any]] = {}
    for item in session.scalars(query):
        label = (item.patient_label or "").strip()
        if not label:
            continue
        key = label.lower()
        existing = grouped.setdefault(
            key,
            {
                "patient_label": label,
                "session_count": 0,
                "latest_session_at": None,
                "latest_session_id": None,
                "therapist_labels": set(),
            },
        )
        existing["session_count"] += 1
        if item.therapist_label:
            existing["therapist_labels"].add(item.therapist_label)
        session_at = item.created_at or item.updated_at
        if session_at and (existing["latest_session_at"] is None or session_at > existing["latest_session_at"]):
            existing["latest_session_at"] = session_at
            existing["latest_session_id"] = item.id
    patients = []
    for value in grouped.values():
        patients.append(
            {
                "patient_label": value["patient_label"],
                "session_count": value["session_count"],
                "latest_session_at": iso_or_none(value["latest_session_at"]),
                "latest_session_id": value["latest_session_id"],
                "therapist_labels": sorted(value["therapist_labels"]),
            }
        )
    return sorted(patients, key=lambda item: item["latest_session_at"] or "", reverse=True)


def list_documentation_patient_sessions(
    session: Session,
    *,
    patient_label: str,
    tenant_id: str | None = DEMO_TENANT_ID,
) -> list[dict[str, Any]]:
    _ensure_documentation_label_columns(session)
    clean_label = patient_label.strip()
    if not clean_label:
        raise ValueError("patient_label is required.")
    query = select(DocumentationSession).where(DocumentationSession.patient_label == clean_label)
    if tenant_id:
        query = query.where(DocumentationSession.tenant_id == tenant_id)
    items = list(session.scalars(query.order_by(DocumentationSession.created_at.desc(), DocumentationSession.updated_at.desc())))
    if not items:
        return []
    session_ids = [item.id for item in items]
    texts = list(
        session.scalars(
            select(DocumentationSessionText).where(DocumentationSessionText.documentation_session_id.in_(session_ids))
        )
    )
    notes = list(
        session.scalars(
            select(DocumentationSessionNote)
            .where(DocumentationSessionNote.documentation_session_id.in_(session_ids))
            .order_by(DocumentationSessionNote.created_at.desc())
        )
    )
    transcript_ids = {text.documentation_session_id for text in texts}
    latest_notes: dict[str, DocumentationSessionNote] = {}
    for note in notes:
        latest_notes.setdefault(note.documentation_session_id, note)
    return [
        documentation_patient_session_to_dict(item, item.id in transcript_ids, latest_notes.get(item.id))
        for item in items
    ]


def documentation_session_detail(session: Session, documentation_session_id: str) -> dict[str, Any]:
    _ensure_documentation_label_columns(session)
    item = session.get(DocumentationSession, documentation_session_id)
    if item is None:
        raise KeyError(f"Unknown documentation session: {documentation_session_id}")
    texts = list(
        session.scalars(
            select(DocumentationSessionText)
            .where(DocumentationSessionText.documentation_session_id == item.id)
            .order_by(DocumentationSessionText.created_at.desc())
        )
    )
    notes = list(
        session.scalars(
            select(DocumentationSessionNote)
            .where(DocumentationSessionNote.documentation_session_id == item.id)
            .order_by(DocumentationSessionNote.created_at.desc())
        )
    )
    return {
        "session": documentation_session_to_dict(item),
        "texts": [documentation_text_to_dict(text) for text in texts],
        "notes": [documentation_note_to_dict(note) for note in notes],
    }


def add_documentation_session_text(
    session: Session,
    *,
    documentation_session_id: str,
    extracted_text: str,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = session.get(DocumentationSession, documentation_session_id)
    if item is None:
        raise KeyError(f"Unknown documentation session: {documentation_session_id}")
    clean_text = extracted_text.strip()
    if not clean_text:
        raise ValueError("Extracted session text is required.")
    text = DocumentationSessionText(
        tenant_id=item.tenant_id,
        documentation_session_id=item.id,
        extracted_text=clean_text,
        input_used="extracted_session_text",
        raw_source_stored=False,
        source_metadata=json_safe(source_metadata or {"source": "manual_or_extracted_text"}),
    )
    item.updated_at = utc_now()
    session.add(text)
    session.flush()
    return documentation_text_to_dict(text)


def transcribe_documentation_session_audio(
    session: Session,
    *,
    documentation_session_id: str,
    audio_bytes: bytes,
    filename: str = "session-audio",
    enable_speaker_labeling: bool | None = None,
) -> dict[str, Any]:
    item = session.get(DocumentationSession, documentation_session_id)
    if item is None:
        raise KeyError(f"Unknown documentation session: {documentation_session_id}")
    if not audio_bytes:
        raise ValueError("Audio file is required.")

    provider = os.getenv("TRANSCRIPTION_PROVIDER", "huggingface").strip().lower() or "huggingface"
    if provider != "huggingface":
        raise ValueError("TRANSCRIPTION_PROVIDER must be 'huggingface' for audio transcription.")
    asr_model = os.getenv("HF_ASR_MODEL", "openai/whisper-large-v3-turbo").strip() or "openai/whisper-large-v3-turbo"
    speaker_labeling_enabled = (
        env_flag("ENABLE_TRANSCRIPT_SPEAKER_LABELING", False)
        if enable_speaker_labeling is None
        else enable_speaker_labeling
    )

    raw_transcript = transcribe_audio_bytes_with_hugging_face(audio_bytes, filename=filename, model=asr_model)
    final_transcript = raw_transcript
    speaker_labeling_method = None
    speaker_labeling_warning = None
    if speaker_labeling_enabled:
        try:
            final_transcript = cleanup_transcript_speaker_labels(raw_transcript)
            speaker_labeling_method = "llm_cleanup"
        except ValueError as exc:
            speaker_labeling_warning = str(exc)

    return add_documentation_session_text(
        session,
        documentation_session_id=item.id,
        extracted_text=final_transcript,
        source_metadata={
            "source": "audio_upload",
            "source_type": "audio",
            "extraction_method": "transcription",
            "raw_source_stored": False,
            "raw_source_deleted": True,
            "transcription_provider": "huggingface",
            "transcription_model": asr_model,
            "speaker_labeling_method": speaker_labeling_method,
            "speaker_labeling_reviewed": False if speaker_labeling_enabled else None,
            "speaker_labeling_enabled": speaker_labeling_enabled,
            "speaker_labeling_warning": speaker_labeling_warning,
            "original_filename": filename,
        },
    )


def transcription_configuration_status() -> dict[str, Any]:
    has_hf_hub = True
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        has_hf_hub = False
    return {
        "transcription_provider": os.getenv("TRANSCRIPTION_PROVIDER", "huggingface").strip().lower() or "huggingface",
        "transcription_model": os.getenv("HF_ASR_MODEL", "openai/whisper-large-v3-turbo").strip()
        or "openai/whisper-large-v3-turbo",
        "hf_token_configured": bool(os.getenv("HF_TOKEN")),
        "hf_base_url": os.getenv("HF_BASE_URL", "https://router.huggingface.co"),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "huggingface_hub_available": has_hf_hub,
        "speaker_labeling_enabled_default": env_flag("ENABLE_TRANSCRIPT_SPEAKER_LABELING", False),
    }


def update_documentation_session_text(
    session: Session,
    *,
    documentation_session_id: str,
    text_id: str,
    extracted_text: str,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = session.get(DocumentationSession, documentation_session_id)
    if item is None:
        raise KeyError(f"Unknown documentation session: {documentation_session_id}")
    text = session.get(DocumentationSessionText, text_id)
    if text is None:
        raise KeyError(f"Unknown documentation source text: {text_id}")
    if text.documentation_session_id != item.id:
        raise ValueError("Source text does not belong to the documentation session.")
    clean_text = extracted_text.strip()
    if not clean_text:
        raise ValueError("Extracted session text is required.")

    text.extracted_text = clean_text
    text.input_used = "extracted_session_text"
    text.raw_source_stored = False
    if source_metadata is not None:
        text.source_metadata = json_safe(source_metadata)
    text.updated_at = utc_now()
    item.updated_at = utc_now()
    session.flush()
    return documentation_text_to_dict(text)


def generate_documentation_note(
    session: Session,
    *,
    documentation_session_id: str,
    source_text_id: str | None = None,
) -> dict[str, Any]:
    item = session.get(DocumentationSession, documentation_session_id)
    if item is None:
        raise KeyError(f"Unknown documentation session: {documentation_session_id}")
    source_text = _select_source_text(session, item.id, source_text_id)
    generator = os.getenv("NOTE_GENERATOR", "fake").strip().lower() or "fake"
    if generator not in {"fake", "huggingface"}:
        raise ValueError("NOTE_GENERATOR must be 'fake' or 'huggingface'.")

    if generator == "huggingface":
        note_json, model = _generate_with_hugging_face(source_text.extracted_text)
    else:
        note_json, model = _generate_fake_note(source_text.extracted_text), "fake"

    validated = validate_session_note_json(note_json, source_text.extracted_text)
    note = DocumentationSessionNote(
        tenant_id=item.tenant_id,
        documentation_session_id=item.id,
        source_text_id=source_text.id,
        draft_json=validated,
        reviewed_json=None,
        status="draft",
        generator=generator,
        model=model,
        generated_at=utc_now(),
    )
    item.updated_at = utc_now()
    session.add(note)
    session.flush()
    return documentation_note_to_dict(note)


def save_reviewed_documentation_note(
    session: Session,
    *,
    note_id: str,
    reviewed_json: dict[str, Any],
    reviewer_id: str | None = None,
) -> dict[str, Any]:
    note = session.get(DocumentationSessionNote, note_id)
    if note is None:
        raise KeyError(f"Unknown documentation note: {note_id}")
    source_text = session.get(DocumentationSessionText, note.source_text_id)
    if source_text is None:
        raise KeyError(f"Unknown source text: {note.source_text_id}")
    if reviewer_id and session.get(User, reviewer_id) is None:
        reviewer_id = None
    note.reviewed_json = validate_session_note_json(reviewed_json, source_text.extracted_text)
    note.status = "reviewed"
    note.reviewed_at = utc_now()
    note.reviewer_id = reviewer_id
    note.updated_at = utc_now()
    doc_session = session.get(DocumentationSession, note.documentation_session_id)
    if doc_session is not None:
        doc_session.updated_at = utc_now()
    return documentation_note_to_dict(note)


def validate_session_note_json(value: Any, source_text: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Session note must be a JSON object.")
    missing = NOTE_KEYS - set(value)
    extra = set(value) - NOTE_KEYS
    if missing:
        raise ValueError(f"Session note JSON is missing required keys: {', '.join(sorted(missing))}.")
    if extra:
        raise ValueError(f"Session note JSON has unsupported keys: {', '.join(sorted(extra))}.")
    if value.get("version") != NOTE_VERSION:
        raise ValueError(f"Session note version must be {NOTE_VERSION}.")
    if not isinstance(value.get("summary"), str):
        raise ValueError("summary must be a string.")
    source_basis = value.get("source_basis")
    if not isinstance(source_basis, dict):
        raise ValueError("source_basis must be an object.")
    if source_basis.get("raw_source_stored") is not False:
        raise ValueError("source_basis.raw_source_stored must be false.")
    if source_basis.get("input_used") != "extracted_session_text":
        raise ValueError("source_basis.input_used must be extracted_session_text.")
    for key in LIST_KEYS:
        if not isinstance(value.get(key), list) or not all(isinstance(item, str) for item in value[key]):
            raise ValueError(f"{key} must be a list of strings.")
    risk = value.get("risk_or_safety")
    if not isinstance(risk, dict):
        raise ValueError("risk_or_safety must be an object.")
    if not isinstance(risk.get("status"), str) or not isinstance(risk.get("details"), str):
        raise ValueError("risk_or_safety.status and risk_or_safety.details must be strings.")
    _validate_clinical_safety(value, source_text or "")
    return json_safe(value)


def documentation_session_to_dict(item: DocumentationSession) -> dict[str, Any]:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "patient_id": item.patient_id,
        "patient_label": item.patient_label,
        "referral_id": item.referral_id,
        "therapist_id": item.therapist_id,
        "therapist_label": item.therapist_label,
        "title": item.title,
        "status": item.status,
        "created_at": iso_or_none(item.created_at),
        "updated_at": iso_or_none(item.updated_at),
    }


def documentation_text_to_dict(text: DocumentationSessionText) -> dict[str, Any]:
    return {
        "id": text.id,
        "tenant_id": text.tenant_id,
        "documentation_session_id": text.documentation_session_id,
        "extracted_text": text.extracted_text,
        "input_used": text.input_used,
        "raw_source_stored": text.raw_source_stored,
        "source_metadata": json_safe(text.source_metadata),
        "created_at": iso_or_none(text.created_at),
        "updated_at": iso_or_none(text.updated_at),
    }


def documentation_note_to_dict(note: DocumentationSessionNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "tenant_id": note.tenant_id,
        "documentation_session_id": note.documentation_session_id,
        "source_text_id": note.source_text_id,
        "draft_json": json_safe(note.draft_json),
        "reviewed_json": json_safe(note.reviewed_json),
        "status": note.status,
        "generator": note.generator,
        "model": note.model,
        "generated_at": iso_or_none(note.generated_at),
        "reviewed_at": iso_or_none(note.reviewed_at),
        "reviewer_id": note.reviewer_id,
        "created_at": iso_or_none(note.created_at),
        "updated_at": iso_or_none(note.updated_at),
    }


def documentation_patient_session_to_dict(
    item: DocumentationSession,
    has_transcript: bool,
    latest_note: DocumentationSessionNote | None,
) -> dict[str, Any]:
    note_status = latest_note.status if latest_note is not None else "no_draft"
    return {
        **documentation_session_to_dict(item),
        "session_date": iso_or_none(item.created_at),
        "transcript_status": "transcript stored" if has_transcript else "no transcript",
        "has_transcript": has_transcript,
        "note_status": note_status,
        "latest_note_id": latest_note.id if latest_note is not None else None,
        "reviewed_at": iso_or_none(latest_note.reviewed_at) if latest_note is not None else None,
        "generated_at": iso_or_none(latest_note.generated_at) if latest_note is not None else None,
    }


def _select_source_text(
    session: Session,
    documentation_session_id: str,
    source_text_id: str | None,
) -> DocumentationSessionText:
    if source_text_id:
        text = session.get(DocumentationSessionText, source_text_id)
        if text is None:
            raise KeyError(f"Unknown documentation source text: {source_text_id}")
        if text.documentation_session_id != documentation_session_id:
            raise ValueError("Source text does not belong to the documentation session.")
        return text
    text = session.scalar(
        select(DocumentationSessionText)
        .where(DocumentationSessionText.documentation_session_id == documentation_session_id)
        .order_by(DocumentationSessionText.created_at.desc())
        .limit(1)
    )
    if text is None:
        raise ValueError("Add extracted session text before generating a note.")
    return text


def _ensure_documentation_label_columns(session: Session) -> None:
    bind = session.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("documentation_sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("documentation_sessions")}
    if "patient_label" not in columns:
        _add_documentation_column_if_missing(session, "patient_label")
    if "therapist_label" not in columns:
        _add_documentation_column_if_missing(session, "therapist_label")


def _add_documentation_column_if_missing(session: Session, column_name: str) -> None:
    try:
        session.execute(text(f"ALTER TABLE documentation_sessions ADD COLUMN {column_name} VARCHAR(255)"))
    except OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _generate_fake_note(source_text: str) -> dict[str, Any]:
    sentences = _sentences(source_text)
    lower = source_text.lower()
    risk_not_assessed = "not directly assessed" in lower or "not assessed" in lower
    risk_denied = any(phrase in lower for phrase in ["denied risk", "denied safety concerns", "no safety concerns"])
    risk_phrases = [
        "not wanting to be alive",
        "doesn't want to be alive",
        "does not want to be alive",
        "suicide",
        "suicidal",
        "self-harm",
        "self harm",
        "harm myself",
        "harm themselves",
        "harm others",
        "harming others",
    ]
    risk_mentions = [sentence for sentence in sentences if any(phrase in sentence.lower() for phrase in risk_phrases)]
    risk_status = "mentioned" if risk_mentions else "not_assessed" if risk_not_assessed or not risk_denied else "assessed_denied"
    risk_details = "Risk and safety concerns were not directly assessed during this session." if risk_not_assessed else ""
    if risk_mentions:
        risk_details = " ".join(risk_mentions)
    if risk_denied and not risk_not_assessed:
        risk_details = "Source text states that risk or safety concerns were assessed and denied."

    interventions = [sentence for sentence in sentences if "therapist" in sentence.lower()]
    subjective = [sentence for sentence in sentences if "client" in sentence.lower()]
    topics = []
    for phrase in ["sleep difficulties", "unfinished work tasks", "tension with their partner", "grounding exercise"]:
        if phrase in lower:
            topics.append(phrase)

    flags = []
    if risk_not_assessed:
        flags.append("Risk and safety were not directly assessed in the provided text.")
    if not interventions:
        flags.append("Therapist interventions are missing or unclear in the provided text.")
    if not any("plan" in sentence.lower() for sentence in sentences):
        flags.append("Plan was not directly documented in the provided text.")

    return {
        "version": NOTE_VERSION,
        "summary": "Test-only fake generator output. Review the stored transcript and replace this with a clinically reviewed summary.",
        "source_basis": {
            "raw_source_stored": False,
            "input_used": "extracted_session_text",
        },
        "presenting_topics": topics,
        "subjective": subjective,
        "objective_observations": [],
        "interventions": interventions,
        "patient_response": [],
        "risk_or_safety": {
            "status": risk_status,
            "details": risk_details,
        },
        "plan": [sentence for sentence in sentences if "plan" in sentence.lower()],
        "uncertainty_flags": flags,
    }


def _generate_with_hugging_face(source_text: str) -> tuple[dict[str, Any], str]:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN is required when NOTE_GENERATOR=huggingface.")
    base_url = hf_chat_base_url()
    model = os.getenv("HF_LLM_MODEL", DEFAULT_HF_MODEL)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": f"Extracted session text:\n{source_text}"},
        ],
        "temperature": 0,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Hugging Face note generation failed: HTTP {exc.code} {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Hugging Face note generation failed: {exc.reason}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Hugging Face response did not include a chat completion message.") from exc
    try:
        return json.loads(_strip_json_fence(content)), model
    except json.JSONDecodeError as exc:
        raise ValueError("Hugging Face returned invalid JSON. No draft was saved.") from exc


def transcribe_audio_bytes_with_hugging_face(audio_bytes: bytes, *, filename: str, model: str) -> str:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN is required when TRANSCRIPTION_PROVIDER=huggingface.")
    if shutil.which("ffmpeg") is None:
        raise ValueError("ffmpeg is required for audio transcription normalization.")
    try:
        from huggingface_hub import InferenceClient
    except ImportError as exc:
        raise ValueError("huggingface_hub is required for Hugging Face ASR. Install requirements first.") from exc

    base_url = os.getenv("HF_ASR_BASE_URL", os.getenv("HF_BASE_URL", "https://router.huggingface.co")).rstrip("/")
    chunk_seconds = int(os.getenv("TRANSCRIPTION_CHUNK_SECONDS", "900"))
    with tempfile.TemporaryDirectory(prefix="lumen-audio-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        suffix = Path(filename or "session-audio").suffix or ".audio"
        raw_path = tmp_path / f"raw{suffix}"
        normalized_path = tmp_path / "normalized.wav"
        raw_path.write_bytes(audio_bytes)
        run_ffmpeg(["ffmpeg", "-y", "-i", str(raw_path), "-ac", "1", "-ar", "16000", str(normalized_path)])
        chunk_paths = split_audio_for_transcription(normalized_path, tmp_path, chunk_seconds)
        client = InferenceClient(base_url=base_url, api_key=token)
        transcripts = []
        for chunk_path in chunk_paths:
            result = client.automatic_speech_recognition(chunk_path, model=model)
            text_value = getattr(result, "text", None)
            if text_value is None and isinstance(result, dict):
                text_value = result.get("text")
            if text_value:
                transcripts.append(str(text_value).strip())
        transcript = "\n".join(item for item in transcripts if item).strip()
        if not transcript:
            raise ValueError("Hugging Face ASR returned an empty transcript.")
        return transcript


def run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown ffmpeg error").strip()
        raise ValueError(f"ffmpeg audio processing failed: {detail[:500]}")


def split_audio_for_transcription(normalized_path: Path, tmp_path: Path, chunk_seconds: int) -> list[Path]:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    output_pattern = chunks_dir / "chunk_%03d.wav"
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(normalized_path),
            "-f",
            "segment",
            "-segment_time",
            str(max(chunk_seconds, 30)),
            "-reset_timestamps",
            "1",
            str(output_pattern),
        ]
    )
    chunk_paths = sorted(chunks_dir.glob("chunk_*.wav"))
    return chunk_paths or [normalized_path]


def cleanup_transcript_speaker_labels(transcript: str) -> str:
    provider = os.getenv("TRANSCRIPT_SPEAKER_LABELING_PROVIDER", "huggingface").strip().lower() or "huggingface"
    if provider != "huggingface":
        raise ValueError("TRANSCRIPT_SPEAKER_LABELING_PROVIDER must be 'huggingface'.")
    token = os.getenv("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN is required for Hugging Face transcript speaker labeling.")
    base_url = hf_chat_base_url()
    model = os.getenv("HF_LLM_MODEL", DEFAULT_HF_MODEL)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": transcript_cleanup_prompt()},
            {"role": "user", "content": f"Raw transcript:\n{transcript}"},
        ],
        "temperature": 0,
        "max_tokens": 2200,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
        cleaned = data["choices"][0]["message"]["content"].strip()
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Transcript speaker labeling failed: {exc}") from exc
    return cleaned or transcript


def transcript_cleanup_prompt() -> str:
    return """
Format the raw therapy session transcript into likely speaker turns.
Use only these labels when supported by the text:
Therapist:
Patient:
Speaker 1:
Speaker 2:
Unknown speaker:

Rules:
- Do not invent content.
- Do not add clinical facts.
- Do not remove clinically relevant wording.
- Do not change meaning.
- Preserve uncertainty.
- If speaker role is unclear, use Speaker 1 / Speaker 2 instead of guessing.
- If a sentence cannot be confidently assigned, leave it under Unknown speaker.
- Keep all clinically relevant risk/safety wording exactly as present.
- Return only the cleaned transcript text, not JSON or commentary.
""".strip()


def hf_chat_base_url() -> str:
    base_url = os.getenv("HF_BASE_URL", DEFAULT_HF_BASE_URL).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _system_prompt() -> str:
    return """
You generate structured psychotherapy session notes. Return valid JSON only.
Use exactly this JSON shape:
{
  "version": "session_note_v0.1",
  "summary": "",
  "source_basis": {
    "raw_source_stored": false,
    "input_used": "extracted_session_text"
  },
  "presenting_topics": [],
  "subjective": [],
  "objective_observations": [],
  "interventions": [],
  "patient_response": [],
  "risk_or_safety": {
    "status": "not_assessed",
    "details": ""
  },
  "plan": [],
  "uncertainty_flags": []
}
Clinical safety rules:
- Use only the provided extracted session text.
- Do not invent facts.
- Do not infer diagnoses, symptoms, mental states, or clinical labels unless explicitly stated in the source text.
- Prefer the client's and therapist's actual wording.
- Do not convert "stress", "rumination", "overwhelm", "activation", or "physical signs of stress" into "anxiety" unless the source explicitly uses "anxiety".
- Do not create diagnoses unless explicitly stated.
- Do not add clinical interpretation beyond what is supported by the text.
- Separate subjective report, objective observations, interventions, patient response, risk/safety, and plan.
- objective_observations must only include observable in-session behavior or therapeutic process.
- Client-reported symptoms, experiences, sleep, thoughts, mood, and behavior belong in subjective unless directly observed during the session.
- If risk/safety was not discussed, use status "not_assessed".
- If risk/safety wording is present, preserve the source wording in risk_or_safety.details, including self-harm, not wanting to be alive, suicide, and harm-to-others wording.
- Do not write "no risk", "denied risk", or "no safety concerns" unless the source explicitly says risk was assessed and denied.
- Add uncertainty flags for missing, unclear, or not directly assessed areas.
""".strip()


def _validate_clinical_safety(note: dict[str, Any], source_text: str) -> None:
    source_lower = source_text.lower()
    note_text = json.dumps(note, ensure_ascii=False).lower()
    if "anxiety" in note_text and "anxiety" not in source_lower:
        raise ValueError("Generated note contains unsupported 'anxiety' wording.")
    diagnoses = ["diagnosis", "diagnosed", "major depressive", "ptsd", "generalized anxiety disorder"]
    if any(term in note_text for term in diagnoses) and not any(term in source_lower for term in diagnoses):
        raise ValueError("Generated note appears to contain an unsupported diagnosis.")
    denied_terms = ["no risk", "denied risk", "no safety concerns"]
    assessed_denied = any(term in source_lower for term in denied_terms)
    if any(term in note_text for term in denied_terms) and not assessed_denied:
        raise ValueError("Generated note contains unsupported risk-denial wording.")
    if "not directly assessed" in source_lower and note.get("risk_or_safety", {}).get("status") != "not_assessed":
        raise ValueError("risk_or_safety.status must be not_assessed when risk was not directly assessed.")


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()]


def _strip_json_fence(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
    return clean.strip()
