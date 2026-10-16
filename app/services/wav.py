"""WAV helpers (joining speech chunks, generating silence for the fake provider)."""

from __future__ import annotations

import io
import wave

from app.providers.errors import ProviderBadOutput


def join_wavs(parts: list[bytes]) -> bytes:
    if len(parts) == 1:
        return parts[0]
    out = io.BytesIO()
    params = None
    with wave.open(out, "wb") as writer:
        for part in parts:
            with wave.open(io.BytesIO(part)) as reader:
                current = reader.getparams()
                if params is None:
                    params = current
                    writer.setparams(params)
                elif current[:3] != params[:3]:
                    raise ProviderBadOutput("speech chunks have different audio formats")
                writer.writeframes(reader.readframes(reader.getnframes()))
    return out.getvalue()


def silent_wav(seconds: float = 0.4, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()
