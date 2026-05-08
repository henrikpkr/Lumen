"""Security and authentication helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .config import load_settings


def hash_password(password: str, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120_000)
    return f"{salt_value}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    check = hash_password(password, salt)
    return hmac.compare_digest(check, stored)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def session_expiry() -> datetime:
    settings = load_settings()
    return datetime.now(timezone.utc) + timedelta(days=settings.session_days)
