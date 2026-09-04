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

ЧЕСТНАЯ ГРАНИЦА: T снимает машинный слой типографики и для этого
выравнивает русскую типографику и Markdown в плоский текст — не
запускайте polish на Markdown и разметке без --preserve-markup: он снимет
##, **, ёлочки, тире и многоточие. Постановку ёлочек и тире по русской
норме делает агентный слой (SKILL.md), а не этот инструмент;
--preserve-markup оставляет разметку и русскую типографику, снимая
только невидимые символы, NBSP и нормализуя переносы строк.

Третий режим — --typographic (публикационный): приводит текст к русской
публикационной типографике БЕЗ снятия заголовков и выделения: парные
прямые кавычки -> ёлочки, «...» -> единый символ многоточия, невидимые
символы и NBSP снимаются, переносы строк к LF; содержимое fenced-блоков
(``` и ~~~) и инлайн-бэктиков не трогается (код есть код). Тире режим не
ставит: выбор тире — решение агентного слоя. Режим идемпотентен и
применим к собственным публичным документам проекта (гейт
scripts/check_polish_modes.py требует changed:false на README.md,
SKILL.md, CONTRIBUTING.md, llms.txt).

Два инварианта (оба проверяются гейтом и самопроверкой):
  1. Идемпотентность: polish(polish(x)) == polish(x).
  2. Ноль смысловых правок: последовательность букв и цифр до и после
     совпадает дословно — трансформация не удаляет, не добавляет и не
     переставляет ни одной буквы (слова и числа содержимого целы;
     нулевые символы внутри слова лишь склеивают разорванное слово).

Доля отказов 0: polish не отказывает ни на каком входе; текст без
типографических дефектов возвращается неизменным (пустой диф — норма).
Пустой и не-русский вход помечаются «вне области» (scope_note): механика
типографики отрабатывает, но область скилла — русский текст.

Режимы:
    python3 scripts/polish.py ФАЙЛ...           # результат в stdout («-» = stdin)
    python3 scripts/polish.py --preserve-markup ФАЙЛ...  # без снятия разметки
    python3 scripts/polish.py --typographic ФАЙЛ...  # публикационная типографика
    python3 scripts/polish.py --diff ФАЙЛ...    # унифицированный диф
    python3 scripts/polish.py --in-place ФАЙЛ...# запись на место (+ .bak)
    python3 scripts/polish.py --dry-run --in-place ФАЙЛ...  # что изменится
    python3 scripts/polish.py --json ФАЙЛ...    # машиночитаемый отчёт
    python3 scripts/polish.py --gate КАТАЛОГ    # инварианты по *.md/*.txt
    python3 scripts/polish.py --selftest        # самопроверка с негативами

Коды: 0 — успех/инварианты целы; 1 — нарушение инварианта или диф-гейт;
2 — вход не читается (с --json конверт ошибки печатается в stdout).
Репозиторий: https://github.com/Vladimir-Human/humanizer-ru
Вход для агентов: llms.txt; машинный контракт: contract.v1.json.
Только стандартная библиотека.
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
# Публикационный режим: парные прямые кавычки в пределах одной строки.
_PAIR_QUOTES = re.compile(r'"([^"\n]*)"')
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FENCE_CLOSE_CH = {"`": re.compile(r"^ {0,3}(`+)\s*$"),
                   "~": re.compile(r"^ {0,3}(~+)\s*$")}


def words_of(text: str) -> list[str]:
    """Последовательность слов (буквы/цифры) — для отчётов и дифов."""
    return _WORD.findall(text)


def letters_of(text: str) -> str:
    """Последовательность букв и цифр — канва инварианта №2."""
    return "".join(_LETTERS.findall(text))


def _polish_once(text: str, preserve_markup: bool = False) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    for ch, repl in _INVIS.items():
        t = t.replace(ch, repl)
    if preserve_markup:
        # Режим сохранения разметки: только невидимые символы/NBSP и LF.
        # Ёлочки, тире, многоточия, ** и ## остаются — русская типографика
        # и Markdown-разметка не являются машинным слоем.
        return t
    t = t.replace("\u2014", "-").replace("\u2013", "-")  # тире: длинное/короткое
    t = t.replace("\u00ab", '"').replace("\u00bb", '"')  # ёлочки -> прямые
    t = t.replace("\u2026", "...")                        # многоточие
    t = _BOLD.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _HEADING.sub("", t)
    return t


def polish(text: str, preserve_markup: bool = False,
           typographic: bool = False) -> str:
    """Трансформация T до неподвижной точки.

    Итерация до фикспойнта обязательна: снятие маркера может обнажить
    следующий (жирный под заголовком, вложенные пары) — однократная замена
    на таких входах неидемпотентна. Фикспойнт гарантирует инвариант №1 по
    построению; буквы и цифры ни одна замена не трогает (инвариант №2).
    preserve_markup=True — снять только машинный слой (невидимые символы,
    NBSP, переносы строк), сохранив разметку и русскую типографику.
    typographic=True — публикационный режим: русская типографика
    (ёлочки из парных прямых кавычек, единый символ многоточия) БЕЗ снятия
    разметки; fenced-блоки и инлайн-бэктики не трогаются; при сочетании
    флагов typographic имеет приоритет.
    """
    t = text
    for _ in range(_FIXPOINT_ROUNDS):
        if typographic:
            nxt = _typographic_once(t)
        else:
            nxt = _polish_once(t, preserve_markup)
        if nxt == t:
            return t
        t = nxt
    return t


def _fenced_mask(lines: list) -> set:
    """Индексы строк внутри ЗАКРЫТЫХ блоков ``` и ~~~ (отступ до трёх).

    Незакрытый забор не маскирует остаток файла — та же конвенция, что в
    check_markers/scan_soft_signals: документация без закрытия не прячет
    текст от трансформации.
    """
    inside = set()
    i = 0
    n = len(lines)
    while i < n:
        m = _FENCE_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        ch = m.group(1)[0]
        flen = len(m.group(1))
        close_rx = _FENCE_CLOSE_CH[ch]
        j = i + 1
        closed_at = -1
        while j < n:
            m2 = close_rx.match(lines[j])
            if m2 and len(m2.group(1)) >= flen:
                closed_at = j
                break
            j += 1
        if closed_at >= 0:
            for k in range(i, closed_at + 1):
                inside.add(k)
            i = closed_at + 1
        else:
            i += 1
    return inside


def _outside_backtick_segments(line: str) -> list:
    """Интервалы (start, end) строки вне `инлайн-бэктиков`."""
    segs = []
    start = 0
    in_bt = False
    for idx, ch in enumerate(line):
        if ch != "`":
            continue
        if not in_bt:
            segs.append((start, idx))
            in_bt = True
        else:
            in_bt = False
            start = idx + 1
    if not in_bt:
        segs.append((start, len(line)))
    return segs


def _typographic_once(text: str) -> str:
    """Один проход публикационного режима (без снятия разметки).

    Трансформации применяются ТОЛЬКО к прозе вне fenced-блоков, YAML-
    frontmatter и инлайн-бэктиков: код и документированные примеры (в том
    числе невидимые символы внутри них) не трогаются. Невидимые символы и
    NBSP в прозе снимаются, переносы строк нормализуются везде.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = t.split("\n")
    fenced = _fenced_mask(lines)
    # YAML-frontmatter (--- ... --- в начале файла) — данные, не проза.
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            fenced.add(j)
            if lines[j].strip() == "---":
                break
    out = []
    for i, line in enumerate(lines):
        if i in fenced:
            out.append(line)
            continue
        if ("`" not in line and '"' not in line and "..." not in line
                and not any(ch in line for ch in _INVIS)):
            out.append(line)
            continue
        pieces = []
        last = 0
        for s, e in _outside_backtick_segments(line):
            pieces.append(line[last:s])
            seg = line[s:e]
            for ch, repl in _INVIS.items():
                seg = seg.replace(ch, repl)
            seg = _PAIR_QUOTES.sub("\u00ab\\1\u00bb", seg)
            seg = seg.replace("...", "\u2026")
            pieces.append(seg)
            last = e
        pieces.append(line[last:])
        out.append("".join(pieces))
    return "\n".join(out)


def _cyrillic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "\u0400" <= c <= "\u04ff")
    return cyr / len(letters)


def scope_note(text: str) -> str:
    """Пометка «вне области»: пустой и не-русский вход — вне домена скилла.

    Градуированный ответ остаётся непустым (контракт): механика типографики
    отрабатывает на любом входе, но честный статус входа агент обязан видеть.
    """
    if not text.strip():
        return "вне области: пустой вход"
    if _cyrillic_share(text) < 0.1:
        return "вне области: текст не на русском (область скилла — русский текст)"
    return ""


def invariant_problems(original: str, cleaned: str,
                       preserve_markup: bool = False,
                       typographic: bool = False) -> list[str]:
    """Проверка пары (до, после): список нарушений инвариантов."""
    problems = []
    if polish(cleaned, preserve_markup, typographic) != cleaned:
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

    # --preserve-markup: разметка и русская типографика сохраняются,
    # машинный слой (невидимые символы) снимается.
    pm = polish("## Заголовок — «цитата» **жирный**\u200b\n", preserve_markup=True)
    case("preserve-markup сохраняет ## заголовка", pm.startswith("## "))
    case("preserve-markup сохраняет ёлочки и тире",
         "\u00ab" in pm and "\u2014" in pm)
    case("preserve-markup сохраняет **жирный**", "**" in pm)
    case("preserve-markup снимает нулевой ширины", "\u200b" not in pm)
    case("preserve-markup идемпотентен", polish(pm, True) == pm)

    # --typographic: публикационная типографика без снятия разметки;
    # fenced-блоки и инлайн-бэктики не трогает.
    tsrc = 'Проза "цитата" и троеточие... вне кода.\n'
    tout = polish(tsrc, typographic=True)
    case("typographic: прямые кавычки -> ёлочки",
         "\u00ab" in tout and '"' not in tout)
    case("typographic: ... -> единый символ", "\u2026" in tout and "..." not in tout)
    case("typographic: идемпотентен", polish(tout, typographic=True) == tout)
    case("typographic: буквы и цифры дословно", letters_of(tsrc) == letters_of(tout))
    case("typographic: инварианты без нарушений",
         invariant_problems(tsrc, tout, typographic=True) == [])
    fsrc = 'Проза "цель".\n```python\nx = "code..."\n```\nЕщё "проза"...\n'
    fout = polish(fsrc, typographic=True)
    case("typographic: fenced-код не тронут", 'x = "code..."' in fout)
    case("typographic: проза вне забора приведена", fout.count("\u00ab") == 2)
    bsrc = 'Вне `"кода"` и "проза".\n'
    bout = polish(bsrc, typographic=True)
    case("typographic: инлайн-бэктики не тронуты", '`"кода"`' in bout)
    case("typographic: кавычки вне бэктиков приведены", "\u00abпроза\u00bb" in bout)
    case("typographic: уже приведённый текст неизменен",
         polish("Обычный «текст» с тире — и многоточием…\n",
                typographic=True) == "Обычный «текст» с тире — и многоточием…\n")
    case("typographic: невидимые внутри бэктиков не трогает",
         "`a\u200bb`" in polish("x `a\u200bb` \"y\"...\n", typographic=True))
    case("typographic: невидимые в прозе снимает",
         "\u200b" not in polish("Слово\u200b и \"цитата\".\n", typographic=True))
    fm = polish('---\nname: "x"\n---\nПроза "y"...\n', typographic=True)
    case("typographic: YAML-frontmatter не трогает",
         fm.splitlines()[1] == 'name: "x"' and "\u00aby\u00bb" in fm)

    # Пометка «вне области»: пустой и не-русский вход (градуированный ответ
    # остаётся непустым, но статус входа честный).
    case("пустой вход — вне области", scope_note("") != "" and scope_note("  \n") != "")
    case("английский текст — вне области",
         scope_note("Plain English text without any Russian.") != "")
    case("русский текст — в области", scope_note("Обычный русский текст.") == "")

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
        description="Типографическая нормализация русского текста. "
                    "Не запускать на Markdown и разметке: снимает ##, **, "
                    "ёлочки, тире, многоточие; режим сохранения разметки — "
                    "--preserve-markup.",
        epilog="Репозиторий: https://github.com/Vladimir-Human/humanizer-ru\n"
               "Вход для агентов: llms.txt; машинный контракт: contract.v1.json",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*",
                    help="файлы для обработки; «-» читает stdin (UTF-8)")
    ap.add_argument("--diff", action="store_true",
                    help="показать унифицированный диф до/после")
    ap.add_argument("--in-place", action="store_true",
                    help="записать результат на место (с копией .bak)")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать изменения, не писать")
    ap.add_argument("--preserve-markup", action="store_true",
                    help="снимать только невидимые символы/NBSP и "
                         "нормализовать переносы строк; Markdown и русская "
                         "типографика (ёлочки, тире) сохраняются")
    ap.add_argument("--remove", action="store_true",
                    help="явный алиас дефолтного режима: снятие "
                         "машинного слоя (невидимые, разметка); "
                         "поведение идентично вызову без флагов")
    ap.add_argument("--typographic", action="store_true",
                    help="публикационный режим: парные прямые кавычки -> "
                         "ёлочки, «...» -> единый символ многоточия, "
                         "невидимые символы снимаются; разметка, fenced-блоки "
                         "и инлайн-код не трогаются; приоритет над "
                         "--preserve-markup")
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
    errors = []
    rc = 0
    for path in args.files:
        if path == "-" and args.in_place:
            msg = "--in-place неприменим к stdin"
            print("НЕ ЧИТАЕТСЯ -: " + msg, file=sys.stderr)
            errors.append({"file": "<stdin>", "error": msg})
            rc = 2
            continue
        try:
            if path == "-":
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
                before = sys.stdin.read()
            else:
                with open(path, encoding="utf-8") as fh:
                    before = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc), file=sys.stderr)
            errors.append({"file": path, "error": repr(exc)})
            rc = 2
            continue
        after = polish(before, args.preserve_markup, args.typographic)
        problems = invariant_problems(before, after, args.preserve_markup,
                                      args.typographic)
        if problems:
            rc = 1
        changed = after != before
        note = scope_note(before)
        entry = {
            "file": "<stdin>" if path == "-" else path,
            "changed": changed,
            "chars_before": len(before),
            "chars_after": len(after),
            "preserve_markup": bool(args.preserve_markup),
            "typographic": bool(args.typographic),
            "invariants": problems,
        }
        if note:
            entry["status"] = "out-of-scope"
            entry["scope_note"] = note
            print("%s: %s" % (path, note), file=sys.stderr)
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
            # Завершающий перевод строки обязателен: следующий промпт
            # консоли не должен прилипать к тексту.
            sys.stdout.write(after if not after or after.endswith("\n")
                             else after + "\n")
    if args.json:
        envelope = {"tool": "humanizer-polish", "schema": 1,
                    "files": report + errors}
        if rc == 2:
            envelope["error"] = "вход не читается (код 2)"
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
