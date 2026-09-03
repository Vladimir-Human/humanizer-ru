#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facts_diff.py — детерминированная сверка фактов двух версий текста (F1).

Извлечение БЕЗ ML, только стандартная библиотека. Категории фактов:
  numbers   — цифры с тысячными разделителями и дробной частью, опционально
              с единицей (%, ₽, $, €, кг, км, ч, штук и т.п.);
  numwords  — русские числительные (слогами до трёх слов) с единицей;
  dates     — дд.мм.гггг, дд месяц гггг, месяц гггг, гггг год/г., ISO гггг-мм-дд;
  urls      — http(s)-ссылки и www.;
  emails    — адреса почты;
  names     — последовательности из 2+ заглавных слов (имена собственные);
  quotes    — кавычные цитаты («…», "…");
  negations — отрицания: отдельное «не» + слово, «нет», «ни» + слово,
              «без» + слово (объём сознательно консервативный);
  modals    — должен/нельзя/можно/нужно/необходимо/запрещено/разрешено/
              требуется/следует.

diff(до, после) -> lost / added / changed с позициями:
  lost    — факт категории есть в «до» и исчез в «после» (мультимножество);
  added   — факт появился в «после», которого не было в «до»;
  changed — инверсия отрицания: «не X» в «до» стало утвердительным X в
            «после» (самый опасный класс потери смысла).

Коды выхода CLI: 0 — lost и changed пусты; 1 — есть lost или changed;
2 — вход не читается (конверт ошибки contract.v1). added на код не влияет
(их ловит check_examples.py как «не добавил факты»).

Запуск:
  python -m humanizer_ru.facts_diff diff <до> <после> [--json]
  python -m humanizer_ru.facts_diff --selftest

Только стандартная библиотека. Вердиктов об авторстве и качестве нет.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

SCHEMA = 1
TOOL = "humanizer-facts"

# ---------------------------------------------------------------- извлечение

_SEP = " \u00a0\u202f"
NUM_RX = re.compile(
    r"\d+(?:[%s]\d{3})*(?:[.,]\d+)?" % _SEP)
UNIT_RX = re.compile(
    r"\s?(?:%|‰|₽|\$|€|£|¥|°C|°|кг|г|т|км|м|см|мм|км|л|мл|шт|штук|человек|"
    r"человека|человек|дней|дня|день|дн|часов|часа|час|ч|минут|минуты|минуту|"
    r"мин|секунд|секунды|сек|лет|года|год|г|месяцев|месяца|месяц|недель|"
    r"недели|недель|страниц|страницы|страниц|стр|слов|слова|слов|символов|"
    r"символа|символ|байт|КБ|МБ|ГБ|ТБ|px|pt|em|rem|ms|kHz|MHz|GHz|Hz|Вт|кВт|"
    r"процентов|процента|процент|п\.?\s?п\.?)")
NUMWORD_SRC = """
один одна одно одного одним два две двух двумя три трех тремя четыре четырех
пять пяти шесть шести семь семи восемь восьми девять девяти десять десяти
одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать
семнадцать восемнадцать девятнадцать двадцать тридцать сорок пятьдесят
шестьдесят семьдесят восемьдесят девяносто сто ста двести триста четыреста
пятьсот шестьсот семьсот восемьсот девятьсот тысяча тысячи тысяч тысячу
миллион миллиона миллионов миллиард миллиардов первый первая первое второй
вторая третье третий третья четвертый четвертая пятый пятая шестой шестая
седьмой седьмая восьмой восьмая девятый девятая десятый десятая двое трое
четверо пятеро шестеро семеро восьмеро девятеро десятеро дюжина дюжины
сотня сотни полсотни
"""
NUMWORDS = set(NUMWORD_SRC.split())
NUMWORD_RX = re.compile(
    r"\b(?:%s)(?:\s+(?:%s)){0,2}\b" % ("|".join(sorted(NUMWORDS, key=len,
                                                      reverse=True)),
                                      "|".join(sorted(NUMWORDS, key=len,
                                                      reverse=True))))
MONTHS = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|"
          "октября|ноября|декабря|январь|февраль|март|апрель|май|июнь|июль|"
          "август|сентябрь|октябрь|ноябрь|декабрь")
DATE_RX = re.compile(
    r"(?:\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?|\d{1,2}\s+(?:%s)\s+\d{4}(?:\s*г\.?)?|"
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


def _norm_num(raw: str) -> str:
    return re.sub("[%s]" % _SEP, "", raw).replace(",", ".")


def extract(text: str) -> Dict[str, List[dict]]:
    """Факты текста: категория -> список {value, pos} (pos — смещение)."""
    out: Dict[str, List[dict]] = {k: [] for k in (
        "numbers", "numwords", "dates", "urls", "emails", "names",
        "quotes", "negations", "modals")}

    for m in DATE_RX.finditer(text):
        out["dates"].append({"value": re.sub(r"\s+", " ", m.group()).strip(),
                             "pos": m.start()})
    date_spans = [(m.start(), m.end()) for m in DATE_RX.finditer(text)]

    def _inside_dates(start: int, end: int) -> bool:
        return any(s <= start and end <= e for s, e in date_spans)

    for m in NUM_RX.finditer(text):
        if _inside_dates(m.start(), m.end()):
            continue
        rest = text[m.end():m.end() + 12]
        unit = UNIT_RX.match(rest)
        value = _norm_num(m.group()) + (unit.group().strip() if unit else "")
        out["numbers"].append({"value": value, "pos": m.start()})
    num_spans = [(m.start(), m.end()) for m in NUM_RX.finditer(text)]

    for m in NUMWORD_RX.finditer(text):
        if any(s <= m.start() < e for s, e in num_spans) or \
                _inside_dates(m.start(), m.end()):
            continue
        words = m.group().split()
        if not any(w in NUMWORDS for w in words):
            continue
        rest = text[m.end():m.end() + 12]
        unit = UNIT_RX.match(rest)
        value = " ".join(words) + ((" " + unit.group().strip()) if unit else "")
        out["numwords"].append({"value": value, "pos": m.start()})

    for m in URL_RX.finditer(text):
        out["urls"].append({"value": m.group(), "pos": m.start()})
    for m in EMAIL_RX.finditer(text):
        out["emails"].append({"value": m.group(), "pos": m.start()})

    tokens = list(CAPWORD_RX.finditer(text))
    i = 0
    while i < len(tokens):
        j = i
        while j + 1 < len(tokens):
            between = text[tokens[j].end():tokens[j + 1].start()]
            if between in (" ", " - ", " — ", " – ") or between in (
                    "-", "—", "–"):
                j += 1
            else:
                break
        if j > i:
            out["names"].append(
                {"value": re.sub(r"\s+", " ",
                                 text[tokens[i].start():tokens[j].end()]).strip(),
                 "pos": tokens[i].start()})
        i = j + 1

    for m in QUOTE_RX.finditer(text):
        out["quotes"].append({"value": m.group(), "pos": m.start()})
    for m in NEG_RX.finditer(text):
        low = m.group().lower()
        head = re.split(r"\s+", low)[0]
        if any(low.startswith(s) for s in NEG_STOP) and head not in (
                "не", "нет", "ни", "без"):
            continue
        out["negations"].append(
            {"value": re.sub(r"\s+", " ", m.group()).strip(), "pos": m.start()})
    for m in MODAL_RX.finditer(text):
        out["modals"].append(
            {"value": m.group().lower(), "pos": m.start()})
    return out


# ---------------------------------------------------------------- сравнение

def _key(cat: str, value: str) -> str:
    # Имена собственные сравниваются без регистра: правка регистра в
    # заголовках («Ранняя Жизнь» -> «Ранняя жизнь») — не потеря факта.
    return value.casefold() if cat == "names" else value


def _multiset(facts: Dict[str, List[dict]]) -> Dict[str, Dict[str, int]]:
    ms: Dict[str, Dict[str, int]] = {}
    for cat, items in facts.items():
        bucket: Dict[str, int] = {}
        for it in items:
            k = _key(cat, it["value"])
            bucket[k] = bucket.get(k, 0) + 1
        ms[cat] = bucket
    return ms


def diff(before: str, after: str) -> dict:
    """lost/added/changed с позициями; changed — инверсии отрицаний."""
    fb, fa = extract(before), extract(after)
    mb, ma = _multiset(fb), _multiset(fa)
    lost: List[dict] = []
    added: List[dict] = []
    for cat in mb:
        for value in sorted(set(mb[cat]) | set(ma[cat])):
            cb, ca = mb[cat].get(value, 0), ma[cat].get(value, 0)
            if cb > ca:
                pos = next(it["pos"] for it in fb[cat]
                           if _key(cat, it["value"]) == value)
                raw = next(it["value"] for it in fb[cat]
                           if _key(cat, it["value"]) == value)
                for _ in range(cb - ca):
                    lost.append({"category": cat, "value": raw,
                                 "pos_before": pos})
            elif ca > cb:
                pos = next(it["pos"] for it in fa[cat]
                           if _key(cat, it["value"]) == value)
                raw = next(it["value"] for it in fa[cat]
                           if _key(cat, it["value"]) == value)
                for _ in range(ca - cb):
                    added.append({"category": cat, "value": raw,
                                  "pos_after": pos})

    # Имя не потеряно, если его слова остались в «после» целой подстрокой
    # без учёта регистра: правка регистра/структуры заголовка — не удаление
    # факта (пара «## Ранняя Жизнь» -> «## Ранняя жизнь»).
    after_low = after.casefold()
    lost = [i for i in lost
            if not (i["category"] == "names"
                    and i["value"].casefold() in after_low)]
    before_low = before.casefold()
    added = [i for i in added
             if not (i["category"] == "names"
                     and i["value"].casefold() in before_low)]

    changed: List[dict] = []
    after_words = set(re.findall(r"[а-яё]+", after.lower()))
    for item in fb["negations"]:
        parts = item["value"].lower().split()
        if len(parts) == 2 and parts[0] == "не":
            stem = parts[1]
            still_negated = any(
                a["value"].lower() == item["value"].lower()
                for a in fa["negations"])
            if not still_negated and stem in after_words:
                changed.append({"category": "negations",
                                "before": item["value"], "after": stem,
                                "pos_before": item["pos"],
                                "kind": "инверсия отрицания"})
    mb_mod = {i["value"] for i in fb["modals"]}
    ma_mod = {i["value"] for i in fa["modals"]}
    for m_norm, m_perm in (("нельзя", "можно"), ("запрещено", "разрешено")):
        if m_norm in mb_mod and m_norm not in ma_mod \
                and m_perm in ma_mod and m_perm not in mb_mod:
            pos = next(i["pos"] for i in fb["modals"] if i["value"] == m_norm)
            changed.append({"category": "modals", "before": m_norm,
                            "after": m_perm, "pos_before": pos,
                            "kind": "инверсия модальности"})
    return {"lost": lost, "added": added, "changed": changed}


def envelope(before: str, after: str, files=None) -> dict:
    d = diff(before, after)
    return {"tool": TOOL, "schema": SCHEMA,
            "files": list(files or ["<before>", "<after>"]),
            "counts": {"lost": len(d["lost"]), "added": len(d["added"]),
                       "changed": len(d["changed"])},
            "diff": d}


# ---------------------------------------------------------------- CLI

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL, description="Сверка фактов двух версий текста (F1).")
    sub = parser.add_subparsers(dest="cmd")
    p_diff = sub.add_parser("diff", help="сравнить два файла")
    p_diff.add_argument("before")
    p_diff.add_argument("after")
    p_diff.add_argument("--json", action="store_true",
                        help="машиночитаемый конверт {tool, schema, counts, diff}")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.cmd != "diff":
        parser.print_help()
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
    env = envelope(before, after, files=[args.before, args.after])
    if args.json:
        print(json.dumps(env, ensure_ascii=False, indent=2))
    else:
        for kind in ("lost", "changed", "added"):
            for item in env["diff"][kind]:
                if kind == "changed":
                    print("%s: %r -> %r (%s)" % (kind, item["before"],
                                                 item["after"], item["kind"]))
                else:
                    print("%s: [%s] %r (pos %d)" % (kind, item["category"],
                                                    item["value"],
                                                    item.get("pos_before",
                                                             item.get("pos_after"))))
        if not env["diff"]["lost"] and not env["diff"]["changed"]:
            print("потерь и инверсий фактов нет")
    return 0 if not env["diff"]["lost"] and not env["diff"]["changed"] else 1


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
    a_ok = "Заявок за неделю стало 12%, срок — до 15.03.2026, бюджет 500 тыс. ₽. " \
        "Иван Петров не подтвердил данные; отчёт нельзя публиковать без соглашения."
    d = diff(b, a_ok)
    case("идентичные тексты: пусто", not d["lost"] and not d["added"]
         and not d["changed"])

    a_lost = "Заявок за неделю стало много, срок — скоро, бюджет уточняется. " \
        "Иван Петров не подтвердил данные; отчёт нельзя публиковать."
    d = diff(b, a_lost)
    case("потерянное число ловится",
         any(i["category"] == "numbers" and i["value"].startswith("12")
             for i in d["lost"]))
    case("потерянная дата ловится",
         any(i["category"] == "dates" for i in d["lost"]))

    a_inv = "Заявок за неделю стало 12%, срок — до 15.03.2026, бюджет 500 тыс. ₽. " \
        "Иван Петров подтвердил данные; отчёт можно публиковать без соглашения."
    d = diff(b, a_inv)
    case("инверсия отрицания ловится как changed",
         any(i["kind"] == "инверсия отрицания" for i in d["changed"]))

    a_add = b + " Встреча прошла 01.04.2026."
    d = diff(b, a_add)
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

    d = diff("двадцать пять страниц отчёта", "страниц отчёта")
    case("числительное ловится как lost",
         any(i["category"] == "numwords" for i in d["lost"]))

    env = envelope(b, b)
    case("конверт стабилен", env["tool"] == TOOL and env["schema"] == SCHEMA
         and env["counts"] == {"lost": 0, "added": 0, "changed": 0})

    print("САМОПРОВЕРКА facts_diff: %d FAIL" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
