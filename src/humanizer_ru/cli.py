#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry points консольных команд humanizer-ru.

humanizer-scan    -> scan_soft_signals.main()  (мягкие признаки)
humanizer-markers -> check_markers.scan()      (скан артефактов копипасты)
humanizer-polish  -> polish.main()             (типографическая нормализация)
humanizer-detect  -> detect_conj.main()        (детектор частоты связок)

Все четыре команды поддерживают --version (версия пакета) и --contract
(машинный контракт contract.v1.json из данных пакета). Оригинальные
модули настраивают sys.stdout/stderr при импорте (обход Windows-консолей
без кириллицы). Стандартная библиотека Python; сторонних зависимостей нет.
"""
from __future__ import annotations

import sys
from typing import List, Optional, Sequence

from . import __version__
from . import check_markers
from . import detect_conj
from . import polish
from . import scan_soft_signals

EPILOG = ("Репозиторий: https://github.com/Vladimir-Human/humanizer-ru\n"
          "Вход для агентов: llms.txt; машинный контракт: contract.v1.json")


def _contract_text() -> str:
    """contract.v1.json из данных пакета (копия едет в wheel/sdist)."""
    try:
        from importlib.resources import files
        return files("humanizer_ru").joinpath("contract.v1.json").read_text(
            encoding="utf-8")
    except Exception:  # pragma: no cover — запасной путь для странных окружений
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "contract.v1.json"),
                  encoding="utf-8") as fh:
            return fh.read()


def _resolved(argv: Optional[Sequence[str]]) -> List[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _common(args: List[str]) -> Optional[int]:
    """Перехват --version/--contract до делегирования парсеру инструмента."""
    if "--version" in args:
        print(__version__)
        return 0
    if "--contract" in args:
        text = _contract_text()
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return 0
    return None


def scan_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-scan: счётчик мягких признаков."""
    args = _resolved(argv)
    rc = _common(args)
    if rc is not None:
        return rc
    return scan_soft_signals.main(args)


def markers_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-markers: скан 40 маркеров артефактов копипасты.

    Полный argparse-интерфейс: --help работает, --json печатает конверт
    контракта {tool, schema, files}, «-» читает stdin. Форма
    `humanizer-markers --scan файл1 [...]` сохранена (флаг --scan —
    совместимость, режим сканирования включён всегда). Без файлов
    запускается самопроверка 40 выражений с явным сообщением в stderr.

    Режим --remove: снятие невидимых меток по классификации риска
    (safe — автоматически; ambiguous — только --include-ambiguous, с
    дифом и предупреждениями; dangerous — показывается и не снимается
    никогда). Массовое удаление всего невидимого запрещено по построению.
    """
    import argparse

    args = _resolved(argv)
    rc = _common(args)
    if rc is not None:
        return rc
    ap = argparse.ArgumentParser(
        prog="humanizer-markers",
        description="Артефакты копипасты и чат-интерфейсов: 40 маркеров "
                    "классов A и B. Находит и показывает; вердикта об "
                    "авторстве нет. --remove снимает невидимые метки по "
                    "классификации риска (safe автоматически, ambiguous "
                    "только opt-in, dangerous никогда); контейнерные файлы "
                    "(PNG/DOCX/…) — scripts/filemarks в репозитории.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*",
                    help="файлы для проверки; «-» читает stdin (UTF-8)")
    ap.add_argument("--scan", action="store_true",
                    help="совместимость: режим сканирования включён всегда")
    ap.add_argument("--class", dest="cls", choices=["a", "all"], default="all",
                    help="код возврата: все маркеры (all) или только класс A (a)")
    ap.add_argument("--json", action="store_true",
                    help="машиночитаемый отчёт (конверт {tool, schema, files})")
    ap.add_argument("--remove", action="store_true",
                    help="снять невидимые метки класса safe (ambiguous — "
                         "только с --include-ambiguous; dangerous не "
                         "снимается никогда)")
    ap.add_argument("--include-ambiguous", action="store_true",
                    help="opt-in снятие ambiguous-символов (bidi, "
                         "вариационные селекторы, ZWJ/ZWNJ, спецпробелы) "
                         "с предупреждением о риске изменения отображения")
    ap.add_argument("--dry-run", action="store_true",
                    help="с --remove: показать отчёт, не писать файл")
    ap.add_argument("--diff", action="store_true",
                    help="с --remove: унифицированный диф до/после")
    ap.add_argument("--in-place", action="store_true",
                    help="с --remove: писать на место (копия .bak)")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка 40 выражений")
    parsed = ap.parse_args(args)
    if parsed.remove:
        return _markers_remove(parsed)
    if parsed.selftest or not parsed.files:
        if not parsed.files and not parsed.selftest:
            print("нет файлов — запускается самопроверка выражений; "
                  "справка: --help", file=sys.stderr)
        return check_markers.main()
    paths = list(parsed.files)
    if parsed.cls != "all":
        paths += ["--class", parsed.cls]
    return check_markers.scan(paths, as_json=parsed.json)


def _markers_remove(parsed) -> int:
    """Режим --remove: снятие невидимых меток по классификации риска."""
    import difflib
    import json

    from . import text_layer

    if not parsed.files:
        print("нет файлов для --remove; «-» читает stdin", file=sys.stderr)
        return 2
    report_files = []
    rc = 0
    for path in parsed.files:
        label = "<stdin>" if path == "-" else path
        try:
            if path == "-":
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
                before = sys.stdin.read()
            else:
                with open(path, encoding="utf-8") as fh:
                    before = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
            report_files.append({"file": label, "mode": "remove",
                                 "error": str(exc)})
            rc = 2
            continue
        after, report = text_layer.remove_invisible(
            before, include_ambiguous=parsed.include_ambiguous)
        entry = {
            "file": label,
            "mode": "remove",
            "removed": report["removed"],
            "reported": report["reported"],
            "flag_sequences_kept": report["flag_sequences_kept"],
            "warnings": report["warnings"],
            "removed_safe": sum(1 for r in report["removed"]
                                if r["class"] == "safe"),
            "removed_ambiguous": sum(1 for r in report["removed"]
                                     if r["class"] == "ambiguous"),
            "reported_total": len(report["reported"]),
            "changed": after != before,
        }
        if parsed.json:
            report_files.append(entry)
            continue
        if parsed.diff:
            sys.stdout.writelines(difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=label + " (до)", tofile=label + " (после)"))
        for w in report["warnings"]:
            print("ПРЕДУПРЕЖДЕНИЕ: " + w, file=sys.stderr)
        for rec in report["reported"]:
            print("ПОКАЗАНО, НЕ СНЯТО [%s] %s %s (строка %d)"
                  % (rec["class"], rec["codepoint"], rec["name"], rec["line"]),
                  file=sys.stderr)
        if parsed.dry_run:
            if entry["changed"]:
                print("ИЗМЕНИТСЯ %s: снято safe %d, ambiguous %d; показано %d"
                      % (label, entry["removed_safe"],
                         entry["removed_ambiguous"], entry["reported_total"]))
            else:
                print("БЕЗ ИЗМЕНЕНИЙ " + label)
            continue
        if parsed.in_place and path != "-":
            if entry["changed"]:
                with open(path + ".bak", "w", encoding="utf-8",
                          newline="") as fh:
                    fh.write(before)
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(after)
            print(("ЗАПИСАНО " if entry["changed"] else "БЕЗ ИЗМЕНЕНИЙ ")
                  + label)
            continue
        if parsed.diff:
            continue
        sys.stdout.write(after if not after or after.endswith("\n")
                         else after + "\n")
    if parsed.json:
        envelope = {"tool": "humanizer-markers", "schema": 1,
                    "files": report_files}
        if rc == 2:
            envelope["error"] = "вход не читается (код 2)"
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return rc


def polish_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-polish: типографическая нормализация."""
    args = _resolved(argv)
    rc = _common(args)
    if rc is not None:
        return rc
    return polish.main(args)


def detect_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-detect: детектор частоты связок."""
    args = _resolved(argv)
    rc = _common(args)
    if rc is not None:
        return rc
    return detect_conj.main(args)
