#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Юнит-тесты mtld (lexical diversity) из humanizer_ru.edit_report (#83)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from humanizer_ru.edit_report import mtld  # noqa: E402

DIVERSE = ("редактор читал черновик утром, потом правил сноски, сверял "
           "цитаты с источником, переписывал вводный абзац дважды, удалил "
           "лишние повторы, добавил пример из старой статьи, сверил даты")
REPETITIVE = ("текст текст текст текст текст текст текст текст текст текст "
              "текст текст текст текст текст текст текст текст текст текст")


class MtldTests(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(mtld(""))

    def test_short_is_none(self):
        self.assertIsNone(mtld("мало слов для метрики"))

    def test_deterministic(self):
        self.assertEqual(mtld(DIVERSE), mtld(DIVERSE))

    def test_repetitive_below_diverse(self):
        self.assertLess(mtld(REPETITIVE), mtld(DIVERSE))

    def test_returns_rounded_float(self):
        val = mtld(DIVERSE)
        self.assertIsInstance(val, float)
        self.assertEqual(val, round(val, 4))


if __name__ == "__main__":
    unittest.main()
