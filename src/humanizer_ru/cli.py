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
    """Точка входа humanizer-markers: режим --scan check_markers.py.

    Поддерживается как форма `humanizer-markers --scan файл1 [...]`, так и
    сокращённая `humanizer-markers файл1 [...]` (--scan подразумевается).
    Без файлов запускается самопроверка 40 выражений, как и в оригинальном
    check_markers.py без аргументов.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--scan":
        args = args[1:]
    if not args:
        return check_markers.main()
    return check_markers.scan(args)


def polish_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-polish: типографическая нормализация."""
    return polish.main(list(sys.argv[1:] if argv is None else argv))


def detect_main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа humanizer-detect: детектор частоты связок."""
    return detect_conj.main(list(sys.argv[1:] if argv is None else argv))
