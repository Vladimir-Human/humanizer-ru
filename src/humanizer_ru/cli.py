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
                    "авторстве нет. Удаление меток — scripts/filemarks "
                    "(в pip-пакет не входит).",
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
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка 40 выражений")
    parsed = ap.parse_args(args)
    if parsed.selftest or not parsed.files:
        if not parsed.files and not parsed.selftest:
            print("нет файлов — запускается самопроверка выражений; "
                  "справка: --help", file=sys.stderr)
        return check_markers.main()
    paths = list(parsed.files)
    if parsed.cls != "all":
        paths += ["--class", parsed.cls]
    return check_markers.scan(paths, as_json=parsed.json)


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
