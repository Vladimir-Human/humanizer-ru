#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_examples.py — гейт честности пар «До/После».

Проверяет главное обещание скилла: правка не дописывает факты за автора.
В варианте «После» не должно появляться проверяемых фактов (чисел, дат,
имён собственных), которых нет в «До».

Два типа пар:
  1. Правка — «**После:**». Новых фактов быть не может.
  2. Образец с данными автора — «**После (с фактами автора):**». Показывает,
     каким станет текст, когда автор подставит свою конкретику.
     Сам скилл такие факты не выдумывает, а запрашивает у автора.

Запуск:
  python3 scripts/check_examples.py
  python3 scripts/check_examples.py --selftest

Только стандартная библиотека.
"""
import argparse
import glob
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGETS = ["SKILL.md", "README.md", "README.en.md"]

NUMWORDS = set("""
один одна одно одного одним два две двух двумя три трех тремя четыре четырех
пять пяти шесть шести семь семи восемь восьми девять девяти десять десяти
одиннадцать двенадцать двадцать тридцать сорок пятьдесят сто ста
тысяча тысячи тысяч миллион миллиона миллиард
первый первая второй вторая третий третья четвертый пятый
вдвое втрое вчетверо половина треть четверть
""".split())

# Заглавные нарицательные, которые не являются проверяемым фактом.
NOT_A_FACT = set("""
Вселенной Вселенная Земля Земли Интернет Интернете
""".split())

WORD_RX = re.compile(r"[а-яё]+")
NUM_RX = re.compile(r"\d+")
CAP_RX = re.compile(r"\b([А-ЯЁ][а-яё]{2,}|[A-Z][A-Za-z]+|[A-Z]{2,})\b")
SENT_END = ".!?…:—–«»\"'()[]—"


def _strip_markup(text):
    """Снимает цитатные префиксы и инлайн-разметку."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*>\s?", "", line)
        line = re.sub(r"^\s*[-*]\s+", "", line)
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"`[^`]*`", " ", out)
    out = out.replace("**", "").replace("__", "")
    return out


def _sentence_starts(text):
    """Позиции первых слов предложений — там заглавная не значит имя."""
    starts = set()
    pending = True
    for i, ch in enumerate(text):
        if pending and (ch.isalpha() or ch.isdigit()):
            starts.add(i)
            pending = False
        elif ch in ".!?\n":
            pending = True
    return starts


def extract_facts(text):
    """Извлекает проверяемые факты: числа, числительные, имена собственные."""
    clean = _strip_markup(text)
    facts = set()
    for m in NUM_RX.finditer(clean):
        facts.add(m.group(0))
    low = clean.lower().replace("ё", "е")
    for w in WORD_RX.findall(low):
        if w in NUMWORDS or w.replace("е", "ё") in NUMWORDS:
            facts.add(w)
    starts = _sentence_starts(clean)
    for m in CAP_RX.finditer(clean):
        if m.start() in starts:
            continue
        if m.group(1) in NOT_A_FACT:
            continue
        facts.add(m.group(1))
    return facts


def new_facts(before, after):
    """Факты, появившиеся в «После» и отсутствующие в «До»."""
    b_low = _strip_markup(before).lower().replace("ё", "е")
    out = set()
    for f in extract_facts(after) - extract_facts(before):
        if f.lower().replace("ё", "е") in b_low:
            continue
        out.add(f)
    return sorted(out)


PAIR_RX = re.compile(
    r"\*\*(?:До|Before):\*\*(?P<before>.*?)\n\s*\n"
    r"\*\*(?:После|After)(?P<label>[^:*]*):\*\*(?P<after>.*?)(?=\n\s*\n|\Z)",
    re.S,
)

AUTHOR_LABELS = ("с фактами автора", "author")


def check_text(text, path="<text>"):
    errors, warnings, stats = [], [], {"pairs": 0, "edit": 0, "authored": 0}
    for m in PAIR_RX.finditer(text):
        stats["pairs"] += 1
        before = m.group("before").strip()
        after = m.group("after").strip()
        label = (m.group("label") or "").strip().lower()
        line = text[: m.start()].count("\n") + 1
        authored = any(k in label for k in AUTHOR_LABELS)
        added = new_facts(before, after)
        if authored:
            stats["authored"] += 1
            if not added:
                warnings.append(
                    "%s:%d: пометка «с фактами автора» излишня: новых фактов нет" % (path, line)
                )
        else:
            stats["edit"] += 1
            if added:
                errors.append(
                    "%s:%d: в «После» появились факты, которых нет в «До»: %s"
                    % (path, line, ", ".join(added))
                )
    return errors, warnings, stats


def selftest():
    ok = True
    clean = "**До:** Галерея выступает в качестве пространства.\n\n**После:** Галерея — это пространство.\n"
    dirty = "**До:** Результаты улучшаются.\n\n**После:** Результаты улучшились на 30%.\n"
    labeled = "**До:** Результаты улучшаются.\n\n**После (с фактами автора):** Результаты улучшились на 30%.\n"
    sent = "**До:** город красив.\n\n**После:** Город красив.\n"
    cases = [
        ("чистая пара проходит", clean, 0),
        ("дописанный факт ловится", dirty, 1),
        ("помеченная пара разрешена", labeled, 0),
        ("заглавная в начале предложения не факт", sent, 0),
    ]
    for name, text, expected in cases:
        errs, _, _ = check_text(text)
        got = len(errs)
        mark = "OK  " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print("[%s] %s (ошибок: %d, ожидалось: %d)" % (mark, name, got, expected))
    print("Самопроверка: " + ("пройдена" if ok else "ПРОВАЛЕНА"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Гейт честности пар До/После")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    files = args.files
    if not files:
        files = [os.path.join(ROOT, f) for f in TARGETS if os.path.exists(os.path.join(ROOT, f))]
        files += sorted(glob.glob(os.path.join(ROOT, "references", "*.md")))

    all_err, all_warn = [], []
    total = {"pairs": 0, "edit": 0, "authored": 0}
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        rel = os.path.relpath(path, ROOT)
        errs, warns, stats = check_text(text, rel)
        all_err += errs
        all_warn += warns
        for k in total:
            total[k] += stats[k]

    for w in all_warn:
        print("[WARN] " + w)
    for e in all_err:
        print("[FAIL] " + e)
    print(
        "Пар «До/После»: %d (правка: %d, с фактами автора: %d)"
        % (total["pairs"], total["edit"], total["authored"])
    )
    if all_err:
        print("ГЕЙТ ЧЕСТНОСТИ ПРИМЕРОВ: провален (%d)" % len(all_err))
        return 1
    print("ГЕЙТ ЧЕСТНОСТИ ПРИМЕРОВ: пройден")
    return 0


if __name__ == "__main__":
    sys.exit(main())
