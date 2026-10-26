"""Grammar catalog: the fixed vocabulary of word types, grammatical roles, colors and signs.

Every role has ONE color used on every screen (US-03 / US-12).
"""

WORD_TYPES = ["اسم", "فعل", "حرف"]

CASES = {"مرفوع": "رفعه", "منصوب": "نصبه", "مجرور": "جره", "مجزوم": "جزمه"}

SIGNS = ["الضمة", "الفتحة", "الكسرة", "السكون", "الواو", "الألف", "الياء", "مبني"]

# governor groups (used by the guided questions)
GOV_IBTIDA = "مفيش عامل قبلها (أول الجملة الاسمية)"
GOV_MUBTADA = "المبتدأ اللي قبلها"
GOV_KANA = "فعل ناسخ (كان وأخواتها)"
GOV_INNA = "حرف ناسخ (إنّ وأخواتها)"
GOV_VERB = "الفعل اللي قبلها"
GOV_JAR = "حرف جر قبلها"
GOV_IDAFA = "اسم قبلها مضاف ليها"
GOV_TABI = "بتتبع اسم قبلها في إعرابه"

GOVERNORS = [GOV_IBTIDA, GOV_MUBTADA, GOV_KANA, GOV_INNA, GOV_VERB, GOV_JAR, GOV_IDAFA, GOV_TABI]

# key: role name shown to students
ROLES: dict[str, dict] = {
    "مبتدأ":      {"key": "mubtada",   "color": "#2563EB", "type": "اسم", "case": "مرفوع", "gov": GOV_IBTIDA},
    "خبر":        {"key": "khabar",    "color": "#16A34A", "type": "اسم", "case": "مرفوع", "gov": GOV_MUBTADA},
    "حرف ناسخ":   {"key": "nasikh",    "color": "#C026D3", "type": "حرف", "case": None,    "gov": None},
    "فعل ناسخ":   {"key": "nasikh",    "color": "#C026D3", "type": "فعل", "case": None,    "gov": None},
    "اسم كان":    {"key": "ism-nasikh",  "color": "#0891B2", "type": "اسم", "case": "مرفوع", "gov": GOV_KANA},
    "خبر كان":    {"key": "khabar-nasikh", "color": "#65A30D", "type": "اسم", "case": "منصوب", "gov": GOV_KANA},
    "اسم إنّ":    {"key": "ism-nasikh",  "color": "#0891B2", "type": "اسم", "case": "منصوب", "gov": GOV_INNA},
    "خبر إنّ":    {"key": "khabar-nasikh", "color": "#65A30D", "type": "اسم", "case": "مرفوع", "gov": GOV_INNA},
    "فعل ماضٍ":   {"key": "fiil",      "color": "#EA580C", "type": "فعل", "case": None,    "gov": None},
    "فعل مضارع":  {"key": "fiil",      "color": "#EA580C", "type": "فعل", "case": "مرفوع", "gov": None},
    "فاعل":       {"key": "faail",     "color": "#DC2626", "type": "اسم", "case": "مرفوع", "gov": GOV_VERB},
    "نائب فاعل":  {"key": "naib",      "color": "#E11D48", "type": "اسم", "case": "مرفوع", "gov": GOV_VERB},
    "مفعول به":   {"key": "mafool",    "color": "#7C3AED", "type": "اسم", "case": "منصوب", "gov": GOV_VERB},
    "حرف جر":     {"key": "jar",       "color": "#64748B", "type": "حرف", "case": None,    "gov": None},
    "اسم مجرور":  {"key": "majrour",   "color": "#0D9488", "type": "اسم", "case": "مجرور", "gov": GOV_JAR},
    "مضاف إليه":  {"key": "mudaf",     "color": "#CA8A04", "type": "اسم", "case": "مجرور", "gov": GOV_IDAFA},
    "نعت":        {"key": "naat",      "color": "#DB2777", "type": "اسم", "case": None,    "gov": GOV_TABI},
    "توكيد":      {"key": "tawkid",    "color": "#4F46E5", "type": "اسم", "case": None,    "gov": GOV_TABI},
    "بدل":        {"key": "badal",     "color": "#B45309", "type": "اسم", "case": None,    "gov": GOV_TABI},
}

UNKNOWN_ROLE = "غير محدد"
UNKNOWN_COLOR = "#94A3B8"

TABI_ROLES = {"نعت", "توكيد", "بدل"}
VERB_ROLES = {"فعل ماضٍ", "فعل مضارع", "فعل ناسخ"}
PARTICLE_ROLES = {"حرف ناسخ", "حرف جر"}

# roles grouped by family — used to build plausible distractors
ROLE_FAMILIES = [
    ["مبتدأ", "خبر", "اسم كان", "خبر كان", "اسم إنّ", "خبر إنّ"],
    ["فاعل", "نائب فاعل", "مفعول به", "مبتدأ"],
    ["اسم مجرور", "مضاف إليه", "نعت", "مفعول به"],
    ["نعت", "توكيد", "بدل", "مضاف إليه"],
    ["فعل ماضٍ", "فعل مضارع", "فعل ناسخ"],
    ["حرف جر", "حرف ناسخ"],
]


def role_color(role: str) -> str:
    return ROLES.get(role, {}).get("color", UNKNOWN_COLOR)


def role_key(role: str) -> str:
    return ROLES.get(role, {}).get("key", "unknown")


def roles_for_type(word_type: str) -> list[str]:
    return [r for r, meta in ROLES.items() if meta["type"] == word_type]


def legend() -> list[dict]:
    seen, out = set(), []
    for role, meta in ROLES.items():
        out.append({"role": role, "color": meta["color"], "key": meta["key"], "type": meta["type"]})
        seen.add(role)
    return out
