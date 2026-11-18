#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Compare an original Russian text with its edited version and report facts that
#          were lost, invented or rebound: numbers (with units, incl. prefix and suffix
#          currencies like $20, €50, £30, ¥100, 20 USD, 50 EUR; versions and IP addresses like
#          2.1.3, 10.0.10.1 as one token), dates (days, months without a day by their noun
#          endings, weekdays incl. single abbreviations like «с пн, 2 ноября»), times, names
#          (incl. США-type acronyms), URLs (host case and the slash after a bare host ignored),
#          phones (by digits), e-mails, quotes, `inline code`, negations (incl. "не на карту",
#          "нельзя" → "можно"), hedges (said another way, «около» → «примерно», «не свыше» →
#          «не более», they are kept; hedges that say the same are counted by mention, any other
#          hedge has to stay somewhere in the edit; bold and italic marks between a hedge and its
#          number do not hide it in either source or edit) and "who/what got which number" pairs
#          (a person may be named by first name or surname, and two people who share one of them
#          are told apart by the other; in a list inside one sentence the number belongs to the
#          name of its own clause between commas or unambiguous «и»-joined items, so swapped
#          amounts in «Анна получила 30 000, Борис 50 000 и Вера 7 000» are an error; names after
#          «от» or «через», incl. «от Бориса и Глеба», give the money, they do not get it; in
#          parallel item/product/tariff enumerations like «капучино 250 ₽, латте 300 ₽» or
#          «тариф Базовый — 500 ₽, тариф Про — 900 ₽» numbers swapped between two or more items
#          are also reported as a binding swap);
#          flags certainty, scope,
#          condition and attribution words that got rarer and intensifiers that got more frequent;
#          HTML tags of the original that were lost (emphasis tags only as checks).
#          Quoted words (up to a paragraph) must survive in order (case endings and quote marks
#          may change): lost direct speech, a quote after a colon or a line opening with a dash
#          and a quote (dialogue, interview answer; not a Markdown «- "…" …» bullet with prose
#          after the quote) is an error; other lost quoted words, words kept without their quote
#          marks and new quotes are checks. Checks also: a lost contrast negation ("а не в
#          феврале"), an added negation, "нельзя" → "можно" when the ban stayed as another
#          negation, a number that lost its unit or currency, a code-like ``` block that changed.
#          A word at the start of a sentence is a name only when the same name stands elsewhere
#          in another case ("Сбер" … "Сбера"): a shared prefix is not enough ("То" is not
#          "Томске"), a footnote or ГОСТ citation mark ("болота.[14, с. 52] Там") and a chat
#          citation between a word and a capital letter do not hide the sentence start.
#          A number written without a space before its unit ("500мл", "990р.", "2019г."), a
#          "к" meaning thousand ("30к", "$30к") and a dimension ("160х200" is "160 × 200") are
#          numbers with that unit; an uppercase letter after the digits ("3D", "1С") is not a unit.
#          A mention of a number that is gone together with its own unit ("скидка 5%", "$20") is a
#          lost fact, not a rarer one.
#          A hedge turned the other way ("не менее 5" → "не более 5", "не свыше 5" → "свыше 5",
#          "после 20 мая" → "до 20 мая") is an error; the same hedge said in other words
#          ("минимум", "не позже") is not. Dates are compared by their hedge too.
#          "Вместо того чтобы купить" is the same refusal as "не покупать": a check, not an
#          inverted negation.
#          A run of 16 digits or more (a bank account) is compared as it is written.
#          The values of the chat assistant's own lines around the text ("Готово, вот текст:",
#          parenthetical length notes like "(≈253 знака…)", "Если нужно, могу…", clarification
#          tails) are not errors: they are reported apart, as removed together with the service lines.
#          Links are compared without the chat assistant's utm_source tail only: a lost
#          author utm tag is a lost link. The source and the edit are both read without chat
#          citation tokens, invisible characters and mixed-script Cyrillic/Latin homoglyphs (the
#          set clean_paste.py repairs), and a dot "time" that the other side writes as a decimal
#          of the same digits is that number; compound number-unit adjectives («шестилетний»,
#          «6-летний») are numbers with their unit, and a negation merged into the prefix «не-»
#          («без больших» → «небольшими») is kept.
# SCOPE: heuristic, offline, stdlib only. Errors are likely real; "check" items need a human look.
#        An empty report does not prove the meaning is intact.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CHECK-FACTS; R-FACTS; R-RECEIPT; R-DETECTOR-RISK; DF-SKILL; V-M-CHECK-FACTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# extract: text -> Facts (numbers with units/currencies, dates, urls, names, quotes, negations, hedges, sentences).
# clause_spans / list_clauses / clause_span / is_list: comma/semicolon and unambiguous «и»-joined
#          clauses of a sentence, the clause around an offset, and whether the sentence lists
#          parallel items (at least two clauses, each one person and a number).
# compare: (before, after) -> {"errors": [...], "checks": [...], "service": [...], "counts": {...}};
#          markup block counts HTML tags;
#          quotes block matches quoted words in order; bindings block pairs numbers with names
#          (clause by clause when a sentence names several people).
# _service_spans: the parts of the source that are the chat assistant's own lines (head, tail,
#          parenthetical length notes), with the guards that keep a real fact an error.
# render: human-readable Russian report.
# receipt: the «Сверка скриптом: …» notes line the skill copies word for word; receipt_hint frames it.
# main: CLI `check_facts.py before.txt after.txt [--json]`; exit 0 clean, 1 errors, 2 bad input.
# END_MODULE_MAP
"""Сверка фактов до и после правки.

    python check_facts.py до.txt после.txt          # отчёт по-русски
    python check_facts.py до.txt после.txt --json   # то же в JSON
    python check_facts.py - после.txt               # исходник из stdin

В конце отчёта — готовая строка для заметок «Сверка скриптом: …».
Код выхода: 0 — ошибок нет, 1 — есть ошибки, 2 — файл не читается.
"""
from __future__ import annotations

import bisect
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# START_BLOCK_LEXICON
SEP = " \u00a0\u202f"
UNIT_SYNONYMS = [
    (("%", "процент", "процента", "процентов", "процентам", "процентами"), "%"),
    (("₽", "р.", "руб.", "руб", "rub", "rur", "рубль", "рубля", "рублей", "рублю", "рублями", "рублях"), "₽"),
    (("$", "usd", "долл.", "долл", "доллар", "доллара", "долларов", "доллару", "долларом", "долларами", "долларах"), "$"),
    (("€", "eur", "евро"), "€"),
    (("£", "gbp", "фунт стерлингов", "фунта стерлингов", "фунтов стерлингов"), "£"),
    (("фунт", "фунта", "фунтов", "фунту", "фунтом", "фунтами", "фунтах"), "фунт"),
    (("¥",), "¥"),
    (("jpy", "иена", "иены", "иен", "иене", "иену", "иеной", "иенами", "иенах",
      "йена", "йены", "йен", "йене", "йену", "йеной", "йенами", "йенах"), "JPY"),
    (("cny", "юань", "юаня", "юаней", "юаню", "юанем", "юанями", "юанях"), "CNY"),
    (("кг", "килограмм", "килограмма", "килограммов"), "кг"),
    (("г", "грамм", "грамма", "граммов"), "г"),
    (("км", "километр", "километра", "километров"), "км"),
    (("м", "метр", "метра", "метров"), "м"),
    (("кв. м", "кв.м", "м²", "квадратных метров", "квадратных метра"), "м²"),
    (("см", "сантиметр", "сантиметра", "сантиметров"), "см"),
    (("мм", "миллиметр", "миллиметра", "миллиметров"), "мм"),
    (("л", "литр", "литра", "литров"), "л"),
    (("мл", "миллилитр", "миллилитра", "миллилитров"), "мл"),
    (("шт", "штука", "штуки", "штук"), "шт"),
    (("ч", "час", "часа", "часов"), "ч"),
    (("мин", "минута", "минуты", "минут"), "мин"),
    (("мс", "миллисекунда", "миллисекунды", "миллисекунд"), "мс"),
    (("сек", "с", "секунда", "секунды", "секунд"), "с"),
    (("день", "дня", "дней", "дн", "сутки", "суток", "суткам", "сутками", "сутках"), "дн"),
    (("неделя", "недели", "недель", "нед"), "нед"),
    (("месяц", "месяца", "месяцев", "мес"), "мес"),
    (("год", "года", "лет"), "год"),
    (("человек", "человека", "чел"), "чел"),
    (("ГБ", "гигабайт", "гигабайта", "гигабайтов"), "ГБ"),
    (("МБ", "мегабайт", "мегабайта"), "МБ"),
    (("°C", "°С", "градус", "градуса", "градусов"), "°C"),
]
UNIT_CANON = {s.lower(): c for syns, c in UNIT_SYNONYMS for s in syns}
UNIT_RX = re.compile(r"[ \u00a0\u202f]?(%s)(?![0-9A-Za-zА-Яа-яЁё])" % "|".join(
    sorted((re.escape(u) for u in UNIT_CANON), key=len, reverse=True)), re.I)
# A unit written right after the digits ("500мл", "990р.", "2019г.", "20USD"): only the lower-case
# spellings of the table and 3-letter ISO currency codes, with a non-letter after them, so "3D"
# and "1С" are not numbers with a unit. The scale "к" ("30к" = "30 тыс.") and the dimension "х"
# ("160х200" = "160 × 200") are read apart.
GLUED_UNITS = ("%", "₽", "р.", "руб.", "руб", "$", "€", "£", "¥", "долл.", "долл", "евро",
               "фунт", "фунта", "фунтов", "иен", "йен", "юаней",
               "USD", "EUR", "GBP", "RUB", "RUR", "JPY", "CNY",
               "кг", "г", "км", "м²", "м", "см", "мм", "л",
               "мл", "шт", "ч", "мин", "мс", "сек", "с", "день", "дня", "дней", "дн", "сутки",
               "неделя", "недели", "недель", "нед", "месяц", "месяца", "месяцев", "мес", "год",
               "года", "лет", "человек", "человека", "чел")
GLUED_UNIT_RX = re.compile(r"(%s)(?![0-9A-Za-zА-Яа-яЁё²³])" % "|".join(
    sorted((re.escape(u) for u in GLUED_UNITS), key=len, reverse=True)))
PREFIX_CURR_RX = re.compile(r"(?:(?<![\w.,])([+\-−]))?([$€£¥₽])[ \u00a0\u202f]*$")
PREFIX_TIME_CURR_RX = re.compile(r"[$€£¥₽][ \u00a0\u202f]*[+\-−]?$")
DIM_RX = re.compile(r"[хx](\d+(?:[%s]\d{3})*(?:[.,]\d+)?)" % SEP)
# A capitalised word of the text: the shape the names are read with.
NAME_RX = re.compile(r"(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*|[А-ЯЁ]{2,4}(?![\w-]))")

WORD_NUM = {
    # "один/одна/одного" are left out on purpose: "одна из причин" is not a number.
    "ноль": 0, "два": 2, "две": 2, "двух": 2, "трое": 3, "двое": 2, "три": 3, "трех": 3,
    # The other cases of "два": "нужны двоим из семи" is the same fact as "касались двух
    # человек из семи".
    "двоим": 2, "двоих": 2,
    "четыре": 4, "четырех": 4, "четверо": 4, "пять": 5, "пяти": 5, "пятеро": 5, "шесть": 6,
    "шести": 6, "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
    "десять": 10, "десяти": 10, "одиннадцать": 11, "двенадцать": 12, "пятнадцать": 15,
    "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "сто": 100, "двести": 200, "триста": 300,
    "полтора": 1.5, "полторы": 1.5, "полутора": 1.5, "половина": 0.5, "половину": 0.5,
    "одиннадцати": 11, "двенадцати": 12, "тринадцать": 13, "тринадцати": 13, "четырнадцать": 14,
    "четырнадцати": 14, "пятнадцати": 15, "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17,
    "семнадцати": 17, "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19,
    "девятнадцати": 19, "сорока": 40, "пятидесяти": 50, "шестидесяти": 60, "семьдесят": 70,
    "семидесяти": 70, "восемьдесят": 80, "восьмидесяти": 80, "девяносто": 90, "девяноста": 90,
    "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800,
    "девятьсот": 900,
    # «вдвое дешевле» is «в 2 раза дешевле» (final2 chukovsky n20 was a false «lost 2»).
    "вдвое": 2, "втрое": 3, "вчетверо": 4, "впятеро": 5, "вдесятеро": 10,
}
# "один" counts only inside a compound number: "двадцать один", "сто одну".
ONE_FORMS = ("один", "одна", "одно", "одну", "одного", "одной", "одному", "одним", "одном")
# Compound number-unit adjectives ("шестилетний" ↔ "шесть лет" ↔ "6-летний", "трёхдневный" ↔ "3 дня").
# "одно-" is left out for the same reason as "один": "однодневный поход" → "поход на день" has no "1".
COMPOUND_NUM = {k: v for k, v in WORD_NUM.items() if k.endswith(("х", "и", "а"))}
COMPOUND_NUM.update({
    "девяносто": 90, "сто": 100, "ста": 100, "двухсот": 200, "трехсот": 300, "четырехсот": 400,
    "пятисот": 500, "шестисот": 600, "семисот": 700, "восьмисот": 800, "девятисот": 900, "тысяче": 1000,
})
COMPOUND_UNIT = {
    "летн": "год", "годовал": "год", "дневн": "дн", "суточн": "дн", "недельн": "нед", "месячн": "мес",
    "часов": "ч", "минутн": "мин", "секундн": "с", "процентн": "%", "метров": "м", "километров": "км",
    "литров": "л", "килограммов": "кг",
}
HYPHEN_UNIT_RX = re.compile(r"-(%s)[а-яё]+" % "|".join(sorted(COMPOUND_UNIT, key=len, reverse=True)), re.I)
COMPOUND_NUM_RX = re.compile(
    r"(?<![а-яё])(%s)-?(%s)[а-яё]+" % (
        "|".join(sorted(COMPOUND_NUM, key=len, reverse=True)),
        "|".join(sorted(COMPOUND_UNIT, key=len, reverse=True)),
    ),
    re.I,
)
SCALE = {"тыс": 1000, "тыс.": 1000, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
         "млн": 10 ** 6, "млн.": 10 ** 6, "миллион": 10 ** 6, "миллиона": 10 ** 6,
         "миллионов": 10 ** 6, "млрд": 10 ** 9, "миллиард": 10 ** 9, "миллиарда": 10 ** 9,
         "миллиардов": 10 ** 9}
# Longest first: "тыс." before "тыс", or the dot stops the unit after it ("30 тыс. человек").
SCALE_ALT = "|".join(re.escape(k) for k in sorted(SCALE, key=len, reverse=True))
# Months in any case, for dates without a day ("в марте 2026", "к апрелю", "между маем и июнем").
# Only the noun endings: "декабристов", "мартини", "январский" are not months.
MONTH_ANY_RX = re.compile(r"(?<![а-яё])(?:(январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)"
                          r"(?:ь|я|ю|ем|ём|е)|(март|август)(?:а|у|ом|е)?|(ма)(?:й|я|ю|ем|е))(?![а-яё])", re.I)
MONTH_ANY_NUM = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
                 "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
MONTHS = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|"
          "январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре|"
          "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь")
MONTH_STEM = {m[:3]: i for i, m in enumerate(
    "янв фев мар апр мая июн июл авг сен окт ноя дек".split(), 1)}
MONTH_STEM["май"] = 5
MONTH_STEM["мае"] = 5
# Links with a scheme or www.; zero-width characters end a link (a paste can glue them on).
# A closing parenthesis ends a link unless it closes one opened inside it:
# https://ru.wikipedia.org/wiki/Колос_(значения) is whole, "(см. https://a.ru)" stops at a.ru.
_ZW = ("\u200b\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069\u180e\u200c\u200d"
       "\u034f\u061c\u2800\u3164\uffa0\u115f\u1160"
       "\u2061-\u2064\ufff9-\ufffb\ue200-\ue204\uea01\uea02\ufe00-\ufe0f\U000e0000-\U000e007f\U000e0100-\U000e01ef")
URL_RX = (r"(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\.)"
          r"(?:\([^\s<>«»\"'()\]`%s]*\)|[^\s<>«»\"')\]`%s])+" % (_ZW, _ZW))
EMAIL_SKIP_RX = (r"(?<![A-Za-zА-Яа-яЁё0-9._%+-])"
                 r"[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\.[A-Za-zА-Яа-яЁё]{2,}")
HOMOGLYPHS = {
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "α": "а", "ε": "е", "ο": "о", "ρ": "р", "χ": "х", "κ": "к",
    "Α": "А", "Β": "В", "Γ": "Г", "Ε": "Е", "Η": "Н", "Κ": "К", "Μ": "М",
    "Ο": "О", "Π": "П", "Ρ": "Р", "Τ": "Т", "Υ": "У", "Φ": "Ф", "Χ": "Х",
}
HOMOGLYPH_TRANS = str.maketrans(HOMOGLYPHS)
_HOMO_LOOK = "".join(HOMOGLYPHS)
_HOMO_ALL = "А-Яа-яЁё\u0301\u0306\u0308" + _HOMO_LOOK
_WORD_CHARS = r"A-Za-z\u0370-\u03ffА-Яа-яЁё\u0301\u0306\u0308"
HOMO_WORD_RX = (r"(?<![%s])(?=[%s]*[А-Яа-яЁё])(?=[%s]*[%s])[%s]+(?![%s])"
                % (_WORD_CHARS, _HOMO_ALL, _HOMO_ALL, _HOMO_LOOK, _HOMO_ALL, _WORD_CHARS))
MD_TARGET_RX = r"(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)"
PROSE_HOMO_RX = re.compile(r"`[^`\n]+`|" + URL_RX + "|" + EMAIL_SKIP_RX + "|" + MD_TARGET_RX + "|(" + HOMO_WORD_RX + ")")
_REGEX_PREV = frozenset("=(,:;!&|?+-~*{[\n\r")
_REGEX_KW = frozenset(("return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"))
_REGEX_FLAGS = frozenset("dgimsuvy")
CYR_STRESS_RX = re.compile(r"(?<=[А-Яа-яЁё])\u0301")
PROSE_STRESS_RX = re.compile(URL_RX + r"|((?<=[А-Яа-яЁё])\u0301)")
# Chat citation tokens and invisible characters, the same set clean_paste.py removes: the source is
# read without them, so a removed "[cite: 1]" is not a lost number and a soft hyphen inside a quoted
# word or a zero-width space inside "20\u200b26" do not count as a change.
_CITETURN_STEP = r"turn\d+(?:search|fetch|file|image|news|video|ref|view)\d+"
CITATION_RX = re.compile(
    r":?contentReference\[oaicite:\d+\]\{index=\d+\}|\[oaicite:\d+\]"
    r"|\ue200[^\ue201\n]{0,120}\ue201|\uea01[^\uea02\n]{0,40}\uea02"
    r"|(?<![A-Za-z0-9/_.\-=?:&#@])cite" + _CITETURN_STEP + r"(?:" + _CITETURN_STEP + r")*"
    r"|【\d+(?::\d+)?(?:†[^】\n]{0,80})?】|\[cite_start\]|\[cite(?:_end)?(?::\s*[\d,\s]+)?\]"
    r"|\[(?:citation|attached_file|web):\d+\]|\[span_\d+\][\[(](?:start_span|end_span)[\])]"
    r"|\[\^\d+\^\]", re.I
)
INVISIBLE_CPS = frozenset((
    0x200B, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069, 0x180E, 0x200C, 0x034F, 0x061C,
    0x2061, 0x2062, 0x2063, 0x2064, 0xFFF9, 0xFFFA, 0xFFFB,
    0xE200, 0xE201, 0xE202, 0xE203, 0xE204, 0xEA01, 0xEA02,
))
SPACE_SPOOFERS = frozenset((0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160))
_WS = frozenset(
    " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)
# Sentence punctuation and Markdown emphasis after a link are not part of it: **https://a.ru**
URL_TAIL = ".,;:!?…*_"


def _url_key(url: str) -> str:
    """Scheme and host are case-insensitive, the path is not. A slash after the bare host is the
    same page (https://a.ru/ = https://a.ru); deeper, /api/item/ and /api/item may differ."""
    m = re.match(r"((?:https?://)?[^/?#]*)(.*)", url, re.S | re.I)
    return m.group(1).lower() + ("" if m.group(2) == "/" else m.group(2))

# Days of the week. "Среда" alone is also "environment" ("рабочая среда", "окружающей среды"),
# so only "в среду", "по средам" and a schedule line "Среда: …" / "Среда, 5 ноября" count.
WEEKDAY_RX = re.compile(r"(?<![а-яё])(понедельник|вторник|четверг|пятниц|суббот|воскресень|"
                        r"сред(?=у|ам)|сред(?=а[ \t]*[,:]))[а-яё]*", re.I)
WEEKDAY_NUM = {"понедельник": 1, "вторник": 2, "сред": 3, "четверг": 4, "пятниц": 5, "суббот": 6,
               "воскресень": 7}
# A schedule range of two-letter forms («пн–пт», «Сб-Вс»): alone «ср.» is «сравни», «вс» and «пт» are
# too short to trust, so only two of them joined by a dash count (frontier arm 2026-11-09, f30).
WEEKDAY_ABBR = {"пн": 1, "вт": 2, "ср": 3, "чт": 4, "пт": 5, "сб": 6, "вс": 7}
WEEKDAY_RANGE_RX = re.compile(r"(?<![а-яё])(пн|вт|ср|чт|пт|сб|вс)\.?[ \t\u00a0]*[-–—][ \t\u00a0]*"
                              r"(пн|вт|ср|чт|пт|сб|вс)\.?(?![а-яё])", re.I)
# A single 2-letter weekday before ", <date>" or ": <time>" ("пн, 2 ноября", "Пн: 9:00") or in
# lower case after a schedule preposition ("с пн", "в пт"), so "1500 Вт", "ВС" and "Ср." stay out.
WEEKDAY_DATE_RX = re.compile(
    r"(?<![А-Яа-яЁёA-Za-z0-9])(пн|вт|ср|чт|пт|сб|вс)\.?(?=[ \t\u00a0]*(?:,[ \t\u00a0]*\d{1,2}"
    r"(?:[ \t\u00a0]+(?:%s)|\.\d{1,2}\b)|:[ \t\u00a0]*\d{1,2}[:.]\d{2}))" % MONTHS, re.I)
WEEKDAY_PREP_RX = re.compile(
    r"(?<![А-Яа-яЁёA-Za-z])(?:[Вв]|[Вв]о|[Сс]|[Сс]о|[Дд]о|[Кк]|[Пп]о)[ \t\u00a0]+"
    r"(пн|вт|чт|сб|вс|(?:ср|пт)(?!\.))(?![А-Яа-яЁёA-Za-z]|[ \t\u00a0]*[-–—])")
HEDGES = ("около", "примерно", "приблизительно", "почти", "порядка", "до", "не более",
          "не менее", "не свыше", "более", "свыше", "менее", "больше", "меньше", "минимум", "максимум",
          "от", "не больше", "не меньше", "не позже", "не позднее", "не раньше", "после",
          "только", "лишь", "кроме", "без", "не старше")
# Hedges that say the same: «около 40» → «примерно 40» and «не менее 5» → «минимум 5» keep the hedge.
HEDGE_SAME = {"около": "≈", "примерно": "≈", "приблизительно": "≈", "порядка": "≈",
              "не менее": "≥", "не меньше": "≥", "минимум": "≥",
              "не более": "≤", "не больше": "≤", "максимум": "≤", "не старше": "≤", "не свыше": "≤",
              "более": ">", "свыше": ">", "больше": ">", "менее": "<", "меньше": "<",
              "не позже": "≤д", "не позднее": "≤д"}


def hedge_class(hedge: str) -> str:
    """Hedges that say the same share a class; any other hedge is its own class."""
    return HEDGE_SAME.get(hedge, hedge)


# The direction of a hedge: a lower bound ("не менее 5", "от 30%", "после 20 мая") or an upper
# one ("не более 5", "до 30%", "не позднее 15 марта"). A hedge turned the other way changes the
# meaning of the number.
HEDGE_DIR = {"≥": "lower", ">": "lower", "≤": "upper", "<": "upper", "≤д": "upper",
             "от": "lower", "после": "lower", "не раньше": "lower", "до": "upper"}
HEDGE_OPPOSITE = {"lower": "upper", "upper": "lower"}


def hedge_direction(hedge: str) -> str:
    """The direction a hedge points to: "lower", "upper" or "" (it points nowhere)."""
    return HEDGE_DIR.get(hedge_class(hedge), "")


# A name after these prepositions gives the money or passes it on, it does not get it.
SOURCE_PREPOSITIONS = ("от", "через")
NEG_WORDS = ("не", "ни", "нет", "нельзя", "без", "никаких", "никакой", "никакого", "никакие", "никакая",
             "никогда", "ничего", "ничто", "ничем", "никто", "никого", "никому", "нигде", "никак", "нисколько")
# Words of certainty and scope: losing one turns "may" into "will", "some" into "sometimes".
MODALITY = [
    ("может", r"мо(?:жет|гут|жем|жете|гу|г|гла|гли|жно)"),
    ("возможно", r"возможн[оа]"),
    ("наверное", r"наверн(?:ое|яка)|вероятно|видимо|скорее всего|кажется"),
    ("план", r"(?:за)?планир\w*"),
    ("обычно", r"обычно"),
    ("иногда", r"иногда"),
    ("часто", r"часто"),
    ("редко", r"редко"),
    ("всегда", r"всегда"),
    ("никогда", r"никогда"),
    ("некоторые", r"некотор\w*"),
    ("многие", r"многи[ехм]\w*"),
    ("каждый", r"кажд\w+"),
    ("почти", r"почти"),
    ("риск", r"риск\w*|вероятност\w*"),
    ("один из", r"(?:один|одна|одно|одного|одной|одним|одну|одном) из"),
    ("только", r"только|лишь"),
    ("если", r"если|в случае|при условии"),
    ("по данным / по словам", r"по (?:данным|словам|оценк\w+|мнению)|согласно"),
]
# Words that make a claim stronger: a check when the edit has more of them than the original
# ("ключевой фактор" -> "главный фактор", "один из лучших" -> "лучший").
INTENSIFIERS = r"сам(?:ый|ая|ое|ые|ого|ой|ым|ых|ую|ом)|главн\w*|наиболее|лучш\w*|важнейш\w*|гарантирован\w*"
SENT_START_STOP = {"В", "На", "С", "И", "А", "Но", "Это", "Мы", "Вы", "Я", "Он", "Она",
                   "Они", "Если", "Когда", "Для", "По", "При", "От", "До", "За", "Из", "К",
                   "О", "У", "Как", "Что", "Так", "Все", "Всё", "Наш", "Наша", "Наши", "Ваш",
                   "Ваша", "Ваши", "Также", "Кроме", "Еще", "Ещё", "Уже", "Теперь", "Сейчас",
                   "Здравствуйте", "Привет", "Добрый", "Уважаемый", "Уважаемая", "Спасибо",
                   "С уважением"}
# "Вы" and "Ваш" written with a capital out of politeness are not names.
POLITE_PRONOUN = re.compile(r"Вы|Вас|Вам|Вами|Ваш(?:а|е|и|его|ему|ем|ей|у|ую|их|им|ими)?|"
                            r"Ты|Тебе|Тебя|Тобой|Твой|Тво(?:я|е|ё|и|его|ему|ем|ём|ей|ю|их|им|ими)")
# Frequent first names: a capitalised word at the start of a sentence is a name when it
# matches one of these (case endings allowed), otherwise only when it is capitalised elsewhere.
FIRST_NAMES = set("""Александр Александра Алексей Алина Алиса Алла Анастасия Анатолий Андрей Анна
Антон Арина Аркадий Арсений Артём Артем Борис Вадим Валентин Валентина Валерий Валерия Варвара
Василий Вера Вероника Виктор Виктория Виталий Владимир Владислав Вячеслав Галина Георгий Глеб
Григорий Дарья Денис Диана Дмитрий Евгений Евгения Егор Екатерина Елена Елизавета Иван Игорь
Илья Инна Ирина Карина Кирилл Константин Кристина Ксения Лариса Леонид Лидия Любовь Людмила
Максим Маргарита Марина Мария Марк Матвей Михаил Надежда Наталья Наталия Никита Николай Нина
Олег Ольга Павел Пётр Петр Полина Роман Руслан Светлана Семён Семен Сергей Софья Станислав
Степан Тамара Татьяна Тимофей Тимур Фёдор Федор Эдуард Юлия Юрий Яна Ярослав""".split())
# The chat assistant's own lines around the text: the head («Готово, вот текст:»), the tail
# («Если нужно, могу…») and the headings («Вариант 1 …»). Their values are not facts of the text.
SERVICE_SEP_RX = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,}|```[^\n]*)[ \t]*$", re.M)
SERVICE_HEAD_RX = re.compile(r"(?i)^\W*(?:вот\b|готов(?:о|ый|ая|ое|ые)\b)")
SERVICE_HEAD_STRICT_RX = re.compile(r"(?i)^\W*(?:готово\b|вот\s+(?:готов|ваш|текст|вариант|пост|письмо))")
SERVICE_TAIL_RX = re.compile(r"(?i)^\W*(?:пара (?:замечаний|уточнений)|несколько (?:замечаний|пояснений|уточнений|слов)|"
                             r"(?:небольшое\s+)?уточнени|что (?:учтено|нужно|стоит)|объём|замечани|служебн|заметки для|"
                             r"если (?:нужно|нужен|нужна|нужны|хотите)|могу\b|готово|советы?\W|перед отправкой)")
SERVICE_FIRST_RX = re.compile(r"(?i)могу|сделаю|напишу|переделаю|перепишу|пересоберу|сокращу|впишу|добавлю|поправлю|"
                              r"я (?:оформил|добавил|убрал|вывел)")
# The author's own lines also open with «Вот», «Советы…», «Если хотите, могу…» (cross-review 10.11,
# two rounds): a head counts only with «готов…», a size or a colon at its end; a tail only when it
# speaks about the text itself. Option headings («Вариант 1 (…)») are never service lines.
SERVICE_ABOUT_RX = re.compile(r"(?i)текст|вариант|верси|пост(?:а|у|ом|е)?\b|письм|сообщени|объявлени|"
                              r"рассылк|описани|карточк|ваканси|резюме|стать[яи]|объ[её]м|знак|символ|"
                              r"публикац|отправк|абзац|заголов|год\s+в\s+дат")
SERVICE_SIZE_RX = re.compile(r"(?i)готов(?:о|ый|ая|ое|ые)(?![а-яё])|(?<![а-яё])(?:знак|символ|слов)(?:ов|а|о|и|ы)?(?![а-яё])")
SERVICE_PAREN_RX = re.compile(r"\([~≈]?\s*(?:около\s+|примерно\s+|порядка\s+|до\s+)?\d+(?:[ \t\u00a0]+\d+)*[ \t\u00a0]*"
                              r"(?:знак|символ|слов)(?:ов|а|о|и|ы)?(?![а-яё])[^)\n]{0,120}\)", re.I)
POUND_MONEY_RX = re.compile(
    r"(?i)(?:(?<![а-яё])(?:за|стоимостью|ценой)|сто(?:ит|ят|ил[аио]?)|цен[аеыуой]|"
    r"оплат\w*|штраф\w*|бюджет\w*|тариф\w*|чек\w*|куп\w*|плат\w*)"
    r"[ \t\u00a0*_]*(?:(?:около|примерно|до|от|не[ \t\u00a0*_]+более|не[ \t\u00a0*_]+менее|порядка|свыше|более|менее)[ \t\u00a0*_]*)?$"
)
ITEM_STOP = frozenset((
    "и", "а", "но", "да", "или", "либо", "ли", "же", "бы", "б", "не", "ни", "нет", "нельзя", "можно",
    "надо", "нужно", "есть", "был", "была", "было", "были", "будет", "будут", "стал", "стала", "стало",
    "стали", "станет", "станут", "я", "меня", "мне", "мной", "мною", "мы", "нас", "нам", "нами",
    "ты", "тебя", "тебе", "тобой", "вы", "вас", "вам", "вами", "он", "его", "него", "ему", "нему",
    "им", "ним", "нем", "она", "ее", "нее", "ей", "ней", "ею", "они", "их", "них", "ими", "ними",
    "себя", "себе", "собой", "мой", "моя", "мое", "мои", "моего", "моей", "моему", "моим", "моем",
    "моих", "моими", "наш", "наша", "наше", "наши", "нашего", "нашей", "нашему", "нашим", "нашем",
    "наших", "нашими", "ваш", "ваша", "ваше", "ваши", "вашего", "вашей", "вашему", "вашим", "вашем",
    "ваших", "вашими", "твой", "свой", "своя", "свое", "свои", "своего", "своей", "своему", "своим",
    "своем", "своих", "своими", "этот", "эта", "это", "эти", "этого", "этой", "этому", "этим", "этом",
    "этих", "этими", "тот", "та", "то", "те", "того", "той", "тому", "тем", "том", "тех", "теми",
    "весь", "вся", "все", "всего", "всей", "всему", "всем", "всех", "всеми", "сам", "сама", "само",
    "сами", "кто", "что", "чего", "чему", "чем", "ком", "какой", "какая", "какое", "какие", "чей",
    "который", "которая", "которое", "которые", "которого", "которой", "которому", "которым",
    "котором", "которых", "которыми", "никто", "ничто", "никакой", "некоторый", "некоторые",
    "каждый", "любой", "иной", "другой", "другая", "другое", "другие", "прочий", "прочие",
    "остальной", "остальные", "такой", "такая", "такое", "такие", "первый", "первого", "первому",
    "первым", "первом", "первая", "первой", "первую", "первое", "первые", "первых", "первыми",
    "второй", "второго", "второму", "вторым", "втором", "вторая", "вторую", "второе", "вторые",
    "вторых", "вторыми", "третий", "третьего", "третьему", "третьим", "третьем", "третья", "третьей",
    "третью", "третье", "третьи", "третьих", "третьими", "четвертый", "пятый", "последний",
    "предыдущий", "следующий", "оба", "обе", "обоих", "обеих", "вариант", "шаг", "этап", "пункт",
    "раздел", "часть", "глава", "где", "тут", "здесь", "там", "туда", "сюда", "оттуда", "тогда",
    "когда", "пока", "уже", "еще", "только", "лишь", "даже", "почти", "просто", "очень", "более",
    "менее", "самый", "самая", "самое", "самые", "итого", "вместе", "впрочем", "однако", "зато",
    "поэтому", "потому", "причем", "притом", "также", "тоже", "например", "скажем", "вроде", "типа",
    "около", "примерно", "приблизительно", "порядка", "свыше", "минимум", "максимум", "сегодня",
    "вчера", "завтра", "сейчас", "теперь", "потом", "затем", "сначала", "сразу", "снова", "опять",
    "всегда", "часто", "редко", "иногда", "обычно", "раньше", "позже", "позднее", "далее", "дальше",
    "если", "хотя", "ведь", "пусть",
))
ITEM_LEAD_PREPS = frozenset((
    "в", "во", "на", "за", "по", "для", "у", "к", "ко", "с", "со", "из", "от", "до", "при",
    "о", "об", "обо", "про", "под", "над", "перед", "через", "между", "около", "вокруг", "после",
    "среди", "против",
))
ITEM_BAD_NUM_PREPS = frozenset((
    "после", "через", "из", "с", "со", "у", "к", "ко", "для", "при", "о", "об", "обо", "про",
    "под", "над", "перед", "между", "без", "кроме", "вместо", "среди", "против", "вокруг",
))
ITEM_VAL_PREPS = frozenset(("за", "по", "в", "во", "на"))
ITEM_LEAD_LOCATIVES = frozenset((
    "меню", "прайсе", "прайс-листе", "каталоге", "списке", "перечне", "таблице", "продаже",
    "наличии", "сайте", "витрине", "заказе", "чеке", "счете", "тарифах", "ассортименте",
))
ITEM_CLASSIFIERS = (
    "тариф", "пакет", "план", "подписк", "опци", "модел", "верси", "размер", "формат",
    "уровен", "уровн", "режим", "тип", "класс", "категори", "курс", "линейк", "сери",
    "комплектаци", "зал", "зон", "корпус", "секци",
)
ITEM_NOUN_LI = frozenset((
    "модели", "недели", "панели", "детали", "мебели", "качели", "капели", "стали", "соли",
    "пыли", "цели", "роли", "доли", "мили", "шали", "дали", "щели", "мели",
))
ITEM_COPULA_RX = re.compile(
    r"^(?:сто(?:ит|ят|ил[аио]?|имостью)|обойдется|обойдутся|обход(?:ится|ятся)|"
    r"обош(?:елся|лась|лось|лись)|выйд(?:ет|ут)|выход(?:ит|ят)|составл(?:яет|яют)|"
    r"состав(?:ил[аио]?|или|ит|ят)|рав(?:ен|на|но|ны|няется|няются)|"
    r"дл(?:ится|ятся|ился|илась|илось|ились)|занима(?:ет|ют)|зан(?:ял[аио]?|яли)|"
    r"займ(?:ет|ут)|вес(?:ит|ят|ил[аио]?)|вмеща(?:ет|ют))$"
)
ITEM_INTRO_VERB_RX = re.compile(
    r"^(?:есть|доступ(?:ен|на|но|ны)|представлен[аоы]?|предлага(?:ем|ют|ется|ются)|"
    r"пода(?:ем|ют|ется|ются)|готов(?:им|ят)|действу(?:ет|ют)|работа(?:ет|ют)|"
    r"вход(?:ит|ят)|прода(?:ем|ют|ется|ются)|жд(?:ет|ут))$"
)
# END_BLOCK_LEXICON


def _norm(s: str) -> str:
    return s.replace("ё", "е").replace("Ё", "Е")


CASE_ENDINGS = frozenset(("", "а", "я", "о", "е", "и", "ы", "у", "ю", "ой", "ей", "ою", "ею", "ом", "ем",
                          "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ий", "ия", "ие", "ья", "ье",
                          "ью", "ая", "ое", "ые", "ый", "ого", "его", "ому", "ему", "ым", "им", "ую", "ых",
                          "их", "ыми", "ими"))


def _case_tail(tail: str) -> bool:
    """The rest of a word after its stem: a case ending, or a soft sign («Гриша» → «Гришу»)."""
    return tail in CASE_ENDINGS or tail in ("ь", "й")


def _first_name_case(word: str, name: str) -> bool:
    """A singular case of a first name of the list (or its -ов/-ев surname), also with a fleeting
    vowel («Павел» → «Павлу»). Sentence-initial verbs and common nouns («Дарим» vs «Дарья»,
    «Верим» vs «Вера», «Лид» vs «Лидия») stay out."""
    w, n = _norm(word.lower()), _norm(name.lower())
    if n.endswith(("ья", "ия")):
        return w.startswith(n[:-1]) and w[len(n) - 1:] in ("я", "и", "е", "ю", "ей", "ею")
    if n.endswith("а"):
        return w.startswith(n[:-1]) and w[len(n) - 1:] in ("а", "ы", "и", "е", "у", "ой", "ою", "ей", "ею")
    if n.endswith("й"):
        return w.startswith(n[:-1]) and w[len(n) - 1:] in (
            "й", "я", "ю", "ем", "е", "и", "ев", "ева", "еву", "евым", "евой")
    if n.endswith("ь"):
        if n == "любовь":
            return w in ("любовь", "любви", "любовью")
        return w.startswith(n[:-1]) and w[len(n) - 1:] in (
            "ь", "я", "ю", "ем", "е", "ев", "ева", "еву", "евым", "евой")
    masc_tails = ("", "а", "у", "ом", "ем", "е", "ов", "ова", "ову", "овым", "овой",
                  "ев", "ева", "еву", "евым", "евой")
    if w.startswith(n) and w[len(n):] in masc_tails:
        return True
    if re.search(r"[бвгджзклмнпрстфхцчшщ][ео][лнр]$", n):
        stem = n[:-2] + n[-1]
        return w.startswith(stem) and w[len(stem):] in masc_tails[1:]
    return False


def _build_first_name_forms() -> frozenset:
    forms = set()
    masc_tails = ("", "а", "у", "ом", "ем", "е", "ов", "ова", "ову", "овым", "овой",
                  "ев", "ева", "еву", "евым", "евой")
    for raw_n in FIRST_NAMES:
        n = _norm(raw_n.lower())
        max_len = len(raw_n) + 3
        if n.endswith(("ья", "ия")):
            cands = [n[:-1] + t for t in ("я", "и", "е", "ю", "ей", "ею")]
        elif n.endswith("а"):
            cands = [n[:-1] + t for t in ("а", "ы", "и", "е", "у", "ой", "ою", "ей", "ею")]
        elif n.endswith("й"):
            cands = [n[:-1] + t for t in ("й", "я", "ю", "ем", "е", "и", "ев", "ева", "еву", "евым", "евой")]
        elif n.endswith("ь"):
            cands = ["любовь", "любви", "любовью"] if n == "любовь" else [
                n[:-1] + t for t in ("ь", "я", "ю", "ем", "е", "ев", "ева", "еву", "евым", "евой")]
        else:
            cands = [n + t for t in masc_tails]
            if re.search(r"[бвгджзклмнпрстфхцчшщ][ео][лнр]$", n):
                stem = n[:-2] + n[-1]
                cands.extend(stem + t for t in masc_tails[1:])
        for c in cands:
            if len(c) <= max_len:
                forms.add(c)
    return frozenset(forms)


FIRST_NAME_FORMS = _build_first_name_forms()


def _same_name_case(a: str, b: str) -> bool:
    """Two spellings of one name («Сбер» … «Сбера», «Соколовы» … «Соколовых»): they share a
    stem and the rest of each word is a case ending. «То» and «Томске» share no stem: not one
    name."""
    a, b = _norm(a.lower()), _norm(b.lower())
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    for k in range(n, 2, -1):
        # The stem is the longest common prefix that leaves a case ending in both words.
        if _case_tail(a[k:]) and _case_tail(b[k:]):
            return k >= min(len(a), len(b)) - 2
    return False


def name_match(a: str, b: str) -> bool:
    """A name in another case. stem_match needs a 3-letter stem, so short names (Ани/Ане, Оля/Оле)
    also match when both tails are case endings. Мария/Марина still match: told apart by meaning only."""
    if stem_match(a, b):
        return True
    a, b = _norm(a.lower()), _norm(b.lower())
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 2 and a[n:] in CASE_ENDINGS and b[n:] in CASE_ENDINGS


def stem_match(a: str, b: str, strict: bool = False) -> bool:
    """Russian case endings: words match when they share all but the last 2 letters (>= 3).
    strict (for verbs and common words): the shared part is also >= 4 letters and >= 60%
    of the longer word, so "перегружал" does not match "перед"."""
    a, b = _norm(a.lower()), _norm(b.lower())
    if a == b:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    if strict:
        return n >= max(4, min(len(a), len(b)) - 2) and n >= 0.6 * max(len(a), len(b))
    return n >= 3 and n >= min(len(a), len(b)) - 2


@dataclass
class Fact:
    kind: str
    value: str
    raw: str
    sent: int
    pos: int
    hedge: str = ""
    unit: str = ""
    speech: bool = False  # quote: direct speech or a quote after a colon


@dataclass
class Facts:
    items: List[Fact] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    starts: List[int] = field(default_factory=list)  # offset of each sentence in the text

    def of(self, kind: str) -> List[Fact]:
        return [f for f in self.items if f.kind == kind]


def clause_spans(sentence: str) -> List[Tuple[int, int]]:
    """Clauses of a sentence: a comma or a semicolon followed by a space ends one item of an
    enumeration («Анна получила 30 000, Борис 50 000»); a decimal comma does not."""
    spans, start = [], 0
    for m in re.finditer(r"[;,]\s", sentence):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(sentence)))
    return spans


ITEM_HEAD_RX = re.compile(r"(?:(?:[Вв]|[Вв]о|[Уу]|[Кк]|[Кк]о|[Дд]ля)\s+)?[*_«\"]*[A-ZА-ЯЁ]")
ITEM_PAD_RX = re.compile(r"[*_]*")
AND_SPLIT_RX = re.compile(r"\s+и\s+")
SRC_PREP_TAIL_RX = re.compile(r"(?<![а-яё])(?:от|через)\s+[A-ZА-ЯЁ][\w.\s-]*$", re.I)


def _item_head(sentence: str, start: int, end: int, numbers) -> bool:
    """True when a sub-clause after «и» opens like a parallel list item: a name (optionally after a
    short preposition like «в Казани») or a leading number («50 000 рублей получил Борис»)."""
    part = sentence[start:min(end, start + 32)]
    if ITEM_HEAD_RX.match(part):
        return True
    pad = len(ITEM_PAD_RX.match(part).group(0))
    return (start + pad) in numbers


def _split_and(sentence: str, a: int, b: int, numbers: List[int], who,
               memo: Optional[Dict[Tuple[int, int], List[Tuple[int, int]]]] = None) -> List[Tuple[int, int]]:
    """Split a comma-clause at « и » only when both sides each hold one distinct receiver and at
    least one number («Борис 50 000 и Вера 7 000»), leaving «Анна и Борис по 100» intact."""
    if memo is not None and (a, b) in memo:
        return memo[(a, b)]
    ands = [(a + m.start(), a + m.end()) for m in AND_SPLIT_RX.finditer(sentence[a:b])]
    if not ands:
        return [(a, b)]
    nums_sorted = sorted(numbers)
    if bisect.bisect_left(nums_sorted, b) <= bisect.bisect_left(nums_sorted, a):
        return [(a, b)]
    num_set = set(nums_sorted)
    k_len = len(ands)
    starts_i = [a] + [nxt for _, nxt in ands]
    head_ok = [_item_head(sentence, nxt, b, num_set) for _, nxt in ands]
    split_choice: List[Optional[Tuple[int, int]]] = [None] * (k_len + 1)
    tail_who_cache: List[Optional[list]] = [None] * (k_len + 1)

    def get_tail_who(idx: int) -> list:
        cached = tail_who_cache[idx]
        if cached is not None:
            return cached
        if idx < k_len and tail_who_cache[idx + 1] is not None and len(tail_who_cache[idx + 1]) > 1:
            if not SRC_PREP_TAIL_RX.search(sentence[starts_i[idx]:ands[idx][0]]):
                tail_who_cache[idx] = tail_who_cache[idx + 1]
                return tail_who_cache[idx]
        got = who(starts_i[idx], b)
        tail_who_cache[idx] = got
        return got

    get_tail_who(k_len)
    valid_js_rev: List[int] = []
    for i in range(k_len - 1, -1, -1):
        nxt_i = ands[i][1]
        if head_ok[i] and bisect.bisect_left(nums_sorted, b) > bisect.bisect_left(nums_sorted, nxt_i):
            if split_choice[i + 1] is not None or len(get_tail_who(i + 1)) == 1:
                valid_js_rev.append(i)
        if not valid_js_rev:
            continue
        a_i = starts_i[i]
        lo_num = bisect.bisect_left(nums_sorted, a_i)
        if lo_num >= len(nums_sorted) or nums_sorted[lo_num] >= b:
            continue
        first_num = nums_sorted[lo_num]
        for j in reversed(valid_js_rev):
            mid_end = ands[j][0]
            if mid_end <= first_num:
                continue
            left_who = who(a_i, mid_end)
            if not left_who:
                continue
            if len(left_who) > 1:
                break
            if split_choice[j + 1] is not None or get_tail_who(j + 1) != left_who:
                split_choice[i] = (mid_end, j + 1)
                break
        if split_choice[i] is None:
            get_tail_who(i)

    res: List[Tuple[int, int]] = []
    cur = 0
    while split_choice[cur] is not None:
        mid_e, nxt_idx = split_choice[cur]
        res.append((starts_i[cur], mid_e))
        cur = nxt_idx
    res.append((starts_i[cur], b))
    if memo is not None:
        memo[(a, b)] = res
    return res


def list_clauses(sentence: str, numbers: List[int], who) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for a, b in clause_spans(sentence):
        out.extend(_split_and(sentence, a, b, numbers, who))
    return out


def clause_span(sentence: str, offset: int, clauses: Optional[List[Tuple[int, int]]] = None) -> Tuple[int, int]:
    """Bounds of the clause that holds `offset`; the whole sentence if none does."""
    spans = clauses if clauses is not None else clause_spans(sentence)
    if spans:
        i = bisect.bisect_right(spans, (offset, 1 << 62)) - 1
        if i >= 0 and spans[i][0] <= offset < spans[i][1]:
            return spans[i]
    return 0, len(sentence)


def is_list(sentence: str, numbers: List[int], who,
            clauses: Optional[List[Tuple[int, int]]] = None) -> bool:
    """The sentence lists parallel items: at least two clauses each hold one person (`who(a, b)`
    names the people of a clause) and a number. «Анна получила 30 000, Борис 50 000 и Вера 7 000»
    is a list; «Анна, Борис, Вера — все получили по 100» is one number for a row of names."""
    spans = clauses if clauses is not None else list_clauses(sentence, numbers, who)
    nums_sorted = sorted(numbers)
    found = 0
    for a, b in spans:
        if bisect.bisect_left(nums_sorted, b) > bisect.bisect_left(nums_sorted, a) and len(who(a, b)) == 1:
            found += 1
            if found >= 2:
                return True
    return False


def split_sentences(text: str) -> List[Tuple[int, str]]:
    out, start = [], 0
    for m in re.finditer(r"(?<=[.!?…])\s+(?=[«\"(A-ZА-ЯЁ0-9])|\n+", text):
        out.append((start, text[start:m.start()]))
        start = m.end()
    out.append((start, text[start:]))
    return [(s, t) for s, t in out if t.strip()]


def _canon_num(raw: str) -> Optional[float]:
    s = re.sub("[%s]" % SEP, "", raw).replace(",", ".").lstrip("+")
    s = s.replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def _big_num_str(raw: str, scale_zeros: int = 0) -> str:
    s = re.sub("[%s]" % SEP, "", raw).replace(",", ".").lstrip("+").replace("−", "-")
    neg = s.startswith("-")
    body = s[1:] if neg else s
    int_part, _, frac_part = body.partition(".")
    int_part = re.sub(r"\D", "", int_part).lstrip("0") or "0"
    frac_part = re.sub(r"\D", "", frac_part)
    if scale_zeros >= len(frac_part):
        int_part = (int_part + frac_part + "0" * (scale_zeros - len(frac_part))).lstrip("0") or "0"
        frac_part = ""
    elif scale_zeros > 0:
        int_part = (int_part + frac_part[:scale_zeros]).lstrip("0") or "0"
        frac_part = frac_part[scale_zeros:]
    frac_part = frac_part.rstrip("0")
    sign = "-" if neg and (int_part != "0" or frac_part) else ""
    return sign + int_part + ("." + frac_part if frac_part else "")


def _fmt(v: float) -> str:
    # 12 significant digits: "%g" kept 6 and made 100000,01 equal to 100000,02.
    if not math.isfinite(v):
        return str(v)
    return str(int(v)) if v == int(v) else ("%.12g" % v)


# START_CONTRACT: extract
# PURPOSE: Pull checkable facts out of one text.
# INPUTS: text (str); edited (bool): the text is the edit, so bold and italic marks between a
#         hedge and its number do not hide the hedge.
# OUTPUTS: Facts with numbers (value, unit, hedge), dates, times, urls, emails, names,
#          quotes, negations; plus the sentence list used for bindings.
# SIDE_EFFECTS: none.
# END_CONTRACT: extract
def extract(text: str, edited: bool = False, stripped: bool = False) -> Facts:
    if not stripped:
        text = _strip_tracking(text)
    facts = Facts()
    sents = split_sentences(text)
    facts.sentences = [t for _, t in sents]
    facts.starts = [s for s, _ in sents]
    prior_taken: List[Tuple[int, int]] = []
    prior_starts: List[int] = []
    pass_taken: List[Tuple[int, int]] = []

    def flush_taken() -> None:
        nonlocal prior_taken, prior_starts
        if not pass_taken:
            return
        merged: List[Tuple[int, int]] = []
        for s, e in sorted(prior_taken + pass_taken):
            if merged and s <= merged[-1][1]:
                if e > merged[-1][1]:
                    merged[-1] = (merged[-1][0], e)
            else:
                merged.append((s, e))
        prior_taken = merged
        prior_starts = [s for s, _ in merged]
        pass_taken.clear()

    def take(a: int, b: int) -> None:
        if a < b:
            pass_taken.append((a, b))

    def sent_of(pos: int) -> int:
        if not facts.starts:
            return 0
        idx = bisect.bisect_right(facts.starts, pos) - 1
        return idx if idx >= 0 else 0

    def free(a: int, b: int) -> bool:
        if prior_taken:
            i = bisect.bisect_right(prior_starts, a) - 1
            if i >= 0 and prior_taken[i][1] > a:
                return False
            if i + 1 < len(prior_taken) and prior_taken[i + 1][0] < b:
                return False
        for k in range(len(pass_taken) - 1, -1, -1):
            ps, pe = pass_taken[k]
            if pe <= a:
                break
            if b > ps and a < pe:
                return False
        return True

    def upgrade_pound(unit: str, num_pos: int) -> str:
        if unit == "фунт" and POUND_MONEY_RX.search(_norm(text[max(0, num_pos - 36):num_pos])):
            return "£"
        return unit

    # Bold and italic marks may stand between a hedge and its number in both source and edit
    # («минимум **2 человека**», «**минимум** 2 человека»): moving them is not losing the hedge,
    # and dropping a hedge around bolded numbers in the source is no longer silent.
    gap = r"[ \u00a0\u202f*_]"
    hedge_rxs = [
        (h, re.compile(r"(?:^|[^а-яa-z])%s(?:%s+чем)?%s*$" % (
            (gap + "+").join(re.escape(p) for p in _norm(h).split(" ")), gap, gap
        )))
        for h in sorted(HEDGES, key=len, reverse=True)
    ]
    cyr_any_rx = re.compile(r"[а-яё]")

    def hedge_before(pos: int) -> str:
        left = _norm(text[max(0, pos - 32):pos].lower())
        if not cyr_any_rx.search(left):
            return ""
        for h, hrx in hedge_rxs:
            # «не менее чем 6»: «чем» may stand between the hedge and the number
            if hrx.search(left):
                return h
        return ""

    # START_BLOCK_URLS
    for m in re.finditer(URL_RX, text):
        url = m.group().rstrip(URL_TAIL)
        facts.items.append(Fact("url", _url_key(url), url, sent_of(m.start()), m.start()))
        take(m.start(), m.start() + len(url))
    flush_taken()
    for m in re.finditer(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        if free(m.start(), m.end()):
            facts.items.append(Fact("email", m.group().lower(), m.group(), sent_of(m.start()), m.start()))
            take(m.start(), m.end())
    flush_taken()
    # Phones are compared by digits: +7 (999) 123-45-67 = 8 999 123 45 67.
    phone_rx = (r"(?<![\w+])(?:\+\d{1,3}[ \xa0-]?|8[ \xa0-]?)\(?\d{3,5}\)?[ \xa0-]?"
                r"\d{1,3}[ \xa0-]?\d{2}[ \xa0-]?\d{2}(?![\w-])")
    for m in re.finditer(phone_rx, text):
        digits = re.sub(r"\D", "", m.group())
        if free(m.start(), m.end()) and 10 <= len(digits) <= 15:
            if len(digits) == 11 and digits[0] == "8":
                digits = "7" + digits[1:]
            facts.items.append(Fact("phone", digits, m.group(), sent_of(m.start()), m.start()))
            take(m.start(), m.end())
    flush_taken()
    # END_BLOCK_URLS

    # START_BLOCK_DATES_TIMES
    # Versions, IP addresses, clause numbers (2.1.3, v3.11.12, 192.168.0.1, п. 3.2.1) are one token
    # compared as written: read as numbers, 2.1.3 and 2.1.4 both gave 2.1. They go before dates and
    # times, which took 10.0.10 out of 10.0.10.1 and 1.10 out of 192.168.1.10. Three parts are a
    # date when they look like one (01.02.26, 1.02.2026) and no "версия" stands before them.
    for m in re.finditer(r"(?<![\w.])(?:v(?=\d))?(\d+(?:\.\d+){2,})(?![\w]|\.\d)", text, re.I):
        parts = m.group(1).split(".")
        cue = m.group()[0] in "vV" or re.search(r"(?i)(?:верси\w*|релиз\w*|сборк\w*|version|release|build)\s*$",
                                                 text[max(0, m.start() - 20):m.start()])
        if (len(parts) == 3 and not cue and len(parts[0]) <= 2 and 1 <= int(parts[0]) <= 31
                and 1 <= int(parts[1]) <= 12
                and (len(parts[2]) == 4 or len(parts[1]) == len(parts[2]) == 2)):
            continue
        if free(m.start(), m.end()):
            facts.items.append(Fact("number", m.group(1), m.group(), sent_of(m.start()), m.start()))
            take(m.start(), m.end())
    flush_taken()
    # Day and month stand on one line: "Вариант 3\n\nНоябрь — ..." is not the 3rd of November.
    date_rx = re.compile(r"\b(\d{1,2})(?:[ \t ]*(?:[–—-]|,|или|и|по|до)[ \t ]*(\d{1,2}))?[ \t ]+(%s)(?:[ \t ]+(\d{4}))?" % MONTHS, re.I)
    for m in date_rx.finditer(text):
        month = MONTH_STEM.get(m.group(3).lower()[:3], 0)
        for day in filter(None, (m.group(1), m.group(2))):
            facts.items.append(Fact("date", "%02d.%02d" % (int(day), month), m.group(),
                                    sent_of(m.start()), m.start(), hedge_before(m.start())))
        if m.group(4):
            facts.items.append(Fact("number", m.group(4), m.group(4), sent_of(m.start()), m.start()))
        take(m.start(), m.end())
    flush_taken()
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", text):
        if free(m.start(), m.end()):
            facts.items.append(Fact("date", "%02d.%02d" % (int(m.group(1)), int(m.group(2))),
                                    m.group(), sent_of(m.start()), m.start()))
            # The year is kept as a number, the same way as in "1 февраля 2026".
            year = m.group(3) if len(m.group(3)) == 4 else "20" + m.group(3)
            facts.items.append(Fact("number", year, m.group(3), sent_of(m.start()), m.start()))
            take(m.start(), m.end())
    flush_taken()
    norm_text = _norm(text)
    for m in re.finditer(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,]\d)", text):
        # "1.50 ₽", "$1.50", "$1.50–2.50", "-1.50" and "1.50 млн" are numbers, not clock times.
        if text[m.end(1)] == "." and (
                UNIT_RX.match(text, m.end()) or (text[m.end():m.end() + 1] in "-–—" and HYPHEN_UNIT_RX.match(norm_text, m.end()))
                or PREFIX_TIME_CURR_RX.search(text[max(0, m.start() - 6):m.start()])
                or re.search(r"(?<![\w.,])[+\-−]$", text[max(0, m.start() - 2):m.start()])
                or re.search(r"[$€£¥₽][ \u00a0\u202f]*[+\-−]?\d+(?:[.,]\d+)?[ \t\u00a0]*[–—-][ \t\u00a0]*$",
                             text[max(0, m.start() - 24):m.start()])
                or re.match(r"[ \u00a0\u202f]+(%s)(?![а-я])" % SCALE_ALT, text[m.end():m.end() + 12], re.I)):
            continue
        if free(m.start(), m.end()):
            hh, mm = int(m.group(1)), m.group(2)
            value = str(hh) if mm == "00" else "%d:%s" % (hh, mm)
            facts.items.append(Fact("number", value, m.group(), sent_of(m.start()), m.start(),
                                    hedge_before(m.start()), "время"))
            take(m.start(), m.end())
    flush_taken()
    for m in WEEKDAY_RX.finditer(text):
        day = WEEKDAY_NUM[_norm(m.group(1).lower())]
        facts.items.append(Fact("date", "день недели %d" % day, m.group(), sent_of(m.start()), m.start()))
    seen_wk_pos = set()
    for m in WEEKDAY_RANGE_RX.finditer(text):
        for g in (1, 2):
            seen_wk_pos.add(m.start(g))
            facts.items.append(Fact("date", "день недели %d" % WEEKDAY_ABBR[m.group(g).lower()], m.group(g),
                                    sent_of(m.start(g)), m.start(g)))
    for rx in (WEEKDAY_DATE_RX, WEEKDAY_PREP_RX):
        for m in rx.finditer(text):
            if m.start(1) not in seen_wk_pos:
                seen_wk_pos.add(m.start(1))
                facts.items.append(Fact("date", "день недели %d" % WEEKDAY_ABBR[m.group(1).lower()],
                                        m.group(1), sent_of(m.start(1)), m.start(1)))
    # A month without a day ("в марте 2026") is a date fact of its own; see MONTHS_DIFF.
    for m in MONTH_ANY_RX.finditer(text):
        # A month is written in lower case; in the middle of a sentence "Марту", "Августа" are names.
        before = text[:m.start()].rstrip(" \t\xa0")
        if m.group()[0].isupper() and before and before[-1] not in ".!?…\n:—–-«\"(*#>|":
            continue
        if free(m.start(), m.end()):
            month = MONTH_ANY_NUM[next(g for g in m.groups() if g).lower()]
            facts.items.append(Fact("month", str(month), m.group(), sent_of(m.start()), m.start()))
    # END_BLOCK_DATES_TIMES

    # START_BLOCK_NUMBERS
    # Counters in headings ("Вариант 1", "Шаг 2") are structure, not facts.
    for m in re.finditer(r"(?i)(?:вариант|шаг|этап|пункт|раздел|часть|глава|блок)\s+(\d+)", text):
        take(m.start(1), m.end(1))
    # So are list markers at a line start ("1. Возьмите чек", "2) …", "## 3. Раздел", "> 4. …",
    # "**5. Заголовок**"): turning steps into a numbered list or back is a legitimate edit (4.2.0:
    # 98 false errors over 1596 old edits, 10 of them ours). A number inside the item stays a fact.
    sp = "[ \\t\\u00a0\\u202f]"
    for m in re.finditer(r"(?m)^[ \t\u00a0\u202f\ufeff]*(?:>%s*)*(?:#{1,6}%s+)?(?:[-*+]%s+)?(?:\*\*|__|\*|_)?"
                         r"(\d{1,2})[.)](?=[ \t\u00a0\u202f*_])" % (sp, sp, sp), text):
        take(m.start(1), m.end(1))
    for m in re.finditer(r"(\d)\ufe0f?\u20e3", text):
        take(m.start(1), m.end(1))
    flush_taken()
    sep_rx = re.compile("[%s]" % SEP)
    sign_rx = re.compile(r"^[+\-−]")
    acct_rx = re.compile(r"\d{16,}")
    scale_rx = re.compile(r"[%s]+(%s)(?![а-я])" % (SEP, SCALE_ALT), re.I)

    def _units_compat(u1: str, u2: str) -> bool:
        return u1 == u2 or (u1 == "¥" and u2 in ("JPY", "CNY")) or (u2 == "¥" and u1 in ("JPY", "CNY"))

    def read_number(start: int, digits: str, glued: bool = True, prefix_unit: str = "") -> Optional[Tuple[str, str, int]]:
        """The value, the unit and the end of a number that starts at `start`.
        None when the digits are not a number at all ("3D", "1С", "Pro2")."""
        plain = sep_rx.sub("", digits)
        int_digits = sign_rx.sub("", plain).split(".", 1)[0].split(",", 1)[0]
        is_acct = bool(acct_rx.fullmatch(plain))
        is_big = not is_acct and len(int_digits) >= 16
        if is_acct:
            value = plain             # a bank account: its digits as written, groups aside
        elif is_big:
            value = _big_num_str(plain)
        else:
            value = _canon_num(digits)
            if value is None:
                return None
            if not math.isfinite(value):
                is_big = True
                value = _big_num_str(plain)
        end = start + len(digits)
        sc, unit, scale_zeros = None, "", 0
        if glued and text[end:end + 1].isalpha():
            # The unit is glued to the digits ("500мл", "990р."): the same value and unit as
            # the spaced form. A capital letter is not a unit ("3D", "1С").
            gm = GLUED_UNIT_RX.match(text, end)
            if gm:
                u_gm = UNIT_CANON.get(gm.group(1).lower(), "")
                if not prefix_unit or (u_gm and _units_compat(u_gm, prefix_unit)):
                    unit = prefix_unit if (prefix_unit and u_gm == "¥") else u_gm
                    end = gm.end()
                else:
                    unit = prefix_unit
            elif text[end] in ("к", "k") and not text[end + 1:end + 2].isalpha():
                scale_zeros = 3
                if is_acct:
                    value += "000"
                elif is_big:
                    value = _big_num_str(plain, 3)
                else:
                    value *= 1000      # "30к" is "30 тыс."
                    if not math.isfinite(value):
                        value = _big_num_str(plain, 3)
                end += 1
                um = UNIT_RX.match(text, end)
                if um:                 # "30к рублей" is "30 тыс. рублей"
                    u_um = UNIT_CANON.get(um.group(1).lower(), "")
                    if not prefix_unit or (u_um and _units_compat(u_um, prefix_unit)):
                        unit = prefix_unit if (prefix_unit and u_um == "¥") else u_um
                        end = um.end()
                if not unit and prefix_unit:
                    unit = prefix_unit
            else:
                return None
        else:
            sc = scale_rx.match(text[end:end + 12])
            if sc:
                scale = SCALE[sc.group(1).lower()]
                scale_zeros = len(str(scale)) - 1
                if is_acct:
                    value += "0" * scale_zeros   # exact: «10…0 тыс.» is three zeros more
                elif is_big:
                    value = _big_num_str(plain, scale_zeros)
                else:
                    value *= scale
                    if not math.isfinite(value):
                        value = _big_num_str(plain, scale_zeros)
                end += sc.end()
            um = UNIT_RX.match(text, end)
            if um:
                u_um = UNIT_CANON.get(um.group(1).lower(), "")
                if not prefix_unit or (u_um and _units_compat(u_um, prefix_unit)):
                    unit = prefix_unit if (prefix_unit and u_um == "¥") else u_um
                    end = um.end()
                else:
                    unit = prefix_unit
            elif not prefix_unit and text[end:end + 1] in "-–—":
                hm = HYPHEN_UNIT_RX.match(norm_text, end)
                if hm:
                    unit = COMPOUND_UNIT[hm.group(1).lower()]
                    end = hm.end()
            elif prefix_unit:
                unit = prefix_unit
        unit = upgrade_pound(unit, start)
        if unit == "г" and not sc and not isinstance(value, str) and value == int(value) \
                and 1800 <= value <= 2100:
            unit = "год"  # "2020 г." is a year, not grams
        return (value if isinstance(value, str) else _fmt(value), unit, end)

    num_rx = re.compile(r"(?<![\w.,])[+\-−]?\d+(?:[%s]\d{3})*(?:[.,]\d+)?" % SEP)
    for m in num_rx.finditer(text):
        digits = m.group()
        num_start = m.start()
        prefix_unit = ""
        neg_prefix = False
        pm = PREFIX_CURR_RX.search(text[max(0, m.start() - 6):m.start()])
        if pm:
            num_start = m.start() - len(pm.group(0))
            prefix_unit = UNIT_CANON.get(pm.group(2).lower(), pm.group(2))
            if pm.group(1) in ("-", "−") and not digits.startswith(("-", "−", "+")):
                neg_prefix = True
        if not free(num_start, m.end()):
            continue
        end = m.end()
        if not prefix_unit and text[end:end + 1] in ("х", "x"):
            dm = DIM_RX.match(text, end)
            if dm:
                # «160х200» is two numbers: «160 × 200». The unit belongs to the second one.
                first = read_number(m.start(), digits, glued=False)
                if first is None:
                    continue
                value, unit, end1 = first
                facts.items.append(Fact("number", value, text[m.start():end1], sent_of(m.start()),
                                        m.start(), hedge_before(m.start()), ""))
                second = read_number(end + 1, dm.group(1))
                if second is None:
                    continue
                value2, unit2, end2 = second
                facts.items.append(Fact("number", value2, text[end + 1:end2], sent_of(m.start()),
                                        end + 1, hedge_before(end + 1), unit2))
                take(m.start(), end2)
                continue
        got = read_number(m.start(), digits, prefix_unit=prefix_unit)
        if got is None:
            continue
        value, unit, end = got
        if neg_prefix and value != "0":
            value = value[1:] if value.startswith("-") else "-" + value
        if not unit and prefix_unit:
            unit = prefix_unit
        facts.items.append(Fact("number", value, text[num_start:end], sent_of(num_start),
                                num_start, hedge_before(num_start), unit))
        take(num_start, end)
    flush_taken()
    for m in COMPOUND_NUM_RX.finditer(norm_text):
        if free(m.start(), m.end()):
            v = float(COMPOUND_NUM[m.group(1).lower()])
            unit = COMPOUND_UNIT[m.group(2).lower()]
            facts.items.append(Fact("number", _fmt(v), text[m.start():m.end()], sent_of(m.start()),
                                    m.start(), hedge_before(m.start()), unit))
            take(m.start(), m.end())
    flush_taken()
    word_rx = re.compile(r"(?<![а-яё])(%s)(?![а-яё])" % "|".join(
        sorted(WORD_NUM, key=len, reverse=True)), re.I)
    for m in word_rx.finditer(norm_text):
        if not free(m.start(), m.end()):
            continue
        v = float(WORD_NUM[m.group(1).lower()])
        end = m.end()
        # "двадцать пять", "сто двадцать" are one number: each next word is a smaller order.
        while True:
            nxt = re.match(r"[ \u00a0]+(%s)(?![а-яё])" % "|".join(
                sorted(list(WORD_NUM) + list(ONE_FORMS), key=len, reverse=True)), norm_text[end:end + 20], re.I)
            if not nxt:
                break
            w = float(WORD_NUM.get(nxt.group(1).lower(), 1))
            last_order = 100 if v % 100 == 0 and v >= 100 else (10 if v % 10 == 0 and v >= 20 else 1)
            if last_order == 1 or w >= last_order or w != int(w):
                break
            v += w
            end += nxt.end()
        sc = re.match(r"[ \u00a0\u202f]+(%s)(?![а-я])" % SCALE_ALT, text[end:end + 12], re.I)
        if sc:
            v *= SCALE[sc.group(1).lower()]
            end += sc.end()
        unit = ""
        um = UNIT_RX.match(text, end)  # "пять рублей" → "пять долларов" is a unit change too
        if um:
            unit = upgrade_pound(UNIT_CANON.get(um.group(1).lower(), ""), m.start())
            end = um.end()
        facts.items.append(Fact("number", _fmt(v), text[m.start():end], sent_of(m.start()),
                                m.start(), hedge_before(m.start()), unit))
        take(m.start(), end)
    flush_taken()
    # Unspaced numeric ranges («$20–30», «20–30 долларов», «$1.50–2.50») and «от X до Y <unit>»
    # share one unit across both bounds without touching spaced clause dashes («Заказ 15 — 300 ₽»).
    num_idxs = [i for i, f in enumerate(facts.items) if f.kind == "number" and f.unit != "время"]
    num_idxs.sort(key=lambda i: facts.items[i].pos)
    for idx_pos in range(len(num_idxs) - 1):
        i1, i2 = num_idxs[idx_pos], num_idxs[idx_pos + 1]
        f1, f2 = facts.items[i1], facts.items[i2]
        if f1.sent != f2.sent:
            continue
        between = text[f1.pos + len(f1.raw):f2.pos]
        if re.fullmatch(r"[–—-]", between):
            if f1.unit and not f2.unit:
                facts.items[i2] = replace(f2, unit=f1.unit)
            elif f2.unit and not f1.unit:
                facts.items[i1] = replace(f1, unit=f2.unit)
        elif (f2.unit and not f1.unit and f1.hedge in ("от", "с")
              and re.fullmatch(r"[ \t\u00a0]+(?:до|по)[ \t\u00a0]+", between, re.I)):
            facts.items[i1] = replace(f1, unit=f2.unit)
    # END_BLOCK_NUMBERS

    # START_BLOCK_NAMES_QUOTES
    # «…», „…“, “…” up to a paragraph (an interview answer is long) and straight "…" up to 80
    # characters; a straight mark after a digit or letter is inches (27").
    quote_rx = r"«([^»\n]{1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)\"(?!\s)([^\"\n]{1,80})(?<!\s)\""
    dash_after_rx = re.compile(r"[*_]*(,?)[ \t]+[—–-][ \t]")
    line_em_rx = re.compile(r"[ \t>*_]*[—–][ \t]*")
    line_hy_rx = re.compile(r"[ \t>*_]*-[ \t]*")
    for m in re.finditer(quote_rx, text):
        q = next(g for g in m.groups() if g).strip()
        # Somebody's words: ответил: «…»; «…», — сказал; «…?» — спросил (before the author's
        # dash the speech ends with a comma or with ?!… inside the marks; «…» — чем is not speech);
        # a line that opens with a dash and the quote is a dialogue or interview answer.
        # Quoted words inside a phrase are often terms, irony or examples a rewrite may rephrase.
        dash = dash_after_rx.match(text[m.end():m.end() + 8])
        speech = bool(text[max(0, m.start() - 8):m.start()].rstrip(" \t*_").endswith(":") or
                      (dash and (dash.group(1) or q.endswith(("?", "!", "…")))))
        if not speech:
            k_left = m.start() - 1
            while k_left >= 0 and text[k_left] in " \t>*_—–-":
                k_left -= 1
            if k_left < 0 or text[k_left] == "\n":
                line_start = text[k_left + 1:m.start()]
                if line_em_rx.fullmatch(line_start):
                    speech = True
                elif line_hy_rx.fullmatch(line_start):
                    k_right = m.end()
                    while k_right < len(text) and text[k_right] in ".!?…*_ \t":
                        k_right += 1
                    speech = (k_right == len(text) or text[k_right] == "\n")
        facts.items.append(Fact("quote", q.lower(), q, sent_of(m.start()), m.start(), speech=speech))
    for s_start, sent in sents:
        # Latin acronyms of any length; Cyrillic ones up to 4 letters (США, РФ, МЧС), longer
        # all-caps words are usually shouting ("ВНИМАНИЕ").
        for m in NAME_RX.finditer(sent):
            word = m.group(1)
            pos = s_start + m.start()
            if word.lower() in UNIT_CANON and not free(pos, pos + len(word)):
                continue
            first = _is_initial(text, pos)
            if word in SENT_START_STOP or POLITE_PRONOUN.fullmatch(word):
                continue
            if first and not (_capitalized_elsewhere(word, text, pos) or _norm(word.lower()) in FIRST_NAME_FORMS):
                # Sentence subject in capitals ("Капучино дорожает"): kept only as an anchor
                # for "who got which number", not as a name that must survive.
                facts.items.append(Fact("subject", word, word, sent_of(pos), pos))
                continue
            facts.items.append(Fact("name", word, word, sent_of(pos), pos))
    # END_BLOCK_NAMES_QUOTES

    # START_BLOCK_NEGATIONS
    # A short preposition between: "не на карту", "не в офисе" negate the next word.
    neg_rx = (r"(?<![а-яё])(не|ни|без)\s+(?:(?:на|в|во|к|ко|с|со|по|за|до|от|из|у|о|об)\s+)?([а-яё]{3,})"
              r"|(?<![а-яё])(нет|нельзя)(?![а-яё])")
    low = _norm(text.lower())
    low_stops = [sm.start() for sm in re.finditer(r"[.!?\n]", low)]
    for m in re.finditer(neg_rx, low):
        if m.group(1):
            # A contrast ("а не в феврале", "не с кофе, а с сигареты") is the "не X, а Y" pattern a
            # rewrite removes on purpose: "хотя раньше планировали в феврале" keeps the meaning.
            si = bisect.bisect_left(low_stops, m.end())
            s_end = low_stops[si] if si < len(low_stops) else len(low)
            contrast = bool(re.search(r"(?:^|[^а-яё])а\s+$", low[max(0, m.start() - 4):m.start()]) or
                            re.search(r",\s*а\s", low[m.end():min(s_end, m.end() + 240)]))
            polar_li = bool(not contrast and m.group(1) == "не"
                            and re.match(r"\s+ли(?![а-яё])", low[m.end():m.end() + 8]))
            neg_kind = "contrast" if contrast else ("polar_li" if polar_li else "")
            facts.items.append(Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(),
                                    hedge=m.group(1), unit=neg_kind))
        else:
            facts.items.append(Fact("negation", m.group(3), m.group(), sent_of(m.start()), m.start(),
                                    hedge=m.group(3)))
    # END_BLOCK_NEGATIONS

    # START_BLOCK_CODE
    # Code is carried as is: `inline code` and fenced blocks, compared with spaces collapsed.
    # Chat answers often wrap the whole text or a diagram in ``` (a README, HTML, "Запрос → ответ"),
    # and the rewrite edits it: only a block that looks like code (under 30% Cyrillic letters)
    # becomes a "code_block" fact, and its loss is a check.
    def _code(s: str) -> str:
        return " ".join(s.split())
    masked_parts: List[str] = []
    m_pos = 0
    for m in re.finditer(r"^```[^\n]*\n(.*?)^```[ \t]*\r?$", text, re.S | re.M):
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", m.group(1))
        cyr = sum(1 for x in letters if x > "z")
        if _code(m.group(1)) and cyr < 0.3 * max(1, len(letters)):
            facts.items.append(Fact("code_block", _code(m.group(1)), m.group(1).strip(),
                                    sent_of(m.start()), m.start()))
        masked_parts.append(text[m_pos:m.start()])
        masked_parts.append(" " * (m.end() - m.start()))
        m_pos = m.end()
    masked_parts.append(text[m_pos:])
    masked = "".join(masked_parts)
    for m in re.finditer(r"`([^`\n]+)`", masked):
        if _code(m.group(1)):
            facts.items.append(Fact("code", _code(m.group(1)), m.group(1), sent_of(m.start()), m.start()))
    # END_BLOCK_CODE
    return facts


class _TextIndex:
    """One text, read once: the words by their first three letters and the ends of the
    sentences. A long text is checked once per word, not once per mention (4.2.1: the negation
    check took 23 s on a text of 97 000 characters)."""

    def __init__(self, text: str):
        self.text = text
        self.stops = [m.start() for m in re.finditer(r"[.!?\n]", text)]
        self.buckets: Dict[str, List[Tuple[int, int, str]]] = {}
        for m in re.finditer(r"[а-яё]{3,}", text):
            self.buckets.setdefault(m.group()[:3], []).append((m.start(), m.end(), m.group()))
        self._occ: Dict[str, List[Tuple[int, int]]] = {}
        self._neg: Dict[str, List[bool]] = {}
        self._instead: Dict[str, List[bool]] = {}
        self._all_neg: Dict[str, bool] = {}
        self._none_neg: Dict[str, bool] = {}
        self._all_inst: Dict[str, bool] = {}
        self._neg_words: Optional[Dict[str, List[str]]] = None
        self._neg_word: Dict[str, bool] = {}
        self._ne_pref: Optional[Dict[str, List[str]]] = None
        self._ne_count: Dict[str, int] = {}

    def occurrences(self, word: str) -> List[Tuple[int, int]]:
        """The places of the text where the word stands (in any case)."""
        got = self._occ.get(word)
        if got is None:
            got = [(a, b) for a, b, w in self.buckets.get(word[:3], ())
                   if not (w in ("больше", "меньше") and word not in ("больше", "меньше"))
                   and stem_match(w, word, strict=True)]
            self._occ[word] = got
        return got

    def negated(self, word: str) -> List[bool]:
        """For every place of the word: a negation stands near it."""
        got = self._neg.get(word)
        if got is None:
            got = [self.negated_at(a, b) for a, b in self.occurrences(word)]
            self._neg[word] = got
        return got

    def instead(self, word: str) -> List[bool]:
        """For every place of the word: «вместо того чтобы» stands in its left window."""
        got = self._instead.get(word)
        if got is None:
            got = [self.instead_at(a, b) for a, b in self.occurrences(word)]
            self._instead[word] = got
        return got

    def all_negated(self, word: str) -> bool:
        got = self._all_neg.get(word)
        if got is None:
            got = all(self.negated(word))
            self._all_neg[word] = got
        return got

    def none_negated(self, word: str) -> bool:
        got = self._none_neg.get(word)
        if got is None:
            got = not any(self.negated(word))
            self._none_neg[word] = got
        return got

    def all_instead(self, word: str) -> bool:
        """Every mention of the word without a negation stands after «вместо того чтобы»."""
        got = self._all_inst.get(word)
        if got is None:
            plain = [i for i, n in zip(self.instead(word), self.negated(word)) if not n]
            got = bool(plain) and all(plain)
            self._all_inst[word] = got
        return got

    def negation_words(self) -> Dict[str, List[str]]:
        """The words that stand right after a negation («не покупать»), by their first three
        letters."""
        if self._neg_words is None:
            buckets: Dict[str, List[str]] = {}
            for m in re.finditer(r"(?<![а-яё])(не|ни|без|нет|нельзя)\s+(?:[а-яё]+\s+){0,2}([а-яё]{3,})",
                                 self.text):
                buckets.setdefault(m.group(2)[:3], []).append(m.group(2))
            self._neg_words = buckets
        return self._neg_words

    def negated_word(self, word: str) -> bool:
        """The word stands right after a negation somewhere in the text."""
        got = self._neg_word.get(word)
        if got is None:
            got = any(stem_match(w, word, strict=True)
                      for w in self.negation_words().get(word[:3], ()))
            self._neg_word[word] = got
        return got

    def ne_prefix_count(self, word: str) -> int:
        got = self._ne_count.get(word)
        if got is None:
            if self._ne_pref is None:
                buckets: Dict[str, List[str]] = {}
                for m in re.finditer(r"(?<![а-яё])не([а-яё]{4,})", self.text):
                    buckets.setdefault(m.group(1)[:3], []).append(m.group(1))
                self._ne_pref = buckets
            got = sum(1 for w in self._ne_pref.get(word[:3], ())
                      if stem_match(w, word, strict=True) and name_match(w, word))
            self._ne_count[word] = got
        return got

    def sentence(self, start: int, end: int) -> Tuple[int, int]:
        """The bounds of the sentence that holds the place."""
        i = bisect.bisect_left(self.stops, start)
        s_from = self.stops[i - 1] + 1 if i else 0
        j = bisect.bisect_left(self.stops, end)
        s_to = self.stops[j] if j < len(self.stops) else len(self.text)
        return s_from, s_to

    def negated_at(self, start: int, end: int) -> bool:
        """A negation within 3 words before or 4 words after, inside the same sentence."""
        s_from, s_to = self.sentence(start, end)
        txt = self.text
        i = start
        for _ in range(3):
            while i > s_from and txt[i - 1].isspace():
                i -= 1
            if i <= s_from:
                break
            w_end = i
            while i > s_from and not txt[i - 1].isspace():
                i -= 1
            if w_end - i <= 24 and re.sub(r"[^а-яё]", "", txt[i:w_end]) in NEG_WORDS:
                return True
        j = end
        for _ in range(4):
            while j < s_to and txt[j].isspace():
                j += 1
            if j >= s_to:
                break
            w_start = j
            while j < s_to and not txt[j].isspace():
                j += 1
            if j - w_start <= 24 and re.sub(r"[^а-яё]", "", txt[w_start:j]) in NEG_WORDS:
                return True
        return False

    def instead_at(self, start: int, end: int) -> bool:
        """«Вместо того чтобы» right before the word: the refusal was reworded, not lost.
        «Вместо писем отправляйте» is not one: there «вместо» rejects the letters."""
        s_from, _ = self.sentence(start, end)
        return bool(re.search(r"(?<![а-яё])вместо\s+того,?\s+чтобы\s+$", self.text[max(s_from, start - 48):start]))


# The indexes of the texts of the last comparison; they are dropped when it ends.
_INDEXES: Dict[int, Tuple[str, _TextIndex]] = {}


def _index(text: str) -> _TextIndex:
    got = _INDEXES.get(id(text))
    if got is not None and got[0] is text:
        return got[1]
    made = _TextIndex(text)
    _INDEXES[id(text)] = (text, made)
    return made


FOOTNOTE_MARK_RX = re.compile(
    r"\[(?:\d{1,4}(?:[ \t\u00a0]*[,;–—-][ \t\u00a0]*(?:(?:с|стр|т|ч|вып|кн)\.?[ \t\u00a0]*)?\d{1,4})*)\]$|\(\d{1,3}\)$",
    re.I
)
LIST_NUM_RX = re.compile(r"\d+[.)]")


def _is_initial(text: str, pos: int) -> bool:
    """True when only markup, list markers, emoji or spaces stand between the word and the
    start of a line or the end of the previous sentence. A footnote or ГОСТ citation mark
    («болота.[1] Там», «опытами.[14, с. 52] Однако») stands between sentences, not inside one."""
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch == "\n" or ch in ".!?…:":
            return True
        if ch in "])":
            mark = FOOTNOTE_MARK_RX.search(text[max(0, i - 32):i + 1])
            if mark:
                i -= len(mark.group())  # step back over the whole mark and keep looking
                continue
        if ch.isalnum() and not (ch.isdigit() and LIST_NUM_RX.match(text[i:min(pos, i + 16)])):
            return False
        if ch.isalpha():
            return False
        i -= 1
    return True


# The capitalised words of a text that stand not at the start of a sentence, by their first
# three letters: a sentence-initial word is a name when the same name stands elsewhere.
_CAP_WORDS: Dict[int, Tuple[str, Dict[str, List[Tuple[int, str]]]]] = {}


def _cap_words(text: str) -> Dict[str, List[Tuple[int, str]]]:
    got = _CAP_WORDS.get(id(text))
    if got is not None and got[0] is text:
        return got[1]
    buckets: Dict[str, List[Tuple[int, str]]] = {}
    for m in NAME_RX.finditer(text):
        if _is_initial(text, m.start()):
            continue
        buckets.setdefault(_norm(m.group(1).lower())[:3], []).append((m.start(), m.group(1)))
    _CAP_WORDS[id(text)] = (text, buckets)
    return buckets


def _capitalized_elsewhere(word: str, text: str, pos: int) -> bool:
    """The same name stands elsewhere in another case («Сбер» … «Сбера»). A shared prefix is
    not enough: «То» is not «Томске» and «Там» is not «Тамара»."""
    for start, other in _cap_words(text).get(_norm(word.lower())[:3], ()):
        if start == pos:
            continue
        if _same_name_case(word, other):
            return True
    return False


# utm_source values chat assistants add to the links they cite (ru.wikipedia,
# «Признаки сгенерированности текста», UTM-метки, revision of 2026-10-08, plus verified domain
# tags of 2025-2026 chat assistants). Any other utm tag is the author's own (newsletter, campaign)
# and belongs to the link.
ASSISTANT_UTM_SOURCES = frozenset({
    "chatgpt.com", "openai", "copilot.com", "perplexity.ai",
    "claude.ai", "gemini.google.com", "grok.com",
    "chat.deepseek.com", "deepseek.com",
})


def _is_assistant_utm(param: str) -> bool:
    key, _, value = param.partition("=")
    return key.lower() == "utm_source" and unquote(value).strip().lower() in ASSISTANT_UTM_SOURCES


def strip_utm(url: str) -> Tuple[str, int]:
    """Drop the assistant's utm_source tail, keep the author's utm tags, other parameters,
    the '?' (when something is left) and the fragment."""
    try:
        parts = urlsplit(url)
    except ValueError:  # a bracketed IPv6 host the link pattern cut short: leave it as is
        return url, 0
    if not parts.query:
        return url, 0
    # A link copied from HTML keeps "&amp;" between its parameters.
    sep = "&amp;" if "&amp;" in parts.query else "&"
    params = re.split(r"&(?:amp;)?", parts.query)
    kept = [x for x in params if not _is_assistant_utm(x)]
    if len(kept) == len(params):
        return url, 0
    return urlunsplit(parts._replace(query=sep.join(kept))), len(params) - len(kept)


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF or 0x2190 <= cp <= 0x21FF or 0x25A0 <= cp <= 0x25FF
            or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139,
                      0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299)
            or 0x1F3FB <= cp <= 0x1F3FF)


def _strip_invisibles(chunk: str, prev_ch: str = "", next_ch: str = "") -> Tuple[str, int]:
    def _ignorable_ahead(cp: int) -> bool:
        return (cp in INVISIBLE_CPS or cp in SPACE_SPOOFERS or cp in (0x200D, 0x200C)
                or 0xFE00 <= cp <= 0xFE0F or 0xE0000 <= cp <= 0xE007F or 0xE0100 <= cp <= 0xE01EF)

    next_kept_pos = -1

    def _next_kept(idx: int) -> str:
        nonlocal next_kept_pos
        if next_kept_pos < idx:
            next_kept_pos = idx
            while next_kept_pos < len(chunk) and _ignorable_ahead(ord(chunk[next_kept_pos])):
                next_kept_pos += 1
        return chunk[next_kept_pos] if next_kept_pos < len(chunk) else next_ch

    out = []
    removed = 0
    in_flag = False
    for i, ch in enumerate(chunk):
        cp = ord(ch)
        if in_flag and 0xE0020 <= cp <= 0xE007F:
            out.append(ch)
            if cp == 0xE007F:
                in_flag = False
            continue
        in_flag = cp in (0x1F3F4, 0x1F3F3)
        if cp in SPACE_SPOOFERS:
            removed += 1
            left_c = out[-1] if out else prev_ch
            if left_c and left_c not in _WS:
                right_c = _next_kept(i + 1)
                if right_c and right_c not in _WS:
                    out.append(" ")
            continue
        if (cp in INVISIBLE_CPS or 0xFE00 <= cp <= 0xFE0E
                or 0xE0000 <= cp <= 0xE007F or 0xE0100 <= cp <= 0xE01EF):
            removed += 1
            continue
        if cp == 0xFE0F:
            left_c = out[-1] if out else prev_ch
            right_c = _next_kept(i + 1)
            if ((left_c and _is_emoji(left_c))
                    or (left_c in "0123456789#*" and right_c == "\u20e3")):
                out.append(ch)
                continue
            removed += 1
            continue
        if cp == 0x200D:
            if out:
                prev_ok = _is_emoji(out[-1]) or (out[-1] == "\ufe0f" and (
                    (len(out) >= 2 and _is_emoji(out[-2]))
                    or (len(out) == 1 and bool(prev_ch) and _is_emoji(prev_ch))
                ))
            else:
                prev_ok = bool(prev_ch) and _is_emoji(prev_ch)
            right_c = _next_kept(i + 1)
            if prev_ok and right_c and _is_emoji(right_c):
                out.append(ch)
                continue
            removed += 1
            continue
        out.append(ch)
    return "".join(out), removed


def _is_ident_char(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9") or ("а" <= c <= "я") or ("А" <= c <= "Я") or c in "_$ёЁ"


def _code_literal_spans(body: str, allow_backtick: bool) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    n = len(body)
    i = 0
    prev_sig = "\n"
    prev_word_start = -1
    prev_word_end = -1
    regex_fail_until = -1
    while i < n:
        ch = body[i]
        if ch in " \t\f\v":
            i += 1
            continue
        if ch in "\r\n":
            prev_sig = "\n"
            prev_word_start = prev_word_end = -1
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = body[i + 1]
            if nxt == "/" and (i == 0 or body[i - 1] != ":"):
                nl = body.find("\n", i + 2)
                i = n if nl < 0 else nl
                continue
            if nxt == "*":
                end_c = body.find("*/", i + 2)
                if end_c < 0:
                    break
                prev_sig = " "
                prev_word_start = prev_word_end = -1
                i = end_c + 2
                continue
        if ch in ("'", '"') and body[i:i + 3] == ch * 3:
            end_q = body.find(ch * 3, i + 3)
            if end_q >= 0:
                spans.append((i, end_q + 3))
                prev_sig = ch
                prev_word_start = prev_word_end = -1
                i = end_q + 3
            else:
                prev_sig = ch
                prev_word_start = prev_word_end = -1
                i += 3
            continue
        if ch in ("'", '"'):
            k = i + 1
            closed = False
            while k < n:
                ck = body[k]
                if ck == "\\" and k + 1 < n and body[k + 1] != "\n":
                    k += 2
                    continue
                if ck == ch:
                    closed = True
                    k += 1
                    break
                if ck in "\r\n":
                    break
                k += 1
            if closed:
                spans.append((i, k))
            prev_sig = ch
            prev_word_start = prev_word_end = -1
            i = k
            continue
        if allow_backtick and ch == "`":
            k = i + 1
            closed = False
            while k < n:
                ck = body[k]
                if ck == "\\" and k + 1 < n:
                    k += 2
                    continue
                if ck == "`":
                    closed = True
                    k += 1
                    break
                k += 1
            if closed:
                spans.append((i, k))
            prev_sig = "`"
            prev_word_start = prev_word_end = -1
            i = k
            continue
        if ch == "/" and i >= regex_fail_until:
            prev_kw = prev_word_end > prev_word_start and body[prev_word_start:prev_word_end] in _REGEX_KW
            if prev_sig in _REGEX_PREV or prev_kw:
                k = i + 1
                in_cls = False
                closed_rx = False
                while k < n:
                    ck = body[k]
                    if ck in "\r\n":
                        break
                    if ck == "\\" and k + 1 < n and body[k + 1] not in "\r\n":
                        k += 2
                        continue
                    if ck == "[":
                        in_cls = True
                    elif ck == "]" and in_cls:
                        in_cls = False
                    elif ck == "/" and not in_cls:
                        closed_rx = True
                        break
                    k += 1
                if closed_rx and k > i + 1:
                    f_end = k + 1
                    seen_f = set()
                    valid_f = True
                    while f_end < n and body[f_end] in _REGEX_FLAGS:
                        if body[f_end] in seen_f:
                            valid_f = False
                            break
                        seen_f.add(body[f_end])
                        f_end += 1
                    after_c = body[f_end] if f_end < n else ""
                    if valid_f and not (after_c and (_is_ident_char(after_c) or after_c == "/")):
                        spans.append((i, f_end))
                        prev_sig = "/"
                        prev_word_start = prev_word_end = -1
                        i = f_end
                        continue
                regex_fail_until = k
        if _is_ident_char(ch) and not ("0" <= ch <= "9"):
            ws = i
            i += 1
            while i < n and _is_ident_char(body[i]):
                i += 1
            prev_sig = body[i - 1]
            prev_word_start, prev_word_end = ws, i
            continue
        prev_sig = ch
        prev_word_start = prev_word_end = -1
        i += 1
    return spans


def _code_spans(s: str) -> List[Tuple[int, int]]:
    fences = []
    for m in re.finditer(r"(?ms)^```[^\n]*\n.*?^```[ \t]*\r?$", s):
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", m.group(0))
        if sum(1 for x in letters if x > "z") < 0.3 * max(1, len(letters)):
            fences.append((m.start(), m.end()))
    fence_starts = [fs for fs, _ in fences]
    spans = list(fences)
    for m in re.finditer(r"`[^`\n]+`", s):
        idx = bisect.bisect_right(fence_starts, m.start()) - 1
        if idx < 0 or m.start() >= fences[idx][1]:
            spans.append((m.start(), m.end()))
    spans.sort()
    return spans


def _strip_code_invisibles(code: str) -> Tuple[str, int]:
    if code.startswith("```"):
        nl = code.find("\n")
        last_nl = code.rfind("\n")
        if 0 <= nl < last_nl:
            head, body, tail, allow_bt = code[:nl + 1], code[nl + 1:last_nl], code[last_nl:], True
        else:
            head, body, tail, allow_bt = "", code, "", False
    elif len(code) >= 2 and code[0] == "`" and code[-1] == "`":
        head, body, tail, allow_bt = "`", code[1:-1], "`", False
    else:
        head, body, tail, allow_bt = "", code, "", False
    sub_parts, c_pos = [], 0
    for s, e in _code_literal_spans(body, allow_bt):
        sub_parts += [body[c_pos:s], body[s:e]]
        c_pos = e
    sub_parts.append(body[c_pos:])
    sub_parts[0] = head + sub_parts[0]
    sub_parts[-1] = sub_parts[-1] + tail
    removed = 0
    for j in range(0, len(sub_parts), 2):
        seg = sub_parts[j]
        if not seg:
            continue
        prev_c = sub_parts[j - 1][-1] if j > 0 and sub_parts[j - 1] else ""
        next_c = sub_parts[j + 1][0] if j + 1 < len(sub_parts) and sub_parts[j + 1] else ""
        seg, n = _strip_invisibles(seg, prev_c, next_c)
        sub_parts[j] = seg
        removed += n
    return "".join(sub_parts), removed


def _strip_prose_stress(s: str) -> str:
    if "\u0301" not in s:
        return s
    parts, pos = [], 0
    for a, b in _code_spans(s):
        parts += [PROSE_STRESS_RX.sub(lambda m: "" if m.group(1) else m.group(0), s[pos:a]), s[a:b]]
        pos = b
    parts.append(PROSE_STRESS_RX.sub(lambda m: "" if m.group(1) else m.group(0), s[pos:]))
    return "".join(parts)


def _strip_tracking(text: str, keep_stress: bool = False) -> str:
    def fix_url(m: "re.Match") -> str:
        url = m.group(0)
        tail = url[len(url.rstrip(URL_TAIL)):]
        return strip_utm(url[:len(url) - len(tail)])[0] + tail

    def fix_homo(m: "re.Match") -> str:
        word = m.group(1)
        return m.group(0) if word is None else unicodedata.normalize("NFC", word.translate(HOMOGLYPH_TRANS))

    # Code blocks (<30% Cyrillic) and `inline code` keep citations, links, homoglyphs and literals
    # untouched; unquoted paste invisibles and prose ``` blocks are cleaned.
    for _ in range(3):
        spans = _code_spans(text)
        parts, pos = [], 0
        for s, e in spans:
            parts += [text[pos:s], text[s:e]]
            pos = e
        parts.append(text[pos:])
        changed = False
        for i in range(1, len(parts), 2):
            parts[i], inv_c = _strip_code_invisibles(parts[i])
            if inv_c:
                changed = True
        for i in range(0, len(parts), 2):
            chunk = parts[i]
            if not chunk:
                continue
            prev_ch = parts[i - 1][-1] if i > 0 and parts[i - 1] else ""
            next_ch = parts[i + 1][0] if i + 1 < len(parts) and parts[i + 1] else ""
            for _ in range(4):
                step = 0
                while True:
                    chunk, n = CITATION_RX.subn("", chunk)
                    step += n
                    if not n:
                        break
                before_url = chunk
                chunk = re.sub(URL_RX, fix_url, chunk)
                if chunk != before_url:
                    step += 1
                chunk, inv_n = _strip_invisibles(chunk, prev_ch, next_ch)
                if step or inv_n:
                    changed = True
                if not step and not inv_n:
                    break
            normed = unicodedata.normalize("NFC", PROSE_HOMO_RX.sub(fix_homo, chunk))
            out_chunk = normed if keep_stress else PROSE_STRESS_RX.sub(
                lambda m: "" if m.group(1) else m.group(0), normed
            )
            if out_chunk != parts[i]:
                changed = True
            parts[i] = out_chunk
        text = "".join(parts)
        if not changed or "`" not in text:
            break
    return text


def _pair_dot_decimals(mine: Facts, other: Facts) -> List[Dict]:
    """"1.15" reads as a time (1:15), "1,15" as a decimal. Mentions of a dot "time" that the other
    side lacks are paired, one by one, with decimals of the same digits that this side lacks
    («коэффициент 1.15» → «коэффициент 1,15», «в 2.10 раза» → «в 2,10 раза»): those facts take the
    decimal value and lose the time unit, in place, so the bindings block sees the same values on
    both sides. Each pairing is a check (it may also be a time that became a number). A real time
    keeps its reading: «14.30» → «14:30»; a time and a coefficient of the same digits pair by count
    and sentence context."""
    def count(facts: Facts, value: str) -> int:
        return sum(1 for f in facts.items if f.kind == "number" and f.value == value)

    def stems(facts: Facts, f: Fact) -> set:
        names = {_norm(x.value.lower()) for x in facts.items if x.kind in ("name", "subject") and x.sent == f.sent}
        out = {_norm(w.lower())[:4] for w in re.findall(r"[а-яё]{4,}", facts.sentences[f.sent], re.I)
               if _norm(w.lower()) not in names}
        if f.hedge:
            out.add("#" + HEDGE_SAME.get(f.hedge, f.hedge))
        return out

    dots: Dict[str, List[int]] = {}
    for i, f in enumerate(mine.items):
        if f.kind == "number" and f.unit == "время" and "." in f.raw:
            dots.setdefault(f.value, []).append(i)
    checks = []
    for value, idxs in dots.items():
        num = _canon_num(mine.items[idxs[0]].raw)
        if num is None:
            continue
        alt = _fmt(num)
        n = min(count(mine, value) - count(other, value), count(other, alt) - count(mine, alt), len(idxs))
        if n <= 0:
            continue
        twin = next(f.raw for f in other.items if f.kind == "number" and f.value == alt)
        if len(idxs) > n:
            dec_stems = set().union(*(stems(other, d) for d in other.items if d.kind == "number" and d.value == alt))
            time_stems = set().union(*(stems(other, t) for t in other.items if t.kind == "number" and t.value == value))
            other_order = [f.value == alt for f in other.items if f.kind == "number" and f.value in (alt, value)]

            def rank(pair: Tuple[int, int]) -> tuple:
                k, idx = pair
                f = mine.items[idx]
                sent = mine.sentences[f.sent]
                off = f.pos - mine.starts[f.sent]
                before_f = _norm(sent[:off].rstrip().lower())
                after_f = _norm(sent[off + len(f.raw):].lstrip().lower())
                time_prep = bool(re.search(r"(?<![а-яё])(?:в|к|до|после|с)$", before_f) and
                                 not re.match(r"раз(?:а|у|ом|е)?(?![а-яё])", after_f))
                st = stems(mine, f)
                score = len(st & dec_stems) - len(st & time_stems)
                pos_hint = not (k < len(other_order) and other_order[k])
                return (time_prep, -score, pos_hint, idx)

            chosen = [idx for _, idx in sorted(enumerate(idxs), key=rank)[:n]]
        else:
            chosen = idxs
        for i in chosen:
            f = mine.items[i]
            mine.items[i] = replace(f, value=alt, unit="")
            checks.append({"kind": "unit", "what": "число",
                           "detail": "%s и %s сверены как одно число: проверь, что это не время" % (f.raw, twin)})
    return checks


def _service_regions(before: str, after_norm: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """The parts of the source that are the chat assistant's own lines around the text: the
    head («Готово, вот текст:»), parenthetical length notes («(≈253 знака…)») and the tail
    («Если нужно, могу переделать текст…», «Пара уточнений: …»). Their values are not facts of
    the text. Returns (all_spans, tail_spans).
    G1: a span counts only when the edit does not keep its beginning: a wrapper the edit kept
    is still the author's text, and a fact lost with it is an error."""
    seps = list(SERVICE_SEP_RX.finditer(before))
    parts: List[Tuple[int, int]] = []
    prev = 0
    if seps:
        for m in seps:
            parts.append((prev, m.start()))
            prev = m.end()
        parts.append((prev, len(before)))
        head_rx = SERVICE_HEAD_RX
    else:
        for m in re.finditer(r"\n[ \t]*\n", before):
            parts.append((prev, m.start()))
            prev = m.end()
        parts.append((prev, len(before)))
        head_rx = SERVICE_HEAD_STRICT_RX
    spans: List[Tuple[int, int]] = []
    tails: List[Tuple[int, int]] = []
    # The head: the first part, when it is one short line that opens like a chat answer.
    if len(parts) > 1:
        body = before[parts[0][0]:parts[0][1]].strip()
        about = SERVICE_SIZE_RX.search(body) or body.rstrip("*_ ").endswith(":")
        if len(body) <= 300 and "\n" not in body and head_rx.match(body) and about:
            spans.append(parts[0])
    # The tail: walk back from the last part while it talks like the assistant.
    i = len(parts) - 1
    while i >= 0:
        body = before[parts[i][0]:parts[i][1]].strip()
        if not SERVICE_TAIL_RX.match(body.split("\n", 1)[0]):
            break
        if not SERVICE_ABOUT_RX.search(body) or (not seps and not SERVICE_FIRST_RX.search(body)):
            break
        spans.append(parts[i])
        tails.append(parts[i])
        i -= 1
    # G1: the edit kept the beginning of the span: the values there are still facts.
    kept = []
    for a, b in spans:
        key = _norm(before[a:b].lower())[:20]
        if key and key not in after_norm:
            kept.append((a, b))
    kept_tails = [sp for sp in tails if sp in kept]
    # Parenthetical length notes in the first or last part («**Инструкция** (~241 знак):»,
    # «(≈253 знака с пробелами…)»): even when the heading itself stays, the dropped size note is service.
    if len(parts) > 1:
        for pa, pb in (parts[0], parts[-1]):
            part_str = before[pa:pb]
            if ")" not in part_str:
                continue
            for pm in SERVICE_PAREN_RX.finditer(part_str):
                line_s = part_str.rfind("\n", 0, pm.start()) + 1
                line_e_pos = part_str.find("\n", pm.end())
                line_e = len(part_str) if line_e_pos < 0 else line_e_pos
                line = part_str[line_s:line_e].strip()
                is_standalone = bool(re.fullmatch(r"[*_ \t]*\([^)\n]+\)\.?[*_ \t]*", line))
                is_heading_note = (
                    len(line) <= 160
                    and (line.startswith(("#", "**", "__")) or line.rstrip("*_ \t").endswith(":"))
                    and part_str[pm.end():line_e].strip("*_ \t:") == ""
                )
                if not (is_standalone or is_heading_note):
                    continue
                sa, sb = pa + pm.start(), pa + pm.end()
                if any(a <= sa and sb <= b for a, b in kept):
                    continue
                key = _norm(before[sa:sb].lower())[:20]
                if key and key not in after_norm:
                    kept.append((sa, sb))
    return kept, kept_tails


def _service_spans(before: str, after_norm: str) -> List[Tuple[int, int]]:
    return _service_regions(before, after_norm)[0]


def _is_item_verb(w: str) -> bool:
    if ITEM_COPULA_RX.match(w) or ITEM_INTRO_VERB_RX.match(w):
        return True
    if re.search(r"(?:ться|тся|лся|лась|лось|лись|ает|яет|ует|еет|ают|яют|уют|еют|йте|йтесь)$", w):
        return True
    if len(w) >= 5 and w not in ITEM_NOUN_LI and re.search(r"[аеиоуыя]ли$", w):
        return True
    return False


def _item_word_match(a: str, b: str) -> bool:
    a, b = _norm(a.lower()), _norm(b.lower())
    if a == b:
        return True
    if len(a) < 3 or len(b) < 3:
        return False
    if len(a) == 3 and len(b) == 3 and a[:2] == b[:2] and a[2] in "йяюе" and b[2] in "йяюе":
        return True
    return _same_name_case(a, b)


def _item_word_keys(w: str) -> Tuple[str, ...]:
    w = _norm(w.lower())
    n = len(w)
    if n < 3:
        return (w,)
    keys = [w]
    if n == 3 and w[2] in "йяюе":
        keys.append("#3:" + w[:2])
    for k in range(n - 1, max(2, n - 4), -1):
        if _case_tail(w[k:]):
            stem = w[:k]
            if stem not in keys:
                keys.append(stem)
    return tuple(keys)


def _bmap_cands(bmap: dict, sig: Tuple[str, ...]) -> list:
    d = len(sig)
    if d == 0 or not bmap:
        return []
    best_pos = 0
    best_cnt = -1
    best_keys: Tuple[str, ...] = ()
    for pos_idx in range(d):
        wkeys = _item_word_keys(sig[pos_idx])
        cnt = 0
        for wk in wkeys:
            lst = bmap.get((d, pos_idx, wk))
            if lst:
                cnt += len(lst)
        if cnt == 0:
            return []
        if best_cnt < 0 or cnt < best_cnt:
            best_cnt = cnt
            best_pos = pos_idx
            best_keys = wkeys
            if cnt == 1:
                break
    if len(best_keys) == 1:
        return bmap.get((d, best_pos, best_keys[0]), [])
    seen = set()
    out = []
    for wk in best_keys:
        for item in bmap.get((d, best_pos, wk), ()):
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def _bmap_put(bmap: dict, sig: Tuple[str, ...], val) -> None:
    d = len(sig)
    for pos_idx in range(d):
        for wk in _item_word_keys(sig[pos_idx]):
            bmap.setdefault((d, pos_idx, wk), []).append(val)


def _bmap_has_sig(bmap: dict, sig: Tuple[str, ...]) -> bool:
    return any(_item_sig_match(sig, other) for other in _bmap_cands(bmap, sig))


def _bmap_add_sig(bmap: dict, sig: Tuple[str, ...]) -> None:
    _bmap_put(bmap, sig, sig)


def _item_sig_match(a: Tuple[str, ...], b: Tuple[str, ...]) -> bool:
    return len(a) == len(b) and all(_item_word_match(x, y) for x, y in zip(a, b))


def _extract_item_label(left: str, right: str, is_first_clause: bool) -> Optional[Tuple[Tuple[str, ...], str]]:
    rw = re.findall(r"[\w-]+", right)
    if len(rw) > 3:
        return None
    for w in rw:
        wn = _norm(w.lower())
        if wn in ("был", "была", "было", "были", "будет", "будут", "есть", "нет", "нельзя", "можно") or _is_item_verb(wn):
            return None
    if ":" in left:
        after_colon = left[left.find(":") + 1:]
        sub_res = _extract_item_label(after_colon, right, False)
        if sub_res is not None:
            return sub_res
    left_clean = re.sub(
        r"^[ \t\u00a0\u202f]*(?:>[ \t\u00a0\u202f]*)*(?:#{1,6}[ \t\u00a0\u202f]+)?(?:[-•*+—–|][ \t\u00a0\u202f]*)*"
        r"(?:\*\*|__|\*|_)?(?:\d{1,2}[.)][ \t\u00a0\u202f]+)?", "", left
    )
    toks = [(m.group(), _norm(m.group().lower()), m.start(), m.end())
            for m in re.finditer(r"[A-Za-zА-Яа-яЁё0-9]+(?:-[A-Za-zА-Яа-яЁё0-9]+)*", left_clean)
            if not m.group().isdigit()]
    if not toks:
        return None
    if len(toks) > 1 and toks[-1][1] == "чем":
        toks = toks[:-1]
    for h in sorted(HEDGES, key=len, reverse=True):
        if h in ("без", "кроме"):
            continue
        hp = _norm(h).split(" ")
        if len(toks) > len(hp) and [t[1] for t in toks[-len(hp):]] == hp:
            toks = toks[:-len(hp)]
            break
    last_raw, last_norm, last_s, last_e = toks[-1]
    has_sep = bool(re.search(r"[:—–(|]", left_clean[last_e:]))
    is_quoted = last_s > 0 and left_clean[last_s - 1] in "«„“\"'`"
    after_cls = len(toks) >= 2 and any(toks[-2][1].startswith(c) for c in ITEM_CLASSIFIERS)
    if last_norm in ITEM_BAD_NUM_PREPS and not (has_sep or is_quoted or last_raw[0].isupper() or after_cls):
        return None
    if len(toks) > 1 and toks[-1][1] in ITEM_VAL_PREPS and not re.search(r"[:—–(|]", left_clean[toks[-1][3]:]):
        toks = toks[:-1]
    if len(toks) > 1 and ITEM_COPULA_RX.match(toks[-1][1]):
        toks = toks[:-1]
    while len(toks) > 1:
        if len(toks) > 2 and (toks[0][1], toks[1][1]) in (("при", "этом"), ("тогда", "как"), ("кроме", "того")):
            toks = toks[2:]
        elif len(toks) > 3 and (toks[0][1], toks[1][1], toks[2][1]) == ("в", "том", "числе"):
            toks = toks[3:]
        elif toks[0][1] in ("и", "а", "но", "да", "или", "либо", "также", "тоже", "причем",
                            "зато", "однако", "еще", "уже", "только", "лишь", "даже", "например",
                            "хотя", "если", "ведь"):
            toks = toks[1:]
        else:
            break
    if is_first_clause:
        intro_at = -1
        for k in range(len(toks) - 1):
            if ITEM_INTRO_VERB_RX.match(toks[k][1]):
                intro_at = k
        if intro_at >= 0:
            toks = toks[intro_at + 1:]
        if len(toks) > 2 and toks[0][1] in ("в", "во", "на", "по") and toks[1][1] in ITEM_LEAD_LOCATIVES:
            toks = toks[2:]
    while len(toks) > 1 and toks[0][1] in ITEM_LEAD_PREPS:
        toks = toks[1:]
    if any(toks[k][1] in ("и", "или", "либо", "да") for k in range(1, len(toks) - 1)):
        return None
    content = [t for t in toks if t[1] not in ITEM_STOP and t[1] not in WORD_NUM
               and t[1] not in ONE_FORMS and t[1] not in SCALE]
    if not (1 <= len(content) <= 3):
        return None
    if any(_is_item_verb(t[1]) for t in content):
        return None
    if len(content) == 1 and len(content[0][1]) < 2 and not content[0][0][0].isupper():
        return None
    if len(content) >= 2 and any(content[0][1].startswith(c) for c in ITEM_CLASSIFIERS):
        content = content[1:]
    sig = tuple(t[1] for t in content)
    return sig, " ".join(sig)


def _collect_item_data(facts: Facts, full_text: str):
    """Extract enumeration groups (2+ parallel item-number clauses in one sentence or list block)
    and all individual item-number clauses of `facts`."""
    nums_by_sent: Dict[int, List[Fact]] = {}
    for n in facts.of("number"):
        nums_by_sent.setdefault(n.sent, []).append(n)
    for s_list in nums_by_sent.values():
        if len(s_list) > 1:
            s_list.sort(key=lambda x: x.pos)

    def clause_item(sent: str, s0: int, a: int, b: int, s_nums: List[Fact], s_rels: List[int], is_first: bool):
        lo = bisect.bisect_left(s_rels, a)
        hi = bisect.bisect_left(s_rels, b)
        if hi - lo != 1:
            return None
        nf = s_nums[lo]
        ns = s_rels[lo]
        ne = ns + len(nf.raw)
        got = _extract_item_label(sent[a:ns], sent[ne:b], is_first)
        if got is None:
            return None
        return (got[0], got[1], nf)

    def split_item_and(sent: str, s0: int, c_a: int, c_b: int, s_nums: List[Fact], s_rels: List[int], is_first: bool):
        lo_all = bisect.bisect_left(s_rels, c_a)
        hi_all = bisect.bisect_left(s_rels, c_b)
        if hi_all - lo_all == 0:
            return []
        if hi_all - lo_all == 1:
            one = clause_item(sent, s0, c_a, c_b, s_nums, s_rels, is_first)
            return [one] if one is not None else []
        ands = [(c_a + m.start(), c_a + m.end()) for m in AND_SPLIT_RX.finditer(sent[c_a:c_b])]
        if not ands:
            return []
        and_ends = [m_end for m_end, _ in ands]
        k_len = len(ands)
        starts_i = [c_a] + [nxt for _, nxt in ands]
        dp_head: List[Optional[tuple]] = [None] * (k_len + 1)
        dp_next: List[int] = [-1] * (k_len + 1)
        dp_bmap: List[Optional[dict]] = [None] * (k_len + 1)
        dp_used: List[bool] = [False] * (k_len + 1)

        one_tail = clause_item(sent, s0, starts_i[k_len], c_b, s_nums, s_rels, False)
        if one_tail is not None:
            dp_head[k_len] = one_tail
            bmap_t: Dict[Tuple[int, str], List[Tuple[str, ...]]] = {}
            _bmap_add_sig(bmap_t, one_tail[0])
            dp_bmap[k_len] = bmap_t

        for i in range(k_len - 1, -1, -1):
            a_i = starts_i[i]
            cur_first = is_first if i == 0 else False
            lo_i = bisect.bisect_left(s_rels, a_i)
            cnt_rem = hi_all - lo_i
            if cnt_rem <= 0:
                continue
            if cnt_rem == 1:
                one_i = clause_item(sent, s0, a_i, c_b, s_nums, s_rels, cur_first)
                if one_i is not None:
                    dp_head[i] = one_i
                    bmap_i: Dict[Tuple[int, str], List[Tuple[str, ...]]] = {}
                    _bmap_add_sig(bmap_i, one_i[0])
                    dp_bmap[i] = bmap_i
                continue
            first_num_pos = s_rels[lo_i]
            second_num_pos = s_rels[lo_i + 1]
            j = max(i, bisect.bisect_right(and_ends, first_num_pos))
            while j < k_len and and_ends[j] <= second_num_pos:
                if dp_head[j + 1] is not None:
                    left_it = clause_item(sent, s0, a_i, and_ends[j], s_nums, s_rels, cur_first)
                    if left_it is not None and not _bmap_has_sig(dp_bmap[j + 1], left_it[0]):
                        dp_head[i] = left_it
                        dp_next[i] = j + 1
                        if not dp_used[j + 1]:
                            dp_used[j + 1] = True
                            bmap_cur = dp_bmap[j + 1]
                        else:
                            bmap_cur = {k: list(v) for k, v in dp_bmap[j + 1].items()}
                        _bmap_add_sig(bmap_cur, left_it[0])
                        dp_bmap[i] = bmap_cur
                        break
                j += 1

        if dp_head[0] is None:
            return []
        res = []
        cur = 0
        while cur >= 0 and dp_head[cur] is not None:
            res.append(dp_head[cur])
            cur = dp_next[cur]
        return res

    def make_group(raw_items: list):
        if len(raw_items) < 2:
            return None
        shared: List[str] = []
        if all(len(it[0]) >= 2 for it in raw_items):
            for tok in raw_items[0][0]:
                if all(any(_item_word_match(tok, w) for w in it[0]) for it in raw_items[1:]):
                    shared.append(tok)
        reduced = []
        for sig, disp, nf in raw_items:
            if shared:
                rem = tuple(w for w in sig if not any(_item_word_match(w, sh) for sh in shared))
                if rem:
                    sig, disp = rem, " ".join(rem)
            reduced.append((sig, disp, nf))
        # Drop signatures that appear twice in the same group with different values.
        vals_by_sig: Dict[Tuple[str, ...], set] = {}
        for sig, _, nf in reduced:
            vals_by_sig.setdefault(sig, set()).add(nf.value)
        uniq_sigs = list(vals_by_sig.keys())
        red_bmap: dict = {}
        for u_i, usig in enumerate(uniq_sigs):
            _bmap_put(red_bmap, usig, u_i)
        bad_sigs = set()
        for u_i, usig in enumerate(uniq_sigs):
            uvals = vals_by_sig[usig]
            if len(uvals) > 1 or any(
                u_j != u_i and vals_by_sig[uniq_sigs[u_j]] != uvals and _item_sig_match(usig, uniq_sigs[u_j])
                for u_j in _bmap_cands(red_bmap, usig)
            ):
                bad_sigs.add(usig)
        clean = [it for it in reduced if it[0] not in bad_sigs]
        if len(clean) < 2:
            return None
        first_sig = clean[0][0]
        if not any(sig != first_sig and not _item_sig_match(first_sig, sig) for sig, _, _ in clean[1:]):
            return None
        return (clean, tuple(shared))

    groups = []
    all_items = []
    single_run = []
    list_marker_rx = re.compile(r"^[ \t>*_]*(?:[-•*+—–|]|\d{1,2}[.)])")

    def flush_run():
        nonlocal single_run
        if len(single_run) >= 2:
            grp = make_group([it for _, it in single_run])
            if grp is not None:
                groups.append(grp)
        single_run = []

    for s_idx, sent in enumerate(facts.sentences):
        s0 = facts.starts[s_idx]
        s_nums = nums_by_sent.get(s_idx, [])
        if not s_nums:
            if not re.match(r"^[ \t|:-]+$", sent):
                flush_run()
            continue
        s_rels = [n.pos - s0 for n in s_nums]
        c_spans = clause_spans(sent)
        sent_items = []
        all_valid = True
        for c_idx, (a, b) in enumerate(c_spans):
            got_list = split_item_and(sent, s0, a, b, s_nums, s_rels, c_idx == 0)
            if not got_list and c_idx == 0 and ":" in sent[a:b]:
                col = sent.find(":", a, b)
                if bisect.bisect_left(s_rels, col) > bisect.bisect_left(s_rels, a) and \
                        bisect.bisect_left(s_rels, b) > bisect.bisect_left(s_rels, col + 1):
                    got_list = split_item_and(sent, s0, col + 1, b, s_nums, s_rels, False)
            if got_list:
                sent_items.extend(got_list)
            elif bisect.bisect_left(s_rels, b) > bisect.bisect_left(s_rels, a):
                all_valid = False
        all_items.extend(sent_items)
        if len(sent_items) >= 2 and all_valid:
            flush_run()
            grp = make_group(sent_items)
            if grp is not None:
                groups.append(grp)
        elif len(s_nums) == 1 and len(sent_items) == 1:
            if single_run:
                prev_idx = single_run[-1][0]
                prev_end = facts.starts[prev_idx] + len(facts.sentences[prev_idx])
                gap_txt = full_text[prev_end:s0]
                both_markers = bool(list_marker_rx.match(facts.sentences[prev_idx]) and list_marker_rx.match(sent))
                if re.search(r"\n[ \t]*\n", gap_txt) and not both_markers:
                    flush_run()
            single_run.append((s_idx, sent_items[0]))
        else:
            flush_run()
    flush_run()
    return groups, all_items


def _item_swap_errors(fb: Facts, fa: Facts, before: str, after: str, swapped_pos: set) -> List[Dict]:
    src_groups, src_all = _collect_item_data(fb, before)
    if not src_groups:
        return []
    edit_groups, edit_all = _collect_item_data(fa, after)
    if not edit_all:
        return []
    edit_shared_all: List[str] = []
    for _, sh in edit_groups:
        for w in sh:
            if not any(_item_word_match(w, x) for x in edit_shared_all):
                edit_shared_all.append(w)

    def reduce_sig(sig: Tuple[str, ...], disp: str, drop: List[str]) -> Tuple[Tuple[str, ...], str]:
        if drop and len(sig) >= 2:
            rem = tuple(w for w in sig if not any(_item_word_match(w, d) for d in drop))
            if rem:
                return rem, " ".join(rem)
        return sig, disp

    drop_cache: Dict[Tuple[str, ...], tuple] = {}

    def get_drop_index(drop: List[str]):
        dkey = tuple(drop)
        got = drop_cache.get(dkey)
        if got is not None:
            return got
        red_edit = [(reduce_sig(sig, disp, drop)[0], reduce_sig(sig, disp, drop)[1], nf)
                    for sig, disp, nf in edit_all]
        edit_idx_by_exact: Dict[Tuple[str, ...], List[int]] = {}
        edit_vals_by_exact: Dict[Tuple[str, ...], set] = {}
        for e_i, (esig, _, enf) in enumerate(red_edit):
            edit_idx_by_exact.setdefault(esig, []).append(e_i)
            edit_vals_by_exact.setdefault(esig, set()).add(enf.value)
        uniq_esigs = list(edit_idx_by_exact.keys())
        e_bmap: dict = {}
        for ue_i, esig in enumerate(uniq_esigs):
            _bmap_put(e_bmap, esig, ue_i)

        src_vals_exact: Dict[Tuple[str, ...], set] = {}
        for sig, disp, nf in src_all:
            ssig = reduce_sig(sig, disp, drop)[0]
            src_vals_exact.setdefault(ssig, set()).add(nf.value)
        uniq_ssigs = list(src_vals_exact.keys())
        s_bmap: dict = {}
        for us_i, ssig in enumerate(uniq_ssigs):
            _bmap_put(s_bmap, ssig, us_i)

        sig_lookup: Dict[Tuple[str, ...], Tuple[List[int], set, set]] = {}
        got = (red_edit, uniq_esigs, edit_idx_by_exact, edit_vals_by_exact, e_bmap,
               uniq_ssigs, src_vals_exact, s_bmap, sig_lookup)
        drop_cache[dkey] = got
        return got

    out: List[Dict] = []
    for g_items, g_shared in src_groups:
        cand_drop = list(g_shared)
        for w in edit_shared_all:
            if not any(_item_word_match(w, x) for x in cand_drop):
                cand_drop.append(w)
        if len(cand_drop) > len(g_shared):
            reduced_g = [(reduce_sig(sig, disp, cand_drop)[0], reduce_sig(sig, disp, cand_drop)[1], nf)
                         for sig, disp, nf in g_items]
            # Only use cand_drop if it keeps distinct source items distinct.
            rg_bmap: dict = {}
            seen_rg_pairs = set()
            clashed_drop = False
            for i, (rsig, _, _) in enumerate(reduced_g):
                pair_key = (g_items[i][0], rsig)
                if pair_key in seen_rg_pairs:
                    continue
                for j in _bmap_cands(rg_bmap, rsig):
                    if not _item_sig_match(g_items[i][0], g_items[j][0]) and _item_sig_match(rsig, reduced_g[j][0]):
                        clashed_drop = True
                        break
                if clashed_drop:
                    cand_drop = list(g_shared)
                    reduced_g = [(sig, disp, nf) for sig, disp, nf in g_items]
                    break
                seen_rg_pairs.add(pair_key)
                _bmap_put(rg_bmap, rsig, i)
        else:
            reduced_g = [(sig, disp, nf) for sig, disp, nf in g_items]
        # Merge identical item signatures within g_items that share one value.
        entries: List[Tuple[Tuple[str, ...], str, str]] = []
        ent_bmap: dict = {}
        seen_ent_exact = set()
        for sig, disp, nf in reduced_g:
            ekey = (sig, nf.value)
            if ekey in seen_ent_exact:
                continue
            seen_ent_exact.add(ekey)
            if any(entries[e_idx][2] == nf.value and _item_sig_match(sig, entries[e_idx][0])
                   for e_idx in _bmap_cands(ent_bmap, sig)):
                continue
            e_new = len(entries)
            entries.append((sig, disp, nf.value))
            _bmap_put(ent_bmap, sig, e_new)
        if len(entries) < 2:
            continue
        (red_edit, uniq_esigs, edit_idx_by_exact, edit_vals_by_exact, e_bmap,
         uniq_ssigs, src_vals_exact, s_bmap, sig_lookup) = get_drop_index(cand_drop)

        matched_ues_by_u: List[List[int]] = []
        edit_vals_by_u: List[set] = []
        src_vals_by_u: List[set] = []
        for sig_u, _, val_u in entries:
            cached = sig_lookup.get(sig_u)
            if cached is None:
                m_ues = [ue_i for ue_i in _bmap_cands(e_bmap, sig_u) if _item_sig_match(sig_u, uniq_esigs[ue_i])]
                e_vals: set = set()
                for ue_i in m_ues:
                    e_vals.update(edit_vals_by_exact[uniq_esigs[ue_i]])
                s_base: set = set()
                for us_i in _bmap_cands(s_bmap, sig_u):
                    if _item_sig_match(sig_u, uniq_ssigs[us_i]):
                        s_base.update(src_vals_exact[uniq_ssigs[us_i]])
                cached = (m_ues, e_vals, s_base)
                sig_lookup[sig_u] = cached
            m_ues, e_vals, s_base = cached
            matched_ues_by_u.append(m_ues)
            edit_vals_by_u.append(e_vals)
            src_vals_by_u.append(s_base if val_u in s_base else (s_base | {val_u}))

        donors_by_val: Dict[str, List[int]] = {}
        for v_idx, (_, _, val_v) in enumerate(entries):
            if val_v not in edit_vals_by_u[v_idx]:
                donors_by_val.setdefault(val_v, []).append(v_idx)
        if not donors_by_val:
            continue

        rebound: Dict[int, List[Tuple[str, Fact, List[str]]]] = {}
        for u_idx, (sig_u, disp_u, val_u) in enumerate(entries):
            if not edit_vals_by_u[u_idx] or val_u in edit_vals_by_u[u_idx]:
                continue
            cand_e_indices: List[int] = []
            for ue_i in matched_ues_by_u[u_idx]:
                cand_e_indices.extend(edit_idx_by_exact[uniq_esigs[ue_i]])
            if len(matched_ues_by_u[u_idx]) > 1:
                cand_e_indices.sort()
            hits_u = []
            for e_i in cand_e_indices:
                _, edisp, enf = red_edit[e_i]
                if enf.value in src_vals_by_u[u_idx]:
                    continue
                donors = [entries[v_idx][1] for v_idx in donors_by_val.get(enf.value, ()) if v_idx != u_idx]
                if donors:
                    hits_u.append((edisp, enf, donors))
            if hits_u:
                rebound[u_idx] = hits_u
        if len(rebound) < 2:
            continue
        ordered_hits = []
        for hits_u in rebound.values():
            for edisp, enf, donors in hits_u:
                ordered_hits.append((enf.pos, edisp, enf, donors))
        ordered_hits.sort(key=lambda x: x[0])
        for pos, edisp, enf, donors in ordered_hits:
            if pos in swapped_pos:
                continue
            swapped_pos.add(pos)
            out.append({
                "kind": "swap", "what": "привязка",
                "detail": "%s в исходнике относится к «%s», в правке стоит рядом с «%s»" % (
                    enf.raw, "/".join(sorted(set(donors))), edisp
                ),
            })
    return out


# START_CONTRACT: compare
# PURPOSE: Find lost, invented, re-bound or inverted facts between two versions.
# INPUTS: before, after (str).
# OUTPUTS: {"errors": [ {kind, what, detail} ], "checks": [...], "service": [...], "counts": {...}}.
# SIDE_EFFECTS: none.
# END_CONTRACT: compare
def compare(before: str, after: str) -> Dict:
    _INDEXES.clear()
    _CAP_WORDS.clear()
    before_st = _strip_tracking(before, keep_stress=True)
    after_st = _strip_tracking(after, keep_stress=True)
    before = _strip_prose_stress(before_st)
    after = _strip_prose_stress(after_st)
    fb, fa = extract(before, stripped=True), extract(after, edited=True, stripped=True)
    errors: List[Dict] = []
    service: List[Dict] = []
    checks: List[Dict] = _pair_dot_decimals(fb, fa) + _pair_dot_decimals(fa, fb)

    # START_BLOCK_SERVICE
    # The chat assistant's own lines around the text («Готово, вот текст:», «Если нужно,
    # могу…»): their values are not facts of the text, but they are not errors either.
    service_spans, tail_spans = _service_regions(before, _norm(after.lower()))
    service_groups: Dict[Tuple[str, str], bool] = {}
    service_items: Dict[str, Dict[str, List[Fact]]] = {}

    def group_key(kind: str, f: Fact) -> str:
        if kind == "name":
            return _norm(f.value.lower())[:5]
        return f.value

    for kind in ("number", "date", "month", "name", "quote"):
        by_value: Dict[str, List[Fact]] = {}
        for f in fb.of(kind):
            by_value.setdefault(group_key(kind, f), []).append(f)
        service_items[kind] = by_value

    def service_only(kind: str, items: List[Fact]) -> bool:
        """Every mention of the value stands inside the service lines of the chat assistant and
        the fact is one that may be re-labelled (G2, G3). Dates and months are service-only when
        every mention stands in an explicit assistant tail note (not in a head line)."""
        allowed = tail_spans if kind in ("date", "month") else service_spans
        if not allowed or not items or kind not in ("number", "date", "month", "name", "quote"):
            return False
        for f in items:
            if kind == "number" and f.unit:
                return False        # a number with a unit is a fact of the text
            if kind == "quote" and f.speech:
                return False        # somebody's words are a fact of the text
            if not any(a <= f.pos < b for a, b in allowed):
                return False
        return True

    def in_service(kind: str, f: Fact) -> bool:
        """The value of the fact stands only in the service lines of the chat assistant."""
        key = (kind, group_key(kind, f))
        got = service_groups.get(key)
        if got is None:
            got = service_only(kind, service_items[kind].get(key[1], []))
            service_groups[key] = got
        return got

    # G4: the service lines may not swallow the source: when they take more than 40% of its
    # text and hold more than 40% of its facts, the source is a chat answer, not a text, and
    # no span applies.
    if service_spans:
        eligible = [f for f in fb.items
                    if (f.kind == "number" and not f.unit) or f.kind == "name"
                    or (f.kind == "quote" and not f.speech)]
        held = sum(1 for f in eligible
                   if any(a <= f.pos < b for a, b in service_spans))
        if sum(b - a for a, b in service_spans) > 0.4 * len(before) \
                and held > 0.4 * len(fb.items):
            service_spans = []
            tail_spans = []
            service_groups.clear()
    # END_BLOCK_SERVICE

    # START_BLOCK_NUMBERS_DIFF
    def bag(facts: Facts, kind: str) -> Dict[str, List[Fact]]:
        d: Dict[str, List[Fact]] = {}
        for f in facts.of(kind):
            d.setdefault(f.value, []).append(f)
        return d

    def unit_of(f: Fact) -> str:
        # "16:00" and "16 часов" are the same hour.
        return "ч" if f.unit == "время" else f.unit

    def _units_match(u1: str, u2: str) -> bool:
        return u1 == u2 or (u1 == "¥" and u2 in ("JPY", "CNY")) or (u2 == "¥" and u1 in ("JPY", "CNY"))

    def lost_unit(items: List[Fact], other: List[Fact]) -> Optional[Fact]:
        """A mention whose unit is in none of the mentions of the edit: the fact is lost, not
        only rarer. The edit keeps a unit of its own: if it kept none, the unit check says so."""
        have = {unit_of(f) for f in other if f.unit}
        if not have:
            return None
        for f in items:
            if f.unit and not any(_units_match(unit_of(f), u) for u in have):
                return f
        return None

    # "одну минуту" ↔ "1 минуту": the word "один" alone is not extracted (see ONE_FORMS).
    one_rx = r"(?<![а-яё])(?:%s)(?![а-яё])" % "|".join(ONE_FORMS)
    one_in = {"before": bool(re.search(one_rx, _norm(before.lower()))),
              "after": bool(re.search(one_rx, _norm(after.lower())))}
    for kind, label in (("number", "число"), ("date", "дата")):
        bb, ba = bag(fb, kind), bag(fa, kind)
        for value, items in bb.items():
            missing = len(items) - len(ba.get(value, []))
            if missing > 0 and value not in ba:
                if value == "1" and one_in["after"]:
                    continue
                if kind in ("number", "date") and in_service(kind, items[0]):
                    service.append({"kind": "lost", "what": label, "detail": items[0].raw})
                    continue
                errors.append({"kind": "lost", "what": label, "detail": items[0].raw})
            elif missing > 0:
                # A mention with its own unit that is gone: the fact is lost, not just rarer.
                gone = lost_unit(items, ba[value]) if kind == "number" else None
                if gone is not None:
                    errors.append({"kind": "lost", "what": label, "detail": gone.raw})
                    continue
                checks.append({"kind": "fewer", "what": label,
                               "detail": "%s встречается реже (%d → %d)" % (items[0].raw, len(items), len(ba[value]))})
        for value, items in ba.items():
            if value not in bb and not (value == "1" and one_in["before"]):
                errors.append({"kind": "added", "what": label, "detail": items[0].raw})
        # units and hedges for the values present in both
        for value, items in bb.items():
            if value not in ba:
                continue
            if kind == "number":
                units_b = {unit_of(f) for f in items if f.unit}
                units_a = {unit_of(f) for f in ba[value] if f.unit}
                if units_b and units_a and not any(_units_match(ub, ua) for ub in units_b for ua in units_a):
                    errors.append({"kind": "unit", "what": "единица",
                                   "detail": "%s → %s" % (items[0].raw, ba[value][0].raw)})
                elif units_b and not units_a:
                    checks.append({"kind": "unit", "what": "единица",
                                   "detail": "%s → %s без единицы" % (items[0].raw, ba[value][0].raw)})
            # A hedge without a synonym has to stay somewhere in the edit. Hedges that say the same
            # («около» → «примерно») are counted mention by mention, so three hedged mentions of 40
            # need three hedges of that meaning in the edit: «около 40 … примерно 40 … около 40» →
            # «40 … примерно 40 … примерно 40» has lost one. A mention of the number that is gone
            # took its hedge along, and the «fewer» check says so.
            was = Counter(f.hedge for f in items if f.hedge)
            now = Counter(f.hedge for f in ba[value] if f.hedge)
            gone = max(0, len(items) - len(ba[value]))
            lost = {h for h in was if h not in HEDGE_SAME and h not in now}
            for cls in {hedge_class(h) for h in was if h in HEDGE_SAME}:
                need = sum(n for h, n in was.items() if hedge_class(h) == cls)
                have = sum(n for h, n in now.items() if hedge_class(h) == cls)
                if have < need and not (have and need - have <= gone):
                    lost |= {h for h in was if hedge_class(h) == cls and was[h] > now[h]}
            for h in sorted(lost):
                checks.append({"kind": "hedge", "what": "оговорка",
                               "detail": "«%s» перед %s не найдено" % (h, items[0].raw)})
            # A hedge turned the other way ("не менее 5" → "не более 5") changes the meaning. A
            # source that bounds the value both ways («до 30 ноября» … «После 30 ноября») has no
            # single way to turn: an edit that keeps one of them dropped the other (the check above).
            dirs_b = {hedge_direction(f.hedge) for f in items if f.hedge}
            dirs_a = {hedge_direction(f.hedge) for f in ba[value] if f.hedge}
            for d in sorted(x for x in dirs_b if x):
                if d in dirs_a or HEDGE_OPPOSITE[d] not in dirs_a or HEDGE_OPPOSITE[d] in dirs_b:
                    continue
                src = next(f for f in items if hedge_direction(f.hedge) == d)
                dst = next(f for f in ba[value] if hedge_direction(f.hedge) == HEDGE_OPPOSITE[d])
                errors.append({"kind": "inverted", "what": "оговорка",
                               "detail": "«%s %s» → «%s %s»" % (src.hedge, src.raw, dst.hedge, dst.raw)})
    # END_BLOCK_NUMBERS_DIFF

    # START_BLOCK_MONTHS_DIFF
    # A month without a day must survive as a month, alone or inside a full date.
    def months(facts: Facts, skip_service: bool = False) -> set:
        return {f.value for f in facts.of("month") if not (skip_service and in_service("month", f))} | {
            str(int(f.value[3:])) for f in facts.of("date")
            if re.fullmatch(r"\d\d\.\d\d", f.value) and not (skip_service and in_service("date", f))}
    mb, ma = months(fb), months(fa)
    mb_body = months(fb, skip_service=True)
    for f in fb.of("month"):
        if f.value not in ma:
            if f.value not in mb_body and in_service("month", f):
                service.append({"kind": "lost", "what": "дата", "detail": f.raw})
                continue
            errors.append({"kind": "lost", "what": "дата", "detail": f.raw})
    for f in fa.of("month"):
        if f.value not in mb:
            errors.append({"kind": "added", "what": "дата", "detail": f.raw})
    # END_BLOCK_MONTHS_DIFF

    # START_BLOCK_NAMES_DIFF
    def _build_name_lookup(word_list: List[str]):
        exact_set = set()
        by2: Dict[str, List[str]] = {}
        for w in word_list:
            wn = _norm(w.lower())
            if wn not in exact_set:
                exact_set.add(wn)
                if len(wn) >= 2:
                    by2.setdefault(wn[:2], []).append(w)
        return exact_set, by2

    after_words = re.findall(r"[\w-]+", after)
    after_exact, after_by2 = _build_name_lookup(after_words)
    seen = set()
    for f in fb.of("name"):
        fn = _norm(f.value.lower())
        key = fn[:5]
        if key in seen:
            continue
        seen.add(key)
        if fn in after_exact or any(name_match(f.value, w) for w in after_by2.get(fn[:2], ())):
            continue
        # An acronym spelled out is kept: «УК» → «управляющую компанию».
        if f.value.isupper() and 2 <= len(f.value) <= 4 and any(
                "".join(w[0] for w in after_words[i:i + len(f.value)]).lower() == f.value.lower()
                for i in range(len(after_words) - len(f.value) + 1)):
            continue
        if in_service("name", f):
            service.append({"kind": "lost", "what": "имя или название", "detail": f.raw})
            continue
        errors.append({"kind": "lost", "what": "имя или название", "detail": f.raw})
    before_words = re.findall(r"[\w-]+", before)
    before_exact, before_by2 = _build_name_lookup(before_words)
    seen = set()
    for f in fa.of("name"):
        fn = _norm(f.value.lower())
        key = fn[:5]
        if key in seen:
            continue
        seen.add(key)
        if fn not in before_exact and not any(name_match(f.value, w) for w in before_by2.get(fn[:2], ())):
            checks.append({"kind": "added", "what": "имя или название", "detail": f.raw})
    for kind, label in (("url", "ссылка"), ("email", "почта"), ("phone", "телефон")):
        vb = {f.value for f in fb.of(kind)}
        va = {f.value for f in fa.of(kind)}
        for v in sorted(vb - va):
            errors.append({"kind": "lost", "what": label, "detail": v})
        for v in sorted(va - vb):
            errors.append({"kind": "added", "what": label, "detail": v})
    # END_BLOCK_NAMES_DIFF

    # START_BLOCK_QUOTES_DIFF
    # Quoted words must survive in order; only case endings («Зерно» → «Зерна») and the marks
    # themselves ("…" → «…» is the skill's own typography) may change. A lost direct speech is an
    # error; other lost quoted words are a check: over 1446 old eval outputs they were mostly
    # terms, irony and examples that the rewrite rephrased or cut with chat advice. Words still
    # there without the marks are a check: scare quotes may go. A new quote with new words is a check.
    def words(s: str) -> List[str]:
        return re.findall(r"[\w\u0301-]+", s)

    def _qkey(w: str) -> str:
        return _norm(w.replace("\u0301", "").lower())[:3]

    def _stress_pos(w: str) -> List[int]:
        out: List[int] = []
        seen_acutes = 0
        for idx_c, ch in enumerate(_norm(w.lower())):
            if ch == "\u0301":
                out.append(idx_c - seen_acutes)
                seen_acutes += 1
        return out

    def _stress_conflict(x: str, y: str) -> bool:
        return "\u0301" in x and "\u0301" in y and _stress_pos(x) != _stress_pos(y)

    def _same_qword(x: str, y: str, exact: bool = False) -> bool:
        if _stress_conflict(x, y):
            return False
        xp, yp = x.replace("\u0301", ""), y.replace("\u0301", "")
        return (_norm(xp.lower()) == _norm(yp.lower())) if exact else stem_match(xp, yp)

    def _index_word_seq(seq: List[str]) -> Dict[str, List[int]]:
        idx_map: Dict[str, List[int]] = {}
        for pos_i, w_i in enumerate(seq):
            idx_map.setdefault(_qkey(w_i), []).append(pos_i)
        return idx_map

    def contains_indexed(seq: List[str], seq_idx: Dict[str, List[int]], needle: List[str], exact: bool = False) -> bool:
        n = len(needle)
        if not n or len(seq) < n:
            return False
        limit = len(seq) - n
        for i in seq_idx.get(_qkey(needle[0]), ()):
            if i <= limit and all(_same_qword(seq[i + j], needle[j], exact) for j in range(n)):
                return True
        return False

    both_stressed = "\u0301" in before_st and "\u0301" in after_st
    quote_scan_rx = r"«([^»\n]{1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)\"(?!\s)([^\"\n]{1,80})(?<!\s)\""
    if both_stressed:
        st_b_map: Dict[str, List[str]] = {}
        for m in re.finditer(quote_scan_rx, before_st):
            q_st = next(g for g in m.groups() if g).strip()
            st_b_map.setdefault(CYR_STRESS_RX.sub("", q_st).lower(), []).append(q_st)
        quotes_a = [words(next(g for g in m.groups() if g).strip())
                    for m in re.finditer(quote_scan_rx, after_st)]
        after_q_words = words(after_st)
    else:
        st_b_map = {}
        quotes_a = [words(f.raw) for f in fa.of("quote")]
        after_q_words = after_words
    quotes_a_exact = set() if both_stressed else {tuple(_norm(x.lower()) for x in q) for q in quotes_a}
    quotes_a_idx: Dict[str, List[Tuple[int, int]]] = {}
    for qi, q in enumerate(quotes_a):
        for pi, qw in enumerate(q):
            quotes_a_idx.setdefault(_qkey(qw), []).append((qi, pi))
    after_q_idx = _index_word_seq(after_q_words)
    before_q_idx = _index_word_seq(before_words)

    def in_quotes_a(needle: List[str], exact: bool) -> bool:
        n = len(needle)
        for qi, pi in quotes_a_idx.get(_qkey(needle[0]), ()):
            q = quotes_a[qi]
            if pi <= len(q) - n and all(_same_qword(q[pi + j], needle[j], exact) for j in range(n)):
                return True
        return False

    seen = set()
    st_b_idx: Dict[str, int] = {}
    for f in fb.of("quote"):
        k_q = CYR_STRESS_RX.sub("", f.value)
        if k_q in st_b_map:
            occ_i = st_b_idx.get(k_q, 0)
            st_b_idx[k_q] = occ_i + 1
            raw_q = st_b_map[k_q][occ_i] if occ_i < len(st_b_map[k_q]) else f.raw
        else:
            raw_q = f.raw
        w = words(raw_q)
        key = tuple(_norm(x.lower()) for x in w)
        if not w or key in seen:
            continue
        seen.add(key)
        if key in quotes_a_exact or in_quotes_a(w, f.speech):
            continue
        if contains_indexed(after_q_words, after_q_idx, w, f.speech):
            checks.append({"kind": "unquoted", "what": "цитата", "detail": "«%s» без кавычек" % raw_q})
        elif not f.speech and in_service("quote", f):
            service.append({"kind": "lost", "what": "цитата", "detail": raw_q})
        else:
            (errors if f.speech else checks).append({"kind": "lost", "what": "цитата", "detail": "«%s»" % raw_q})
    seen = set()
    for f in fa.of("quote"):
        w = words(f.raw)
        key = tuple(_norm(x.lower()) for x in w)
        if not w or key in seen:
            continue
        seen.add(key)
        if not contains_indexed(before_words, before_q_idx, w):
            checks.append({"kind": "added", "what": "цитата", "detail": "«%s»" % f.raw})
    # END_BLOCK_QUOTES_DIFF

    # START_BLOCK_CODE_DIFF
    # Code of the original must stay as is; code only found without its backticks is a check.
    code_a = {f.value for f in fa.of("code")}
    flat_a = " ".join(after.split())
    for f in fb.of("code"):
        if f.value in code_a:
            continue
        if f.value in flat_a:
            checks.append({"kind": "unquoted", "what": "код", "detail": "%s без оформления кода" % f.raw[:80]})
        else:
            errors.append({"kind": "lost", "what": "код", "detail": f.raw[:80]})
    code_b = {f.value for f in fb.of("code")}
    flat_b = " ".join(before.split())
    for f in fa.of("code"):
        if f.value not in code_b and f.value not in flat_b:
            checks.append({"kind": "added", "what": "код", "detail": f.raw[:80]})
    blocks_a = {f.value for f in fa.of("code_block")}
    for f in fb.of("code_block"):
        if f.value not in blocks_a and f.value not in flat_a:
            checks.append({"kind": "lost", "what": "блок кода", "detail": f.raw[:80]})
    # END_BLOCK_CODE_DIFF

    # START_BLOCK_NEGATIONS_DIFF
    after_norm = _norm(after.lower())
    before_norm = _norm(before.lower())
    idx_a, idx_b = _index(after_norm), _index(before_norm)
    gone_cache: Dict[str, bool] = {}
    can_more_opt: Optional[bool] = None
    polar_li_ok: Dict[str, bool] = {}
    for f in fb.of("negation"):
        if f.hedge in ("нет", "нельзя"):
            gone = gone_cache.get(f.hedge)
            if gone is None:
                gone = not re.search(r"(?<![а-яё])%s(?![а-яё])" % f.hedge, after_norm)
                gone_cache[f.hedge] = gone
            if gone and f.hedge == "нельзя":
                if can_more_opt is None:
                    can = r"(?<![а-яё])можно(?![а-яё])"
                    can_more_opt = len(re.findall(can, after_norm)) > len(re.findall(can, before_norm))
                if can_more_opt:
                    # «нельзя без сливок» → «без сливок не готовим, можно взять молоко»: the ban stayed
                    # as another negation, so it is only a check.
                    item = {"kind": "inverted", "what": "отрицание", "detail": "«нельзя» пропало, а «можно» появилось"}
                    (errors if len(fa.of("negation")) < len(fb.of("negation")) else checks).append(item)
                    continue
            if gone and len(fa.of("negation")) < len(fb.of("negation")):
                checks.append({"kind": "negation", "what": "отрицание", "detail": "«%s» не найдено" % f.raw})
            continue
        word = f.value
        if word in ("только", "менее", "более", "свыше", "раньше", "позже", "позднее", "просто", "всегда", "совсем"):
            continue
        negated = idx_a.negated_word(word)
        if negated:
            continue
        hits = idx_a.occurrences(word)
        only_negated_in_source = idx_b.all_negated(word)
        if hits:
            if only_negated_in_source and idx_a.none_negated(word):
                if f.unit == "polar_li":
                    ok_li = polar_li_ok.get(word)
                    if ok_li is None:
                        ok_li = all(
                            re.search(r"(?<![а-яё])ли(?![а-яё])", after_norm[idx_a.sentence(a, b)[0]:idx_a.sentence(a, b)[1]])
                            for a, b in hits
                        )
                        polar_li_ok[word] = ok_li
                    if ok_li:
                        continue
                item = {"kind": "inverted", "what": "отрицание",
                        "detail": "«%s» в правке стоит без отрицания" % f.raw}
                # «Вместо того чтобы купить» is the same refusal in other words: a check.
                (checks if f.unit == "contrast" or idx_a.all_instead(word) else errors).append(item)
        else:
            # «без больших порций» → «порции небольшими»: the negation joined the word as the prefix «не-».
            if idx_a.ne_prefix_count(word) <= idx_b.ne_prefix_count(word):
                checks.append({"kind": "negation", "what": "отрицание",
                               "detail": "«%s» не найдено, проверь, что смысл сохранён" % f.raw})
    # The other way round: "Мы храним данные" → "Мы не храним данные".
    seen = set()
    for f in fa.of("negation"):
        word = f.value
        if f.hedge not in ("не", "ни") or word in seen or word in (
                "только", "менее", "более", "свыше", "раньше", "позже", "позднее", "просто", "всегда", "совсем"):
            continue
        seen.add(word)
        src_hits = idx_b.occurrences(word)
        if src_hits and idx_b.none_negated(word) and idx_a.all_negated(word):
            # A check: over the old eval outputs the word was mostly used in another sense
            # ("может" in the original, "не можете" in the edit).
            checks.append({"kind": "inverted", "what": "отрицание",
                           "detail": "«%s» в правке стоит с отрицанием" % f.raw})
    # END_BLOCK_NEGATIONS_DIFF

    # START_BLOCK_MODALITY_DIFF
    for label, rx in MODALITY:
        pat = r"(?<![а-яё])(?:%s)(?![а-яё])" % rx
        nb, na = len(re.findall(pat, before_norm)), len(re.findall(pat, after_norm))
        if nb > na:
            checks.append({"kind": "modality", "what": "уверенность и охват",
                           "detail": "«%s» встречается реже (%d → %d): не стало ли утверждение сильнее?" % (label, nb, na)})
        elif na > nb == 0:
            checks.append({"kind": "modality", "what": "уверенность и охват",
                           "detail": "появилось «%s», которого не было" % label})
    pat = r"(?<![а-яё])(?:%s)(?![а-яё])" % INTENSIFIERS
    nb, na = len(re.findall(pat, before_norm)), len(re.findall(pat, after_norm))
    if na > nb:
        checks.append({"kind": "modality", "what": "уверенность и охват",
                       "detail": "слов вроде «самый», «главный», «лучший» стало больше (%d → %d): не усилено ли утверждение?" % (nb, na)})
    # END_BLOCK_MODALITY_DIFF

    # START_BLOCK_MARKUP_DIFF
    # HTML in the original is part of the text: structural tags must survive the edit; lost
    # emphasis tags only need a look (decorative bold may be removed on purpose).
    # The name ends at a space, "/" or ">": autolinks <https://…> and <a@b.ru> are not tags.
    tag_rx = re.compile(r"<([a-z][a-z0-9]*)(?:\s[^<>]*)?/?>", re.I)
    emphasis = {"b", "strong", "i", "em", "mark", "u"}
    tags_b = [t.lower() for t in tag_rx.findall(before)]
    if len(tags_b) >= 2:
        tags_a = [t.lower() for t in tag_rx.findall(after)]
        for tag in sorted(set(tags_b)):
            nb, na = tags_b.count(tag), tags_a.count(tag)
            if na < nb:
                (checks if tag in emphasis else errors).append(
                    {"kind": "lost", "what": "разметка", "detail": "<%s> %d → %d" % (tag, nb, na)})
        for tag in sorted(set(tags_a) - set(tags_b)):
            checks.append({"kind": "added", "what": "разметка", "detail": "появился тег <%s>" % tag})
    # END_BLOCK_MARKUP_DIFF

    # START_BLOCK_BINDINGS
    # Who got which number: in the original sentence a name and a number stand together;
    # in the edit the number must not move to a sentence with another of those names only.
    pairs: Dict[str, set] = {}
    # Only real names anchor a number: sentence subjects ("Капучино", "Итог") were too noisy.
    # A surname right after a first name is the same person: «Анна Иванова» is one owner, and the
    # edit may name her by either word («Иванова получила 50»).
    def after_source(f: Fact) -> bool:
        # «получила от Бориса 70 рублей»: Борис sends the money, he is not the one who gets it.
        if f.sent >= len(fb.starts):
            return False
        sent, end = fb.sentences[f.sent], f.pos - fb.starts[f.sent]
        gap = end  # the spaces before the name, then the word before them
        while gap > 0 and sent[gap - 1].isspace():
            gap -= 1
        start = gap
        while start > 0 and (sent[start - 1].isalnum() or sent[start - 1] == "-"):
            start -= 1
        return gap < end and sent[start:gap].lower() in SOURCE_PREPOSITIONS

    # [sentence, keys, end of the last word, start of the first word, stands after «от»]
    people: List[list] = []
    spelt: Dict[str, List[str]] = {}  # the keys seen so far, by their first three letters

    def stem_key(word: str) -> str:
        # One key for the case forms of a name: «анна» and «анны» are both Анна. Stems that match
        # share their first three letters, so only the keys that start alike are compared.
        key = _norm(word.lower())[:5]
        same = spelt.setdefault(key[:3], [])
        known = next((k for k in same if stem_match(k, key)), None)
        if known is None:
            same.append(key)
        return known or key

    number_at: Dict[int, Dict[int, List[int]]] = {}

    def numbers_at(facts: Facts, sent: int) -> List[int]:
        # Offsets of the numbers of one sentence, collected once per text.
        by_sent = number_at.get(id(facts))
        if by_sent is None:
            by_sent = number_at[id(facts)] = {}
            for m in facts.of("number"):
                by_sent.setdefault(m.sent, []).append(m.pos - facts.starts[m.sent])
        return by_sent.get(sent, [])

    def _coord_sender_b(f: Fact) -> bool:
        if not (people and people[-1][0] == f.sent and people[-1][4]):
            return False
        if re.fullmatch(r"\s+и\s+", before[people[-1][2]:f.pos], re.I) is None:
            return False
        s0 = fb.starts[f.sent]
        sent = fb.sentences[f.sent]
        ca, cb = clause_span(sent, f.pos - s0)
        s_nums = numbers_at(fb, f.sent)
        prev_rel = people[-1][3] - s0
        end_rel = f.pos + len(f.raw) - s0
        while end_rel < cb:
            nxt_cap = re.match(r"[\s.]+([A-ZА-ЯЁ][\w-]*)", sent[end_rel:cb])
            if not nxt_cap:
                break
            end_rel += nxt_cap.end()
        if any(ca <= p < prev_rel for p in s_nums) and any(end_rel <= p < cb for p in s_nums):
            return False
        if re.match(r"\s*(?:[—–:]|[а-яё]+л[аио]?(?![а-яё]))", _norm(sent[end_rel:cb])):
            return False
        return True

    for f in sorted(fb.of("name"), key=lambda x: x.pos):
        key = stem_key(f.value)
        if people and people[-1][0] == f.sent and people[-1][2] + 1 == f.pos:
            people[-1][1].add(key)
        else:
            is_src = after_source(f) or _coord_sender_b(f)
            people.append([f.sent, {key}, 0, f.pos, is_src])
        people[-1][2] = f.pos + len(f.raw)
    # One person is the words of a full name («Анна Иванова» is {анна, ивано}). Full names that are
    # the same or one inside the other are one person («Анна Сергеевна Иванова» holds «Анна Иванова»);
    # «Анна Иванова» and «Анна Петрова» share a first name and are two. A mention by one word is the
    # person who has that word, if there is only one, so «Иванова получила 50» is Анна Иванова.
    persons: List[set] = []
    for p in people:
        if len(p[1]) > 1:
            same = [g for g in persons if g <= p[1] or p[1] <= g]
            persons = [g for g in persons if g not in same] + [set(p[1]).union(*same)]
    # A first name or surname that two persons have tells them apart no better than nothing does:
    # both are left out, and a mention by that word alone is nobody in particular.
    unclear = {k for k, n in Counter(k for g in persons for k in g).items() if n > 1}
    for p in people:
        have = [g for g in persons if (p[1] <= g if len(p[1]) > 1 else p[1] & g)]
        p[1] = have[0] - unclear if len(have) == 1 else (set() if have else set(p[1]))
    people = [p for p in people if p[1]]
    groups: List[set] = []  # the keys of each person, as the names of the original give them
    for p in people:
        if p[1] not in groups:
            groups.append(p[1])

    people_by_sent: Dict[int, List[list]] = {}
    pstarts_by_sent: Dict[int, List[int]] = {}
    pnext_by_sent: Dict[int, List[int]] = {}
    for p in people:
        people_by_sent.setdefault(p[0], []).append(p)
        pstarts_by_sent.setdefault(p[0], []).append(p[3])
    for s_id, plist in people_by_sent.items():
        nxt_arr = [len(plist)] * len(plist)
        for k_p in range(len(plist) - 2, -1, -1):
            if plist[k_p][1] == plist[k_p + 1][1] and plist[k_p][4] == plist[k_p + 1][4]:
                nxt_arr[k_p] = nxt_arr[k_p + 1]
            else:
                nxt_arr[k_p] = k_p + 1
        pnext_by_sent[s_id] = nxt_arr

    def owners_in(sent: int, lo: int, hi: int, receivers_only: bool = False, limit: int = 0) -> List[set]:
        owners: List[set] = []  # «Анна Иванова … Анна» is still one person
        plist = people_by_sent.get(sent)
        if not plist:
            return owners
        pstarts = pstarts_by_sent[sent]
        pnext = pnext_by_sent[sent]
        idx_p = bisect.bisect_left(pstarts, lo)
        while idx_p < len(plist) and pstarts[idx_p] < hi:
            p = plist[idx_p]
            if not (receivers_only and p[4]) and p[1] not in owners:
                owners.append(p[1])
                if limit and len(owners) >= limit:
                    break
            idx_p = pnext[idx_p]
        return owners

    sent_owners_b: Dict[int, List[set]] = {}
    clauses_b: Dict[int, Optional[List[Tuple[int, int]]]] = {}
    for n in fb.of("number"):
        if n.sent not in sent_owners_b:
            sent_owners_b[n.sent] = owners_in(n.sent, 0, 1 << 62, False, 2)
        owners = list(sent_owners_b[n.sent])
        if len(owners) > 1 and fb.starts:
            # A list in one sentence («Анна получила 30 000, Борис 50 000 и Вера 7 000»): the number
            # belongs to the person of its own clause. A clause with no name or with two names binds
            # nothing, and neither does a row of names with one number («Анна, Борис — все по 100»).
            s0 = fb.starts[n.sent]
            if n.sent not in clauses_b:
                who_b = lambda a, b: owners_in(n.sent, s0 + a, s0 + b, True, 2)
                spans_b = list_clauses(fb.sentences[n.sent], numbers_at(fb, n.sent), who_b)
                clauses_b[n.sent] = spans_b if is_list(
                    fb.sentences[n.sent], numbers_at(fb, n.sent), who_b, spans_b) else None
            if clauses_b[n.sent]:
                a, b = clause_span(fb.sentences[n.sent], n.pos - s0, clauses_b[n.sent])
                owners = owners_in(n.sent, s0 + a, s0 + b, True, 2)
        elif len(owners) == 1 and fb.starts:
            # «Столичная команда разгромила соперников со счетом 7:2, а на счету Гончара — три передачи»:
            # when the sole person stands in another clause that has its own number or opens with «а/но/однако»,
            # the first clause's numbers are not that person's.
            s0 = fb.starts[n.sent]
            sent_b = fb.sentences[n.sent]
            cspans = clause_spans(sent_b)
            if len(cspans) > 1:
                ca, cb = clause_span(sent_b, n.pos - s0, cspans)
                if not owners_in(n.sent, s0 + ca, s0 + cb):
                    s_nums = numbers_at(fb, n.sent)
                    other_with_owner = [(oa, ob) for oa, ob in cspans if owners_in(n.sent, s0 + oa, s0 + ob)]
                    if other_with_owner and all(
                        any(oa <= p < ob for p in s_nums)
                        or re.match(r"^(?:а|но|однако|зато|тогда\s+как|при\s+этом)(?![а-яё])",
                                    _norm(sent_b[oa:ob].lstrip().lower()))
                        or (oa >= 2 and sent_b[oa - 2] == ";")
                        for oa, ob in other_with_owner
                    ):
                        owners = []
        if len(owners) == 1:
            pairs.setdefault(n.value, set()).update(owners[0])
    all_owners = set().union(*pairs.values()) if pairs else set()

    someone = "?"  # stands for a word that two persons have, when nothing beside it tells which one

    def _owner_word_match(owner_key: str, word: str) -> bool:
        if not stem_match(owner_key, word):
            return False
        if len(owner_key) >= 5:
            return True
        wn = _norm(word.lower())
        return owner_key == wn or _same_name_case(owner_key, word)

    def named(part: str, receivers_only: bool = False) -> set:
        found = list(re.finditer(r"[\w-]+", part))
        words = []
        sender = False
        prev_sender = False
        for i, m in enumerate(found):
            # «от Бориса Петрова и Глеба Волкова» names senders: the words after the preposition,
            # capitalised continuations, and a second capitalised sender joined directly by «и».
            gap_prev = part[found[i - 1].end():m.start()] if i > 0 else ""
            if receivers_only and i > 0 and found[i - 1].group().lower() in SOURCE_PREPOSITIONS and m.group()[:1].isupper():
                sender = True
            elif receivers_only and sender and m.group()[:1].isupper() and re.fullmatch(r"[\s.]*", gap_prev) is not None:
                sender = True
            elif (receivers_only and prev_sender and i >= 2 and found[i - 1].group().lower() == "и"
                  and m.group()[:1].isupper()
                  and re.fullmatch(r"\s+", part[found[i - 2].end():found[i - 1].start()]) is not None
                  and re.fullmatch(r"\s+", gap_prev) is not None):
                k_end = m.end()
                j_k = i + 1
                while j_k < len(found) and found[j_k].group()[:1].isupper() and re.fullmatch(r"[\s.]*", part[k_end:found[j_k].start()]) is not None:
                    k_end = found[j_k].end()
                    j_k += 1
                sender = re.match(r"\s*(?:[—–:]|[а-яё]+л[аио]?(?![а-яё]))", _norm(part[k_end:])) is None
            else:
                sender = False
            prev_sender = sender or (receivers_only and prev_sender and m.group().lower() == "и"
                                     and i > 0 and re.fullmatch(r"\s+", gap_prev) is not None)
            if not sender:
                words.append(m)
        hit = [{o for o in all_owners if _owner_word_match(o, m.group())} for m in words]
        owners = set().union(*hit)
        for i, m in enumerate(words):
            # «Петров» alone, when two persons have that surname, is one of them: the number may be his.
            if not hit[i] and any(_owner_word_match(k, m.group()) for k in unclear) and not any(
                    hit[j] and re.fullmatch(r"[\s.]*", part[words[min(i, j)].end():words[max(i, j)].start()])
                    for j in (i - 1, i + 1) if 0 <= j < len(words)):
                owners.add(someone)
        return owners

    seen_near: Dict[Tuple[int, int], tuple] = {}

    def near(facts, n) -> set:
        # The owners named in the number's sentence; in a list, in its own clause.
        key = (id(facts), n.sent)
        if key not in seen_near:
            sent = facts.sentences[n.sent] if n.sent < len(facts.sentences) else ""
            here = named(sent)
            clauses = None
            if facts.starts and sum(1 for g in groups if g & here) > 1:
                part_cache: Dict[Tuple[int, int], set] = {}

                def part_named(a: int, b: int) -> set:
                    if (a, b) not in part_cache:
                        part_cache[(a, b)] = named(sent[a:b], True)
                    return part_cache[(a, b)]

                who_s = lambda a, b: [g for g in groups if g & part_named(a, b)]
                spans = list_clauses(sent, numbers_at(facts, n.sent), who_s)
                if is_list(sent, numbers_at(facts, n.sent), who_s, spans):
                    clauses = ([a for a, _ in spans], [(a, b, part_named(a, b)) for a, b in spans])
            seen_near[key] = (here, clauses)
        here, clauses = seen_near[key]
        if clauses:
            offset = n.pos - facts.starts[n.sent]
            c_starts, c_list = clauses
            ci = bisect.bisect_right(c_starts, offset) - 1
            if ci >= 0 and c_list[ci][0] <= offset < c_list[ci][1]:
                return c_list[ci][2] or here
        return here

    swapped_after_pos: set = set()
    if len(all_owners) >= 2:
        # A number that already stood next to a name somewhere in the original has not moved
        # there: «750 мл из стали» in a product card, with «Сталь 18/8» in its table.
        near_b: Dict[str, set] = {}
        for n in fb.of("number"):
            nb = near_b.setdefault(n.value, set())
            nb.update(near(fb, n))
            for g in groups:
                if nb & g:
                    nb.update(g)
        for n in fa.of("number"):
            want = pairs.get(n.value)
            if not want:
                continue
            here = near(fa, n)
            if someone in here:  # a name that fits two persons: whose number it is cannot be told
                continue
            if here - near_b.get(n.value, set()) and not (here & want):
                swapped_after_pos.add(n.pos)
                errors.append({"kind": "swap", "what": "привязка",
                               "detail": "%s в исходнике относится к «%s», в правке стоит рядом с «%s»" % (
                                   n.raw, "/".join(sorted(want)), "/".join(sorted(here)))})
    errors.extend(_item_swap_errors(fb, fa, before, after, swapped_after_pos))
    # END_BLOCK_BINDINGS

    # The values of the chat assistant's own lines are not facts of the text: they are not
    # counted as facts of the source either.
    counts: Dict[str, int] = {}
    for k in ("number", "date", "name", "url", "phone", "quote", "negation"):
        items = fb.of(k)
        counts[k] = len(items)
        if k in ("number", "date", "name", "quote"):
            for key, group in service_items[k].items():
                if in_service(k, group[0]):
                    counts[k] -= len(group)
    return {"errors": _dedupe(errors), "checks": _dedupe(checks),
            "service": _dedupe(service), "counts": counts}


def _dedupe(items: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in items:
        key = (it["kind"], it["what"], it["detail"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


KIND_RU = {"lost": "потеряно", "added": "появилось", "unit": "изменилась", "swap": "перепутано",
           "inverted": "перевёрнуто",
           "fewer": "реже", "hedge": "потеряна", "negation": "проверь"}
# The verb agrees with the noun: «потеряна цитата», «потерян телефон», «потеряно число».
KIND_FEM = {"потеряно": "потеряна", "появилось": "появилась", "перевёрнуто": "перевёрнута",
               "перепутано": "перепутана"}
KIND_MASC = {"потеряно": "потерян", "появилось": "появился", "перевёрнуто": "перевёрнут",
                "перепутано": "перепутан"}
MASC_WHAT = {"телефон", "код"}


def render(result: Dict) -> str:
    lines = ["Сверка фактов: исходник → правка"]
    c = result["counts"]
    lines.append("В исходнике: чисел %d, дат %d, имён и названий %d, ссылок %d, телефонов %d, цитат %d, "
                 "отрицаний %d." % (c["number"], c["date"], c["name"], c["url"], c["phone"], c["quote"],
                                    c["negation"]))
    if result["errors"]:
        lines.append("Ошибки (%d):" % len(result["errors"]))
        for e in result["errors"]:
            verb = KIND_RU.get(e["kind"], e["kind"])
            if e["what"].endswith("а"):
                verb = KIND_FEM.get(verb, verb)
            elif e["what"] in MASC_WHAT:
                verb = KIND_MASC.get(verb, verb)
            lines.append("  - %s %s: %s" % (verb, e["what"], e["detail"]))
    if result.get("service"):
        lines.append("Убрано вместе со служебными строками чат-бота (не ошибка, но проверь, что это не текст автора):")
        for e in result["service"]:
            lines.append("  - %s: %s" % (e["what"], e["detail"]))
    if result["checks"]:
        lines.append("Проверь глазами (%d):" % len(result["checks"]))
        for e in result["checks"]:
            lines.append("  - %s: %s" % (e["what"], e["detail"]))
    lines.append("Итог: " + ("есть ошибки, верни факты в текст" if result["errors"] else
                             "ошибок не найдено (это не гарантия смысла: перечитай условия и связи)"))
    return "\n".join(lines)


# START_BLOCK_RECEIPT
# The notes line the skill copies word for word (SKILL.md step 6, R-RECEIPT): written by the script,
# so its numbers are the script's. M4 on 2026-11-09: agents that retold the report in their own words
# gave other numbers in 3 of 9 lines («8 чисел, телефон» for 9 numbers and 1 phone).
RECEIPT_FORMS = (  # counts key, forms for 1 / 2-4 / 5 and more
    ("number", ("число", "числа", "чисел")),
    ("date", ("дата", "даты", "дат")),
    ("name", ("имя или название", "имени и названия", "имён и названий")),
    ("url", ("ссылка", "ссылки", "ссылок")),
    ("phone", ("телефон", "телефона", "телефонов")),
    ("quote", ("цитата", "цитаты", "цитат")),
    ("negation", ("отрицание", "отрицания", "отрицаний")),
)


def plural(n: int, forms: Tuple[str, str, str]) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def receipt(result: Dict) -> str:
    """«Сверка скриптом: …» for the notes; "" while there are errors other than lost facts."""
    c = result["counts"]
    have = ", ".join("%d %s" % (c[k], plural(c[k], forms)) for k, forms in RECEIPT_FORMS if c.get(k))
    # The values of the chat assistant's own lines are not facts of the text: they are named
    # apart, so the notes line does not read as a list of lost facts.
    service = "; вместе со служебными строками чат-бота убрано: %s" % \
        ", ".join(s["detail"] for s in result.get("service", [])) if result.get("service") else ""
    if not result["errors"]:
        return "Сверка скриптом: " + ("%s на месте%s." % (have, service) if have
                                     else "чисел, дат и имён в тексте нет%s." % service)
    if all(e["kind"] == "lost" for e in result["errors"]):
        return "Сверка скриптом: в исходнике %s; в правке нет: %s%s." % (
            have or "фактов нет", ", ".join(e["detail"] for e in result["errors"]), service)
    return ""


def receipt_hint(result: Dict) -> str:
    line = receipt(result)
    if not result["errors"]:
        return "Строка для заметок: " + line
    if line:
        return ("Если пропавшее убрано намеренно (служебные слова чат-бота), строка для заметок: %s\n"
                "Иначе верни факты и запусти сверку снова." % line)
    return "Строки для заметок нет: исправь ошибки и запусти сверку снова."
# END_BLOCK_RECEIPT


def _read(path: str) -> str:
    if path == "-":
        # Bytes, not sys.stdin: on Windows it decodes with the console code page (cp1251), and two
        # identical UTF-8 texts with the source piped in gave four false errors (found 2026-11-09).
        return sys.stdin.buffer.read().decode("utf-8-sig")
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) != 2 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    try:
        before, after = _read(args[0]), _read(args[1])
    except (OSError, UnicodeDecodeError) as exc:
        print("Не могу прочитать файл: %s" % exc, file=sys.stderr)
        return 2
    result = compare(before, after)
    print(json.dumps(result, ensure_ascii=False, indent=2) if as_json else
          render(result) + "\n\n" + receipt_hint(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
