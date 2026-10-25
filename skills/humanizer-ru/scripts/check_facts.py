#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Compare an original Russian text with its edited version and report facts that
#          were lost, invented or rebound: numbers (with units, versions like 2.1.3), dates
#          (days, months without a day, weekdays), times, names (incl. США-type acronyms),
#          URLs (host case and a trailing slash ignored), phones (by digits), e-mails, quotes,
#          `inline code`, negations (incl. "не на карту", "нельзя" → "можно"), hedges and
#          "who got which number" pairs; flags certainty, scope,
#          condition and attribution words that got rarer and intensifiers that got more frequent;
#          HTML tags of the original that were lost (emphasis tags only as checks).
#          Quoted words must survive in order (case endings and quote marks may change): lost
#          direct speech or a quote after a colon is an error; other lost quoted words, words
#          kept without their quote marks and new quotes are checks. Checks also: a lost
#          contrast negation ("а не в феврале"), an added negation, a number that lost its
#          unit, a code-like ``` block that changed.
#          Links are compared without the chat assistant's utm_source tail only: a lost
#          author utm tag is a lost link.
# SCOPE: heuristic, offline, stdlib only. Errors are likely real; "check" items need a human look.
#        An empty report does not prove the meaning is intact.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CHECK-FACTS; DF-SKILL-CHECK; V-M-CHECK-FACTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# extract: text -> Facts (numbers with units, dates, urls, names, quotes, negations, hedges, sentences).
# compare: (before, after) -> {"errors": [...], "checks": [...]}; markup block counts HTML tags;
#          quotes block matches quoted words in order.
# render: human-readable Russian report.
# main: CLI `check_facts.py before.txt after.txt [--json]`; exit 0 clean, 1 errors, 2 bad input.
# END_MODULE_MAP
"""Сверка фактов до и после правки.

    python check_facts.py до.txt после.txt          # отчёт по-русски
    python check_facts.py до.txt после.txt --json   # то же в JSON
    python check_facts.py - после.txt               # исходник из stdin

Код выхода: 0 — ошибок нет, 1 — есть ошибки, 2 — файл не читается.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# START_BLOCK_LEXICON
SEP = " \u00a0\u202f"
UNIT_SYNONYMS = [
    (("%", "процент", "процента", "процентов", "процентам", "процентами"), "%"),
    (("₽", "р.", "руб.", "руб", "рубль", "рубля", "рублей", "рублю", "рублями", "рублях"), "₽"),
    (("$", "доллар", "доллара", "долларов"), "$"),
    (("€", "евро"), "€"),
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
    (("день", "дня", "дней", "дн"), "дн"),
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

WORD_NUM = {
    # "один/одна/одного" are left out on purpose: "одна из причин" is not a number.
    "ноль": 0, "два": 2, "две": 2, "двух": 2, "трое": 3, "двое": 2, "три": 3, "трех": 3,
    "четыре": 4, "четырех": 4, "четверо": 4, "пять": 5, "пяти": 5, "пятеро": 5, "шесть": 6,
    "шести": 6, "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
    "десять": 10, "десяти": 10, "одиннадцать": 11, "двенадцать": 12, "пятнадцать": 15,
    "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "сто": 100, "двести": 200, "триста": 300,
    "полтора": 1.5, "полторы": 1.5, "половина": 0.5, "половину": 0.5,
    "одиннадцати": 11, "двенадцати": 12, "тринадцать": 13, "тринадцати": 13, "четырнадцать": 14,
    "четырнадцати": 14, "пятнадцати": 15, "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17,
    "семнадцати": 17, "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19,
    "девятнадцати": 19, "сорока": 40, "пятидесяти": 50, "шестидесяти": 60, "семьдесят": 70,
    "семидесяти": 70, "восемьдесят": 80, "восьмидесяти": 80, "девяносто": 90, "девяноста": 90,
    "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800,
    "девятьсот": 900,
}
# "один" counts only inside a compound number: "двадцать один", "сто одну".
ONE_FORMS = ("один", "одна", "одно", "одну", "одного", "одной", "одному", "одним", "одном")
SCALE = {"тыс": 1000, "тыс.": 1000, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
         "млн": 10 ** 6, "млн.": 10 ** 6, "миллион": 10 ** 6, "миллиона": 10 ** 6,
         "миллионов": 10 ** 6, "млрд": 10 ** 9, "миллиард": 10 ** 9, "миллиарда": 10 ** 9,
         "миллиардов": 10 ** 9}
# Longest first: "тыс." before "тыс", or the dot stops the unit after it ("30 тыс. человек").
SCALE_ALT = "|".join(re.escape(k) for k in sorted(SCALE, key=len, reverse=True))
# Months in any case, for dates without a day ("в марте 2026", "к апрелю").
MONTH_ANY_RX = re.compile(r"(?<![а-яё])(январ|феврал|март|апрел|ма(?=[йяюе](?![а-яё]))|июн|июл|август|сентябр|"
                          r"октябр|ноябр|декабр)[а-яё]*", re.I)
MONTH_ANY_NUM = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
                 "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
MONTHS = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|"
          "январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре|"
          "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь")
MONTH_STEM = {m[:3]: i for i, m in enumerate(
    "янв фев мар апр мая июн июл авг сен окт ноя дек".split(), 1)}
MONTH_STEM["май"] = 5
# Links with a scheme or www.; zero-width characters end a link (a paste can glue them on).
URL_RX = r"(?:https?://|www\.)[^\s<>«»\"')\]`%s]+" % "".join(map(chr, (0x200B, 0x2060, 0xFEFF)))
# Sentence punctuation and Markdown emphasis after a link are not part of it: **https://a.ru**
URL_TAIL = ".,;:!?…*_"


def _url_key(url: str) -> str:
    """Scheme and host are case-insensitive, the path is not; a trailing slash is the same page."""
    if not re.search(r"[?#]", url):
        url = url.rstrip("/")
    m = re.match(r"((?:https?://)?[^/?#]*)(.*)", url, re.S | re.I)
    return m.group(1).lower() + m.group(2)

# Days of the week. "Среда" alone is also "environment" ("рабочая среда", "окружающей среды"),
# so only "в среду", "по средам" and a schedule line "Среда: …" / "Среда, 5 ноября" count.
WEEKDAY_RX = re.compile(r"(?<![а-яё])(понедельник|вторник|четверг|пятниц|суббот|воскресень|"
                        r"сред(?=у|ам)|сред(?=а[ \t]*[,:]))[а-яё]*", re.I)
WEEKDAY_NUM = {"понедельник": 1, "вторник": 2, "сред": 3, "четверг": 4, "пятниц": 5, "суббот": 6,
               "воскресень": 7}
HEDGES = ("около", "примерно", "приблизительно", "почти", "порядка", "до", "не более",
          "не менее", "более", "свыше", "менее", "больше", "меньше", "минимум", "максимум",
          "от", "не больше", "не меньше", "не позже", "не позднее", "не раньше", "после",
          "только", "лишь", "кроме", "без")
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
# END_BLOCK_LEXICON


def _norm(s: str) -> str:
    return s.replace("ё", "е").replace("Ё", "Е")


CASE_ENDINGS = frozenset(("", "а", "я", "о", "е", "и", "ы", "у", "ю", "ой", "ей", "ою", "ею", "ом", "ем",
                          "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ий", "ия", "ие", "ья", "ье",
                          "ью", "ая", "ое", "ые", "ый", "ого", "его", "ому", "ему", "ым", "им", "ую", "ых",
                          "их", "ыми", "ими"))


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

    def of(self, kind: str) -> List[Fact]:
        return [f for f in self.items if f.kind == kind]


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


def _fmt(v: float) -> str:
    # 12 significant digits: "%g" kept 6 and made 100000,01 equal to 100000,02.
    return str(int(v)) if v == int(v) else ("%.12g" % v)


# START_CONTRACT: extract
# PURPOSE: Pull checkable facts out of one text.
# INPUTS: text (str).
# OUTPUTS: Facts with numbers (value, unit, hedge), dates, times, urls, emails, names,
#          quotes, negations; plus the sentence list used for bindings.
# SIDE_EFFECTS: none.
# END_CONTRACT: extract
def extract(text: str) -> Facts:
    text = _strip_tracking(text)
    facts = Facts()
    sents = split_sentences(text)
    facts.sentences = [t for _, t in sents]
    taken: List[Tuple[int, int]] = []

    def sent_of(pos: int) -> int:
        idx = 0
        for i, (s, _) in enumerate(sents):
            if s <= pos:
                idx = i
        return idx

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    def hedge_before(pos: int) -> str:
        left = _norm(text[max(0, pos - 24):pos].lower())
        for h in sorted(HEDGES, key=len, reverse=True):
            if re.search(r"(?:^|[^а-яa-z])%s[ \u00a0\u202f]*$" % re.escape(_norm(h)), left):
                return h
        return ""

    # START_BLOCK_URLS
    for m in re.finditer(URL_RX, text):
        url = m.group().rstrip(URL_TAIL)
        facts.items.append(Fact("url", _url_key(url), url, sent_of(m.start()), m.start()))
        taken.append((m.start(), m.start() + len(url)))
    for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        if free(m.start(), m.end()):
            facts.items.append(Fact("email", m.group().lower(), m.group(), sent_of(m.start()), m.start()))
            taken.append((m.start(), m.end()))
    # Phones are compared by digits: +7 (999) 123-45-67 = 8 999 123 45 67.
    phone_rx = (r"(?<![\w+])(?:\+\d{1,3}[ \xa0-]?|8[ \xa0-]?)\(?\d{3,5}\)?[ \xa0-]?"
                r"\d{1,3}[ \xa0-]?\d{2}[ \xa0-]?\d{2}(?![\w-])")
    for m in re.finditer(phone_rx, text):
        digits = re.sub(r"\D", "", m.group())
        if free(m.start(), m.end()) and 10 <= len(digits) <= 15:
            if len(digits) == 11 and digits[0] == "8":
                digits = "7" + digits[1:]
            facts.items.append(Fact("phone", digits, m.group(), sent_of(m.start()), m.start()))
            taken.append((m.start(), m.end()))
    # END_BLOCK_URLS

    # START_BLOCK_DATES_TIMES
    # Day and month stand on one line: "Вариант 3\n\nНоябрь — ..." is not the 3rd of November.
    date_rx = re.compile(r"\b(\d{1,2})(?:[ \t ]*(?:[–—-]|,|и|по|до)[ \t ]*(\d{1,2}))?[ \t ]+(%s)(?:[ \t ]+(\d{4}))?" % MONTHS, re.I)
    for m in date_rx.finditer(text):
        month = MONTH_STEM.get(m.group(3).lower()[:3], 0)
        for day in filter(None, (m.group(1), m.group(2))):
            facts.items.append(Fact("date", "%02d.%02d" % (int(day), month), m.group(),
                                    sent_of(m.start()), m.start(), hedge_before(m.start())))
        if m.group(4):
            facts.items.append(Fact("number", m.group(4), m.group(4), sent_of(m.start()), m.start()))
        taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", text):
        if free(m.start(), m.end()):
            facts.items.append(Fact("date", "%02d.%02d" % (int(m.group(1)), int(m.group(2))),
                                    m.group(), sent_of(m.start()), m.start()))
            # The year is kept as a number, the same way as in "1 февраля 2026".
            year = m.group(3) if len(m.group(3)) == 4 else "20" + m.group(3)
            facts.items.append(Fact("number", year, m.group(3), sent_of(m.start()), m.start()))
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,]\d)", text):
        # "1.50 ₽" is a price, not ten to two: a dot time is never followed by a unit.
        if text[m.end(1)] == "." and UNIT_RX.match(text, m.end()):
            continue
        if free(m.start(), m.end()):
            hh, mm = int(m.group(1)), m.group(2)
            value = str(hh) if mm == "00" else "%d:%s" % (hh, mm)
            facts.items.append(Fact("number", value, m.group(), sent_of(m.start()), m.start(),
                                    hedge_before(m.start()), "время"))
            taken.append((m.start(), m.end()))
    for m in WEEKDAY_RX.finditer(text):
        day = WEEKDAY_NUM[_norm(m.group(1).lower())]
        facts.items.append(Fact("date", "день недели %d" % day, m.group(), sent_of(m.start()), m.start()))
    # A month without a day ("в марте 2026") is a date fact of its own; see MONTHS_DIFF.
    for m in MONTH_ANY_RX.finditer(text):
        if free(m.start(), m.end()):
            month = MONTH_ANY_NUM[m.group(1).lower()]
            facts.items.append(Fact("month", str(month), m.group(), sent_of(m.start()), m.start()))
    # END_BLOCK_DATES_TIMES

    # START_BLOCK_NUMBERS
    # Counters in headings ("Вариант 1", "Шаг 2") are structure, not facts.
    for m in re.finditer(r"(?i)(?:вариант|шаг|этап|пункт|раздел|часть|глава)\s+(\d+)", text):
        taken.append((m.start(1), m.end(1)))
    # Versions, IP addresses, clause numbers (2.1.3, 192.168.0.1, п. 3.2.1) are one token
    # compared as written: read as numbers, 2.1.3 and 2.1.4 both gave 2.1.
    for m in re.finditer(r"(?<![\w.])\d+(?:\.\d+){2,}(?![\w]|\.\d)", text):
        if free(m.start(), m.end()):
            facts.items.append(Fact("number", m.group(), m.group(), sent_of(m.start()), m.start()))
            taken.append((m.start(), m.end()))
    num_rx = re.compile(r"(?<![\w.,])[+\-−]?\d+(?:[%s]\d{3})*(?:[.,]\d+)?(?![\w])" % SEP)
    for m in num_rx.finditer(text):
        if not free(m.start(), m.end()):
            continue
        v = _canon_num(m.group())
        if v is None:
            continue
        end = m.end()
        sc = re.match(r"[ \u00a0\u202f]+(%s)(?![а-я])" % SCALE_ALT, text[end:end + 12], re.I)
        if sc:
            v *= SCALE[sc.group(1).lower()]
            end += sc.end()
        unit = ""
        um = UNIT_RX.match(text, end)
        if um:
            unit = UNIT_CANON.get(um.group(1).lower(), "")
            end = um.end()
        if unit == "г" and not sc and v == int(v) and 1800 <= v <= 2100:
            unit = "год"  # "2020 г." is a year, not grams
        facts.items.append(Fact("number", _fmt(v), text[m.start():end], sent_of(m.start()),
                                m.start(), hedge_before(m.start()), unit))
        taken.append((m.start(), end))
    word_rx = re.compile(r"(?<![а-яё])(%s)(?![а-яё])" % "|".join(
        sorted(WORD_NUM, key=len, reverse=True)), re.I)
    norm_text = _norm(text)
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
            unit = UNIT_CANON.get(um.group(1).lower(), "")
            end = um.end()
        facts.items.append(Fact("number", _fmt(v), text[m.start():end], sent_of(m.start()),
                                m.start(), hedge_before(m.start()), unit))
        taken.append((m.start(), end))
    # END_BLOCK_NUMBERS

    # START_BLOCK_NAMES_QUOTES
    # «…», „…“, “…” and straight "…"; a straight mark after a digit or letter is inches (27").
    quote_rx = r"«([^»\n]{1,80})»|„([^“”\n]{1,80})[“”]|“([^”\n]{1,80})”|(?<!\w)\"(?!\s)([^\"\n]{1,80})(?<!\s)\""
    for m in re.finditer(quote_rx, text):
        q = next(g for g in m.groups() if g).strip()
        # Somebody's words: ответил: «…»; «…», — сказал; «…?» — спросил (before the author's
        # dash the speech ends with a comma or with ?!… inside the marks; «…» — чем is not speech).
        # Quoted words inside a phrase are often terms, irony or examples a rewrite may rephrase.
        dash = re.match(r"[*_]*(,?)[ \t]+[—–-][ \t]", text[m.end():m.end() + 8])
        speech = bool(text[max(0, m.start() - 8):m.start()].rstrip(" \t*_").endswith(":") or
                      dash and (dash.group(1) or q.endswith(("?", "!", "…"))))
        facts.items.append(Fact("quote", q.lower(), q, sent_of(m.start()), m.start(), speech=speech))
    for s_start, sent in sents:
        # Latin acronyms of any length; Cyrillic ones up to 4 letters (США, РФ, МЧС), longer
        # all-caps words are usually shouting ("ВНИМАНИЕ").
        for m in re.finditer(r"(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*|[А-ЯЁ]{2,4}(?![\w-]))", sent):
            word = m.group(1)
            first = _is_initial(text, s_start + m.start())
            if word in SENT_START_STOP or POLITE_PRONOUN.fullmatch(word):
                continue
            pos = s_start + m.start()
            if first and not (_capitalized_elsewhere(word, text, pos) or
                              any(len(word) <= len(n) + 3 and stem_match(word, n) for n in FIRST_NAMES)):
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
    for m in re.finditer(neg_rx, low):
        if m.group(1):
            # A contrast ("а не в феврале", "не с кофе, а с сигареты") is the "не X, а Y" pattern a
            # rewrite removes on purpose: "хотя раньше планировали в феврале" keeps the meaning.
            s_end = min([i for i in (low.find(c, m.end()) for c in ".!?\n") if i != -1] or [len(low)])
            contrast = bool(re.search(r"(?:^|[^а-яё])а\s+$", low[max(0, m.start() - 4):m.start()]) or
                            re.search(r",\s*а\s", low[m.end():s_end]))
            facts.items.append(Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(),
                                    hedge=m.group(1), unit="contrast" if contrast else ""))
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
    masked = text
    for m in re.finditer(r"^```[^\n]*\n(.*?)^```[ \t]*$", text, re.S | re.M):
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", m.group(1))
        cyr = sum(1 for x in letters if x > "z")
        if _code(m.group(1)) and cyr < 0.3 * max(1, len(letters)):
            facts.items.append(Fact("code_block", _code(m.group(1)), m.group(1).strip(),
                                    sent_of(m.start()), m.start()))
        masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    for m in re.finditer(r"`([^`\n]+)`", masked):
        if _code(m.group(1)):
            facts.items.append(Fact("code", _code(m.group(1)), m.group(1), sent_of(m.start()), m.start()))
    # END_BLOCK_CODE
    return facts


def _occurrences(text: str, word: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"[а-яё]{3,}", text) if stem_match(m.group(), word, strict=True)]


def _negated_near(text: str, start: int, end: int) -> bool:
    """A negation within 3 words before or 4 words after, inside the same sentence."""
    s_from = max(text.rfind(c, 0, start) for c in ".!?\n") + 1
    stops = [i for i in (text.find(c, end) for c in ".!?\n") if i != -1]
    s_to = min(stops) if stops else len(text)
    left = text[s_from:start].split()[-3:]
    right = text[end:s_to].split()[:4]
    return any(re.sub(r"[^а-яё]", "", w) in NEG_WORDS for w in left + right)


def _is_initial(text: str, pos: int) -> bool:
    """True when only markup, list markers, emoji or spaces stand between the word and the
    start of a line or the end of the previous sentence."""
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch == "\n" or ch in ".!?…:":
            return True
        if ch.isalnum() and not (ch.isdigit() and re.match(r"\d+[.)]", text[i:pos].lstrip())):
            return False
        if ch.isalpha():
            return False
        i -= 1
    return True


def _capitalized_elsewhere(word: str, text: str, pos: int) -> bool:
    for m in re.finditer(r"(?<![\w-])" + re.escape(word[:max(3, len(word) - 2)]), text):
        if m.start() == pos:
            continue
        if text[m.start()].isupper() and not _is_initial(text, m.start()):
            return True
    return False


# utm_source values chat assistants add to the links they cite (ru.wikipedia,
# «Признаки сгенерированности текста», UTM-метки, revision of 2026-10-08). Any other utm
# tag is the author's own (newsletter, campaign) and belongs to the link.
ASSISTANT_UTM_SOURCES = frozenset({"chatgpt.com", "openai"})


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


def _strip_tracking(text: str) -> str:
    def fix(m: "re.Match") -> str:
        url = m.group(0)
        tail = url[len(url.rstrip(URL_TAIL)):]
        return strip_utm(url[:len(url) - len(tail)])[0] + tail
    text = re.sub(URL_RX, fix, text)
    return re.sub(r":contentReference\[oaicite:\d+\]\{index=\d+\}|【\d+(?::\d+)?†[^】]*】", "", text)



# START_CONTRACT: compare
# PURPOSE: Find lost, invented, re-bound or inverted facts between two versions.
# INPUTS: before, after (str).
# OUTPUTS: {"errors": [ {kind, what, detail} ], "checks": [...], "counts": {...}}.
# SIDE_EFFECTS: none.
# END_CONTRACT: compare
def compare(before: str, after: str) -> Dict:
    fb, fa = extract(before), extract(after)
    errors: List[Dict] = []
    checks: List[Dict] = []

    # START_BLOCK_NUMBERS_DIFF
    def bag(facts: Facts, kind: str) -> Dict[str, List[Fact]]:
        d: Dict[str, List[Fact]] = {}
        for f in facts.of(kind):
            d.setdefault(f.value, []).append(f)
        return d

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
                errors.append({"kind": "lost", "what": label, "detail": items[0].raw})
            elif missing > 0:
                checks.append({"kind": "fewer", "what": label,
                               "detail": "%s встречается реже (%d → %d)" % (items[0].raw, len(items), len(ba[value]))})
        for value, items in ba.items():
            if value not in bb and not (value == "1" and one_in["before"]):
                errors.append({"kind": "added", "what": label, "detail": items[0].raw})
        # units and hedges for numbers present in both
        if kind == "number":
            for value, items in bb.items():
                if value not in ba:
                    continue
                # "16:00" and "16 часов" are the same hour.
                units_b = {"ч" if f.unit == "время" else f.unit for f in items if f.unit}
                units_a = {"ч" if f.unit == "время" else f.unit for f in ba[value] if f.unit}
                if units_b and units_a and not (units_b & units_a):
                    errors.append({"kind": "unit", "what": "единица",
                                   "detail": "%s → %s" % (items[0].raw, ba[value][0].raw)})
                elif units_b and not units_a:
                    checks.append({"kind": "unit", "what": "единица",
                                   "detail": "%s → %s без единицы" % (items[0].raw, ba[value][0].raw)})
                hedges_b = {f.hedge for f in items if f.hedge}
                hedges_a = {f.hedge for f in ba[value] if f.hedge}
                for h in hedges_b - hedges_a:
                    checks.append({"kind": "hedge", "what": "оговорка",
                                   "detail": "«%s» перед %s не найдено" % (h, items[0].raw)})
    # END_BLOCK_NUMBERS_DIFF

    # START_BLOCK_MONTHS_DIFF
    # A month without a day must survive as a month, alone or inside a full date.
    def months(facts: Facts) -> set:
        return {f.value for f in facts.of("month")} | {
            str(int(f.value[3:])) for f in facts.of("date") if re.fullmatch(r"\d\d\.\d\d", f.value)}
    mb, ma = months(fb), months(fa)
    for f in fb.of("month"):
        if f.value not in ma:
            errors.append({"kind": "lost", "what": "дата", "detail": f.raw})
    for f in fa.of("month"):
        if f.value not in mb:
            errors.append({"kind": "added", "what": "дата", "detail": f.raw})
    # END_BLOCK_MONTHS_DIFF

    # START_BLOCK_NAMES_DIFF
    after_words = re.findall(r"[\w-]+", after)
    seen = set()
    for f in fb.of("name"):
        key = _norm(f.value.lower())[:5]
        if key in seen:
            continue
        seen.add(key)
        if any(name_match(f.value, w) for w in after_words):
            continue
        # An acronym spelled out is kept: «УК» → «управляющую компанию».
        if f.value.isupper() and 2 <= len(f.value) <= 4 and any(
                "".join(w[0] for w in after_words[i:i + len(f.value)]).lower() == f.value.lower()
                for i in range(len(after_words) - len(f.value) + 1)):
            continue
        errors.append({"kind": "lost", "what": "имя или название", "detail": f.raw})
    before_words = re.findall(r"[\w-]+", before)
    seen = set()
    for f in fa.of("name"):
        key = _norm(f.value.lower())[:5]
        if key in seen:
            continue
        seen.add(key)
        if not any(name_match(f.value, w) for w in before_words):
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
        return re.findall(r"[\w-]+", s)

    def contains(hay: List[str], needle: List[str], exact: bool = False) -> bool:
        # Direct speech is compared word for word: «запустили» → «запустим» changes the words.
        same = (lambda x, y: _norm(x.lower()) == _norm(y.lower())) if exact else stem_match
        n = len(needle)
        return any(all(same(x, y) for x, y in zip(hay[i:i + n], needle))
                   for i in range(len(hay) - n + 1))

    quotes_a = [words(f.raw) for f in fa.of("quote")]
    seen = set()
    for f in fb.of("quote"):
        w = words(f.raw)
        key = tuple(_norm(x.lower()) for x in w)
        if not w or key in seen:
            continue
        seen.add(key)
        if any(contains(q, w, f.speech) for q in quotes_a):
            continue
        if contains(after_words, w, f.speech):
            checks.append({"kind": "unquoted", "what": "цитата", "detail": "«%s» без кавычек" % f.raw})
        else:
            (errors if f.speech else checks).append({"kind": "lost", "what": "цитата", "detail": "«%s»" % f.raw})
    seen = set()
    for f in fa.of("quote"):
        w = words(f.raw)
        key = tuple(_norm(x.lower()) for x in w)
        if not w or key in seen:
            continue
        seen.add(key)
        if not contains(before_words, w):
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
    for f in fb.of("negation"):
        if f.hedge in ("нет", "нельзя"):
            gone = not re.search(r"(?<![а-яё])%s(?![а-яё])" % f.hedge, after_norm)
            can = r"(?<![а-яё])можно(?![а-яё])"
            if gone and f.hedge == "нельзя" and \
                    len(re.findall(can, after_norm)) > len(re.findall(can, before_norm)):
                errors.append({"kind": "inverted", "what": "отрицание",
                               "detail": "«нельзя» пропало, а «можно» появилось"})
            elif gone and len(fa.of("negation")) < len(fb.of("negation")):
                checks.append({"kind": "negation", "what": "отрицание", "detail": "«%s» не найдено" % f.raw})
            continue
        word = f.value
        negated = [m for m in re.finditer(r"(?<![а-яё])(не|ни|без|нет|нельзя)\s+(?:[а-яё]+\s+){0,2}([а-яё]{3,})", after_norm)
                   if stem_match(m.group(2), word, strict=True)]
        if negated:
            continue
        if word in ("только", "менее", "более", "раньше", "позже", "позднее", "просто", "всегда", "совсем"):
            continue
        hits = _occurrences(after_norm, word)
        src_hits = _occurrences(before_norm, word)
        only_negated_in_source = all(_negated_near(before_norm, a, b) for a, b in src_hits)
        if hits:
            if only_negated_in_source and all(not _negated_near(after_norm, a, b) for a, b in hits):
                (checks if f.unit == "contrast" else errors).append(
                    {"kind": "inverted", "what": "отрицание",
                     "detail": "«%s» в правке стоит без отрицания" % f.raw})
        else:
            checks.append({"kind": "negation", "what": "отрицание",
                           "detail": "«%s» не найдено, проверь, что смысл сохранён" % f.raw})
    # The other way round: "Мы храним данные" → "Мы не храним данные".
    seen = set()
    for f in fa.of("negation"):
        word = f.value
        if f.hedge not in ("не", "ни") or word in seen or word in (
                "только", "менее", "более", "раньше", "позже", "позднее", "просто", "всегда", "совсем"):
            continue
        seen.add(word)
        src_hits = _occurrences(before_norm, word)
        if src_hits and all(not _negated_near(before_norm, a, b) for a, b in src_hits) and \
                all(_negated_near(after_norm, a, b) for a, b in _occurrences(after_norm, word)):
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
    # A surname right after a first name is the same person: «Анна Иванова» is one owner.
    names_b = [f for f in fb.of("name")
               if not any(y.sent == f.sent and y.pos + len(y.raw) + 1 == f.pos for y in fb.of("name"))]
    for n in fb.of("number"):
        owners = {_norm(x.value.lower())[:5] for x in names_b if x.sent == n.sent}
        if len(owners) == 1:
            pairs.setdefault(n.value, set()).update(owners)
    all_owners = set().union(*pairs.values()) if pairs else set()

    def near(facts, n) -> set:
        words = re.findall(r"[\w-]+", facts.sentences[n.sent] if n.sent < len(facts.sentences) else "")
        return {o for o in all_owners if any(stem_match(o, w) for w in words)}

    if len(all_owners) >= 2:
        # A number that already stood next to a name somewhere in the original has not moved
        # there: «750 мл из стали» in a product card, with «Сталь 18/8» in its table.
        near_b: Dict[str, set] = {}
        for n in fb.of("number"):
            near_b.setdefault(n.value, set()).update(near(fb, n))
        for n in fa.of("number"):
            want = pairs.get(n.value)
            if not want:
                continue
            here = near(fa, n)
            if here - near_b.get(n.value, set()) and not (here & want):
                errors.append({"kind": "swap", "what": "привязка",
                               "detail": "%s в исходнике относится к «%s», в правке стоит рядом с «%s»" % (
                                   n.raw, "/".join(sorted(want)), "/".join(sorted(here)))})
    # END_BLOCK_BINDINGS

    counts = {k: len(fb.of(k)) for k in ("number", "date", "name", "url", "phone", "quote", "negation")}
    return {"errors": _dedupe(errors), "checks": _dedupe(checks), "counts": counts}


def _dedupe(items: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in items:
        key = (it["kind"], it["what"], it["detail"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


KIND_RU = {"lost": "потеряно", "added": "появилось", "unit": "изменилась", "swap": "перестановка",
           "inverted": "перевёрнуто",
           "fewer": "реже", "hedge": "потеряна", "negation": "проверь"}
# The verb agrees with the noun: «потеряна цитата», «потерян телефон», «потеряно число».
KIND_FEM = {"потеряно": "потеряна", "появилось": "появилась", "перевёрнуто": "перевёрнута"}
KIND_MASC = {"потеряно": "потерян", "появилось": "появился", "перевёрнуто": "перевёрнут"}
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
    if result["checks"]:
        lines.append("Проверь глазами (%d):" % len(result["checks"]))
        for e in result["checks"]:
            lines.append("  - %s: %s" % (e["what"], e["detail"]))
    lines.append("Итог: " + ("есть ошибки, верни факты в текст" if result["errors"] else
                             "ошибок не найдено (это не гарантия смысла: перечитай условия и связи)"))
    return "\n".join(lines)


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
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
    print(json.dumps(result, ensure_ascii=False, indent=2) if as_json else render(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
