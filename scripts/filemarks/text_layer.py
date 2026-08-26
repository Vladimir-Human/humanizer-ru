# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
"""Текстовый слой снятия: невидимые символы (слой A), видимые copy-paste
артефакты класса A (MARKUP), форматные/дефектные символы (TAG_STRIP).

Слой A использует те же выражения, что и детектор (check_markers), для
«невидимых» кейсов LAYER_A_CASES. MARKUP_CASES — видимые артефакты класса A,
снимаемые доказуемо безпотерно. Снятие детерминированное и проверяемое
повторным прогоном детектора.
"""
import re

_MARKER_CASES = {}
try:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    # Выражения берутся из check_markers.py — единый источник правил
    # (scripts/check_markers.py, словарь CASES).
    from check_markers import CASES as _MARKER_CASES
except Exception as _exc:  # слой A без детектора пуст — обязан шуметь
    import sys as _sys
    print("ВНИМАНИЕ: check_markers не импортирован, DETECTOR_OK=False: %s"
          % _exc, file=_sys.stderr)

DETECTOR_OK = _MARKER_CASES != {}


def _det(name):
    return _MARKER_CASES[name][0] if name in _MARKER_CASES else None


# I.8: явная константа кейсов слоя A вместо хардкода двух имён. Раньше это были
# только zero_width + invisible_layout; теперь добавлены openai_pua (U+E200–E204)
# и openai_pua_short (U+EA01/EA02). У детектора они класса B, но для снятия
# входят в слой A. Примечание про openai_pua_short: выражение `[\uea01\uea02]`
# убирает обёртки, а ограждённая цифра-номер сноски сохраняется (I.10-а).
LAYER_A_CASES = ("zero_width", "invisible_layout", "openai_pua", "openai_pua_short")

# I.28: Unicode tag-символы (U+E0000–U+E007F) и default-ignorable (U+206A–F,
# U+180E, U+034F) — снятие вне эмодзи-флагов. guard: не трогаем символ, если он
# часть последовательности тегов, идущей за флагом U+1F3F4 (или U+1F3F3+U+FE0F);
# lookbehind включает сам флаг и все tag-глифы, поэтому весь флаг-блок
# (флаг + теги + завершающий U+E007F) защищается как единое целое. re.sub
# переоценивает соседей после удаления, так что одиночные tag-артефакты вне
# флага всё равно снимаются.
_TAG_STRIP_CHARS = (
    r"(?<![\U0001F3F4\U0001F3F3\uFE0F\U000E0000-\U000E007F])"
    r"[\U000E0000-\U000E007F\u206A-\u206F\u180E\u034F]"
)
TAG_STRIP_RX = re.compile(_TAG_STRIP_CHARS)

_RX = None
_BUILT = False


def layer_a_rx():
    global _RX, _BUILT
    if not _BUILT:
        _BUILT = True
        parts = []
        for name in LAYER_A_CASES:
            if name in _MARKER_CASES:
                parts.append("(?:" + _MARKER_CASES[name][0] + ")")
        _RX = re.compile("|".join(parts)) if parts else None
    return _RX


def clean_text_layer(text):
    # I.28: слой снятия включает и Unicode tag-символы (отдельная
    # константа TAG_STRIP_RX с guard эмодзи-флагов). Применяется во всех
    # путях снятия (текст и контейнеры); tag-глифы невидимы в XML-узлах.
    rx = layer_a_rx()
    total = 0
    if rx is not None:
        text, n = rx.subn("", text)
        total += n
    text, t = clean_tag_strip(text)
    total += t
    return text, total


# I.10: видимые copy-paste артефакты класса A, снимаемые доказуемо безпотерно.
# ПОРЯДОК важен: сначала полные/частные формы, потом короткие, чтобы не оставлять
# огрызков («:contentReference[…]» раньше «oaicite:N»; «citeturn…» раньше «turn…»).
# Исключены из снятия (остаются только в inspect) — ломают смысл/разметку:
# ref_name_search (вики-разметка), sandbox_link (ссылка на файл),
# placeholder_url/placeholder_date (требуют ручного заполнения).
MARKUP_CASES = {
    "contentReference": _det("contentReference") or r":contentReference\[oaicite:\d+\]\{index=\d+\}",
    "gemini_span": _det("gemini_span"),
    "gemini_cite_n": _det("gemini_cite_n"),
    "gemini_cite_start": _det("gemini_cite_start"),
    "cite_turn": _det("cite_turn"),
    "deepseek_line_ref": _det("deepseek_line_ref"),
    "assistants_source": _det("assistants_source"),
    "generated_ref_id": _det("generated_ref_id"),
    "oai_citation": _det("oai_citation"),
    "citation_n": _det("citation_n"),
    "oaicite_short": _det("oaicite_short"),
    "turn_search": _det("turn_search"),
    "turn_fetch": _det("turn_fetch"),
    "turn_file": _det("turn_file"),
    "turn_other": _det("turn_other"),
    "copilot_caret": _det("copilot_caret"),
    "attributableIndex": _det("attributableIndex"),
    "attached_web_bracket": _det("attached_web_bracket"),
    # Расширенные токены: снимается целиком примета, а не её обрывок.
    "writing_block": r":::\w+\{(?:[^\n}\"]|\"[^\"]*\")*\}",
    "grok_render_json": r"\[\]\(grok_render_citation_card_json=[^)]*\)",
    "attached_file": r"attached_file://\S*",
    "grok_card": r"grok_card://\S*",
    "vertexaisearch": r"(?:https?://)?vertexaisearch\.cloud\.google\.com/grounding-api-redirect\S*",
    "perplexity_s3": r"(?:https?://)?\S*ppl-ai-file-upload[^\s]*",
    # Кейсы со снятием-функцией (содержимое / URL-параметр) — см. _FUNC_CASES.
    "think_tag": r"(?s)<think(?:ing)?>.*?</think(?:ing)?>",
    "source_plus_chain": r"(?:[A-Za-zА-Яа-яЁё)]\+\d+){2,}",
    "utm_chatgpt": _det("utm_chatgpt"),
    "utm_openai": _det("utm_openai"),
    "utm_copilot": _det("utm_copilot"),
    "grok_referrer": _det("grok_referrer"),
}

# Имена, снятие которых — функция, а не простая подмена: think-блок удаляется
# вместе с содержимым; utm/referrer вырезается только как параметр URL;
# source_plus_chain снимает клей «+N», сохраняя источник.
_FUNC_CASES = frozenset({"think_tag", "source_plus_chain", "utm_chatgpt",
                         "utm_openai", "utm_copilot", "grok_referrer"})

_MK_CACHE = None


def _compiled_markup():
    global _MK_CACHE
    if _MK_CACHE is None:
        _MK_CACHE = [(name, re.compile(pat))
                     for name, pat in MARKUP_CASES.items() if name not in _FUNC_CASES]
    return _MK_CACHE


# I.10-в: think-блок с содержимым — рассуждение не для публикации. Полный
# парный блок <thinking>…</thinking> снимается целиком (содержимое тоже).
_THINK_RX = re.compile(r"(?s)<think(?:ing)?>.*?</think(?:ing)?>")

# I.10: сцепки «Источник+3» — минимально два сегмента «+число» (одиночная
# склейка «Excel+1С» — живая речь, не трогаем). Снимается клей «+N»,
# источник сохраняется (безпотерно). Между сегментами допускаются буквы
# источника, &, точка, дефис и пробел (те же разделители, что у детектора).
_CHAIN_RUN = re.compile(
    r"[A-Za-zА-Яа-яЁё)]\+\d+"
    r"(?:[A-Za-zА-Яа-яЁё&.\- ]*[A-Za-zА-Яа-яЁё)]\+\d+){1,3}"
)


def _strip_source_chain(text):
    count = 0

    def _sub(m):
        nonlocal count
        seg = m.group(0)
        count += len(re.findall(r"\+\d+", seg))
        return re.sub(r"\+\d+", "", seg)
    return _CHAIN_RUN.sub(_sub, text), count

# I.10-б: utm/referrer — вырезать только параметр из URL, не всю ссылку.
_UTM_PARAMS = (
    (r"utm_source=chatgpt\.com", "utm_source=chatgpt.com"),
    (r"utm_source=openai", "utm_source=openai"),
    (r"utm_source=copilot\.com", "utm_source=copilot.com"),
    (r"referrer=grok\.com", "referrer=grok.com"),
)


def _clean_utm(text):
    count = 0
    for val_pat, _label in _UTM_PARAMS:
        rx = re.compile(r"[?&]" + val_pat + r"[^\s&#]*")
        while True:
            m = rx.search(text)
            if not m:
                break
            start, end = m.start(), m.end()
            count += 1
            if text[start:start + 1] == "?" and text[end:end + 1] == "&":
                # "?param&rest" -> "?rest" (оставляем начало query-строки)
                text = text[:start] + "?" + text[end + 1:]
            else:
                # "?param..." или "&param..." -> удалить параметр с его разделителем
                text = text[:start] + text[end:]
    return text, count


def clean_markup(text):
    """I.10: снятие видимых copy-paste артефактов класса A (безпотерно).

    Возвращает (текст, число снятых примет). Порядок: think-блок, сцепки
    источника, обычные маркеры, затем utm-параметры.
    """
    count = 0
    text, n = _THINK_RX.subn("", text)
    count += n

    text, n = _strip_source_chain(text)
    count += n

    for _name, rx in _compiled_markup():
        text, n = rx.subn("", text)
        count += n

    text, n = _clean_utm(text)
    count += n
    return text, count


def clean_tag_strip(text):
    """I.28: снятие Unicode tag-символов и default-ignorable вне эмодзи-флагов."""
    cleaned, n = TAG_STRIP_RX.subn("", text)
    return cleaned, n


# I.9: гейт паритета «снятие ↔ детектор». Семейство «невидимых» кейсов
# детектора обязано совпадать с LAYER_A_CASES один в один; MARKUP_CASES
# обязаны ссылаться только на существующие кейсы CASES. Новый невидимый кейс
# в детекторе без записи в этот список роняет гейт — как и новый кейс в
# списках снятия без записи в CASES (защита от дублей/расхождений).
INVISIBLE_FAMILY = frozenset(
    {"zero_width", "invisible_layout", "openai_pua", "openai_pua_short"})


def removal_parity_errors():
    """Список ошибок паритета снятие↔детектор; пуст — паритет соблюдён."""
    errors = []
    if not DETECTOR_OK:
        return ["детектор check_markers недоступен: паритет не проверяется"]
    cases = _MARKER_CASES
    layer_a = set(LAYER_A_CASES)
    if layer_a != set(INVISIBLE_FAMILY):
        errors.append("LAYER_A_CASES != INVISIBLE_FAMILY: %s != %s"
                      % (sorted(layer_a), sorted(INVISIBLE_FAMILY)))
    for name in sorted(layer_a | set(INVISIBLE_FAMILY)):
        if name not in cases:
            errors.append("кейс %s в списках снятия отсутствует в CASES" % name)
    for name in sorted(INVISIBLE_FAMILY):
        if name not in layer_a:
            errors.append("невидимый кейс %s не в LAYER_A_CASES (снятие не покрывает детектор)" % name)
    for name in sorted(MARKUP_CASES):
        if name not in cases:
            errors.append("MARKUP_CASES ссылается на несуществующий кейс: %s" % name)
    return errors
