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

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

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


# Разметка markdown, которую снимает --skip-markup. Нужна, чтобы мерить
# прозаический стиль собственных файлов проекта: в них списки, заголовки и
# жирный — техническая структура документа, а не стилевые нарушения автора.
_FENCED_RX = re.compile(r"(?ms)^[ \t]*(?:```|~~~).*?(?:^[ \t]*(?:```|~~~)[ \t]*$|\Z)")
_INLINE_CODE_RX = re.compile(r"`[^`\n]*`")
_TABLE_ROW_RX = re.compile(r"(?m)^[ \t]*\|.*$")
_LINK_RX = re.compile(r"\[([^\]\n]*)\]\((?:[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_BARE_URL_RX = re.compile(r"(?i)\bhttps?://\S+")
_HEADER_MARK_RX = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+")
_BULLET_MARK_RX = re.compile(r"(?m)^([ \t]*)(?:[-*•]|\d+\.)[ \t]+")
_BOLD_RX = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC_RX = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def strip_markup(text):
    """Убирает разметку markdown, оставляя прозаический текст.

    Снимаются: блоки кода, инлайн-код, строки таблиц, адресная часть ссылок,
    маркеры заголовков и списков, звёздочки выделения. Видимый текст ссылок и
    выделений сохраняется — «важно отметить» в жирном остаётся словом-подушкой.
    """
    text = _FENCED_RX.sub("", text)
    text = _TABLE_ROW_RX.sub("", text)
    text = _INLINE_CODE_RX.sub("", text)
    text = _LINK_RX.sub(r"\1", text)
    text = _BARE_URL_RX.sub("", text)
    text = _HEADER_MARK_RX.sub("", text)
    text = _BULLET_MARK_RX.sub(r"\1", text)
    text = _BOLD_RX.sub(r"\1", text)
    text = _ITALIC_RX.sub(r"\1", text)
    return text


def main(paths, skip_markup=False):
    if not paths:
        print("нет входных файлов", file=sys.stderr)
        return 2
    if skip_markup:
        print("# режим --skip-markup: разметка markdown снята, считается только проза")
    print("file\t" + "\t".join(COLS) + "\ttotal")
    grand = 0
    for p in paths:
        try:
            with io.open(p, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            print("ошибка чтения %s: %s" % (p, exc), file=sys.stderr)
            return 2
        c = count_text(strip_markup(raw) if skip_markup else raw)
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

    # --skip-markup: структура документа не должна попадать в стилевой счёт,
    # а проза внутри разметки — должна.
    md = (u"# Заголовок\n\n"
          u"- первый пункт\n- второй пункт\n\n"
          u"| столбец | значение |\n|---|---|\n| a | b |\n\n"
          u"```python\n# важно отметить в коде\nx = 1\n```\n\n"
          u"См. [документацию](https://example.org/важно-отметить).\n\n"
          u"**Важно отметить**, что текст остаётся прозой.\n"
          u"Встрочный `код` и обычная фраза.\n")
    raw_counts = count_text(md)
    skipped = count_text(strip_markup(md))
    checks += [
        ("skip: заголовки обнулены", skipped["headers"] == 0 and raw_counts["headers"] >= 1),
        ("skip: списки обнулены", skipped["bullets"] == 0 and raw_counts["bullets"] >= 2),
        ("skip: жирный обнулён", skipped["bold"] == 0 and raw_counts["bold"] >= 1),
        ("skip: слово-подушка в прозе сохраняется", skipped["pillow"] >= 1),
        ("skip: слово-подушка из блока кода не считается",
         skipped["pillow"] < raw_counts["pillow"]),
        ("skip: строки таблицы не считаются",
         u"столбец" not in strip_markup(md)),
        ("skip: адрес ссылки убран, видимый текст остался",
         u"example.org" not in strip_markup(md)
         and u"документацию" in strip_markup(md)),
        ("skip: обычный текст не портится",
         count_text(strip_markup(good)) == cg),
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
    skip = "--skip-markup" in args
    sys.exit(main([a for a in args if not a.startswith("--")], skip_markup=skip))
