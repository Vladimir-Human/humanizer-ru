#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_report.py — гейт F2: selftest отчёта правки humanizer-report.

Негативы: идентичная пара даёт нули; пара с изменённым фактом авторской
категории помечается facts.unchanged = False. Позитив: известная пара
даёт ожидаемые счётчики токенов и классов.
"""
import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from humanizer_ru import edit_report as er  # noqa: E402

BEFORE = ("Текст с меткой :" + "contentReference" + "[oaicite:" + "1]{index=1} "
          "и невидимым \u200b символом.\n"
          "Вторая строка с  двойным пробелом.\n")
AFTER = ("Текст с меткой и невидимым символом.\n"
         "Вторая строка с двойным пробелом.\n")


def _pair(before, after):
    d = tempfile.mkdtemp()
    b = os.path.join(d, "b.txt")
    a = os.path.join(d, "a.txt")
    with open(b, "w", encoding="utf-8") as fh:
        fh.write(before)
    with open(a, "w", encoding="utf-8") as fh:
        fh.write(after)
    return b, a


def selftest():
    checks = []
    b, a = _pair(BEFORE, AFTER)
    env = er.report(b, a)
    f = env["files"][0]
    checks.append(("delete равен 2 на известной паре",
                   f["tokens"]["delete"] == 2))
    checks.append(("невидимый класс учтён", f["edit_types"]["invisible"] >= 1))
    checks.append(("пробельный класс учтён", f["edit_types"]["whitespace"] >= 1))
    checks.append(("факты не потеряны на чистой паре", f["facts"]["unchanged"]))
    b2, a2 = _pair(BEFORE, BEFORE)
    f2 = er.report(b2, a2)["files"][0]
    checks.append(("идентичная пара даёт нули",
                   f2["tokens"]["add"] == 0 and f2["tokens"]["delete"] == 0
                   and f2["sari_adapted"]["keep"] == 1.0))
    b3, a3 = _pair("В отчёте 25 таблиц и 3 вывода.\n",
                   "В отчёте 26 таблиц и 3 вывода.\n")
    f3 = er.report(b3, a3)["files"][0]
    checks.append(("изменённый факт помечается", not f3["facts"]["unchanged"]))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА report: %d FAIL" % fails)
    return 1 if fails else 0


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
