#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты F2: humanizer-report."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from humanizer_ru import edit_report as er  # noqa: E402


class EditReportTest(unittest.TestCase):
    def _pair(self, before, after):
        d = tempfile.mkdtemp()
        b = os.path.join(d, "b.txt")
        a = os.path.join(d, "a.txt")
        with open(b, "w", encoding="utf-8") as fh:
            fh.write(before)
        with open(a, "w", encoding="utf-8") as fh:
            fh.write(after)
        return b, a

    def test_tokens(self):
        b, a = self._pair("один два три\n", "один три\n")
        f = er.report(b, a)["files"][0]
        self.assertEqual(f["tokens"]["delete"], 1)
        self.assertEqual(f["tokens"]["keep"], 2)

    def test_identical(self):
        b, a = self._pair("текст\n", "текст\n")
        f = er.report(b, a)["files"][0]
        self.assertEqual(f["sari_adapted"]["keep"], 1.0)

    def test_facts_flag(self):
        b, a = self._pair("Срок 12 дней.\n", "Срок 13 дней.\n")
        f = er.report(b, a)["files"][0]
        self.assertFalse(f["facts"]["unchanged"])

    def test_facts_fraction_not_truncated(self):
        # дробь не усечена до целого: 1,1 -> 1,9 видна в отчёте как потеря
        b, a = self._pair("Доза 1,1 мг.\n", "Доза 1,9 мг.\n")
        f = er.report(b, a)["files"][0]
        self.assertGreaterEqual(f["facts"]["lost"], 1)
        self.assertFalse(f["facts"]["unchanged"])

    def test_facts_equivalent_notations_clean(self):
        b, a = self._pair("Вес 1.5 кг.\n", "Вес 1,5 кг.\n")
        f = er.report(b, a)["files"][0]
        self.assertTrue(f["facts"]["unchanged"])


if __name__ == "__main__":
    unittest.main()
