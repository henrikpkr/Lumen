"""Local audio storage helpers with optional encryption."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import os

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AESGCM = None

from .config import load_settings


@dataclass(frozen=True)
class StoredAudio:
    relative_path: str
    size_bytes: int


def _key_bytes(key: str) -> bytes:
    raw = key.strip()
    try:
        if raw.startswith("base64:"):
            return base64.b64decode(raw.split(":", 1)[1])
        return bytes.fromhex(raw)
    except Exception as exc:
        raise ValueError("Invalid PSYCH_SUITE_AUDIO_KEY format.") from exc


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def store_audio(content: bytes, filename: str) -> StoredAudio:
    settings = load_settings()
    _ensure_dir(settings.audio_storage_dir)
    safe_name = _safe_filename(filename)
    target = settings.audio_storage_dir / safe_name

    if settings.audio_encryption_key:
        if AESGCM is None:
            raise RuntimeError("cryptography is required for encrypted audio storage.")
        key = _key_bytes(settings.audio_encryption_key)
        if len(key) not in {16, 24, 32}:
            raise ValueError("Audio encryption key must be 16, 24, or 32 bytes.")
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        encrypted = aesgcm.encrypt(nonce, content, None)
        payload = nonce + encrypted
        target.write_bytes(payload)
        return StoredAudio(relative_path=str(target.relative_to(settings.audio_storage_dir.parent)), size_bytes=len(payload))

    target.write_bytes(content)
    return StoredAudio(relative_path=str(target.relative_to(settings.audio_storage_dir.parent)), size_bytes=len(content))


def load_audio(relative_path: str) -> bytes:
    settings = load_settings()
    path = settings.audio_storage_dir.parent / relative_path
    data = path.read_bytes()
    if settings.audio_encryption_key:
        if AESGCM is None:
            raise RuntimeError("cryptography is required to decrypt audio files.")
        key = _key_bytes(settings.audio_encryption_key)
        aesgcm = AESGCM(key)
        nonce, ciphertext = data[:12], data[12:]
        return aesgcm.decrypt(nonce, ciphertext, None)
    return data


def delete_audio(relative_path: str) -> None:
    settings = load_settings()
    path = settings.audio_storage_dir.parent / relative_path
    if path.exists():
        path.unlink()


def _safe_filename(value: str) -> str:
    base = Path(value).name
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in base)
    return safe[:120] or "audio"
