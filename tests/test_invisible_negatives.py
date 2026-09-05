#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Отрицательные фикстуры невидимых символов (#84): человеческий текст без
невидимых символов не даёт находок zero_width и invisible_layout."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from check_markers import CASES  # noqa: E402

FIXTURES = ("zero-width-negative-human.txt", "invisible-negative-human.txt")
WATCH = ("zero_width", "invisible_layout")


class InvisibleNegativeTests(unittest.TestCase):
    def test_no_invisible_hits(self):
        for name in FIXTURES:
            path = os.path.join(ROOT, "tests", "fixtures", name)
            text = open(path, encoding="utf-8").read()
            for case in WATCH:
                import re
                rx = re.compile(CASES[case][0])
                self.assertIsNone(rx.search(text),
                                  "%s дал находку %s" % (name, case))


if __name__ == "__main__":
    unittest.main()
