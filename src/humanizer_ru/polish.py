#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""polish.py — типографическая нормализация русского текста (главный режим).

Единственный путь проекта с доказанными числами: типографическая чистка
снимает верхний слой «машинности» так, что детерминированные линтеры
перестают обвинять текст (интервенция на панелях двух чужих линтеров).
Числа интервенции живут в реестре фактов прогона и здесь не цитируются.

Трансформация T (и только она): тире→дефис, ёлочки→прямые кавычки,
многоточие, невидимые символы и NBSP, снятие **/__ и хэшей заголовков,
переносы строк к LF. Лексика и списки нетронуты.

Два инварианта (оба проверяются гейтом и самопроверкой):
  1. Идемпотентность: polish(polish(x)) == polish(x).
  2. Ноль смысловых правок: последовательность букв и цифр до и после
     совпадает дословно — трансформация не удаляет, не добавляет и не
     переставляет ни одной буквы (слова и числа содержимого целы;
     нулевые символы внутри слова лишь склеивают разорванное слово).

Доля отказов 0: polish не отказывает ни на каком входе; текст без
типографических дефектов возвращается неизменным (пустой диф — норма).

Режимы:
    python3 scripts/polish.py ФАЙЛ...           # результат в stdout
    python3 scripts/polish.py --diff ФАЙЛ...    # унифицированный диф
    python3 scripts/polish.py --in-place ФАЙЛ...# запись на место (+ .bak)
    python3 scripts/polish.py --dry-run --in-place ФАЙЛ...  # что изменится
    python3 scripts/polish.py --json ФАЙЛ...    # машиночитаемый отчёт
    python3 scripts/polish.py --gate КАТАЛОГ    # инварианты по *.md/*.txt
    python3 scripts/polish.py --selftest        # самопроверка с негативами

Коды: 0 — успех/инварианты целы; 1 — нарушение инварианта или диф-гейт;
2 — вход не читается. Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

# Невидимые символы: пробельные -> обычный пробел, нулевой ширины -> удалить.
_INVIS = {
    "\u00a0": " ",   # неразрывный пробел
    "\u2009": " ",   # узкий пробел
    "\u202f": " ",   # узкий неразрывный пробел
    "\u200b": "",    # нулевая ширина, пробел
    "\u200c": "",    # разъединитель нулевой ширины
    "\u200d": "",    # соединитель нулевой ширины
    "\u2060": "",    # межсловный соединитель
    "\ufeff": "",    # BOM / неразрывный пробел нулевой ширины
    "\u00ad": "",    # мягкий перенос
}
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)
_HEADING = re.compile(r"(?m)^(?:#{1,6}[ \t]+)+")
_WORD = re.compile(r"[0-9A-Za-z\u0410-\u042f\u0430-\u044f\u0401\u0451]+")
_LETTERS = re.compile(r"[0-9A-Za-z\u0410-\u042f\u0430-\u044f\u0401\u0451]")
_FIXPOINT_ROUNDS = 20


def words_of(text: str) -> list[str]:
    """Последовательность слов (буквы/цифры) — для отчётов и дифов."""
    return _WORD.findall(text)


def letters_of(text: str) -> str:
    """Последовательность букв и цифр — канва инварианта №2."""
    return "".join(_LETTERS.findall(text))


def _polish_once(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    for ch, repl in _INVIS.items():
        t = t.replace(ch, repl)
    t = t.replace("\u2014", "-").replace("\u2013", "-")  # тире: длинное/короткое
    t = t.replace("\u00ab", '"').replace("\u00bb", '"')  # ёлочки -> прямые
    t = t.replace("\u2026", "...")                        # многоточие
    t = _BOLD.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _HEADING.sub("", t)
    return t


def polish(text: str) -> str:
    """Трансформация T до неподвижной точки.

    Итерация до фикспойнта обязательна: снятие маркера может обнажить
    следующий (жирный под заголовком, вложенные пары) — однократная замена
    на таких входах неидемпотентна. Фикспойнт гарантирует инвариант №1 по
    построению; буквы и цифры ни одна замена не трогает (инвариант №2).
    """
    t = text
    for _ in range(_FIXPOINT_ROUNDS):
        nxt = _polish_once(t)
        if nxt == t:
            return t
        t = nxt
    return t


def invariant_problems(original: str, cleaned: str) -> list[str]:
    """Проверка пары (до, после): список нарушений инвариантов."""
    problems = []
    if polish(cleaned) != cleaned:
        problems.append("идемпотентность: повторный проход меняет текст")
    if letters_of(original) != letters_of(cleaned):
        problems.append("смысловая правка: буквы/цифры изменены")
    return problems


# ------------------------------------------------------------------ selftest

def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    src = ("# Заголовок раздела\n\n"
           "**Жирная мысль** о длинном — тире и «ёлочках»…\n"
           "Второй абзац с неразрывным\u00a0пробелом и нулевым\u200bсловом.\n")
    out = polish(src)
    case("тире заменено на дефис", "\u2014" not in out and "-" in out)
    case("ёлочки заменены на прямые", "\u00ab" not in out and '"' in out)
    case("многоточие заменено", "\u2026" not in out and "..." in out)
    case("жирный снят", "**" not in out and "Жирная мысль" in out)
    case("хэш заголовка снят", not out.startswith("#") and "Заголовок" in out)
    case("NBSP заменён на пробел", "\u00a0" not in out)
    case("нулевой ширины удалён", "\u200b" not in out and "нулевымсловом" in out)
    case("идемпотентность на образце", polish(out) == out)
    case("буквы и цифры сохранены дословно", letters_of(src) == letters_of(out))
    case("инварианты без нарушений", invariant_problems(src, out) == [])

    # Коварные вложения: снятие маркера обнажает следующий маркер.
    nested = "## **# Заголовок**\n"
    nout = polish(nested)
    case("идемпотентность при вложении (жирный под заголовком)",
         polish(nout) == nout)
    case("буквы целы при вложении", letters_of(nested) == letters_of(nout))
    nested2 = "**__двойное__**"
    case("идемпотентность при вложенных парах", polish(polish(nested2)) == polish(nested2))

    # Концы строк: CRLF и одиночный CR приводятся к LF.
    crlf = "Строка один — с тире.\r\nСтрока два…\rТретья.\n"
    cout = polish(crlf)
    case("переносы строк к LF", "\r" not in cout)
    case("буквы целы при нормализации концов", letters_of(crlf) == letters_of(cout))
    case("идемпотентность после нормализации концов", polish(cout) == cout)

    # Негативы: гейт обязан уметь падать.
    case("ловит смысловую правку (вставка слова)",
         "смысловая правка" in " ".join(invariant_problems(src, out + " Лишнее")))
    case("ловит смысловую правку (удаление слова)",
         "смысловая правка" in " ".join(invariant_problems(src, "Заголовок")))
    broken = out.replace("-", "\u2014")  # обратная замена ломает идемпотентность
    case("ловит нарушение идемпотентности",
         "идемпотентность" in " ".join(invariant_problems(broken, broken)))

    # Текст без дефектов возвращается неизменным (пустой диф — норма, не отказ).
    clean = "Обычный текст без дефектов. Второй абзац.\n"
    case("чистый текст неизменен (доля отказов 0)", polish(clean) == clean)

    print("САМОПРОВЕРКА polish: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


# --------------------------------------------------------------------- gate

def gate(paths: list[str]) -> int:
    """Инварианты по файлам (*.md, *.txt). Падает при нарушении."""
    bad = 0
    checked = 0
    for path in paths:
        if os.path.isdir(path):
            for dirpath, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.endswith((".md", ".txt")):
                        bad += _gate_file(os.path.join(dirpath, name))
                        checked += 1
        else:
            bad += _gate_file(path)
            checked += 1
    if bad:
        print("ПОЛИРОВКА: нарушений инвариантов %d (файлов проверено %d)"
              % (bad, checked))
        return 1
    print("ПОЛИРОВКА: инварианты целы на %d файлах" % checked)
    return 0


def _gate_file(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc))
        return 1
    cleaned = polish(text)
    problems = invariant_problems(text, cleaned)
    for p in problems:
        print("НАРУШЕНИЕ %s: %s" % (path, p))
    return 1 if problems else 0


# ---------------------------------------------------------------------- CLI

def _diff_text(before: str, after: str, label: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=label + " (до)", tofile=label + " (после)")
    return "".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Типографическая нормализация русского текста.")
    ap.add_argument("files", nargs="*", help="файлы для обработки")
    ap.add_argument("--diff", action="store_true",
                    help="показать унифицированный диф до/после")
    ap.add_argument("--in-place", action="store_true",
                    help="записать результат на место (с копией .bak)")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать изменения, не писать")
    ap.add_argument("--json", action="store_true",
                    help="машиночитаемый отчёт (схема 1)")
    ap.add_argument("--gate", metavar="ПУТЬ",
                    help="режим гейта: проверить инварианты по файлам/каталогу")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка с негативными кейсами")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.gate:
        return gate([args.gate])
    if not args.files:
        print("нет файлов; справка: --help, самопроверка: --selftest",
              file=sys.stderr)
        return 2

    report = []
    rc = 0
    for path in args.files:
        try:
            with open(path, encoding="utf-8") as fh:
                before = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc), file=sys.stderr)
            rc = 2
            continue
        after = polish(before)
        problems = invariant_problems(before, after)
        if problems:
            rc = 1
        changed = after != before
        entry = {
            "file": path,
            "changed": changed,
            "chars_before": len(before),
            "chars_after": len(after),
            "invariants": problems,
        }
        if args.json:
            report.append(entry)
        elif args.diff:
            sys.stdout.write(_diff_text(before, after, path))
        elif args.in_place:
            if args.dry_run:
                print(("ИЗМЕНИТСЯ " if changed else "БЕЗ ИЗМЕНЕНИЙ ") + path)
            else:
                if changed:
                    with open(path + ".bak", "w", encoding="utf-8",
                              newline="") as fh:
                        fh.write(before)
                    with open(path, "w", encoding="utf-8", newline="") as fh:
                        fh.write(after)
                print(("ЗАПИСАНО " if changed else "БЕЗ ИЗМЕНЕНИЙ ") + path)
        else:
            sys.stdout.write(after)
    if args.json:
        print(json.dumps({"tool": "humanizer-polish", "schema": 1, "files": report},
                         ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
