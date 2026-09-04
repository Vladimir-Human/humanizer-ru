#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_robustness.py — гейт F3: selftest устойчивости детекторного слоя.

Негатив: мутации чистого текста (все операторы предрега
f3-adversarial-prereg-2026-09, глубина 1) не создают находок классов A/B.
Позитив: немутрированные канонические образцы маркеров обнаруживаются.
Пороги recall кривой живут в предреге и отчёте
research/ADVERSARIAL-ROBUSTNESS-2026.md, гейт их не дублирует.

Запуск:
  python3 scripts/check_robustness.py --selftest
"""
import argparse
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "filemarks"))
import check_markers as cm  # noqa: E402

COMPILED_AB = {n: re.compile(c[0]) for n, c in cm.CASES.items()
               if cm.CLASS_OF.get(n) in ("A", "B")}

CLEAN = ("Живой человеческий текст без артефактов копипасты и служебных "
         "меток чат-интерфейсов. Обычные предложения, обычные слова.")

HOMO = {"a": "а", "e": "е", "o": "о", "c": "с", "x": "х", "y": "у"}


def _mut(kind, s, rng):
    if kind == "homoglyph":
        return "".join(HOMO.get(ch, ch) for ch in s)
    if kind == "zero-width":
        return s[:3] + "​" + s[3:]
    if kind == "punctuation":
        return s.replace(":", "：")
    if kind == "linebreak":
        return s[:5] + "\n" + s[5:]
    if kind == "nfc-nfkc":
        import unicodedata
        return unicodedata.normalize("NFKC", s)
    if kind == "translit":
        return s.replace("c", "к").replace("o", "о")
    if kind == "word-smart":
        return s.replace('"', "“")
    if kind == "html-convert":
        return s.replace("&", "&amp;")
    return s.replace("  ", " ")


def _hits(text):
    for line in text.splitlines():
        if cm._line_matches(line, COMPILED_AB):
            return True
    return False


def selftest():
    checks = []
    rng = random.Random(20260904)
    for kind in ("homoglyph", "zero-width", "punctuation", "linebreak",
                 "nfc-nfkc", "translit", "word-smart", "html-convert",
                 "telegram-pdf"):
        checks.append(("мутация чистого текста не создаёт находок: %s" % kind,
                       not _hits(_mut(kind, CLEAN, rng))))
    src = json_samples()
    pos = 0
    for name, sample in src.items():
        if _hits(sample):
            pos += 1
    checks.append(("канонические образцы обнаруживаются (%d/%d)"
                   % (pos, len(src)), pos == len(src) and pos > 0))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА robustness: %d FAIL" % fails)
    return 1 if fails else 0


def json_samples():
    import json
    fp = os.path.join(ROOT, "research", "fixtures", "marker-sources.json")
    out = {}
    for rec in json.load(open(fp, encoding="utf-8")):
        name = rec.get("case")
        sample = rec.get("verbatim_sample")
        if name and sample:
            out[name] = sample
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    print("гейт работает только в режиме --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
