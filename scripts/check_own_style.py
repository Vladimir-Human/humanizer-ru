#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Порог мягких признаков на собственные файлы поставки.

Считает мягкие признаки счётчиком проекта со снятой разметкой
(`count_style_markers.py --skip-markup`) и требует, чтобы каждый файл скоупа
держался не выше порога. Скоуп — проза поставки; справочники `references/`,
`CHANGELOG.md` и `research/` не берутся по причинам, описанным в
`research/BACKLOG.md` («Собственный стиль», замер 2026-08-06): справочники
цитируют машинный текст, журнал версий только дописывается, история изысканий
фиксирует записанное.

Запуск из корня репозитория:
    python3 scripts/check_own_style.py            # весь скоуп
    python3 scripts/check_own_style.py --selftest

Коды: 0 — порог соблюдён; 1 — есть файл выше порога; 2 — ошибка запуска
(счётчик не отработал, файл скоупа исчез, вывод не распарсился). Только
стандартная библиотека.
"""
import os
import subprocess
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COUNTER = os.path.join(HERE, "count_style_markers.py")
LIMIT = 90
SCOPE = (
    "SKILL.md",
    "README.md",
    "README.en.md",
    "CONTRIBUTING.md",
    "PERSONA.md",
    "eval/README.md",
    "eval/HOW-TO-RUN.md",
    "eval/runs/README.md",
    "SECURITY.md",
    "SECURITY.en.md",
    "CODE_OF_CONDUCT.md",
    ".github/pull_request_template.md",
)


def count_total(path):
    """Суммарный счёт файла со снятой разметкой; None — счётчик не понялся."""
    proc = subprocess.run(
        [sys.executable, COUNTER, "--skip-markup", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] == path:
            try:
                return int(parts[-1])
            except ValueError:
                return None
    return None


def run(paths, limit):
    """Возвращает (строки отчёта, превышения, ошибки инструмента)."""
    rows, over, broken = [], [], []
    for rel in paths:
        path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        if not os.path.exists(path):
            broken.append(rel)
            continue
        total = count_total(path)
        if total is None:
            broken.append(rel)
            continue
        rows.append(("OK   " if total <= limit else "МНОГО", rel, total))
        if total > limit:
            over.append((rel, total))
    return rows, over, broken


def render(rows, limit):
    width = max(len(rel) for _s, rel, _t in rows) if rows else 0
    out = []
    for status, rel, total in rows:
        out.append("%s %-*s  %d из %d" % (status, width, rel, total, limit))
    return "\n".join(out)


def selftest():
    cases = []
    with tempfile.TemporaryDirectory(prefix="own-style-selftest-") as td:
        loud = os.path.join(td, "loud.md")
        quiet = os.path.join(td, "quiet.md")
        with open(loud, "w", encoding="utf-8") as fh:
            fh.write("Слово — слово.\n" * 100)  # сто длинных тире
        with open(quiet, "w", encoding="utf-8") as fh:
            fh.write("Спокойный текст без примет.\n")

        rows, over, broken = run([loud, quiet], LIMIT)
        cases.append(("громкий файл выше порога",
                      not broken and over == [(loud, 100)]))
        cases.append(("тихий файл в отчёте без превышения",
                      any(r[1] == quiet and r[2] == 0 for r in rows)))

        rows, over, broken = run([loud], 200)
        cases.append(("высокий лимит пропускает тот же файл", not over))

        rows, over, broken = run([os.path.join(td, "нет.md")], LIMIT)
        cases.append(("пропавший файл — ошибка инструмента, не провал порога",
                      broken and not over))

        ok = 0
        for name, passed in cases:
            print(("  [OK]   " if passed else "  [FAIL] ") + name)
            ok += 1 if passed else 0
        print("Самопроверка: %d/%d" % (ok, len(cases)))
        return 0 if ok == len(cases) else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    rows, over, broken = run(SCOPE, LIMIT)
    if broken:
        print("ошибка инструмента: не посчитаны %s" % ", ".join(broken),
              file=sys.stderr)
        return 2
    print(render(rows, LIMIT))
    if over:
        print("Итог: %d файл(а) выше порога %d" % (len(over), LIMIT))
        return 1
    peak = max(total for _s, _r, total in rows) if rows else 0
    print("Итог: порог %d соблюдён, максимум %d" % (LIMIT, peak))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
