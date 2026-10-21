from langchain_core.language_models.chat_models import BaseChatModel

from .config import Settings
from .fake_llm import FakeChatModel


def create_model(settings: Settings) -> BaseChatModel:
    """The chat model from LLM_MODEL ("provider:model"). The provider's package and API key must be installed and set,
    for example langchain-openai with OPENAI_API_KEY, or langchain-google-genai with GOOGLE_API_KEY."""
    if settings.llm_model == "fake":
        return FakeChatModel()
    from langchain.chat_models import init_chat_model

    return init_chat_model(settings.llm_model, temperature=settings.llm_temperature, max_retries=1)
