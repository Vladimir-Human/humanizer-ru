#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Объективный подсчёт стилевых нарушений для A/B-теста PERSONA.md (issue #19).

Один ответ модели = один текстовый файл. Считает:
  bullets  - строки-элементы списков        emdash  - длинные тире U+2014
  parens   - уточнения в скобках           neb     - оборот «А — это не Б, а В»
  intro    - шаблонные вступления          pillow  - слова-подушки
  bureau   - канцелярит                    emoji   - эмодзи
  headers  - markdown-заголовки              bold    - жирный **...**

Запуск:
    python3 scripts/count_style_markers.py файл1.txt файл2.txt ...
    python3 scripts/count_style_markers.py --selftest
Вывод: TSV-строка на файл + итог. Коды: 0 - ok, 1 - провал самопроверки, 2 - ошибка входа.
"""
import io
import re
import sys

PATTERNS = {
    "bullets": re.compile(r"(?m)^\s*(?:[-*\u2022]|\d+\.)\s+"),
    "emdash": re.compile("\u2014"),
    "parens": re.compile(r"\([^)]{3,}\)"),
    "neb": re.compile("\u2014\\s*(?:\u044d\u0442о\\s+)?\u043dе\\s+[^,.;]{1,60},\\s*\u0430\\s+"),
    "intro": re.compile("(?i)(\u043eтличный \u0432опрос|\u0445ороший \u0432опрос|\u0432ы \u043fравы|\u043aонечно!)"),
    "pillow": re.compile("(?i)(\u0432ажно \u043eтметить|\u0441тоит \u043fодчеркнуть|\u0441ледует \u043eтметить|\u0431езусловно|\u0432 \u0446елом)"),
    "bureau": re.compile("(?i)\\b(\u044fвляется|\u043fредставляет \u0441обой|\u043eсуществл\u044f\\w+|\u0434анн(?:\u044bй|\u0430я|\u043eе|\u044bе)|\u0432 \u0440амках)\\b"),
    "emoji": re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]"),
    "headers": re.compile(r"(?m)^#{1,6}\s"),
    "bold": re.compile(r"\*\*[^*]+\*\*"),
}
COLS = list(PATTERNS)


def count_text(text):
    return {k: len(rx.findall(text)) for k, rx in PATTERNS.items()}


def main(paths):
    if not paths:
        print("нет входных файлов", file=sys.stderr)
        return 2
    print("file\t" + "\t".join(COLS) + "\ttotal")
    grand = 0
    for p in paths:
        try:
            with io.open(p, encoding="utf-8") as fh:
                c = count_text(fh.read())
        except OSError as exc:
            print("ошибка чтения %s: %s" % (p, exc), file=sys.stderr)
            return 2
        total = sum(c.values())
        grand += total
        print(p + "\t" + "\t".join(str(c[k]) for k in COLS) + "\t" + str(total))
    print("# суммарно нарушений: %d" % grand)
    return 0


def selftest():
    bad = ("\u041eтличный \u0432опрос! \u0412ажно \u043eтметить, \u0447то \u0434анный \u043eтвет \u044fвляется \u043fолным.\n"
           "- \u043fункт\n- \u043fункт\n## \u0417аголовок\n**\u0436ирно** (\u0443точнение \u0432 \u0441кобках)\n"
           "\u0418И \u2014 \u044dто \u043dе \u0438грушка, \u0430 \u0438нструмент.\n")
    good = "\u041dе \u0443верен, \u043dо \u043fохоже, \u043eтвет \u043fростой: \u0434а.\n"
    cb, cg = count_text(bad), count_text(good)
    checks = [
        ("bad: вступление", cb["intro"] >= 1),
        ("bad: слово-подушка", cb["pillow"] >= 1),
        ("bad: канцелярит x2", cb["bureau"] >= 2),
        ("bad: два пункта списка", cb["bullets"] == 2),
        ("bad: заголовок", cb["headers"] == 1),
        ("bad: жирный", cb["bold"] == 1),
        ("bad: скобки", cb["parens"] == 1),
        ("bad: оборот не-Б-а-В", cb["neb"] == 1),
        ("good: ноль нарушений", sum(cg.values()) == 0),
    ]
    fails = [n for n, p in checks if not p]
    for n, p in checks:
        print(("PASS: " if p else "FAIL: ") + n)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    sys.exit(main(args))
