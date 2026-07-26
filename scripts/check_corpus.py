#!/usr/bin/env python3
"""check_corpus.py — регрессионная проверка корпусов валидации.

Гарантирует, что:
- human corpus (research/validation/human/*.txt) не содержит совпадений regex;
- AI raw corpus (research/raw/**/*.txt) содержит только известное ожидаемое
  совпадение (BOM в начале файла Le Chat), не артефакт модели;
- boundary controls (research/validation/boundary/*.txt) совпадают ровно с
  заявленными ожиданиями (документирует границы ложных срабатываний).

Запуск:  python3 scripts/check_corpus.py [--selftest]
Код возврата 0 — корпус в норме, 1 — регрессия (ложное срабатывание или
пропуск ожидаемого совпадения).
Только стандартная библиотека.
"""
import os
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

try:
    from check_markers import CASES, _inside_backticks, _console_text
except Exception:  # noqa: BLE001
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from check_markers import CASES, _inside_backticks, _console_text

import re

HUMAN_DIR = "research/validation/human"
RAW_DIRS = ("research/raw/gigachat", "research/raw/alisa", "research/raw/le-chat")
BOUNDARY_DIR = "research/validation/boundary"

# Ожидаемые совпадения в boundary-корпусе: файл -> множество имён case.
# Документирует заведомо известные пересечения.
# emoji-zwj.txt: с версии 3.7.0 выражение zero_width исключает ZWJ внутри
# эмодзи-контекста, поэтому составные эмодзи больше не совпадают. Файл остаётся
# в корпусе как страж: любое совпадение здесь означает возврат ложного
# срабатывания на семейных эмодзи и флагах.
BOUNDARY_EXPECTED = {
    "emoji-zwj.txt": set(),
}

# Ожидаемое совпадение в raw-корпусе: BOM в начале файла Le Chat.
# Ключ — «каталог/имя», а не одно имя: файлы с одинаковыми именами лежат в
# разных каталогах моделей (01-слепая-печать.txt есть и в gigachat, и в alisa),
# и разрешение по одному имени распространялось бы на все одноимённые файлы.
RAW_EXPECTED = {
    "le-chat/01-fast-канберра.txt": ("zero_width",),  # U+FEFF BOM
}


def _scan_file(path, compiled):
    hits = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        return [(0, "read-error", str(exc))]
    for lineno, line in enumerate(lines, 1):
        for name, rx in compiled.items():
            for m in rx.finditer(line):
                if _inside_backticks(line, m.start(), m.end()):
                    continue
                hits.append((lineno, name, _console_text(line.strip()[:80])))
    return hits


def run(human_dir=HUMAN_DIR, raw_dirs=RAW_DIRS, boundary_dir=BOUNDARY_DIR):
    compiled = {name: re.compile(case[0]) for name, case in CASES.items()}
    fails = []

    # Без корпусов проверять нечего, а прежний код печатал «ОК» и возвращал 0:
    # вне полного клона (в релизном архиве research/ нет) это выглядело как
    # успешная проверка. Отказ инструмента — код 2, отдельно от регрессии (1).
    present = [d for d in ((human_dir, boundary_dir) + tuple(raw_dirs)) if os.path.isdir(d)]
    if not present:
        print("[СБОЙ] корпусов нет ни в одном из каталогов: %s"
              % ", ".join((human_dir, boundary_dir) + tuple(raw_dirs)))
        print("CORPUS: валидатор работает только в полном клоне репозитория "
              "(в релизном архиве каталога research/ нет).")
        return 2

    # Human corpus: 0 совпадений.
    if os.path.isdir(human_dir):
        for fn in sorted(os.listdir(human_dir)):
            if not fn.endswith(".txt"):
                continue
            hits = _scan_file(os.path.join(human_dir, fn), compiled)
            if hits:
                fails.append("%s: ложное срабатывание на human-корпусе: %s"
                             % (fn, hits[:3]))

    # Raw corpus: только ожидаемые совпадения.
    seen_expected = set()
    for d in raw_dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".txt"):
                continue
            hits = _scan_file(os.path.join(d, fn), compiled)
            key = "%s/%s" % (os.path.basename(d.rstrip("/\\")), fn)
            allowed = RAW_EXPECTED.get(key, ())
            allowed_names = set(allowed)
            actual_names = {h[1] for h in hits}
            unexpected = actual_names - allowed_names
            if unexpected:
                fails.append("%s/%s: неожиданное совпадение в raw-корпусе: %s"
                             % (d, fn, unexpected))
            if allowed_names:
                seen_expected.add(key)

    # Boundary corpus: ровно заявленные совпадения.
    if os.path.isdir(boundary_dir):
        for fn in sorted(os.listdir(boundary_dir)):
            if not fn.endswith(".txt"):
                continue
            hits = _scan_file(os.path.join(boundary_dir, fn), compiled)
            expected = BOUNDARY_EXPECTED.get(fn, set())
            actual = {h[1] for h in hits}
            if actual != expected:
                fails.append("%s: boundary mismatch — ожидалось %s, найдено %s"
                             % (fn, expected, actual))

    if not seen_expected and all(os.path.isdir(d) for d in raw_dirs):
        fails.append("raw-корпус: ни одного ожидаемого BOM-совпадения — проверьте corpus")

    if fails:
        for f in fails:
            print("[FAIL] " + f)
        print("CORPUS: регрессия — %d проблем." % len(fails))
        return 1
    print("CORPUS: human 0 совпадений, raw только BOM, boundary совпал. ОК.")
    return 0


def selftest():
    import tempfile
    tmp = tempfile.mkdtemp()
    human = os.path.join(tmp, "human"); os.makedirs(human)
    boundary = os.path.join(tmp, "boundary"); os.makedirs(boundary)
    raw = os.path.join(tmp, "raw", "le-chat"); os.makedirs(raw)
    with open(os.path.join(human, "01.txt"), "w", encoding="utf-8") as f:
        f.write("обычный человеческий текст без маркеров\n")
    with open(os.path.join(boundary, "emoji-zwj.txt"), "w", encoding="utf-8") as f:
        f.write("семья: \U0001F468\u200d\U0001F469\u200d\U0001F466\n")
    with open(os.path.join(raw, "01-fast-канберра.txt"), "w", encoding="utf-8") as f:
        f.write("\ufeffответ модели\n")
    checks = []
    rc = run(human_dir=human, raw_dirs=(raw,), boundary_dir=boundary)
    checks.append(("чистый human + ожиданный raw BOM + ZWJ-граница -> OK", rc == 0))
    with open(os.path.join(human, "02.txt"), "w", encoding="utf-8") as f:
        f.write("текст с turn0search0 маркером\n")
    rc = run(human_dir=human, raw_dirs=(raw,), boundary_dir=boundary)
    checks.append(("human с маркером -> FAIL", rc == 1))
    os.unlink(os.path.join(human, "02.txt"))

    # Прежний кейс писал в boundary файл без маркеров: ожидалось пусто, найдено
    # пусто — проверка возвращала 0 и ничего не доказывала. Настоящий негатив —
    # boundary-файл с маркером, которого в BOUNDARY_EXPECTED нет.
    extra = os.path.join(boundary, "extra.txt")
    with open(extra, "w", encoding="utf-8") as f:
        f.write("граничный файл с turn0search0 внутри\n")
    rc = run(human_dir=human, raw_dirs=(raw,), boundary_dir=boundary)
    checks.append(("boundary с незаявленным совпадением -> FAIL", rc == 1))
    os.unlink(extra)

    # Ключ RAW_EXPECTED учитывает каталог: одноимённый файл в другом каталоге
    # модели не наследует разрешение на BOM.
    other_raw = os.path.join(tmp, "raw", "gigachat")
    os.makedirs(other_raw)
    with open(os.path.join(other_raw, "01-fast-канберра.txt"), "w", encoding="utf-8") as f:
        f.write("﻿тот же файл, но другая модель\n")
    rc = run(human_dir=human, raw_dirs=(raw, other_raw), boundary_dir=boundary)
    checks.append(("одноимённый файл в другом каталоге не наследует разрешение -> FAIL",
                   rc == 1))

    # Полное отсутствие корпусов — громкий отказ инструмента (код 2).
    empty = os.path.join(tmp, "пусто")
    rc = run(human_dir=os.path.join(empty, "human"),
             raw_dirs=(os.path.join(empty, "raw"),),
             boundary_dir=os.path.join(empty, "boundary"))
    checks.append(("корпусов нет вовсе -> код 2, а не молчаливый успех", rc == 2))

    fails = [n for n, p in checks if not p]
    for n, p in checks:
        print(("PASS: " if p else "FAIL: ") + n)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(run())
