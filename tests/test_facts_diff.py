#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_facts_diff.py — юнит-тесты F1 (facts_diff)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from humanizer_ru import facts_diff  # noqa: E402


class FactsDiffTest(unittest.TestCase):
    def test_identical(self):
        d = facts_diff.diff("Бюджет 500 тыс. ₽ до 15 марта 2026 года.",
                            "Бюджет 500 тыс. ₽ до 15 марта 2026 года.")
        self.assertEqual((d["lost"], d["added"], d["changed"]), ([], [], []))

    def test_lost_number_and_date(self):
        d = facts_diff.diff("Бюджет 500 тыс. ₽ до 15 марта 2026 года.",
                            "Бюджет уточняется.")
        cats = {i["category"] for i in d["lost"]}
        self.assertIn("numbers", cats)
        self.assertIn("dates", cats)

    def test_negation_inversion(self):
        d = facts_diff.diff("отчёт не подтверждён", "отчёт подтверждён")
        self.assertTrue(any(i["kind"] == "инверсия отрицания"
                            for i in d["changed"]))

    def test_modal_inversion(self):
        d = facts_diff.diff("отчёт нельзя публиковать",
                            "отчёт можно публиковать")
        self.assertTrue(any(i["kind"] == "инверсия модальности"
                            for i in d["changed"]))

    def test_added_date(self):
        d = facts_diff.diff("встреча состоялась", "встреча 01 апреля 2026 года")
        self.assertTrue(any(i["category"] == "dates" for i in d["added"]))

    def test_names_case_insensitive(self):
        d = facts_diff.diff("## Ранняя Жизнь и Образование",
                            "## Ранняя жизнь и образование")
        self.assertEqual(d["lost"], [])
        self.assertEqual(d["added"], [])

    def test_numword_equals_digits(self):
        d = facts_diff.diff("пятнадцать процентов роста", "15 % роста")
        self.assertEqual((d["lost"], d["added"]), ([], []))

    def test_year_words_equals_digits(self):
        d = facts_diff.diff("две тысячи двадцать шесть год", "2026 год")
        self.assertEqual((d["lost"], d["added"]), ([], []))

    def test_protect_term(self):
        d = facts_diff.diff("термин КвантовыйОтжиг важен", "важен",
                            protect=["КвантовыйОтжиг"])
        self.assertTrue(any(i["category"] == "protected"
                            for i in d["lost"]))

    def test_envelope(self):
        env = facts_diff.envelope("x 5", "x 5")
        self.assertEqual(env["tool"], "humanizer-facts")
        self.assertEqual(env["schema"], 1)
        self.assertEqual(env["counts"], {"lost": 0, "added": 0,
                                          "changed": 0})

    def test_selftest_green(self):
        self.assertEqual(facts_diff.selftest(), 0)


class NumericCanonTests(unittest.TestCase):
    """Точный канон чисел: без float, со знаком, единицами и границами."""

    def test_canon_exact_strings(self):
        self.assertEqual(facts_diff._canon_number("1,1", ""), "1.1")
        self.assertEqual(facts_diff._canon_number("1.50", ""), "1.5")
        self.assertEqual(facts_diff._canon_number("-5", ""), "-5")
        self.assertEqual(facts_diff._canon_number("\u22125", ""), "-5")
        self.assertEqual(facts_diff._canon_number("+5", ""), "5")
        self.assertEqual(facts_diff._canon_number("1 000", ""), "1000")
        self.assertEqual(facts_diff._canon_number("9" * 400, ""), "9" * 400)
        self.assertEqual(facts_diff._canon_number("007", ""), "7")

    def test_unit_boundary_in_extract(self):
        ex = facts_diff.extract("Ждать 5 миндалин.")
        self.assertEqual(ex["numbers"][0]["value"], "5")
        ex = facts_diff.extract("Ждать 5 минут.")
        self.assertEqual(ex["numbers"][0]["value"], "5|мин")

    def test_date_like_flag(self):
        ex = facts_diff.extract("Версия 1.5 вышла.")
        self.assertTrue(ex["numbers"][0].get("date_like"))
        full = "Срок до 15" + ".03.20" + "26."
        ex = facts_diff.extract(full)
        self.assertTrue(ex["dates"])
        self.assertFalse(ex["numbers"])


if __name__ == "__main__":
    unittest.main()
