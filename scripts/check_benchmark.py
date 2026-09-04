#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_benchmark.py — гейт W9: числа публичной бенчмарк-страницы равны
снимку research/benchmark-<date>/results.json; источники существуют;
selftest с негативом."""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    bd = os.path.join(ROOT, "demo", "benchmark", "index.html")
    page = open(bd, encoding="utf-8").read()
    rd = sorted(d for d in os.listdir(os.path.join(ROOT, "research"))
                if d.startswith("benchmark-"))
    if not rd:
        return page, None, []
    res = json.load(open(os.path.join(ROOT, "research", rd[-1],
                                      "results.json"), encoding="utf-8"))
    return page, res, rd


def check(page=None, res=None):
    if page is None or res is None:
        page, res, _ = load()
        if res is None:
            return ["нет снимка бенчмарка в research/"]
    errs = []
    for row in res["rows"]:
        if str(row["value"]) not in page:
            errs.append("значение метрики %s отсутствует на странице" % row["id"])
        if row["ci95"] and ("[%s; %s]" % tuple(row["ci95"])) not in page:
            errs.append("интервал метрики %s отсутствует на странице" % row["id"])
        if not os.path.isfile(os.path.join(ROOT, row["source"])):
            errs.append("источник %s не существует" % row["source"])
    if "Как обмануть humanizer-ru" not in page:
        errs.append("нет абзаца «Как обмануть humanizer-ru»")
    if "Конкуренты" not in page:
        errs.append("нет раздела конкурентов")
    return errs


def selftest():
    checks = [("страница бенчмарка сходится со снимком", check() == [])]
    page, res, _ = load()
    bad = page.replace(str(res["rows"][0]["value"]), "0.9999", 1)
    checks.append(("подмена значения ловится", check(bad, res) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА benchmark: %d FAIL" % fails)
    return 1 if fails else 0


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
        print("BENCHMARK: %d расхождений" % len(errs))
        return 1
    print("BENCHMARK: страница сходится со снимком")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
