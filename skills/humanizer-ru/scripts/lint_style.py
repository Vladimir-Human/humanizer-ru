#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Find signs of machine style and technical hygiene risks in Russian text (RuSlop):
#          fixed phrases from the sign table of SKILL.md plus calibrated structure, stylometry and
#          hygiene metrics (dashes, sentence and paragraph rhythm, nominalization chains, bold,
#          headings, emoji, mixed Cyrillic/Latin subwords, invisible characters and watermarks).
#          It evaluates style and text hygiene, never authorship: people write like this too.
#          Used by step 7 of the skill as a self-check of the result.
# SCOPE: deterministic, stdlib only; reads rules.json next to this file (or --rules); prints a
#        Russian report or --json. Text inside fenced blocks (```/~~~) and inside quotes is not
#        checked for phrase rules or nominalization chains; inline code is skipped for phrases,
#        dashes, bold and mixed_script; URLs/mail are skipped for mixed_script and non-paste
#        phrases; invisible skips string/template/regex literals inside code-like fences and inline
#        code.
# DEPENDS: Python 3.8+ standard library; rules.json (single source, also read by site/check).
# LINKS: M-LINT-STYLE; R-LINT-STYLE; R-RULES-EVIDENCE; R-DETECTOR-RISK; V-M-LINT-STYLE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load_rules: rules.json -> compiled phrase rules and metric settings; \b means a Cyrillic-aware
#             word boundary (expanded the same way in site/check/engine.js).
# lint: text -> report dict (hits with examples, metrics, score, level).
# render: report dict -> Russian text.
# main: CLI `lint_style.py file|- [--json] [--rules PATH] [--max-score X] [--encoding ENC]`.
# END_MODULE_MAP
"""Поиск признаков машинного стиля и технических следов в русском тексте.

    python lint_style.py текст.txt          # отчёт
    python lint_style.py текст.txt --json   # отчёт в JSON
    python lint_style.py -                  # чтение из stdin (UTF-8)

Это оценка стиля и чистоты текста, а не авторства. Код выхода: 0 — отчёт готов;
1 — балл выше --max-score; 2 — ошибка чтения файла или правил.
"""
from __future__ import annotations

import argparse
import codecs
import json
import re
import statistics
import sys
import unicodedata
from bisect import bisect_right
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

RULES_PATH = Path(__file__).resolve().parent / "rules.json"

# START_BLOCK_ENGINE
# Everything here is mirrored line by line in site/check/engine.js; change both together
# (tests/test_lint.py runs both on the same fixtures).
ACUTE = chr(0x0301)
COMB = "\u0301\u0306\u0308"
LAT_EXT = "\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff\ua7dc"
GK = "\u0370-\u0374\u0376\u0377\u037a-\u037d\u037f\u0386\u0388-\u038a\u038c\u038e-\u03a1\u03a3-\u03f5\u03f7-\u03ff\u1fb0\u1fb8\u1fe8"
LAT = "A-Za-z" + LAT_EXT + GK
W = "0-9" + LAT + "А-Яа-яЁё" + COMB + "_"
BOUNDARY = "(?:(?<=[%s])(?![%s])|(?<![%s])(?=[%s]))" % (W, W, W, W)
WORD_RX = re.compile("[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+(?:-[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+)*")
QUOTE_RX = re.compile(
    r'«(?:[^«»\n]|«[^«»\n]*»){0,600}»'
    r'|„[^“”\n]{0,600}[“”]'
    r'|“[^“”\n]{0,600}”'
    r'|(?<![0-9A-Za-zА-Яа-яЁё])"(?!\s)(?:[^"\n]|(?<=[\s(])"(?!\s)[^"\n]{1,120}(?<!\s)"(?=[\s.,;:!?…—–\-)])){0,600}(?<!\s)"'
)
SENT_SPLIT_RX = re.compile("[.!?…]+(?=\\s|$)|\\n+")
DASH_RX = re.compile("(?<=[ \\u00a0])[—–-](?=[ \\u00a0])")
BULLET_PREFIX_RX = re.compile("^[ \\t\\u00a0]*(?:>[ \\t\\u00a0]*)*$")
BOLD_RX = re.compile("\\*\\*[^*\\n]+?\\*\\*")
HEADING_RX = re.compile("^(?:>[ \\t\\u00a0]*)*(?:#{1,6}\\s+\\S[^\\n]*|\\*\\*[^*\\n]+\\*\\*:?)$")
LIST_LINE_RX = re.compile("^(?:>[ \\t\\u00a0]*)*(?:[-*•+]|[0-9]+[.)])\\s+\\S")
TABLE_SEP_LINE_RX = re.compile(
    "^[ \\t\\u00a0]*(?:>[ \\t\\u00a0]*)*(?:"
    "\\|[ \\t]*:?-{2,}:?[ \\t]*(?:\\|[ \\t]*:?-{2,}:?[ \\t]*)*\\|?|"
    "[ \\t]*:?-{2,}:?[ \\t]*(?:\\|[ \\t]*:?-{2,}:?[ \\t]*)+\\|?"
    ")[ \\t]*$"
)
LINK_MAIL_RX = re.compile(
    r"(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\.)(?:\([^\s<>«»\"'()\]`]*\)|[^\s<>«»\"')\]`])+"
    r"|(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\.[A-Za-zА-Яа-яЁё]{2,}"
    r"|(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)"
)
SUBWORD_RX = re.compile("[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+")
LAT_RX = re.compile("[" + LAT + "]")
CYR_RX = re.compile("[А-Яа-яЁё]")
NOM_SPLIT_RX = re.compile("[.!?…,:;()|\\n—–«»\"“”]+")
CYR_TOK_RX = re.compile("[А-Яа-яЁёѢѣІіѲѳѴѵ" + ACUTE + "]{2,}")
PRE1918_TRANS = str.maketrans({"ё": "е", "ѣ": "е", "і": "и", "ѳ": "ф", "ѵ": "и"})
NOM_WORD_RX = re.compile(
    "^[а-я]{3,}(?:ени(?:е|я|ю|ем|и|й|ям|ями|ях)|ани(?:е|я|ю|ем|и|й|ям|ями|ях)|"
    "ост(?:ь|и|ью|ей|ям|ями|ях)|ств(?:о|а|у|ом|е|ам|ами|ах)|аци(?:я|и|ю|ей|й|ям|ями|ях))$"
)
NON_NOM_RX = re.compile(
    "^(?:компани[а-я]*|кампани[а-я]*|армени[а-я]*|германи[а-я]*|испани[а-я]*|"
    "словени[а-я]*|федераци[а-я]*|посредством|полностью|впоследствии|частности|"
    "новост[а-я]*|рождения)$"
)
NOM_GEN_RX = re.compile("^[а-я]{3,}(?:ени(?:я|й)|ани(?:я|й)|ост(?:и|ей)|ств(?:а)|аци(?:и|й))$")
ADJ_GEN_RX = re.compile("^[а-я]{3,}(?:ого|его|ой|ей|ых|их)$")
FINITE_VERB_RX = re.compile(
    "^(?:[а-я]{2,}(?:ет|ют|ут|ит|ат|ят|ется|ются|утся|ится|атся|ятся|"
    "ал|ала|ало|али|ил|ила|ило|или|ел|ела|ело|ели|ул|ула|уло|ули|"
    "ыл|ыла|ыло|ыли|ял|яла|яло|яли|лся|лась|лось|лись|ялся|ялась|ялось|ялись)|"
    "(?:не|по|при|пре|про|от|у|вы|с|за|до|на|пере)?бы(?:л|ла|ло|ли)|"
    "(?:по|при|про|вы|у|во|до|за|на|от|пере|под|обо|разо|со|снизо)?(?:шел|шла|шло|шли)|"
    "(?:по|с|вы|превоз|изне)?мог(?:ла|ло|ли)?|"
    "(?:пере|про|вы|от|по|при|раз|с|соз|из|за|на|об|под|пре|в)?(?:дал|дала|дало|дали|вел|вела|вело|вели)|"
    "(?:по|про|вы|от|при|за|на|пере|у|с|до)?(?:жил|жила|жило|жили|нес|несла|несло|несли|рос|росла|росло|росли))$"
)
NON_VERB_RX = re.compile(
    "^(?:[а-я]+[аия]тели|модели|недели|цели|щели|мебели|комитет|интернет|бюджет|билет|"
    "секрет|кабинет|университет|факультет|авторитет|приоритет|суверенитет|пакет|макет|"
    "букет|сюжет|привет|совет|ответ|примет|предмет|запрет|портрет|расцвет|рассвет|свет|"
    "цвет|счет|отчет|расчет|зачет|учет|полет|вертолет|самолет|пилот|генерал|журнал|"
    "канал|финал|квартал|материал|потенциал|оригинал|сигнал|филиал|сериал|фестиваль|"
    "капитал|металл|адвокат|депутат|кандидат|аппарат|результат|формат|климат|мандат|"
    "агрегат|автомат|дипломат|экспонат|чемпионат|препарат|сертификат|комбинат|минут|"
    "институт|маршрут|статут|атрибут|дефицит|кредит|визит|транзит|лимит|магнит|гранит|"
    "алфавит|аудит|павел|михаил|кирилл|даниил|отдел|отдела|предел|предела|раздел|"
    "раздела|пробел|узел|козел|орел|котел|факел|ангел|сначала|материала|канала|"
    "журнала|квартала|финала|капитала|сигнала|филиала|сериала|генерала)$"
)
_FENCE_HEAD_RX = re.compile(r"^[ ]{0,3}(?:`{3,}|~{3,})")
_PROSE_FENCE_TAGS = frozenset({"", "markdown", "md", "text", "txt", "plain", "plaintext"})
_REGEX_PREV = frozenset("=(,:;!&|?+-~*{[\n\r")
_REGEX_KW = frozenset(("return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"))
_REGEX_FLAGS = frozenset("dgimsuvy")

W_START = "(?<![%s])" % W
W_END = "(?![%s])" % W


def _char_class_from_spec(cps, ranges) -> str:
    parts = [re.escape(chr(cp)) for cp in cps]
    for a, b in ranges:
        parts.append(re.escape(chr(a)) if a == b else "%s-%s" % (re.escape(chr(a)), re.escape(chr(b))))
    return "[" + "".join(parts) + "]"


def load_rules(path=RULES_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for rule in data["phrases"]:
        flags = 0
        for f in rule.get("flags", "i"):
            flags |= {"i": re.IGNORECASE, "m": re.MULTILINE}[f]
        pat = re.sub(r"\\b(?=[0-9A-Za-zА-Яа-яЁё])", lambda _: W_START, rule["re"])
        pat = re.sub(r"(?<=[0-9A-Za-zА-Яа-яЁё])\\b", lambda _: W_END, pat)
        rule["rx"] = re.compile(pat.replace("\\b", BOUNDARY), flags)
    m = data["metrics"]
    m["emoji_per_1000"]["_rx"] = re.compile(_char_class_from_spec((), m["emoji_per_1000"]["ranges"]))
    inv = m["invisible"]
    inv_fast = set(inv["codepoints"])
    inv_big = []
    for a, b in inv.get("ranges", ()):
        if b - a <= 4096:
            inv_fast.update(range(a, b + 1))
        else:
            inv_big.append((a, b))
    inv["_set"] = inv_fast
    inv["_big"] = inv_big
    inv["_rx"] = re.compile(
        _char_class_from_spec(
            list(inv["codepoints"]) + [0x200C, 0x200D, 0xFE0F],
            list(inv.get("ranges", ())) + [[0xE0000, 0xE007F]],
        )
    )
    return data


def _all_fence_spans(text: str) -> List[Tuple[int, int]]:
    """Linear O(N) fenced code block scanner (0-3 spaces, >=3 ` or ~, matching closer)."""
    cand = []
    n = len(text)
    pos = 0
    while pos < n:
        nl = text.find("\n", pos)
        line_end = n if nl < 0 else nl
        content_end = line_end - 1 if line_end > pos and text[line_end - 1] == "\r" else line_end
        i = pos
        sp = 0
        while i < content_end and text[i] == " " and sp < 4:
            i += 1
            sp += 1
        if sp <= 3 and i < content_end and text[i] in ("`", "~"):
            ch = text[i]
            j = i
            while j < content_end and text[j] == ch:
                j += 1
            flen = j - i
            if flen >= 3:
                rest = text[j:content_end]
                is_closer = all(c in (" ", "\t") for c in rest)
                if is_closer or ch == "~" or "`" not in rest:
                    cand.append((pos, line_end, ch, flen, is_closer))
        if nl < 0:
            break
        pos = nl + 1
    if len(cand) < 2:
        return []
    m = len(cand)
    max_bt = [0] * (m + 1)
    max_ti = [0] * (m + 1)
    for idx in range(m - 1, -1, -1):
        _, _, ch, flen, is_closer = cand[idx]
        max_bt[idx] = max(max_bt[idx + 1], flen if (is_closer and ch == "`") else 0)
        max_ti[idx] = max(max_ti[idx + 1], flen if (is_closer and ch == "~") else 0)
    spans: List[Tuple[int, int]] = []
    idx = 0
    while idx < m:
        open_start, _, ch, flen, _ = cand[idx]
        mc = max_bt if ch == "`" else max_ti
        if mc[idx + 1] < flen:
            idx += 1
            continue
        j = idx + 1
        while j < m:
            _, close_end, c2, flen2, is_closer2 = cand[j]
            if is_closer2 and c2 == ch and flen2 >= flen:
                spans.append((open_start, close_end))
                idx = j + 1
                break
            j += 1
        else:
            idx += 1
    return spans


def _inline_code_spans(text: str, excluded: List[Tuple[int, int]] = ()) -> List[Tuple[int, int]]:
    """Linear O(N) single-line multi-backtick inline code matcher outside excluded spans."""
    spans: List[Tuple[int, int]] = []
    n = len(text)
    ex_i = 0
    ex_n = len(excluded)
    pos = 0
    while pos < n:
        while ex_i < ex_n and excluded[ex_i][1] <= pos:
            ex_i += 1
        if ex_i < ex_n and excluded[ex_i][0] <= pos:
            pos = excluded[ex_i][1]
            continue
        nl = text.find("\n", pos)
        line_end = n if nl < 0 else nl
        seg_end = min(line_end, excluded[ex_i][0]) if ex_i < ex_n else line_end
        if "`" in text[pos:seg_end]:
            runs: List[Tuple[int, int, bool]] = []
            by_len: Dict[int, List[int]] = {}
            i = pos
            while i < seg_end:
                if text[i] == "`":
                    s = i
                    bs = 0
                    b = s - 1
                    while b >= pos and text[b] == "\\":
                        bs += 1
                        b -= 1
                    while i < seg_end and text[i] == "`":
                        i += 1
                    rlen = i - s
                    ridx = len(runs)
                    runs.append((s, rlen, (bs & 1) == 1))
                    by_len.setdefault(rlen, []).append(ridx)
                else:
                    i += 1
            ptr: Dict[int, int] = {}
            r = 0
            while r < len(runs):
                s, rlen, esc = runs[r]
                if esc:
                    r += 1
                    continue
                lst = by_len[rlen]
                p = ptr.get(rlen, 0)
                while p < len(lst) and lst[p] <= r:
                    p += 1
                ptr[rlen] = p
                if p < len(lst):
                    cr = lst[p]
                    cs, clen, _ = runs[cr]
                    spans.append((s, cs + clen))
                    r = cr + 1
                else:
                    r += 1
        if seg_end < line_end:
            pos = seg_end
        elif nl < 0:
            break
        else:
            pos = nl + 1
    return spans


def _is_ident_char(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9") or ("а" <= c <= "я") or ("А" <= c <= "Я") or c in "_$ёЁ"


def _code_literal_spans(body: str, allow_backtick: bool) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    n = len(body)
    i = 0
    prev_sig = "\n"
    prev_word_start = -1
    prev_word_end = -1
    regex_fail_until = -1
    while i < n:
        ch = body[i]
        if ch in " \t\f\v":
            i += 1
            continue
        if ch in "\r\n":
            prev_sig = "\n"
            prev_word_start = prev_word_end = -1
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = body[i + 1]
            if nxt == "/" and (i == 0 or body[i - 1] != ":"):
                nl = body.find("\n", i + 2)
                i = n if nl < 0 else nl
                continue
            if nxt == "*":
                end_c = body.find("*/", i + 2)
                if end_c < 0:
                    break
                prev_sig = " "
                prev_word_start = prev_word_end = -1
                i = end_c + 2
                continue
        if ch in ("'", '"') and body[i:i + 3] == ch * 3:
            end_q = body.find(ch * 3, i + 3)
            if end_q >= 0:
                spans.append((i, end_q + 3))
                prev_sig = ch
                prev_word_start = prev_word_end = -1
                i = end_q + 3
            else:
                prev_sig = ch
                prev_word_start = prev_word_end = -1
                i += 3
            continue
        if ch in ("'", '"'):
            k = i + 1
            closed = False
            while k < n:
                ck = body[k]
                if ck == "\\" and k + 1 < n and body[k + 1] != "\n":
                    k += 2
                    continue
                if ck == ch:
                    closed = True
                    k += 1
                    break
                if ck in "\r\n":
                    break
                k += 1
            if closed:
                spans.append((i, k))
            prev_sig = ch
            prev_word_start = prev_word_end = -1
            i = k
            continue
        if allow_backtick and ch == "`":
            k = i + 1
            closed = False
            while k < n:
                ck = body[k]
                if ck == "\\" and k + 1 < n:
                    k += 2
                    continue
                if ck == "`":
                    closed = True
                    k += 1
                    break
                k += 1
            if closed:
                spans.append((i, k))
            prev_sig = "`"
            prev_word_start = prev_word_end = -1
            i = k
            continue
        if ch == "/" and i >= regex_fail_until:
            prev_kw = prev_word_end > prev_word_start and body[prev_word_start:prev_word_end] in _REGEX_KW
            if prev_sig in _REGEX_PREV or prev_kw:
                k = i + 1
                in_cls = False
                closed_rx = False
                while k < n:
                    ck = body[k]
                    if ck in "\r\n":
                        break
                    if ck == "\\" and k + 1 < n and body[k + 1] not in "\r\n":
                        k += 2
                        continue
                    if ck == "[":
                        in_cls = True
                    elif ck == "]" and in_cls:
                        in_cls = False
                    elif ck == "/" and not in_cls:
                        closed_rx = True
                        break
                    k += 1
                if closed_rx and k > i + 1:
                    f_end = k + 1
                    seen_f = set()
                    valid_f = True
                    while f_end < n and body[f_end] in _REGEX_FLAGS:
                        if body[f_end] in seen_f:
                            valid_f = False
                            break
                        seen_f.add(body[f_end])
                        f_end += 1
                    after_c = body[f_end] if f_end < n else ""
                    if valid_f and not (after_c and (_is_ident_char(after_c) or after_c == "/")):
                        spans.append((i, f_end))
                        prev_sig = "/"
                        prev_word_start = prev_word_end = -1
                        i = f_end
                        continue
                regex_fail_until = k
        if _is_ident_char(ch) and not ("0" <= ch <= "9"):
            ws = i
            i += 1
            while i < n and _is_ident_char(body[i]):
                i += 1
            prev_sig = body[i - 1]
            prev_word_start, prev_word_end = ws, i
            continue
        prev_sig = ch
        prev_word_start = prev_word_end = -1
        i += 1
    return spans


def _is_code_fence(info: str, fbody: str) -> bool:
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", fbody)
    if sum(1 for x in letters if x > "z") < 0.3 * max(1, len(letters)):
        return True
    parts = info.strip().split(None, 1)
    tag = parts[0].lower() if parts else ""
    if tag in _PROSE_FENCE_TAGS:
        return False
    lits = _code_literal_spans(fbody, False)
    if not lits:
        return False
    outside = []
    pos = 0
    for ls, le in lits:
        outside.append(fbody[pos:ls])
        pos = le
    outside.append(fbody[pos:])
    out_letters = re.findall(r"[A-Za-zА-Яа-яЁё]", "".join(outside))
    return bool(out_letters) and sum(1 for x in out_letters if x > "z") < 0.3 * len(out_letters)


def _protected_invisible_spans(norm: str, all_fences: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """String/template/regex literal spans inside code-like fences and inline code."""
    code_fences = []
    for s, e in all_fences:
        block = norm[s:e]
        nl = block.find("\n")
        last_nl = block.rfind("\n")
        head = block[:nl] if nl >= 0 else block
        hm = _FENCE_HEAD_RX.match(head)
        info = head[hm.end():] if hm else ""
        fbody = block[nl + 1:last_nl] if 0 <= nl < last_nl else ""
        if _is_code_fence(info, fbody):
            code_fences.append((s, e))
    code_spans = sorted(code_fences + _inline_code_spans(norm, code_fences))
    out: List[Tuple[int, int]] = []
    for s, e in code_spans:
        chunk = norm[s:e]
        if "\n" in chunk and _FENCE_HEAD_RX.match(chunk):
            nl = chunk.find("\n")
            last_nl = chunk.rfind("\n")
            if 0 <= nl < last_nl:
                b_start, body, allow_bt = s + nl + 1, chunk[nl + 1:last_nl], True
            else:
                continue
        elif chunk and chunk[0] == "`":
            k = 0
            while k < len(chunk) and chunk[k] == "`":
                k += 1
            if len(chunk) >= 2 * k and chunk.endswith("`" * k):
                b_start, body, allow_bt = s + k, chunk[k:-k], k >= 2
            else:
                continue
        else:
            continue
        for ls, le in _code_literal_spans(body, allow_bt):
            out.append((b_start + ls, b_start + le))
    return out


def _blank_fences(text: str, fences: List[Tuple[int, int]] = None) -> str:
    """Code blocks become blank lines, so line numbers and lengths of the rest stay."""
    if fences is None:
        fences = _all_fence_spans(text)
    if not fences:
        return text
    parts = []
    pos = 0
    for s, e in fences:
        parts.append(text[pos:s])
        parts.append(re.sub("[^\\n]", " ", text[s:e]))
        pos = e
    parts.append(text[pos:])
    return "".join(parts)


def _mask_spans(text: str, spans: List[Tuple[int, int]]) -> str:
    if not spans:
        return text
    parts = []
    pos = 0
    for s, e in spans:
        parts.append(text[pos:s])
        parts.append(" " * (e - s))
        pos = e
    parts.append(text[pos:])
    return "".join(parts)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _sentences(text: str) -> list:
    out = []
    for piece in SENT_SPLIT_RX.split(text):
        words = WORD_RX.findall(piece)
        if words:
            out.append(words)
    return out


def _paragraph_lengths(body: str, min_words: int) -> list:
    out = []
    for block in re.split("\n[ \t]*\n", body):
        trimmed = block.strip()
        if not trimmed or HEADING_RX.match(trimmed):
            continue
        b_lines = [ln.strip() for ln in trimmed.split("\n")
                   if ln.strip() and not TABLE_SEP_LINE_RX.match(ln)]
        if not b_lines or all(LIST_LINE_RX.match(ln) for ln in b_lines):
            continue
        w = len(WORD_RX.findall("\n".join(b_lines)))
        if w >= min_words:
            out.append(w)
    return out


def _count_dashes(text: str) -> int:
    total = 0
    for m in DASH_RX.finditer(text):
        ls = text.rfind("\n", 0, m.start()) + 1
        if m.group(0) == "-" and BULLET_PREFIX_RX.match(text[ls:m.start()]):
            continue
        le = text.find("\n", m.end())
        line = text[ls:] if le < 0 else text[ls:le]
        if TABLE_SEP_LINE_RX.match(line):
            continue
        total += 1
    return total


def _cyr_words(text: str) -> list:
    out = []
    for tok in CYR_TOK_RX.findall(text):
        w = tok.lower().translate(PRE1918_TRANS).replace(ACUTE, "")
        if len(w) > 2 and w.endswith("ъ"):
            w = w[:-1]
        if len(w) >= 2:
            out.append(w)
    return out


def _is_nom(w: str) -> bool:
    return bool(NOM_WORD_RX.match(w)) and not NON_NOM_RX.match(w)


def _nominal_cascades(body: str) -> int:
    unquoted = QUOTE_RX.sub(",", body)
    total = 0
    for clause in NOM_SPLIT_RX.split(unquoted):
        cw = _cyr_words(clause)
        i = 0
        while i < len(cw) - 1:
            if _is_nom(cw[i]):
                if NOM_GEN_RX.match(cw[i + 1]) and not NON_NOM_RX.match(cw[i + 1]):
                    total += 1
                    i += 2
                    continue
                if (i + 2 < len(cw) and ADJ_GEN_RX.match(cw[i + 1])
                        and NOM_GEN_RX.match(cw[i + 2]) and not NON_NOM_RX.match(cw[i + 2])):
                    total += 1
                    i += 3
                    continue
            i += 1
    return total


def _nom_to_verb(body: str) -> float:
    unquoted = QUOTE_RX.sub(" ", body)
    cw = _cyr_words(unquoted)
    noms = sum(1 for w in cw if _is_nom(w))
    verbs = sum(1 for w in cw if FINITE_VERB_RX.match(w) and not NON_VERB_RX.match(w))
    return noms / max(1, verbs)


def _mixed_subwords(body_no_code_links: str) -> list:
    return [m for m in SUBWORD_RX.finditer(body_no_code_links)
            if LAT_RX.search(m.group(0)) and CYR_RX.search(m.group(0))]


def _is_emoji_base(cp: int) -> bool:
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF or 0x2190 <= cp <= 0x21FF or 0x25A0 <= cp <= 0x25FF
            or 0x1F3FB <= cp <= 0x1F3FF
            or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299))


def _ignorable_ahead(cp: int, inv_set: set, inv_ranges: list) -> bool:
    return (cp in inv_set or cp in (0x200C, 0x200D) or 0xFE00 <= cp <= 0xFE0F
            or 0xE0000 <= cp <= 0xE007F or 0xE0100 <= cp <= 0xE01EF
            or any(a <= cp <= b for a, b in inv_ranges))


def _count_invisible(cps: list, inv_set: set, inv_ranges: list,
                     protected: List[Tuple[int, int]] = ()) -> int:
    total = 0
    in_flag = False
    last1 = -1
    last2 = -1
    n = len(cps)
    next_kept_pos = -1
    pi = 0
    pn = len(protected)

    def _next_kept(idx: int) -> int:
        nonlocal next_kept_pos
        if next_kept_pos < idx:
            next_kept_pos = idx
            while next_kept_pos < n and _ignorable_ahead(cps[next_kept_pos], inv_set, inv_ranges):
                next_kept_pos += 1
        return cps[next_kept_pos] if next_kept_pos < n else -1

    for i, cp in enumerate(cps):
        while pi < pn and protected[pi][1] <= i:
            pi += 1
        if pi < pn and protected[pi][0] <= i < protected[pi][1]:
            in_flag = False
            last2, last1 = last1, cp
            continue
        if in_flag and 0xE0020 <= cp <= 0xE007F:
            if cp == 0xE007F:
                in_flag = False
            last2, last1 = last1, cp
            continue
        if cp in (0x1F3F4, 0x1F3F3):
            in_flag = True
        elif not (in_flag and cp == 0xFE0F and last1 in (0x1F3F4, 0x1F3F3)):
            in_flag = False
        if cp in inv_set or any(a <= cp <= b for a, b in inv_ranges):
            total += 1
        elif cp == 0xFE0F:
            nxt = _next_kept(i + 1)
            if _is_emoji_base(last1) or ((last1 in (0x23, 0x2A) or 0x30 <= last1 <= 0x39) and nxt == 0x20E3):
                last2, last1 = last1, cp
            else:
                total += 1
        elif cp == 0x200C:
            total += 1
        elif cp == 0x200D:
            prev_ok = _is_emoji_base(last1) or (last1 == 0xFE0F and _is_emoji_base(last2))
            nxt = _next_kept(i + 1)
            if prev_ok and _is_emoji_base(nxt):
                last2, last1 = last1, cp
            else:
                total += 1
        elif 0xE0000 <= cp <= 0xE007F:
            total += 1
        else:
            last2, last1 = last1, cp
    return total


def _in_quotes(q_starts: list, q_ends: list, pos: int) -> bool:
    idx = bisect_right(q_starts, pos - 1) - 1
    return idx >= 0 and pos < q_ends[idx]


# START_CONTRACT: lint
# PURPOSE: All signs in one text.
# INPUTS: text (str), rules from load_rules.
# OUTPUTS: {"chars", "words", "hits": [{id, sign, name, hint, soft, count, examples:[{text, line}]}],
#           "metrics": {id: {sign, name, hint, value, limit, bound, over, scored, examples?}}, "score", "level"}.
# RULES: input is NFC-normalized; fenced blocks are blanked; inline code is masked before phrases,
#        quotes, dashes, bold and mixed_script; URLs/mail are masked before mixed_script and
#        non-paste_garbage phrases; invisible skips string/template/regex literals inside code-like
#        fences and inline code; chars are code points; score = 1000 * weighted hits / max(words,
#        levels.min_words) + scored metrics over the limit (a metric with "score": false is shown,
#        never counted), where a "soft" rule weighs 0.5; level by rules["levels"].
# END_CONTRACT: lint
def lint(text: str, rules: dict) -> dict:
    norm = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    all_fences = _all_fence_spans(norm)
    body = _blank_fences(norm, all_fences)
    body_no_code = _mask_spans(body, _inline_code_spans(body))
    body_no_code_links = LINK_MAIL_RX.sub(lambda m: " " * len(m.group(0)), body_no_code)
    quotes = [(m.start(), m.end()) for m in QUOTE_RX.finditer(body_no_code)]
    q_starts = [a for a, _ in quotes]
    q_ends = [b for _, b in quotes]
    words = len(WORD_RX.findall(body))
    chars = len(body)
    hits, weighted = [], 0.0
    for rule in rules["phrases"]:
        src = body_no_code if rule["id"] == "paste_garbage" else body_no_code_links
        found = [m for m in rule["rx"].finditer(src)
                 if m.group(0).strip() and not _in_quotes(q_starts, q_ends, m.start())]
        if not found:
            continue
        soft = bool(rule.get("soft"))
        weighted += len(found) * (0.5 if soft else 1.0)
        hits.append({"id": rule["id"], "sign": rule["sign"], "name": rule["name"], "hint": rule["hint"],
                     "soft": soft, "count": len(found),
                     "examples": [{"text": m.group(0).strip()[:60], "line": _line_of(body, m.start())} for m in found[:3]]})

    m = rules["metrics"]
    lines = [ln.strip() for ln in body.split("\n") if ln.strip() and not TABLE_SEP_LINE_RX.match(ln)]
    sents = _sentences(body)
    lens = [len(s) for s in sents]
    para_lens = _paragraph_lengths(body, m["paragraph_cv"]["min_words"])
    openers = Counter(s[0].lower().replace("ё", "е").replace(ACUTE, "") for s in sents)
    mixed_found = _mixed_subwords(body_no_code_links)
    inv_cfg = m["invisible"]
    inv_set = inv_cfg.get("_set") or set(inv_cfg["codepoints"])
    inv_ranges = inv_cfg.get("_big") if "_set" in inv_cfg else inv_cfg.get("ranges", [])
    inv_rx = inv_cfg.get("_rx")
    emoji_rx = m["emoji_per_1000"].get("_rx")
    if inv_rx is not None and not inv_rx.search(norm):
        inv_count = 0
    else:
        protected = _protected_invisible_spans(norm, all_fences)
        inv_count = _count_invisible([ord(ch) for ch in norm], inv_set, inv_ranges, protected)
    emoji_count = (
        len(emoji_rx.findall(body)) if emoji_rx is not None
        else sum(1 for ch in body if any(a <= ord(ch) <= b for a, b in m["emoji_per_1000"]["ranges"]))
    )
    vals = {
        "dash_per_1000": (1000.0 * _count_dashes(body_no_code) / chars) if chars else 0.0,
        "sentence_cv": (statistics.pstdev(lens) / statistics.mean(lens))
        if len(lens) >= m["sentence_cv"]["min_sentences"] else None,
        "paragraph_cv": (statistics.pstdev(para_lens) / statistics.mean(para_lens))
        if len(para_lens) >= m["paragraph_cv"]["min_paragraphs"] else None,
        "same_opener_share": (max(openers.values()) / len(sents))
        if len(sents) >= m["same_opener_share"]["min_sentences"] else None,
        "nominal_chain": (1000.0 * _nominal_cascades(body_no_code_links) / words)
        if words >= m["nominal_chain"]["min_words"] else None,
        "nom_to_verb": _nom_to_verb(body_no_code_links)
        if words >= m["nom_to_verb"]["min_words"] else None,
        "bold_per_line": (len(BOLD_RX.findall(body_no_code)) / len(lines))
        if len(lines) >= m["bold_per_line"]["min_lines"] else None,
        "heading_share": (sum(1 for ln in lines if HEADING_RX.match(ln)) / len(lines))
        if len(lines) >= m["heading_share"]["min_lines"] else None,
        "emoji_per_1000": (1000.0 * emoji_count / chars)
        if chars else 0.0,
        "mixed_script": float(len(mixed_found)),
        "invisible": float(inv_count),
    }
    metrics, over_count = {}, 0
    for key, value in vals.items():
        cfg = m[key]
        is_min = "min" in cfg
        limit = cfg["min"] if is_min else cfg["max"]
        over = value is not None and (value < cfg["min"] if is_min else value > cfg["max"])
        scored = cfg.get("score", True)
        over_count += over and scored
        entry = {"sign": cfg["sign"], "name": cfg["name"], "hint": cfg["hint"],
                 "value": None if value is None else round(value, 3), "limit": limit,
                 "bound": "min" if is_min else "max", "over": over, "scored": scored}
        if key == "mixed_script" and mixed_found:
            entry["examples"] = [{"text": mm.group(0)[:60], "line": _line_of(body, mm.start())} for mm in mixed_found[:3]]
        metrics[key] = entry
    lv = rules["levels"]
    score = round(1000.0 * weighted / max(words, lv["min_words"]) + over_count, 2)
    # Info-only metrics (score: false) never raise the level, even from "нет".
    level = ("нет" if not hits and not over_count else
             "много" if score >= lv["many"] else "есть" if score >= lv["some"] else "мало")
    return {"chars": chars, "words": words, "hits": hits, "metrics": metrics, "score": score, "level": level}
# END_BLOCK_ENGINE


LEVEL_TEXT = {"нет": "признаков не найдено", "мало": "мало признаков", "есть": "есть признаки",
              "много": "много признаков"}


def _fmt_num(val: float):
    r = round(val, 2)
    return int(r) if r == int(r) else r


def render(rep: dict) -> str:
    out = ["Машинный стиль: %s (балл %.1f; слов %d). Это оценка стиля, а не авторства: "
           "найденное может быть к месту." % (LEVEL_TEXT[rep["level"]], rep["score"], rep["words"])]
    for h in sorted(rep["hits"], key=lambda h: (h["sign"], h["id"])):
        ex = "; ".join("«%s» (стр. %d)" % (e["text"], e["line"]) for e in h["examples"])
        out.append("#%d %s — %d: %s. %s" % (h["sign"], h["name"], h["count"], ex, h["hint"]))
    for key, mt in rep["metrics"].items():
        if mt["over"]:
            ex = (": " + "; ".join("«%s» (стр. %d)" % (e["text"], e["line"]) for e in mt["examples"])
                  if mt.get("examples") else "")
            note = "" if mt["scored"] else " Для сведения: в балл не входит."
            bound_label = "минимум" if mt.get("bound") == "min" else "максимум"
            out.append("#%d %s: %s (%s %s)%s. %s%s" % (
                mt["sign"], mt["name"], _fmt_num(mt["value"]), bound_label, _fmt_num(mt["limit"]), ex, mt["hint"], note))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Поиск признаков машинного стиля и технических следов в русском тексте.",
        epilog="Код выхода: 0 — отчёт готов; 1 — балл выше --max-score; 2 — ошибка ввода или правил.",
    )
    ap.add_argument("file", help="файл с текстом или - для чтения из stdin")
    ap.add_argument("--json", action="store_true", help="вывести отчёт в JSON")
    ap.add_argument("--rules", default=str(RULES_PATH), help="путь к rules.json")
    ap.add_argument("--max-score", type=float, default=None, help="код выхода 1, если балл выше порога")
    ap.add_argument("--encoding", default="utf-8", help="кодировка входного файла (по умолчанию utf-8)")
    args = ap.parse_args(argv)
    try:
        codecs.lookup(args.encoding)
        # stdin as bytes: on Windows sys.stdin decodes with the console code page (cp1251), and
        # UTF-8 text piped in turned into mojibake with no signs found.
        if args.file == "-":
            buf = getattr(sys.stdin, "buffer", None)
            text = buf.read().decode(args.encoding) if buf is not None else sys.stdin.read()
        else:
            text = Path(args.file).read_text(encoding=args.encoding)
        rules = load_rules(args.rules)
    except UnicodeDecodeError as exc:
        print("Не могу прочитать файл (%s; ожидается UTF-8, укажите --encoding для другой кодировки)." % exc,
              file=sys.stderr)
        return 2
    except (OSError, ValueError, LookupError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print("Не могу прочитать входные данные или правила: %s" % exc, file=sys.stderr)
        return 2
    rep = lint(text, rules)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render(rep))
    return 1 if args.max_score is not None and rep["score"] > args.max_score else 0


if __name__ == "__main__":
    raise SystemExit(main())
