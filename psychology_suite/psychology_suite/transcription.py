"""Local Whisper transcription helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from faster_whisper import WhisperModel

from .config import load_settings


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    low_confidence: bool
    meta: dict[str, Any]


_MODEL: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        settings = load_settings()
        _MODEL = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _MODEL


def transcribe_file(path: str) -> TranscriptionResult:
    model = _get_model()
    segments, info = model.transcribe(path, beam_size=5)
    transcript = " ".join(segment.text for segment in segments).strip()
    avg_logprob = getattr(info, "avg_logprob", None)
    no_speech_prob = getattr(info, "no_speech_prob", None)
    low_confidence = False
    if isinstance(avg_logprob, (int, float)) and avg_logprob < -1.0:
        low_confidence = True
    if isinstance(no_speech_prob, (int, float)) and no_speech_prob > 0.6:
        low_confidence = True
    meta = {
        "avg_logprob": avg_logprob,
        "no_speech_prob": no_speech_prob,
        "language": getattr(info, "language", None),
        "duration": getattr(info, "duration", None),
    }
    return TranscriptionResult(transcript=transcript, low_confidence=low_confidence, meta=meta)
