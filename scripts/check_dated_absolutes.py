#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_dated_absolutes.py — датированные абсолюты (приказ 2026-09-05):
в docs/THREAT-MODEL.md слова «ноль/нулевой/всегда/никогда» (кроме термина
«нулевой ширины» и производных) допускаются только с датой или источником
в той же строке либо в соседней: 20YY, [bib:*], (FNN), ссылка на реестр.
Selftest с негативами."""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "docs", "THREAT-MODEL.md")
ABS_RX = re.compile(r"\b(?:нол\w*|нул\w*|всегда|никогда)\b", re.I)
TERM_RX = re.compile(r"нулев\w*\s+(?:ширины|высоты|длины)", re.I)
EVID_RX = re.compile(r"20\d{2}|\[bib:[A-Za-z0-9_]+\]|\(F\d+|реестр|Wilson")


def check_lines(lines):
    errs = []
    for i, ln in enumerate(lines):
        bare = ln
        # термин «нулевой ширины» — не абсолют
        stripped = TERM_RX.sub("", bare)
        if not ABS_RX.search(stripped):
            continue
        ctx = " ".join(lines[max(0, i - 1):i + 2])
        if not EVID_RX.search(ctx):
            errs.append("строка %d: абсолют «%s» без даты и источника: %s"
                        % (i + 1, ABS_RX.search(stripped).group(0),
                           ln.strip()[:80]))
    return errs


def check(path=None):
    with open(path or TARGET, encoding="utf-8") as fh:
        return check_lines(fh.read().split("\n"))


def selftest():
    checks = [
        ("THREAT-MODEL: абсолюты датированы", check() == []),
        ("абсолют без даты ловится", check_lines(
            ["снятие следов с нулём ложных срабатываний"]) != []),
        ("абсолют с датой проходит", check_lines(
            ["0 FP (F16, замер 2026-09-04): ноль флагов класса A"]) == []),
        ("термин нулевой ширины не ловится", check_lines(
            ["Невидимые символы нулевой ширины снимаются по классам"]) == []),
    ]
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА dated-absolutes: %d FAIL" % fails)
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
        print("DATED-ABSOLUTES: %d абсолютов без даты или источника" % len(errs))
        return 1
    print("DATED-ABSOLUTES: абсолюты THREAT-MODEL датированы")
    return 0


if __name__ == "__main__":
    sys.exit(main())
