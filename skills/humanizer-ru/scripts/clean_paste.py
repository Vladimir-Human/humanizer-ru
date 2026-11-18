#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Remove chat-interface leftovers and mixed-script homoglyph spoofing from pasted text:
#          citation tokens (contentReference, 【N†source】, [cite: N], bare citeturn leaks), the
#          utm_source tail a chat assistant adds to links (chatgpt.com, openai, perplexity.ai,
#          claude.ai, deepseek, gemini.google.com, grok.com, copilot.com; also behind &amp;, **
#          or an invisible character), invisible/watermark characters (incl. Variation Selectors
#          outside emoji and Unicode Tags outside subdivision flags), and Latin/Greek lookalikes
#          mixed into Cyrillic words (incl. NFD й/ё). Text, links, e-mails, the author's own utm
#          tags, emoji, `inline code`, code-like ``` blocks, hyphenated compounds (IT-отдел) and
#          line endings (CRLF) stay intact.
# SCOPE: deterministic, stdlib only; style and wording are not touched.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CLEAN-PASTE; R-PASTE; R-DETECTOR-RISK; DF-SKILL; V-M-CLEAN-PASTE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# clean: text -> (cleaned text, counts by kind).
# main: CLI `clean_paste.py file [--in-place]`; prints cleaned text or rewrites the file
#       (keeps file.bak); report goes to stderr; exit 0 nothing found, 1 cleaned, 2 bad input.
# END_MODULE_MAP
"""Очистка мусора вставки из чата.

    python clean_paste.py текст.txt              # очищенный текст в stdout
    python clean_paste.py текст.txt --in-place   # правка файла, копия в текст.txt.bak
    python clean_paste.py -                      # чтение из stdin

Код выхода: 0 — мусора нет, 1 — мусор снят, 2 — файл не читается.
"""
from __future__ import annotations

import bisect
import re
import shutil
import sys
import unicodedata
from typing import Dict, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# START_BLOCK_PATTERNS
_CITETURN_STEP = r"turn\d+(?:search|fetch|file|image|news|video|ref|view)\d+"
CITATIONS = [
    ("contentReference", re.compile(r"[ \t]?:?contentReference\[oaicite:\d+\]\{index=\d+\}")),
    ("oaicite", re.compile(
        r"(?i)[ \t]?(?:\[oaicite:\d+\]|\ue200[^\ue201\n]{0,120}\ue201|\uea01[^\uea02\n]{0,40}\uea02"
        r"|(?<![A-Za-z0-9/_.\-=?:&#@])cite" + _CITETURN_STEP + r"(?:" + _CITETURN_STEP + r")*)"
    )),
    ("source-token", re.compile(r"[ \t]?【\d+(?::\d+)?(?:†[^】\n]{0,80})?】")),
    # Gemini opens a cited span with [cite_start] glued to its first word: the space before stays.
    ("cite", re.compile(r"(?i)\[cite_start\]")),
    ("cite", re.compile(r"(?i)[ \t]?(?:\[cite(?:_end)?(?::\s*[\d,\s]+)?\]|"
                        r"\[(?:citation|attached_file|web):\d+\]|"
                        r"\[span_\d+\][\[(](?:start_span|end_span)[\])]|"
                        r"\[\^\d+\^\])")),
]

# Invisible characters that never carry meaning in Russian prose (U+202F and U+2009 stay intact).
INVISIBLE = {
    0x200B: "zero-width space", 0x2060: "word joiner", 0xFEFF: "BOM / zero-width no-break",
    0x00AD: "soft hyphen", 0x200E: "LTR mark", 0x200F: "RTL mark", 0x202A: "bidi", 0x202B: "bidi",
    0x202C: "bidi", 0x202D: "bidi", 0x202E: "bidi", 0x2066: "bidi", 0x2067: "bidi",
    0x2068: "bidi", 0x2069: "bidi", 0x180E: "mongolian vowel separator",
    0x034F: "combining grapheme joiner", 0x061C: "arabic letter mark",
    0x2061: "invisible math", 0x2062: "invisible math", 0x2063: "invisible math", 0x2064: "invisible math",
    0xFFF9: "interlinear annotation", 0xFFFA: "interlinear annotation", 0xFFFB: "interlinear annotation",
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
HOMOGLYPHS = {
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "α": "а", "ε": "е", "ο": "о", "ρ": "р", "χ": "х", "κ": "к",
    "Α": "А", "Β": "В", "Γ": "Г", "Ε": "Е", "Η": "Н", "Κ": "К", "Μ": "М",
    "Ο": "О", "Π": "П", "Ρ": "Р", "Τ": "Т", "Υ": "У", "Φ": "Ф", "Χ": "Х",
}
HOMOGLYPH_TRANS = str.maketrans(HOMOGLYPHS)
_HOMO_LOOK = "".join(HOMOGLYPHS)
_HOMO_ALL = "А-Яа-яЁё\u0301\u0306\u0308" + _HOMO_LOOK
_WORD_CHARS = r"A-Za-z\u0370-\u03ffА-Яа-яЁё\u0301\u0306\u0308"
HOMO_WORD_RX = (r"(?<![%s])(?=[%s]*[А-Яа-яЁё])(?=[%s]*[%s])[%s]+(?![%s])"
                % (_WORD_CHARS, _HOMO_ALL, _HOMO_ALL, _HOMO_LOOK, _HOMO_ALL, _WORD_CHARS))
MD_TARGET_RX = r"(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)"
PROSE_HOMO_RX = re.compile(r"`[^`\n]+`|" + URL_RX + "|" + EMAIL_RX + "|" + MD_TARGET_RX + "|(" + HOMO_WORD_RX + ")")
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

    out = []
    removed = 0
    in_flag = False
    for i, ch in enumerate(chunk):
        cp = ord(ch)
        if in_flag and 0xE0020 <= cp <= 0xE007F:
            out.append(ch)
            if cp == 0xE007F:
                in_flag = False
            continue
        in_flag = cp in (0x1F3F4, 0x1F3F3)
        if cp in SPACE_SPOOFERS:
            removed += 1
            left_c = out[-1] if out else prev_ch
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
            left_c = out[-1] if out else prev_ch
            right_c = _next_kept(i + 1)
            if ((left_c and _is_emoji(left_c))
                    or (left_c in "0123456789#*" and right_c == "\u20e3")):
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
    if code.startswith("```"):
        nl = code.find("\n")
        last_nl = code.rfind("\n")
        if 0 <= nl < last_nl:
            head, body, tail, allow_bt = code[:nl + 1], code[nl + 1:last_nl], code[last_nl:], True
        else:
            head, body, tail, allow_bt = "", code, "", False
    elif len(code) >= 2 and code[0] == "`" and code[-1] == "`":
        head, body, tail, allow_bt = "`", code[1:-1], "`", False
    else:
        head, body, tail, allow_bt = "", code, "", False
    sub_parts, pos = [], 0
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
            # Sentence punctuation and Markdown emphasis after the link: **https://a.ru**
            tail = url[len(url.rstrip(".,;:!?…*_")):]
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
        # `inline code` and code-like (<30% Cyrillic) ``` blocks stay untouched, while paste
        # invisibles in unquoted code tokens are stripped. A ``` block of Russian prose is cleaned.
        fences = []
        # A file is read as is (CRLF kept), so the closing fence may end in \r.
        for m in re.finditer(r"^```[^\n]*\n.*?^```[ \t]*\r?$", cur, re.S | re.M):
            letters = re.findall(r"[A-Za-zА-Яа-яЁё]", m.group())
            if sum(1 for x in letters if x > "z") < 0.3 * max(1, len(letters)):
                fences.append((m.start(), m.end()))
        fence_starts = [s for s, _ in fences]
        spans = list(fences)
        for m in re.finditer(r"`[^`\n]+`", cur):
            idx = bisect.bisect_right(fence_starts, m.start()) - 1
            if idx < 0 or m.start() >= fences[idx][1]:
                spans.append((m.start(), m.end()))
        parts, pos = [], 0
        for s, e in sorted(spans):
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
                while True:
                    c_step = 0
                    for kind, rx in CITATIONS:
                        chunk, n = rx.subn("", chunk)
                        bump(kind, n)
                        c_step += n
                    step += c_step
                    if not c_step:
                        break
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
            # gone, so "c\u200bиcт\u00adeмa" and NFD "cиcтeмoи\u0306" repair in one pass.
            parts[i] = PROSE_HOMO_RX.sub(fix_homo, chunk)
        return "".join(parts), step_counts

    for _ in range(3):
        text, step_counts = _clean_once(text)
        if not step_counts:
            break
        for k, v in step_counts.items():
            counts[k] = counts.get(k, 0) + v
        if "`" not in text:
            break
    return text, counts


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    in_place = "--in-place" in args
    args = [a for a in args if a != "--in-place"]
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    path = args[0]
    # Line endings are kept as they are: removing one invisible character must not turn a
    # Windows file (CRLF) into LF or write CR CR LF to the console.
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="")
    try:
        if path == "-":
            src = sys.stdin.read()
        else:
            with open(path, encoding="utf-8", newline="") as fh:
                src = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("Не могу прочитать файл: %s" % exc, file=sys.stderr)
        return 2
    cleaned, counts = clean(src)
    if in_place and path != "-":
        if counts:
            shutil.copyfile(path, path + ".bak")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(cleaned)
    else:
        sys.stdout.write(cleaned)
    report = ", ".join("%s: %d" % kv for kv in sorted(counts.items())) or "мусора вставки нет"
    print("Очистка вставки: " + report, file=sys.stderr)
    return 1 if counts else 0


if __name__ == "__main__":
    raise SystemExit(main())
