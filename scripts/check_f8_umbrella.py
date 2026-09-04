#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_f8_umbrella.py — гейт П3: сверка чисел отчётов F8-UMBRELLA и
METRICS со снимком result.json + присутствие формулировки П6 в четырёх
носителях (FP-CORPUS, METRICS, README, llms.txt). Selftest с негативом."""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG = os.path.join(ROOT, "research", "f8-2026-09")
P6_HEAD = "Классовая разбивка FP, exploratory"


def load():
    rep = open(os.path.join(ROOT, "research", "F8-UMBRELLA-2026.md"),
               encoding="utf-8").read()
    met = open(os.path.join(ROOT, "research", "METRICS.md"),
               encoding="utf-8").read()
    res = json.load(open(os.path.join(AGG, "result.json"), encoding="utf-8"))
    return rep, met, res


def check(rep, met, res):
    errs = []
    for k, v in res["f8c_auc"].items():
        frag = "| %s | %s |" % (k, v["auc"])
        if frag not in rep:
            errs.append("AUC строка %s не совпадает со снимком" % k)
    ov = res["f16b_fp"]["overall"]
    frag = "| overall | %d/%d |" % (ov["k"], ov["n"])
    if frag not in rep:
        errs.append("F16b overall не совпадает со снимком")
    for k, v in res["s5_recall"].items():
        frag = "| %s | %d/%d |" % (k, v["k"], v["n"])
        frag_bt = "| `%s` | %d/%d |" % (k, v["k"], v["n"])
        if frag not in rep and frag_bt not in rep:
            errs.append("S5 строка %s не совпадает со снимком" % k)
    for name, doc in (("FP-CORPUS", open(os.path.join(
            ROOT, "research", "FP-CORPUS-2026.md"), encoding="utf-8").read()),
            ("METRICS", met),
            ("README", open(os.path.join(ROOT, "README.md"),
                            encoding="utf-8").read()),
            ("llms", open(os.path.join(ROOT, "llms.txt"),
                          encoding="utf-8").read())):
        if P6_HEAD not in doc:
            errs.append("формулировка П6 отсутствует в %s" % name)
    return errs


def selftest():
    rep, met, res = load()
    checks = [("числа отчётов сходятся со снимком и П6 на месте",
               check(rep, met, res) == [])]
    bad = rep.replace("| overall |", "| overall_X |", 1)
    checks.append(("детектор реагирует на подмену строки",
                   check(bad, met, res) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА f8-umbrella: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    rep, met, res = load()
    errs = check(rep, met, res)
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("F8-UMBRELLA: %d расхождений" % len(errs))
        return 1
    print("F8-UMBRELLA: числа отчётов сходятся со снимком, П6 в четырёх носителях")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
