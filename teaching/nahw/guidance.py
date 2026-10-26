"""US-08: a chain of small questions that leads the student to the answer without giving it away.
The final answer is revealed only on request AND after at least 2 wrong attempts."""
import random

from teaching.nahw.catalog import (
    GOV_IBTIDA, GOV_IDAFA, GOV_INNA, GOV_JAR, GOV_KANA, GOV_MUBTADA, GOV_TABI, GOV_VERB, GOVERNORS,
    ROLE_FAMILIES, ROLES, SIGNS, WORD_TYPES,
)

TYPE_HINTS = {
    "اسم": "جرب: هل الكلمة تقبل «ال» أو التنوين؟ لو أيوه تبقى…",
    "فعل": "جرب: هل الكلمة بتدل على حدث مرتبط بزمن (حصل أو بيحصل)؟",
    "حرف": "جرب: هل الكلمة ليها معنى لوحدها؟ ولا بتربط وبتأثر في الكلمة اللي بعدها؟",
}
GOV_HINTS = {
    GOV_IBTIDA: "هل فيه أي كلمة قبلها أصلًا؟",
    GOV_MUBTADA: "الكلمة دي بتكمّل معنى اسم قبلها… مين؟",
    GOV_KANA: "فيه فعل في أول الجملة من أخوات كان؟",
    GOV_INNA: "فيه حرف في أول الجملة من أخوات إنّ؟",
    GOV_VERB: "فيه فعل تام قبلها؟",
    GOV_JAR: "فيه حرف زي (في، من، إلى، على، عن) قبلها مباشرة؟",
    GOV_IDAFA: "هل الاسم اللي قبلها مضاف ليها (زي «كتاب الطالب»)؟",
    GOV_TABI: "هل هي بتوصف أو بتأكد أو بتوضح الاسم اللي قبلها؟",
}
ROLE_HINTS = {
    GOV_IBTIDA: "الاسم اللي بنبدأ بيه الجملة الاسمية اسمه إيه؟",
    GOV_MUBTADA: "الجزء اللي بيكمّل معنى المبتدأ اسمه إيه؟",
    GOV_KANA: "كان وأخواتها بترفع الاسم وتنصب الخبر… الكلمة دي الاسم ولا الخبر؟",
    GOV_INNA: "إنّ وأخواتها بتنصب الاسم وترفع الخبر… الكلمة دي الاسم ولا الخبر؟",
    GOV_VERB: "هي اللي عملت الفعل؟ ولا الفعل وقع عليها؟ والفعل مبني للمعلوم ولا للمجهول؟",
    GOV_JAR: "الاسم اللي بعد حرف الجر اسمه إيه؟",
    GOV_IDAFA: "الاسم التاني في الإضافة اسمه إيه؟",
    GOV_TABI: "بتوصف (نعت)؟ ولا بتأكد بكلمة زي نفس/كل (توكيد)؟ ولا بتوضح بإسم تاني (بدل)؟",
}


def _options(correct: str, pool: list[str], n: int = 4, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    others = [x for x in dict.fromkeys(pool) if x != correct]
    rng.shuffle(others)
    opts = [correct] + others[: n - 1]
    rng.shuffle(opts)
    return opts


def _role_pool(role: str) -> list[str]:
    pool = []
    for fam in ROLE_FAMILIES:
        if role in fam:
            pool += fam
    return pool or list(ROLES)


def build_steps(words: list[dict], i: int) -> list[dict]:
    w = words[i]
    role, wtype, sign = w["role"], w["type"], w["sign"]
    seed = hash((w["text"], role)) & 0xFFFF
    before = " ".join(x["text"] for x in words[:i]) or "مفيش كلمات قبلها"
    steps = [{
        "question": f"كلمة «{w['text']}» نوعها إيه؟",
        "options": WORD_TYPES, "answer": wtype, "hint": TYPE_HINTS[wtype],
    }]
    gov = ROLES[role]["gov"]
    if wtype == "اسم" and gov:
        steps.append({
            "question": f"اقرا الكلام اللي قبل «{w['text']}»: ({before}). إيه اللي متحكم في إعرابها؟",
            "options": _options(gov, GOVERNORS, seed=seed), "answer": gov, "hint": GOV_HINTS[gov],
        })
        steps.append({
            "question": f"يبقى «{w['text']}» موقعها إيه في الجملة؟",
            "options": _options(role, _role_pool(role), seed=seed + 1), "answer": role, "hint": ROLE_HINTS[gov],
        })
    else:
        steps.append({
            "question": f"طيب «{w['text']}» بتعمل إيه في الجملة؟",
            "options": _options(role, [r for r, m in ROLES.items() if m["type"] == wtype] + _role_pool(role), seed=seed),
            "answer": role,
            "hint": "الفعل الماضي حدث خلص، والمضارع بيحصل دلوقتي، والناسخ بيدخل على مبتدأ وخبر." if wtype == "فعل"
            else "حرف الجر بيجر الاسم بعده، والحرف الناسخ بيدخل على جملة اسمية.",
        })
    case = w.get("case")
    sign_q = (f"و«{w['text']}» {case}… علامة إعرابها إيه؟" if case
              else f"و«{w['text']}» معربة ولا مبنية؟ علامتها إيه؟")
    steps.append({
        "question": sign_q,
        "options": _options(sign, SIGNS, seed=seed + 2), "answer": sign,
        "hint": f"بص على آخر حرف في «{w['text']}»: هي مفرد ولا مثنى ولا جمع مذكر سالم؟"
        if sign != "مبني" else "الحروف والفعل الماضي مش بيتغير آخرهم…",
    })
    return steps
