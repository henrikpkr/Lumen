"""Data store abstraction that falls back to JSON when SQLAlchemy is unavailable."""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    import sqlalchemy  # noqa: F401

    SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:
    SQLALCHEMY_AVAILABLE = False


if SQLALCHEMY_AVAILABLE:
    from .db import init_database, session_scope  # type: ignore[assignment]
    from .models import AuthSession, Patient, Psychologist, Session as PsychSession  # noqa: F401
    from .repositories import (
        delete_patient,
        delete_session,
        ensure_patient,
        ensure_session,
        get_active_session,
        get_psychologist_by_email,
        list_patients,
        list_sessions,
        revoke_session,
        set_consents,
        write_audit,
    )
    from .seed import seed_initial_user

    def bootstrap() -> None:
        init_database()
        seed_initial_user()

else:
    from .lite_store import (  # type: ignore[assignment]
        create_auth_session,
        create_patient,
        create_session,
        delete_patient,
        delete_session,
        ensure_bootstrap_user,
        get_active_session,
        get_patient,
        get_session,
        get_user,
        get_user_by_email,
        list_patients,
        list_sessions,
        revoke_auth_session,
        set_consent,
        update_patient,
        update_session,
        purge_sessions_before,
    )

    def bootstrap() -> None:
        ensure_bootstrap_user()
