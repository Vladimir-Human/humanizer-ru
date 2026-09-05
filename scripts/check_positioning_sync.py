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


FORBIDDEN_SHORT = ("regex", "stdlib", "CLI", "слой", "сканер")


def forbidden_in(text):
    """Слова, запрещённые в короткой формуле позиционирования
    (POSITIONING.md: «regex, stdlib, CLI, слой, сканер — не используются»).
    Регистр учитывается для аббревиатур, остальные — регистронезависимо."""
    hits = []
    for w in FORBIDDEN_SHORT:
        if w in ("regex", "stdlib", "слой", "сканер"):
            if w.lower() in text.lower():
                hits.append(w)
        elif w in text:
            hits.append(w)
    return hits


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def check_formula_words(pos_text=None):
    """Короткая формула не содержит запрещённых слов (regex, stdlib, CLI,
    слой, сканер) — POSITIONING.md:39 заявляет это как проверенное гейтом."""
    errs = []
    if pos_text is None:
        with open(os.path.join(ROOT, "POSITIONING.md"), encoding="utf-8") as fh:
            pos_text = fh.read()
    import re
    for label, pat in (("RU", r"## Короткая формула \(RU[^)]*\)\n([^\n]+)"),
                       ("EN", r"## Короткая формула \(EN\)\n([^\n]+)")):
        m = re.search(pat, pos_text)
        if not m:
            errs.append("POSITIONING: короткая формула %s не найдена" % label)
            continue
        hits = forbidden_in(m.group(1))
        if hits:
            errs.append("POSITIONING: короткая формула %s содержит запрещённые "
                        "слова: %s" % (label, ", ".join(hits)))
    return errs


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
    formula_bad = check_formula_words(
        "## Короткая формула (RU, <= 60 символов)\nСканер слоя regex\n\n"
        "## Короткая формула (EN)\nFinds machine-text traces\n")
    checks.append(("запрещённые слова в формуле ловятся", formula_bad != []))
    formula_ok = check_formula_words(
        "## Короткая формула (RU, <= 60 символов)\nНаходит следы машинного "
        "текста в русском и объясняет их вам\n\n"
        "## Короткая формула (EN)\nFinds machine-text traces in Russian and "
        "explains them\n")
    checks.append(("чистая формула проходит проверку слов", formula_ok == []))
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
    errs = check() + check_formula_words()
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("POSITIONING-SYNC: %d расхождений" % len(errs))
        return 1
    print("POSITIONING-SYNC: формулы дословно во всех поверхностях")
    return 0


if __name__ == "__main__":
    sys.exit(main())
