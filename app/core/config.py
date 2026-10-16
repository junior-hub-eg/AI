"""Application settings.

Every value can be set through an environment variable (or the `.env` file in
the project root). Names are the upper-case version of the field names below,
for example `llm_turn_model` -> `LLM_TURN_MODEL`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GROQ_KEY_PLACEHOLDER = "PASTE_YOUR_GROQ_KEY_HERE"

_MISSING_GROQ_KEY = """
==============================================================================
  GROQ_API_KEY IS MISSING
  1. Create a key at https://console.groq.com/keys
  2. Open the file  .env  in the project root
  3. Replace  PASTE_YOUR_GROQ_KEY_HERE  with your key
  (or set FAKE_MODELS=true to run with fake AI answers and no key)
==============================================================================
"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---------------------------------------------------------------- runtime
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    # When true no real model is called. For tests and UI work only.
    fake_models: bool = False

    # ------------------------------------------------------------------ auth
    # Backend -> AI service calls carry an RS256 JWT. Provide the PUBLIC key of
    # the backend either inline (PEM, "\n" escapes allowed) or as a file path.
    jwt_public_key: str | None = None
    jwt_public_key_file: Path | None = None
    jwt_audience: str = "discovery-ai"
    jwt_issuer: str | None = None
    jwt_leeway_seconds: int = Field(default=30, ge=0, le=300)
    # Local development only. Refused when APP_ENV=production.
    auth_disabled: bool = False

    # ------------------------------------------------------------------ groq
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>>  YOUR GROQ API KEY LIVES IN THE `.env` FILE (GROQ_API_KEY=...)   <<<
    # >>>  Do not hard-code it here. Never commit it to git.               <<<
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # ---------------------------------------------------------------- models
    # Two different gpt-oss models are used on purpose: on the free plan each
    # model has its own quota, and each acts as the other's fallback.
    llm_turn_model: str = "openai/gpt-oss-20b"
    llm_turn_fallback_model: str | None = "openai/gpt-oss-120b"
    llm_result_model: str = "openai/gpt-oss-120b"
    llm_result_fallback_model: str | None = "openai/gpt-oss-20b"
    # gpt-oss reasoning effort: low | medium | high. Empty string = do not send.
    llm_turn_reasoning_effort: str = "low"
    llm_result_reasoning_effort: str = "medium"
    llm_turn_temperature: float = Field(default=0.7, ge=0, le=2)
    llm_result_temperature: float = Field(default=0.2, ge=0, le=2)
    # Output budget includes the model's hidden reasoning tokens.
    llm_turn_max_tokens: int = Field(default=1024, ge=64)
    llm_result_max_tokens: int = Field(default=2048, ge=64)

    stt_model: str = "whisper-large-v3"
    stt_language: str = "en"
    tts_model: str = "canopylabs/orpheus-v1-english"
    tts_voice: str = "autumn"
    # Orpheus accepts short inputs; longer text is split on sentence bounds.
    tts_max_chars: int = Field(default=200, ge=40)

    # ----------------------------------------------------------------- prompts
    prompts_dir: Path = PROJECT_ROOT / "prompts"
    prompt_turn_version: str = "v1"
    prompt_result_version: str = "v1"
    # Token savers (important on the free plan: 8,000 tokens per minute).
    include_tracks_in_turn: bool = True
    profile_max_chars_turn: int = Field(default=300, ge=50)
    profile_max_chars_result: int = Field(default=600, ge=50)
    transcript_max_chars_in_prompt: int = Field(default=700, ge=100)

    # ------------------------------------------------------------- interview
    opening_question: str = (
        "Hi there! I'm excited to get to know you. When you have free time, what do you enjoy doing the most?"
    )
    result_min_responses: int = Field(default=5, ge=1)
    result_max_responses: int = Field(default=20, ge=1)

    # ---------------------------------------------------------------- limits
    max_text_chars: int = 1000
    max_audio_bytes: int = 10 * 1024 * 1024
    max_audio_seconds: int = 120
    max_request_bytes: int = 15 * 1024 * 1024

    # --------------------------------------------------------------- timeouts
    # The backend waits 20 s (turn) and 30 s (result); answer before that.
    turn_deadline_seconds: float = Field(default=18.0, gt=0)
    result_deadline_seconds: float = Field(default=28.0, gt=0)
    llm_turn_timeout_seconds: float = Field(default=10.0, gt=0)
    llm_result_timeout_seconds: float = Field(default=20.0, gt=0)
    stt_timeout_seconds: float = Field(default=12.0, gt=0)
    tts_timeout_seconds: float = Field(default=8.0, gt=0)

    @property
    def groq_key_value(self) -> str:
        return self.groq_api_key.get_secret_value().strip() if self.groq_api_key else ""

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        if self.app_env == "production":
            if self.auth_disabled:
                raise ValueError("AUTH_DISABLED must be false when APP_ENV=production")
            if self.fake_models:
                raise ValueError("FAKE_MODELS must be false when APP_ENV=production")
        if not self.fake_models and self.groq_key_value in ("", GROQ_KEY_PLACEHOLDER):
            raise ValueError(_MISSING_GROQ_KEY)
        if not self.auth_disabled and not (self.jwt_public_key or self.jwt_public_key_file):
            raise ValueError(
                "JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_FILE is required "
                "(or set AUTH_DISABLED=true for local development only)"
            )
        if self.result_min_responses > self.result_max_responses:
            raise ValueError("RESULT_MIN_RESPONSES must be <= RESULT_MAX_RESPONSES")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
