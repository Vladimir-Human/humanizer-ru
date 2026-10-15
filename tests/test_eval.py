# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Unit tests for the vote rules of the blind comparison report (no API calls).
# SCOPE: fact_flag and the equal-weight means of eval/report.py; answer repair in eval/judge.py.
# DEPENDS: unittest; eval/report.py, eval/judge.py and eval/evallib.py loaded by path.
# LINKS: V-M-EVAL.
# END_MODULE_CONTRACT
import importlib.util
import sys
import unittest
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))
_spec = importlib.util.spec_from_file_location("eval_report", EVAL / "report.py")
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)
_jspec = importlib.util.spec_from_file_location("eval_judge", EVAL / "judge.py")
judge = importlib.util.module_from_spec(_jspec)
_jspec.loader.exec_module(judge)


class EvalReportTest(unittest.TestCase):
    def test_two_passes_of_one_judge_do_not_outvote_another(self):
        # Old rule: 2 of 3 passes. Now one judge flagging twice is one vote of three.
        votes = {"argon": [2, 2], "kimi": [0, 1], "muse": [0, 1]}
        self.assertEqual(report.fact_flag(votes), (False, True))

    def test_majority_of_three_judges(self):
        votes = {"argon": [1, 2], "kimi": [1, 1], "muse": [0, 1]}
        self.assertEqual(report.fact_flag(votes), (True, True))

    def test_two_judges_need_both(self):
        self.assertEqual(report.fact_flag({"argon": [2, 2], "kimi": [0, 1]}), (False, True))
        self.assertEqual(report.fact_flag({"argon": [1, 2], "kimi": [1, 1]}), (True, True))

    def test_clean_output(self):
        self.assertEqual(report.fact_flag({"argon": [0, 2], "kimi": [0, 1], "muse": [0, 1]}), (False, False))

    def test_one_judge_keeps_pass_rule(self):
        self.assertEqual(report.fact_flag({"argon": [1, 1]}), (False, True))
        self.assertEqual(report.fact_flag({"argon": [2, 2]}), (True, True))

    def test_parse_repairs_kimi_brace_before_score(self):
        body = ('{"candidates": {"A": {"fact_errors": [], "language_errors": ["x"]}, "send_as_is": 9}, '
                '"B": {"fact_errors": [], "language_errors": []}, "send_as_is": 8')
        # After the move "candidates" is either still open (one brace before "ranking") or closed (two).
        for tail in ('}, "ranking": ["A", "B"]}', '}}, "ranking": ["A", "B"]}'):
            data = judge.parse(body + tail)
            self.assertIsNotNone(data, tail)
            self.assertEqual(data["ranking"], ["A", "B"])
            self.assertEqual(data["candidates"]["A"]["send_as_is"], 9)
            self.assertEqual(data["candidates"]["B"]["send_as_is"], 8)
        self.assertEqual(judge.parse('{"ranking": ["A"], "candidates": {}}')["ranking"], ["A"])

    def test_equal_weight_mean(self):
        # Argon made four passes, Kimi one: both weigh the same.
        self.assertAlmostEqual(report._equal_weight({"argon": [1, 1, 1, 1], "kimi": [3]}), 2.0)
        self.assertIsNone(report._equal_weight({}))


if __name__ == "__main__":
    unittest.main()
