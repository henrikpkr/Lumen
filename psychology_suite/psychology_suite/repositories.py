"""Data access helpers for the psychology suite app."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import AuditLog, AuthSession, Consent, Patient, Psychologist, Session as PsychSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_audit(
    session: Session,
    *,
    psychologist_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: str | None = None,
) -> None:
    session.add(
        AuditLog(
            psychologist_id=psychologist_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )


def get_psychologist_by_email(session: Session, email: str) -> Psychologist | None:
    return session.scalar(select(Psychologist).where(Psychologist.email == email))


def get_active_session(session: Session, session_id: str) -> AuthSession | None:
    return session.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.revoked.is_(False),
            AuthSession.expires_at > utc_now(),
        )
    )


def revoke_session(session: Session, session_id: str) -> None:
    auth = session.get(AuthSession, session_id)
    if auth:
        auth.revoked = True


def list_patients(session: Session, psychologist_id: str) -> list[Patient]:
    return list(
        session.scalars(
            select(Patient)
            .where(Patient.psychologist_id == psychologist_id)
            .order_by(Patient.updated_at.desc())
        )
    )


def list_sessions(session: Session, psychologist_id: str, patient_id: str | None = None) -> list[PsychSession]:
    query = select(PsychSession).where(PsychSession.psychologist_id == psychologist_id)
    if patient_id:
        query = query.where(PsychSession.patient_id == patient_id)
    return list(session.scalars(query.order_by(PsychSession.started_at.desc())))


def delete_patient(session: Session, psychologist_id: str, patient_id: str) -> None:
    patient = session.get(Patient, patient_id)
    if not patient or patient.psychologist_id != psychologist_id:
        raise KeyError("Patient not found")
    session.delete(patient)


def delete_session(session: Session, psychologist_id: str, session_id: str) -> None:
    item = session.get(PsychSession, session_id)
    if not item or item.psychologist_id != psychologist_id:
        raise KeyError("Session not found")
    session.delete(item)


def ensure_patient(session: Session, psychologist_id: str, patient_id: str) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None or patient.psychologist_id != psychologist_id:
        raise KeyError("Patient not found")
    return patient


def ensure_session(session: Session, psychologist_id: str, session_id: str) -> PsychSession:
    item = session.get(PsychSession, session_id)
    if item is None or item.psychologist_id != psychologist_id:
        raise KeyError("Session not found")
    return item


def set_consents(session: Session, session_id: str, version: str) -> Consent:
    consent = Consent(session_id=session_id, consent_text_version=version)
    session.add(consent)
    return consent


def delete_audio_for_sessions(session: Session, session_ids: Iterable[str]) -> list[str]:
    paths: list[str] = []
    for item in session.scalars(select(PsychSession).where(PsychSession.id.in_(list(session_ids)))):
        if item.audio_path:
            paths.append(item.audio_path)
            item.audio_path = None
    return paths


def purge_sessions_before(session: Session, cutoff: datetime) -> list[PsychSession]:
    targets = list(session.scalars(select(PsychSession).where(PsychSession.started_at < cutoff)))
    for item in targets:
        session.delete(item)
    return targets


def delete_audit_logs_before(session: Session, cutoff: datetime) -> int:
    result = session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    return int(result.rowcount or 0)
