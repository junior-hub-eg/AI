"""Validation and decoding of audio sent by the backend (processed in memory only)."""

from __future__ import annotations

import base64
import binascii
import io
import wave
from dataclasses import dataclass

from app.core.errors import AudioTooLarge, AudioUnsupported, InvalidRequest

_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
}


@dataclass(frozen=True)
class DecodedAudio:
    data: bytes
    mime_type: str
    extension: str

    @property
    def filename(self) -> str:
        return f"answer{self.extension}"


def normalize_mime(mime_type: str) -> str:
    """'audio/webm;codecs=opus' -> 'audio/webm'."""
    return mime_type.split(";", 1)[0].strip().lower()


def decode_audio(audio_base64: str, mime_type: str, *, max_bytes: int, max_seconds: int) -> DecodedAudio:
    mime = normalize_mime(mime_type)
    if mime not in _EXTENSIONS:
        raise AudioUnsupported(f"Unsupported audio type: {mime or 'unknown'}")
    if len(audio_base64) * 3 // 4 > max_bytes + 3:
        raise AudioTooLarge(f"Audio is larger than {max_bytes // (1024 * 1024)} MB")
    try:
        data = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidRequest("audio_base64 is not valid base64") from None
    if not data:
        raise InvalidRequest("Audio is empty")
    if len(data) > max_bytes:
        raise AudioTooLarge(f"Audio is larger than {max_bytes // (1024 * 1024)} MB")
    if _EXTENSIONS[mime] == ".wav":
        _check_wav_duration(data, max_seconds)
    return DecodedAudio(data=data, mime_type=mime, extension=_EXTENSIONS[mime])


def _check_wav_duration(data: bytes, max_seconds: int) -> None:
    """Duration can only be read cheaply from WAV; other formats rely on the size cap."""
    try:
        with wave.open(io.BytesIO(data)) as wav:
            seconds = wav.getnframes() / float(wav.getframerate() or 1)
    except (wave.Error, EOFError):
        return
    if seconds > max_seconds:
        raise AudioTooLarge(f"Audio is longer than {max_seconds} seconds")
