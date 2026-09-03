#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Независимые unittest-тесты таблицы CASES из scripts/check_markers.py.

Прямой import модуля безопасен: при импорте настраивается только
безопасный stdout для консолей Windows (sys.stdout.reconfigure), а вся
полезная работа спрятана под `if __name__ == "__main__"`. Поэтому таблицу
CASES можно импортировать, добавив scripts/ в sys.path, без каких-либо
побочных эффектов.

Для каждого из 40 маркеров генерируются отдельные тестовые методы:
  test_positive_<имя>  — все позитивные образцы обязаны сработать;
  test_negative_<имя>  — ни один негативный образец не должен сработать;
  test_multiplicity_<имя> — если задан многократный образец, re.findall
                          обязан вернуть ровно ожидаемое число совпадений.
Кроме того, проверяются пустая строка, дедупликация _line_matches и
экранирование невидимых символов _console_text.
"""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

if os.path.isdir(SCRIPTS):
    # Дерево репозитория: канон — scripts/ (установленный пакет может быть
    # старее рабочего дерева).
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import check_markers  # noqa: E402
else:
    # sdist вне дерева: копия из пакета побайтово равна scripts/
    # (гейт scripts/check_pkg_sync.py).
    from humanizer_ru import check_markers  # noqa: F401


class TestMarkerCases(unittest.TestCase):
    """Сгенерированные тесты CASES."""

    @classmethod
    def setUpClass(cls):
        cls.compiled = {
            name: re.compile(case[0])
            for name, case in check_markers.CASES.items()
        }

    def test_structure(self):
        """Таблица содержит 40 кейсов ожидаемой формы."""
        self.assertEqual(len(check_markers.CASES), 40)
        for name, case in check_markers.CASES.items():
            with self.subTest(name=name):
                self.assertIsInstance(case, tuple)
                self.assertEqual(len(case), 4)
                pattern, positives, negatives, multi = case
                self.assertIsInstance(pattern, str)
                self.assertTrue(pattern, name)
                self.assertIsInstance(positives, list)
                self.assertTrue(positives, name)
                self.assertIsInstance(negatives, list)
                self.assertIsInstance(multi, (tuple, type(None)))
                if multi is not None:
                    self.assertEqual(len(multi), 2)


def _make_positive_test(name, case):
    def test(self):
        rx = self.compiled[name]
        for s in case[1]:
            with self.subTest(marker=name, sample=s):
                self.assertIsNotNone(
                    rx.search(s),
                    "Кейс %r: прямой образец не пойман: %r" % (name, s))

    return test


def _make_negative_test(name, case):
    def test(self):
        rx = self.compiled[name]
        for s in case[2]:
            with self.subTest(marker=name, sample=s):
                self.assertIsNone(
                    rx.search(s),
                    "Кейс %r: ложное срабатывание на: %r" % (name, s))

    return test


def _make_multiplicity_test(name, case):
    def test(self):
        rx = self.compiled[name]
        text, expected = case[3]
        got = len(rx.findall(text))
        self.assertEqual(
            got, expected,
            "Кейс %r: ожидалось %d совпадений, найдено %d в %r"
            % (name, expected, got, text))

    return test


def _make_empty_test(name, case):
    def test(self):
        rx = self.compiled[name]
        self.assertIsNone(
            rx.search(""),
            "Кейс %r: срабатывание на пустой строке" % name)

    return test


for _name, _case in check_markers.CASES.items():
    setattr(TestMarkerCases, "test_positive_" + _name, _make_positive_test(_name, _case))
    setattr(TestMarkerCases, "test_negative_" + _name, _make_negative_test(_name, _case))
    if _case[3] is not None:
        setattr(TestMarkerCases, "test_multiplicity_" + _name,
                _make_multiplicity_test(_name, _case))
    setattr(TestMarkerCases, "test_empty_" + _name, _make_empty_test(_name, _case))


class TestCheckMarkersHelpers(unittest.TestCase):
    def test_line_matches_deduplicates_nested_artefacts(self):
        compiled_all = {
            name: re.compile(case[0])
            for name, case in check_markers.CASES.items()
        }
        full_form = check_markers.CASES["contentReference"][1][0]
        turn_file_form = check_markers.CASES["turn_file"][1][0]
        pua_form = check_markers.CASES["openai_pua"][1][0]
        for text, expected in (
            (full_form, 1),
            (turn_file_form, 2),
            (pua_form, 4),
            ("обычная строка без примет", 0),
        ):
            with self.subTest(expected=expected):
                got = len(check_markers._line_matches(text, compiled_all))
                self.assertEqual(got, expected)

    def test_console_text_escapes_nonprintable_for_ascii(self):
        self.assertEqual(check_markers._console_text("\ufeff", "ascii"), r"\ufeff")


if __name__ == "__main__":
    unittest.main()
