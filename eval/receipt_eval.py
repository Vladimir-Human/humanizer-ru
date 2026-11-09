#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Gate 4 of 4.2.0 (eval/README, plan v3 M4): with a terminal the skill ends its notes with
#          «Сверка скриптом: …», and that line is the one check_facts.py prints for the same source and
#          edit (the agent copies it word for word); without a terminal the line never appears (a
#          made-up receipt would be worse than none).
# SCOPE: reads eval/results/<run>/outputs/<system>/<id>.txt and the corpus sources; writes
#        eval/results/<run>/receipt.md and receipt.json. No model calls.
# DEPENDS: evallib (split_notes, IO), skills/humanizer-ru/scripts/check_facts.py.
# LINKS: M-EVAL-RECEIPT; R-RECEIPT; V-M-EVAL-RECEIPT.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# receipt_line: the last notes line that opens with «Сверка скриптом».
# stated_counts: {"number"|"date"|"name": n} named in that line («4 числа, 2 даты, 3 имени»).
# same_line: the answer's line equals check_facts.receipt for the source and the edit (case, dashes,
#            quotes and the final dot aside).
# score_one: line present, same as the script's, stated counts vs the script's, script errors left;
#            facts_ok: the counts it names and every value the script misses in the edit are in it.
# main: CLI `receipt_eval.py --run R [--system ours] [--expect present|absent]`.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import importlib.util
import re
import sys

import evallib as lib

_spec = importlib.util.spec_from_file_location("check_facts", lib.EVAL_DIR.parent / "skills" / "humanizer-ru" / "scripts" / "check_facts.py")
check_facts = importlib.util.module_from_spec(_spec)
sys.modules["check_facts"] = check_facts
_spec.loader.exec_module(check_facts)

LINE_RX = re.compile(r"^\W*Сверка скриптом\b.*$", re.M)
COUNT_RX = {
    "number": re.compile(r"(\d+)\s+чис", re.I),
    "date": re.compile(r"(\d+)\s+дат", re.I),
    "name": re.compile(r"(\d+)\s+(?:им[еяё]|назван)", re.I),  # имя, имени, имён, названий
}


def receipt_line(answer: str) -> str:
    found = LINE_RX.findall(answer)
    return found[-1].strip() if found else ""


def stated_counts(line: str) -> dict:
    out = {}
    for kind, rx in COUNT_RX.items():
        m = rx.search(line)
        if m:
            out[kind] = int(m.group(1))
    return out


def _plain(line: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^\W+|[.\s]+$", "", line.replace("ё", "е"))).lower()


def same_line(line: str, expected: str) -> bool:
    return bool(line) and bool(expected) and _plain(line) == _plain(expected)


def score_one(source: str, answer: str) -> dict:
    edit = lib.split_notes(answer, source)[0]
    res = check_facts.compare(source, edit)
    line = receipt_line(answer)
    stated = stated_counts(line)
    wrong = {k: (v, res["counts"][k]) for k, v in stated.items() if res["counts"][k] != v}
    expected = check_facts.receipt(res)
    missing = [e["detail"] for e in res["errors"]]
    facts_ok = bool(line) and not wrong and all(d in line for d in missing)
    return {"line": line, "expected": expected, "same_line": same_line(line, expected), "facts_ok": facts_ok,
            "stated": stated,
            "counts_match": bool(line) and not wrong, "wrong_counts": wrong,
            "script_errors": [e["detail"] for e in res["errors"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--system", default="ours")
    ap.add_argument("--expect", choices=("present", "absent"), default="present")
    args = ap.parse_args(argv)
    run_dir = lib.EVAL_DIR / "results" / args.run
    rows = {}
    for f in sorted((run_dir / "outputs" / args.system).glob("*.txt")):
        src = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (f.stem + ".txt"))
        rows[f.stem] = score_one(src, lib.read_text(f))
    n = len(rows)
    present = sum(1 for r in rows.values() if r["line"])
    match = sum(1 for r in rows.values() if r["counts_match"])
    same = sum(1 for r in rows.values() if r["same_line"])
    facts = sum(1 for r in rows.values() if r["facts_ok"])
    with_errors = sorted(t for t, r in rows.items() if r["script_errors"])
    md = ["# Строка сверки: %s / %s" % (args.run, args.system), "",
          "Ответов: %d. Строка «Сверка скриптом» есть в %d; дословно совпадает со строкой скрипта для "
          "этого исходника и этой правки в %d; названные в ней числа совпадают со сверкой в %d; "
          "числа и все значения, которых скрипт не нашёл в правке, в ней такие же, как у скрипта, в %d. "
          "Тексты, где сверка скриптом ещё находит ошибки в итоговой правке: %s." % (
              n, present, same, match, facts, ", ".join(with_errors) or "нет"), "",
          "| Текст | Строка | Как у скрипта | Ошибки сверки |", "|---|---|---|---|"]
    for tid, r in rows.items():
        md.append("| %s | %s | %s | %s |" % (tid, r["line"].replace("|", "/") or "—",
                                             "да" if r["same_line"] else ("нет: %s" % (r["expected"] or "строки нет") if r["line"] else "—"),
                                             "; ".join(r["script_errors"]) or "—"))
    if args.expect == "present":
        md += ["", "Порог 4 (R-RECEIPT): строка хотя бы в 10 из 12: %s; факты в строке как у скрипта хотя бы в 10 из 12: %s; "
               "дословно как у скрипта хотя бы в 10 из 12: %s." % (
            "пройден" if present >= 10 else "не пройден", "да" if facts >= 10 else "нет", "да" if same >= 10 else "нет")]
    else:
        md += ["", "Без терминала строки быть не должно: %s." % ("ни одной" if present == 0 else "есть в %d" % present)]
    lib.write_text(run_dir / "receipt.md", "\n".join(md) + "\n")
    lib.write_json(run_dir / "receipt.json", rows)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
