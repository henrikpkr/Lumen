"""Configuration helpers for the psychology suite app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_URL = f"sqlite:///{BASE_DIR / 'psychology_suite_dev.db'}"


def _load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def database_url() -> str:
    url = os.getenv("PSYCH_SUITE_DATABASE_URL", "").strip() or DEFAULT_SQLITE_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    audio_storage_dir: Path
    audio_encryption_key: str | None
    session_days: int
    retention_days: int
    max_upload_mb: int
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    llm_model: str
    ollama_base_url: str
    session_cookie_name: str
    bootstrap_email: str | None
    bootstrap_password: str | None
    bootstrap_name: str | None


def load_settings() -> Settings:
    _load_env_file()
    return Settings(
        database_url=database_url(),
        audio_storage_dir=BASE_DIR / "storage" / "audio",
        audio_encryption_key=os.getenv("PSYCH_SUITE_AUDIO_KEY"),
        session_days=int(os.getenv("PSYCH_SUITE_SESSION_DAYS", "7")),
        retention_days=int(os.getenv("PSYCH_SUITE_RETENTION_DAYS", "30")),
        max_upload_mb=int(os.getenv("PSYCH_SUITE_MAX_UPLOAD_MB", "50")),
        whisper_model=os.getenv("PSYCH_SUITE_WHISPER_MODEL", "base"),
        whisper_device=os.getenv("PSYCH_SUITE_WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("PSYCH_SUITE_WHISPER_COMPUTE", "int8"),
        llm_model=os.getenv("PSYCH_SUITE_LLM_MODEL", "qwen3:8b"),
        ollama_base_url=os.getenv("PSYCH_SUITE_OLLAMA_BASE_URL", "http://localhost:11434"),
        session_cookie_name=os.getenv("PSYCH_SUITE_SESSION_COOKIE", "psych_suite_session"),
        bootstrap_email=os.getenv("PSYCH_SUITE_BOOTSTRAP_EMAIL"),
        bootstrap_password=os.getenv("PSYCH_SUITE_BOOTSTRAP_PASSWORD"),
        bootstrap_name=os.getenv("PSYCH_SUITE_BOOTSTRAP_NAME"),
    )
