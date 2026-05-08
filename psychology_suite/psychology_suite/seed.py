"""Seed initial psychologist for local usage."""

from __future__ import annotations

from sqlalchemy import select

from .config import load_settings
from .db import session_scope
from .models import Psychologist
from .security import hash_password


def seed_initial_user() -> None:
    settings = load_settings()
    if not (settings.bootstrap_email and settings.bootstrap_password and settings.bootstrap_name):
        return
    email = settings.bootstrap_email.strip().lower()
    with session_scope() as session:
        existing = session.scalar(select(Psychologist).where(Psychologist.email == email))
        if existing:
            return
        user = Psychologist(
            name=settings.bootstrap_name.strip(),
            email=email,
            password_hash=hash_password(settings.bootstrap_password),
        )
        session.add(user)
