#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Find signs of machine style in Russian text (RuSlop): fixed phrases from the sign
#          table of SKILL.md and simple structure metrics (dashes, rhythm, bold, headings,
#          emoji, invisible characters). It says where to look, not who wrote the text: people
#          write like this too. Used by step 7 of the skill as a self-check of the result.
# SCOPE: deterministic, stdlib only; reads rules.json next to this file (or --rules); prints a
#        Russian report or --json. Text inside ``` blocks and inside quotes is not checked.
# DEPENDS: Python 3.8+ standard library; rules.json (single source, also read by site/check).
# LINKS: M-LINT-STYLE; R-LINT-STYLE; V-M-LINT-STYLE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load_rules: rules.json -> compiled phrase rules and metric settings; \b means a Cyrillic-aware
#             word boundary (expanded the same way in site/check/engine.js).
# lint: text -> report dict (hits with examples, metrics, score, level).
# render: report dict -> Russian text.
# main: CLI `lint_style.py file|- [--json] [--rules PATH] [--max-score X]`.
# END_MODULE_MAP
"""Поиск признаков машинного стиля в русском тексте.

    python lint_style.py текст.txt          # отчёт
    python lint_style.py текст.txt --json   # отчёт в JSON
    python lint_style.py -                  # чтение из stdin

Это оценка стиля, а не авторства. Код выхода: 0 — отчёт готов; 1 — балл выше --max-score;
2 — файл не читается.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

RULES_PATH = Path(__file__).resolve().parent / "rules.json"

# START_BLOCK_ENGINE
# Everything here is mirrored line by line in site/check/engine.js; change both together
# (tests/test_lint.py runs both on the same fixtures).
W = "0-9A-Za-zА-Яа-яЁё_"
BOUNDARY = "(?:(?<=[%s])(?![%s])|(?<![%s])(?=[%s]))" % (W, W, W, W)
WORD_RX = re.compile("[0-9A-Za-zА-Яа-яЁё]+(?:-[0-9A-Za-zА-Яа-яЁё]+)*")
FENCE_RX = re.compile("```[\\s\\S]*?```")
QUOTE_RX = re.compile("«[^«»\\n]{0,300}»|\"[^\"\\n]{0,300}\"|“[^“”\\n]{0,300}”")
SENT_SPLIT_RX = re.compile("[.!?…]+(?=\\s|$)|\\n+")
DASH_RX = re.compile("(?<=[ \\u00a0])[—–-](?=[ \\u00a0])")
BOLD_RX = re.compile("\\*\\*[^*\\n]+?\\*\\*")
HEADING_RX = re.compile("^(?:#{1,6}\\s+\\S.*|\\*\\*[^*\\n]+\\*\\*:?)$")


def load_rules(path=RULES_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for rule in data["phrases"]:
        flags = 0
        for f in rule.get("flags", "i"):
            flags |= {"i": re.IGNORECASE, "m": re.MULTILINE}[f]
        rule["rx"] = re.compile(rule["re"].replace("\\b", BOUNDARY), flags)
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


# START_CONTRACT: lint
# PURPOSE: All signs in one text.
# INPUTS: text (str), rules from load_rules.
# OUTPUTS: {"chars", "words", "hits": [{id, sign, name, hint, soft, count, examples:[{text, line}]}],
#           "metrics": {id: {sign, name, hint, value, limit, over}}, "score", "level"}.
# RULES: a phrase match that starts inside «…», "…" or “…” is a quote and does not count; chars
#        are code points; score = 1000 * weighted hits / max(words, levels.min_words) + scored
#        metrics over the limit (a metric with "score": false is shown, never counted),
#        where a "soft" rule weighs 0.5; level by rules["levels"].
# END_CONTRACT: lint
def lint(text: str, rules: dict) -> dict:
    body = _blank_fences(text.replace("\r\n", "\n"))
    quotes = [(m.start(), m.end()) for m in QUOTE_RX.finditer(body)]
    words = len(WORD_RX.findall(body))
    chars = len(body)
    hits, weighted = [], 0.0
    for rule in rules["phrases"]:
        found = [m for m in rule["rx"].finditer(body)
                 if m.group(0).strip() and not any(a < m.start() < b for a, b in quotes)]
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
    openers = Counter(s[0].lower().replace("ё", "е") for s in sents)
    vals = {
        "dash_per_1000": (1000.0 * len(DASH_RX.findall(body)) / chars) if chars else 0.0,
        "sentence_cv": (statistics.pstdev(lens) / statistics.mean(lens))
        if len(lens) >= m["sentence_cv"]["min_sentences"] else None,
        "same_opener_share": (max(openers.values()) / len(sents))
        if len(sents) >= m["same_opener_share"]["min_sentences"] else None,
        "bold_per_line": (len(BOLD_RX.findall(body)) / len(lines))
        if len(lines) >= m["bold_per_line"]["min_lines"] else None,
        "heading_share": (sum(1 for ln in lines if HEADING_RX.match(ln)) / len(lines))
        if len(lines) >= m["heading_share"]["min_lines"] else None,
        "emoji_per_1000": (1000.0 * sum(1 for ch in body if any(a <= ord(ch) <= b for a, b in m["emoji_per_1000"]["ranges"])) / chars)
        if chars else 0.0,
        "invisible": float(sum(1 for ch in text if ord(ch) in m["invisible"]["codepoints"])),
    }
    metrics, over_count = {}, 0
    for key, value in vals.items():
        cfg = m[key]
        limit = cfg.get("max", cfg.get("min"))
        over = value is not None and (value < cfg["min"] if "min" in cfg else value > cfg["max"])
        scored = cfg.get("score", True)
        over_count += over and scored
        metrics[key] = {"sign": cfg["sign"], "name": cfg["name"], "hint": cfg["hint"],
                        "value": None if value is None else round(value, 3), "limit": limit, "over": over,
                        "scored": scored}
    lv = rules["levels"]
    score = round(1000.0 * weighted / max(words, lv["min_words"]) + over_count, 2)
    # Info-only metrics (score: false) never raise the level, even from "нет".
    level = ("нет" if not hits and not over_count else
             "много" if score >= lv["many"] else "есть" if score >= lv["some"] else "мало")
    return {"chars": chars, "words": words, "hits": hits, "metrics": metrics, "score": score, "level": level}
# END_BLOCK_ENGINE


LEVEL_TEXT = {"нет": "признаков не найдено", "мало": "мало признаков", "есть": "есть признаки",
              "много": "много признаков"}


def render(rep: dict) -> str:
    out = ["Машинный стиль: %s (балл %.1f; слов %d). Это оценка стиля, а не авторства: "
           "найденное может быть к месту." % (LEVEL_TEXT[rep["level"]], rep["score"], rep["words"])]
    for h in sorted(rep["hits"], key=lambda h: (h["sign"], h["id"])):
        ex = "; ".join("«%s» (стр. %d)" % (e["text"], e["line"]) for e in h["examples"])
        out.append("#%d %s — %d: %s. %s" % (h["sign"], h["name"], h["count"], ex, h["hint"]))
    for key, mt in rep["metrics"].items():
        if mt["over"]:
            note = "" if mt["scored"] else " Для сведения: в балл не входит."
            out.append("#%d %s: %s (граница %s). %s%s" % (mt["sign"], mt["name"], round(mt["value"], 2), mt["limit"], mt["hint"], note))
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
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print("[M-LINT-STYLE] не читается: %s" % exc, file=sys.stderr)
        return 2
    rep = lint(text, load_rules(args.rules))
    print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else render(rep))
    return 1 if args.max_score is not None and rep["score"] > args.max_score else 0


if __name__ == "__main__":
    raise SystemExit(main())
