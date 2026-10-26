"""Groq provider (OpenAI-compatible chat/completions at https://api.groq.com/openai/v1).

Every feature goes through here:
  OCR (vision model) · sentence analysis · leveled sentence generation · mistake message · guided hints.
Every output is validated by the services before it reaches a student; on any failure they fall back offline."""
import base64
import json
import re
import time

import httpx

from teaching.nahw.catalog import ROLES, SIGNS, WORD_TYPES
from teaching.nahw.base import AIError, AIProvider

ROLE_LIST = "، ".join(ROLES.keys())
SIGN_LIST = "، ".join(SIGNS)

SCHEMA_HINT = (
    'كل كلمة: {"text": الكلمة كما هي, "type": واحد من [' + "، ".join(WORD_TYPES) + '], '
    '"role": واحد من [' + ROLE_LIST + '], "sign": واحد من [' + SIGN_LIST + '], '
    '"case": واحد من [مرفوع، منصوب، مجرور، مجزوم] أو null للمبني, "note": ملاحظة قصيرة اختيارية}'
)

SYSTEM = (
    "أنت مدرس نحو عربي دقيق جدًا لطلاب من 11 لـ 18 سنة، وبتعرب حسب النحو المدرسي. "
    "استخدم أسماء الأدوار المسموحة بالحرف فقط. لكان وأخواتها: «فعل ناسخ» و«اسم كان» و«خبر كان». "
    "لإنّ وأخواتها: «حرف ناسخ» و«اسم إنّ» و«خبر إنّ». الفعل الماضي وكل الحروف علامتهم «مبني». "
    "المثنى: الألف رفعًا والياء نصبًا وجرًا. جمع المذكر السالم: الواو رفعًا والياء نصبًا وجرًا. "
    "الممنوع من الصرف يُجر بالفتحة إلا لو معرّف بأل أو مضاف. "
    "رد دائمًا بـ JSON صالح فقط بدون أي نص زيادة."
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _extract_json(text: str):
    text = _THINK.sub("", text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if not m:
            raise AIError("الرد مش JSON")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise AIError(f"JSON مش سليم: {e}") from e


def _signature(words: list[dict]) -> list[tuple]:
    return [(w.get("role"), w.get("sign")) for w in words]


class GroqProvider(AIProvider):
    name = "groq"
    supports_generation = True
    supports_ocr = True

    def __init__(self, api_key: str, model: str, fast_model: str, vision_model: str,
                 base_url: str = "https://api.groq.com/openai/v1", timeout: float = 60, max_retries: int = 2,
                 client: httpx.Client | None = None):
        self.api_key, self.base_url = api_key, base_url.rstrip("/")
        self.model, self.fast_model, self.vision_model = model, fast_model, vision_model
        self.max_retries = max_retries
        self.client = client or httpx.Client(timeout=timeout)
        self.label = f"Groq · {model.split('/')[-1]}"

    # ------------------------------------------------------------ transport
    def _optional_params(self, model: str) -> dict:
        if model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "medium" if model == self.model else "low"}
        if model.startswith("qwen/"):
            return {"reasoning_format": "hidden"}
        return {}

    def _post(self, payload: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(self.max_retries + 1):
            try:
                r = self.client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            except httpx.HTTPError as e:
                if attempt == self.max_retries:
                    raise AIError(f"Groq مش متاح: {e}") from e
                time.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503) and attempt < self.max_retries:
                wait = r.headers.get("retry-after")
                time.sleep(min(float(wait) if wait and wait.replace(".", "").isdigit() else 1.0 * (attempt + 1), 8))
                continue
            return r
        return r

    def _chat(self, messages: list[dict], model: str | None = None, json_mode: bool = True,
              temperature: float = 0.2) -> str:
        model = model or self.model
        payload = {"model": model, "messages": messages, "temperature": temperature,
                   **self._optional_params(model)}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = self._post(payload)
        if r.status_code == 400:  # an optional param isn't accepted by this model → retry plain
            for k in ("reasoning_effort", "reasoning_format", "response_format"):
                payload.pop(k, None)
            r = self._post(payload)
        if r.status_code == 401:
            raise AIError("مفتاح Groq غلط (401)")
        if r.status_code >= 400:
            raise AIError(f"Groq رجّع {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise AIError(f"رد Groq مش مفهوم: {e}") from e

    def status(self) -> dict:
        try:
            r = self.client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as e:
            return {"provider": self.name, "ok": False, "error": f"مش قادر أوصل لـ Groq: {e}"}
        if r.status_code != 200:
            return {"provider": self.name, "ok": False, "error": f"Groq رجّع {r.status_code}"}
        available = {m.get("id") for m in r.json().get("data", [])}
        models = {"text": self.model, "fast": self.fast_model, "vision": self.vision_model}
        missing = [m for m in models.values() if available and m not in available]
        return {"provider": self.name, "ok": not missing, "models": models,
                "missing_models": missing}

    # ------------------------------------------------------------ features
    def ocr(self, image: bytes, mime: str) -> dict:
        b64 = base64.b64encode(image).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "دي صورة من كتاب نحو عربي. اقرأ النص العربي اللي فيها بالظبط كلمة كلمة، "
                                     "واحتفظ بالتشكيل زي ما هو. ماتصلحش ولا تضيف حاجة. خلي كل جملة تنتهي بنقطة. "
                                     "رجّع JSON بس: {\"text\": النص}"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}]
        data = _extract_json(self._chat(messages, model=self.vision_model, temperature=0))
        text = (data.get("text") if isinstance(data, dict) else "") or ""
        if not text.strip():
            raise AIError("مفيش نص اتقرا")
        return {"text": text.strip(), "note": None}

    def analyze_sentence(self, sentence: str, tokens: list[str]) -> list[dict] | None:
        prompt = (
            f"أعرب الجملة: «{sentence}»\n"
            f"الكلمات بالترتيب ({len(tokens)} كلمة): {json.dumps(tokens, ensure_ascii=False)}\n"
            f"رجّع JSON: {{\"words\": [...]}} بنفس عدد وترتيب الكلمات بالظبط. {SCHEMA_HINT}"
        )
        data = _extract_json(self._chat([{"role": "system", "content": SYSTEM},
                                         {"role": "user", "content": prompt}], temperature=0))
        return data.get("words") if isinstance(data, dict) else data

    def generate_sentence(self, topic_title, focus_roles, level, avoid) -> dict | None:
        levels = {1: "قصيرة 2–3 كلمات وتركيب بسيط ومفرد",
                  2: "3–4 كلمات، فيها مثنى أو جمع مذكر سالم",
                  3: "4–5 كلمات، فيها نعت أو تركيب أصعب"}
        prompt = (
            f"اكتب جملة عربية فصحى مشكولة تشكيلًا كاملًا لتمرين موضوع «{topic_title}» "
            f"لازم تحتوي على: {'، '.join(focus_roles)}. المستوى: {levels.get(level, levels[3])}. "
            "قيود: كلمات منفصلة بمسافات، من غير ضمائر متصلة، ومن غير حروف ملزوقة (بـ/لـ/كـ/و/ف)، "
            "ومن غير أسماء مقصورة أو منقوصة، ومفردات مناسبة لطالب في المدرسة. "
            f"ماتكررش أي جملة من دول: {json.dumps(avoid[-40:], ensure_ascii=False)}.\n"
            f"رجّع JSON: {{\"text\": الجملة, \"words\": [...]}}. {SCHEMA_HINT}"
        )
        data = _extract_json(self._chat([{"role": "system", "content": SYSTEM},
                                         {"role": "user", "content": prompt}], temperature=0.9))
        return data if isinstance(data, dict) else None

    def verify(self, sentence: str, tokens: list[str], words: list[dict]) -> bool:
        """Independent second pass: re-analyze the generated sentence and require the same role/sign per word."""
        second = self.analyze_sentence(sentence, tokens)
        if not isinstance(second, list) or len(second) != len(words):
            return False
        return _signature(second) == _signature(words)

    def rephrase_mistake(self, sentence, word, answer, default) -> str:
        prompt = (
            f"طالب بيعرب «{sentence}». الكلمة «{word['text']}» إعرابها الصح: {word['role']} ({word['sign']}). "
            f"الطالب اختار: {answer.get('type')} / {answer.get('role')} / {answer.get('sign')}.\n"
            "اكتب جملة واحدة قصيرة بالعامية المصرية البسيطة بنبرة مشجعة: تحدد الكلمة الغلط وسبب واحد بسيط، "
            f"من غير ما تقول الإعراب الصح ولا علامته، ومن غير كلمة راسب. مثال للأسلوب: {default}\n"
            "رجّع JSON: {\"message\": الجملة}"
        )
        msg = self._short(prompt, "message")
        leaks = msg and word["role"] != answer.get("role") and word["role"] in msg
        return default if (not msg or leaks or len(msg) > 220) else msg

    def guidance_hint(self, sentence, word, question, wrong_choice, answer, default) -> str:
        prompt = (
            f"طالب بيتدرب على إعراب «{sentence}». السؤال عن «{word}»: {question}\n"
            f"الطالب اختار «{wrong_choice}» وده غلط. الإجابة الصح هي «{answer}» (ماتقولهاش أبدًا).\n"
            "اكتب تلميح واحد قصير (جملة أو اتنين) بالعامية المصرية يخليه يفكر ويوصل بنفسه، "
            f"من غير ما تذكر الإجابة. مثال للأسلوب: {default}\nرجّع JSON: {{\"hint\": التلميح}}"
        )
        hint = self._short(prompt, "hint")
        return default if (not hint or answer in hint or len(hint) > 240) else hint

    def _short(self, prompt: str, key: str) -> str:
        try:
            data = _extract_json(self._chat([{"role": "user", "content": prompt}], model=self.fast_model,
                                            temperature=0.5))
            return (data.get(key) or "").strip() if isinstance(data, dict) else ""
        except AIError:
            return ""
