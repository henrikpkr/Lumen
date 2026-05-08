"""Pydantic request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class PsychologistProfile(BaseModel):
    id: str
    name: str
    email: str


class PatientCreateRequest(BaseModel):
    display_name: str
    date_of_birth: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None


class PatientUpdateRequest(BaseModel):
    display_name: str | None = None
    date_of_birth: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    active: bool | None = None


class SessionCreateRequest(BaseModel):
    patient_id: str
    note_format: str = "soap"


class SessionUpdateRequest(BaseModel):
    status: str | None = None
    note_text: str | None = None
    note_format: str | None = None


class SummarizeRequest(BaseModel):
    transcript: str | None = None
    session_id: str | None = None


class ConsentRequest(BaseModel):
    consent_text_version: str = "v1"


class TranscriptConfirmRequest(BaseModel):
    confirmed: bool = True


class SessionNoteUpdateRequest(BaseModel):
    note_text: str
    status: str | None = None


class RetentionRequest(BaseModel):
    dry_run: bool = False
    retention_days: int | None = None


class TranscriptValidation(BaseModel):
    valid: bool
    error: str | None = None


class TranscriptionResponse(BaseModel):
    transcript: str
    low_confidence: bool
    meta: dict = Field(default_factory=dict)
