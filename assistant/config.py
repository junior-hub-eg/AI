"""Settings of the student assistant.

Environment variables (or `.env`) with the `ASSISTANT_` prefix, so they never mix with the Discovery settings of the
same service: `ASSISTANT_LLM_MODEL`, `ASSISTANT_AUTH_PUBLIC_KEY_PEM`, ... The provider's own API key keeps its usual
name (`GROQ_API_KEY`, already set for the Discovery interview).
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment variables or .env (see .env.example)."""

    model_config = SettingsConfigDict(env_prefix="ASSISTANT_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "provider:model" for langchain's init_chat_model, for example "groq:openai/gpt-oss-120b",
    # "cohere:command-a-03-2025", "openai:gpt-4.1-mini", "google_genai:gemini-2.5-flash".
    # "fake" runs a keyword-based stand-in with no API key (tests and wiring checks only); FAKE_MODELS=true of the
    # Discovery service also switches the assistant to "fake".
    # Groq by default: the service already has a Groq key. gpt-oss-120b is Groq's replacement for
    # llama-3.3-70b-versatile (shut down 16 Aug 2026) and supports tool calling. It shares its quota with the
    # interview's result call. Check https://console.groq.com/docs/deprecations before changing it.
    llm_model: str = "groq:openai/gpt-oss-120b"
    llm_temperature: float = 0.3
    # gpt-oss models think before answering: low keeps a reply (up to MAX_STEPS model calls) inside the timeout.
    # Sent only to gpt-oss models; empty = the provider's default.
    llm_reasoning_effort: str = "low"
    # "any" makes the model call a tool every turn (it must end with `respond`). Use "auto" for a provider
    # that does not support forcing tools; plain-text answers are then accepted too.
    # "auto" by default: Groq's gpt-oss often fails forced tool calls (400 tool_use_failed).
    llm_tool_choice: str = "auto"

    max_steps: int = 4
    reply_timeout_seconds: float = 18

    # The backend signs a 5-minute RS256 token for audience "assistant-ai" with its own key pair (not the
    # Discovery one). The service holds only the public key.
    auth_disabled: bool = False
    auth_public_key_pem: str | None = None
    auth_public_key_file: str | None = None
    auth_audience: str = "assistant-ai"
    auth_issuer: str = "JuniorHub.Api"

    # /assistant/ test page and /v1/dev/* to chat as a mock student without a token. Never in production.
    dev_endpoints: bool = False

    def public_key(self) -> str | None:
        if self.auth_public_key_pem:
            return self.auth_public_key_pem.replace("\\n", "\n")
        if self.auth_public_key_file:
            with open(self.auth_public_key_file, encoding="utf-8") as f:
                return f.read()
        return None


@lru_cache
def get_settings() -> Settings:
    # Settings only reads its own fields from .env. The provider's key (GROQ_API_KEY, COHERE_API_KEY...) is read by
    # the provider's client from the environment, so .env is loaded into it too. Real environment variables win.
    load_dotenv(".env", override=False)  # the same file Settings reads: .env in the working folder
    return Settings()
