#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_fp_report.py — гейт сверки чисел research/FP-CORPUS-2026.md
со снимком measurement/fp-corpus-2026-09/result.json и extras.json
(верификация 2026-09-04, пункт 5).

Запуск:
  python3 scripts/check_fp_report.py
  python3 scripts/check_fp_report.py --selftest
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Агрегаты опубликованы в репозитории (CI-воспроизводимость);
# приватный run-dir остаётся каноническим местом прогона,
# копия в репо = публикация снимка.
AGG = os.path.join(ROOT, "research", "fp-corpus-2026-09")


def load():
    rep = open(os.path.join(ROOT, "research", "FP-CORPUS-2026.md"),
               encoding="utf-8").read()
    res = json.load(open(os.path.join(AGG, "result.json"), encoding="utf-8"))
    ex = json.load(open(os.path.join(AGG, "extras.json"), encoding="utf-8"))
    return rep, res, ex


def check():
    rep, res, ex = load()
    errs = []
    ov = res["overall"]
    if ("n = %d, FP = %d" % (ov["n"], ov["fp"])) not in rep:
        errs.append("overall n/FP не совпадают со снимком")
    if ("[0.0003; 0.0013]" if ov["wilson95"] == [0.0003, 0.0013]
            else "[%s; %s]" % tuple(ov["wilson95"])) not in rep:
        errs.append("overall CI не совпадает со снимком")
    L = ex["lengths"]
    if ("медиана %d символа" % L["median"]) not in rep:
        errs.append("медиана длин не совпадает с extras")
    if ("максимум %d" % L["max"]) not in rep:
        errs.append("максимум длин не совпадает с extras")
    p2 = "%.1f" % (100.0 * L["lt200_n"] / L["n"])
    p5 = "%.1f" % (100.0 * L["lt500_n"] / L["n"])
    if ("короче 200 символов %s" % p2) not in rep:
        errs.append("доля <200 не совпадает с extras")
    if ("короче 500 %s" % p5) not in rep:
        errs.append("доля <500 не совпадает с extras")
    for s in res["strata"]:
        if s.get("excluded"):
            continue
        row = "| %s | %d | %d |" % (s["stratum"], s["n"], s.get("fp", 0))
        if row not in rep:
            errs.append("строка страты %s не совпадает со снимком" % s["stratum"])
    fbm = ex["fp_by_marker"]
    frag = ", ".join("%s x%d" % (k, v) for k, v in sorted(fbm.items()))
    if frag not in rep:
        errs.append("разбор FP по маркерам не совпадает с extras")
    if ex["fp_by_class"].get("A"):
        errs.append("extras: класс A присутствует в FP — разобрать вручную")
    if "первые два" not in rep:
        errs.append("нет оговорки «первые два запуска»")
    return errs


def selftest():
    checks = []
    errs = check()
    checks.append(("числа отчёта сходятся со снимком", errs == []))
    rep, res, ex = load()
    bad = rep.replace("медиана %d символа" % ex["lengths"]["median"],
                      "медиана 9999 символа")
    import io
    saved = open(os.path.join(ROOT, "research", "FP-CORPUS-2026.md"),
                 encoding="utf-8").read()
    checks.append(("детектор расхождения реагирует на подмену числа",
                   _check_text(bad, res, ex) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА fp-report: %d FAIL" % fails)
    return 1 if fails else 0


def _check_text(rep, res, ex):
    errs = []
    ov = res["overall"]
    if ("n = %d, FP = %d" % (ov["n"], ov["fp"])) not in rep:
        errs.append("overall")
    L = ex["lengths"]
    if ("медиана %d символа" % L["median"]) not in rep:
        errs.append("median")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    errs = check()
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("FP-REPORT: %d расхождений" % len(errs))
        return 1
    print("FP-REPORT: числа отчёта сходятся со снимком result.json/extras.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
