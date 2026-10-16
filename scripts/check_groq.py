"""Check, one by one, every Groq model this service uses.

    python scripts/check_groq.py

Run it from the project root (it reads your key from .env). For every model it
prints OK or FAIL with the real reason and what to do about it.
The text-to-speech check also writes tts_test.wav so you can listen to the voice.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.providers.errors import ProviderError
from app.providers.groq.client import GroqHttpClient
from app.services.wav import silent_wav

HINTS = {
    "model_terms_required": "Open the Groq Playground, pick this model and accept its terms once "
    "(https://console.groq.com/playground), then run this check again.",
    "rejected the API key": "The key is wrong or revoked. Check GROQ_API_KEY in .env.",
    "rate limited": "Free-plan limit reached. Wait a minute (or until tomorrow for daily limits).",
    "timed out": "Groq did not answer in time. Check your internet connection and try again.",
    "network error": "Cannot reach api.groq.com. Check your internet / VPN / firewall.",
    "model_not_found": "The model name does not exist (or is retired). Fix it in .env.",
    "400": "Groq refused the request. Check the model name / voice name in .env.",
    "404": "Groq does not know this model name. Fix it in .env.",
}


def hint_for(message: str) -> str:
    return next((hint for key, hint in HINTS.items() if key in message), "")


async def attempt(label: str, call) -> bool:
    try:
        detail = await call()
    except ProviderError as exc:
        print(f"[FAIL] {label}\n       {type(exc).__name__}: {exc}")
        if hint := hint_for(str(exc)):
            print(f"       -> {hint}")
        return False
    print(f"[ OK ] {label}" + (f"  ({detail})" if detail else ""))
    return True


async def main() -> int:
    try:
        s = Settings(fake_models=False, auth_disabled=True)
    except ValueError as exc:
        print(exc)
        return 1
    client = GroqHttpClient(api_key=s.groq_key_value, base_url=s.groq_base_url)
    results: list[bool] = []

    chat_models = {
        (s.llm_turn_model, s.llm_turn_reasoning_effort): "question model",
        (s.llm_turn_fallback_model or "", s.llm_turn_reasoning_effort): "question fallback model",
        (s.llm_result_model, s.llm_result_reasoning_effort): "result model",
        (s.llm_result_fallback_model or "", s.llm_result_reasoning_effort): "result fallback model",
    }
    seen: set[tuple[str, str]] = set()
    for (model, effort), role in chat_models.items():
        if not model or (model, effort) in seen:
            continue
        seen.add((model, effort))

        async def chat(model=model, effort=effort):
            reply = await client.chat_json(
                model=model,
                messages=[{"role": "user", "content": 'Reply with this JSON: {"ok": true}'}],
                temperature=0,
                max_completion_tokens=300,
                reasoning_effort=effort,
                timeout=30,
            )
            return reply.strip()[:30]

        results.append(await attempt(f"{role}: {model}", chat))

    async def stt():
        text = await client.transcribe(
            model=s.stt_model,
            audio=silent_wav(1.0),
            filename="check.wav",
            mime_type="audio/wav",
            language=s.stt_language,
            timeout=30,
        )
        return f"silence -> {text!r}"

    results.append(await attempt(f"speech-to-text: {s.stt_model}", stt))

    async def tts():
        audio = await client.speak(
            model=s.tts_model,
            voice=s.tts_voice,
            text="Hello! This is a test of the interview voice.",
            timeout=30,
        )
        Path("tts_test.wav").write_bytes(audio)
        return f"{len(audio)} bytes saved to tts_test.wav, play it"

    results.append(await attempt(f"text-to-speech: {s.tts_model} (voice {s.tts_voice})", tts))

    await client.aclose()
    print(f"\n{sum(results)} of {len(results)} checks passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
