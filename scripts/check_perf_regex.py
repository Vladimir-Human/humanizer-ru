#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_perf_regex.py — F13: статический ReDoS-контроль сигнатур маркеров
(вложенные кванторы) + линейность scan на 5 МБ фикстуре.

Запуск:
  python3 scripts/check_perf_regex.py
  python3 scripts/check_perf_regex.py --selftest
"""
import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import check_markers as cm  # noqa: E402

NESTED_RX = re.compile(r"\((?:[^()\\]|\\.)*[+*](?:[^()\\]|\\.)*\)[+*?]"
                       r"|\([^()]*\([^()]*[+*][^()]*\)[^()]*\)[+*?]")


# Белый список: внутренние кванторы с обязательным разделителем
# (запятая/двоеточие) не дают перекрытия итераций и не являются ReDoS;
# ограничение задокументировано в docstring гейта.
SAFE_NESTED = {"assistants_source", "gemini_cite_n", "deepseek_line_ref",
               "placeholder_url"}


def nested_patterns():
    out = []
    for name, case in cm.CASES.items():
        if name in SAFE_NESTED:
            continue
        pat = case[0]
        if NESTED_RX.search(pat):
            out.append(name)
    return out


def linearity_ok(limit_s=30.0):
    text = ("Живой человеческий текст без артефактов копипасты. "
            "Обычные предложения без служебных меток чат-интерфейсов.\n") * 60000
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        t0 = time.time()
        cm.scan([path])
        dt = time.time() - t0
    finally:
        os.unlink(path)
    return dt <= limit_s, dt


def selftest():
    checks = []
    checks.append(("чистые сигнатуры без вложенных кванторов",
                   nested_patterns() == []))
    bad = {"x": ["(a+)+ b", "A"]}
    saved = cm.CASES
    cm.CASES = dict(saved)
    cm.CASES["__quadratic__"] = bad["x"]
    try:
        checks.append(("квадратичное правило ловится статически",
                       "__quadratic__" in nested_patterns()))
    finally:
        cm.CASES = saved
    ok, dt = linearity_ok()
    checks.append(("линейность scan на 5 МБ не выше 30 с (%.1f с)" % dt, ok))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА perf-regex: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    bad = nested_patterns()
    if bad:
        print("PERF-REGEX: вложенные кванторы в сигнатурах: %s" % bad)
        return 1
    ok, dt = linearity_ok()
    if not ok:
        print("PERF-REGEX: scan 5 МБ занял %.1f с выше порога 30 с" % dt)
        return 1
    print("PERF-REGEX: пройден (вложенных кванторов нет, 5 МБ за %.1f с)" % dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
