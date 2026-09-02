#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry points консольных команд humanizer-ru.

humanizer-scan    -> scan_soft_signals.main()  (мягкие признаки)
humanizer-markers -> check_markers.scan()      (режим --scan из CLI скрипта)
humanizer-polish  -> polish.main()             (типографическая нормализация)
humanizer-detect  -> detect_conj.main()        (детектор частоты связок)

Оригинальные модули настраивают sys.stdout/stderr при импорте (обход
Windows-консолей без кириллицы). Стандартная библиотека Python; сторонних
зависимостей нет.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from . import check_markers
from . import detect_conj
from . import polish
from . import scan_soft_signals


def scan_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-scan: счётчик мягких признаков."""
    return scan_soft_signals.main(argv)


def markers_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-markers: скан 40 маркеров артефактов копипасты.

    Полный argparse-интерфейс: --help работает, --json печатает конверт
    контракта {tool, schema, files}, «-» читает stdin. Форма
    `humanizer-markers --scan файл1 [...]` сохранена (флаг --scan —
    совместимость, режим сканирования включён всегда). Без файлов
    запускается самопроверка 40 выражений с явным сообщением в stderr.
    """
    import argparse

    ap = argparse.ArgumentParser(
        prog="humanizer-markers",
        description="Артефакты копипасты и чат-интерфейсов: 40 маркеров "
                    "классов A и B. Находит и показывает; вердикта об "
                    "авторстве нет. Удаление меток — scripts/filemarks "
                    "(в pip-пакет не входит).")
    ap.add_argument("files", nargs="*",
                    help="файлы для проверки; «-» читает stdin (UTF-8)")
    ap.add_argument("--scan", action="store_true",
                    help="совместимость: режим сканирования включён всегда")
    ap.add_argument("--class", dest="cls", choices=["a", "all"], default="all",
                    help="код возврата: все маркеры (all) или только класс A (a)")
    ap.add_argument("--json", action="store_true",
                    help="машиночитаемый отчёт (конверт {tool, schema, files})")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка 40 выражений")
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.selftest or not args.files:
        if not args.files and not args.selftest:
            print("нет файлов — запускается самопроверка выражений; "
                  "справка: --help", file=sys.stderr)
        return check_markers.main()
    paths = list(args.files)
    if args.cls != "all":
        paths += ["--class", args.cls]
    return check_markers.scan(paths, as_json=args.json)


def polish_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-polish: типографическая нормализация."""
    return polish.main(list(sys.argv[1:] if argv is None else argv))


def detect_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-detect: детектор частоты связок."""
    return detect_conj.main(list(sys.argv[1:] if argv is None else argv))
