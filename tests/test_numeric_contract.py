#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_numeric_contract.py — числовой контракт facts_diff: точные
значения, знак, единицы с границей слова, разведение дат и дробей,
устойчивость машинного интерфейса к длинному числовому входу,
поведение тех же пар через CLI, report и MCP.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
os.environ["PYTHONPATH"] = SRC + os.pathsep + os.environ.get("PYTHONPATH", "")

from humanizer_ru import facts_diff as fd  # noqa: E402
from humanizer_ru import mcp_server as m  # noqa: E402

BIG = "9" * 400


def run_cli(args):
    return subprocess.run([sys.executable, "-X", "utf8",
                           "-m", "humanizer_ru.facts_diff"] + args,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


class NumericSemanticsTests(unittest.TestCase):
    def test_fraction_preserved(self):
        d = fd.diff("Доза 1,1 мг.", "Доза 1,9 мг.")
        self.assertTrue(any(i["category"] == "numbers" for i in d["lost"]))
        self.assertTrue(any(i["category"] == "numbers" for i in d["added"]))

    def test_sign_is_part_of_fact(self):
        d = fd.diff("Убыток -5 млн.", "Убыток 5 млн.")
        self.assertTrue(any(i["category"] == "numbers" for i in d["lost"]))
        ex = fd.extract("Убыток -5 млн.")
        self.assertEqual(ex["numbers"][0]["value"], "-5")

    def test_range_stays_unsigned(self):
        ex = fd.extract("Диапазон страниц 10-20.")
        self.assertEqual([n["value"] for n in ex["numbers"]], ["10", "20"])

    def test_big_ints_exact(self):
        d = fd.diff("Идентификатор 9007199254740992.",
                    "Идентификатор 9007199254740993.")
        self.assertTrue(any(i["category"] == "numbers" for i in d["lost"]))

    def test_unit_word_boundary(self):
        d = fd.diff("Ждать 5 минут.", "Ждать 5 миндалин.")
        self.assertTrue(any(i["category"] == "numbers" for i in d["lost"]))
        ex = fd.extract("Убыток 5 млн.")
        self.assertEqual(ex["numbers"][0]["value"], "5")

    def test_units_distinguished(self):
        d = fd.diff("Объём 1.5 кг сырья.", "Объём 1.5 л сырья.")
        self.assertTrue(any(i["category"] == "numbers" for i in d["lost"]))

    def test_dot_comma_equivalent(self):
        d = fd.diff("Вес 1.5 кг.", "Вес 1,5 кг.")
        self.assertEqual((d["lost"], d["added"], d["changed"]), ([], [], []))

    def test_grouping_equivalent(self):
        d = fd.diff("Итого 1 000 рублей.", "Итого 1000 рублей.")
        self.assertEqual((d["lost"], d["added"]), ([], []))

    def test_date_vs_decimal_rule(self):
        ex = fd.extract("Версия 1.5 вышла.")
        self.assertTrue(ex["numbers"])
        self.assertTrue(ex["numbers"][0].get("date_like"))
        self.assertFalse(ex["dates"])
        full = "Срок до 15" + ".03.20" + "26."
        ex2 = fd.extract(full)
        self.assertTrue(ex2["dates"])
        self.assertFalse(ex2["numbers"])

    def test_names_env_independent(self):
        # продуктовый контур не импортирует словарную морфологию
        self.assertFalse(hasattr(fd, "_MORPH"))
        self.assertEqual(fd._lemma("Петрова"), "петрова")


class NumericCliContractTests(unittest.TestCase):
    def test_long_number_keeps_json(self):
        with tempfile.TemporaryDirectory() as td:
            b = os.path.join(td, "b.txt")
            a = os.path.join(td, "a.txt")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write("Значение %s единиц." % BIG)
            with open(a, "w", encoding="utf-8") as fh:
                fh.write("Значение %s единиц." % BIG)
            p = run_cli(["diff", b, a, "--json"])
            self.assertEqual(p.returncode, 0, p.stderr)
            env = json.loads(p.stdout)
            self.assertEqual(env["tool"], "humanizer-facts")
            self.assertEqual(env["counts"],
                             {"lost": 0, "added": 0, "changed": 0})

    def test_long_number_difference_detected(self):
        with tempfile.TemporaryDirectory() as td:
            b = os.path.join(td, "b.txt")
            a = os.path.join(td, "a.txt")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write("Значение %s единиц." % BIG)
            with open(a, "w", encoding="utf-8") as fh:
                fh.write("Значение %s единиц." % (BIG + "1"))
            p = run_cli(["diff", b, a, "--json"])
            self.assertEqual(p.returncode, 1)
            env = json.loads(p.stdout)
            self.assertGreaterEqual(env["counts"]["lost"], 1)

    def test_unreadable_input_envelope(self):
        p = run_cli(["diff", "нет-файла-1.txt", "нет-файла-2.txt", "--json"])
        self.assertEqual(p.returncode, 2)
        env = json.loads(p.stdout)
        self.assertIn("error", env)


class NumericSurfaceParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = m.generate_tool_defs(m.load_contract())

    def _facts(self, before, after):
        res, rpc = m.call_tool("humanizer_facts",
                               {"text_before": before, "text_after": after},
                               self.defs)
        self.assertIsNone(rpc)
        return res

    def test_mcp_fraction_pair(self):
        res = self._facts("Доза 1,1 мг.", "Доза 1,9 мг.")
        sc = res["structuredContent"]
        self.assertTrue(sc["diff"]["lost"])
        self.assertFalse(res["isError"])

    def test_mcp_bad_then_good(self):
        bad, rpc = m.call_tool("humanizer_facts",
                               {"text_before": "а", "text_after": "б",
                                "лишний": 1}, self.defs)
        self.assertEqual(rpc[0], -32602)
        res = self._facts("Убыток -5 млн.", "Убыток 5 млн.")
        self.assertTrue(res["structuredContent"]["diff"]["lost"])

    def test_mcp_long_number_structured(self):
        res = self._facts("Значение %s единиц." % BIG,
                          "Значение %s единиц." % BIG)
        self.assertFalse(res["isError"])
        self.assertEqual(res["structuredContent"]["counts"],
                         {"lost": 0, "added": 0, "changed": 0})

    def test_report_surface_sees_fraction_change(self):
        with tempfile.TemporaryDirectory() as td:
            b = os.path.join(td, "b.txt")
            a = os.path.join(td, "a.txt")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write("Доза 1,1 мг.")
            with open(a, "w", encoding="utf-8") as fh:
                fh.write("Доза 1,9 мг.")
            p = subprocess.run([sys.executable, "-X", "utf8",
                                "-m", "humanizer_ru.edit_report", b, a,
                                "--json"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            # humanizer-report по контракту всегда rc=0: отчёт информативен,
            # потеря фактов видна в конверте, а не в коде выхода.
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            env = json.loads(p.stdout)
            facts = env["files"][0]["facts"]
            self.assertGreaterEqual(facts["lost"], 1)
            self.assertFalse(facts["unchanged"])


if __name__ == "__main__":
    unittest.main()
