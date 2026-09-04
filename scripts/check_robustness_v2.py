#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_robustness_v2.py — гейт F3v2: сверка чисел отчёта
research/ADVERSARIAL-ROBUSTNESS-V2-2026.md со снимком
research/adversarial-2026-09/result.json (selftest с негативом подмены)."""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG = os.path.join(ROOT, "research", "adversarial-2026-09")


def load():
    rep = open(os.path.join(ROOT, "research",
                            "ADVERSARIAL-ROBUSTNESS-V2-2026.md"),
               encoding="utf-8").read()
    res = json.load(open(os.path.join(AGG, "result.json"), encoding="utf-8"))
    return rep, res


def check(rep, res):
    errs = []
    sa = res["self_attack_remove"]
    if ("%s -> %s" % (sa["E_recall_before"], sa["E_recall_after_remove"])) \
            not in rep:
        errs.append("self-attack строка не совпадает со снимком")
    sw = res["skill_rewrite"]
    if ("n=%d пар" % sw["n"]) not in rep:
        errs.append("skill_rewrite n не совпадает со снимком")
    for op, row in res["retention"].items():
        frag = "| %s | %s |" % (op, row["d1"])
        if frag not in rep:
            errs.append("retention строка %s не совпадает со снимком" % op)
    for op, row in res["fpr_curve"].items():
        frag = "| %s | %s |" % (op, row["d1"])
        if frag not in rep:
            errs.append("fpr строка %s не совпадает со снимком" % op)
    return errs


def selftest():
    rep, res = load()
    checks = [("числа отчёта сходятся со снимком", check(rep, res) == [])]
    bad = rep.replace("zero-width |", "zero-width_X |", 1)
    checks.append(("детектор реагирует на подмену строки",
                   check(bad, res) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА robustness-v2: %d FAIL" % fails)
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
        print("ROBUSTNESS-V2: %d расхождений" % len(errs))
        return 1
    print("ROBUSTNESS-V2: числа отчёта сходятся со снимком")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
