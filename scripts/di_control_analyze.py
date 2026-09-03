#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""di_control_analyze.py — единственный анализатор положительного контроля Di.

Один проход; написан и хеширован ДО прогона (предрег di-control-2026-09.md
§4). Вход: measurement/di-control-2026-09/results-<family>.json ×3
(append-only блоки судей: [{"cell","choice","reason"} ×18]) + sides.json.
Выход: control-report.json + печать. Переанализ запрещён (кроме ошибки кода
этого скрипта с документированием diffs).

Правила (дословно из предрега):
  - верный выбор = выбрана человеческая сторона (side из sides.json);
  - tie = неверно; choice=null = неголос (вне знаменателя);
  - аннулирование: reason, совпадающий с INVALIDATION_PATTERNS (канон v4) =
    неголос + нарушение протокола; ≥1 аннулирования за контроль = СТОП
    (метрики не формируются, отчёт помечается PROTOCOL_VIOLATION);
  - критерий семейства: определённых ≥ 15 из 18 И верных/определённых ≥ 0.75;
  - PASS контроля: все три семейства прошли; иначе FAIL;
  - агрегат описательно: попарное большинство семейств (ничьи/null семьи не
    голосуют; равенство = пара не определена) + Wilson 95% CI.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent
DIR = RUN / "measurement" / "di-control-2026-09"
FAMILIES = ("qwen", "deepseek", "kimi")
EXPECTED_CELLS = 18
FAMILY_MIN_DECIDED = 15
FAMILY_MIN_ACC = 0.75

# Канон аннулирования дословно из предрега v4 §2 (единый литерал).
INVALIDATION_PATTERNS = re.compile(
    r"\bфайл|\bхеш|\bsha|\bhash|\bкаталог|\.txt\b|\.json\b|путь к файлу|по пути|идентичн\w*\s+пут",
    re.IGNORECASE)


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (c - h, c + h)


def load_family(fam: str):
    p = DIR / f"results-{fam}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def analyze() -> dict:
    sides = json.loads((DIR / "sides.json").read_text(encoding="utf-8"))
    report = {"design": "di-control-2026-09", "cells": EXPECTED_CELLS,
              "families": list(FAMILIES), "protocol_violations": [],
              "absent_families": [], "family_results": {}, "aggregate": None,
              "verdict": None}
    per_cell_votes = {}  # cell -> [True/False per valid family]
    for fam in FAMILIES:
        rows = load_family(fam)
        if rows is None:
            report["absent_families"].append(fam)
            continue
        fam_sides = {r["cell"]: r for r in sides[fam]}
        if len(rows) != EXPECTED_CELLS:
            report["absent_families"].append(fam)
            report["protocol_violations"].append(
                f"{fam}: блок вернул {len(rows)} строк вместо {EXPECTED_CELLS} — ABSENT (дозапуск целым блоком один раз)")
            continue
        correct = wrong = nulls = invalid = ties = 0
        for row in rows:
            cell = row.get("cell")
            if cell not in fam_sides:
                invalid += 1
                report["protocol_violations"].append(
                    f"{fam}: строка с неизвестной ячейкой {cell!r}")
                continue
            reason = str(row.get("reason") or "")
            if INVALIDATION_PATTERNS.search(reason):
                invalid += 1
                report["protocol_violations"].append(
                    f"{fam}/{cell}: аннулирование (токен канона в reason)")
                continue
            choice = row.get("choice")
            if choice is None:
                nulls += 1
                continue
            s = fam_sides[cell]
            human_side = "1" if s["side1"] == "human" else "2"
            if str(choice) == "tie":
                ties += 1
                wrong += 1
                per_cell_votes.setdefault(cell, []).append(False)
            elif str(choice) == human_side:
                correct += 1
                per_cell_votes.setdefault(cell, []).append(True)
            elif str(choice) in ("1", "2"):
                wrong += 1
                per_cell_votes.setdefault(cell, []).append(False)
            else:
                invalid += 1
                report["protocol_violations"].append(
                    f"{fam}/{cell}: choice вне схемы: {choice!r}")
        decided = correct + wrong
        acc = (correct / decided) if decided else 0.0
        lo, hi = wilson(correct, decided)
        fam_pass = decided >= FAMILY_MIN_DECIDED and acc >= FAMILY_MIN_ACC
        report["family_results"][fam] = {
            "correct": correct, "wrong": wrong, "ties": ties, "nulls": nulls,
            "invalid": invalid, "decided": decided, "accuracy": round(acc, 4),
            "wilson95": [round(lo, 4), round(hi, 4)], "pass": fam_pass,
        }
    # Агрегат (описательно): попарное большинство голосов семейств.
    pairs_correct = pairs_wrong = pairs_undecided = 0
    for cell, votes in sorted(per_cell_votes.items()):
        if not votes:
            pairs_undecided += 1
            continue
        t = sum(1 for v in votes if v)
        f = len(votes) - t
        if t > f:
            pairs_correct += 1
        elif f > t:
            pairs_wrong += 1
        else:
            pairs_undecided += 1
    dec = pairs_correct + pairs_wrong
    lo, hi = wilson(pairs_correct, dec)
    report["aggregate"] = {
        "pairs": EXPECTED_CELLS, "decided": dec,
        "correct_majority": pairs_correct, "undecided": pairs_undecided,
        "share_of_decided": round(pairs_correct / dec, 4) if dec else None,
        "wilson95": [round(lo, 4), round(hi, 4)],
    }
    fams_ok = [f for f in FAMILIES if f in report["family_results"]]
    if report["protocol_violations"] and any("аннулирование" in v for v in report["protocol_violations"]):
        report["verdict"] = "PROTOCOL_VIOLATION"
    elif report["absent_families"]:
        report["verdict"] = "ABSENT:" + ",".join(report["absent_families"])
    elif len(fams_ok) == 3 and all(report["family_results"][f]["pass"] for f in fams_ok):
        report["verdict"] = "PASS"
    else:
        report["verdict"] = "FAIL"
    return report


def main() -> int:
    report = analyze()
    out = DIR / "control-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("ВЕРДИКТ:", report["verdict"])
    for fam, r in report["family_results"].items():
        print("  %s: верных %d из %d определённых (ничьи %d, null %d, "
              "аннулировано %d) acc=%.3f CI[%.3f; %.3f] pass=%s"
              % (fam, r["correct"], r["decided"], r["ties"], r["nulls"],
                 r["invalid"], r["accuracy"], r["wilson95"][0],
                 r["wilson95"][1], r["pass"]))
    a = report["aggregate"]
    if a:
        print("  агрегат (описательно): большинство верных на %d из %d "
              "определённых пар, CI[%.3f; %.3f]"
              % (a["correct_majority"], a["decided"], a["wilson95"][0],
                 a["wilson95"][1]))
    for v in report["protocol_violations"]:
        print("  НАРУШЕНИЕ:", v)
    print("отчёт:", out)
    print("sha256 отчёта:", hashlib.sha256(out.read_bytes()).hexdigest()[:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
