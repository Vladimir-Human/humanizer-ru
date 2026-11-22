#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Remove chat-interface leftovers and mixed-script homoglyph spoofing from pasted text:
#          citation tokens (contentReference, 【N†source】, [cite: N], bare citeturn leaks, Claude
#          <antml:cite>/<cite index="..."> XML tags keeping inner prose), the utm_source tail a chat
#          assistant adds to links (chatgpt.com, openai, perplexity.ai, claude.ai, deepseek,
#          gemini.google.com, grok.com, copilot.com; also behind &amp;, **, ~~ or an invisible
#          character), invisible/watermark characters (incl. Variation Selectors outside emoji,
#          Unicode Tags outside subdivision flags, deprecated format U+206A..U+206F, U+FFFC), and
#          Latin/Greek lookalikes mixed into Cyrillic words (incl. NFC accented á/é/ó/ý/ë and NFD
#          й/ё). Text, links, e-mails, the author's own utm tags, emoji, inline code spans,
#          code-like fenced blocks (```/~~~), hyphenated compounds (IT-отдел) and line endings
#          (CRLF) stay intact.
# SCOPE: deterministic, stdlib only; style and wording are not touched.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CLEAN-PASTE; R-PASTE; R-DETECTOR-RISK; DF-SKILL; V-M-CLEAN-PASTE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# clean: text -> (cleaned text, counts by kind).
# main: CLI `clean_paste.py file|- [--in-place] [--no-backup] [--check] [--json] [--exit-zero]
#       [--encoding ENC]`; prints cleaned text or rewrites the file atomically (keeps file.bak
#       unless --no-backup); report goes to stderr (or JSON to stdout); exit 0 nothing found (or
#       --exit-zero), 1 cleaned/found, 2 bad input/write error.
# END_MODULE_MAP
"""Очистка мусора вставки из чата.

    python clean_paste.py текст.txt              # очищенный текст в stdout
    python clean_paste.py текст.txt --in-place   # атомарная правка файла, копия в текст.txt.bak
    python clean_paste.py текст.txt --check      # только проверить без вывода текста
    python clean_paste.py -                      # чтение из stdin (UTF-8)

Код выхода: 0 — мусора нет (или задан --exit-zero), 1 — мусор найден/снят, 2 — ошибка ввода/записи.
"""
from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# START_BLOCK_PATTERNS
_CITETURN_STEP = (
    r"turn\d+(?:search|fetch|file|image|news|video|ref|view|"
    r"product|finance|map|sports|weather|local|code|calc|browser)\d+"
)
CITATIONS = [
    ("contentReference", re.compile(r"[ \t]?:{0,2}contentReference\[oaicite:\d+\](?:\{index=\d+\})?")),
    ("oaicite", re.compile(
        r"(?i)[ \t]?(?:\[oaicite:\d+\](?:\{index=\d+\})?|\ue200[^\ue201\n]{0,400}\ue201|\uea01[^\uea02\n]{0,40}\uea02"
        r"|(?<![A-Za-z0-9/_.\-=?:&#@])cite" + _CITETURN_STEP + r"(?:" + _CITETURN_STEP + r")*)"
    )),
    ("source-token", re.compile(r"[ \t]?【\d+(?:[:\-–,][ \t]*\d+)*(?:†[^】\n]{0,80})?】")),
    # Gemini opens a cited span with [cite_start] glued to its first word: the space before stays.
    ("cite", re.compile(r"(?i)\[cite_start\]")),
    ("cite", re.compile(
        r"(?i)[ \t]?(?:\[cite(?:_end)?(?::[ \t]*[0-9]+(?:[ \t]*[\-–,][ \t]*[0-9]+)*[ \t]*)?\]|"
        r"\[(?:citation|attached_file|web):[ \t]*[0-9]+(?:[ \t]*[\-–,][ \t]*[0-9]+)*[ \t]*\]|"
        r"\[span_[0-9]+\][\[(](?:start_span|end_span)[\])]|"
        r"\[\^[0-9]+\^\])"
    )),
    ("cite", re.compile(r"(?i)</?antml:cite(?:[ \t]+[^>\n]{0,200})?>")),
]
CITE_XML_PAIR_RX = re.compile(
    r"""(?i)<cite[ \t]+index=(?:"[^"\n]{0,120}"|'[^'\n]{0,120}')[ \t]*>((?:(?!</?cite[ \t\r\n>/])[\s\S]){0,4000})</cite>"""
)
CITE_XML_OPEN_RX = re.compile(r"""(?i)<cite[ \t]+index=(?:"[^"\n]{0,120}"|'[^'\n]{0,120}')[ \t]*>""")

# Invisible characters that never carry meaning in Russian prose (U+202F and U+2009 stay intact).
INVISIBLE = {
    0x200B: "zero-width space", 0x2060: "word joiner", 0xFEFF: "BOM / zero-width no-break",
    0x00AD: "soft hyphen", 0x200E: "LTR mark", 0x200F: "RTL mark", 0x202A: "bidi", 0x202B: "bidi",
    0x202C: "bidi", 0x202D: "bidi", 0x202E: "bidi", 0x2066: "bidi", 0x2067: "bidi",
    0x2068: "bidi", 0x2069: "bidi", 0x180E: "mongolian vowel separator",
    0x034F: "combining grapheme joiner", 0x061C: "arabic letter mark",
    0x2061: "invisible math", 0x2062: "invisible math", 0x2063: "invisible math", 0x2064: "invisible math",
    0x206A: "deprecated format", 0x206B: "deprecated format", 0x206C: "deprecated format",
    0x206D: "deprecated format", 0x206E: "deprecated format", 0x206F: "deprecated format",
    0xFFF9: "interlinear annotation", 0xFFFA: "interlinear annotation", 0xFFFB: "interlinear annotation",
    0xFFFC: "object replacement",
    0xE200: "pua cite", 0xE201: "pua cite", 0xE202: "pua cite", 0xE203: "pua cite", 0xE204: "pua cite",
    0xEA01: "pua cite", 0xEA02: "pua cite",
}
SPACE_SPOOFERS = frozenset({0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160})
_WS = frozenset(
    " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)
ZWJ = 0x200D
ZWNJ = 0x200C
# A closing parenthesis ends a link unless it closes one opened inside it, so the utm tail of
# https://ru.wikipedia.org/wiki/Колос_(значения)?utm_source=chatgpt.com is seen.
_ZW = ("".join(map(chr, (*INVISIBLE, *SPACE_SPOOFERS, ZWJ, ZWNJ)))
       + "\ufe00-\ufe0f\U000e0000-\U000e007f\U000e0100-\U000e01ef")
URL_RX = (r"(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\.)"
          r"(?:\([^\s<>«»\"'()\]`%s]*\)|[^\s<>«»\"')\]`%s])+" % (_ZW, _ZW))
EMAIL_RX = (r"(?<![A-Za-zА-Яа-яЁё0-9._%+-])"
            r"[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\.[A-Za-zА-Яа-яЁё]{2,}")
LAT_EXT = "\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff\ua7dc"
HOMOGLYPHS = {
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "á": "а\u0301", "é": "е\u0301", "ó": "о\u0301", "ý": "у\u0301",
    "Á": "А\u0301", "É": "Е\u0301", "Ó": "О\u0301", "Ý": "У\u0301",
    "ë": "ё", "Ë": "Ё",
    "α": "а", "ε": "е", "ο": "о", "ρ": "р", "χ": "х", "κ": "к",
    "Α": "А", "Β": "В", "Γ": "Г", "Ε": "Е", "Η": "Н", "Κ": "К", "Μ": "М",
    "Ο": "О", "Π": "П", "Ρ": "Р", "Τ": "Т", "Υ": "У", "Φ": "Ф", "Χ": "Х",
}
HOMOGLYPH_TRANS = str.maketrans(HOMOGLYPHS)
_HOMO_LOOK = "".join(HOMOGLYPHS)
_HOMO_ALL = "А-Яа-яЁё\u0301\u0306\u0308" + _HOMO_LOOK
_WORD_CHARS = "A-Za-z" + LAT_EXT + r"\u0370-\u03ffА-Яа-яЁё\u0301\u0306\u0308"
HOMO_WORD_RX = (r"(?<![%s])(?=[%s]*[А-Яа-яЁё])(?=[%s]*[%s])[%s]+(?![%s])"
                % (_WORD_CHARS, _HOMO_ALL, _HOMO_ALL, _HOMO_LOOK, _HOMO_ALL, _WORD_CHARS))
MD_TARGET_RX = r"(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)"
PROSE_HOMO_RX = re.compile(URL_RX + "|" + EMAIL_RX + "|" + MD_TARGET_RX + "|(" + HOMO_WORD_RX + ")")
_FENCE_HEAD_RX = re.compile(r"^[ ]{0,3}(?:`{3,}|~{3,})")
_PROSE_FENCE_TAGS = frozenset({"", "markdown", "md", "text", "txt", "plain", "plaintext"})
_REGEX_PREV = frozenset("=(,:;!&|?+-~*{[\n\r")
_REGEX_KW = frozenset(("return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"))
_REGEX_FLAGS = frozenset("dgimsuvy")
# END_BLOCK_PATTERNS


# utm_source values chat assistants add to the links they cite (ru.wikipedia,
# «Признаки сгенерированности текста», UTM-метки, revision of 2026-10-08, plus verified domain
# tags of 2025-2026 chat assistants). Any other utm tag is the author's own (newsletter, campaign)
# and belongs to the link.
ASSISTANT_UTM_SOURCES = frozenset({
    "chatgpt.com", "openai", "copilot.com", "perplexity.ai",
    "claude.ai", "gemini.google.com", "grok.com",
    "chat.deepseek.com", "deepseek.com",
})


def _is_assistant_utm(param: str) -> bool:
    key, _, value = param.partition("=")
    return key.lower() == "utm_source" and unquote(value).strip().lower() in ASSISTANT_UTM_SOURCES


def strip_utm(url: str) -> Tuple[str, int]:
    """Drop the assistant's utm_source tail, keep the author's utm tags, other parameters,
    the '?' (when something is left) and the fragment."""
    try:
        parts = urlsplit(url)
    except ValueError:  # a bracketed IPv6 host the link pattern cut short: leave it as is
        return url, 0
    if not parts.query:
        return url, 0
    # A link copied from HTML keeps "&amp;" between its parameters.
    sep = "&amp;" if "&amp;" in parts.query else "&"
    params = re.split(r"&(?:amp;)?", parts.query)
    kept = [x for x in params if not _is_assistant_utm(x)]
    if len(kept) == len(params):
        return url, 0
    return urlunsplit(parts._replace(query=sep.join(kept))), len(params) - len(kept)


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF or 0x2190 <= cp <= 0x21FF or 0x25A0 <= cp <= 0x25FF
            or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139,
                      0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299)
            or 0x1F3FB <= cp <= 0x1F3FF)


def _ignorable_ahead(cp: int) -> bool:
    return (cp in INVISIBLE or cp in SPACE_SPOOFERS or cp in (ZWJ, ZWNJ)
            or 0xFE00 <= cp <= 0xFE0F or 0xE0000 <= cp <= 0xE007F or 0xE0100 <= cp <= 0xE01EF)


def _strip_invisibles_chunk(chunk: str, prev_ch: str, next_ch: str) -> Tuple[str, int]:
    next_kept_pos = -1

    def _next_kept(idx: int) -> str:
        nonlocal next_kept_pos
        if next_kept_pos < idx:
            next_kept_pos = idx
            while next_kept_pos < len(chunk) and _ignorable_ahead(ord(chunk[next_kept_pos])):
                next_kept_pos += 1
        return chunk[next_kept_pos] if next_kept_pos < len(chunk) else next_ch

    out: List[str] = []
    removed = 0
    in_flag = False
    for i, ch in enumerate(chunk):
        cp = ord(ch)
        if in_flag and 0xE0020 <= cp <= 0xE007F:
            out.append(ch)
            if cp == 0xE007F:
                in_flag = False
            continue
        left_c = out[-1] if out else prev_ch
        if cp in (0x1F3F4, 0x1F3F3):
            in_flag = True
        elif not (in_flag and cp == 0xFE0F and left_c and ord(left_c) in (0x1F3F4, 0x1F3F3)):
            in_flag = False
        if cp in SPACE_SPOOFERS:
            removed += 1
            if left_c and left_c not in _WS:
                right_c = _next_kept(i + 1)
                if right_c and right_c not in _WS:
                    out.append(" ")
            continue
        if (cp in INVISIBLE or 0xFE00 <= cp <= 0xFE0E
                or 0xE0000 <= cp <= 0xE007F or 0xE0100 <= cp <= 0xE01EF):
            removed += 1
            continue
        if cp == 0xFE0F:
            right_c = _next_kept(i + 1)
            if ((left_c and _is_emoji(left_c))
                    or (bool(left_c) and left_c in "0123456789#*" and right_c == "\u20e3")):
                out.append(ch)
                continue
            removed += 1
            continue
        if cp in (ZWJ, ZWNJ):
            if cp == ZWJ:
                if out:
                    prev_ok = _is_emoji(out[-1]) or (out[-1] == "\ufe0f" and (
                        (len(out) >= 2 and _is_emoji(out[-2]))
                        or (len(out) == 1 and bool(prev_ch) and _is_emoji(prev_ch))
                    ))
                else:
                    prev_ok = bool(prev_ch) and _is_emoji(prev_ch)
                right_c = _next_kept(i + 1)
                if prev_ok and right_c and _is_emoji(right_c):
                    out.append(ch)
                    continue
            removed += 1
            continue
        out.append(ch)
    return "".join(out), removed


def _is_code_fence(info: str, fbody: str) -> bool:
    """True when fence body is <30% Cyrillic (info string never inflates Latin count);
    explicit code language tags also protect short snippets whose Cyrillic sits inside literals."""
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


def _code_fence_spans(text: str) -> List[Tuple[int, int]]:
    """Linear O(N) fenced code scanner (0-3 spaces, >=3 ` or ~, matching closer, body-only <30% Cyrillic)."""
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
                    cand.append((pos, line_end, ch, flen, is_closer, rest))
        if nl < 0:
            break
        pos = nl + 1
    if len(cand) < 2:
        return []
    m = len(cand)
    max_bt = [0] * (m + 1)
    max_ti = [0] * (m + 1)
    for idx in range(m - 1, -1, -1):
        _, _, ch, flen, is_closer, _ = cand[idx]
        max_bt[idx] = max(max_bt[idx + 1], flen if (is_closer and ch == "`") else 0)
        max_ti[idx] = max(max_ti[idx + 1], flen if (is_closer and ch == "~") else 0)
    spans: List[Tuple[int, int]] = []
    idx = 0
    while idx < m:
        open_start, _, ch, flen, _, open_info = cand[idx]
        mc = max_bt if ch == "`" else max_ti
        if mc[idx + 1] < flen:
            idx += 1
            continue
        j = idx + 1
        while j < m:
            _, close_end, c2, flen2, is_closer2, _ = cand[j]
            if is_closer2 and c2 == ch and flen2 >= flen:
                block = text[open_start:close_end]
                nl_b = block.find("\n")
                last_nl_b = block.rfind("\n")
                fbody = block[nl_b + 1:last_nl_b] if 0 <= nl_b < last_nl_b else ""
                if _is_code_fence(open_info, fbody):
                    spans.append((open_start, close_end))
                idx = j + 1
                break
            j += 1
        else:
            idx += 1
    return spans


def _inline_code_spans(text: str, excluded: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Linear O(N) single-line multi-backtick inline code matcher outside excluded fence spans."""
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


def _strip_code_invisibles(code: str) -> Tuple[str, int]:
    """Strip paste invisibles outside string, template and regex literals inside code."""
    if "\n" in code and _FENCE_HEAD_RX.match(code):
        nl = code.find("\n")
        last_nl = code.rfind("\n")
        if 0 <= nl < last_nl:
            head, body, tail, allow_bt = code[:nl + 1], code[nl + 1:last_nl], code[last_nl:], True
        else:
            head, body, tail, allow_bt = "", code, "", False
    elif code and code[0] == "`":
        k = 0
        while k < len(code) and code[k] == "`":
            k += 1
        if len(code) >= 2 * k and code.endswith("`" * k):
            head, body, tail, allow_bt = code[:k], code[k:-k], code[-k:], k >= 2
        else:
            head, body, tail, allow_bt = "", code, "", False
    else:
        head, body, tail, allow_bt = "", code, "", False
    sub_parts: List[str] = []
    pos = 0
    for s, e in _code_literal_spans(body, allow_bt):
        sub_parts += [body[pos:s], body[s:e]]
        pos = e
    sub_parts.append(body[pos:])
    sub_parts[0] = head + sub_parts[0]
    sub_parts[-1] = sub_parts[-1] + tail
    removed = 0
    for j in range(0, len(sub_parts), 2):
        seg = sub_parts[j]
        if not seg:
            continue
        prev_c = sub_parts[j - 1][-1] if j > 0 and sub_parts[j - 1] else ""
        next_c = sub_parts[j + 1][0] if j + 1 < len(sub_parts) and sub_parts[j + 1] else ""
        seg, n = _strip_invisibles_chunk(seg, prev_c, next_c)
        sub_parts[j] = seg
        removed += n
    return "".join(sub_parts), removed


# START_CONTRACT: clean
# PURPOSE: Strip paste artifacts from text.
# INPUTS: text (str).
# OUTPUTS: (cleaned text, {kind: count}).
# SIDE_EFFECTS: none.
# END_CONTRACT: clean
def clean(text: str) -> Tuple[str, Dict[str, int]]:
    counts: Dict[str, int] = {}

    def _clean_once(cur: str) -> Tuple[str, Dict[str, int]]:
        step_counts: Dict[str, int] = {}

        def bump(kind: str, n: int = 1) -> None:
            if n:
                step_counts[kind] = step_counts.get(kind, 0) + n

        def fix_url(m: re.Match) -> str:
            url = m.group(0)
            # Sentence punctuation and Markdown emphasis/strikethrough after the link: **https://a.ru**, ~~https://a.ru~~
            tail = url[len(url.rstrip(".,;:!?…*_~")):]
            new, n = strip_utm(url[:len(url) - len(tail)])
            bump("utm", n)
            return new + tail

        def fix_homo(m: re.Match) -> str:
            word = m.group(1)
            if word is None:
                return m.group(0)
            bump("homoglyph")
            return unicodedata.normalize("NFC", word.translate(HOMOGLYPH_TRANS))

        # Code is copied as is: citations, links, homoglyphs and quoted string literals inside
        # inline code spans and code-like (<30% Cyrillic) fenced blocks stay untouched, while paste
        # invisibles in unquoted code tokens are stripped. A fenced block of Russian prose is cleaned.
        fences = _code_fence_spans(cur)
        spans = sorted(fences + _inline_code_spans(cur, fences))
        parts: List[str] = []
        pos = 0
        for s, e in spans:
            parts += [cur[pos:s], cur[s:e]]
            pos = e
        parts.append(cur[pos:])
        for i in range(1, len(parts), 2):
            parts[i], inv_c = _strip_code_invisibles(parts[i])
            bump("invisible", inv_c)
        for i in range(0, len(parts), 2):
            chunk = parts[i]
            if not chunk:
                continue
            prev_ch = parts[i - 1][-1] if i > 0 and parts[i - 1] else ""
            next_ch = parts[i + 1][0] if i + 1 < len(parts) and parts[i + 1] else ""
            for _ in range(4):
                step = 0
                for _ in range(4):
                    c_step = 0
                    for kind, rx in CITATIONS:
                        chunk, n = rx.subn("", chunk)
                        bump(kind, n)
                        c_step += n
                    chunk, n_xml = CITE_XML_PAIR_RX.subn(r"\1", chunk)
                    bump("cite", n_xml)
                    c_step += n_xml
                    step += c_step
                    if not c_step:
                        break
                chunk, n_open = CITE_XML_OPEN_RX.subn("", chunk)
                bump("cite", n_open)
                step += n_open
                # A zero-width character glued after a link ends it, so the utm tail before it is seen
                # on the first pass; if invisibles split a citation or utm_source, the next pass catches it.
                before_url = chunk
                chunk = re.sub(URL_RX, fix_url, chunk)
                if chunk != before_url:
                    step += 1
                chunk, inv_n = _strip_invisibles_chunk(chunk, prev_ch, next_ch)
                bump("invisible", inv_n)
                if not step and not inv_n:
                    break
            # Fold mixed-script Latin/Greek homoglyphs inside Russian words after invisible characters are
            # gone, so "c\u200bиcт\u00adeмa", NFC "бéлый" and NFD "cиcтeмoи\u0306" repair in one pass.
            parts[i] = PROSE_HOMO_RX.sub(fix_homo, chunk)
        return "".join(parts), step_counts

    for _ in range(3):
        text, step_counts = _clean_once(text)
        if not step_counts:
            break
        for k, v in step_counts.items():
            counts[k] = counts.get(k, 0) + v
        if "`" not in text and "~" not in text:
            break
    return text, counts


def _atomic_write_text(target: Path, content: str, encoding: str) -> None:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, newline="", dir=str(target.parent),
            prefix="." + target.name + ".", suffix=".tmp", delete=False,
        ) as fh:
            tmp_path = Path(fh.name)
            fh.write(content)
        shutil.copymode(str(target), str(tmp_path))
        os.replace(str(tmp_path), str(target))
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Очистка мусора вставки из чата и букв-двойников (омоглифов).",
        epilog="Код выхода: 0 — мусора нет (или --exit-zero); 1 — мусор найден/снят; 2 — ошибка.",
    )
    ap.add_argument("file", help="файл с текстом или - для чтения из stdin")
    ap.add_argument("--in-place", action="store_true", help="атомарно перезаписать файл (резервная копия .bak)")
    ap.add_argument("--no-backup", action="store_true", help="при --in-place не создавать файл .bak")
    ap.add_argument("--check", action="store_true", help="только проверить, ничего не менять и не выводить текст")
    ap.add_argument("--json", action="store_true", help="вывести сводку в JSON в stdout")
    ap.add_argument("--exit-zero", action="store_true", help="возвращать код 0 даже если мусор найден/снят")
    ap.add_argument("--encoding", default="utf-8", help="кодировка ввода/вывода файла (по умолчанию utf-8)")
    args = ap.parse_args(argv)
    if args.file == "-" and args.in_place:
        print("Нельзя использовать --in-place со stdin (-).", file=sys.stderr)
        return 2
    if args.in_place and args.check:
        print("Нельзя сочетать --in-place и --check.", file=sys.stderr)
        return 2
    try:
        codecs.lookup(args.encoding)
    except LookupError as exc:
        print("Неизвестная кодировка: %s" % exc, file=sys.stderr)
        return 2
    try:
        if args.file == "-":
            buf = getattr(sys.stdin, "buffer", None)
            src = buf.read().decode(args.encoding) if buf is not None else sys.stdin.read()
        else:
            target = Path(args.file)
            if args.in_place and target.is_symlink():
                print("Отказ: --in-place не перезаписывает символические ссылки: %s" % args.file, file=sys.stderr)
                return 2
            with open(target, encoding=args.encoding, newline="") as fh:
                src = fh.read()
    except UnicodeDecodeError as exc:
        print("Не могу прочитать файл (%s; ожидается UTF-8, укажите --encoding для другой кодировки)." % exc,
              file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("Не могу прочитать файл: %s" % exc, file=sys.stderr)
        return 2
    cleaned, counts = clean(src)
    if args.in_place:
        if counts:
            target = Path(args.file)
            try:
                if target.is_symlink():
                    print("Отказ: --in-place не перезаписывает символические ссылки: %s" % args.file, file=sys.stderr)
                    return 2
                if not args.no_backup:
                    bak = Path(args.file + ".bak")
                    if bak.is_symlink():
                        print("Отказ: резервная копия .bak — символическая ссылка: %s" % bak, file=sys.stderr)
                        return 2
                    shutil.copyfile(str(target), str(bak))
                _atomic_write_text(target, cleaned, args.encoding)
            except (OSError, ValueError) as exc:
                print("Не могу записать файл: %s" % exc, file=sys.stderr)
                return 2
    elif not args.check and not args.json:
        # Line endings are kept as they are: removing one invisible character must not turn a
        # Windows file (CRLF) into LF or write CR CR LF to the console.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="")
        sys.stdout.write(cleaned)
    if args.json:
        payload = {"file": args.file, "changed": bool(counts), "counts": counts}
        if not args.in_place and not args.check:
            payload["text"] = cleaned
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        report = ", ".join("%s: %d" % kv for kv in sorted(counts.items())) or "мусора вставки нет"
        print("Очистка вставки: " + report, file=sys.stderr)
    return 0 if (args.exit_zero or not counts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
