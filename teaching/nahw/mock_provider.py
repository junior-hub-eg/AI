"""Offline provider: lets the product run with no API key.
Sentences come from the verified bank, analysis from the rule-based analyzer, OCR returns a sample passage."""
from teaching.nahw.base import AIProvider

SAMPLE_PASSAGE = (
    "إنَّ العلمَ نافعٌ. كانَ الجوُّ باردًا. ذهبَ الطالبُ إلى المدرسةِ. "
    "قرأَ الطالبُ الكتابَ المفيدَ. الحديقةُ واسعةٌ."
)


class MockProvider(AIProvider):
    name = "mock"
    label = "وضع تجريبي (بدون AI)"
    supports_generation = False
    supports_ocr = False

    def __init__(self, reason: str | None = None):
        self.reason = reason

    def ocr(self, image: bytes, mime: str) -> dict:
        return {
            "text": SAMPLE_PASSAGE,
            "note": "الوضع التجريبي (مفيش GEMINI_API_KEY ولا GROQ_API_KEY): ده نص نموذجي مكان القراءة الحقيقية للصورة — عدّله أو الصق نص قطعتك.",
        }

    def analyze_sentence(self, sentence: str, tokens: list[str]) -> list[dict] | None:
        return None

    def generate_sentence(self, topic_title, focus_roles, level, avoid) -> dict | None:
        return None

    def rephrase_mistake(self, sentence, word, answer, default) -> str:
        return default

    def guidance_hint(self, sentence, word, question, wrong_choice, answer, default) -> str:
        return default

    def status(self) -> dict:
        return {"provider": self.name, "ok": True, "reason": self.reason}
