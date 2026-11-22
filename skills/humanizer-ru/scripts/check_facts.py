#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Compare an original Russian text with its edited version and report lost, invented,
#          rebound or inverted facts: numbers (with SI/IT/currency units, ranges, ratios, versions/IPs,
#          bank accounts, compound adjectives), dates (days, months, weekdays), times, names/acronyms,
#          URLs (assistant utm_source ignored), phones, e-mails, quotes (nested guillemets, direct
#          speech, blockquotes), inline/fenced code, negations, directional hedges, comparison deltas,
#          person/item bindings (incl. appositives), modality/intensifiers, HTML tags, and assistant
#          service wrappers. Source and edit are read without chat citations, invisibles and homoglyphs.
# SCOPE: heuristic, offline, stdlib only. Errors are likely real; checks need a human look.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CHECK-FACTS; R-FACTS; R-RECEIPT; R-DETECTOR-RISK; DF-SKILL; V-M-CHECK-FACTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# extract: text -> Facts (numbers, ratios, dates, months, urls, emails, phones, names, quotes, negations, code, sentences).
# clause_spans / list_clauses / clause_span / is_list: clause/appositive/«и» splitting for binding checks.
# compare: (before, after) -> {"errors", "checks", "service", "counts"}.
# _service_spans: assistant wrapper spans (head, tail, parenthetical length notes).
# render / receipt / receipt_hint: Russian report and «Сверка скриптом: …» receipt line.
# main: CLI `check_facts.py before.txt after.txt [--json] [--encoding ENC]`; exit 0/1/2.
# END_MODULE_MAP
"""Сверка фактов до и после правки.

    python check_facts.py до.txt после.txt                 # отчёт по-русски
    python check_facts.py до.txt после.txt --json          # то же в JSON (+ receipt)
    python check_facts.py - после.txt                      # исходник из stdin
    python check_facts.py до.txt после.txt --encoding cp1251

В конце отчёта — готовая строка для заметок «Сверка скриптом: …».
Код выхода: 0 — ошибок нет, 1 — есть ошибки, 2 — файл не читается или неверные аргументы.
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
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# START_BLOCK_LEXICON
SEP = " \u00a0\u202f"
_UNIT_ROWS = """%|%,процент,процента,процентов,процентам,процентами
₽|₽,р.,руб.,руб,rub,rur,рубль,рубля,рублей,рублю,рублями,рублях
$|$,usd,долл.,долл,доллар,доллара,долларов,доллару,долларом,долларами,долларах
€|€,eur,евро
£|£,gbp,фунт стерлингов,фунта стерлингов,фунтов стерлингов
фунт|фунт,фунта,фунтов,фунту,фунтом,фунтами,фунтах
¥|¥
JPY|jpy,иена,иены,иен,иене,иену,иеной,иенами,иенах,йена,йены,йен,йене,йену,йеной,йенами,йенах
CNY|cny,юань,юаня,юаней,юаню,юанем,юанями,юанях
кг|кг,килограмм,килограмма,килограммов
г|г,грамм,грамма,граммов
мг|мг,миллиграмм,миллиграмма,миллиграммов
мкг|мкг,микрограмм,микрограмма,микрограммов
т|тонна,тонны,тонн,тонне,тонну,тонной,тоннами,тоннах
км/ч|км/ч,километров в час,километра в час,километр в час
км/с|км/с,километров в секунду,километра в секунду,километр в секунду
м/с|м/с,м/сек,метров в секунду,метра в секунду,метр в секунду
м/мин|м/мин,метров в минуту,метра в минуту,метр в минуту
об/мин|об/мин,оборотов в минуту,оборота в минуту,оборот в минуту,rpm
км²|км²,кв. км,кв.км,квадратных километров,квадратных километра
км|км,километр,километра,километров
м²|м²,кв. м,кв.м,кв. м.,кв.м.,квадратных метров,квадратных метра,квадратный метр
м³|м³,куб. м,куб.м,кубометр,кубометра,кубометров,кубических метров,кубических метра,кубический метр
см²|см²,кв. см,кв.см,квадратных сантиметров,квадратных сантиметра
см³|см³,куб. см,куб.см,кубических сантиметров,кубических сантиметра
мм²|мм²,кв. мм,кв.мм
м|м,метр,метра,метров
см|см,сантиметр,сантиметра,сантиметров
мм|мм,миллиметр,миллиметра,миллиметров
га|га,гектар,гектара,гектаров,гектарах
л|л,литр,литра,литров
мл|мл,миллилитр,миллилитра,миллилитров
шт|шт,штука,штуки,штук
кВт·ч|квт·ч,квтч,квт*ч,квт-ч,квт/ч,квт ч,киловатт-час,киловатт-часа,киловатт-часов
Вт·ч|вт·ч,втч,вт*ч,вт-ч,вт/ч,ватт-час,ватт-часа,ватт-часов
МВт·ч|мвт·ч,мвтч,мвт*ч,мвт-ч,мвт/ч,мегаватт-час,мегаватт-часа,мегаватт-часов
ГВт|гвт,гигаватт,гигаватта,гигаваттов
МВт|мвт,мегаватт,мегаватта,мегаваттов
кВт|квт,киловатт,киловатта,киловаттов
Вт|вт,ватт,ватта,ваттов,ваттам,ваттами,ваттах
л.с.|л.с.,л. с.,лошадиных сил,лошадиные силы,лошадиная сила,лошадиной силы
ГГц|ггц,гигагерц,гигагерца,гигагерцев
МГц|мгц,мегагерц,мегагерца,мегагерцев
кГц|кгц,килогерц,килогерца,килогерцев
Гц|гц,герц,герца,герцев
ккал|ккал,килокалорий,килокалории,килокалория,килокалорию
Гбит/с|гбит/с,гбит/сек,гигабит в секунду,гигабита в секунду,гигабитов в секунду,gbps
Мбит/с|мбит/с,мбит/сек,мегабит в секунду,мегабита в секунду,мегабитов в секунду,mbps
Кбит/с|кбит/с,кбит/сек,килобит в секунду,килобита в секунду,килобитов в секунду,kbps
Гбит|гбит,гигабит,гигабита,гигабитов
Мбит|мбит,мегабит,мегабита,мегабитов
Кбит|кбит,килобит,килобита,килобитов
ГБ/с|гб/с,гб/сек,гигабайт в секунду,гигабайта в секунду,гигабайтов в секунду
МБ/с|мб/с,мб/сек,мегабайт в секунду,мегабайта в секунду,мегабайтов в секунду
КБ/с|кб/с,кб/сек,килобайт в секунду,килобайта в секунду,килобайтов в секунду
ТБ|тб,терабайт,терабайта,терабайтов,tb
ГБ|гб,гигабайт,гигабайта,гигабайтов,gb
МБ|мб,мегабайт,мегабайта,мегабайтов,mb
КБ|кб,килобайт,килобайта,килобайтов,kb
ч|ч,час,часа,часов
мин|мин,минута,минуты,минут
мс|мс,миллисекунда,миллисекунды,миллисекунд
с|сек,с,секунда,секунды,секунд
дн|день,дня,дней,дн,сутки,суток,суткам,сутками,сутках
нед|неделя,недели,недель,нед
мес|месяц,месяца,месяцев,мес
год|год,года,лет,году,годом,годе,годам,годами,годах
чел|человек,человека,чел
°C|°C,°С,градус,градуса,градусов"""
UNIT_SYNONYMS = [(tuple(s.split(",")), c) for row in _UNIT_ROWS.splitlines() for c, s in (row.split("|", 1),)]
UNIT_CANON = {s.lower(): c for syns, c in UNIT_SYNONYMS for s in syns}
UNIT_RX = re.compile(r"(?:[ \u00a0\u202f]|&nbsp;)?(%s)(?![0-9A-Za-zА-Яа-яЁё²³])" % "|".join(
    re.escape(u).replace(r"\ ", r"[ \u00a0\u202f]")
    for u in sorted(UNIT_CANON, key=lambda x: len(re.escape(x)), reverse=True)), re.I)


def _canon_unit(raw: str) -> str:
    return UNIT_CANON.get(raw.replace("\u00a0", " ").replace("\u202f", " ").lower(), "")


BARE_S_ALLOW = frozenset("до по после на при через и или назад спустя".split())
BARE_S_NEXT_WORD_RX = re.compile(r"[ \t\u00a0]+([а-яё]{2,})", re.I)
BARE_S_DOT_LOWER_RX = re.compile(r"\.[ \t\u00a0]+([а-яё]{2,})")
GLUED_UNITS = tuple(
    "% ₽ р. руб. руб $ € £ ¥ долл. долл евро фунт фунта фунтов иен йен юаней "
    "USD EUR GBP RUB RUR JPY CNY ТБ ГБ МБ КБ TB GB MB KB "
    "Гбит/с Мбит/с Кбит/с Гбит Мбит Кбит ГБ/с МБ/с КБ/с "
    "ГГц МГц кГц Гц ГВт МВт кВт Вт кВт·ч кВтч Вт·ч Втч МВт·ч МВтч ккал л.с. "
    "км/ч км/с м/с м/мин об/мин км² м² м³ см² см³ мм² кв.м куб.м кв.см кв.км га "
    "кг г мг мкг км м см мм л мл шт ч мин мс сек с день дня дней дн сутки "
    "неделя недели недель нед месяц месяца месяцев мес год года лет году человек человека чел °C °С".split())
GLUED_UNIT_RX = re.compile(r"(%s)(?![0-9A-Za-zА-Яа-яЁё²³])" % "|".join(
    sorted((re.escape(u) for u in GLUED_UNITS), key=len, reverse=True)))
PREFIX_CURR_RX = re.compile(r"(?:(?<![\w.,])([+\-−]))?([$€£¥₽])[ \u00a0\u202f]*$")
PREFIX_TIME_CURR_RX = re.compile(r"[$€£¥₽][ \u00a0\u202f]*[+\-−]?$")
DIM_RX = re.compile(r"[хx]((?:\d{1,3}(?:[%s]\d{3})+|\d+)(?:[.,]\d+)?)" % SEP)
NAME_RX = re.compile(r"(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*|[А-ЯЁ]{2,4}(?![\w-]))")
WORD_NUM = {
    "ноль": 0, "два": 2, "две": 2, "двух": 2, "трое": 3, "двое": 2, "три": 3, "трех": 3, "двоим": 2, "двоих": 2,
    "четыре": 4, "четырех": 4, "четверо": 4, "пять": 5, "пяти": 5, "пятеро": 5, "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9, "десять": 10, "десяти": 10,
    "одиннадцать": 11, "двенадцать": 12, "пятнадцать": 15, "двадцать": 20, "двадцати": 20,
    "тридцать": 30, "тридцати": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
    "сто": 100, "двести": 200, "триста": 300, "полтора": 1.5, "полторы": 1.5, "полутора": 1.5,
    "половина": 0.5, "половину": 0.5, "одиннадцати": 11, "двенадцати": 12, "тринадцать": 13, "тринадцати": 13,
    "четырнадцать": 14, "четырнадцати": 14, "пятнадцати": 15, "шестнадцать": 16, "шестнадцати": 16,
    "семнадцать": 17, "семнадцати": 17, "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19,
    "девятнадцати": 19, "сорока": 40, "пятидесяти": 50, "шестидесяти": 60, "семьдесят": 70, "семидесяти": 70,
    "восемьдесят": 80, "восьмидесяти": 80, "девяносто": 90, "девяноста": 90, "четыреста": 400,
    "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
    "вдвое": 2, "втрое": 3, "вчетверо": 4, "впятеро": 5, "вдесятеро": 10,
}
ONE_FORMS = tuple("один одна одно одну одного одной одному одним одном".split())
WORD_NO_CONT = frozenset("вдвое втрое вчетверо впятеро вдесятеро двое двоим двоих трое четверо пятеро".split())
WORD_RX = re.compile(r"(?<![а-яё])(%s)(?![а-яё])" % "|".join(sorted(WORD_NUM, key=len, reverse=True)), re.I)
WORD_CONT_RX = re.compile(
    r"[ \u00a0]+(%s)(?![а-яё])" % "|".join(sorted(
        [k for k in WORD_NUM if k not in WORD_NO_CONT] + list(ONE_FORMS), key=len, reverse=True)), re.I)
COMPOUND_NUM = {k: v for k, v in WORD_NUM.items() if k.endswith(("х", "и", "а"))}
COMPOUND_NUM.update({"девяносто": 90, "сто": 100, "ста": 100, "двухсот": 200, "трехсот": 300, "четырехсот": 400,
                     "пятисот": 500, "шестисот": 600, "семисот": 700, "восьмисот": 800, "девятисот": 900, "тысяче": 1000})
COMPOUND_UNIT = {"летн": "год", "годовал": "год", "дневн": "дн", "суточн": "дн", "недельн": "нед", "месячн": "мес",
                 "часов": "ч", "минутн": "мин", "секундн": "с", "процентн": "%", "метров": "м", "километров": "км",
                 "литров": "л", "килограммов": "кг"}
HYPHEN_UNIT_RX = re.compile(r"[-–—](%s)[а-яё]+" % "|".join(sorted(COMPOUND_UNIT, key=len, reverse=True)), re.I)
COMPOUND_NUM_RX = re.compile(
    r"(?<![а-яё])(%s)-?(%s)[а-яё]+" % (
        "|".join(sorted(COMPOUND_NUM, key=len, reverse=True)),
        "|".join(sorted(COMPOUND_UNIT, key=len, reverse=True)),
    ), re.I)
SCALE = {"тыс": 1000, "тыс.": 1000, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
         "млн": 10**6, "млн.": 10**6, "миллион": 10**6, "миллиона": 10**6, "миллионов": 10**6,
         "млрд": 10**9, "млрд.": 10**9, "миллиард": 10**9, "миллиарда": 10**9, "миллиардов": 10**9}
SCALE_ALT = "|".join(re.escape(k) for k in sorted(SCALE, key=len, reverse=True))
SCALE_RX = re.compile(r"[%s]+(%s)(?![а-я])" % (SEP, SCALE_ALT), re.I)
GLUED_SCALE_RX = re.compile(r"(%s)(?![а-яёa-z])" % SCALE_ALT)
SEP_STRIP_RX = re.compile(r"[%s]|&nbsp;" % SEP, re.I)
SIGN_RX = re.compile(r"^[+\-−]")
ACCT_RX = re.compile(r"\d{16,}")
NUM_RX = re.compile(
    r"(?:(?<![\w.,%%₽$€£¥°])[+\-−]|(?<![\w.,]))(?:\d{1,3}(?:(?:[%s]|&nbsp;)\d{3})+|\d+)(?:[.,]\d+)?" % SEP, re.I)
HTML_ENTITY_RX = re.compile(r"&(?:[A-Za-z]{2,8}|#x[0-9a-fA-F]{1,6}|#[0-9]{1,7});")
HTML_TAG_RX = re.compile(r"<([a-z][a-z0-9]*)(?:\s[^<>]*)?/?>", re.I)
HTML_ANY_TAG_RX = re.compile(r"</?[a-z][a-z0-9]*(?:\s[^<>]*)?/?>", re.I)
MONTH_ANY_RX = re.compile(r"(?<![а-яё])(?:(январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)"
                          r"(?:ь|я|ю|ем|ём|е)|(март|август)(?:а|у|ом|е)?|(ма)(?:й|я|ю|ем|е))(?![а-яё])", re.I)
MONTH_ANY_NUM = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
                 "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
MONTHS = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|"
          "январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре|"
          "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь")
MONTH_STEM = {m[:3]: i for i, m in enumerate("янв фев мар апр мая июн июл авг сен окт ноя дек".split(), 1)}
MONTH_STEM["май"] = MONTH_STEM["мае"] = 5
DATE_NAMED_RX = re.compile(
    r"(?<![.:,/])\b(\d{1,2})(?:[ \t\u00a0]*(?:[–—-]|,|или|и|по|до)[ \t\u00a0]*(\d{1,2}))?"
    r"[ \t\u00a0]+(%s)(?:[ \t\u00a0]+(\d{4}))?" % MONTHS, re.I)
DATE_DOT_RX = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b")
TIME_RX = re.compile(r"(?<!\d:)\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,:]\d)")
TIME_PREP_RX = re.compile(r"(?<![а-яё])(?:в|к|до|после)[ \t\u00a0]+$")
RATIO_CUE_RX = re.compile(
    r"(?<![а-яё])(?:масштаб|пропорц|соотношен|отношен|формат|разрешен|сторон|экран|"
    r"счет|разбав|развед|концентрац|шанс|вероятност|коэффициент|рейтинг|баланс)", re.I)
RATIO_COLON_RX = re.compile(
    r"(?<![:\w])(?:(\d+(?:[.,]\d+)?):(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)[ \t\u00a0]+:[ \t\u00a0]+(\d+(?:[.,]\d+)?))(?![:\w])")
RATIO_K_RX = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)[ \t\u00a0]+к[ \t\u00a0]+(\d+(?:[.,]\d+)?)(?!\w|[.,]\d)", re.I)
RATIO_NA_RX = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)[ \t\u00a0]+на[ \t\u00a0]+(\d+(?:[.,]\d+)?)(?!\w|[.,]\d)", re.I)
_ZW = ("\u200b\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069\u180e\u200c\u200d"
       "\u034f\u061c\u2800\u3164\uffa0\u115f\u1160\u2061-\u2064\u206a-\u206f\ufff9-\ufffc"
       "\ue200-\ue204\uea01\uea02\ufe00-\ufe0f\U000e0000-\U000e007f\U000e0100-\U000e01ef")
URL_RX = r"(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\.)(?:\([^\s<>«»\"'()\]`%s]*\)|[^\s<>«»\"')\]`%s])+" % (_ZW, _ZW)
EMAIL_SKIP_RX = r"(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\.[A-Za-zА-Яа-яЁё]{2,}"
HOMOGLYPHS = dict(zip(
    "aceopxyABCEHKMOPTXYëËαεορχκΑΒΓΕΗΚΜΟΠΡΤΥΦΧ",
    "асеорхуАВСЕНКМОРТХУёЁаеорхкАВГЕНКМОПРТУФХ",
))
HOMOGLYPHS.update({"á": "а\u0301", "é": "е\u0301", "ó": "о\u0301", "ý": "у\u0301",
                   "Á": "А\u0301", "É": "Е\u0301", "Ó": "О\u0301", "Ý": "У\u0301"})
HOMOGLYPH_TRANS = str.maketrans(HOMOGLYPHS)
_HOMO_LOOK = "".join(HOMOGLYPHS)
_HOMO_ALL = "А-Яа-яЁё\u0301\u0306\u0308" + _HOMO_LOOK
LAT_EXT = "\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff\ua7dc"
_WORD_CHARS = "A-Za-z" + LAT_EXT + r"\u0370-\u03ffА-Яа-яЁё\u0301\u0306\u0308"
HOMO_WORD_RX = r"(?<![%s])(?=[%s]*[А-Яа-яЁё])(?=[%s]*[%s])[%s]+(?![%s])" % (
    _WORD_CHARS, _HOMO_ALL, _HOMO_ALL, _HOMO_LOOK, _HOMO_ALL, _WORD_CHARS)
MD_TARGET_RX = r"(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)"
PROSE_HOMO_RX = re.compile(URL_RX + "|" + EMAIL_SKIP_RX + "|" + MD_TARGET_RX + "|(" + HOMO_WORD_RX + ")")
_REGEX_PREV = frozenset("=(,:;!&|?+-~*{[\n\r")
_REGEX_KW = frozenset("return typeof void delete throw case in of yield await".split())
_REGEX_FLAGS = frozenset("dgimsuvy")
CYR_STRESS_RX = re.compile(r"(?<=[А-Яа-яЁё])\u0301")
PROSE_STRESS_RX = re.compile(URL_RX + r"|((?<=[А-Яа-яЁё])\u0301)")
_CITETURN_STEP = r"turn\d+(?:search|fetch|file|image|news|video|ref|view|product|finance|map|sports|weather|local|code|calc|browser)\d+"
CITATION_RX = re.compile(
    r"[ \t]?:{0,2}contentReference\[oaicite:\d+\](?:\{index=\d+\})?|[ \t]?\[oaicite:\d+\](?:\{index=\d+\})?"
    r"|[ \t]?\ue200[^\ue201\n]{0,400}\ue201|[ \t]?\uea01[^\uea02\n]{0,40}\uea02"
    r"|[ \t]?(?<![A-Za-z0-9/_.\-=?:&#@])cite" + _CITETURN_STEP + r"(?:" + _CITETURN_STEP + r")*"
    r"|[ \t]?【\d+(?:(?:[:,\-–][ \t]*|[ \t]+)\d+)*(?:†[^】\n]{0,80})?】|\[cite_start\]"
    r"|[ \t]?\[cite(?:_end)?(?::[ \t]*[0-9]+(?:[ \t]*[\-–,][ \t]*[0-9]+)*[ \t]*)?\]"
    r"|[ \t]?\[(?:citation|attached_file|web):[ \t]*[0-9]+(?:[ \t]*[\-–,][ \t]*[0-9]+)*[ \t]*\]"
    r"|[ \t]?\[span_\d+\][\[(](?:start_span|end_span)[\])]"
    r"|[ \t]?\[\^\d+\^\]|</?antml:cite(?:[ \t]+[^>\n]{0,200})?>", re.I)
CITE_XML_PAIR_RX = re.compile(
    r"""(?is)<cite[ \t]+index=(?:"[^"\n]{0,120}"|'[^'\n]{0,120}')[ \t]*>((?:(?!</?cite[ \t\r\n>/]).){0,4000})</cite>""")
CITE_XML_OPEN_RX = re.compile(r"""(?i)<cite[ \t]+index=(?:"[^"\n]{0,120}"|'[^'\n]{0,120}')[ \t]*>""")
INVISIBLE_CPS = frozenset((
    0x200B, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069, 0x180E, 0x200C, 0x034F, 0x061C, 0x2061, 0x2062, 0x2063,
    0x2064, 0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F, 0xFFF9, 0xFFFA, 0xFFFB, 0xFFFC,
    0xE200, 0xE201, 0xE202, 0xE203, 0xE204, 0xEA01, 0xEA02))
SPACE_SPOOFERS = frozenset((0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160))
_WS = frozenset(" \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000")
URL_TAIL = ".,;:!?…*_~"


def _url_key(url: str) -> str:
    m = re.match(r"((?:https?://)?[^/?#]*)(.*)", url, re.S | re.I)
    return m.group(1).lower() + ("" if m.group(2) == "/" else m.group(2))


WEEKDAY_RX = re.compile(r"(?<![а-яё])(понедельник|вторник|четверг|пятниц|суббот|воскресень)[а-яё]*", re.I)
WEEKDAY_WED_RX = re.compile(
    r"(?<![а-яё])(?:в|на)[ \t\u00a0]+(?:(?:эту|прошлую|следующую|ближайшую|каждую|ту)[ \t\u00a0]+)?(среду)(?![а-яё])"
    r"|(?<![а-яё])по[ \t\u00a0]+(средам)(?![а-яё])"
    r"|(?<![а-яё])(среда)(?=[ \t\u00a0]*(?:,[ \t\u00a0]*\d{1,2}|:[ \t\u00a0]*\d{1,2}[:.]\d{2}))"
    r"|^[ \t\u00a0]*(?:[*_#>-][ \t\u00a0]*)*(среда)(?=[ \t\u00a0]*:)", re.I | re.M)
WEEKDAY_NUM = {"понедельник": 1, "вторник": 2, "сред": 3, "четверг": 4, "пятниц": 5, "суббот": 6, "воскресень": 7}
WEEKDAY_ABBR = {"пн": 1, "вт": 2, "ср": 3, "чт": 4, "пт": 5, "сб": 6, "вс": 7}
WEEKDAY_RANGE_RX = re.compile(r"(?<![а-яё])(пн|вт|ср|чт|пт|сб|вс)\.?[ \t\u00a0]*[-–—][ \t\u00a0]*(пн|вт|ср|чт|пт|сб|вс)\.?(?![а-яё])", re.I)
WEEKDAY_DATE_RX = re.compile(
    r"(?<![А-Яа-яЁёA-Za-z0-9])(пн|вт|ср|чт|пт|сб|вс)\.?(?=[ \t\u00a0]*(?:,[ \t\u00a0]*\d{1,2}"
    r"(?:[ \t\u00a0]+(?:%s)|\.\d{1,2}\b)|:[ \t\u00a0]*\d{1,2}[:.]\d{2}))" % MONTHS, re.I)
WEEKDAY_PREP_RX = re.compile(
    r"(?<![А-Яа-яЁёA-Za-z])(?:[Вв]|[Вв]о|[Сс]|[Сс]о|[Дд]о|[Кк]|[Пп]о)[ \t\u00a0]+(пн|вт|чт|сб|вс|(?:ср|пт)(?!\.))(?![А-Яа-яЁёA-Za-z]|[ \t\u00a0]*[-–—])")
HEDGE_G1 = tuple("не более,не менее,не свыше,не больше,не меньше,не позже,не позднее,не раньше,не старше,не короче,"
                 "не дешевле,не моложе,не дольше,не дороже,минимум,максимум,около,примерно,приблизительно,почти,порядка,только,лишь".split(","))
HEDGE_G2 = tuple("более свыше менее больше меньше короче дольше дешевле дороже старше моложе".split())
HEDGE_G3 = tuple("до от после кроме без".split())
HEDGES = HEDGE_G1 + HEDGE_G2 + HEDGE_G3
HEDGE_SAME = {"около": "≈", "примерно": "≈", "приблизительно": "≈", "порядка": "≈",
              "не менее": "≥", "не меньше": "≥", "минимум": "≥", "не короче": "≥", "не дешевле": "≥", "не моложе": "≥",
              "не позже за": "≥", "не позднее за": "≥",
              "не более": "≤", "не больше": "≤", "максимум": "≤", "не старше": "≤", "не свыше": "≤",
              "не дольше": "≤", "не дороже": "≤", "не раньше за": "≤",
              "более": ">", "свыше": ">", "больше": ">", "дольше": ">", "дороже": ">", "старше": ">",
              "менее": "<", "меньше": "<", "короче": "<", "дешевле": "<", "моложе": "<",
              "не позже": "≤д", "не позднее": "≤д"}
_HGAP = r"[ \u00a0\u202f*_]"
_HPREP = r"(?:за|на|в|во|через|к|ко|по|с|со|у|из)"
_h_alt = lambda hs: "|".join((_HGAP + "+").join(re.escape(p) for p in h.replace("ё", "е").split(" "))
                             for h in sorted(hs, key=len, reverse=True))
HEDGE_BEFORE_RX = re.compile(
    r"(?:^|[^а-яa-z])(?:(%s)(?:%s+чем)?(?:%s+(%s))?|(%s)(?:%s+чем(?:%s+%s)?)?|(%s))%s*$" % (
        _h_alt(HEDGE_G1), _HGAP, _HGAP, _HPREP, _h_alt(HEDGE_G2), _HGAP, _HGAP, _HPREP, _h_alt(HEDGE_G3), _HGAP))
HEDGE_CLEAN_RX = re.compile(r"[ \u00a0\u202f*_]+")
CYR_ANY_RX = re.compile(r"[а-яё]")
HEDGE_TOK_PARTS = tuple(tuple(h.replace("ё", "е").split(" ")) for h in sorted(HEDGES, key=len, reverse=True)
                        if h not in ("без", "кроме"))
QUOTE_RX = re.compile(
    r"«((?:[^«»\n]|«[^«»\n]{0,500}»){1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)\"(?!\s)([^\"\n]{1,80})(?<!\s)\"")
DASH_AFTER_RX = re.compile(r"[*_]*(,?)[ \t\u00a0]+[—–-][ \t\u00a0]")
LINE_EM_RX = re.compile(r"[ \t\u00a0>*_]*[—–][ \t\u00a0]*")
LINE_HY_RX = re.compile(r"[ \t\u00a0>*_]*-[ \t\u00a0]*")
COLON_BEFORE_QUOTE_RX = re.compile(r":(?:[ \t\u00a0]*\r?\n[ \t\u00a0]*>)?[ \t\u00a0*_]*$")
NEG_RX = re.compile(
    r"(?<![а-яё])(не|ни|без)[ \t\u00a0\u202f]+(?:(?:на|в|во|к|ко|с|со|по|за|до|от|из|у|о|об)[ \t\u00a0\u202f]+)?([а-яё]{3,})"
    r"|(?<![а-яё])(нет|нельзя)(?![а-яё])")
NEG_WORDS_SCAN_RX = re.compile(r"(?<![а-яё])(не|ни|без|нет|нельзя)[ \t\u00a0\u202f]+(?:[а-яё]+[ \t\u00a0\u202f]+){0,2}([а-яё]{3,})")
COMP_DELTA_WORDS = (
    r"(?:больше|меньше|выше|ниже|дороже|дешевле|старше|моложе|раньше|позже|позднее|"
    r"дольше|короче|быстрее|медленнее|крупнее|мельче|шире|уже|тяжелее|легче|лучше|хуже|чаще|реже)")
COMP_DELTA_BEFORE_NA_RX = re.compile(r"(?<![а-яё])на[ \t\u00a0*_]+$", re.I)
COMP_DELTA_AFTER_RX = re.compile(
    r"^(?:[ \t\u00a0*_]+(?:[а-яёa-z%%₽$€£¥°²³]+(?:\.[ \t\u00a0]*[а-яё]+)?\.?)){0,2}"
    r"[ \t\u00a0*_]+%s(?![а-яё])(?![ \t\u00a0]+не(?![а-яё]))" % COMP_DELTA_WORDS, re.I)
COMP_DELTA_BEFORE_REV_RX = re.compile(
    r"(?<![а-яё])%s(?![а-яё])(?![ \t\u00a0]+не(?![а-яё]))[^.!?;:\n]{0,48}(?<![а-яё])на[ \t\u00a0*_]+$" % COMP_DELTA_WORDS, re.I)
COMP_TARGET_LEFT_RX = re.compile(
    r"(?<![а-яё])(?:на[ \t\u00a0*_]+(?:[+\-−]?[$€£¥₽]?[ \t\u00a0*_]*\d[\d \u00a0\u202f.,]*|"
    r"два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|двадцать|тридцать|сорок|пятьдесят|сто|полтора|полторы|половину)"
    r"(?:[ \t\u00a0*_]+[а-яёa-z%%₽$€£¥°²³.]+){0,2}"
    r"|в[ \t\u00a0*_]+(?:\d[\d \u00a0\u202f.,]*|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|полтора|полторы)[ \t\u00a0]+раз[ао]?"
    r"|вдвое|втрое|вчетверо|впятеро|вдесятеро)"
    r"[ \t\u00a0*_]+%s(?![а-яё])(?:,?[ \t\u00a0]+чем)?(?:[ \t\u00a0]+(?:у|в|во|на|от|для|по|с|со))?[ \t\u00a0*_]+$" % COMP_DELTA_WORDS)
APPOS_STOP_RX = re.compile(
    r"^(?:и|а|но|однако|зато|или|либо|да|потом|затем|потому|поскольку|так\s+как|если|хотя|чтобы|"
    r"когда|пока|где|куда|откуда|сколько|почему|зачем|чем)(?![а-яё])", re.I)
ABBREV_CAP_RX = re.compile(
    r"(?:(?:^|[\s(«\"—–-])(?:ул|пр|пер|пл|бул|наб|пос|им|обл|р-н|т\.?[ \t\u00a0]*н)"
    r"|(?:^|[,;\n(«\"—–-][ \t\u00a0]*|(?:в|во|из|к|ко|от|до|по|о|об|на|у|при|около|для|близ|через)[ \t\u00a0]+)[гсд])\.$", re.I)
ABBREV_DIGIT_RX = re.compile(r"(?:^|[\s,;(\[«\"—–-])(?:с|стр|т|ч|гл|п|ст|рис|табл|вып|кн|д|кв|корп|пп|п\.п|ст\.ст)\.$", re.I)
TABLE_SEP_LINE_RX = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)+\|?[ \t]*\r?$")


def hedge_class(hedge: str) -> str:
    return HEDGE_SAME.get(hedge, hedge)


HEDGE_DIR = {"≥": "lower", ">": "lower", "≤": "upper", "<": "upper", "≤д": "upper",
             "от": "lower", "после": "lower", "не раньше": "lower", "до": "upper"}
HEDGE_OPPOSITE = {"lower": "upper", "upper": "lower"}


def hedge_direction(hedge: str) -> str:
    return HEDGE_DIR.get(hedge_class(hedge), "")


SOURCE_PREPOSITIONS = ("от", "через")
NEG_WORDS = frozenset("не ни нет нельзя без никаких никакой никакого никакие никакая никогда ничего ничто ничем никто никого никому нигде никак нисколько".split())
MODALITY = [
    ("может", r"мо(?:жет|гут|жем|жете|гу|г|гла|гли|жно)"), ("возможно", r"возможн[оа]"),
    ("наверное", r"наверн(?:ое|яка)|вероятно|видимо|скорее всего|кажется"), ("план", r"(?:за)?планир\w*"),
    ("обычно", r"обычно"), ("иногда", r"иногда"), ("часто", r"часто"), ("редко", r"редко"),
    ("всегда", r"всегда"), ("никогда", r"никогда"), ("некоторые", r"некотор\w*"),
    ("многие", r"многи[ехм]\w*"), ("каждый", r"кажд\w+"), ("почти", r"почти"),
    ("риск", r"риск\w*|вероятност\w*"), ("один из", r"(?:один|одна|одно|одного|одной|одним|одну|одном) из"),
    ("только", r"только|лишь"), ("если", r"если|в случае|при условии"),
    ("по данным / по словам", r"по (?:данным|словам|оценк\w+|мнению)|согласно"),
]
INTENSIFIERS = r"сам(?:ый|ая|ое|ые|ого|ой|ым|ых|ую|ом)|главн\w*|наиболее|лучш\w*|важнейш\w*|гарантирован\w*"
SENT_START_STOP = frozenset(
    "В На С И А Но Это Мы Вы Я Он Она Они Если Когда Для По При От До За Из К О У Как Что Так Все Всё "
    "Наш Наша Наши Ваш Ваша Ваши Также Кроме Еще Ещё Уже Теперь Сейчас Здравствуйте Привет Добрый "
    "Уважаемый Уважаемая Спасибо".split()) | {"С уважением"}
POLITE_PRONOUN = re.compile(r"Вы|Вас|Вам|Вами|Ваш(?:а|е|и|его|ему|ем|ей|у|ую|их|им|ими)?|"
                            r"Ты|Тебе|Тебя|Тобой|Твой|Тво(?:я|е|ё|и|его|ему|ем|ём|ей|ю|их|им|ими)")
FIRST_NAMES = set("""Александр Александра Алексей Алина Алиса Алла Анастасия Анатолий Андрей Анна
Антон Арина Аркадий Арсений Артём Артем Богдан Борис Вадим Валентин Валентина Валерий Валерия Варвара
Василий Вера Вероника Виктор Виктория Виталий Владимир Владислав Вячеслав Галина Геннадий Георгий Глеб
Григорий Даниил Дарья Денис Диана Дмитрий Евгений Евгения Егор Екатерина Елена Елизавета Жанна Захар
Зинаида Зоя Иван Игорь Илья Инна Ирина Карина Кирилл Клавдия Константин Кристина Ксения Лариса Лев Леонид
Лидия Любовь Людмила Максим Маргарита Марина Мария Марк Матвей Михаил Надежда Наталья Наталия Никита
Николай Нина Оксана Олег Олеся Ольга Павел Пётр Петр Полина Раиса Роман Руслан Светлана Семён Семен
Сергей Софья Станислав Степан Тамара Татьяна Тимофей Тимур Ульяна Фёдор Федор Филипп Эдуард Юлия Юрий
Яков Яна Ярослав""".split())
SERVICE_SEP_RX = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,}|```[^\n]*)[ \t]*\r?$", re.M)
SERVICE_HEAD_RX = re.compile(r"(?i)^\W*(?:вот\b|готов(?:о|ый|ая|ое|ые)\b)")
SERVICE_HEAD_STRICT_RX = re.compile(r"(?i)^\W*(?:готово\b|вот\s+(?:готов|ваш|текст|вариант|пост|письмо))")
SERVICE_TAIL_RX = re.compile(
    r"(?i)^\W*(?:пара (?:замечаний|уточнений)|несколько (?:замечаний|пояснений|уточнений|слов)|"
    r"(?:небольшое\s+)?уточнени|что (?:учтено|нужно|стоит)|объём|замечани|служебн|заметки для|"
    r"если (?:нужно|нужен|нужна|нужны|хотите)|могу\b|готово|советы?\W|перед отправкой)")
SERVICE_FIRST_RX = re.compile(r"(?i)могу|сделаю|напишу|переделаю|перепишу|пересоберу|сокращу|впишу|добавлю|поправлю|я (?:оформил|добавил|убрал|вывел)")
SERVICE_ABOUT_RX = re.compile(
    r"(?i)текст|вариант|верси|пост(?:а|у|ом|е)?\b|письм|сообщени|объявлени|рассылк|описани|карточк|"
    r"ваканси|резюме|стать[яи]|объ[её]м|знак|символ|публикац|отправк|абзац|заголов|год\s+в\s+дат")
SERVICE_SIZE_RX = re.compile(r"(?i)готов(?:о|ый|ая|ое|ые)(?![а-яё])|(?<![а-яё])(?:знак|символ|слов)(?:ов|а|о|и|ы)?(?![а-яё])")
SERVICE_PAREN_RX = re.compile(
    r"\([~≈]?\s*(?:около\s+|примерно\s+|порядка\s+|до\s+)?\d+(?:[ \t\u00a0]+\d+)*[ \t\u00a0]*"
    r"(?:знак|символ|слов)(?:ов|а|о|и|ы)?(?![а-яё])[^)\n]{0,120}\)", re.I)
POUND_MONEY_RX = re.compile(
    r"(?i)(?:(?<![а-яё])(?:за|стоимостью|ценой)|сто(?:ит|ят|ил[аио]?)|цен[аеыуой]|"
    r"оплат\w*|штраф\w*|бюджет\w*|тариф\w*|чек\w*|куп\w*|плат\w*)"
    r"[ \t\u00a0*_]*(?:(?:около|примерно|до|от|не[ \t\u00a0*_]+более|не[ \t\u00a0*_]+менее|порядка|свыше|более|менее)[ \t\u00a0*_]*)?$")
ITEM_STOP = frozenset("""и а но да или либо ли же бы б не ни нет нельзя можно надо нужно есть был была было были будет будут
стал стала стало стали станет станут я меня мне мной мною мы нас нам нами ты тебя тебе тобой вы вас вам вами он его него ему нему
им ним нем она ее нее ей ней ею они их них ими ними себя себе собой мой моя мое мои моего моей моему моим моем моих моими наш наша
наше наши нашего нашей нашему нашим нашем наших нашими ваш ваша ваше ваши вашего вашей вашему вашим вашем ваших вашими твой свой
своя свое свои своего своей своему своим своем своих своими этот эта это эти этого этой этому этим этом этих этими тот та то те того
той тому тем том тех теми весь вся все всего всей всему всем всех всеми сам сама само сами кто что чего чему чем ком какой какая какое
какие чей который которая которое которые которого которой которому которым котором которых которыми никто ничто никакой некоторый
некоторые каждый любой иной другой другая другое другие прочий прочие остальной остальные такой такая такое такие первый первого
первому первым первом первая первой первую первое первые первых первыми второй второго второму вторым втором вторая вторую второе
вторые вторых вторыми третий третьего третьему третьим третьем третья третьей третью третье третьи третьих третьими четвертый пятый
последний предыдущий следующий оба обе обоих обеих вариант шаг этап пункт раздел часть глава где тут здесь там туда сюда оттуда тогда
когда пока уже еще только лишь даже почти просто очень более менее самый самая самое самые итого вместе впрочем однако зато поэтому
потому причем притом также тоже например скажем вроде типа около примерно приблизительно порядка свыше минимум максимум сегодня вчера
завтра сейчас теперь потом затем сначала сразу снова опять всегда часто редко иногда обычно раньше позже позднее далее дальше если хотя
ведь пусть""".split())
ITEM_LEAD_PREPS = frozenset("в во на за по для у к ко с со из от до при о об обо про под над перед через между около вокруг после среди против".split())
ITEM_BAD_NUM_PREPS = frozenset("после через из с со у к ко для при о об обо про под над перед между без кроме вместо среди против вокруг".split())
ITEM_VAL_PREPS = frozenset("за по в во на".split())
ITEM_LEAD_LOCATIVES = frozenset("меню прайсе прайс-листе каталоге списке перечне таблице продаже наличии сайте витрине заказе чеке счете тарифах ассортименте".split())
ITEM_CLASSIFIERS = tuple("тариф пакет план подписк опци модел верси размер формат уровен уровн режим тип класс категори курс линейк сери комплектаци зал зон корпус секци".split())
ITEM_NOUN_LI = frozenset("модели недели панели детали мебели качели капели стали соли пыли цели роли доли мили шали дали щели мели".split())
ITEM_COPULA_RX = re.compile(
    r"^(?:сто(?:ит|ят|ил[аио]?|имостью)|обойдется|обойдутся|обход(?:ится|ятся)|обош(?:елся|лась|лось|лись)|"
    r"выйд(?:ет|ут)|выход(?:ит|ят)|составл(?:яет|яют)|состав(?:ил[аио]?|или|ит|ят)|рав(?:ен|на|но|ны|няется|няются)|"
    r"дл(?:ится|ятся|ился|илась|илось|ились)|занима(?:ет|ют)|зан(?:ял[аио]?|яли)|займ(?:ет|ут)|вес(?:ит|ят|ил[аио]?)|вмеща(?:ет|ют))$")
ITEM_INTRO_VERB_RX = re.compile(
    r"^(?:есть|доступ(?:ен|на|но|ны)|представлен[аоы]?|предлага(?:ем|ют|ется|ются)|"
    r"пода(?:ем|ют|ется|ются)|готов(?:им|ят)|действу(?:ет|ют)|работа(?:ет|ют)|вход(?:ит|ят)|прода(?:ем|ют|ется|ются)|жд(?:ет|ут))$")
# END_BLOCK_LEXICON


def _norm(s: str) -> str:
    return s.replace("ё", "е").replace("Ё", "Е")


CASE_ENDINGS = frozenset(("",) + tuple(
    "а я о е и ы у ю ой ей ою ею ом ем ам ям ами ями ах ях ов ев ий ия ие ии ию ием ией иею "
    "ья ье ью ьи ьей ьею ая ое ые ый ого его ому ему ым им ую ых их ыми ими".split()))
_BAD_EMPTY_TAILS = frozenset("ия ии ию ием ией иею ья ьи ьей ьею ая ое ые ый".split())
_FEM_IYA_TAILS = frozenset("ия ии ию ием ией иею ья ьи ьей ьею".split())
_MASC_CASE_TAILS = frozenset("а у ом е".split())
_FLEET_L_RX = re.compile(r"л[ео]([вдн])$")
_FLEET_CONS_RX = re.compile(r"[бвгджзклмнпрстфхцчшщ][ео]([лкц])$")
_FLEET_VOW_C_RX = re.compile(r"[аеиоуыэюя][ея]ц$")
_FLEET_SOFT_RX = re.compile(r"[ео](?:нь|вь)$")
_FLEET_EY_RX = re.compile(r"(?:соловей|воробей|муравей|ручей|улей)$")


def _fleeting_stems(w: str) -> Tuple[str, ...]:
    if not w or w[-1] not in "вднлкцьй":
        return (w,)
    out = [w]
    if _FLEET_L_RX.search(w):
        out.append(w[:-3] + "ль" + w[-1])
    if w.endswith("елец"):
        out.append(w[:-4] + "ельц")
    if len(w) >= 4:
        if _FLEET_CONS_RX.search(w):
            out.append(w[:-2] + w[-1])
        if _FLEET_VOW_C_RX.search(w):
            out.append(w[:-2] + "йц")
        if _FLEET_SOFT_RX.search(w):
            out.append(w[:-3] + w[-2])
    if _FLEET_EY_RX.search(w):
        out.append(w[:-2] + "ь")
    return tuple(dict.fromkeys(out))


def _case_tail(tail: str) -> bool:
    return tail in CASE_ENDINGS or tail in ("ь", "й")


def _build_first_name_forms() -> frozenset:
    forms = set()
    masc = ("",) + tuple("а у ом ем е ов ова ову овым овой ев ева еву евым евой".split())
    for raw_n in FIRST_NAMES:
        n = _norm(raw_n.lower())
        max_len = len(raw_n) + 3
        if n.endswith("я"):
            cands = [n[:-1] + t for t in ("я", "и", "е", "ю", "ей", "ею")]
        elif n.endswith("а"):
            cands = [n[:-1] + t for t in ("а", "ы", "и", "е", "у", "ой", "ою", "ей", "ею")]
        elif n.endswith("й"):
            cands = [n[:-1] + t for t in "й я ю ем е и ев ева еву евым евой".split()]
        elif n.endswith("ь"):
            cands = ["любовь", "любви", "любовью"] if n == "любовь" else [
                n[:-1] + t for t in "ь я ю ем е ев ева еву евым евой".split()]
        else:
            cands = [n + t for t in masc]
            for stem in _fleeting_stems(n)[1:]:
                cands.extend(stem + t for t in masc[1:])
        for c in cands:
            if len(c) <= max_len:
                forms.add(c)
    return frozenset(forms)


FIRST_NAME_FORMS = _build_first_name_forms()


_ASCII_LATIN_RX = re.compile(r"^[a-z]+$")


def _same_stem_core(x: str, y: str, allow_short: bool = True) -> bool:
    if x == y:
        return True
    n = 0
    for cx, cy in zip(x, y):
        if cx != cy:
            break
        n += 1
    min_len = min(len(x), len(y))
    min_k = 2 if (allow_short and min_len <= 4) else 3
    for k in range(n, min_k - 1, -1):
        tx, ty = x[k:], y[k:]
        ok = (tx in CASE_ENDINGS and ty in CASE_ENDINGS) if k == 2 else (_case_tail(tx) and _case_tail(ty))
        if ok and k >= min_len - 2:
            if (tx == "" and ty in _BAD_EMPTY_TAILS) or (ty == "" and tx in _BAD_EMPTY_TAILS):
                continue
            if (tx in _FEM_IYA_TAILS and ty in _MASC_CASE_TAILS) or (ty in _FEM_IYA_TAILS and tx in _MASC_CASE_TAILS):
                continue
            return True
    return False


def _same_name_stem(x: str, y: str, allow_short: bool = True) -> bool:
    if _same_stem_core(x, y, allow_short):
        return True
    if len(x) >= 5 and len(y) >= 5 and ("э" in x or "э" in y):
        if (_same_stem_core(x.replace("э", "а"), y.replace("э", "а"), allow_short)
                or _same_stem_core(x.replace("э", "е"), y.replace("э", "е"), allow_short)):
            return True
    if _ASCII_LATIN_RX.fullmatch(x) and _ASCII_LATIN_RX.fullmatch(y):
        if (len(x) >= 3 and y in (x + "s", x + "es")) or (len(y) >= 3 and x in (y + "s", y + "es")):
            return True
        if len(x) == len(y) >= 6 and x[:4] == y[:4] and sum(cx != cy for cx, cy in zip(x[4:], y[4:])) == 1:
            return True
    return False


def _same_name_case_fleeting(a: str, b: str, allow_short: bool = True) -> bool:
    an, bn = _norm(a.lower()), _norm(b.lower())
    if an == bn:
        return True
    if "-" in an and "-" in bn:
        pa, pb = an.split("-"), bn.split("-")
        if len(pa) == len(pb) and all(
            x == y or any(_same_name_stem(sx, sy, allow_short) for sx in _fleeting_stems(x) for sy in _fleeting_stems(y))
            for x, y in zip(pa, pb)
        ):
            return True
    return any(_same_name_stem(sa, sb, allow_short) for sa in _fleeting_stems(an) for sb in _fleeting_stems(bn))


_ADJ_SK_RX = re.compile(r"^[ьй]?ск(?:ий|ая|ое|ие|ого|ой|ому|им|ом|их|ими|ую)$")
_ADJ_SK_END_RX = re.compile(r"[ьй]?ск(?:ий|ая|ое|ие|ого|ой|ому|им|ом|их|ими|ую)$")


def _part_base_keys(part: str) -> List[str]:
    out = []
    stems = _fleeting_stems(part)
    if "э" in part and len(part) >= 5:
        stems = list(stems)
        for st in list(stems):
            if "э" in st and len(st) >= 5:
                for rep in ("а", "е"):
                    alt = st.replace("э", rep)
                    if alt not in stems:
                        stems.append(alt)
    for st in stems:
        if st not in out:
            out.append(st)
        L_st = len(st)
        if L_st >= 3 and st[-1] in "аяоеиыуюйьмхв":
            for cut in range(1, min(3, L_st - 2) + 1):
                if _case_tail(st[L_st - cut:]):
                    base = st[:L_st - cut]
                    if base not in out:
                        out.append(base)
    if part and "a" <= part[0] <= "z" and _ASCII_LATIN_RX.fullmatch(part):
        if len(part) >= 4 and part.endswith("s"):
            if part[:-1] not in out:
                out.append(part[:-1])
            if len(part) >= 5 and part.endswith("es") and part[:-2] not in out:
                out.append(part[:-2])
        if len(part) >= 6 and part[:4] not in out:
            out.append(part[:4])
    elif len(part) >= 6 and part[-1] in "йяеомху":
        am = _ADJ_SK_END_RX.search(part)
        if am and am.start() >= 4:
            base = part[:am.start()]
            if base not in out:
                out.append(base)
    return out


def _name_keys(wn: str) -> Tuple[str, ...]:
    if "-" in wn:
        parts = wn.split("-")
        first_k, last_k = _part_base_keys(parts[0]), _part_base_keys(parts[-1])
        out = [f"{a}-{b}" for a in first_k for b in last_k]
        if all(p[:1].isalpha() for p in parts[1:] if p):
            for fk in first_k:
                if fk not in out:
                    out.append(fk)
        if wn not in out:
            out.append(wn)
        return tuple(out)
    return tuple(_part_base_keys(wn))


def _adj_name_match(a: str, b: str) -> bool:
    an, bn = _norm(a.lower()), _norm(b.lower())
    for base_w, adj_w in ((an, bn), (bn, an)):
        if len(base_w) < 4 or len(adj_w) < 6:
            continue
        n = 0
        for cx, cy in zip(base_w, adj_w):
            if cx != cy:
                break
            n += 1
        for k in range(min(n, len(base_w)), 3, -1):
            if k >= len(base_w) - 2 and _case_tail(base_w[k:]) and _ADJ_SK_RX.fullmatch(adj_w[k:]):
                return True
    return False


def _same_name_case(a: str, b: str) -> bool:
    return _same_name_case_fleeting(a, b, allow_short=False)


def name_match(a: str, b: str) -> bool:
    if _same_name_case_fleeting(a, b, allow_short=True):
        return True
    for comp, plain in ((a, b), (b, a)):
        if "-" in comp and "-" not in plain:
            parts = comp.split("-")
            if len(parts[0]) >= 2 and parts[0][:1].isupper() and all(p[:1].islower() for p in parts[1:] if p):
                if _same_name_case_fleeting(parts[0], plain, allow_short=True):
                    return True
    return _adj_name_match(a, b)


def stem_match(a: str, b: str, strict: bool = False) -> bool:
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
_CAP_WORD_RX = re.compile(r"[A-ZА-ЯЁ][\w-]*")
_LOWER_CYR_RX = re.compile(r"[а-яё]{2,}")


def _item_head(sentence: str, start: int, end: int, numbers) -> bool:
    part = sentence[start:min(end, start + 32)]
    if ITEM_HEAD_RX.match(part):
        return True
    return (start + len(ITEM_PAD_RX.match(part).group(0))) in numbers


def _clean_appos_head(sentence: str, a: int, b: int) -> bool:
    last_end = -1
    for m in _CAP_WORD_RX.finditer(sentence, a, b):
        last_end = m.end()
    return last_end >= 0 and _LOWER_CYR_RX.search(sentence, last_end, b) is None


def _merge_appositives(sentence: str, spans: List[Tuple[int, int]], numbers: List[int], who) -> List[Tuple[int, int]]:
    if len(spans) < 3 or not numbers:
        return spans
    nums_sorted = sorted(numbers)
    num_set = set(nums_sorted)
    has_num = lambda a, b: bisect.bisect_left(nums_sorted, b) > bisect.bisect_left(nums_sorted, a)
    slen = len(sentence)

    def _valid_mid(a: int, b: int) -> bool:
        return not has_num(a, b) and not who(a, b) and not APPOS_STOP_RX.match(_norm(sentence[a:b].lstrip().lower()))

    expanded = []
    for idx, (a, b) in enumerate(spans):
        did_split = False
        if idx + 2 < len(spans) and b < slen and sentence[b] == "," and has_num(a, b):
            m1, m2 = spans[idx + 1], spans[idx + 2]
            if (m1[1] < slen and sentence[m1[1]] == "," and _valid_mid(*m1)
                    and (has_num(*m2) or (idx + 3 < len(spans) and m2[1] < slen and sentence[m2[1]] == ","
                                         and _valid_mid(*m2) and has_num(*spans[idx + 3])))):
                last_and = None
                for am in AND_SPLIT_RX.finditer(sentence, a, b):
                    last_and = am
                if last_and is not None:
                    and_s, and_e = last_and.start(), last_and.end()
                    if (has_num(a, and_s) and not has_num(and_e, b) and _item_head(sentence, and_e, b, num_set)
                            and len(who(and_e, b)) == 1 and _clean_appos_head(sentence, and_e, b)):
                        expanded.extend(((a, and_s), (and_e, b)))
                        did_split = True
        if not did_split:
            expanded.append((a, b))

    out, i, n = [], 0, len(expanded)
    while i < n:
        merged = False
        if i + 2 < n:
            a_i, b_i = expanded[i]
            if (not has_num(a_i, b_i) and b_i < slen and sentence[b_i] == ","
                    and len(who(a_i, b_i)) == 1 and _clean_appos_head(sentence, a_i, b_i)):
                for j in (i + 2, i + 3):
                    if j >= n or not all(expanded[k][1] < slen and sentence[expanded[k][1]] == "," for k in range(i, j)):
                        break
                    if not all(_valid_mid(*expanded[k]) for k in range(i + 1, j)):
                        continue
                    a_j, b_j = expanded[j]
                    if not has_num(a_j, b_j) or APPOS_STOP_RX.match(_norm(sentence[a_j:b_j].lstrip().lower())):
                        continue
                    am = AND_SPLIT_RX.search(sentence, a_j, b_j)
                    if not who(a_j, am.start() if am else b_j):
                        out.append((a_i, b_j))
                        i = j + 1
                        merged = True
                        break
        if not merged:
            out.append(expanded[i])
            i += 1
    return out


def _split_and(sentence: str, a: int, b: int, numbers: List[int], who,
               memo: Optional[Dict[Tuple[int, int], List[Tuple[int, int]]]] = None) -> List[Tuple[int, int]]:
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
    split_choice = [None] * (k_len + 1)
    tail_who_cache = [None] * (k_len + 1)

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
    valid_js_rev = []
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
        max_j = valid_js_rev[0]
        if ands[max_j][0] > first_num and who(a_i, ands[max_j][0]):
            lo_v, hi_v = 0, len(valid_js_rev) - 1
            while lo_v < hi_v:
                mid_v = (lo_v + hi_v + 1) >> 1
                mj = valid_js_rev[mid_v]
                if ands[mj][0] > first_num and who(a_i, ands[mj][0]):
                    lo_v = mid_v
                else:
                    hi_v = mid_v - 1
            j = valid_js_rev[lo_v]
            mid_end = ands[j][0]
            left_who = who(a_i, mid_end)
            if len(left_who) == 1 and (split_choice[j + 1] is not None or get_tail_who(j + 1) != left_who):
                split_choice[i] = (mid_end, j + 1)
        if split_choice[i] is None:
            get_tail_who(i)

    res, cur = [], 0
    while split_choice[cur] is not None:
        mid_e, nxt_idx = split_choice[cur]
        res.append((starts_i[cur], mid_e))
        cur = nxt_idx
    res.append((starts_i[cur], b))
    if memo is not None:
        memo[(a, b)] = res
    return res


def list_clauses(sentence: str, numbers: List[int], who) -> List[Tuple[int, int]]:
    spans = _merge_appositives(sentence, clause_spans(sentence), numbers, who)
    out = []
    for a, b in spans:
        out.extend(_split_and(sentence, a, b, numbers, who))
    return out


def clause_span(sentence: str, offset: int, clauses: Optional[List[Tuple[int, int]]] = None) -> Tuple[int, int]:
    spans = clauses if clauses is not None else clause_spans(sentence)
    if spans:
        i = bisect.bisect_right(spans, (offset, 1 << 62)) - 1
        if i >= 0 and spans[i][0] <= offset < spans[i][1]:
            return spans[i]
    return 0, len(sentence)


def is_list(sentence: str, numbers: List[int], who,
            clauses: Optional[List[Tuple[int, int]]] = None) -> bool:
    spans = clauses if clauses is not None else list_clauses(sentence, numbers, who)
    nums_sorted, found = sorted(numbers), 0
    for a, b in spans:
        if bisect.bisect_left(nums_sorted, b) > bisect.bisect_left(nums_sorted, a) and len(who(a, b)) == 1:
            found += 1
            if found >= 2:
                return True
    return False


def split_sentences(text: str) -> List[Tuple[int, str]]:
    out, start = [], 0
    for m in re.finditer(r"(?<=[.!?…])\s+(?=[«\"(A-ZА-ЯЁ0-9])|\n+", text):
        if "\n" not in m.group() and m.start() > 0 and text[m.start() - 1] == ".":
            left = _norm(text[max(0, m.start() - 24):m.start()].lower())
            nxt_ch = text[m.end():m.end() + 1]
            if (nxt_ch.isdigit() and ABBREV_DIGIT_RX.search(left)) or (not nxt_ch.isdigit() and ABBREV_CAP_RX.search(left)):
                continue
        out.append((start, text[start:m.start()]))
        start = m.end()
    out.append((start, text[start:]))
    return [(s, t) for s, t in out if t.strip()]


def _canon_num(raw: str) -> Optional[float]:
    s = SEP_STRIP_RX.sub("", raw).replace(",", ".").lstrip("+")
    s = s.replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def _big_num_str(raw: str, scale_zeros: int = 0) -> str:
    s = SEP_STRIP_RX.sub("", raw).replace(",", ".").lstrip("+").replace("−", "-")
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


def _match_unit(text: str, pos: int):
    um = UNIT_RX.match(text, pos)
    if not um:
        return None
    raw_u = um.group(1)
    if raw_u.lower() == "с":
        if raw_u != "с":
            return None  # uppercase spaced "С" ("1 С") is not seconds
        tail = text[um.end():um.end() + 24]
        if tail.startswith("."):
            dm = BARE_S_DOT_LOWER_RX.match(_norm(tail))
            if dm and dm.group(1) not in BARE_S_ALLOW:
                return None  # "52 с. текста" -> pages, not seconds
        else:
            wm = BARE_S_NEXT_WORD_RX.match(_norm(tail))
            if wm and wm.group(1).lower() not in BARE_S_ALLOW:
                return None  # "500 с доставкой", "50 с лишним", "500 с НДС" -> preposition
    return um


def _mask_spans(text: str, spans: List[Tuple[int, int]]) -> str:
    if not spans:
        return text
    out: List[str] = []
    pos = 0
    for a, b in spans:
        if a < pos:
            a = pos
        if a < b:
            out.append(text[pos:a])
            out.append(" " * (b - a))
            pos = b
    out.append(text[pos:])
    return "".join(out)


_PROSE_FENCE_TAGS = frozenset(("", "markdown", "md", "text", "txt", "plain", "plaintext"))


def _is_code_fence(info: str, fbody: str) -> bool:
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", fbody)
    if sum(1 for x in letters if x > "z") < 0.3 * max(1, len(letters)):
        return True
    parts = info.strip().split(None, 1)
    tag = parts[0].lower() if parts else ""
    if tag in _PROSE_FENCE_TAGS:
        return False
    lits = _code_literal_spans(fbody, False)
    if not lits:
        return False
    outside = []
    p = 0
    for ls, le in lits:
        outside.append(fbody[p:ls])
        p = le
    outside.append(fbody[p:])
    out_letters = re.findall(r"[A-Za-zА-Яа-яЁё]", "".join(outside))
    return bool(out_letters) and sum(1 for x in out_letters if x > "z") < 0.3 * len(out_letters)


def _code_fence_spans(text: str) -> List[Tuple[int, int, int, int, bool]]:
    if "```" not in text and "~~~" not in text:
        return []
    out, n, pos, in_fence, f_char, f_len, open_s, body_s, f_info = [], len(text), 0, False, "", 0, 0, 0, ""
    while pos < n:
        nl = text.find("\n", pos)
        line_end, next_pos = (n, n) if nl < 0 else (nl, nl + 1)
        eff_end = line_end - 1 if line_end > pos and text[line_end - 1] == "\r" else line_end
        i = pos
        while i < eff_end and text[i] == " " and i - pos < 4:
            i += 1
        if i - pos <= 3 and i < eff_end and text[i] in ("`", "~"):
            ch, j = text[i], i
            while j < eff_end and text[j] == ch:
                j += 1
            if j - i >= 3:
                rest = text[j:eff_end]
                if not in_fence:
                    if nl >= 0 and (ch == "~" or "`" not in rest):
                        in_fence, f_char, f_len, open_s, body_s, f_info, pos = True, ch, j - i, pos, next_pos, rest, next_pos
                        continue
                elif ch == f_char and j - i >= f_len and not rest.strip(" \t"):
                    out.append((open_s, line_end, body_s, pos, _is_code_fence(f_info, text[body_s:pos])))
                    in_fence, pos = False, next_pos
                    continue
        pos = next_pos
    return out


def _inline_code_spans(s: str, skip_spans: List[Tuple[int, int]]) -> List[Tuple[int, int, int, int]]:
    if "`" not in s:
        return []
    out, n, fi, n_skip, i = [], len(s), 0, len(skip_spans), 0
    while i < n:
        while fi < n_skip and skip_spans[fi][1] <= i:
            fi += 1
        if fi < n_skip and skip_spans[fi][0] <= i < skip_spans[fi][1]:
            i = skip_spans[fi][1]
            continue
        bt = s.find("`", i)
        if bt < 0:
            break
        while fi < n_skip and skip_spans[fi][1] <= bt:
            fi += 1
        if fi < n_skip and skip_spans[fi][0] <= bt < skip_spans[fi][1]:
            i = skip_spans[fi][1]
            continue
        bs, k = 0, bt - 1
        while k >= 0 and s[k] == "\\":
            bs += 1
            k -= 1
        run_end = bt
        while run_end < n and s[run_end] == "`":
            run_end += 1
        run_len = run_end - bt
        if bs & 1:
            i = run_end
            continue
        nl = s.find("\n", run_end)
        limit = n if nl < 0 else nl
        if fi < n_skip and skip_spans[fi][0] < limit:
            limit = skip_spans[fi][0]
        cur, matched = run_end, False
        while cur < limit:
            cpos = s.find("`", cur, limit)
            if cpos < 0:
                break
            cend = cpos
            while cend < limit and s[cend] == "`":
                cend += 1
            if cend - cpos == run_len and cpos > run_end:
                out.append((bt, cend, run_end, cpos))
                i, matched = cend, True
                break
            cur = cend
        if not matched:
            i = run_end
    return out


def _mask_code_fences(text: str) -> str:
    return _mask_spans(text, [(a, b) for a, b, _, _, is_code in _code_fence_spans(text) if is_code])


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
    all_fences = _code_fence_spans(text)
    code_fence_ranges = [(a, b) for a, b, _, _, is_code in all_fences if is_code]
    prose_text = _mask_spans(text, code_fence_ranges)
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

    has_cyr = bool(re.search(r"[А-Яа-яЁё]", text))
    has_curr_sym = any(c in text for c in "$€£¥₽")
    _unit_lead = SEP + "&%₽$€£¥°"

    def upgrade_pound(unit: str, num_pos: int) -> str:
        if unit == "фунт" and POUND_MONEY_RX.search(_norm(text[max(0, num_pos - 36):num_pos])):
            return "£"
        return unit

    def hedge_before(pos: int) -> str:
        if not has_cyr or pos == 0:
            return ""
        left = _norm(text[max(0, pos - 40):pos].lower())
        if not CYR_ANY_RX.search(left):
            return ""
        hm = HEDGE_BEFORE_RX.search(left)
        if not hm:
            return ""
        raw_h = hm.group(1) or hm.group(3) or hm.group(4)
        h = HEDGE_CLEAN_RX.sub(" ", raw_h).strip()
        if hm.group(2) == "за" and h in ("не позже", "не позднее", "не раньше"):
            h += " за"
        return h

    # START_BLOCK_URLS
    if "://" in text or "w." in text or "W." in text:
        for m in re.finditer(URL_RX, text):
            url = m.group().rstrip(URL_TAIL)
            facts.items.append(Fact("url", _url_key(url), url, sent_of(m.start()), m.start()))
            take(m.start(), m.start() + len(url))
        flush_taken()
    if "@" in text:
        for m in re.finditer(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
            if free(m.start(), m.end()):
                facts.items.append(Fact("email", m.group().lower(), m.group(), sent_of(m.start()), m.start()))
                take(m.start(), m.end())
        flush_taken()
    # Phones are compared by digits: +7 (999) 123-45-67 = 8 999 123 45 67.
    if "+" in text or "8" in text:
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
    # HTML entities other than &nbsp; (which acts as a thousands/unit space in NUM_RX/UNIT_RX)
    # are not numbers or names (&REG;, &COPY;, &#8212;).
    nbsp_spans: List[Tuple[int, int]] = []
    if "&" in text:
        for m in HTML_ENTITY_RX.finditer(text):
            if not free(m.start(), m.end()):
                continue
            if m.group().lower() == "&nbsp;":
                nbsp_spans.append((m.start(), m.end()))
            else:
                take(m.start(), m.end())
        flush_taken()
    # END_BLOCK_URLS

    # START_BLOCK_DATES_TIMES
    if "." in text:
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
    if has_cyr:
        for m in DATE_NAMED_RX.finditer(text):
            days = [int(d) for d in filter(None, (m.group(1), m.group(2)))]
            if not all(1 <= d <= 31 for d in days) or not free(m.start(), m.end()):
                continue
            month = MONTH_STEM.get(m.group(3).lower()[:3], 0)
            for day in days:
                facts.items.append(Fact("date", "%02d.%02d" % (day, month), m.group(),
                                        sent_of(m.start()), m.start(), hedge_before(m.start())))
            if m.group(4):
                facts.items.append(Fact("number", m.group(4), m.group(4), sent_of(m.start()), m.start()))
            take(m.start(), m.end())
        flush_taken()
    if "." in text:
        for m in DATE_DOT_RX.finditer(text):
            if free(m.start(), m.end()):
                d_num, m_num = int(m.group(1)), int(m.group(2))
                if 1 <= d_num <= 31 and 1 <= m_num <= 12:
                    facts.items.append(Fact("date", "%02d.%02d" % (d_num, m_num),
                                            m.group(), sent_of(m.start()), m.start(), hedge_before(m.start())))
                    year = m.group(3) if len(m.group(3)) == 4 else "20" + m.group(3)
                    facts.items.append(Fact("number", year, m.group(3), sent_of(m.start()), m.start()))
                    take(m.start(), m.end())
        flush_taken()
    norm_text = _norm(text)

    def _ratio_cue_before(pos: int) -> bool:
        s_idx = sent_of(pos)
        s0 = facts.starts[s_idx] if s_idx < len(facts.starts) else 0
        win = _norm(text[max(s0, pos - 36):pos].lower())
        return bool(RATIO_CUE_RX.search(win) and not TIME_PREP_RX.search(win))

    if ":" in text or "." in text:
        for m in TIME_RX.finditer(text):
            if text[m.end(1)] == "." and (
                    _match_unit(text, m.end()) or (text[m.end():m.end() + 1] in "-–—" and HYPHEN_UNIT_RX.match(norm_text, m.end()))
                    or PREFIX_TIME_CURR_RX.search(text[max(0, m.start() - 6):m.start()])
                    or re.search(r"(?<![\w.,])[+\-−]$", text[max(0, m.start() - 2):m.start()])
                    or re.search(r"[$€£¥₽][ \u00a0\u202f]*[+\-−]?\d+(?:[.,]\d+)?[ \t\u00a0]*[–—-][ \t\u00a0]*$",
                                 text[max(0, m.start() - 24):m.start()])
                    or SCALE_RX.match(text, m.end())):
                continue
            if text[m.end(1)] == ":" and _ratio_cue_before(m.start()):
                continue
            if free(m.start(), m.end()):
                hh, mm = int(m.group(1)), m.group(2)
                value = str(hh) if mm == "00" else "%d:%s" % (hh, mm)
                facts.items.append(Fact("number", value, m.group(), sent_of(m.start()), m.start(),
                                        hedge_before(m.start()), "время"))
                take(m.start(), m.end())
        flush_taken()

    def _add_ratio(a_raw: str, b_raw: str, raw: str, pos: int) -> None:
        va_n, vb_n = _canon_num(a_raw), _canon_num(b_raw)
        if va_n is not None and vb_n is not None and math.isfinite(va_n) and math.isfinite(vb_n):
            va, vb = _fmt(va_n), _fmt(vb_n)
            if va != vb:
                facts.items.append(Fact("ratio", "%s:%s" % (va, vb), raw, sent_of(pos), pos))

    if ":" in prose_text:
        for m in RATIO_COLON_RX.finditer(prose_text):
            if free(m.start(), m.end()):
                a_raw, b_raw = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(4))
                _add_ratio(a_raw, b_raw, m.group(), m.start())
    if has_cyr:
        for m in RATIO_K_RX.finditer(prose_text):
            if free(m.start(), m.end()):
                _add_ratio(m.group(1), m.group(2), m.group(), m.start())
        for m in RATIO_NA_RX.finditer(prose_text):
            if free(m.start(), m.end()) and _ratio_cue_before(m.start()):
                _add_ratio(m.group(1), m.group(2), m.group(), m.start())
        seen_wk_pos = set()
        for m in WEEKDAY_RX.finditer(prose_text):
            if free(m.start(), m.end()):
                day = WEEKDAY_NUM[_norm(m.group(1).lower())]
                facts.items.append(Fact("date", "день недели %d" % day, m.group(), sent_of(m.start()), m.start()))
                seen_wk_pos.add(m.start())
        for m in WEEKDAY_WED_RX.finditer(prose_text):
            g = next(k for k in (1, 2, 3, 4) if m.group(k) is not None)
            ws, we = m.start(g), m.end(g)
            if ws not in seen_wk_pos and free(ws, we):
                seen_wk_pos.add(ws)
                facts.items.append(Fact("date", "день недели 3", m.group(g), sent_of(ws), ws))
        for m in WEEKDAY_RANGE_RX.finditer(prose_text):
            for g in (1, 2):
                ws, we = m.start(g), m.end(g)
                if ws not in seen_wk_pos and free(ws, we):
                    seen_wk_pos.add(ws)
                    facts.items.append(Fact("date", "день недели %d" % WEEKDAY_ABBR[m.group(g).lower()], m.group(g),
                                            sent_of(ws), ws))
        for rx in (WEEKDAY_DATE_RX, WEEKDAY_PREP_RX):
            for m in rx.finditer(prose_text):
                ws, we = m.start(1), m.end(1)
                if ws not in seen_wk_pos and free(ws, we):
                    seen_wk_pos.add(ws)
                    facts.items.append(Fact("date", "день недели %d" % WEEKDAY_ABBR[m.group(1).lower()],
                                            m.group(1), sent_of(ws), ws))
        for m in MONTH_ANY_RX.finditer(text):
            if m.group()[0].isupper():
                k = m.start() - 1
                while k >= 0 and text[k] in " \t\xa0":
                    k -= 1
                if k >= 0 and text[k] not in ".!?…\n:—–-«\"(*#>|":
                    continue
            if free(m.start(), m.end()):
                month = MONTH_ANY_NUM[next(g for g in m.groups() if g).lower()]
                facts.items.append(Fact("month", str(month), m.group(), sent_of(m.start()), m.start()))
    # END_BLOCK_DATES_TIMES

    # START_BLOCK_NUMBERS
    # Counters in headings ("Вариант 1", "Шаг 2") are structure, not facts.
    for m in re.finditer(r"(?i)(?:вариант|шаг|этап|пункт|раздел|часть|глава|блок)\s+(\d+)", text):
        take(m.start(1), m.end(1))
    # List markers at a line start ("1. Возьмите чек", "2) …", "## 3. Раздел", "> 4. …", "**5. Заголовок**").
    sp = "[ \\t\\u00a0\\u202f]"
    for m in re.finditer(r"(?m)^[ \t\u00a0\u202f\ufeff]*(?:>%s*)*(?:#{1,6}%s+)?(?:[-*+]%s+)?(?:\*\*|__|\*|_)?"
                         r"(\d{1,2})[.)](?=[ \t\u00a0\u202f*_])" % (sp, sp, sp), text):
        take(m.start(1), m.end(1))
    for m in re.finditer(r"(\d)\ufe0f?\u20e3", text):
        take(m.start(1), m.end(1))
    flush_taken()

    def _units_compat(u1: str, u2: str) -> bool:
        return u1 == u2 or (u1 == "¥" and u2 in ("JPY", "CNY")) or (u2 == "¥" and u1 in ("JPY", "CNY"))

    def _apply_scale(value, plain: str, is_acct: bool, is_big: bool, scale: int):
        scale_zeros = len(str(scale)) - 1
        if is_acct:
            return value + "0" * scale_zeros
        if is_big:
            return _big_num_str(plain, scale_zeros)
        value *= scale
        return _big_num_str(plain, scale_zeros) if not math.isfinite(value) else value

    def read_number(start: int, digits: str, glued: bool = True, prefix_unit: str = "") -> Optional[Tuple[str, str, int]]:
        plain = SEP_STRIP_RX.sub("", digits) if len(digits) >= 5 else digits
        is_acct = len(plain) >= 16 and bool(ACCT_RX.fullmatch(plain))
        if is_acct:
            is_big, value = False, plain
        else:
            is_big = len(plain) >= 16 and len(SIGN_RX.sub("", plain).split(".", 1)[0].split(",", 1)[0]) >= 16
            if is_big:
                value = _big_num_str(plain)
            else:
                try:
                    value = float(plain.replace(",", ".").replace("−", "-"))
                except ValueError:
                    return None
                if not math.isfinite(value):
                    is_big = True
                    value = _big_num_str(plain)
        end = start + len(digits)
        sc, unit = None, ""

        def _take_unit(m_u, fallback_prefix: bool) -> None:
            nonlocal unit, end
            if m_u:
                u_m = _canon_unit(m_u.group(1))
                if not prefix_unit or (u_m and _units_compat(u_m, prefix_unit)):
                    unit = prefix_unit if (prefix_unit and u_m == "¥") else u_m
                    end = m_u.end()
                elif fallback_prefix:
                    unit = prefix_unit
            if not unit and prefix_unit and fallback_prefix:
                unit = prefix_unit

        if glued and text[end:end + 1].isalpha():
            gm = GLUED_UNIT_RX.match(text, end)
            if gm:
                _take_unit(gm, True)
            else:
                gsm = GLUED_SCALE_RX.match(text, end)
                if gsm:
                    sc = gsm
                    value = _apply_scale(value, plain, is_acct, is_big, SCALE[gsm.group(1)])
                    end = gsm.end()
                    _take_unit(_match_unit(text, end), True)
                elif text[end] in ("к", "k") and not text[end + 1:end + 2].isalpha():
                    sc = True
                    value = _apply_scale(value, plain, is_acct, is_big, 1000)
                    end += 1
                    _take_unit(_match_unit(text, end), True)
                else:
                    return None
        else:
            em_end = end + (2 if text[end:end + 2] in ("**", "__") else (1 if text[end:end + 1] in ("*", "_") else 0))
            ch_em = text[em_end:em_end + 1]
            if ch_em and ch_em in SEP:
                sc = SCALE_RX.match(text, em_end)
                if sc:
                    value = _apply_scale(value, plain, is_acct, is_big, SCALE[sc.group(1).lower()])
                    end = em_end = sc.end()
                    ch_em = text[em_end:em_end + 1]
            um = _match_unit(text, em_end) if (ch_em and (ch_em in _unit_lead or ch_em.isalpha())) else None
            if um:
                _take_unit(um, True)
            elif not prefix_unit and text[end:end + 1] in "-–—":
                hm = HYPHEN_UNIT_RX.match(norm_text, end)
                if hm:
                    unit, end = COMPOUND_UNIT[hm.group(1).lower()], hm.end()
            elif prefix_unit:
                unit = prefix_unit
        unit = upgrade_pound(unit, start)
        if unit == "г" and not sc and not isinstance(value, str) and value == int(value) and 1800 <= value <= 2100:
            unit = "год"
        return (value if isinstance(value, str) else _fmt(value), unit, end)

    for m in NUM_RX.finditer(text):
        digits = m.group()
        num_start = m.start()
        prefix_unit = ""
        neg_prefix = False
        pm = PREFIX_CURR_RX.search(text[max(0, m.start() - 6):m.start()]) if has_curr_sym else None
        if pm and free(m.start() - len(pm.group(0)), m.start()):
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
    if has_cyr:
        for m in COMPOUND_NUM_RX.finditer(norm_text):
            if free(m.start(), m.end()):
                v = float(COMPOUND_NUM[m.group(1).lower()])
                unit = COMPOUND_UNIT[m.group(2).lower()]
                facts.items.append(Fact("number", _fmt(v), text[m.start():m.end()], sent_of(m.start()),
                                        m.start(), hedge_before(m.start()), unit))
                take(m.start(), m.end())
        flush_taken()
        for m in WORD_RX.finditer(norm_text):
            if not free(m.start(), m.end()):
                continue
            w0 = m.group(1).lower()
            v = float(WORD_NUM[w0])
            end = m.end()
            if w0 not in WORD_NO_CONT:
                while True:
                    nxt = WORD_CONT_RX.match(norm_text, end)
                    if not nxt:
                        break
                    w = float(WORD_NUM.get(nxt.group(1).lower(), 1))
                    last_order = 100 if v % 100 == 0 and v >= 100 else (10 if v % 10 == 0 and v >= 20 else 1)
                    if last_order == 1 or w >= last_order or w != int(w):
                        break
                    v += w
                    end = nxt.end()
            sc = SCALE_RX.match(text, end)
            if sc:
                v *= SCALE[sc.group(1).lower()]
                end = sc.end()
            unit = ""
            um = _match_unit(text, end)
            if um:
                unit = upgrade_pound(_canon_unit(um.group(1)), m.start())
                end = um.end()
            facts.items.append(Fact("number", _fmt(v), text[m.start():end], sent_of(m.start()),
                                    m.start(), hedge_before(m.start()), unit))
            take(m.start(), end)
        flush_taken()
    if nbsp_spans:
        for a, b in nbsp_spans:
            take(a, b)
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
        elif (f2.unit and not f1.unit and f1.hedge == "от"
              and re.fullmatch(r"[ \t\u00a0]+(?:до|по)[ \t\u00a0]+", between, re.I)):
            facts.items[i1] = replace(f1, unit=f2.unit)
    # END_BLOCK_NUMBERS

    # START_BLOCK_NAMES_QUOTES
    # Mask <30%-Cyrillic fenced code and HTML tags before quote, name & _is_initial scanning.
    tag_spans = [(m.start(), m.end()) for m in HTML_ANY_TAG_RX.finditer(prose_text)] if "<" in prose_text else []
    quote_text = _mask_spans(prose_text, tag_spans)
    for m in QUOTE_RX.finditer(quote_text):
        q = next(g for g in m.groups() if g).strip()
        dash = DASH_AFTER_RX.match(quote_text[m.end():m.end() + 8])
        speech = bool(COLON_BEFORE_QUOTE_RX.search(quote_text[max(0, m.start() - 24):m.start()]) or
                      (dash and (dash.group(1) or q.endswith(("?", "!", "…")))))
        if not speech:
            k_left = m.start() - 1
            while k_left >= 0 and quote_text[k_left] in " \t\u00a0>*_—–-":
                k_left -= 1
            if k_left < 0 or quote_text[k_left] == "\n":
                line_start = quote_text[k_left + 1:m.start()]
                if LINE_EM_RX.fullmatch(line_start):
                    speech = True
                elif LINE_HY_RX.fullmatch(line_start):
                    k_right = m.end()
                    while k_right < len(quote_text) and quote_text[k_right] in ".!?…*_ \t\u00a0":
                        k_right += 1
                    speech = (k_right == len(quote_text) or quote_text[k_right] in "\r\n")
        facts.items.append(Fact("quote", q.lower(), q, sent_of(m.start()), m.start(), speech=speech))

    cap_buckets: Optional[Dict[str, List[Tuple[int, str]]]] = None

    def _cap_elsewhere(word: str, pos: int) -> bool:
        nonlocal cap_buckets
        if cap_buckets is None:
            cap_buckets = {}
            for cm in NAME_RX.finditer(quote_text):
                cpos = cm.start()
                cword = cm.group(1)
                if not free(cpos, cpos + len(cword)) or _is_initial(quote_text, cpos):
                    continue
                for bk in _name_keys(_norm(cword.lower())):
                    cap_buckets.setdefault(bk, []).append((cpos, cword))
        for bk in _name_keys(_norm(word.lower())):
            for start_c, other in cap_buckets.get(bk, ()):
                if start_c != pos and _same_name_case(word, other):
                    return True
        return False

    for s_start, sent in sents:
        # Latin acronyms of any length; Cyrillic ones up to 4 letters (США, РФ, МЧС).
        sent_clean = quote_text[s_start:s_start + len(sent)]
        for m in NAME_RX.finditer(sent_clean):
            word = m.group(1)
            pos = s_start + m.start()
            if not free(pos, pos + len(word)):
                continue
            first = _is_initial(quote_text, pos)
            if word in SENT_START_STOP or POLITE_PRONOUN.fullmatch(word):
                continue
            if first and not (_cap_elsewhere(word, pos) or _norm(word.lower()) in FIRST_NAME_FORMS):
                facts.items.append(Fact("subject", word, word, sent_of(pos), pos))
                continue
            facts.items.append(Fact("name", word, word, sent_of(pos), pos))
    # END_BLOCK_NAMES_QUOTES

    # START_BLOCK_NEGATIONS
    if has_cyr:
        low = _norm(text.lower())
        low_stops = [sm.start() for sm in re.finditer(r"[.!?\n]", low)]
        for m in NEG_RX.finditer(low):
            if m.group(1):
                si = bisect.bisect_left(low_stops, m.end())
                s_end = low_stops[si] if si < len(low_stops) else len(low)
                contrast = bool(
                    re.search(r"(?:^|[^а-яё])а[ \t\u00a0\u202f]+$", low[max(0, m.start() - 4):m.start()])
                    or re.search(r",[ \t\u00a0\u202f]*а[ \t\u00a0\u202f]+(?!(?:еще|также|потом|затем)(?![а-яё]))",
                                 low[m.end():min(s_end, m.end() + 240)]))
                polar_li = bool(not contrast and m.group(1) == "не"
                                and re.match(r"[ \t\u00a0\u202f]+ли(?![а-яё])", low[m.end():m.end() + 8]))
                neg_kind = "contrast" if contrast else ("polar_li" if polar_li else "")
                facts.items.append(Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(),
                                        hedge=m.group(1), unit=neg_kind))
            else:
                facts.items.append(Fact("negation", m.group(3), m.group(), sent_of(m.start()), m.start(),
                                        hedge=m.group(3)))
    # END_BLOCK_NEGATIONS

    # START_BLOCK_CODE
    # Code is carried as is: `inline code` and fenced blocks (<30% Cyrillic on body), spaces collapsed.
    def _code(s: str) -> str:
        return " ".join(s.split())
    skip_inline: List[Tuple[int, int]] = []
    for open_s, close_e, body_s, body_e, is_code in all_fences:
        if is_code:
            body = text[body_s:body_e]
            if _code(body):
                facts.items.append(Fact("code_block", _code(body), body.strip(), sent_of(open_s), open_s))
            skip_inline.append((open_s, close_e))
        else:
            skip_inline.append((open_s, body_s))
            skip_inline.append((body_e, close_e))
    for full_s, _, body_s, body_e in _inline_code_spans(text, skip_inline):
        raw_c = text[body_s:body_e]
        if _code(raw_c):
            facts.items.append(Fact("code", _code(raw_c), raw_c, sent_of(full_s), full_s))
    # END_BLOCK_CODE
    return facts


_CLAUSE_CONJ_WORDS = frozenset(("но", "а", "и", "однако", "зато", "или"))


class _TextIndex:
    def __init__(self, text: str):
        self.text = text
        self.stops = [m.start() for m in re.finditer(r"[.!?\n]", text)]
        self.buckets = {}
        for m in re.finditer(r"[а-яё]{3,}", text):
            self.buckets.setdefault(m.group()[:3], []).append((m.start(), m.end(), m.group()))
        self._occ, self._neg, self._instead = {}, {}, {}
        self._all_neg, self._none_neg, self._all_inst = {}, {}, {}
        self._neg_words = self._ne_pref = None
        self._neg_word, self._ne_count = {}, {}

    def occurrences(self, word: str) -> List[Tuple[int, int]]:
        got = self._occ.get(word)
        if got is None:
            got = [(a, b) for a, b, w in self.buckets.get(word[:3], ())
                   if not (w in ("больше", "меньше") and word not in ("больше", "меньше"))
                   and stem_match(w, word, strict=True)]
            self._occ[word] = got
        return got

    def negated(self, word: str) -> List[bool]:
        got = self._neg.get(word)
        if got is None:
            got = [self.negated_at(a, b) for a, b in self.occurrences(word)]
            self._neg[word] = got
        return got

    def instead(self, word: str) -> List[bool]:
        got = self._instead.get(word)
        if got is None:
            got = [self.instead_at(a, b) for a, b in self.occurrences(word)]
            self._instead[word] = got
        return got

    def all_negated(self, word: str) -> bool:
        got = self._all_neg.get(word)
        if got is None:
            got = self._all_neg[word] = all(self.negated(word))
        return got

    def none_negated(self, word: str) -> bool:
        got = self._none_neg.get(word)
        if got is None:
            got = self._none_neg[word] = not any(self.negated(word))
        return got

    def all_instead(self, word: str) -> bool:
        got = self._all_inst.get(word)
        if got is None:
            plain = [i for i, n in zip(self.instead(word), self.negated(word)) if not n]
            got = self._all_inst[word] = bool(plain) and all(plain)
        return got

    def negation_words(self) -> Dict[str, List[str]]:
        if self._neg_words is None:
            buckets = {}
            for m in NEG_WORDS_SCAN_RX.finditer(self.text):
                buckets.setdefault(m.group(2)[:3], []).append(m.group(2))
            self._neg_words = buckets
        return self._neg_words

    def negated_word(self, word: str) -> bool:
        got = self._neg_word.get(word)
        if got is None:
            got = self._neg_word[word] = any(stem_match(w, word, strict=True)
                                             for w in self.negation_words().get(word[:3], ()))
        return got

    def ne_prefix_count(self, word: str) -> int:
        got = self._ne_count.get(word)
        if got is None:
            if self._ne_pref is None:
                buckets = {}
                for m in re.finditer(r"(?<![а-яё])не([а-яё]{4,})", self.text):
                    buckets.setdefault(m.group(1)[:3], []).append(m.group(1))
                self._ne_pref = buckets
            got = self._ne_count[word] = sum(
                1 for w in self._ne_pref.get(word[:3], ()) if stem_match(w, word, strict=True) and name_match(w, word))
        return got

    def sentence(self, start: int, end: int) -> Tuple[int, int]:
        i, j = bisect.bisect_left(self.stops, start), bisect.bisect_left(self.stops, end)
        return (self.stops[i - 1] + 1 if i else 0), (self.stops[j] if j < len(self.stops) else len(self.text))

    def negated_at(self, start: int, end: int) -> bool:
        s_from, s_to = self.sentence(start, end)
        txt, i, prev_conj = self.text, start, False
        for _ in range(3):
            while i > s_from and txt[i - 1].isspace():
                i -= 1
            if i <= s_from:
                break
            w_end = i
            while i > s_from and not txt[i - 1].isspace():
                i -= 1
            tok = txt[i:w_end]
            st = tok.rstrip("»\"'*_)")
            if st.endswith(";") or (prev_conj and (st.endswith((",", "—", "–")) or tok in ("—", "–"))):
                break
            letters = re.sub(r"[^а-яё]", "", tok) if w_end - i <= 24 else ""
            if letters == "нет" and st.endswith(","):
                break
            if letters in NEG_WORDS:
                return True
            prev_conj = letters in _CLAUSE_CONJ_WORDS
        j = end
        saw_sep = txt[end:min(s_to, end + 2)].lstrip("»\"'*_)").startswith((",", ";", "—", "–"))
        for _ in range(4):
            while j < s_to and txt[j].isspace():
                j += 1
            if j >= s_to:
                break
            w_start = j
            while j < s_to and not txt[j].isspace():
                j += 1
            tok = txt[w_start:j]
            letters = re.sub(r"[^а-яё]", "", tok) if j - w_start <= 24 else ""
            if saw_sep and letters in _CLAUSE_CONJ_WORDS:
                break
            if letters in NEG_WORDS:
                return True
            st = tok.rstrip("»\"'*_)")
            if st.endswith(";"):
                break
            saw_sep = st.endswith((",", "—", "–")) or tok in ("—", "–")
        return False

    def instead_at(self, start: int, end: int) -> bool:
        s_from, _ = self.sentence(start, end)
        return bool(re.search(r"(?<![а-яё])вместо\s+того,?\s+чтобы\s+$", self.text[max(s_from, start - 48):start]))


FOOTNOTE_MARK_RX = re.compile(
    r"\[(?:\d{1,4}(?:[ \t\u00a0]*[,;–—-][ \t\u00a0]*(?:(?:с|стр|т|ч|гл|п|ст|разд|прим|вып|кн|pp?|s)\.?[ \t\u00a0]*)?\d{1,4})*)\]$"
    r"|\[\^[A-Za-zА-Яа-яЁё0-9_-]{1,20}\]$|\[[А-ЯЁA-Z][^\]\n]{1,40}\d{4}[^\]]*\]$|\(\d{1,3}\)$", re.I)
LIST_NUM_RX = re.compile(r"\d+[.)]")


def _is_table_header_pipe(text: str, pipe_pos: int) -> bool:
    line_s = text.rfind("\n", 0, pipe_pos) + 1
    if not text[line_s:pipe_pos].strip(" \t"):
        return False
    line_e = text.find("\n", pipe_pos)
    line_e = len(text) if line_e < 0 else line_e
    line = text[line_s:line_e]
    if any(c.isdigit() for c in line):
        return False
    if line_s > 0:
        prev_line = text[text.rfind("\n", 0, line_s - 1) + 1:line_s - 1].strip()
        if prev_line.startswith("|") or prev_line.count("|") >= 2:
            return False
    if line_e < len(text):
        next_e = text.find("\n", line_e + 1)
        next_line = text[line_e + 1:len(text) if next_e < 0 else next_e]
        if TABLE_SEP_LINE_RX.match(next_line) or ("|" in next_line and any(c.isdigit() for c in next_line)):
            return True
    return len([c for c in line.strip().strip("|").split("|") if c.strip()]) >= 3


_CELL_PHRASE_RX = re.compile(r"[\w-]+[ \t\u00a0*_]+[а-яё]{2,}")


def _is_initial(text: str, pos: int) -> bool:
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch in ",;":
            return False
        if ch == "|":
            if not text[text.rfind("\n", 0, i) + 1:i].strip(" \t") or _is_table_header_pipe(text, i):
                return True
            return bool(_CELL_PHRASE_RX.match(text[pos:pos + 40]))
        if ch == "\n" or ch in "!?…:":
            return True
        if ch == ".":
            return not ABBREV_CAP_RX.search(_norm(text[max(0, i - 24):i + 1].lower()))
        if ch in "])":
            mark = FOOTNOTE_MARK_RX.search(text[max(0, i - 64):i + 1])
            if mark:
                i -= len(mark.group())
                continue
        if (ch.isalnum() and not (ch.isdigit() and LIST_NUM_RX.match(text[i:min(pos, i + 16)]))) or ch.isalpha():
            return False
        i -= 1
    return True


ASSISTANT_UTM_SOURCES = frozenset(
    "chatgpt.com openai copilot.com perplexity.ai claude.ai gemini.google.com grok.com chat.deepseek.com deepseek.com".split())


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


_ANY_INV_SCAN_RX = re.compile(
    r"[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f"
    r"\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0\ufffc\U000e0000-\U000e007f\U000e0100-\U000e01ef]")


def _strip_invisibles(chunk: str, prev_ch: str = "", next_ch: str = "") -> Tuple[str, int]:
    if not _ANY_INV_SCAN_RX.search(chunk):
        return chunk, 0
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
        left_c = out[-1] if out else prev_ch
        if cp in (0x1F3F4, 0x1F3F3):
            in_flag = True
        elif not (in_flag and cp == 0xFE0F and left_c and ord(left_c) in (0x1F3F4, 0x1F3F3)):
            in_flag = False
        if cp in SPACE_SPOOFERS:
            removed += 1
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
            right_c = _next_kept(i + 1)
            if ((left_c and _is_emoji(left_c))
                    or (bool(left_c) and left_c in "0123456789#*" and right_c == "\u20e3")):
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
    all_fences = _code_fence_spans(s)
    spans: List[Tuple[int, int]] = []
    skip_inline: List[Tuple[int, int]] = []
    for open_s, close_e, body_s, body_e, is_code in all_fences:
        if is_code:
            spans.append((open_s, close_e))
            skip_inline.append((open_s, close_e))
        else:
            skip_inline.append((open_s, body_s))
            skip_inline.append((body_e, close_e))
    for full_s, full_e, _, _ in _inline_code_spans(s, skip_inline):
        spans.append((full_s, full_e))
    spans.sort()
    return spans


def _strip_code_invisibles(code: str) -> Tuple[str, int]:
    if code.lstrip(" ").startswith(("```", "~~~")):
        nl = code.find("\n")
        last_nl = code.rfind("\n")
        if 0 <= nl < last_nl:
            head, body, tail, allow_bt = code[:nl + 1], code[nl + 1:last_nl], code[last_nl:], True
        else:
            head, body, tail, allow_bt = "", code, "", False
    elif code.startswith("`"):
        k = 0
        while k < len(code) and code[k] == "`":
            k += 1
        if len(code) >= 2 * k and code.endswith("`" * k):
            head, body, tail, allow_bt = code[:k], code[k:-k], code[-k:], k >= 2
        else:
            head, body, tail, allow_bt = "", code, "", False
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
                for _ in range(8):
                    chunk, n = CITATION_RX.subn("", chunk)
                    n_xml = 0
                    if "<" in chunk:
                        chunk, n_xml = CITE_XML_PAIR_RX.subn(r"\1", chunk)
                    step += n + n_xml
                    if not (n or n_xml):
                        break
                if "<" in chunk:
                    chunk, n_open = CITE_XML_OPEN_RX.subn("", chunk)
                    step += n_open
                if "://" in chunk or "w." in chunk or "W." in chunk:
                    before_url = chunk
                    chunk = re.sub(URL_RX, fix_url, chunk)
                    if chunk != before_url:
                        step += 1
                chunk, inv_n = _strip_invisibles(chunk, prev_ch, next_ch)
                if step or inv_n:
                    changed = True
                if not step and not inv_n:
                    break
            if re.search(r"[А-Яа-яЁё]", chunk):
                normed = unicodedata.normalize("NFC", PROSE_HOMO_RX.sub(fix_homo, chunk))
            else:
                normed = chunk if chunk.isascii() else unicodedata.normalize("NFC", chunk)
            out_chunk = normed if keep_stress else PROSE_STRESS_RX.sub(
                lambda m: "" if m.group(1) else m.group(0), normed
            )
            if out_chunk != parts[i]:
                changed = True
            parts[i] = out_chunk
        text = "".join(parts)
        if not changed or ("`" not in text and "~" not in text):
            break
    return text


def _pair_dot_decimals(mine: Facts, other: Facts) -> List[Dict]:
    def count(facts: Facts, value: str) -> int:
        return sum(1 for f in facts.items if f.kind == "number" and f.value == value)

    def stems(facts: Facts, f: Fact) -> set:
        names = {_norm(x.value.lower()) for x in facts.items if x.kind in ("name", "subject") and x.sent == f.sent}
        out = {_norm(w.lower())[:4] for w in re.findall(r"[а-яё]{4,}", facts.sentences[f.sent], re.I) if _norm(w.lower()) not in names}
        if f.hedge:
            out.add("#" + HEDGE_SAME.get(f.hedge, f.hedge))
        return out

    dots = {}
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
                sent, off = mine.sentences[f.sent], f.pos - mine.starts[f.sent]
                before_f = _norm(sent[:off].rstrip().lower())
                after_f = _norm(sent[off + len(f.raw):].lstrip().lower())
                time_prep = bool(re.search(r"(?<![а-яё])(?:в|к|до|после|с)$", before_f) and not re.match(r"раз(?:а|у|ом|е)?(?![а-яё])", after_f))
                st = stems(mine, f)
                return (time_prep, -(len(st & dec_stems) - len(st & time_stems)), not (k < len(other_order) and other_order[k]), idx)

            chosen = [idx for _, idx in sorted(enumerate(idxs), key=rank)[:n]]
        else:
            chosen = idxs
        for i in chosen:
            f = mine.items[i]
            mine.items[i] = replace(f, value=alt, unit="")
            checks.append({"kind": "unit", "what": "число", "detail": "%s и %s сверены как одно число: проверь, что это не время" % (f.raw, twin)})
    return checks


def _service_regions(before: str, after_norm: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    seps = list(SERVICE_SEP_RX.finditer(before))
    parts, prev = [], 0
    if seps:
        for m in seps:
            parts.append((prev, m.start()))
            prev = m.end()
        parts.append((prev, len(before)))
        head_rx = SERVICE_HEAD_RX
    else:
        for m in re.finditer(r"\r?\n[ \t]*\r?\n", before):
            parts.append((prev, m.start()))
            prev = m.end()
        parts.append((prev, len(before)))
        head_rx = SERVICE_HEAD_STRICT_RX
    spans, tails = [], []
    if len(parts) > 1:
        body = before[parts[0][0]:parts[0][1]].strip()
        if len(body) <= 300 and "\n" not in body and head_rx.match(body) and (SERVICE_SIZE_RX.search(body) or body.rstrip("*_ ").endswith(":")):
            spans.append(parts[0])
    i = len(parts) - 1
    while i >= 0:
        body = before[parts[i][0]:parts[i][1]].strip()
        if not SERVICE_TAIL_RX.match(body.split("\n", 1)[0]) or not SERVICE_ABOUT_RX.search(body) or (not seps and not SERVICE_FIRST_RX.search(body)):
            break
        spans.append(parts[i])
        tails.append(parts[i])
        i -= 1
    after_lf = after_norm.replace("\r\n", "\n")
    kept = []
    for a, b in spans:
        key = _norm(before[a:b].strip().replace("\r\n", "\n").lower())[:20]
        if key and key not in after_lf:
            kept.append((a, b))
    kept_tails = [sp for sp in tails if sp in kept]
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
                is_heading_note = (len(line) <= 160 and (line.startswith(("#", "**", "__")) or line.rstrip("*_ \t").endswith(":"))
                                   and part_str[pm.end():line_e].strip("*_ \t:\r") == "")
                if not (is_standalone or is_heading_note):
                    continue
                sa, sb = pa + pm.start(), pa + pm.end()
                if any(a <= sa and sb <= b for a, b in kept):
                    continue
                key = _norm(before[sa:sb].strip().replace("\r\n", "\n").lower())[:20]
                if key and key not in after_lf:
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


ITEM_HEDGE_PREPS = ITEM_VAL_PREPS | frozenset(("через", "к", "ко", "до", "с", "со"))
_ITEM_LEFT_CLEAN_RX = re.compile(
    r"^[ \t\u00a0\u202f]*(?:>[ \t\u00a0\u202f]*)*(?:#{1,6}[ \t\u00a0\u202f]+)?(?:[-•*+—–|][ \t\u00a0\u202f]*)*"
    r"(?:\*\*|__|\*|_)?(?:\d{1,2}[.)][ \t\u00a0\u202f]+)?")
_ITEM_TOK_RX = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:-[A-Za-zА-Яа-яЁё0-9]+)*")
_ITEM_SEP_RX = re.compile(r"[:—–(|]")
_ITEM_LIST_MARKER_RX = re.compile(r"^[ \t>*_]*(?:[-•*+—–|]|\d{1,2}[.)])")


def _extract_item_label(left: str, right: str, is_first_clause: bool) -> Optional[Tuple[Tuple[str, ...], str]]:
    r_check = right.split("|", 1)[0] if "|" in right else right
    rw = re.findall(r"[\w-]+", r_check)
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
    left_clean = _ITEM_LEFT_CLEAN_RX.sub("", left)
    toks = [(m.group(), _norm(m.group().lower()), m.start(), m.end())
            for m in _ITEM_TOK_RX.finditer(left_clean)
            if not m.group().isdigit()]
    if not toks:
        return None
    # Strip trailing hedge preposition (e.g. «минимум за», «не более чем через») when no sep follows.
    if len(toks) > 2 and toks[-1][1] in ITEM_HEDGE_PREPS and not _ITEM_SEP_RX.search(left_clean[toks[-1][3]:]):
        pre_toks = toks[:-1]
        if pre_toks[-1][1] == "чем" or any(
            len(pre_toks) > len(hp) and tuple(t[1] for t in pre_toks[-len(hp):]) == hp for hp in HEDGE_TOK_PARTS
        ):
            toks = pre_toks
    if len(toks) > 1 and toks[-1][1] == "чем":
        toks = toks[:-1]
    for hp in HEDGE_TOK_PARTS:
        if len(toks) > len(hp) and tuple(t[1] for t in toks[-len(hp):]) == hp:
            toks = toks[:-len(hp)]
            break
    last_raw, last_norm, last_s, last_e = toks[-1]
    has_sep = bool(_ITEM_SEP_RX.search(left_clean[last_e:]))
    is_quoted = last_s > 0 and left_clean[last_s - 1] in "«„“\"'`"
    after_cls = len(toks) >= 2 and any(toks[-2][1].startswith(c) for c in ITEM_CLASSIFIERS)
    if last_norm in ITEM_BAD_NUM_PREPS and not (has_sep or is_quoted or last_raw[0].isupper() or after_cls):
        return None
    if len(toks) > 1 and toks[-1][1] in ITEM_VAL_PREPS and not _ITEM_SEP_RX.search(left_clean[toks[-1][3]:]):
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
                both_markers = bool(_ITEM_LIST_MARKER_RX.match(facts.sentences[prev_idx]) and _ITEM_LIST_MARKER_RX.match(sent))
                if re.search(r"\r?\n[ \t]*\r?\n", gap_txt) and not both_markers:
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
    before_st = _strip_tracking(before, keep_stress=True)
    after_st = _strip_tracking(after, keep_stress=True)
    before = _strip_prose_stress(before_st)
    after = _strip_prose_stress(after_st)
    prose_before = _mask_code_fences(before)
    prose_after = _mask_code_fences(after)
    fb, fa = extract(before, stripped=True), extract(after, edited=True, stripped=True)
    errors: List[Dict] = []
    service: List[Dict] = []
    checks: List[Dict] = _pair_dot_decimals(fb, fa) + _pair_dot_decimals(fa, fb)

    # START_BLOCK_SERVICE
    service_spans, tail_spans = _service_regions(before, _norm(after.lower()))
    service_groups, service_items, svc_exact, svc_spelt = {}, {}, {}, {}

    def _svc_name_key(word: str) -> str:
        key = _norm(word.lower())
        hit = svc_exact.get(key)
        if hit is not None:
            return hit
        bks = _name_keys(key)
        for bk in bks:
            for k in svc_spelt.get(bk, ()):
                if _same_name_case_fleeting(k, key):
                    svc_exact[key] = k
                    return k
        svc_exact[key] = key
        for bk in bks:
            svc_spelt.setdefault(bk, []).append(key)
        return key

    def group_key(kind: str, f: Fact) -> str:
        return _svc_name_key(f.value) if kind == "name" else f.value

    for kind in ("number", "date", "month", "name", "quote"):
        by_value = {}
        for f in fb.of(kind):
            by_value.setdefault(group_key(kind, f), []).append(f)
        service_items[kind] = by_value

    def service_only(kind: str, items: List[Fact]) -> bool:
        allowed = tail_spans if kind in ("date", "month") else service_spans
        if not allowed or not items or kind not in ("number", "date", "month", "name", "quote"):
            return False
        for f in items:
            if (kind == "number" and f.unit) or (kind == "quote" and f.speech) or not any(a <= f.pos < b for a, b in allowed):
                return False
        return True

    def in_service(kind: str, f: Fact) -> bool:
        key = (kind, group_key(kind, f))
        got = service_groups.get(key)
        if got is None:
            got = service_groups[key] = service_only(kind, service_items[kind].get(key[1], []))
        return got

    if service_spans:
        eligible = [f for f in fb.items if (f.kind == "number" and not f.unit) or f.kind == "name" or (f.kind == "quote" and not f.speech)]
        held = sum(1 for f in eligible if any(a <= f.pos < b for a, b in service_spans))
        if sum(b - a for a, b in service_spans) > 0.4 * len(before) and held > 0.4 * len(fb.items):
            service_spans, tail_spans = [], []
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
            # Count every hedge class mention by mention, including singletons («после», «до», «от»).
            # A dropped number mention took its hedge along (suppressed when need - have <= gone and have > 0).
            was = Counter(f.hedge for f in items if f.hedge)
            now = Counter(f.hedge for f in ba[value] if f.hedge)
            gone = max(0, len(items) - len(ba[value]))
            lost = set()
            for cls in {hedge_class(h) for h in was}:
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
    # Reversed ordered ratio («3:4» → «4:3», «7:2» → «2:7»): numbers survive, order flipped.
    ratios_b = {f.value for f in fb.of("ratio")}
    ratios_a = {f.value for f in fa.of("ratio")}
    seen_r = set()
    for f in fb.of("ratio"):
        if f.value in seen_r:
            continue
        seen_r.add(f.value)
        a_r, b_r = f.value.split(":", 1)
        rev = "%s:%s" % (b_r, a_r)
        if f.value not in ratios_a and rev in ratios_a and rev not in ratios_b:
            errors.append({"kind": "lost", "what": "число", "detail": f.raw})
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
        by_key: Dict[str, List[str]] = {}
        for w in word_list:
            wn = _norm(w.lower())
            if wn not in exact_set:
                exact_set.add(wn)
                if len(wn) >= 2:
                    for bk in _name_keys(wn):
                        by_key.setdefault(bk, []).append(w)
        return exact_set, by_key

    def _has_name_match(val: str, fn: str, exact_set: set, by_key: Dict[str, List[str]]) -> bool:
        if fn in exact_set:
            return True
        for bk in _name_keys(fn):
            if any(name_match(val, w) for w in by_key.get(bk, ())):
                return True
        return False

    def _mark_seen_name(seen_exact: set, seen_by_key: Dict[str, List[str]], fn: str) -> bool:
        if fn in seen_exact:
            return True
        bks = _name_keys(fn)
        for bk in bks:
            for prev in seen_by_key.get(bk, ()):
                if _same_name_case_fleeting(prev, fn):
                    seen_exact.add(fn)
                    return True
        seen_exact.add(fn)
        for bk in bks:
            seen_by_key.setdefault(bk, []).append(fn)
        return False

    after_words = re.findall(r"[\w-]+", after)
    after_exact, after_by2 = _build_name_lookup(after_words)
    after_init_ngrams: Optional[set] = None
    seen_exact_n: set = set()
    seen_names: Dict[str, List[str]] = {}
    for f in fb.of("name"):
        fn = _norm(f.value.lower())
        if _mark_seen_name(seen_exact_n, seen_names, fn):
            continue
        if _has_name_match(f.value, fn, after_exact, after_by2):
            continue
        # An acronym spelled out is kept: «УК» → «управляющую компанию».
        if f.value.isupper() and 2 <= len(f.value) <= 4:
            if after_init_ngrams is None:
                init_chars = [w[0].lower() for w in after_words if w]
                after_init_ngrams = {"".join(init_chars[i:i + k]) for k in (2, 3, 4)
                                     for i in range(max(0, len(init_chars) - k + 1))}
            if f.value.lower() in after_init_ngrams:
                continue
        if in_service("name", f):
            service.append({"kind": "lost", "what": "имя или название", "detail": f.raw})
            continue
        errors.append({"kind": "lost", "what": "имя или название", "detail": f.raw})
    before_words = re.findall(r"[\w-]+", before)
    before_exact, before_by2 = _build_name_lookup(before_words)
    seen_exact_n = set()
    seen_names = {}
    for f in fa.of("name"):
        fn = _norm(f.value.lower())
        if _mark_seen_name(seen_exact_n, seen_names, fn):
            continue
        if not _has_name_match(f.value, fn, before_exact, before_by2):
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
    words = lambda s: re.findall(r"[\w\u0301-]+", s)
    _qkey = lambda w: _norm(w.replace("\u0301", "").lower())[:3]

    def _stress_pos(w: str) -> List[int]:
        out, seen_acutes = [], 0
        for idx_c, ch in enumerate(_norm(w.lower())):
            if ch == "\u0301":
                out.append(idx_c - seen_acutes)
                seen_acutes += 1
        return out

    def _same_qword(x: str, y: str, exact: bool = False) -> bool:
        if "\u0301" in x and "\u0301" in y and _stress_pos(x) != _stress_pos(y):
            return False
        xp, yp = x.replace("\u0301", ""), y.replace("\u0301", "")
        return (_norm(xp.lower()) == _norm(yp.lower())) if exact else stem_match(xp, yp)

    def _index_word_seq(seq: List[str]) -> Dict[str, List[int]]:
        idx_map = {}
        for pos_i, w_i in enumerate(seq):
            idx_map.setdefault(_qkey(w_i), []).append(pos_i)
        return idx_map

    def contains_indexed(seq: List[str], seq_idx: Dict[str, List[int]], needle: List[str], exact: bool = False) -> bool:
        n = len(needle)
        if not n or len(seq) < n:
            return False
        limit = len(seq) - n
        return any(i <= limit and all(_same_qword(seq[i + j], needle[j], exact) for j in range(n))
                   for i in seq_idx.get(_qkey(needle[0]), ()))

    both_stressed = "\u0301" in before_st and "\u0301" in after_st
    if both_stressed:
        def _mask_quote_st(s: str) -> str:
            p = _mask_code_fences(s)
            return _mask_spans(p, [(m.start(), m.end()) for m in HTML_ANY_TAG_RX.finditer(p)]) if "<" in p else p
        st_b_map = {}
        for m in QUOTE_RX.finditer(_mask_quote_st(before_st)):
            q_st = next(g for g in m.groups() if g).strip()
            st_b_map.setdefault(CYR_STRESS_RX.sub("", q_st).lower(), []).append(q_st)
        quotes_a = [words(next(g for g in m.groups() if g).strip()) for m in QUOTE_RX.finditer(_mask_quote_st(after_st))]
        after_q_words = words(after_st)
    else:
        st_b_map, quotes_a, after_q_words = {}, [words(f.raw) for f in fa.of("quote")], after_words
    quotes_a_exact = set() if both_stressed else {tuple(_norm(x.lower()) for x in q) for q in quotes_a}
    quotes_a_idx = {}
    for qi, q in enumerate(quotes_a):
        for pi, qw in enumerate(q):
            quotes_a_idx.setdefault(_qkey(qw), []).append((qi, pi))
    after_q_idx, before_q_idx = _index_word_seq(after_q_words), _index_word_seq(before_words)

    def in_quotes_a(needle: List[str], exact: bool) -> bool:
        n = len(needle)
        return any(pi <= len(quotes_a[qi]) - n and all(_same_qword(quotes_a[qi][pi + j], needle[j], exact) for j in range(n))
                   for qi, pi in quotes_a_idx.get(_qkey(needle[0]), ()))

    seen, st_b_idx = set(), {}
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
        skey = (key, f.speech)
        if not w or skey in seen:
            continue
        seen.add(skey)
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
    idx_a, idx_b = _TextIndex(after_norm), _TextIndex(before_norm)
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
    prose_before_norm = before_norm if prose_before == before else _norm(prose_before.lower())
    prose_after_norm = after_norm if prose_after == after else _norm(prose_after.lower())
    for label, rx in MODALITY:
        pat = r"(?<![а-яё])(?:%s)(?![а-яё])" % rx
        nb, na = len(re.findall(pat, prose_before_norm)), len(re.findall(pat, prose_after_norm))
        if nb > na:
            checks.append({"kind": "modality", "what": "уверенность и охват",
                           "detail": "«%s» встречается реже (%d → %d): не стало ли утверждение сильнее?" % (label, nb, na)})
        elif na > nb == 0:
            checks.append({"kind": "modality", "what": "уверенность и охват",
                           "detail": "появилось «%s», которого не было" % label})
    pat = r"(?<![а-яё])(?:%s)(?![а-яё])" % INTENSIFIERS
    nb, na = len(re.findall(pat, prose_before_norm)), len(re.findall(pat, prose_after_norm))
    if na > nb:
        checks.append({"kind": "modality", "what": "уверенность и охват",
                       "detail": "слов вроде «самый», «главный», «лучший» стало больше (%d → %d): не усилено ли утверждение?" % (nb, na)})
    # END_BLOCK_MODALITY_DIFF

    # START_BLOCK_MARKUP_DIFF
    # HTML in the original is part of the text: structural tags must survive the edit; lost
    # emphasis tags only need a look (decorative bold may be removed on purpose).
    # The name ends at a space, "/" or ">": autolinks <https://…> and <a@b.ru> are not tags.
    emphasis = {"b", "strong", "i", "em", "mark", "u"}
    tags_b = Counter(t.lower() for t in HTML_TAG_RX.findall(prose_before))
    if sum(tags_b.values()) >= 2:
        tags_a = Counter(t.lower() for t in HTML_TAG_RX.findall(prose_after))
        for tag in sorted(tags_b):
            nb, na = tags_b[tag], tags_a[tag]
            if na < nb:
                (checks if tag in emphasis else errors).append(
                    {"kind": "lost", "what": "разметка", "detail": "<%s> %d → %d" % (tag, nb, na)})
        for tag in sorted(set(tags_a) - set(tags_b)):
            checks.append({"kind": "added", "what": "разметка", "detail": "появился тег <%s>" % tag})
    # END_BLOCK_MARKUP_DIFF

    # START_BLOCK_BINDINGS
    pairs = {}
    _WS_MERGE_RX = re.compile(r"[ \t\u00a0]+")
    _TOK_RX = re.compile(r"[\w-]+")
    _GAP_DOT_RX = re.compile(r"[\s.]*")
    _GAP_WS_RX = re.compile(r"\s+")
    _COORD_VERB_RX = re.compile(r"\s*(?:[—–:]|[а-яё]+л[аио]?(?![а-яё]))")

    def _is_comparison_delta(facts: Facts, n: Fact) -> bool:
        if not facts.starts or n.sent >= len(facts.sentences):
            return False
        sent, rel = facts.sentences[n.sent], n.pos - facts.starts[n.sent]
        left = _norm(sent[max(0, rel - 80):rel])
        right = _norm(sent[rel + len(n.raw):rel + len(n.raw) + 64])
        return bool((COMP_DELTA_BEFORE_NA_RX.search(left) and COMP_DELTA_AFTER_RX.match(right))
                    or COMP_DELTA_BEFORE_REV_RX.search(left))

    def after_source(f: Fact) -> bool:
        if f.sent >= len(fb.starts):
            return False
        sent, end = fb.sentences[f.sent], f.pos - fb.starts[f.sent]
        gap = end
        while gap > 0 and sent[gap - 1].isspace():
            gap -= 1
        start = gap
        while start > 0 and (sent[start - 1].isalnum() or sent[start - 1] == "-"):
            start -= 1
        return gap < end and sent[start:gap].lower() in SOURCE_PREPOSITIONS

    def _after_comp_target_b(f: Fact) -> bool:
        if f.sent >= len(fb.starts):
            return False
        sent, rel = fb.sentences[f.sent], f.pos - fb.starts[f.sent]
        return bool(COMP_TARGET_LEFT_RX.search(_norm(sent[max(0, rel - 96):rel].lower())))

    people, spelt_exact, spelt = [], {}, {}

    def stem_key(word: str) -> str:
        key = _norm(word.lower())
        hit = spelt_exact.get(key)
        if hit is not None:
            return hit
        bks = _name_keys(key)
        for bk in bks:
            for k in spelt.get(bk, ()):
                if _same_name_case_fleeting(k, key):
                    spelt_exact[key] = k
                    return k
        spelt_exact[key] = key
        for bk in bks:
            spelt.setdefault(bk, []).append(key)
        return key

    number_at = {}

    def numbers_at(facts: Facts, sent: int) -> List[int]:
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
        s0, sent = fb.starts[f.sent], fb.sentences[f.sent]
        ca, cb = clause_span(sent, f.pos - s0)
        s_nums, prev_rel, end_rel = numbers_at(fb, f.sent), people[-1][3] - s0, f.pos + len(f.raw) - s0
        while end_rel < cb:
            nxt_cap = re.match(r"[\s.]+([A-ZА-ЯЁ][\w-]*)", sent[end_rel:cb])
            if not nxt_cap:
                break
            end_rel += nxt_cap.end()
        if any(ca <= p < prev_rel for p in s_nums) and any(end_rel <= p < cb for p in s_nums):
            return False
        return _COORD_VERB_RX.match(_norm(sent[end_rel:min(cb, end_rel + 32)])) is None

    for f in sorted(fb.of("name"), key=lambda x: x.pos):
        key = stem_key(f.value)
        if people and people[-1][0] == f.sent and people[-1][2] < f.pos and _WS_MERGE_RX.fullmatch(before[people[-1][2]:f.pos]):
            people[-1][1].add(key)
        else:
            people.append([f.sent, {key}, 0, f.pos, after_source(f) or _coord_sender_b(f) or _after_comp_target_b(f)])
        people[-1][2] = f.pos + len(f.raw)
    persons_map, key_to_pids, next_pid = {}, {}, 0
    for p in people:
        if len(p[1]) > 1:
            cands = set()
            for k in p[1]:
                cands.update(key_to_pids.get(k, ()))
            same_ids = [pid for pid in cands if persons_map[pid] <= p[1] or p[1] <= persons_map[pid]]
            merged = set(p[1])
            for pid in same_ids:
                g = persons_map.pop(pid)
                merged.update(g)
                for k in g:
                    key_to_pids[k].discard(pid)
            persons_map[next_pid] = merged
            for k in merged:
                key_to_pids.setdefault(k, set()).add(next_pid)
            next_pid += 1
    unclear = {k for k, pids in key_to_pids.items() if len(pids) > 1}
    for p in people:
        if len(p[1]) > 1:
            cand_ids = key_to_pids.get(next(iter(p[1])))
            have_ids = [pid for pid in cand_ids if p[1] <= persons_map[pid]] if cand_ids else []
        else:
            have_ids = list(key_to_pids.get(next(iter(p[1])), ()))
        p[1] = persons_map[have_ids[0]] - unclear if len(have_ids) == 1 else (set() if have_ids else set(p[1]))
    people = [p for p in people if p[1]]
    groups, seen_groups = [], set()
    for p in people:
        fg = frozenset(p[1])
        if fg not in seen_groups:
            seen_groups.add(fg)
            groups.append(p[1])

    people_by_sent, pstarts_by_sent, pnext_by_sent = {}, {}, {}
    for p in people:
        people_by_sent.setdefault(p[0], []).append(p)
        pstarts_by_sent.setdefault(p[0], []).append(p[3])
    for s_id, plist in people_by_sent.items():
        nxt_arr = [len(plist)] * len(plist)
        for k_p in range(len(plist) - 2, -1, -1):
            nxt_arr[k_p] = nxt_arr[k_p + 1] if (plist[k_p][1] == plist[k_p + 1][1] and plist[k_p][4] == plist[k_p + 1][4]) else k_p + 1
        pnext_by_sent[s_id] = nxt_arr

    def owners_in(sent: int, lo: int, hi: int, receivers_only: bool = False, limit: int = 0) -> List[set]:
        owners, plist = [], people_by_sent.get(sent)
        if not plist:
            return owners
        pstarts, pnext = pstarts_by_sent[sent], pnext_by_sent[sent]
        idx_p = bisect.bisect_left(pstarts, lo)
        while idx_p < len(plist) and pstarts[idx_p] < hi:
            p = plist[idx_p]
            if not (receivers_only and p[4]) and p[1] not in owners:
                owners.append(p[1])
                if limit and len(owners) >= limit:
                    break
            idx_p = pnext[idx_p]
        return owners

    sent_owners_b, clauses_b, cspans_b_cache = {}, {}, {}
    if people_by_sent:
        for n in fb.of("number"):
            if n.sent not in sent_owners_b:
                sent_owners_b[n.sent] = owners_in(n.sent, 0, 1 << 62, False, 2)
            owners = sent_owners_b[n.sent]
            if not owners or _is_comparison_delta(fb, n):
                continue
            owners = list(owners)
            if len(owners) > 1 and fb.starts:
                s0 = fb.starts[n.sent]
                if n.sent not in clauses_b:
                    who_b = lambda a, b: owners_in(n.sent, s0 + a, s0 + b, True, 2)
                    spans_b = list_clauses(fb.sentences[n.sent], numbers_at(fb, n.sent), who_b)
                    clauses_b[n.sent] = spans_b if is_list(fb.sentences[n.sent], numbers_at(fb, n.sent), who_b, spans_b) else None
                if clauses_b[n.sent]:
                    a, b = clause_span(fb.sentences[n.sent], n.pos - s0, clauses_b[n.sent])
                    owners = owners_in(n.sent, s0 + a, s0 + b, True, 2)
                else:
                    receivers = owners_in(n.sent, 0, 1 << 62, True, 2)
                    if len(receivers) == 1:
                        owners = receivers
            elif len(owners) == 1 and fb.starts:
                s0, sent_b = fb.starts[n.sent], fb.sentences[n.sent]
                cached_cs = cspans_b_cache.get(n.sent)
                if cached_cs is None:
                    cspans, other_ok = clause_spans(sent_b), False
                    if len(cspans) > 1:
                        s_nums = sorted(numbers_at(fb, n.sent))
                        other_with_owner = [(oa, ob) for oa, ob in cspans if owners_in(n.sent, s0 + oa, s0 + ob, False, 1)]
                        other_ok = bool(other_with_owner) and all(
                            (bisect.bisect_left(s_nums, ob) > bisect.bisect_left(s_nums, oa))
                            or re.match(r"^(?:а|но|однако|зато|тогда\s+как|при\s+этом)(?![а-яё])", _norm(sent_b[oa:ob].lstrip().lower()))
                            or (oa >= 2 and sent_b[oa - 2] == ";")
                            for oa, ob in other_with_owner)
                    cached_cs = cspans_b_cache[n.sent] = (cspans, other_ok)
                cspans, other_ok = cached_cs
                if len(cspans) > 1 and other_ok:
                    ca, cb = clause_span(sent_b, n.pos - s0, cspans)
                    if not owners_in(n.sent, s0 + ca, s0 + cb, False, 1):
                        owners = []
            if len(owners) == 1:
                pairs.setdefault(n.value, set()).update(owners[0])
    all_owners = set().union(*pairs.values()) if pairs else set()
    owners_by2, unclear_by2, key_to_gidxs = {}, {}, {}
    for o in all_owners:
        for bk in _name_keys(o):
            owners_by2.setdefault(bk, []).append(o)
    for k in unclear:
        for bk in _name_keys(k):
            unclear_by2.setdefault(bk, []).append(k)
    for gidx, g in enumerate(groups):
        for k in g:
            key_to_gidxs.setdefault(k, []).append(gidx)
    someone = "?"

    def _match_owner_set(word: str, by2: Dict[str, List[str]]) -> set:
        if not by2:
            return set()
        return {cand for bk in _name_keys(_norm(word.lower())) for cand in by2.get(bk, ()) if _same_name_case_fleeting(cand, word)}

    def _scan_sent_tokens(sent: str):
        found = [(m.start(), m.end(), m.group()) for m in _TOK_RX.finditer(sent)]
        n_tok = len(found)
        if not n_tok or (not owners_by2 and not unclear_by2):
            return [], [], []
        sent_low = _norm(sent.lower())
        src_starts, comp_flags = [-1] * n_tok, [False] * n_tok
        sender, sender_src, prev_sender, prev_src, ct = False, -1, False, -1, False
        for i, (s_i, e_i, tok_i) in enumerate(found):
            gap_prev = sent[found[i - 1][1]:s_i] if i > 0 else ""
            is_up = tok_i[:1].isupper()
            ct = bool(is_up and (COMP_TARGET_LEFT_RX.search(sent_low[max(0, s_i - 96):s_i]) or (ct and _GAP_DOT_RX.fullmatch(gap_prev))))
            comp_flags[i] = ct
            if i > 0 and found[i - 1][2].lower() in SOURCE_PREPOSITIONS and is_up:
                sender, sender_src = True, found[i - 1][0]
            elif sender and is_up and _GAP_DOT_RX.fullmatch(gap_prev):
                sender = True
            elif (prev_sender and i >= 2 and found[i - 1][2].lower() == "и" and is_up
                  and _GAP_WS_RX.fullmatch(sent[found[i - 2][1]:found[i - 1][0]]) and _GAP_WS_RX.fullmatch(gap_prev)):
                k_end, j_k = e_i, i + 1
                while j_k < n_tok and found[j_k][2][:1].isupper() and _GAP_DOT_RX.fullmatch(sent[k_end:found[j_k][0]]):
                    k_end = found[j_k][1]
                    j_k += 1
                sender = _COORD_VERB_RX.match(sent_low[k_end:k_end + 32]) is None
                sender_src = prev_src if sender else -1
            else:
                sender, sender_src = False, -1
            if sender:
                src_starts[i], prev_sender, prev_src = sender_src, True, sender_src
            elif prev_sender and tok_i.lower() == "и" and i > 0 and _GAP_WS_RX.fullmatch(gap_prev):
                prev_sender = True
            else:
                prev_sender, prev_src = False, -1
        hits = [_match_owner_set(tok_i, owners_by2) for _, _, tok_i in found]
        uncs = [bool(not hits[i] and unclear_by2 and _match_owner_set(found[i][2], unclear_by2)) for i in range(n_tok)]
        active, active_starts = [], []
        for i in range(n_tok):
            if not hits[i] and not uncs[i]:
                continue
            s_i, e_i, _ = found[i]
            gidxs = tuple(sorted({gidx for o in hits[i] for gidx in key_to_gidxs.get(o, ())}))
            sup_all, sup_recv = [], []
            if uncs[i]:
                for step in (-1, 1):
                    j = i + step
                    while 0 <= j < n_tok and comp_flags[j]:
                        j += step
                    if 0 <= j < n_tok and hits[j] and _GAP_DOT_RX.fullmatch(sent[e_i:found[j][0]] if j > i else sent[found[j][1]:s_i]):
                        sup_all.append((found[j][0], found[j][1]))
                    j = i + step
                    while 0 <= j < n_tok and (comp_flags[j] or src_starts[j] >= 0):
                        j += step
                    if 0 <= j < n_tok and hits[j] and _GAP_DOT_RX.fullmatch(sent[e_i:found[j][0]] if j > i else sent[found[j][1]:s_i]):
                        sup_recv.append((found[j][0], found[j][1]))
            active.append((s_i, e_i, hits[i], uncs[i], src_starts[i], comp_flags[i], gidxs, sup_all, sup_recv))
            active_starts.append(s_i)
        m_act = len(active)
        next_diff = [m_act] * m_act
        for k_a in range(m_act - 2, -1, -1):
            cur, nxt = active[k_a], active[k_a + 1]
            next_diff[k_a] = next_diff[k_a + 1] if (cur[4] < 0 and not cur[5] and nxt[4] < 0 and not nxt[5] and cur[6] == nxt[6]) else k_a + 1
        return active, active_starts, next_diff

    def _query_named(scan, a: int, b: int, receivers_only: bool = False) -> set:
        active, active_starts, _ = scan
        if not active:
            return set()
        owners, idx_a = set(), bisect.bisect_left(active_starts, a)
        while idx_a < len(active) and active[idx_a][0] < b:
            s_i, e_i, hit_i, is_unc, src_s, comp_f, _, sup_all, sup_recv = active[idx_a]
            idx_a += 1
            if e_i > b or comp_f or (receivers_only and src_s >= a):
                continue
            if hit_i:
                owners.update(hit_i)
            elif is_unc and not any(a <= ja and jb <= b for ja, jb in (sup_recv if receivers_only else sup_all)):
                owners.add(someone)
        return owners

    def _query_who(scan, a: int, b: int) -> List[set]:
        active, active_starts, next_diff = scan
        if not active:
            return []
        found_g, idx_a = [], bisect.bisect_left(active_starts, a)
        while idx_a < len(active) and active[idx_a][0] < b:
            s_i, e_i, _, _, src_s, comp_f, gidxs, _, _ = active[idx_a]
            if e_i <= b and not comp_f and not (src_s >= a) and gidxs:
                for gidx in gidxs:
                    if gidx not in found_g:
                        found_g.append(gidx)
                        if len(found_g) >= 2:
                            return [groups[found_g[0]], groups[found_g[1]]]
            idx_a = next_diff[idx_a] if (src_s < 0 and not comp_f) else idx_a + 1
        return [groups[gidx] for gidx in found_g]

    seen_near = {}

    def near(facts, n) -> set:
        key = (id(facts), n.sent)
        if key not in seen_near:
            sent = facts.sentences[n.sent] if n.sent < len(facts.sentences) else ""
            scan = _scan_sent_tokens(sent)
            here, clauses = _query_named(scan, 0, len(sent), False), None
            if facts.starts and len({gidx for o in here for gidx in key_to_gidxs.get(o, ())}) > 1:
                who_s = lambda a, b: _query_who(scan, a, b)
                spans = list_clauses(sent, numbers_at(facts, n.sent), who_s)
                if is_list(sent, numbers_at(facts, n.sent), who_s, spans):
                    clauses = ([a for a, _ in spans], [(a, b, _query_named(scan, a, b, True)) for a, b in spans])
            seen_near[key] = (here, clauses)
        here, clauses = seen_near[key]
        if clauses:
            offset = n.pos - facts.starts[n.sent]
            c_starts, c_list = clauses
            ci = bisect.bisect_right(c_starts, offset) - 1
            if ci >= 0 and c_list[ci][0] <= offset < c_list[ci][1]:
                return c_list[ci][2] or here
        return here

    swapped_after_pos = set()
    if len(all_owners) >= 2:
        near_b = {}
        for n in fb.of("number"):
            near_b.setdefault(n.value, set()).update(near(fb, n))
        for nb in near_b.values():
            extra = {gk for k in nb for gidx in key_to_gidxs.get(k, ()) for gk in groups[gidx]}
            nb.update(extra)
        for n in fa.of("number"):
            want = pairs.get(n.value)
            if not want or _is_comparison_delta(fa, n):
                continue
            here = near(fa, n)
            if someone in here:
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


def _read(path: str, encoding: str = "utf-8-sig") -> str:
    if path == "-":
        # Bytes, not sys.stdin: on Windows it decodes with the console code page (cp1251), and two
        # identical UTF-8 texts with the source piped in gave four false errors (found 2026-11-09).
        buf = getattr(sys.stdin, "buffer", None)
        if buf is not None:
            return buf.read().decode(encoding)
        return sys.stdin.read()
    with open(path, encoding=encoding) as fh:
        return fh.read()


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    encoding = "utf-8-sig"
    pos: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a in ("-h", "--help"):
            print(__doc__)
            return 0
        if a == "--json":
            as_json = True
        elif a == "--encoding":
            if i + 1 >= len(args):
                print("Не указана кодировка после --encoding.", file=sys.stderr)
                return 2
            i += 1
            encoding = args[i]
        elif a.startswith("--encoding="):
            encoding = a.split("=", 1)[1]
            if not encoding:
                print("Не указана кодировка после --encoding=.", file=sys.stderr)
                return 2
        elif a.startswith("-") and a != "-":
            print("Неизвестный параметр: %s" % a, file=sys.stderr)
            return 2
        else:
            pos.append(a)
        i += 1
    if len(pos) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    if pos[0] == "-" and pos[1] == "-":
        print("Нельзя передать «-» (stdin) сразу для обоих файлов.", file=sys.stderr)
        return 2
    try:
        before, after = _read(pos[0], encoding), _read(pos[1], encoding)
    except LookupError as exc:
        print("Неизвестная кодировка: %s" % exc, file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print("Не могу декодировать файл в %s (попробуй --encoding cp1251): %s" % (encoding, exc), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("Не могу прочитать файл: %s" % exc, file=sys.stderr)
        return 2
    result = compare(before, after)
    if as_json:
        payload = dict(result)
        payload["receipt"] = receipt(result)
        payload["receipt_hint"] = receipt_hint(result)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(result) + "\n\n" + receipt_hint(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
