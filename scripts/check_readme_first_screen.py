#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_readme_first_screen.py — гейт W4: первые 40 строк README содержат
слоган, hero, не более трёх бейджей, слово «демо» и pip install; структура
первого экрана совпадает по схеме в RU и EN. Selftest с негативом."""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read().split("\n")


def check(lines_ru=None, lines_en=None):
    errs = []
    ru = lines_ru if lines_ru is not None else read("README.md")
    en = lines_en if lines_en is not None else read("README.en.md")
    head_ru = ru[:40]
    head_en = en[:40]
    pos = None
    with open(os.path.join(ROOT, "POSITIONING.md"), encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("## Короткая формула (RU"):
                continue
    short_ru = None
    with open(os.path.join(ROOT, "POSITIONING.md"), encoding="utf-8") as fh:
        txt = fh.read()
    m = re.search(r"## Короткая формула \(RU, <= 60 символов\)\n([^\n]+)\n", txt)
    short_ru = m.group(1).strip() if m else None
    m = re.search(r"## Короткая формула \(EN\)\n([^\n]+)\n", txt)
    short_en = m.group(1).strip() if m else None
    if short_ru not in head_ru:
        errs.append("README.md: слоган не во первых 40 строках")
    if short_en not in head_en:
        errs.append("README.en.md: слоган EN не во первых 40 строках")
    if not any("assets/hero.svg" in ln for ln in head_ru):
        errs.append("README.md: hero.svg не во первых 40 строках")
    badges = [ln for ln in head_ru if ln.startswith("[![")]
    if len(badges) > 3:
        errs.append("README.md: больше трёх бейджей на первом экране")
    if not any("демо" in ln.lower() for ln in head_ru):
        errs.append("README.md: нет слова «демо» на первом экране")
    if not any("pip install" in ln for ln in head_ru):
        errs.append("README.md: нет pip install на первом экране")
    if not any("pip install" in ln for ln in head_en):
        errs.append("README.en.md: нет pip install на первом экране")
    ru_text = "\n".join(ru)
    en_text = "\n".join(en)
    ru_lim = ru_text.find("## Цифры проекта")
    en_lim = en_text.find("## Project in numbers")
    for need in ("## Кому это нужно", "## Попробовать за 30 секунд",
                 "## Что это НЕ делает", "## Почему можно доверять"):
        pos = ru_text.find(need)
        if pos == -1 or (ru_lim != -1 and pos > ru_lim):
            errs.append("README.md: нет секции %s в первом экране" % need)
    for need in ("## Who needs it", "## Try it in 30 seconds",
                 "## What it does NOT do", "## Why you can trust it"):
        pos = en_text.find(need)
        if pos == -1 or (en_lim != -1 and pos > en_lim):
            errs.append("README.en.md: нет секции %s в первом экране" % need)
    return errs


def selftest():
    checks = [("первый экран RU и EN по схеме", check() == [])]
    ru = read("README.md")
    bad = [ln for ln in ru if "assets/hero.svg" not in ln]
    checks.append(("без hero гейт падает", check(bad, None) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА readme-first-screen: %d FAIL" % fails)
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
        print("README-FIRST-SCREEN: %d расхождений" % len(errs))
        return 1
    print("README-FIRST-SCREEN: первый экран по схеме")
    return 0


if __name__ == "__main__":
    sys.exit(main())
