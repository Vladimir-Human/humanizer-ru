#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Compare an original Russian text with its edited version and report facts that
#          were lost, invented or rebound: numbers, dates, times, names, URLs, quotes,
#          negations, hedges and "who got which number" pairs; flags certainty, scope,
#          condition and attribution words that got rarer and intensifiers that got more frequent.
# SCOPE: heuristic, offline, stdlib only. Errors are likely real; "check" items need a human look.
#        An empty report does not prove the meaning is intact.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-CHECK-FACTS; DF-SKILL-CHECK; V-M-CHECK-FACTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# extract: text -> Facts (numbers with units, dates, urls, names, quotes, negations, hedges, sentences).
# compare: (before, after) -> {"errors": [...], "checks": [...]}.
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
from urllib.parse import urlsplit, urlunsplit

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
}
SCALE = {"тыс": 1000, "тыс.": 1000, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
         "млн": 10 ** 6, "млн.": 10 ** 6, "миллион": 10 ** 6, "миллиона": 10 ** 6,
         "миллионов": 10 ** 6, "млрд": 10 ** 9, "миллиард": 10 ** 9, "миллиарда": 10 ** 9,
         "миллиардов": 10 ** 9}
MONTHS = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|"
          "январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре|"
          "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь")
MONTH_STEM = {m[:3]: i for i, m in enumerate(
    "янв фев мар апр мая июн июл авг сен окт ноя дек".split(), 1)}
MONTH_STEM["май"] = 5
WEEKDAYS = ("понедельник|вторник|сред|четверг|пятниц|суббот|воскресень")
HEDGES = ("около", "примерно", "приблизительно", "почти", "порядка", "до", "не более",
          "не менее", "более", "свыше", "менее", "больше", "меньше", "минимум", "максимум",
          "от", "не больше", "не меньше", "не позже", "не позднее", "не раньше", "после",
          "только", "лишь", "кроме", "без")
NEG_WORDS = ("не", "ни", "нет", "нельзя", "без")
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
    return str(int(v)) if v == int(v) else ("%g" % v)


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
    for m in re.finditer(r"(?:https?://|www\.)[^\s<>«»\"')\]]+", text):
        url = m.group().rstrip(".,;:!?")
        facts.items.append(Fact("url", url.lower(), url, sent_of(m.start()), m.start()))
        taken.append((m.start(), m.start() + len(url)))
    for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        if free(m.start(), m.end()):
            facts.items.append(Fact("email", m.group().lower(), m.group(), sent_of(m.start()), m.start()))
            taken.append((m.start(), m.end()))
    # END_BLOCK_URLS

    # START_BLOCK_DATES_TIMES
    # Day and month stand on one line: "Вариант 3\n\nНоябрь — ..." is not the 3rd of November.
    date_rx = re.compile(r"\b(\d{1,2})(?:[ \t ]*(?:[–—-]|,|и)[ \t ]*(\d{1,2}))?[ \t ]+(%s)(?:[ \t ]+(\d{4}))?" % MONTHS, re.I)
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
        if free(m.start(), m.end()):
            hh, mm = int(m.group(1)), m.group(2)
            value = str(hh) if mm == "00" else "%d:%s" % (hh, mm)
            facts.items.append(Fact("number", value, m.group(), sent_of(m.start()), m.start(),
                                    hedge_before(m.start()), "время"))
            taken.append((m.start(), m.end()))
    # END_BLOCK_DATES_TIMES

    # START_BLOCK_NUMBERS
    # Counters in headings ("Вариант 1", "Шаг 2") are structure, not facts.
    for m in re.finditer(r"(?i)(?:вариант|шаг|этап|пункт|раздел|часть|глава)\s+(\d+)", text):
        taken.append((m.start(1), m.end(1)))
    num_rx = re.compile(r"(?<![\w.,])[+\-−]?\d+(?:[%s]\d{3})*(?:[.,]\d+)?(?![\w])" % SEP)
    for m in num_rx.finditer(text):
        if not free(m.start(), m.end()):
            continue
        v = _canon_num(m.group())
        if v is None:
            continue
        end = m.end()
        sc = re.match(r"[ \u00a0\u202f]+(%s)(?![а-я])" % "|".join(re.escape(k) for k in SCALE), text[end:end + 12], re.I)
        if sc:
            v *= SCALE[sc.group(1).lower()]
            end += sc.end()
        unit = ""
        um = UNIT_RX.match(text, end)
        if um:
            unit = UNIT_CANON.get(um.group(1).lower(), "")
            end = um.end()
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
            nxt = re.match(r"[ \u00a0]+(%s)(?![а-яё])" % "|".join(sorted(WORD_NUM, key=len, reverse=True)),
                           norm_text[end:end + 20], re.I)
            if not nxt:
                break
            w = float(WORD_NUM[nxt.group(1).lower()])
            last_order = 100 if v % 100 == 0 and v >= 100 else (10 if v % 10 == 0 and v >= 20 else 1)
            if last_order == 1 or w >= last_order or w != int(w):
                break
            v += w
            end += nxt.end()
        sc = re.match(r"[ \u00a0\u202f]+(%s)(?![а-я])" % "|".join(re.escape(k) for k in SCALE), text[end:end + 12], re.I)
        if sc:
            v *= SCALE[sc.group(1).lower()]
            end += sc.end()
        facts.items.append(Fact("number", _fmt(v), text[m.start():end], sent_of(m.start()),
                                m.start(), hedge_before(m.start())))
        taken.append((m.start(), end))
    # END_BLOCK_NUMBERS

    # START_BLOCK_NAMES_QUOTES
    for m in re.finditer(r"«([^»\n]{1,80})»|\"([^\"\n]{1,80})\"", text):
        q = (m.group(1) or m.group(2)).strip()
        facts.items.append(Fact("quote", q.lower(), q, sent_of(m.start()), m.start()))
    for s_start, sent in sents:
        for m in re.finditer(r"(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*)", sent):
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
    for m in re.finditer(r"(?<![а-яё])(не|ни|без)\s+([а-яё]{3,})|(?<![а-яё])(нет|нельзя)(?![а-яё])", _norm(text.lower())):
        if m.group(1):
            facts.items.append(Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(),
                                    hedge=m.group(1)))
        else:
            facts.items.append(Fact("negation", m.group(3), m.group(), sent_of(m.start()), m.start(),
                                    hedge=m.group(3)))
    # END_BLOCK_NEGATIONS
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


def strip_utm(url: str) -> Tuple[str, int]:
    """Drop utm_* query parameters, keep the others, the '?' and the fragment."""
    parts = urlsplit(url)
    if not parts.query:
        return url, 0
    params = parts.query.split("&")
    kept = [x for x in params if not x.lower().startswith("utm_")]
    if len(kept) == len(params):
        return url, 0
    return urlunsplit(parts._replace(query="&".join(kept))), len(params) - len(kept)


def _strip_tracking(text: str) -> str:
    def fix(m: "re.Match") -> str:
        url = m.group(0)
        tail = re.search(r"[.,;:!?]*$", url).group()
        return strip_utm(url[:len(url) - len(tail)])[0] + tail
    text = re.sub(r"https?://[^\s<>«»\"')\]]+", fix, text)
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

    for kind, label in (("number", "число"), ("date", "дата")):
        bb, ba = bag(fb, kind), bag(fa, kind)
        for value, items in bb.items():
            missing = len(items) - len(ba.get(value, []))
            if missing > 0 and value not in ba:
                errors.append({"kind": "lost", "what": label, "detail": items[0].raw})
            elif missing > 0:
                checks.append({"kind": "fewer", "what": label,
                               "detail": "%s встречается реже (%d → %d)" % (items[0].raw, len(items), len(ba[value]))})
        for value, items in ba.items():
            if value not in bb:
                errors.append({"kind": "added", "what": label, "detail": items[0].raw})
        # units and hedges for numbers present in both
        if kind == "number":
            for value, items in bb.items():
                if value not in ba:
                    continue
                units_b = {f.unit for f in items if f.unit}
                units_a = {f.unit for f in ba[value] if f.unit}
                if units_b and units_a and not (units_b & units_a):
                    errors.append({"kind": "unit", "what": "единица",
                                   "detail": "%s → %s" % (items[0].raw, ba[value][0].raw)})
                hedges_b = {f.hedge for f in items if f.hedge}
                hedges_a = {f.hedge for f in ba[value] if f.hedge}
                for h in hedges_b - hedges_a:
                    checks.append({"kind": "hedge", "what": "оговорка",
                                   "detail": "«%s» перед %s не найдено" % (h, items[0].raw)})
    # END_BLOCK_NUMBERS_DIFF

    # START_BLOCK_NAMES_DIFF
    after_words = re.findall(r"[\w-]+", after)
    seen = set()
    for f in fb.of("name"):
        key = _norm(f.value.lower())[:5]
        if key in seen:
            continue
        seen.add(key)
        if not any(stem_match(f.value, w) for w in after_words):
            errors.append({"kind": "lost", "what": "имя или название", "detail": f.raw})
    before_words = re.findall(r"[\w-]+", before)
    seen = set()
    for f in fa.of("name"):
        key = _norm(f.value.lower())[:5]
        if key in seen:
            continue
        seen.add(key)
        if not any(stem_match(f.value, w) for w in before_words):
            checks.append({"kind": "added", "what": "имя или название", "detail": f.raw})
    for kind, label in (("url", "ссылка"), ("email", "почта")):
        vb = {f.value for f in fb.of(kind)}
        va = {f.value for f in fa.of(kind)}
        for v in sorted(vb - va):
            errors.append({"kind": "lost", "what": label, "detail": v})
        for v in sorted(va - vb):
            errors.append({"kind": "added", "what": label, "detail": v})
    # END_BLOCK_NAMES_DIFF

    # START_BLOCK_NEGATIONS_DIFF
    after_norm = _norm(after.lower())
    before_norm = _norm(before.lower())
    for f in fb.of("negation"):
        if f.hedge in ("нет", "нельзя"):
            if not re.search(r"(?<![а-яё])%s(?![а-яё])" % f.hedge, after_norm) and \
                    len(fa.of("negation")) < len(fb.of("negation")):
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
                errors.append({"kind": "inverted", "what": "отрицание",
                               "detail": "«%s» в правке стоит без отрицания" % f.raw})
        else:
            checks.append({"kind": "negation", "what": "отрицание",
                           "detail": "«%s» не найдено, проверь, что смысл сохранён" % f.raw})
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

    # START_BLOCK_BINDINGS
    # Who got which number: in the original sentence a name and a number stand together;
    # in the edit the number must not move to a sentence with another of those names only.
    pairs: Dict[str, set] = {}
    # Only real names anchor a number: sentence subjects ("Капучино", "Итог") were too noisy.
    names_b = [f for f in fb.of("name")]
    for n in fb.of("number"):
        owners = {_norm(x.value.lower())[:5] for x in names_b if x.sent == n.sent}
        if len(owners) == 1:
            pairs.setdefault(n.value, set()).update(owners)
    all_owners = set().union(*pairs.values()) if pairs else set()
    if len(all_owners) >= 2:
        for n in fa.of("number"):
            want = pairs.get(n.value)
            if not want:
                continue
            sent_words = re.findall(r"[\w-]+", fa.sentences[n.sent] if n.sent < len(fa.sentences) else "")
            here = {o for o in all_owners if any(stem_match(o, w) for w in sent_words)}
            if here and not (here & want):
                errors.append({"kind": "swap", "what": "привязка",
                               "detail": "%s в исходнике относится к «%s», в правке стоит рядом с «%s»" % (
                                   n.raw, "/".join(sorted(want)), "/".join(sorted(here)))})
    # END_BLOCK_BINDINGS

    counts = {k: len(fb.of(k)) for k in ("number", "date", "name", "url", "quote", "negation")}
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


def render(result: Dict) -> str:
    lines = ["Сверка фактов: исходник → правка"]
    c = result["counts"]
    lines.append("В исходнике: чисел %d, дат %d, имён и названий %d, ссылок %d, отрицаний %d." % (
        c["number"], c["date"], c["name"], c["url"], c["negation"]))
    if result["errors"]:
        lines.append("Ошибки (%d):" % len(result["errors"]))
        for e in result["errors"]:
            lines.append("  - %s %s: %s" % (KIND_RU.get(e["kind"], e["kind"]), e["what"], e["detail"]))
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
