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

# Гомоглифная мутация двунаправленная: латиница->кириллица и
# кириллица->латиница, иначе оператор не меняет кириллический CLEAN и
# проверка границы становится вакуумной (дефект пойман 2026-09-07).
HOMO = {"a": "а", "e": "е", "o": "о", "c": "с", "x": "х", "y": "у",
        "A": "А", "E": "Е", "O": "О", "C": "С", "X": "Х", "Y": "У",
        "а": "a", "е": "e", "о": "o", "с": "c", "х": "x", "у": "y",
        "А": "A", "Е": "E", "О": "O", "С": "C", "Х": "X", "У": "Y"}


def _mut(kind, s, rng):
    if kind == "homoglyph":
        return "".join(HOMO.get(ch, ch) for ch in s)
    if kind == "zero-width":
        return s[:3] + "\u200b" + s[3:]
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
    for kind in ("homoglyph", "punctuation", "linebreak",
                 "nfc-nfkc", "translit", "word-smart", "html-convert",
                 "telegram-pdf"):
        checks.append(("мутация без артефактов не создаёт находок: %s" % kind,
                       not _hits(_mut(kind, CLEAN, rng))))
    checks.append(("zero-width мутация ловится (невидимый = артефакт)",
                   _hits(_mut("zero-width", CLEAN, rng))))
    # Оператор мутации обязан фактически менять применимый вход: пустая
    # мутация не проверяет границу (дефект гомоглифной таблицы пойман
    # 2026-09-07: таблица латиница->кириллица не меняла кириллический
    # CLEAN). Применимый вход для каждого оператора — свой зонд.
    probes = {
        "homoglyph": CLEAN,
        "punctuation": "Источник: живой текст без артефактов.",
        "linebreak": CLEAN,
        "nfc-nfkc": "и\u0306 живой текст без артефактов.",
        "translit": "живой текст code слово",
        "word-smart": "живой текст \"цитата\" слово",
        "html-convert": "живой текст & слово",
        "zero-width": CLEAN,
        "telegram-pdf": "живой  текст с двойным пробелом",
    }
    for kind, probe in probes.items():
        mut = _mut(kind, probe, rng)
        checks.append(("мутация %s фактически меняет применимый вход" % kind,
                       mut != probe))
        if kind != "zero-width":
            checks.append(("мутация %s применимого входа не создаёт "
                           "находок" % kind, not _hits(mut)))
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
