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

    def test_envelope(self):
        env = facts_diff.envelope("x 5", "x 5")
        self.assertEqual(env["tool"], "humanizer-facts")
        self.assertEqual(env["schema"], 1)
        self.assertEqual(env["counts"], {"lost": 0, "added": 0,
                                          "changed": 0})

    def test_selftest_green(self):
        self.assertEqual(facts_diff.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
