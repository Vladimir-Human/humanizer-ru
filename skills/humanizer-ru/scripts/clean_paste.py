#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Remove chat-interface leftovers from pasted text: citation tokens
#          (contentReference, 【N†source】, [cite: N]), the utm_source tail a chat assistant
#          adds to links (chatgpt.com, openai; also behind &amp;, ** or a zero-width
#          character), invisible characters. Text, links, the author's own utm tags, emoji,
#          `inline code`, code-like ``` blocks and line endings (CRLF) stay intact.
# SCOPE: deterministic, stdlib only; style and wording are not touched.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CLEAN-PASTE; DF-SKILL-CLEAN; V-M-CLEAN-PASTE.
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

import re
import shutil
import sys
from typing import Dict, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# START_BLOCK_PATTERNS
CITATIONS = [
    ("contentReference", re.compile(r"[ \t]?:?contentReference\[oaicite:\d+\]\{index=\d+\}")),
    ("oaicite", re.compile(r"[ \t]?\[oaicite:\d+\]")),
    ("source-token", re.compile(r"[ \t]?【\d+(?::\d+)?(?:†[^】\n]{0,80})?】")),
    # Gemini opens a cited span with [cite_start] glued to its first word: the space before stays.
    ("cite", re.compile(r"\[cite_start\]")),
    ("cite", re.compile(r"[ \t]?\[cite(?:_end)?(?::\s*[\d,\s]+)?\]")),
]

# Invisible characters that never carry meaning in Russian prose.
INVISIBLE = {
    0x200B: "zero-width space", 0x2060: "word joiner", 0xFEFF: "BOM / zero-width no-break",
    0x00AD: "soft hyphen", 0x200E: "LTR mark", 0x200F: "RTL mark", 0x202A: "bidi", 0x202B: "bidi",
    0x202C: "bidi", 0x202D: "bidi", 0x202E: "bidi", 0x2066: "bidi", 0x2067: "bidi",
    0x2068: "bidi", 0x2069: "bidi", 0x180E: "mongolian vowel separator",
}
ZWJ = 0x200D
ZWNJ = 0x200C
URL_RX = r"(?:https?://|www\.)[^\s<>«»\"')\]`%s]+" % "".join(map(chr, (0x200B, 0x2060, 0xFEFF)))
# END_BLOCK_PATTERNS


# utm_source values chat assistants add to the links they cite (ru.wikipedia,
# «Признаки сгенерированности текста», UTM-метки, revision of 2026-10-08). Any other utm
# tag is the author's own (newsletter, campaign) and belongs to the link.
ASSISTANT_UTM_SOURCES = frozenset({"chatgpt.com", "openai"})


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
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or cp == 0xFE0F
            or 0x1F3FB <= cp <= 0x1F3FF)


# START_CONTRACT: clean
# PURPOSE: Strip paste artifacts from text.
# INPUTS: text (str).
# OUTPUTS: (cleaned text, {kind: count}).
# SIDE_EFFECTS: none.
# END_CONTRACT: clean
def clean(text: str) -> Tuple[str, Dict[str, int]]:
    counts: Dict[str, int] = {}

    def bump(kind: str, n: int = 1) -> None:
        if n:
            counts[kind] = counts.get(kind, 0) + n

    def fix_url(m: re.Match) -> str:
        url = m.group(0)
        # Sentence punctuation and Markdown emphasis after the link: **https://a.ru**
        tail = url[len(url.rstrip(".,;:!?…*_")):]
        new, n = strip_utm(url[:len(url) - len(tail)])
        bump("utm", n)
        return new + tail

    # Code is copied as is: citations and links inside `inline code` and code blocks stay. A ``` block
    # of Russian prose (a chat answer wraps a whole README or post in one) is text and is cleaned.
    spans = []
    # A file is read as is (CRLF kept), so the closing fence may end in \r.
    for m in re.finditer(r"^```[^\n]*\n.*?^```[ \t]*\r?$", text, re.S | re.M):
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", m.group())
        if sum(1 for x in letters if x > "z") < 0.3 * max(1, len(letters)):
            spans.append((m.start(), m.end()))
    for m in re.finditer(r"`[^`\n]+`", text):
        if not any(s <= m.start() < e for s, e in spans):
            spans.append((m.start(), m.end()))
    parts, pos = [], 0
    for s, e in sorted(spans):
        parts += [text[pos:s], text[s:e]]
        pos = e
    parts.append(text[pos:])
    for i in range(0, len(parts), 2):
        for kind, rx in CITATIONS:
            parts[i], n = rx.subn("", parts[i])
            bump(kind, n)
        # A zero-width character glued after a link ends it, so the utm tail before it is still seen.
        parts[i] = re.sub(URL_RX, fix_url, parts[i])
    text = "".join(parts)

    out = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp in INVISIBLE:
            bump("invisible")
            continue
        if cp in (ZWJ, ZWNJ):
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if cp == ZWJ and prev and nxt and (_is_emoji(prev) or _is_emoji(nxt)):
                out.append(ch)
                continue
            bump("invisible")
            continue
        out.append(ch)
    return "".join(out), counts


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
