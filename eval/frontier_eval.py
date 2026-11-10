#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The frontier-agent arm of the 4.2.0 measurement (eval/README, amendment of 09.11 21:00 UTC):
#          the same 12 holdout4 texts edited by Claude Sonnet 5.5 subagents with a terminal under
#          4.2.0, 4.1.7 and a plain request; per system, edits where check_facts.py still finds an
#          error, the errors themselves (read by eye afterwards), the style linter's score and
#          whether the notes end with the receipt line. Facts are checked against the text part of the
#          source; values only the chat's own head or tail held (split off by «---») are listed apart,
#          as removed with the wrapper (cross-review 10.11 F3).
# SCOPE: reads eval/results/<run>/outputs/<system>/<id>.txt and the corpus sources; writes
#        eval/results/<run>/frontier.md and frontier.json. No model calls, no judge.
# DEPENDS: evallib (split_notes, IO), receipt_eval (check_facts, receipt_line), lint_style.py + rules.json.
# LINKS: M-EVAL-FRONTIER; R-RECEIPT; V-M-EVAL-FRONTIER.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# text_part: a source -> its longest stretch between «---» lines (the whole source when it has none).
# score_text: one answer -> errors against the text part, wrapper-only errors, lint score and level, receipt line.
# summarize: rows of one system -> texts with errors, error count, mean lint score, receipt lines.
# main: CLI `frontier_eval.py --run R [--systems ours,ours417,prompt]`.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import importlib.util
import re
import sys

import evallib as lib
import receipt_eval

_spec = importlib.util.spec_from_file_location(
    "lint_style", lib.EVAL_DIR.parent / "skills" / "humanizer-ru" / "scripts" / "lint_style.py")
lint_style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_style)
RULES = lint_style.load_rules()


# A chat answer's own head («Вот готовый вариант:», «Готовый пост (≈683 знака):») and tail («Пара
# замечаний», «Что учтено», «**Объём:**», «Если нужно, могу…»). Only the first and the last stretch can
# be one: «---» between the sections of a long text (m12, n05, t11 in the corpus) is text.
HEAD_RX = re.compile(r"(?i)^\W*(?:вот\b|готов)")
TAIL_RX = re.compile(r"(?i)^\W*(?:пара замечаний|несколько (?:замечаний|пояснений|слов)|что (?:учтено|нужно|стоит)|"
                     r"объём|замечани|служебн|заметки для|если (?:нужно|хотите)|могу\b|готово|советы?\W|"
                     r"перед отправкой)")


def text_part(source: str) -> str:
    parts, cur = [], []
    for ln in source.split("\n"):
        if ln.strip() == "---":
            parts.append("\n".join(cur).strip())
            cur = []
        else:
            cur.append(ln)
    parts.append("\n".join(cur).strip())
    if len(parts) > 1 and HEAD_RX.match(parts[0]) and len(parts[0]) <= 300 and "\n" not in parts[0]:
        parts = parts[1:]
    if len(parts) > 1 and TAIL_RX.match(parts[-1]):
        parts = parts[:-1]
    return "\n\n---\n\n".join(parts)


def _errors(source: str, edit: str) -> list:
    return [[e["kind"], e["what"], e["detail"]] for e in receipt_eval.check_facts.compare(source, edit)["errors"]]


def score_text(source: str, answer: str) -> dict:
    edit = lib.split_notes(answer, source)[0]
    errors = _errors(text_part(source), edit)
    rep = lint_style.lint(edit, RULES)
    return {"errors": errors, "wrapper": [e for e in _errors(source, edit) if e not in errors],
            "lint_score": rep["score"], "lint_level": rep["level"],
            "receipt": receipt_eval.receipt_line(answer)}


def summarize(rows: dict) -> dict:
    n = len(rows)
    return {"texts": n,
            "texts_with_errors": sorted(t for t, r in rows.items() if r["errors"]),
            "errors": sum(len(r["errors"]) for r in rows.values()),
            "wrapper": sum(len(r.get("wrapper", [])) for r in rows.values()),
            "lint_mean": round(sum(r["lint_score"] for r in rows.values()) / n, 2) if n else 0.0,
            "receipts": sum(1 for r in rows.values() if r["receipt"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--systems", default="ours,ours417,prompt")
    args = ap.parse_args(argv)
    run_dir = lib.EVAL_DIR / "results" / args.run
    data, md = {}, ["# Сверка фактов и стиль правок: %s" % args.run, "",
                    "Факты сверены с текстовой частью исходника; значения только из головы или хвоста ответа "
                    "чат-бота (за чертой «---») — в столбце «Снято с обёрткой».", "",
                    "| Участник | Правок | С ошибкой сверки | Ошибок | Снято с обёрткой | Стиль, средний балл | Строка сверки |",
                    "|---|---|---|---|---|---|---|"]
    for name in args.systems.split(","):
        rows = {}
        for f in sorted((run_dir / "outputs" / name).glob("*.txt")):
            src = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (f.stem + ".txt"))
            rows[f.stem] = score_text(src, lib.read_text(f))
        s = summarize(rows)
        data[name] = {"summary": s, "rows": rows}
        md.append("| %s | %d | %d (%s) | %d | %d | %.2f | %d |" % (
            name, s["texts"], len(s["texts_with_errors"]), ", ".join(s["texts_with_errors"]) or "—",
            s["errors"], s["wrapper"], s["lint_mean"], s["receipts"]))
    md += ["", "Ошибки сверки по текстам (каждую читать глазами: служебные слова чат-бота без черты «---» "
               "тоже попадают сюда):", ""]
    for name, d in data.items():
        for tid, r in d["rows"].items():
            if r["errors"] or r["wrapper"]:
                md.append("- %s %s: %s%s" % (name, tid, "; ".join("%s %s %s" % tuple(e) for e in r["errors"]) or "—",
                                             "; с обёрткой: " + ", ".join(e[2] for e in r["wrapper"])
                                             if r["wrapper"] else ""))
    lib.write_text(run_dir / "frontier.md", "\n".join(md) + "\n")
    lib.write_json(run_dir / "frontier.json", data)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
