from abc import ABC, abstractmethod


class AIError(Exception):
    """Raised when the AI provider fails; services catch it and fall back to the offline path."""


class AIProvider(ABC):
    name: str = "base"
    label: str = ""
    supports_generation: bool = False
    supports_ocr: bool = False

    @abstractmethod
    def ocr(self, image: bytes, mime: str) -> dict:
        """Return {"text": str, "note": str | None}."""

    @abstractmethod
    def analyze_sentence(self, sentence: str, tokens: list[str]) -> list[dict] | None:
        """Return raw word analyses (validated by the caller) or None if not supported."""

    @abstractmethod
    def generate_sentence(self, topic_title: str, focus_roles: list[str], level: int, avoid: list[str]) -> dict | None:
        """Return {"text": str, "words": [...]} or None."""

    @abstractmethod
    def rephrase_mistake(self, sentence: str, word: dict, answer: dict, default: str) -> str:
        """Return a one-sentence encouraging message that does NOT reveal the right answer."""

    @abstractmethod
    def guidance_hint(self, sentence: str, word: str, question: str, wrong_choice: str, answer: str, default: str) -> str:
        """Return a short hint for a guided-question step that does NOT contain the answer."""

    def status(self) -> dict:
        return {"provider": self.name, "ok": True}
