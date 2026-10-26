"""Grammar logic shared by every feature: full إعراب text, the "why" sentence, error messages,
a small rule-based analyzer (used offline), and validation of AI-produced analyses."""
from teaching.nahw.catalog import (
    CASES, GOV_IBTIDA, GOV_IDAFA, GOV_INNA, GOV_JAR, GOV_KANA, GOV_MUBTADA, GOV_TABI, GOV_VERB,
    ROLES, SIGNS, UNKNOWN_ROLE, VERB_ROLES, WORD_TYPES, role_color, role_key,
)
from teaching.nahw.arabic import final_mark, normalize, tokenize

SIGN_WHY = {"الواو": "جمع مذكر سالم", "الألف": "مثنى"}


# ---------------------------------------------------------------- full إعراب text
def full_irab(word: dict) -> str:
    role, sign, case = word.get("role"), word.get("sign"), word.get("case")
    if role == UNKNOWN_ROLE or role not in ROLES:
        return "لم يُحدَّد بعد — يحتاج مراجعة المدرس"
    if sign == "مبني":
        if word.get("type") == "حرف":
            text = f"{role} مبني لا محل له من الإعراب"
        else:
            text = f"{role} مبني"
    else:
        case = case or ROLES[role]["case"] or ""
        noun = CASES.get(case, "")
        label = role if case and role.endswith(case) else f"{role} {case}"  # «اسم مجرور» not «اسم مجرور مجرور»
        text = f"{label} وعلامة {noun} {sign}".replace("  ", " ")
    if word.get("note"):
        text += f" ({word['note']})"
    return text


# ---------------------------------------------------------------- context helpers
def _find_back(words: list[dict], i: int, roles: set[str]) -> dict | None:
    for j in range(i - 1, -1, -1):
        if words[j].get("role") in roles:
            return words[j]
    return None


def _prev_noun(words: list[dict], i: int) -> dict | None:
    for j in range(i - 1, -1, -1):
        if words[j].get("type") == "اسم":
            return words[j]
    return None


def governor_word(words: list[dict], i: int) -> dict | None:
    gov = ROLES.get(words[i].get("role"), {}).get("gov")
    if gov == GOV_KANA:
        return _find_back(words, i, {"فعل ناسخ"})
    if gov == GOV_INNA:
        return _find_back(words, i, {"حرف ناسخ"})
    if gov == GOV_VERB:
        return _find_back(words, i, {"فعل ماضٍ", "فعل مضارع"})
    if gov == GOV_JAR:
        return _find_back(words, i, {"حرف جر"})
    if gov == GOV_MUBTADA:
        return _find_back(words, i, {"مبتدأ"})
    if gov in (GOV_IDAFA, GOV_TABI):
        return _prev_noun(words, i)
    return None


def _q(w: dict | None) -> str:
    return f"«{w['text']}»" if w else "الكلمة اللي قبلها"


def reason_for(words: list[dict], i: int) -> str:
    """One simple sentence explaining WHY the word has its إعراب (used in examples & after guidance)."""
    w = words[i]
    role = w.get("role")
    g = governor_word(words, i)
    case = w.get("case") or ROLES.get(role, {}).get("case")
    reasons = {
        "مبتدأ": "اسم جه في أول الجملة الاسمية ومفيش قبله عامل، فهو مبتدأ مرفوع.",
        "خبر": f"بيكمّل معنى المبتدأ {_q(g)} ويقول عنه معلومة، فهو خبر مرفوع.",
        "حرف ناسخ": f"«{w['text']}» من إنّ وأخواتها: بتنصب الاسم اللي بعدها وترفع الخبر.",
        "فعل ناسخ": f"«{w['text']}» من كان وأخواتها: بترفع الاسم وتنصب الخبر.",
        "اسم كان": f"جه بعد الفعل الناسخ {_q(g)} فهو اسمه، واسم كان مرفوع.",
        "خبر كان": f"هو خبر الفعل الناسخ {_q(g)}، وخبر كان منصوب.",
        "اسم إنّ": f"جه بعد {_q(g)} مباشرة فهو اسمها، واسم إنّ منصوب.",
        "خبر إنّ": f"هو خبر {_q(g)}، وخبر إنّ بيفضل مرفوع.",
        "فعل ماضٍ": "فعل بيدل على حدث حصل وخلص، والماضي دايمًا مبني.",
        "فعل مضارع": "فعل بيدل على الحاضر، ومفيش قبله ناصب ولا جازم فهو مرفوع.",
        "فاعل": f"اسم جه بعد الفعل {_q(g)} وهو اللي عمل الفعل، فهو فاعل مرفوع.",
        "نائب فاعل": f"الفعل {_q(g)} مبني للمجهول، والاسم بعده أخد مكان الفاعل فبقى نائب فاعل مرفوع.",
        "مفعول به": f"الفعل {_q(g)} وقع عليه، فهو مفعول به منصوب.",
        "حرف جر": f"«{w['text']}» حرف جر مبني، وبيجرّ الاسم اللي بعده.",
        "اسم مجرور": f"جه بعد حرف الجر {_q(g)}، فهو اسم مجرور.",
        "مضاف إليه": f"اتضاف للاسم اللي قبله {_q(g)}، والمضاف إليه دايمًا مجرور.",
        "نعت": f"بيوصف {_q(g)} اللي قبله وبياخد نفس إعرابه، فهو {case}.",
        "توكيد": f"بيأكد {_q(g)} اللي قبله وبيتبعه في الإعراب، فهو {case}.",
        "بدل": f"جه مكان {_q(g)} عشان يوضحه، وبيتبعه في الإعراب فهو {case}.",
    }
    text = reasons.get(role, "الإعراب ده لسه محتاج مراجعة المدرس.")
    if w.get("sign") in SIGN_WHY:
        text += f" وعلامته {w['sign']} لأنه {SIGN_WHY[w['sign']]}."
    elif w.get("sign") == "الياء":
        text += " وعلامته الياء لأنه مثنى أو جمع مذكر سالم."
    return text


GOV_KIND = {
    GOV_KANA: "فعل ناسخ من كان وأخواتها",
    GOV_INNA: "حرف ناسخ من إنّ وأخواتها",
    GOV_VERB: "فعل",
    GOV_JAR: "حرف جر",
    GOV_IDAFA: "اسم مضاف",
    GOV_TABI: "اسم بتتبعه",
    GOV_MUBTADA: "المبتدأ",
}


def mistake_message(words: list[dict], i: int, answer: dict) -> str:
    """US-07: name the wrong word and give ONE simple reason, without handing over the answer."""
    w = words[i]
    chosen_role = answer.get("role") or "؟"
    if answer.get("type") != w.get("type"):
        return f"«{w['text']}» مش {answer.get('type') or 'ده نوعها'} — فكّر تاني: هي اسم ولا فعل ولا حرف؟"
    if chosen_role != w.get("role"):
        gov = ROLES.get(w["role"], {}).get("gov")
        g = governor_word(words, i)
        if gov == GOV_IBTIDA:
            why = "لأنها في أول جملة اسمية ومفيش قبلها حاجة متحكمة فيها."
        elif gov == GOV_TABI:
            why = f"لأنها مرتبطة بـ{_q(g)} اللي قبلها مباشرة."
        elif gov and g:
            why = f"لأن اللي متحكم فيها هو «{g['text']}» وده {GOV_KIND.get(gov, '')}."
        elif w["type"] == "فعل":
            why = "بص على زمن الفعل وهل هو بيدخل على مبتدأ وخبر."
        elif w["type"] == "حرف":
            why = "بص هو بيعمل إيه في الكلمة اللي بعده."
        else:
            why = "بص على الكلمات اللي قبلها."
        return f"«{w['text']}» مش {chosen_role} — {why}"
    return (f"«{w['text']}» موقعها صح 👏 بس علامة الإعراب مش {answer.get('sign')} — "
            f"بص على آخرها: هي مفرد ولا مثنى ولا جمع مذكر سالم؟")


def decorate(words: list[dict]) -> list[dict]:
    """Attach the presentation data the views need: color, css key, full إعراب, reason."""
    out = []
    for i, w in enumerate(words):
        d = dict(w)
        d["color"] = role_color(w.get("role"))
        d["key"] = role_key(w.get("role"))
        d["full"] = full_irab(w)
        d["reason"] = reason_for(words, i)
        d["index"] = i
        out.append(d)
    return out


def grade(words: list[dict], answers: list[dict]) -> list[dict]:
    results = []
    for i, w in enumerate(words):
        a = answers[i] if i < len(answers) and answers[i] else {}
        gradable = w.get("role") in ROLES
        type_ok = a.get("type") == w.get("type")
        role_ok = a.get("role") == w.get("role")
        sign_ok = a.get("sign") == w.get("sign")
        results.append({
            "index": i, "text": w["text"], "gradable": gradable,
            "type_ok": type_ok, "role_ok": role_ok, "sign_ok": sign_ok,
            "correct": (type_ok and role_ok and sign_ok) if gradable else True,
            "answered": bool(a),
        })
    return results


# ---------------------------------------------------------------- rule-based analyzer (offline fallback)
_INNA = {normalize(x) for x in ["إنّ", "أنّ", "كأنّ", "لكنّ", "ليت", "لعلّ"]}
_KANA = {normalize(x) for x in ["كان", "أصبح", "أضحى", "أمسى", "ظلّ", "بات", "صار", "ليس"]}
_JAR = {normalize(x) for x in ["من", "إلى", "عن", "على", "في", "حتى"]}


def unknown_word(text: str) -> dict:
    return {"text": text, "type": "اسم", "role": UNKNOWN_ROLE, "sign": "؟", "case": None, "needs_review": True}


def rule_analyze(sentence: str, bank: dict[str, list[dict]]) -> list[dict]:
    """Best-effort analysis without an LLM: exact match from the verified bank, otherwise simple rules.
    Anything the rules can't decide is marked «غير محدد» for the teacher."""
    tokens = tokenize(sentence)
    key = normalize(" ".join(tokens))
    if key in bank and len(bank[key]) == len(tokens):
        return [dict(w, text=t) for w, t in zip(bank[key], tokens)]

    words = [unknown_word(t) for t in tokens]
    for i, tok in enumerate(tokens):
        n = normalize(tok)
        if n in _INNA:
            words[i] = {"text": tok, "type": "حرف", "role": "حرف ناسخ", "sign": "مبني", "case": None}
        elif n in _KANA:
            words[i] = {"text": tok, "type": "فعل", "role": "فعل ناسخ", "sign": "مبني", "case": None}
        elif n in _JAR:
            words[i] = {"text": tok, "type": "حرف", "role": "حرف جر", "sign": "مبني", "case": None}

    def set_noun(j: int, role: str, expect: set[str]) -> bool:
        if j >= len(words) or words[j]["role"] != UNKNOWN_ROLE:
            return False
        sign = final_mark(tokens[j])
        if sign not in expect:
            return False
        words[j] = {"text": tokens[j], "type": "اسم", "role": role, "sign": sign,
                    "case": ROLES[role]["case"], "auto": True}
        return True

    for i, w in enumerate(list(words)):
        if w["role"] == "حرف جر":
            set_noun(i + 1, "اسم مجرور", {"الكسرة", "الياء"})
        elif w["role"] == "حرف ناسخ":
            if set_noun(i + 1, "اسم إنّ", {"الفتحة", "الياء"}):
                set_noun(i + 2, "خبر إنّ", {"الضمة", "الواو", "الألف"})
        elif w["role"] == "فعل ناسخ":
            if set_noun(i + 1, "اسم كان", {"الضمة", "الواو", "الألف"}):
                set_noun(i + 2, "خبر كان", {"الفتحة", "الياء"})
    if len(words) == 2 and all(w["role"] == UNKNOWN_ROLE for w in words):
        if set_noun(0, "مبتدأ", {"الضمة", "الواو", "الألف"}):
            set_noun(1, "خبر", {"الضمة", "الواو", "الألف"})
    return words


def build_bank(sentences) -> dict[str, list[dict]]:
    return {normalize(s.text): s.words for s in sentences}


# ---------------------------------------------------------------- validation of AI output
def validate_words(tokens: list[str], words: list) -> list[dict] | None:
    if not isinstance(words, list) or len(words) != len(tokens):
        return None
    clean = []
    for tok, w in zip(tokens, words):
        if not isinstance(w, dict):
            return None
        role, wtype, sign = w.get("role"), w.get("type"), w.get("sign")
        if role not in ROLES or wtype not in WORD_TYPES or sign not in SIGNS:
            return None
        case = w.get("case") if w.get("case") in CASES else ROLES[role]["case"]
        if sign == "مبني":
            case = None
        item = {"text": tok, "type": ROLES[role]["type"], "role": role, "sign": sign, "case": case}
        if w.get("note"):
            item["note"] = str(w["note"])[:120]
        clean.append(item)
    return clean


def is_verb(role: str) -> bool:
    return role in VERB_ROLES
