#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The frontier-agent arm of the 4.2.0 measurement (eval/README, amendment of 09.11 21:00 UTC):
#          the same 12 holdout4 texts edited by Claude Sonnet 5.5 subagents with a terminal under
#          4.2.0, 4.1.7 and a plain request; per system, edits where check_facts.py still finds an
#          error, the errors themselves (read by eye afterwards), the style linter's score and
#          whether the notes end with the receipt line.
# SCOPE: reads eval/results/<run>/outputs/<system>/<id>.txt and the corpus sources; writes
#        eval/results/<run>/frontier.md and frontier.json. No model calls, no judge.
# DEPENDS: evallib (split_notes, IO), receipt_eval (check_facts, receipt_line), lint_style.py + rules.json.
# LINKS: M-EVAL-FRONTIER; R-RECEIPT; V-M-EVAL-FRONTIER.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# score_text: one answer -> errors (kind, what, detail), lint score and level, receipt line.
# summarize: rows of one system -> texts with errors, error count, mean lint score, receipt lines.
# main: CLI `frontier_eval.py --run R [--systems ours,ours417,prompt]`.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import importlib.util
import sys

import evallib as lib
import receipt_eval

_spec = importlib.util.spec_from_file_location(
    "lint_style", lib.EVAL_DIR.parent / "skills" / "humanizer-ru" / "scripts" / "lint_style.py")
lint_style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_style)
RULES = lint_style.load_rules()


def score_text(source: str, answer: str) -> dict:
    edit = lib.split_notes(answer, source)[0]
    res = receipt_eval.check_facts.compare(source, edit)
    rep = lint_style.lint(edit, RULES)
    return {"errors": [[e["kind"], e["what"], e["detail"]] for e in res["errors"]],
            "lint_score": rep["score"], "lint_level": rep["level"],
            "receipt": receipt_eval.receipt_line(answer)}


def summarize(rows: dict) -> dict:
    n = len(rows)
    return {"texts": n,
            "texts_with_errors": sorted(t for t, r in rows.items() if r["errors"]),
            "errors": sum(len(r["errors"]) for r in rows.values()),
            "lint_mean": round(sum(r["lint_score"] for r in rows.values()) / n, 2) if n else 0.0,
            "receipts": sum(1 for r in rows.values() if r["receipt"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--systems", default="ours,ours417,prompt")
    args = ap.parse_args(argv)
    run_dir = lib.EVAL_DIR / "results" / args.run
    data, md = {}, ["# Фронтир-агент: %s" % args.run, "",
                    "| Участник | Правок | С ошибкой сверки | Ошибок | Стиль, средний балл | Строка сверки |",
                    "|---|---|---|---|---|---|"]
    for name in args.systems.split(","):
        rows = {}
        for f in sorted((run_dir / "outputs" / name).glob("*.txt")):
            src = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (f.stem + ".txt"))
            rows[f.stem] = score_text(src, lib.read_text(f))
        s = summarize(rows)
        data[name] = {"summary": s, "rows": rows}
        md.append("| %s | %d | %d (%s) | %d | %.2f | %d |" % (
            name, s["texts"], len(s["texts_with_errors"]), ", ".join(s["texts_with_errors"]) or "—",
            s["errors"], s["lint_mean"], s["receipts"]))
    md += ["", "Ошибки сверки по текстам (каждую читать глазами: снятая обёртка чат-бота — не ошибка):", ""]
    for name, d in data.items():
        for tid, r in d["rows"].items():
            if r["errors"]:
                md.append("- %s %s: %s" % (name, tid, "; ".join("%s %s %s" % tuple(e) for e in r["errors"])))
    lib.write_text(run_dir / "frontier.md", "\n".join(md) + "\n")
    lib.write_json(run_dir / "frontier.json", data)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
