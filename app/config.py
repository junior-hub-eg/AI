from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment variables or .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "provider:model" for langchain's init_chat_model, for example "cohere:command-a-03-2025", "openai:gpt-4.1-mini",
    # "google_genai:gemini-2.5-flash", "anthropic:claude-haiku-4-5", "groq:llama-3.3-70b-versatile".
    # "fake" runs a keyword-based stand-in with no API key (tests and wiring checks only).
    llm_model: str = "fake"
    llm_temperature: float = 0.3
    # "any" makes the model call a tool every turn (it must end with `respond`). Use "auto" for a provider
    # that does not support forcing tools; plain-text answers are then accepted too.
    llm_tool_choice: str = "any"

    max_steps: int = 4
    reply_timeout_seconds: float = 18

    # The backend signs a 5-minute RS256 token for audience "assistant-ai". The service holds only the public key.
    auth_disabled: bool = False
    auth_public_key_pem: str | None = None
    auth_public_key_file: str | None = None
    auth_audience: str = "assistant-ai"
    auth_issuer: str = "JuniorHub.Api"

    # /v1/dev/* endpoints to chat as a mock student without a token or context. Never in production.
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
    # Settings only reads its own fields from .env. The provider's key (COHERE_API_KEY, OPENAI_API_KEY...) is read by
    # the provider's client from the environment, so .env is loaded into it too. Real environment variables win.
    load_dotenv(".env", override=False)  # the same file Settings reads: .env in the working folder
    return Settings()
