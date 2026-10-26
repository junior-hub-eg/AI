"""OCR for passage photos via Gemini (OpenAI-compatible endpoint).
Everything else stays on Groq; this engine only reads images."""
import base64
import re

import httpx

from teaching.nahw.base import AIError

PROMPT = (
    "دي صورة صفحة من كتاب نحو عربي لطلاب المدارس. انسخ النص العربي اللي فيها حرفيًا كلمة كلمة.\n"
    "- انسخ التشكيل (الفتحة والضمة والكسرة والسكون والشدة والتنوين) بالظبط زي ما هو مطبوع.\n"
    "- ماتضيفش تشكيل مش موجود، وماتصلحش أي كلمة، وماتترجمش.\n"
    "- تجاهل أرقام الصفحات والعناوين الجانبية والتعليمات (زي: أعرب ما تحته خط).\n"
    "- خلي كل جملة تنتهي بنقطة، وكل جملة في سطر.\n"
    "رجّع النص بس من غير أي كلام تاني."
)

_FENCE = re.compile(r"^```[a-z]*\s*|\s*```$")


class GeminiOCR:
    name = "gemini"

    def __init__(self, api_key: str, model: str,
                 base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
                 timeout: float = 60, max_retries: int = 2, client: httpx.Client | None = None):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")
        self.max_retries = max_retries
        self.client = client or httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def ocr(self, image: bytes, mime: str) -> dict:
        payload = {
            "model": self.model,
            "temperature": 0,
            "reasoning_effort": "low",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}},
            ]}],
        }
        r = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self.client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
            except httpx.HTTPError as e:
                if attempt == self.max_retries:
                    raise AIError(f"Gemini مش متاح: {e}") from e
                continue
            if r.status_code == 400 and "reasoning_effort" in payload:
                payload.pop("reasoning_effort")
                continue
            if r.status_code in (429, 500, 503) and attempt < self.max_retries:
                continue
            break
        if r is None or r.status_code >= 400:
            raise AIError(f"Gemini رجّع {r.status_code if r is not None else '—'}: {r.text[:200] if r is not None else ''}")
        try:
            text = r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise AIError(f"رد Gemini مش مفهوم: {e}") from e
        text = _FENCE.sub("", text.strip()).strip()
        if not text:
            raise AIError("مفيش نص اتقرا")
        return {"text": text, "note": None}

    def status(self) -> dict:
        try:
            r = self.client.get(f"{self.base_url}/models", headers=self._headers())
        except httpx.HTTPError as e:
            return {"engine": self.name, "model": self.model, "ok": False, "error": f"مش قادر أوصل لـ Gemini: {e}"}
        if r.status_code != 200:
            return {"engine": self.name, "model": self.model, "ok": False, "error": f"Gemini رجّع {r.status_code}"}
        ids = {m.get("id", "").removeprefix("models/") for m in r.json().get("data", [])}
        return {"engine": self.name, "model": self.model, "ok": not ids or self.model in ids,
                "missing_model": bool(ids) and self.model not in ids}
