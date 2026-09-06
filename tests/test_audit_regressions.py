#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессии независимого аудита 2026-09-06 (поток L1, находки N41/N42).

Контрпримеры воспроизводили исходную проблему на срезе ecf4652
(см. .audit/2026-09-05/triage1-3.json): utm_source=openair и
utm_source=chatgpt.com.example давали ложные маркеры класса A; двойной
code span обрабатывался иначе, чем одинарный (чётность бэктиков).
После исправлений тесты ниже проходят; они же падают на возвращении
старых паттернов или чётностной семантики.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_markers as cm  # noqa: E402

UTM = ("utm_openai", "utm_chatgpt", "utm_copilot")


def _utm_hits(text):
    return [c for c in UTM if re.compile(cm.CASES[c][0]).search(text)]


class UtmBoundaryTests(unittest.TestCase):
    def test_openair_negative(self):
        self.assertEqual(_utm_hits("https://example.com/r?utm_source=openair"), [])

    def test_openai_community_negative(self):
        self.assertEqual(
            _utm_hits("https://example.com/r?utm_source=openai.community"), [])

    def test_chatgpt_example_negative(self):
        self.assertEqual(
            _utm_hits("https://example.com/r?utm_source=chatgpt.com.example"),
            [])
        self.assertEqual(_utm_hits("https://chatgpt.com.example/share/abc"), [])

    def test_copilot_community_negative(self):
        self.assertEqual(
            _utm_hits("https://example.com/r?utm_source=copilot.community"), [])

    def test_positives_preserved(self):
        self.assertEqual(
            _utm_hits("https://docs.example.com/?utm_source=openai"),
            ["utm_openai"])
        self.assertEqual(
            _utm_hits("https://example.com/r?utm_source=openai&x=1"),
            ["utm_openai"])
        self.assertEqual(
            _utm_hits("https://example.com/article?utm_source=chatgpt.com"),
            ["utm_chatgpt"])
        self.assertEqual(
            _utm_hits("?utm_source=chatgpt.com&other=1"), ["utm_chatgpt"])
        self.assertEqual(
            _utm_hits("https://example.com/?utm_source=copilot.com&next=2"),
            ["utm_copilot"])


class CodeSpanSemanticsTests(unittest.TestCase):
    ART = ":contentReference[oaicite:1]{index=1}"

    def _hits(self, line):
        compiled = {k: re.compile(cm.CASES[k][0]) for k in cm.CASES
                    if "oaicite" in k}
        return len(cm._line_matches(line, compiled))

    def test_single_span_hides(self):
        self.assertEqual(self._hits("x `" + self.ART + "` y"), 0)

    def test_double_span_hides(self):
        self.assertEqual(self._hits("x ``" + self.ART + "`` y"), 0)

    def test_unclosed_span_hides_to_eol(self):
        self.assertEqual(self._hits("x `" + self.ART + " y"), 0)

    def test_inner_run_is_content(self):
        self.assertEqual(self._hits("x ``a ` " + self.ART + " b`` y"), 0)

    def test_after_closed_span_visible(self):
        self.assertEqual(self._hits("x ``a`` " + self.ART + " y"), 1)

    def test_outside_span_visible(self):
        self.assertEqual(self._hits("x " + self.ART + " y"), 1)

    def test_span_pairs_documented(self):
        self.assertEqual(cm._code_spans("a `b` c ``d`` e"),
                         [(3, 4), (10, 11)])


if __name__ == "__main__":
    unittest.main()
