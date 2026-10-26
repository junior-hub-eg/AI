"""Settings of the teaching AI (subject links for track videos, the grammar coach).

Environment variables (or `.env`) with the `TEACHING_` prefix, so they never mix with the Discovery or assistant
settings: `TEACHING_LLM_MODEL`, `TEACHING_AUTH_PUBLIC_KEY_PEM`, ... The provider's key keeps its usual name
(`GROQ_API_KEY`).
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEACHING_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "provider:model" for langchain's init_chat_model. "fake" answers canned content with no API key (tests only);
    # FAKE_MODELS=true of the service also switches to "fake".
    llm_model: str = "groq:openai/gpt-oss-120b"
    # Used when the main model is rate limited (429). Empty = no fallback.
    llm_fallback_model: str = "groq:openai/gpt-oss-20b"
    # Reads photos of grammar passages (OCR). It must accept images.
    vision_model: str = "groq:meta-llama/llama-4-scout-17b-16e-instruct"
    # "nahw": the grammar coach runs on Kareem's Nahw Coach engine (verified sentence bank, catalog-checked Groq
    # analysis, Gemini OCR; teaching/nahw). "llm": the plain prompts of teaching/service.py.
    grammar_engine: str = "nahw"
    llm_temperature: float = 0.2
    llm_reasoning_effort: str = "low"
    reply_timeout_seconds: float = 40

    # The backend signs a 5-minute RS256 token for audience "teaching-ai" with its own key pair.
    auth_disabled: bool = False
    auth_public_key_pem: str | None = None
    auth_public_key_file: str | None = None
    auth_audience: str = "teaching-ai"
    auth_issuer: str = "JuniorHub.Api"

    def public_key(self) -> str | None:
        if self.auth_public_key_pem:
            return self.auth_public_key_pem.replace("\\n", "\n")
        if self.auth_public_key_file:
            with open(self.auth_public_key_file, encoding="utf-8") as f:
                return f.read()
        return None


@lru_cache
def get_settings() -> Settings:
    load_dotenv(".env", override=False)
    return Settings()
