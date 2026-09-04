#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_marker_lr.py — гейт F17: сверка чисел research/MARKER-LR-2026.md
со снимком research/marker-lr-2026-09/result.json (selftest с негативом)."""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG = os.path.join(ROOT, "research", "marker-lr-2026-09")


def load():
    rep = open(os.path.join(ROOT, "research", "MARKER-LR-2026.md"),
               encoding="utf-8").read()
    res = json.load(open(os.path.join(AGG, "result.json"), encoding="utf-8"))
    return rep, res


def check(rep, res):
    errs = []
    for name, r in res["markers"].items():
        lr = ("%.4f" % r["lr_lower"]) if r["lr_lower"] is not None else "-"
        frag = "| `%s` | %s | %.6f |" % (name, r["class"], r["p1"])
        if frag not in rep:
            errs.append("строка маркера %s не совпадает со снимком" % name)
        if lr != "-" and lr not in rep:
            errs.append("LR_lower маркера %s не найден в отчёте" % name)
    return errs


def selftest():
    rep, res = load()
    checks = [("числа отчёта сходятся со снимком", check(rep, res) == [])]
    bad = rep.replace("| `zero_width` |", "| `zero_width_X` |", 1)
    checks.append(("детектор реагирует на подмену строки",
                   check(bad, res) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА marker-lr: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    rep, res = load()
    errs = check(rep, res)
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("MARKER-LR: %d расхождений" % len(errs))
        return 1
    print("MARKER-LR: числа отчёта сходятся со снимком")
    return 0


if __name__ == "__main__":
    sys.exit(main())
