#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_positioning_sync.py — гейт W1: короткая и длинная формулы
позиционирования присутствуют дословно во всех пользовательских поверхностях.

Поверхности: POSITIONING.md (источник), src/humanizer_ru/positioning.py,
pyproject description, README.md (вторая строка + абзац «Почему так
называется»), README.en.md (короткая EN), demo/index.html (title, h1,
meta description, og:title/og:description), server.json description,
CITATION.cff (title/abstract), первая строка описания --help у CLI
с argparse (scan_soft_signals, polish, detect_conj, facts_diff, edit_report).
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def formulas(pos_text):
    def grab(head):
        m = re.search(re.escape(head) + r"\n([^\n]+)\n", pos_text)
        return m.group(1).strip() if m else None
    return (grab("## Короткая формула (RU, <= 60 символов)"),
            grab("## Длинная формула (RU, <= 160 символов)"),
            grab("## Короткая формула (EN)"),
            grab("## Длинная формула (EN)"))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def check(pos_text=None):
    if pos_text is None:
        pos_text = read("POSITIONING.md")
    short_ru, long_ru, short_en, long_en = formulas(pos_text)
    errs = []
    if not (short_ru and long_ru and short_en and long_en):
        return ["POSITIONING.md: не все формулы найдены"]
    if len(short_ru) > 60 or len(long_ru) > 160:
        errs.append("POSITIONING.md: длины формул RU вне лимитов")
    py = read("src/humanizer_ru/positioning.py")
    if ('SHORT_RU = "%s"' % short_ru) not in py:
        errs.append("positioning.py: SHORT_RU расходится с POSITIONING.md")
    if ('LONG_RU = "%s"' % long_ru) not in py:
        errs.append("positioning.py: LONG_RU расходится с POSITIONING.md")
    pj = read("pyproject.toml")
    if ('description = "%s"' % short_ru) not in pj:
        errs.append("pyproject description не равен короткой формуле")
    ru = read("README.md")
    lines = ru.split("\n")
    if len(lines) < 2 or lines[1] != short_ru:
        errs.append("README.md: вторая строка не равна короткой формуле")
    if "Почему так называется" not in ru:
        errs.append("README.md: нет абзаца «Почему так называется»")
    en = read("README.en.md")
    if short_en not in en:
        errs.append("README.en.md: нет короткой формулы EN")
    demo = read("demo/index.html")
    if ("<title>%s</title>" % short_ru) not in demo:
        errs.append("demo title не равен короткой формуле")
    if long_ru not in demo:
        errs.append("demo meta/og description не содержит длинную формулу")
    sj = json.loads(read("server.json"))
    if long_ru not in str(sj.get("description", "")):
        errs.append("server.json description не содержит длинную формулу")
    cff = read("CITATION.cff")
    cff_flat = re.sub(r"\s+", " ", cff)
    if short_ru not in cff_flat:
        errs.append("CITATION.cff title не содержит короткую формулу")
    if long_ru not in cff_flat:
        errs.append("CITATION.cff abstract не содержит длинную формулу")
    for rel in ("scripts/scan_soft_signals.py", "scripts/polish.py",
                "scripts/detect_conj.py", "src/humanizer_ru/facts_diff.py",
                "src/humanizer_ru/edit_report.py"):
        r = subprocess.run([sys.executable, "-X", "utf8",
                            os.path.join(ROOT, rel), "--help"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        out = [ln for ln in (r.stdout or "").split("\n") if ln.strip()]
        desc = [ln for ln in out if ln.strip().startswith(short_ru)]
        if not desc:
            errs.append("%s: --help не несёт короткую формулу строкой" % rel)
    return errs


def selftest():
    checks = [("все поверхности несут формулы дословно", check() == [])]
    pos = read("POSITIONING.md")
    bad = pos.replace("объясняет их вам", "объясняет их кому-то")
    checks.append(("расхождение формулы ловится", check(bad) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА positioning-sync: %d FAIL" % fails)
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
        print("POSITIONING-SYNC: %d расхождений" % len(errs))
        return 1
    print("POSITIONING-SYNC: формулы дословно во всех поверхностях")
    return 0


if __name__ == "__main__":
    sys.exit(main())
