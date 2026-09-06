#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facts_diff.py — детерминированная сверка фактов двух версий текста (F1).

Извлечение БЕЗ ML и БЕЗ внешних зависимостей: только стандартная
библиотека; поведение не зависит от окружения (словарная морфология в
продуктовый контур не входит — сравнение имён регистр-независимо;
исследовательская морфология отделена от поставляемого продукта,
решение 2026-09-07).

Категории фактов:
  numbers   — цифры и числительные словами (таблица 0-999 + разряды);
              канон значения = точное десятичное представление без
              промежуточного float (знак, группировка разрядов и
              десятичный разделитель нормализуются строково) плюс
              каноническая единица с границей слова, поэтому
              «15 %» и «пятнадцать процентов» — один факт, а
              «5 минут» и «5 миндалин» — разные;
              знак числа («-», «+», U+2212) входит в значение, если не
              стоит сразу после цифры («10-20» — два беззнаковых);
              поле date_like=true помечает запись вида дд.мм или дд,мм
              без года: по явному правилу ниже она прочитана десятичным
              числом, неоднозначность не скрывается;
  dates     — дд.мм.гггг, дд.мм.гг, дд месяц гггг, месяц гггг,
              гггг год/г., ISO; запись дд.мм БЕЗ года датой не
              считается (явное правило разведения дат и десятичных
              чисел: без года и имени месяца это десятичное число);
  urls      — http(s)-ссылки и www.;
  emails    — адреса почты;
  names     — последовательности из 2+ заглавных слов,
              регистр-независимо;
  quotes    — кавычные цитаты («…», "…");
  negations — отрицания: отдельное «не» + слово, «нет», «ни» + слово,
              «без» + слово;
  modals    — должен/нельзя/можно/нужно/необходимо/запрещено/разрешено/
              требуется/следует;
  protected — термины из --protect terms.txt, потеря которых = ошибка.

diff(до, после) -> lost / added / changed с позициями; changed — инверсии
отрицаний («не X» -> «X») и нормативных модальностей (нельзя -> можно,
запрещено -> разрешено). Коды выхода CLI: 0 — нет lost/changed, 1 — есть,
2 — вход не читается (конверт ошибки). Конверт: {tool, schema, files,
counts, diff}.

Неполнота извлечения: сверка оперирует поддерживаемыми категориями
фактов; успешная сверка НЕ является семантической гарантией сохранения
смысла текста (порядок слов, отрицания вне шаблонов, смысл единиц вне
канонического списка остаются за границей проверки).

Запуск:
  python -m humanizer_ru.facts_diff diff <до> <после> [--json]
                                    [--protect terms.txt]
  python -m humanizer_ru.facts_diff --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Dict, List, Optional, Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

SCHEMA = 1
TOOL = "humanizer-facts"


def _lemma(word: str) -> str:
    """Регистр-независимое сравнение имён: продуктовый контур не зависит
    от окружения (словарная морфология — исследовательский инструмент)."""
    return word.casefold()


# ---------------------------------------------------------------- извлечение

_SEP = " \u00a0\u202f"
# Знак входит в число, только если не стоит сразу после цифры:
# «-5 млн» — знаковое, «10-20» — два беззнаковых (диапазон, не знак).
_SIGN = "+\\-\u2212"
NUM_RX = re.compile(r"(?<!\d)[%s]?\d+(?:[%s]\d{3})*(?:[.,]\d+)?"
                    % (_SIGN, _SEP))
# Запись вида дд.мм / дд,мм без года: кандидат в «дату без года»,
# по явному правилу читается десятичным числом и помечается date_like.
_DATE_LIKE_RX = re.compile(r"^[%s]?\d{1,2}[.,]\d{1,2}$" % _SIGN)

UNIT_SYNONYMS = [
    (("%", "процент", "процента", "процентов", "проценту", "процентами"), "%"),
    (("₽", "рубль", "рубля", "рублей", "рублю", "рублями", "руб"), "₽"),
    (("$", "доллар", "доллара", "долларов", "долларам"), "$"),
    (("€", "евро"), "€"),
    (("кг", "килограмм", "килограмма", "килограммов"), "кг"),
    (("км", "километр", "километра", "километров"), "км"),
    (("см", "сантиметр", "сантиметра"), "см"),
    (("мм", "миллиметр", "миллиметра"), "мм"),
    (("л", "литр", "литра", "литров"), "л"),
    (("мл", "миллилитр", "миллилитра"), "мл"),
    (("шт", "штука", "штуки", "штук"), "шт"),
    (("ч", "час", "часа", "часов", "часу"), "ч"),
    (("мин", "минута", "минуты", "минут"), "мин"),
    (("сек", "секунда", "секунды", "секунд"), "сек"),
    (("день", "дня", "дней", "дн"), "дн"),
    (("неделя", "недели", "недель"), "нед"),
    (("месяц", "месяца", "месяцев"), "мес"),
    (("год", "года", "лет", "г"), "год"),
    (("человек", "человека", "людей", "чел"), "чел"),
    (("страница", "страницы", "страниц", "стр"), "стр"),
    (("слово", "слова", "слов"), "слов"),
    (("символ", "символа", "символов"), "сим"),
    (("байт", "байта"), "Б"),
    (("КБ", "килобайт", "килобайта"), "КБ"),
    (("МБ", "мегабайт", "мегабайта"), "МБ"),
    (("ГБ", "гигабайт", "гигабайта"), "ГБ"),
]
UNIT_CANON = {}
for _syns, _canon in UNIT_SYNONYMS:
    for _syn in _syns:
        UNIT_CANON[_syn] = _canon
UNIT_RX = re.compile(
    r"\s?(?:%s)(?![0-9A-Za-z\u0400-\u04ff])"
    % "|".join(sorted((re.escape(w) for w in UNIT_CANON),
                      key=len, reverse=True)))

_UNITS_MAP = {
    "один": 1, "одна": 1, "одно": 1, "одного": 1, "одной": 1, "одним": 1,
    "одном": 1, "одну": 1, "два": 2, "две": 2, "двух": 2, "двумя": 2,
    "двум": 2, "три": 3, "трех": 3, "тремя": 3, "четыре": 4, "четырех": 4,
    "четырьмя": 4, "пять": 5, "пяти": 5, "пятью": 5, "шесть": 6, "шести": 6,
    "шестью": 6, "семь": 7, "семи": 7, "семью": 7, "восемь": 8, "восьми": 8,
    "восьмью": 8, "девять": 9, "девяти": 9, "девятью": 9,
}
_TEENS_MAP = {
    "десять": 10, "десяти": 10, "десятью": 10, "одиннадцать": 11,
    "одиннадцати": 11, "одиннадцатью": 11, "двенадцать": 12,
    "двенадцати": 12, "двенадцатью": 12, "тринадцать": 13,
    "тринадцати": 13, "четырнадцать": 14, "четырнадцати": 14,
    "пятнадцать": 15, "пятнадцати": 15, "пятнадцатью": 15,
    "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17,
    "семнадцати": 17, "восемнадцать": 18, "восемнадцати": 18,
    "девятнадцать": 19, "девятнадцати": 19,
}
_TENS_MAP = {
    "двадцать": 20, "двадцати": 20, "двадцатью": 20, "тридцать": 30,
    "тридцати": 30, "тридцатью": 30, "сорок": 40, "сорока": 40,
    "пятьдесят": 50, "пятидесяти": 50, "пятьюдесятью": 50,
    "шестьдесят": 60, "шестидесяти": 60, "шестьюдесятью": 60,
    "семьдесят": 70, "семидесяти": 70, "семьюдесятью": 70,
    "восемьдесят": 80, "восьмидесяти": 80, "восьмьюдесятью": 80,
    "девяносто": 90, "девяноста": 90,
}
_HUNDREDS_MAP = {
    "сто": 100, "ста": 100, "сот": 100, "стами": 100, "двести": 200,
    "двухсот": 200, "двумястами": 200, "триста": 300, "трехсот": 300,
    "тремястами": 300, "четыреста": 400, "четырехсот": 400,
    "четырьмястами": 400, "пятьсот": 500, "пятисот": 500,
    "пятьюстами": 500, "шестьсот": 600, "шестисот": 600,
    "шестьюстами": 600, "семьсот": 700, "семисот": 700,
    "семьюстами": 700, "восемьсот": 800, "восьмисот": 800,
    "восьмьюстами": 800, "девятьсот": 900, "девятисот": 900,
    "девятьюстами": 900,
}
_SCALES = {
    "сотня": 100, "сотни": 100, "сотен": 100,
    "дюжина": 12, "дюжины": 12, "дюжин": 12,
    "полсотни": 50,
    "тысяча": 1000, "тысячи": 1000, "тысяч": 1000, "тысячу": 1000,
    "тысячей": 1000, "тысячам": 1000, "тысячах": 1000,
    "миллион": 1000000, "миллиона": 1000000, "миллионов": 1000000,
    "миллиону": 1000000, "миллионом": 1000000, "миллионах": 1000000,
    "миллиард": 1000000000, "миллиарда": 1000000000,
    "миллиардов": 1000000000, "миллиарду": 1000000000,
}
NUMWORD_ALL = (set(_UNITS_MAP) | set(_TEENS_MAP) | set(_TENS_MAP)
               | set(_HUNDREDS_MAP) | set(_SCALES))
NUMWORD_RX = re.compile(r"\b(?:%s)\b" % "|".join(
    sorted((re.escape(w) for w in NUMWORD_ALL), key=len, reverse=True)))


def _word_value(word: str) -> Optional[int]:
    w = word.lower()
    for tbl in (_UNITS_MAP, _TEENS_MAP, _TENS_MAP, _HUNDREDS_MAP):
        if w in tbl:
            return tbl[w]
    return None


def _numwords_to_int(words: Sequence[str]) -> Optional[int]:
    total = 0
    section = 0
    seen = False
    for w in words:
        low = w.lower()
        if low in _SCALES:
            scale = _SCALES[low]
            if scale in (100, 12, 50):
                section += scale
                seen = True
                continue
            if section == 0:
                section = 1
            total += section * scale
            section = 0
            seen = True
            continue
        val = _word_value(low)
        if val is None:
            return None
        section += val
        seen = True
    if not seen:
        return None
    return total + section


MONTHS = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|"
          "октября|ноября|декабря|январь|февраль|март|апрель|май|июнь|июль|"
          "август|сентябрь|октябрь|ноябрь|декабрь")
# Явное правило разведения дат и десятичных чисел (2026-09-07): датой
# считаются только записи с годом, с именем месяца либо ISO; «дд.мм» без
# года извлекается как десятичное число с пометкой date_like (см. extract).
DATE_RX = re.compile(
    r"(?:\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+(?:%s)\s+\d{4}(?:\s*г\.?)?|"
    r"(?:%s)\s+\d{4}|\d{4}\s*(?:год|года|г\.|годы|годах|году)|"
    r"\d{4}-\d{2}-\d{2})" % (MONTHS, MONTHS))
URL_RX = re.compile(r"(?:https?://|www\.)[^\s<>«»\"')\]]+")
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CAPWORD_RX = re.compile(r"(?:[А-ЯЁ][а-яё]+|[A-Z][a-z]+)")
QUOTE_RX = re.compile(r"«[^»\n]{3,}»|\"[^\"\n]{3,}\"")
NEG_RX = re.compile(
    r"\b(?:не\s+[а-яё]{2,}|нет|ни\s+[а-яё]{2,}|без\s+[а-яё]{2,})\b", re.I)
NEG_STOP = {"небо", "невод", "нерв", "нефть", "неделя", "недели", "неделю",
            "неделях", "немного", "немало", "несколько", "некоторый",
            "некоторые", "некоторых", "безупреч", "безопас", "безотказ",
            "безгранич", "безукориз"}
MODAL_RX = re.compile(
    r"\b(?:должен|должна|должно|должны|нельзя|можно|нужно|необходимо|"
    r"запрещено|разрешено|требуется|следует)\b", re.I)
MODAL_INVERSION = (("нельзя", "можно"), ("запрещено", "разрешено"))


def _norm_num(raw: str) -> str:
    return re.sub("[%s]" % _SEP, "", raw).replace(",", ".")


def _canon_number(value: str, unit_raw: str) -> str:
    """Точный канон числа строково, без float: знак, группировка и
    десятичный разделитель нормализуются; дробь не усечена; целые любой
    длины точны (400 девяток — штатный вход, не OverflowError)."""
    unit = UNIT_CANON.get(unit_raw.strip().lower(), unit_raw.strip())
    s = re.sub("[%s]" % _SEP, "", value).replace(",", ".")
    sign = ""
    if s[:1] in ("+", "-", "\u2212"):
        sign = "-" if s[:1] in ("-", "\u2212") else ""
        s = s[1:]
    if "." in s:
        int_part, frac = s.split(".", 1)
        frac = frac.rstrip("0")
    else:
        int_part, frac = s, ""
    int_part = int_part.lstrip("0") or "0"
    num = int_part + ("." + frac if frac else "")
    if sign and num != "0":
        num = sign + num
    return num + ("|" + unit if unit else "")


def extract(text: str) -> Dict[str, List[dict]]:
    """Факты текста: категория -> список {value, raw, pos}."""
    out: Dict[str, List[dict]] = {k: [] for k in (
        "numbers", "dates", "urls", "emails", "names", "quotes",
        "negations", "modals", "protected")}

    date_spans = [(m.start(), m.end()) for m in DATE_RX.finditer(text)]
    for s, e in date_spans:
        out["dates"].append({"value": re.sub(r"\s+", " ", text[s:e]).strip(),
                             "raw": text[s:e], "pos": s})

    def _inside_dates(start: int, end: int) -> bool:
        return any(s <= start and end <= e for s, e in date_spans)

    num_spans = []
    for m in NUM_RX.finditer(text):
        if _inside_dates(m.start(), m.end()):
            continue
        rest = text[m.end():m.end() + 14]
        unit = UNIT_RX.match(rest)
        value = _canon_number(_norm_num(m.group()),
                              unit.group() if unit else "")
        item = {"value": value, "raw": m.group(), "pos": m.start()}
        if _DATE_LIKE_RX.match(m.group()):
            # дд.мм / дд,мм без года: прочитано десятичным числом по
            # явному правилу; неоднозначность помечена, не скрыта.
            item["date_like"] = True
        out["numbers"].append(item)
        num_spans.append((m.start(), m.end()))

    for m in NUMWORD_RX.finditer(text):
        if any(s <= m.start() < e for s, e in num_spans) or \
                _inside_dates(m.start(), m.end()):
            continue
        words = [m.group()]
        end = m.end()
        while end < len(text) and text[end] == " ":
            nxt = NUMWORD_RX.match(text, end + 1)
            if nxt is None:
                break
            words.append(nxt.group())
            end = nxt.end()
        rest = text[end:end + 14]
        unit = UNIT_RX.match(rest)
        num = _numwords_to_int(words)
        if num is None:
            continue
        unit_raw = unit.group() if unit else ""
        if UNIT_CANON.get(unit_raw.strip().lower()) == "год" \
                and 1000 <= num <= 2999:
            # год словами — та же дата, что «2026 год» цифрами
            out["dates"].append({"value": "%d год" % num,
                                 "raw": " ".join(words), "pos": m.start()})
        else:
            value = _canon_number(str(num), unit_raw)
            out["numbers"].append({"value": value, "raw": " ".join(words),
                                   "pos": m.start()})
        num_spans.append((m.start(), end))

    for m in URL_RX.finditer(text):
        out["urls"].append({"value": m.group(), "raw": m.group(),
                            "pos": m.start()})
    for m in EMAIL_RX.finditer(text):
        out["emails"].append({"value": m.group(), "raw": m.group(),
                              "pos": m.start()})

    tokens = list(CAPWORD_RX.finditer(text))
    i = 0
    while i < len(tokens):
        j = i
        while j + 1 < len(tokens):
            between = text[tokens[j].end():tokens[j + 1].start()]
            if between in (" ", " - ", " — ", " – ", "-", "—", "–"):
                j += 1
            else:
                break
        if j > i:
            raw = re.sub(r"\s+", " ",
                         text[tokens[i].start():tokens[j].end()]).strip()
            value = " ".join(_lemma(w) for w in raw.split())
            out["names"].append({"value": value, "raw": raw,
                                 "pos": tokens[i].start()})
        i = j + 1

    for m in QUOTE_RX.finditer(text):
        out["quotes"].append({"value": m.group(), "raw": m.group(),
                              "pos": m.start()})
    for m in NEG_RX.finditer(text):
        low = m.group().lower()
        head = re.split(r"\s+", low)[0]
        if any(low.startswith(s) for s in NEG_STOP) and head not in (
                "не", "нет", "ни", "без"):
            continue
        out["negations"].append({"value": re.sub(r"\s+", " ",
                                                 m.group()).strip(),
                                 "raw": m.group(), "pos": m.start()})
    for m in MODAL_RX.finditer(text):
        out["modals"].append({"value": m.group().lower(),
                              "raw": m.group(), "pos": m.start()})
    return out


# ---------------------------------------------------------------- сравнение

def _key(cat: str, value: str) -> str:
    return value.casefold() if cat in ("names", "quotes") else value


def _multiset(facts: Dict[str, List[dict]]) -> Dict[str, Dict[str, int]]:
    ms: Dict[str, Dict[str, int]] = {}
    for cat, items in facts.items():
        bucket: Dict[str, int] = {}
        for it in items:
            k = _key(cat, it["value"])
            bucket[k] = bucket.get(k, 0) + 1
        ms[cat] = bucket
    return ms


def diff(before: str, after: str,
         protect: Optional[Sequence[str]] = None) -> dict:
    fb, fa = extract(before), extract(after)
    mb, ma = _multiset(fb), _multiset(fa)
    lost: List[dict] = []
    added: List[dict] = []
    for cat in mb:
        for value in sorted(set(mb[cat]) | set(ma[cat])):
            cb, ca = mb[cat].get(value, 0), ma[cat].get(value, 0)
            if cb > ca:
                src = next(it for it in fb[cat]
                           if _key(cat, it["value"]) == value)
                for _ in range(cb - ca):
                    lost.append({"category": cat, "value": src["raw"],
                                 "pos_before": src["pos"]})
            elif ca > cb:
                src = next(it for it in fa[cat]
                           if _key(cat, it["value"]) == value)
                for _ in range(ca - cb):
                    added.append({"category": cat, "value": src["raw"],
                                  "pos_after": src["pos"]})

    # Имя/цитата не потеряны, если их слова остались целой подстрокой
    # без регистра: правка регистра/структуры — не удаление факта.
    after_low = after.casefold()
    before_low = before.casefold()
    lost = [i for i in lost
            if not (i["category"] in ("names", "quotes")
                    and i["value"].casefold() in after_low)]
    added = [i for i in added
             if not (i["category"] in ("names", "quotes")
                     and i["value"].casefold() in before_low)]

    changed: List[dict] = []
    after_words = set(re.findall(r"[а-яё]+", after.lower()))
    for item in fb["negations"]:
        parts = item["value"].lower().split()
        if len(parts) == 2 and parts[0] == "не":
            stem = parts[1]
            still = any(a["value"].lower() == item["value"].lower()
                        for a in fa["negations"])
            if not still and stem in after_words:
                changed.append({"category": "negations",
                                "before": item["value"], "after": stem,
                                "pos_before": item["pos"],
                                "kind": "инверсия отрицания"})
    mb_mod = {i["value"] for i in fb["modals"]}
    ma_mod = {i["value"] for i in fa["modals"]}
    for m_norm, m_perm in MODAL_INVERSION:
        if m_norm in mb_mod and m_norm not in ma_mod \
                and m_perm in ma_mod and m_perm not in mb_mod:
            pos = next(i["pos"] for i in fb["modals"] if i["value"] == m_norm)
            changed.append({"category": "modals", "before": m_norm,
                            "after": m_perm, "pos_before": pos,
                            "kind": "инверсия модальности"})

    for term in protect or ():
        term = term.strip()
        if not term:
            continue
        if term.lower() in before_low and term.lower() not in after_low:
            lost.append({"category": "protected", "value": term,
                         "pos_before": before_low.find(term.lower())})
    return {"lost": lost, "added": added, "changed": changed}


def envelope(before: str, after: str, files=None) -> dict:
    d = diff(before, after)
    return {"tool": TOOL, "schema": SCHEMA,
            "files": list(files or ["<before>", "<after>"]),
            "counts": {"lost": len(d["lost"]), "added": len(d["added"]),
                       "changed": len(d["changed"])},
            "diff": d}


# ---------------------------------------------------------------- CLI

SHORT_RU = "Проверяемая гигиена вставки из чата для русского текста"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL, description="Сверка фактов двух версий текста (F1).")
    sub = parser.add_subparsers(dest="cmd")
    p_diff = sub.add_parser("diff", help="сравнить два файла")
    p_diff.add_argument("before")
    p_diff.add_argument("after")
    p_diff.add_argument("--json", action="store_true",
                        help="машиночитаемый конверт {tool, schema, files, "
                             "counts, diff}")
    p_diff.add_argument("--protect", metavar="TERMS",
                        help="файл терминов/имён (по строке), потеря "
                             "которых = ошибка (category protected)")
    parser.add_argument("--selftest", action="store_true")
    parser.description = SHORT_RU + "\n\n" + (parser.description or "")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.cmd != "diff":
        parser.print_help()
        return 2
    protect = None
    if args.protect:
        try:
            with open(args.protect, encoding="utf-8") as fh:
                protect = [ln for ln in fh.read().splitlines() if ln.strip()]
        except OSError:
            print(json.dumps({"tool": TOOL, "schema": SCHEMA,
                              "error": "вход не читается (код 2)"},
                             ensure_ascii=False))
            return 2
    try:
        with open(args.before, encoding="utf-8") as fh:
            before = fh.read()
        with open(args.after, encoding="utf-8") as fh:
            after = fh.read()
    except OSError:
        print(json.dumps({"tool": TOOL, "schema": SCHEMA,
                          "error": "вход не читается (код 2)"},
                         ensure_ascii=False))
        return 2
    d = diff(before, after, protect=protect)
    env = {"tool": TOOL, "schema": SCHEMA,
           "files": [args.before, args.after],
           "counts": {"lost": len(d["lost"]), "added": len(d["added"]),
                      "changed": len(d["changed"])},
           "diff": d}
    if args.json:
        print(json.dumps(env, ensure_ascii=False, indent=2))
    else:
        for kind in ("lost", "changed", "added"):
            for item in env["diff"][kind]:
                if kind == "changed":
                    print("%s: %r -> %r (%s)" % (kind, item["before"],
                                                  item["after"],
                                                  item["kind"]))
                else:
                    print("%s: [%s] %r (pos %d)" % (
                        kind, item["category"], item["value"],
                        item.get("pos_before", item.get("pos_after"))))
        if not d["lost"] and not d["changed"]:
            print("потерь и инверсий фактов нет")
    return 0 if not d["lost"] and not d["changed"] else 1


# ---------------------------------------------------------------- selftest

def selftest() -> int:
    fails = 0

    def case(name: str, ok: bool):
        nonlocal fails
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        if not ok:
            fails += 1

    b = "Заявок за неделю стало 12%, срок — до 15.03.2026, бюджет 500 тыс. ₽. " \
        "Иван Петров не подтвердил данные; отчёт нельзя публиковать без соглашения."
    d = diff(b, b)
    case("идентичные тексты: пусто", not d["lost"] and not d["added"]
         and not d["changed"])

    a_lost = "Заявок за неделю стало много, срок — скоро, бюджет уточняется. " \
        "Иван Петров не подтвердил данные; отчёт нельзя публиковать."
    d = diff(b, a_lost)
    case("потерянное число ловится",
         any(i["category"] == "numbers" for i in d["lost"]))
    case("потерянная дата ловится",
         any(i["category"] == "dates" for i in d["lost"]))

    a_inv = "Заявок за неделю стало 12%, срок — до 15.03.2026, бюджет 500 тыс. ₽. " \
        "Иван Петров подтвердил данные; отчёт можно публиковать без соглашения."
    d = diff(b, a_inv)
    case("инверсия отрицания ловится как changed",
         any(i["kind"] == "инверсия отрицания" for i in d["changed"]))
    case("инверсия модальности ловится как changed",
         any(i["kind"] == "инверсия модальности" for i in d["changed"]))

    d = diff("встреча состоялась", "встреча 01 апреля 2026 года")
    case("добавленная дата ловится как added",
         any(i["category"] == "dates" for i in d["added"]))

    d = diff("см. https://example.com/report и mail team@corp.ru",
             "см. источники")
    case("url и email ловятся как lost",
         any(i["category"] == "urls" for i in d["lost"])
         and any(i["category"] == "emails" for i in d["lost"]))

    d = diff("«рынок вырос на 12%» — цитата", "цитата исчезла")
    case("кавычная цитата ловится как lost",
         any(i["category"] == "quotes" for i in d["lost"]))

    d = diff("пятнадцать процентов роста", "15 % роста")
    case("числительное словом равно цифре", not d["lost"] and not d["added"])
    d = diff("бюджет пятьсот тысяч рублей", "бюджет 500000 ₽")
    case("разрядное числительное равно цифре", not d["lost"] and not d["added"])
    d = diff("две тысячи двадцать шесть год", "2026 год")
    case("год словами равен цифре", not d["lost"] and not d["added"])

    d = diff("дорога длиной 5 километров", "дорога длиной 5 км")
    case("синонимы единиц не дают потерь", not d["lost"] and not d["added"])

    d = diff("Доза 1,1 мг.", "Доза 1,9 мг.")
    case("дробь не усечена: 1,1 -> 1,9 ловится",
         any(i["category"] == "numbers" for i in d["lost"])
         and any(i["category"] == "numbers" for i in d["added"]))
    d = diff("Убыток -5 млн.", "Убыток 5 млн.")
    case("знак числа входит в факт",
         any(i["category"] == "numbers" for i in d["lost"]))
    d = diff("Идентификатор 9007199254740992.",
             "Идентификатор 9007199254740993.")
    case("большие целые точны за границей 2^53",
         any(i["category"] == "numbers" for i in d["lost"]))
    d = diff("Ждать 5 минут.", "Ждать 5 миндалин.")
    case("единица с границей слова: минут/миндалин различаются",
         any(i["category"] == "numbers" for i in d["lost"]))
    d = diff("Объём 1.5 кг сырья.", "Объём 1.5 л сырья.")
    case("единицы кг/л различаются",
         any(i["category"] == "numbers" for i in d["lost"]))
    d = diff("Вес 1.5 кг.", "Вес 1,5 кг.")
    case("1.5 и 1,5 — один факт, ложной тревоги нет",
         not d["lost"] and not d["added"] and not d["changed"])
    d = diff("Итого 1 000 рублей.", "Итого 1000 рублей.")
    case("группировка разрядов не ломает равенство",
         not d["lost"] and not d["added"])
    case("диапазон 10-20 — два беззнаковых числа",
         len(extract("Диапазон страниц 10-20.")["numbers"]) == 2)
    big = "9" * 400
    d = diff("Значение %s единиц." % big, "Значение %s единиц." % big)
    case("400 девяток: точное равенство, без OverflowError",
         not d["lost"] and not d["added"])
    d = diff("Значение %s единиц." % big,
             "Значение %s единиц." % (big + "1"))
    case("400 и 401 цифра различаются",
         any(i["category"] == "numbers" for i in d["lost"]))
    ex = extract("Версия 1.5 вышла.")
    case("date_like помечает дд.мм без года",
         bool(ex["numbers"]) and ex["numbers"][0].get("date_like") is True)
    ex = extract("Срок до 15.03.2026.")
    case("полная дата остаётся датой, не числом",
         bool(ex["dates"]) and not ex["numbers"])

    d = diff("термин КвантовыйОтжиг важен", "важен",
             protect=["КвантовыйОтжиг"])
    case("protect: потеря термина ловится",
         any(i["category"] == "protected" for i in d["lost"]))
    d = diff("термин КвантовыйОтжиг важен", "КвантовыйОтжиг важен",
             protect=["КвантовыйОтжиг"])
    case("protect: термин на месте — чисто", not d["lost"])

    d = diff("## Ранняя Жизнь и Образование", "## Ранняя жизнь и образование")
    case("регистр заголовка не потеря", not d["lost"] and not d["added"])

    env = envelope(b, b)
    case("конверт стабилен", env["tool"] == TOOL and env["schema"] == SCHEMA
         and env["counts"] == {"lost": 0, "added": 0, "changed": 0})

    print("САМОПРОВЕРКА facts_diff: %d FAIL" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
