"""JSON-backed storage for environments without SQLAlchemy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .config import BASE_DIR, load_settings
from .security import hash_password


DATA_PATH = BASE_DIR / "storage" / "psychology_suite_data.json"
LOCK = Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _new_id() -> str:
    return str(uuid4())


def _load() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {
            "psychologists": [],
            "auth_sessions": [],
            "patients": [],
            "sessions": [],
            "consents": [],
        }
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_bootstrap_user() -> None:
    settings = load_settings()
    if not (settings.bootstrap_email and settings.bootstrap_password and settings.bootstrap_name):
        return
    email = settings.bootstrap_email.strip().lower()
    with LOCK:
        data = _load()
        if any(user["email"] == email for user in data["psychologists"]):
            return
        user = {
            "id": _new_id(),
            "name": settings.bootstrap_name.strip(),
            "email": email,
            "password_hash": hash_password(settings.bootstrap_password),
            "active": True,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
        }
        data["psychologists"].append(user)
        _save(data)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with LOCK:
        data = _load()
        return next((user for user in data["psychologists"] if user["email"] == email), None)


def get_user(user_id: str) -> dict[str, Any] | None:
    with LOCK:
        data = _load()
        return next((user for user in data["psychologists"] if user["id"] == user_id), None)


def create_auth_session(psychologist_id: str, expires_at: str) -> str:
    session_id = _new_id()
    with LOCK:
        data = _load()
        data["auth_sessions"].append(
            {
                "id": session_id,
                "psychologist_id": psychologist_id,
                "expires_at": expires_at,
                "revoked": False,
                "created_at": _iso_now(),
            }
        )
        _save(data)
    return session_id


def revoke_auth_session(session_id: str) -> None:
    with LOCK:
        data = _load()
        for session in data["auth_sessions"]:
            if session["id"] == session_id:
                session["revoked"] = True
        _save(data)


def get_active_session(session_id: str) -> dict[str, Any] | None:
    now = _utc_now()
    with LOCK:
        data = _load()
        for session in data["auth_sessions"]:
            if session["id"] != session_id:
                continue
            if session.get("revoked"):
                return None
            expires = datetime.fromisoformat(session["expires_at"])
            if expires <= now:
                return None
            return session
    return None


def list_patients(psychologist_id: str) -> list[dict[str, Any]]:
    with LOCK:
        data = _load()
        return [
            patient
            for patient in sorted(
                data["patients"],
                key=lambda row: row.get("updated_at", ""),
                reverse=True,
            )
            if patient["psychologist_id"] == psychologist_id
        ]


def create_patient(psychologist_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    patient = {
        "id": _new_id(),
        "psychologist_id": psychologist_id,
        "display_name": payload.get("display_name", "").strip(),
        "date_of_birth": payload.get("date_of_birth"),
        "contact_email": payload.get("contact_email"),
        "contact_phone": payload.get("contact_phone"),
        "notes": payload.get("notes"),
        "active": True,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    with LOCK:
        data = _load()
        data["patients"].append(patient)
        _save(data)
    return patient


def get_patient(psychologist_id: str, patient_id: str) -> dict[str, Any] | None:
    with LOCK:
        data = _load()
        return next(
            (
                patient
                for patient in data["patients"]
                if patient["id"] == patient_id and patient["psychologist_id"] == psychologist_id
            ),
            None,
        )


def update_patient(psychologist_id: str, patient_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    with LOCK:
        data = _load()
        for patient in data["patients"]:
            if patient["id"] == patient_id and patient["psychologist_id"] == psychologist_id:
                for key, value in updates.items():
                    if value is not None:
                        patient[key] = value
                patient["updated_at"] = _iso_now()
                _save(data)
                return patient
    return None


def delete_patient(psychologist_id: str, patient_id: str) -> list[str]:
    with LOCK:
        data = _load()
        audio_paths: list[str] = []
        data["patients"] = [
            patient
            for patient in data["patients"]
            if not (patient["id"] == patient_id and patient["psychologist_id"] == psychologist_id)
        ]
        sessions = []
        for session in data["sessions"]:
            if session["patient_id"] == patient_id and session["psychologist_id"] == psychologist_id:
                if session.get("audio_path"):
                    audio_paths.append(session["audio_path"])
                continue
            sessions.append(session)
        data["sessions"] = sessions
        _save(data)
    return audio_paths


def list_sessions(psychologist_id: str, patient_id: str | None = None) -> list[dict[str, Any]]:
    with LOCK:
        data = _load()
        rows = [
            session
            for session in data["sessions"]
            if session["psychologist_id"] == psychologist_id
            and (patient_id is None or session["patient_id"] == patient_id)
        ]
        return sorted(rows, key=lambda row: row.get("started_at", ""), reverse=True)


def create_session(psychologist_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = {
        "id": _new_id(),
        "psychologist_id": psychologist_id,
        "patient_id": payload.get("patient_id"),
        "status": "draft",
        "note_format": payload.get("note_format", "soap"),
        "transcript_text": None,
        "note_text": None,
        "audio_path": None,
        "audio_duration_seconds": None,
        "transcript_confirmed": False,
        "low_confidence": False,
        "transcript_meta": None,
        "started_at": _iso_now(),
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    with LOCK:
        data = _load()
        data["sessions"].append(session)
        _save(data)
    return session


def get_session(psychologist_id: str, session_id: str) -> dict[str, Any] | None:
    with LOCK:
        data = _load()
        return next(
            (
                session
                for session in data["sessions"]
                if session["id"] == session_id and session["psychologist_id"] == psychologist_id
            ),
            None,
        )


def update_session(psychologist_id: str, session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    with LOCK:
        data = _load()
        for session in data["sessions"]:
            if session["id"] == session_id and session["psychologist_id"] == psychologist_id:
                for key, value in updates.items():
                    if value is not None:
                        session[key] = value
                session["updated_at"] = _iso_now()
                _save(data)
                return session
    return None


def delete_session(psychologist_id: str, session_id: str) -> str | None:
    with LOCK:
        data = _load()
        audio_path = None
        sessions = []
        for session in data["sessions"]:
            if session["id"] == session_id and session["psychologist_id"] == psychologist_id:
                audio_path = session.get("audio_path")
                continue
            sessions.append(session)
        data["sessions"] = sessions
        _save(data)
    return audio_path


def set_consent(session_id: str, version: str) -> dict[str, Any]:
    consent = {
        "id": _new_id(),
        "session_id": session_id,
        "consent_text_version": version,
        "accepted_at": _iso_now(),
    }
    with LOCK:
        data = _load()
        data["consents"].append(consent)
        _save(data)
    return consent


def purge_sessions_before(psychologist_id: str, cutoff: datetime) -> list[str]:
    with LOCK:
        data = _load()
        kept = []
        removed_audio: list[str] = []
        for session in data["sessions"]:
            if session["psychologist_id"] != psychologist_id:
                kept.append(session)
                continue
            started = datetime.fromisoformat(session["started_at"])
            if started < cutoff:
                if session.get("audio_path"):
                    removed_audio.append(session["audio_path"])
                continue
            kept.append(session)
        data["sessions"] = kept
        _save(data)
    return removed_audio
