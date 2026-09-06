#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""protected_regions.py — единый источник правил защищённых областей.

Защищённая область — фрагмент текста, который инструменты очистки и
форматирования обязаны оставлять байт-в-байт неизменным:

  1. inline-code: серии обратных кавычек фиксированной длины (серия из N
     открывает спан, закрывает следующая серия ровно из N; серии другой
     длины внутри — содержимое; незакрытая серия тянет спан до конца
     строки) — та же семантика, что в scripts/check_markers.py и
     demo/engine.js;
  2. fenced-блоки ``` и ~~~ по принятой в проекте конвенции: отступ до
     трёх пробелов, закрывает блок строка из того же символа длиной не
     меньше открывающей без иного содержимого; незакрытый забор остаток
     файла не маскирует;
  3. YAML-frontmatter (--- ... --- в начале файла) — данные, не проза;
  4. URL: `(?:https?://|www\\.)` до пробела и границ `<>"'«»)]` — то же
     выражение, что маскирует URL в детекторе (check_markers.URL_MASK_RX);
  5. поддерживаемая разметка: HTML-тег `<...>` целиком (кавычки атрибутов
     внутри тега — часть тега);
  6. значимые Unicode-последовательности: ZWJ (U+200D) в эмодзи-контексте
     (сосед слева и справа из набора EMOJI_CONTEXT) — составные эмодзи
     (семья, флаги, профессии). Граница набора совпадает с lookaround-
     классами детектора zero_width: ZWJ вне эмодзи-контекста остаётся
     артефактом и защиты не получает.

Модуль зеркалится в src/humanizer_ru/ (гейт check_pkg_sync.py): копия
пакета обязана быть побайтно равна оригиналу. Только стандартная
библиотека; все функции детерминированы.
"""
from __future__ import annotations

import re

# Набор эмодзи-контекста для ZWJ — те же диапазоны, что в lookaround
# детектора zero_width (scripts/check_markers.py, кейс zero_width).
EMOJI_CONTEXT = "\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\U0001F1E6-\U0001F1FF"

_EMOJI_CH_RX = re.compile("[" + EMOJI_CONTEXT + "]")

# URL-спан: то же выражение, что URL_MASK_RX детектора.
URL_RX = re.compile(r"(?:https?://|www\.)[^\s<>«»\"')\]]+")

# HTML-тег: открывающий/закрывающий/комментарий/doctype. Выражение —
# ориентир для документации; фактические границы считает сканер
# html_tag_spans: кавычки атрибутов защищают «>» внутри значения,
# перевод строки внутри тега допустим (многострочные конструкции).
HTML_TAG_RX = re.compile(r"<[a-zA-Z!/][^>\n]*>")
_TAG_OPEN_RX = re.compile(r"<[a-zA-Z!/]")


def html_tag_spans(text: str) -> list:
    """Интервалы (start, end) HTML-тегов в тексте (многострочные).

    Границы: открывающий символ «<» с ASCII-буквой, «!» или «/» далее;
    конец — первый «>» ВНЕ кавычек атрибута («"» и «'»); перевод строки
    внутри тега допустим. Незакрытая кавычка: неуверенность трактуется в
    пользу сохранения — область защищается до конца строки. «>» без
    закрывающей кавычки и без кавычек вообще тегом не считается.
    """
    spans = []
    n = len(text)
    i = 0
    while i < n:
        m = _TAG_OPEN_RX.search(text, i)
        if m is None:
            break
        pos = m.end()
        quote = ""
        closed_at = -1
        line_end = text.find("\n", pos)
        if line_end < 0:
            line_end = n
        while pos < n:
            ch = text[pos]
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch == ">":
                closed_at = pos
                break
            pos += 1
        if closed_at >= 0:
            spans.append((m.start(), closed_at + 1))
            i = closed_at + 1
            continue
        if quote:
            # незакрытая кавычка атрибута: сохраняем участок до конца строки
            spans.append((m.start(), line_end))
            i = line_end
            continue
        i = m.start() + 1
    return spans

ZWJ = "\u200d"


def _in_emoji_context(ch: str) -> bool:
    return bool(ch) and bool(_EMOJI_CH_RX.match(ch))


def zwj_is_protected(text: str, pos: int) -> bool:
    """ZWJ в позиции pos защищён, если соседи слева и справа — эмодзи-контекст.

    Семантика совпадает с lookaround детектора: (?<![EMOJI])U+200D(?![EMOJI])
    считается артефактом, защищён только ZWJ между эмодзи-символами.
    """
    if text[pos] != ZWJ:
        return False
    prev_ch = text[pos - 1] if pos > 0 else ""
    next_ch = text[pos + 1] if pos + 1 < len(text) else ""
    return _in_emoji_context(prev_ch) and _in_emoji_context(next_ch)


def zwj_protected_positions(text: str) -> set:
    """Позиции всех защищённых ZWJ текста (абсолютные, 0-based)."""
    return {i for i, ch in enumerate(text)
            if ch == ZWJ and zwj_is_protected(text, i)}


def code_spans(line: str) -> list:
    """Интервалы (start, end) содержимого inline-code строки.

    Семантика серий бэктиков (N42): серия из N открывает спан, закрывает
    следующая серия ровно из N; серии другой длины внутри — содержимое;
    незакрытая серия тянет спан до конца строки. Интервалы — содержимое
    без самих разделителей, как _code_spans в scripts/check_markers.py.
    """
    runs = []
    i, n = 0, len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    spans = []
    k = 0
    while k < len(runs):
        length = runs[k][1]
        closer = -1
        for t in range(k + 1, len(runs)):
            if runs[t][1] == length:
                closer = t
                break
        if closer == -1:
            spans.append((runs[k][0] + length, n))
            break
        spans.append((runs[k][0] + length, runs[closer][0]))
        k = closer + 1
    return spans


def _leading_count(s: str, ch: str) -> int:
    n = 0
    while n < len(s) and s[n] == ch:
        n += 1
    return n


_FENCE_OPEN_RX = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def fenced_line_indices(lines: list) -> set:
    """Индексы строк (0-based) внутри ЗАКРЫТЫХ блоков ``` и ~~~.

    Конвенция проекта (check_markers/engine.js/polish): отступ до трёх
    пробелов; закрывает блок строка, начинающаяся с того же символа длиной
    не меньше открывающей, без иного содержимого кроме пробельного
    хвоста; незакрытый забор остаток файла не маскирует.
    """
    inside = set()
    fence_char = None
    open_line = -1
    fence_len = 0
    for idx, line in enumerate(lines):
        stripped = line.lstrip(" \t")
        if len(line) - len(stripped) > 3:
            continue
        if fence_char is None:
            m = _FENCE_OPEN_RX.match(line)
            if m:
                fence_char = m.group(1)[0]
                open_line = idx
                fence_len = len(m.group(1))
            continue
        close_len = _leading_count(stripped, fence_char)
        trail = stripped.rstrip()
        if close_len >= fence_len and trail == fence_char * close_len:
            for k in range(open_line, idx + 1):
                inside.add(k)
            fence_char = None
            open_line = -1
            fence_len = 0
    return inside


def frontmatter_line_indices(lines: list) -> set:
    """Индексы строк YAML-frontmatter (--- ... --- в начале файла)."""
    if not lines or lines[0].strip() != "---":
        return set()
    idxs = {0}
    for j in range(1, len(lines)):
        idxs.add(j)
        if lines[j].strip() == "---":
            return idxs
    # Незакрытый frontmatter защищает остаток файла: данные не становятся
    # прозой (прежнее поведение typographic-режима сохранено).
    return idxs


def url_spans(text: str) -> list:
    """Интервалы (start, end) URL в тексте (работает и для одной строки)."""
    return [(m.start(), m.end()) for m in URL_RX.finditer(text)]


def merge_spans(spans: list) -> list:
    """Слияние перекрывающихся интервалов; результат отсортирован."""
    merged = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def protected_line_spans(line: str) -> list:
    """Объединённые защищённые интервалы одной строки.

    inline-code + URL + HTML-теги (слитно, отсортировано). Межстрочные
    области (fenced-блоки, frontmatter) вызываются отдельно по индексам
    строк — они защищают строки целиком. Для многострочных конструкций
    пользуйтесь protected_text_spans / protected_spans_by_line.
    """
    return merge_spans(code_spans(line) + url_spans(line)
                       + html_tag_spans(line))


def _line_offsets(text: str) -> list:
    offs = []
    start = 0
    for line in text.split("\n"):
        offs.append((start, start + len(line)))
        start += len(line) + 1
    return offs


def protected_text_spans(text: str, protect_urls: bool = True,
                         protect_html: bool = True) -> list:
    """Абсолютные защищённые интервалы всего текста (слитно, сортировано).

    fenced-блоки и frontmatter — строки целиком; в остальных строках
    инлайн-код и URL; HTML-теги — по всему тексту, включая многострочные
    (кавычки атрибутов и перевод строки внутри тега уважаются).
    """
    lines = text.split("\n")
    offs = _line_offsets(text)
    fenced = fenced_line_indices(lines)
    front = frontmatter_line_indices(lines)
    spans = []
    for i, line in enumerate(lines):
        s, _e = offs[i]
        if i in fenced or i in front:
            spans.append((s, s + len(line)))
            continue
        for cs, ce in code_spans(line):
            spans.append((s + cs, s + ce))
        if protect_urls:
            for us, ue in url_spans(line):
                spans.append((s + us, s + ue))
    if protect_html:
        spans.extend(html_tag_spans(text))
    return merge_spans(spans)


def protected_spans_by_line(text: str, protect_urls: bool = True,
                            protect_html: bool = True) -> list:
    """Проекция protected_text_spans на строки: список по индексу строки.

    Многострочная область покрывает свои строки целиком по части:
    преобразование вне защит не видит её содержимое ни на одной строке.
    """
    offs = _line_offsets(text)
    spans = protected_text_spans(text, protect_urls, protect_html)
    out = [[] for _ in offs]
    for s, e in spans:
        for i, (ls, le) in enumerate(offs):
            if e <= ls:
                break
            if s >= le:
                continue
            out[i].append((max(s, ls) - ls, min(e, le) - ls))
    return [merge_spans(x) for x in out]


def protected_regions(text: str) -> list:
    """Список (вид, текст) всех защищённых областей документа.

    Виды: fenced, frontmatter, code, url, html, zwj. Порядок
    детерминирован: по строкам сверху вниз (fenced/frontmatter — строки
    целиком, затем code/url внутри строки), затем HTML-теги по тексту
    (многострочный тег — одна область), затем ZWJ-пары по позициям.
    Используется инвариантами сохранения: каждый элемент обязан
    присутствовать в результате преобразования неизменным.
    """
    lines = text.split("\n")
    fenced = fenced_line_indices(lines)
    front = frontmatter_line_indices(lines)
    out = []
    for i, line in enumerate(lines):
        if i in fenced:
            if line:
                out.append(("fenced", line))
            continue
        if i in front:
            if line:
                out.append(("frontmatter", line))
            continue
        for s, e in code_spans(line):
            if e > s:
                out.append(("code", line[s:e]))
        for s, e in url_spans(line):
            out.append(("url", line[s:e]))
    # HTML-теги — по всему тексту: многострочный тег — одна область.
    for s, e in html_tag_spans(text):
        out.append(("html", text[s:e]))
    for pos in sorted(zwj_protected_positions(text)):
        out.append(("zwj", text[max(0, pos - 1):pos + 2]))
    return out


def protected_texts(text: str) -> list:
    """Тексты всех защищённых областей документа (без вида)."""
    return [t for _k, t in protected_regions(text)]


def remove_invisibles(seg: str, mapping: dict) -> str:
    """Замена невидимых символов по отображению с охраной защищённых ZWJ.

    mapping: {символ: замена} (например, NBSP -> пробел, ZWSP -> "").
    ZWJ в эмодзи-контексте (zwj_is_protected) сохраняется независимо от
    mapping: разрушение составного эмодзи — потеря смысла, а не снятие
    машинного слоя.

    Зазор схлопывается В ТОЧКЕ СЪЁМА: снятие нулевой ширины между двумя
    пробелами не оставляет двойной пробел, замена на пробел рядом с
    существующим пробелом суммарно даёт один. Авторская типографика вне
    точек съёма не трогается (схлопывающей подстановки по всему тексту
    нет).
    """
    out = []
    n = len(seg)
    i = 0
    while i < n:
        ch = seg[i]
        if ch in mapping and not (ch == ZWJ and zwj_is_protected(seg, i)):
            repl = mapping[ch]
            left = out[-1] if out else ""
            right = seg[i + 1] if i + 1 < n else ""
            if left == " " and right == " ":
                i += 2          # зазор схлопнут: правый пробел поглощён
                continue
            if repl == "":
                i += 1          # снятие без следа
                continue
            if left == " ":
                i += 1          # пробел уже есть слева — замена не дописывается
                continue
            if right == " ":
                out.append(" ")
                i += 2          # замена поставлена, правый пробел поглощён
                continue
            out.append(repl)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- selftest

def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    # code spans: семантика серий (N42).
    case("одинарные бэктики", code_spans("`a b`") == [(1, 4)])
    case("двойные бэктики с одинарным внутри",
         code_spans("``a ` b``") == [(2, 7)])
    case("незакрытая серия тянется до конца строки",
         code_spans("x `abc") == [(3, 6)])
    case("серии другой длины внутри — содержимое",
         code_spans("``a``b`c``") == [(2, 3), (7, 10)])

    # fenced-блоки.
    lines = ["текст", "```", "код", "```", "снова текст"]
    case("закрытый забор маскирует строки целиком",
         fenced_line_indices(lines) == {1, 2, 3})
    case("незакрытый забор не маскирует остаток",
         fenced_line_indices(["a", "```", "b"]) == set())
    case("отступ больше трёх не открывает забор",
         fenced_line_indices(["a", "    ```", "b", "    ```"]) == set())
    case("тильдовый забор", fenced_line_indices(["~~~", "x", "~~~"]) == {0, 1, 2})

    # frontmatter.
    case("frontmatter в начале файла",
         frontmatter_line_indices(["---", "k: v", "---", "проза"]) == {0, 1, 2})
    case("без frontmatter", frontmatter_line_indices(["проза", "---"]) == set())
    case("незакрытый frontmatter защищает до конца (данные)",
         frontmatter_line_indices(["---", "k: v"]) == {0, 1})

    # URL.
    spans = url_spans("См. https://example.org/a?b=1&c=2 тут")
    case("URL-спан находится", spans and "https://example.org/a?b=1&c=2"
         == "См. https://example.org/a?b=1&c=2 тут"[spans[0][0]:spans[0][1]])
    case("URL останавливается на закрывающей скобке markdown",
         url_spans("[x](https://e.org/a)") == [(4, 19)])

    # HTML-теги.
    tags = html_tag_spans('<a href="x">текст</a>')
    case("HTML-тег целиком с кавычками атрибутов",
         len(tags) == 2 and '<a href="x">' == '<a href="x">текст</a>'[tags[0][0]:tags[0][1]])
    src = 'Проза <span title="a > b..." data-x="q">текст</span>.'
    tags = html_tag_spans(src)
    case("«>» внутри кавычек атрибута не закрывает тег",
         len(tags) == 2
         and src[tags[0][0]:tags[0][1]] == '<span title="a > b..." data-x="q">')
    src2 = 'Проза <span\n title="x...">текст</span>.\n'
    tags2 = html_tag_spans(src2)
    case("многострочный тег защищён целиком",
         len(tags2) == 2
         and src2[tags2[0][0]:tags2[0][1]] == '<span\n title="x...">')
    src3 = 'Проза <span title="незакрытая\nдалее текст'
    tags3 = html_tag_spans(src3)
    case("незакрытая кавычка атрибута: сохранение до конца строки",
         len(tags3) == 1
         and src3[tags3[0][0]:tags3[0][1]] == '<span title="незакрытая')
    case("проза без тега не защищается",
         html_tag_spans("a < b и c > d") == [])
    by_line = protected_spans_by_line(src2)
    case("проекция многострочного тега покрывает его строки",
         len(by_line) >= 2 and bool(by_line[0]) and bool(by_line[1]))

    # ZWJ.
    family = "\U0001F468\u200d\U0001F469\u200d\U0001F467"
    case("ZWJ семьи защищён", zwj_protected_positions(family) == {1, 3})
    flag = "\U0001F3F3\uFE0F\u200d\U0001F308"
    case("ZWJ радужного флага защищён (сосед FE0F)",
         zwj_protected_positions(flag) == {2})
    cyr = "сло\u200dво"
    case("ZWJ внутри кириллицы не защищён", zwj_protected_positions(cyr) == set())

    # remove_invisibles.
    mapping = {"\u200b": "", "\u200d": "", "\u00a0": " "}
    case("невидимые снимаются по отображению",
         remove_invisibles("a\u200bb\u00a0c", mapping) == "ab c")
    case("защищённый ZWJ переживает снятие",
         remove_invisibles(family, mapping) == family)
    case("незащищённый ZWJ снимается",
         remove_invisibles(cyr, mapping) == "слово")
    case("схлопывание в точке съёма: двойного пробела нет",
         remove_invisibles("слово \u200b слово", mapping) == "слово слово")
    case("замена NBSP рядом с пробелом даёт один пробел",
         remove_invisibles("a\u00a0 b", mapping) == "a b"
         and remove_invisibles("a \u00a0b", mapping) == "a b"
         and remove_invisibles("a \u00a0 b", mapping) == "a b")
    case("авторский двойной пробел вне точек съёма сохранён",
         remove_invisibles("авторский  текст", mapping) == "авторский  текст")

    # protected_texts.
    doc = 'Проза `код "x"` и https://e.org/a...b и <a href="q">ссылка</a> ' + family
    texts = protected_texts(doc)
    case("защищённые тексты включают код, URL, тег и ZWJ-пары",
         any('код "x"' == t for t in texts)
         and any(t == "https://e.org/a...b" for t in texts)
         and any(t == '<a href="q">' for t in texts)
         and any(ZWJ in t for t in texts))

    print("САМОПРОВЕРКА protected_regions: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(selftest())
    raise SystemExit("модуль защищённых областей; самопроверка: --selftest")
