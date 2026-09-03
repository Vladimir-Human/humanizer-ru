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
import unicodedata

_MARKER_CASES = {}
try:
    # Контекст пакета (humanizer_ru.text_layer): check_markers лежит рядом.
    from . import check_markers as _cm
    _MARKER_CASES = _cm.CASES
except ImportError:
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
except Exception as _exc:  # относительный импорт вне пакета и т.п.
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


# ---------------------------------------------------------------------------
# Классификация невидимых символов по риску (критерий v2 3.2).
#
# safe       — невидимые обвязки копипасты (zero-width, BOM, мягкий перенос,
#              word joiner, теговые символы, PUA-метки цитирования): снимаются
#              автоматически; легитимного использования в связном тексте нет.
# ambiguous  — символы с легитимными источниками (bidi-марки и вложения,
#              вариационные селекторы, ZWJ/ZWNJ эмодзи-последовательностей и
#              индийских письменностей, хангыль-филлеры, специальные пробелы):
#              снятие ТОЛЬКО opt-in (include_ambiguous), с дифом и
#              предупреждением о риске изменения отображения.
# dangerous  — структурные и аннотационные (разделители строк/абзацев,
#              межстрочные аннотации): показываются в отчёте и НЕ снимаются
#              никогда, ни в каком режиме.
#
# Невидимый символ вне таблицы считается dangerous (fail-safe: лучше
# показать, чем молча испортить). Массовое «удалить всё невидимое» запрещено
# по построению: такого режима нет.
# Формат записи: ((lo, hi), класс, имя, риск, действие).
INVISIBLE_CLASSES = [
    ((0x200B, 0x200B), "safe", "zero-width space",
     "обвязка копипасты чат-интерфейсов", "remove"),
    ((0x2060, 0x2060), "safe", "word joiner",
     "обвязка копипасты", "remove"),
    ((0xFEFF, 0xFEFF), "safe", "BOM / ZWNBSP",
     "обвязка копипасты и кодировок", "remove"),
    ((0x00AD, 0x00AD), "safe", "soft hyphen",
     "скрытый перенос, ломает поиск и сравнение", "remove"),
    ((0x180E, 0x180E), "safe", "mongolian vowel separator",
     "исторический разделитель, в русском тексте не легитимен", "remove"),
    ((0x034F, 0x034F), "safe", "combining grapheme joiner",
     "невидимая обвязка, в русском тексте не легитимна", "remove"),
    ((0xE0000, 0xE007F), "safe", "unicode tag characters",
     "теговые метки поставщиков (OpenAI/Gemini); вне эмодзи-флагов",
     "remove"),
    ((0xE200, 0xE204), "safe", "openai citation PUA",
     "служебные метки цитирования ChatGPT", "remove"),
    ((0xEA01, 0xEA02), "safe", "openai citation PUA short",
     "обёртки усечённой формы меток ChatGPT", "remove"),
    ((0x200C, 0x200D), "ambiguous", "ZWNJ / ZWJ",
     "эмодзи-последовательности и индийские письменности: снятие меняет "
     "отображение", "opt-in"),
    ((0x200E, 0x200F), "ambiguous", "LRM / RLM",
     "bidi-марки: легитимны в смешанных направлениях", "opt-in"),
    ((0x202A, 0x202E), "ambiguous", "bidi embeddings/overrides",
     "риск Trojan Source: показывать диф обязательно", "opt-in"),
    ((0x2066, 0x2069), "ambiguous", "bidi isolates",
     "легитимная bidi-изоляция", "opt-in"),
    ((0x206A, 0x206F), "ambiguous", "deprecated format characters",
     "устаревшие форматные; в контейнерных путях снимаются TAG_STRIP",
     "opt-in"),
    ((0xFE00, 0xFE0F), "ambiguous", "variation selectors",
     "эмодзи-вариации: снятие меняет глиф", "opt-in"),
    ((0x3164, 0x3164), "ambiguous", "hangul filler",
     "корейские филлеры: легитимны в хангыле", "opt-in"),
    ((0xFFA0, 0xFFA0), "ambiguous", "hangul filler (halfwidth)",
     "корейские филлеры: легитимны в хангыле", "opt-in"),
    ((0x00A0, 0x00A0), "ambiguous", "no-break space",
     "легитимная типографика (неразрывные сочетания); действие — обычный "
     "пробел, не удаление", "to-space"),
    ((0x2009, 0x2009), "ambiguous", "thin space",
     "типографский узкий пробел; действие — обычный пробел", "to-space"),
    ((0x202F, 0x202F), "ambiguous", "narrow no-break space",
     "типографский узкий неразрывный пробел; действие — обычный пробел",
     "to-space"),
    ((0x2028, 0x2028), "dangerous", "line separator",
     "структура текста: снятие склеивает строки", "report-only"),
    ((0x2029, 0x2029), "dangerous", "paragraph separator",
     "структура текста: снятие склеивает абзацы", "report-only"),
    ((0xFFF9, 0xFFFB), "dangerous", "interlinear annotation",
     "межстрочные аннотации: снятие теряет чтение", "report-only"),
]

_FLAG_BASE = 0x1F3F4  # основание эмодзи-флагов (tag-последовательности)

# Fail-safe: невидимый символ ВНЕ таблицы классификации считается dangerous
# (показывается, не снимается). Невидимость определяется категорией Unicode:
# Cf (форматные), Zl/Zp (разделители), нестандартные Zs (пробельные),
# управляющие C0/C1 кроме структурных \t \n \r.
_STRUCTURAL_WHITESPACE = "\t\n\r"


def _is_invisible_unclassified(ch):
    cat = unicodedata.category(ch)
    if cat in ("Cf", "Zl", "Zp"):
        return True
    if cat == "Zs" and ch != " ":
        return True
    if cat == "Cc" and ch not in _STRUCTURAL_WHITESPACE:
        return True
    return False


def classify_codepoint(cp):
    """(класс, имя, риск, действие) для кодовой точки; None — вне таблицы."""
    for (lo, hi), cls, name, risk, action in INVISIBLE_CLASSES:
        if lo <= cp <= hi:
            return cls, name, risk, action
    return None


def _is_flag_tag_context(text, i):
    """True, если позиция i — теговый символ внутри эмодзи-флага.

    Флаг: U+1F3F4, за ним последовательность тегов U+E0020–U+E007E,
    завершение U+E007F. Такие блоки легитимны (флаги Англии/Шотландии/
    Уэльса) и не снимаются даже как safe.
    """
    cp = ord(text[i])
    if not (0xE0000 <= cp <= 0xE007F):
        return False
    j = i - 1
    while j >= 0 and 0xE0000 <= ord(text[j]) <= 0xE007F:
        j -= 1
    if j >= 0 and ord(text[j]) == _FLAG_BASE:
        k = i
        while k < len(text) and 0xE0020 <= ord(text[k]) <= 0xE007E:
            k += 1
        if k < len(text) and ord(text[k]) == 0xE007F:
            return True
    return False


def remove_invisible(text, include_ambiguous=False):
    """Снятие невидимых символов по классификации риска.

    Возвращает (cleaned, report):
      report["removed"]  — снятые (класс safe; при include_ambiguous — и
                           ambiguous: действие remove или to-space);
      report["reported"] — показанные, но не тронутые (dangerous всегда;
                           ambiguous при include_ambiguous=False);
      report["flag_sequences_kept"] — теговые символы эмодзи-флагов (не
                           снимаются никогда);
      report["warnings"] — предупреждения opt-in-снятия.
    Записи: {"codepoint": "U+XXXX", "name", "class", "action", "line"}
    (line — 1-based). Режим «удалить всё невидимое» отсутствует по
    построению: dangerous не снимается ни при каком флаге.
    """
    out = []
    report = {"removed": [], "reported": [], "flag_sequences_kept": [],
              "warnings": []}
    line = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            out.append(ch)
            i += 1
            continue
        entry = classify_codepoint(ord(ch))
        if entry is None:
            if _is_invisible_unclassified(ch):
                # Fail-safe: невидимый вне таблицы — dangerous, только отчёт.
                entry = ("dangerous", "unclassified invisible",
                         "символ вне таблицы классификации: показывается, "
                         "не снимается", "report-only")
            else:
                out.append(ch)
                i += 1
                continue
        cls, name, risk, action = entry
        rec = {"codepoint": "U+%04X" % ord(ch), "name": name, "class": cls,
               "action": action, "line": line}
        if cls == "safe" and _is_flag_tag_context(text, i):
            report["flag_sequences_kept"].append(rec)
            out.append(ch)
            i += 1
            continue
        if cls == "safe":
            report["removed"].append(rec)
            i += 1
            continue
        if cls == "ambiguous":
            if include_ambiguous:
                if action == "to-space":
                    out.append(" ")
                report["removed"].append(rec)
                report["warnings"].append(
                    "%s (U+%04X, строка %d): снят opt-in — возможно "
                    "изменение отображения (%s)"
                    % (name, ord(ch), line, risk))
            else:
                out.append(ch)
                report["reported"].append(rec)
            i += 1
            continue
        # dangerous — только отчёт, символ остаётся.
        out.append(ch)
        report["reported"].append(rec)
        i += 1
    return "".join(out), report
