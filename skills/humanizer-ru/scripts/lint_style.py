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
#        Russian report or --json. Text inside ``` blocks and inside quotes is not checked for
#        phrase rules or nominalization chains; mixed_script also skips inline code, URLs and mail.
# DEPENDS: Python 3.8+ standard library; rules.json (single source, also read by site/check).
# LINKS: M-LINT-STYLE; R-LINT-STYLE; R-RULES-EVIDENCE; R-DETECTOR-RISK; V-M-LINT-STYLE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load_rules: rules.json -> compiled phrase rules and metric settings; \b means a Cyrillic-aware
#             word boundary (expanded the same way in site/check/engine.js).
# lint: text -> report dict (hits with examples, metrics, score, level).
# render: report dict -> Russian text.
# main: CLI `lint_style.py file|- [--json] [--rules PATH] [--max-score X]`.
# END_MODULE_MAP
"""Поиск признаков машинного стиля и технических следов в русском тексте.

    python lint_style.py текст.txt          # отчёт
    python lint_style.py текст.txt --json   # отчёт в JSON
    python lint_style.py -                  # чтение из stdin

Это оценка стиля и чистоты текста, а не авторства. Код выхода: 0 — отчёт готов;
1 — балл выше --max-score; 2 — файл не читается.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import unicodedata
from bisect import bisect_right
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
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
FENCE_RX = re.compile("```[\\s\\S]*?```")
QUOTE_RX = re.compile("«[^«»\\n]{0,300}»|\"[^\"\\n]{0,300}\"|“[^“”\\n]{0,300}”")
SENT_SPLIT_RX = re.compile("[.!?…]+(?=\\s|$)|\\n+")
DASH_RX = re.compile("(?<=[ \\u00a0])[—–-](?=[ \\u00a0])")
BOLD_RX = re.compile("\\*\\*[^*\\n]+?\\*\\*")
HEADING_RX = re.compile("^(?:#{1,6}\\s+\\S[^\\n]*|\\*\\*[^*\\n]+\\*\\*:?)$")
LIST_LINE_RX = re.compile("^(?:[-*•+]|[0-9]+[.)])\\s+\\S")
INLINE_CODE_RX = re.compile("`[^`\\n]+`")
LINK_MAIL_RX = re.compile(
    "(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\\.)\\S+"
    "|(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\\.[A-Za-zА-Яа-яЁё]{2,}"
    "|\\]\\([ \\t]*(?:<[^>\\n]+>|[^)<\\s][^)\\s]*)"
)
SUBWORD_RX = re.compile("[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+")
LAT_RX = re.compile("[" + LAT + "]")
CYR_RX = re.compile("[А-Яа-яЁё]")
NOM_SPLIT_RX = re.compile("[.!?…,:;()\\n—–«»\"“”]+")
CYR_TOK_RX = re.compile("[А-Яа-яЁё" + ACUTE + "]{2,}")
NOM_WORD_RX = re.compile(
    "^[а-я]{3,}(?:ени(?:е|я|ю|ем|и|й|ям|ями|ях)|ани(?:е|я|ю|ем|и|й|ям|ями|ях)|"
    "ост(?:ь|и|ью|ей|ям|ями|ях)|ств(?:о|а|у|ом|е|ам|ами|ах)|аци(?:я|и|ю|ей|й|ям|ями|ях))$"
)
NOM_GEN_RX = re.compile("^[а-я]{3,}(?:ени(?:я|й)|ани(?:я|й)|ост(?:и|ей)|ств(?:а)|аци(?:и|й))$")
ADJ_GEN_RX = re.compile("^[а-я]{3,}(?:ого|его|ой|ей|ых|их)$")
FINITE_VERB_RX = re.compile(
    "^[а-я]{2,}(?:ет|ют|ит|ат|ят|ется|ются|ится|атся|ятся|"
    "ал|ала|ало|али|ил|ила|ило|или|ел|ела|ело|ели|ул|ула|ули|лся|лась|лись)$"
)


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
            list(inv["codepoints"]) + [0xFE0F],
            list(inv.get("ranges", ())) + [[0xE0000, 0xE007F]],
        )
    )
    return data


def _blank_fences(text: str) -> str:
    """Code blocks become blank lines, so line numbers and lengths of the rest stay."""
    return FENCE_RX.sub(lambda m: re.sub("[^\\n]", " ", m.group(0)), text)


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
        b_lines = [ln.strip() for ln in trimmed.split("\n") if ln.strip()]
        if all(LIST_LINE_RX.match(ln) for ln in b_lines):
            continue
        w = len(WORD_RX.findall(trimmed))
        if w >= min_words:
            out.append(w)
    return out


def _cyr_words(text: str) -> list:
    out = []
    for tok in CYR_TOK_RX.findall(text):
        w = tok.lower().replace("ё", "е").replace(ACUTE, "")
        if len(w) >= 2:
            out.append(w)
    return out


def _nominal_cascades(body: str) -> int:
    unquoted = QUOTE_RX.sub(",", body)
    total = 0
    for clause in NOM_SPLIT_RX.split(unquoted):
        cw = _cyr_words(clause)
        i = 0
        while i < len(cw) - 1:
            if NOM_WORD_RX.match(cw[i]):
                if NOM_GEN_RX.match(cw[i + 1]):
                    total += 1
                    i += 2
                    continue
                if i + 2 < len(cw) and ADJ_GEN_RX.match(cw[i + 1]) and NOM_GEN_RX.match(cw[i + 2]):
                    total += 1
                    i += 3
                    continue
            i += 1
    return total


def _nom_to_verb(body: str) -> float:
    unquoted = QUOTE_RX.sub(" ", body)
    cw = _cyr_words(unquoted)
    noms = sum(1 for w in cw if NOM_WORD_RX.match(w))
    verbs = sum(1 for w in cw if FINITE_VERB_RX.match(w))
    return noms / max(1, verbs)


def _mixed_subwords(body: str) -> list:
    scrub = INLINE_CODE_RX.sub(lambda m: " " * len(m.group(0)), body)
    scrub = LINK_MAIL_RX.sub(lambda m: " " * len(m.group(0)), scrub)
    return [m for m in SUBWORD_RX.finditer(scrub)
            if LAT_RX.search(m.group(0)) and CYR_RX.search(m.group(0))]


def _is_emoji_base(cp: int) -> bool:
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF or 0x2190 <= cp <= 0x21FF or 0x25A0 <= cp <= 0x25FF
            or 0x1F3FB <= cp <= 0x1F3FF
            or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299))


def _count_invisible(cps: list, inv_set: set, inv_ranges: list) -> int:
    total = 0
    in_flag = False
    n = len(cps)
    for i, cp in enumerate(cps):
        if in_flag and 0xE0020 <= cp <= 0xE007F:
            if cp == 0xE007F:
                in_flag = False
            continue
        in_flag = cp in (0x1F3F4, 0x1F3F3)
        if cp in inv_set or any(a <= cp <= b for a, b in inv_ranges):
            total += 1
        elif cp == 0xFE0F:
            prev = cps[i - 1] if i > 0 else -1
            nxt = cps[i + 1] if i + 1 < n else -1
            if not (_is_emoji_base(prev) or ((prev in (0x23, 0x2A) or 0x30 <= prev <= 0x39) and nxt == 0x20E3)):
                total += 1
        elif 0xE0000 <= cp <= 0xE007F:
            total += 1
    return total


def _in_quotes(q_starts: list, q_ends: list, pos: int) -> bool:
    idx = bisect_right(q_starts, pos - 1) - 1
    return idx >= 0 and pos < q_ends[idx]


# START_CONTRACT: lint
# PURPOSE: All signs in one text.
# INPUTS: text (str), rules from load_rules.
# OUTPUTS: {"chars", "words", "hits": [{id, sign, name, hint, soft, count, examples:[{text, line}]}],
#           "metrics": {id: {sign, name, hint, value, limit, over, scored, examples?}}, "score", "level"}.
# RULES: input is NFC-normalized; a phrase match that starts inside «…», "…" or “…” is a quote and
#        does not count; chars are code points; score = 1000 * weighted hits / max(words, levels.min_words)
#        + scored metrics over the limit (a metric with "score": false is shown, never counted),
#        where a "soft" rule weighs 0.5; level by rules["levels"].
# END_CONTRACT: lint
def lint(text: str, rules: dict) -> dict:
    norm = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    body = _blank_fences(norm)
    quotes = [(m.start(), m.end()) for m in QUOTE_RX.finditer(body)]
    q_starts = [a for a, _ in quotes]
    q_ends = [b for _, b in quotes]
    words = len(WORD_RX.findall(body))
    chars = len(body)
    hits, weighted = [], 0.0
    for rule in rules["phrases"]:
        found = [m for m in rule["rx"].finditer(body)
                 if m.group(0).strip() and not _in_quotes(q_starts, q_ends, m.start())]
        if not found:
            continue
        soft = bool(rule.get("soft"))
        weighted += len(found) * (0.5 if soft else 1.0)
        hits.append({"id": rule["id"], "sign": rule["sign"], "name": rule["name"], "hint": rule["hint"],
                     "soft": soft, "count": len(found),
                     "examples": [{"text": m.group(0).strip()[:60], "line": _line_of(body, m.start())} for m in found[:3]]})

    m = rules["metrics"]
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    sents = _sentences(body)
    lens = [len(s) for s in sents]
    para_lens = _paragraph_lengths(body, m["paragraph_cv"]["min_words"])
    openers = Counter(s[0].lower().replace("ё", "е").replace(ACUTE, "") for s in sents)
    mixed_found = _mixed_subwords(body)
    inv_cfg = m["invisible"]
    inv_set = inv_cfg.get("_set") or set(inv_cfg["codepoints"])
    inv_ranges = inv_cfg.get("_big") if "_set" in inv_cfg else inv_cfg.get("ranges", [])
    inv_rx = inv_cfg.get("_rx")
    emoji_rx = m["emoji_per_1000"].get("_rx")
    inv_count = (
        0 if (inv_rx is not None and not inv_rx.search(norm))
        else _count_invisible([ord(ch) for ch in norm], inv_set, inv_ranges)
    )
    emoji_count = (
        len(emoji_rx.findall(body)) if emoji_rx is not None
        else sum(1 for ch in body if any(a <= ord(ch) <= b for a, b in m["emoji_per_1000"]["ranges"]))
    )
    vals = {
        "dash_per_1000": (1000.0 * len(DASH_RX.findall(body)) / chars) if chars else 0.0,
        "sentence_cv": (statistics.pstdev(lens) / statistics.mean(lens))
        if len(lens) >= m["sentence_cv"]["min_sentences"] else None,
        "paragraph_cv": (statistics.pstdev(para_lens) / statistics.mean(para_lens))
        if len(para_lens) >= m["paragraph_cv"]["min_paragraphs"] else None,
        "same_opener_share": (max(openers.values()) / len(sents))
        if len(sents) >= m["same_opener_share"]["min_sentences"] else None,
        "nominal_chain": (1000.0 * _nominal_cascades(body) / words)
        if words >= m["nominal_chain"]["min_words"] else None,
        "nom_to_verb": _nom_to_verb(body)
        if words >= m["nom_to_verb"]["min_words"] else None,
        "bold_per_line": (len(BOLD_RX.findall(body)) / len(lines))
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
        limit = cfg.get("max", cfg.get("min"))
        over = value is not None and (value < cfg["min"] if "min" in cfg else value > cfg["max"])
        scored = cfg.get("score", True)
        over_count += over and scored
        entry = {"sign": cfg["sign"], "name": cfg["name"], "hint": cfg["hint"],
                 "value": None if value is None else round(value, 3), "limit": limit, "over": over,
                 "scored": scored}
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
            out.append("#%d %s: %s (граница %s)%s. %s%s" % (
                mt["sign"], mt["name"], _fmt_num(mt["value"]), _fmt_num(mt["limit"]), ex, mt["hint"], note))
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Признаки машинного стиля в русском тексте")
    ap.add_argument("file", help="файл с текстом или - для stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rules", default=str(RULES_PATH))
    ap.add_argument("--max-score", type=float, default=None)
    args = ap.parse_args(argv)
    try:
        # stdin as bytes: on Windows sys.stdin decodes with the console code page (cp1251), and
        # UTF-8 text piped in turned into mojibake with no signs found.
        text = sys.stdin.buffer.read().decode("utf-8-sig") if args.file == "-" else Path(args.file).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        print("[M-LINT-STYLE] не читается: %s" % exc, file=sys.stderr)
        return 2
    rep = lint(text, load_rules(args.rules))
    print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else render(rep))
    return 1 if args.max_score is not None and rep["score"] > args.max_score else 0


if __name__ == "__main__":
    raise SystemExit(main())
