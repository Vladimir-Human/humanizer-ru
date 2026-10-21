# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Unit tests for the blind comparison scripts (no API calls, no subagents).
# SCOPE: fact_flag, equal-weight means and rank judges of eval/report.py; answer repair in
#        eval/judge.py; patterns.py; the free DSH route of evallib.py; subagent batches (batches.py).
# DEPENDS: unittest; eval/*.py loaded by path; temporary folders only.
# LINKS: V-M-EVAL; V-M-EVAL-PATTERNS; V-M-EVAL-LIB; V-M-EVAL-BATCH.
# END_MODULE_CONTRACT
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))
_spec = importlib.util.spec_from_file_location("eval_report", EVAL / "report.py")
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)
_jspec = importlib.util.spec_from_file_location("eval_judge", EVAL / "judge.py")
judge = importlib.util.module_from_spec(_jspec)
_jspec.loader.exec_module(judge)
_pspec = importlib.util.spec_from_file_location("eval_patterns", EVAL / "patterns.py")
patterns = importlib.util.module_from_spec(_pspec)
_pspec.loader.exec_module(patterns)
_bspec = importlib.util.spec_from_file_location("eval_batches", EVAL / "batches.py")
batches = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(batches)
import evallib as lib  # noqa: E402  (eval/ is on sys.path)
import run_systems as rs  # noqa: E402


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

    def test_rank_judges_place_and_every_judge_votes_on_facts(self):
        # R-EVAL-RANK-JUDGES: Sol only votes on meaning errors; places come from the other judges.
        rows = [{"id": "q01", "judge": "argon", "round": 0, "ranking": ["x", "y"],
                 "candidates": {"x": {"fact_errors": ["потеряна дата"], "send_as_is": 6}, "y": {"fact_errors": [], "send_as_is": 5}}},
                {"id": "q01", "judge": "sol", "round": 0, "ranking": ["y", "x"],
                 "candidates": {"x": {"fact_errors": ["нет даты"], "send_as_is": 2}, "y": {"fact_errors": [], "send_as_is": 9}}}]
        outputs, sources = {("x", "q01"): "а", ("y", "q01"): "б"}, {"q01": "а"}
        table, pair, _ = report.aggregate(rows, {"q01"}, outputs, sources, rank_judges={"argon"})
        self.assertEqual(table["x"]["mean_position"], 1.0)
        self.assertEqual(pair["x>y"], 1.0)
        self.assertEqual(table["x"]["send_as_is"], 6.0)
        self.assertEqual(table["x"]["texts_with_fact_errors"], ["q01"])  # both judges flagged it
        table_all, _, _ = report.aggregate(rows, {"q01"}, outputs, sources)
        self.assertEqual(table_all["x"]["mean_position"], 1.5)


class EvalDshRouteTest(unittest.TestCase):
    """R-EVAL-DSH: only the owner's free routes, no paid fallback, nothing booked, plain reply."""

    def test_task_text_rules_then_system_then_user(self):
        text = lib.dsh_task_text([{"role": "user", "content": "USER-REQ"}, {"role": "system", "content": "SYS-INSTR"}])
        self.assertTrue(text.startswith(lib.DSH_RULES))
        self.assertLess(text.index("SYS-INSTR"), text.index("USER-REQ"))
        with self.assertRaises(ValueError):
            lib.dsh_task_text([{"role": "assistant", "content": "x"}])

    def test_other_routes_are_refused_before_anything_runs(self):
        with mock.patch.object(lib.subprocess, "run") as run:
            with self.assertRaises(SystemExit):
                lib.chat("dsh:fal/openai/gpt-6.1-sol", [{"role": "user", "content": "x"}])
            run.assert_not_called()

    def test_free_route_runs_without_fallback_and_books_nothing(self):
        report_json = {"ok": True, "answer": "текст", "cost": 0.0123, "seconds": 3, "tokens": {"in": 1, "out": 2}}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lib, "CACHE_DIR", Path(d)), \
                mock.patch.object(lib.subprocess, "run", return_value=mock.Mock(
                    stdout=json.dumps(report_json), stderr="", returncode=0)) as run, \
                mock.patch.object(lib, "ledger") as ledger:
            msg, usage = lib.chat("dsh:agentrouter-astra/gpt-6.1-sol", [{"role": "user", "content": "x"}], effort="medium")
        cmd = run.call_args[0][0]
        self.assertIn("--no-fallback", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "agentrouter-astra/gpt-6.1-sol")
        self.assertEqual((msg["content"], usage["cost"], usage["listed_cost"]), ("текст", 0.0, 0.0123))
        ledger.assert_not_called()

    def test_failed_run_is_retried_on_the_same_free_route(self):
        failed = {"ok": False, "stderrTail": ["Server is restarting; please retry shortly"]}
        good = {"ok": True, "answer": "текст", "cost": 0.01, "seconds": 2, "tokens": {}}
        replies = [mock.Mock(stdout=json.dumps(r), stderr="", returncode=0) for r in (failed, good)]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lib, "CACHE_DIR", Path(d)), \
                mock.patch.object(lib.time, "sleep"), mock.patch.object(lib.subprocess, "run", side_effect=replies) as run:
            msg, _ = lib.chat("dsh:agentrouter-astra/gpt-6.1-sol", [{"role": "user", "content": "x"}])
        self.assertEqual(msg["content"], "текст")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0][0][0], run.call_args_list[1][0][0])

    def test_failed_empty_or_truncated_answers(self):
        with self.assertRaises(RuntimeError):
            lib.dsh_answer({"ok": False, "failKind": "timeout", "errors": ["x"]})
        with self.assertRaises(RuntimeError):
            lib.dsh_answer({"ok": True, "answer": "  "})
        with tempfile.TemporaryDirectory() as d:
            full = Path(d) / "answer.md"
            full.write_text("полный ответ", encoding="utf-8")
            msg, _ = lib.dsh_answer({"ok": True, "answer": "полн", "answerTruncated": True, "answerPath": str(full)})
        self.assertEqual(msg["content"], "полный ответ")


class EvalBatchTest(unittest.TestCase):
    """R-EVAL-BATCH: subagents get the API run's prompt and request, judges stay blind."""

    def _skill(self, root: Path) -> dict:
        lib.write_text(root / "SKILL.md", "# Навык\nПравило.")
        lib.write_text(root / "references" / "a.md", "Пример.")
        lib.write_text(root / "scripts" / "x.py", "print(1)")
        return {"name": "sk", "kind": "local", "path": str(root)}

    def test_subagent_prompt_is_the_api_prompt_with_read_paths(self):
        with tempfile.TemporaryDirectory() as d:
            sysdef = self._skill(Path(d) / "skill-src")
            api, files = rs.load_system(sysdef)
            sub, sub_files = batches.subagent_system(sysdef, Path(d) / "copy")
        self.assertEqual(files, sub_files)  # the same readable files: .md only, no scripts
        self.assertNotIn("read_file", sub)
        sentence = batches.READ_SUBAGENT % (Path(d) / "copy").as_posix()
        self.assertIn(sentence, sub)
        self.assertEqual(sub.replace(sentence, batches.READ_API), api)

    def test_prepare_run_same_requests_and_order_for_every_system(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sysdef = self._skill(d / "skill-src")
            other = dict(sysdef, name="sk2")
            for tid in ("q01", "q02", "h01"):
                lib.write_text(d / "texts" / (tid + ".txt"), "Исходник %s." % tid)
            tasks = batches.prepare_run([sysdef, other], [["q01", "q02"], ["h01"]], d / "batch", d / "run", d / "texts", "exec")
            bodies = [t.read_text(encoding="utf-8") for t in tasks]
            request = (d / "batch" / "requests" / "q02.txt").read_text(encoding="utf-8")
            copied = sorted(p.relative_to(d / "batch" / "sk").as_posix() for p in (d / "batch" / "sk" / "skill").rglob("*") if p.is_file())
        self.assertEqual(len(tasks), 4)
        strip = lambda body, name: body.replace("/%s/" % name, "/S/")
        self.assertEqual(strip(bodies[0], "sk"), strip(bodies[2], "sk2"))
        self.assertLess(bodies[0].index("q01.txt"), bodies[0].index("q02.txt"))
        self.assertEqual(request, rs.REQUEST + "Исходник q02.")
        self.assertEqual(copied, ["skill/SKILL.md", "skill/references/a.md"])

    def test_collect_run_flags_missing_and_empty_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            lib.write_json(run_dir / "config.json", {"executor": "e", "systems": ["a", "b"], "batches": [["q01", "q02"]]})
            lib.write_text(run_dir / "outputs" / "a" / "q01.txt", "Готовый текст длиннее двадцати знаков.\r\n\r\n")
            lib.write_text(run_dir / "outputs" / "a" / "q02.txt", "Готовый текст длиннее двадцати знаков.")
            lib.write_text(run_dir / "outputs" / "b" / "q01.txt", "  ")
            missing = batches.collect_run(run_dir)
            first = (run_dir / "outputs" / "a" / "q01.txt").read_bytes()
            rows = (run_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(missing, ["b/q01", "b/q02"])
        self.assertEqual(first, "Готовый текст длиннее двадцати знаков.\n".encode("utf-8"))
        self.assertEqual(len(rows), 2)

    def test_judge_bundles_are_blind_and_map_back(self):
        judge_name = "claude-code/opus-5.5"
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for s, body in {"ours": "Вариант один.", "ours411": "Вариант два.", "ilyautov332": "Вариант три."}.items():
                lib.write_text(d / "run" / "outputs" / s / "q01.txt", body)
            lib.write_text(d / "texts" / "q01.txt", "Исходник.")
            tasks = batches.prepare_judge(d / "run", d / "texts", d / "batch", judge_name, ["q01"], 6)
            jdir = d / "batch" / "judge-claude-code-opus-5.5"
            seen = (jdir / "bundles" / "q01.md").read_text(encoding="utf-8") + tasks[0].read_text(encoding="utf-8")
            key = json.loads((d / "batch" / "judge-claude-code-opus-5.5-keys.json").read_text(encoding="utf-8"))["q01"]
            answer = {"candidates": {"A": {"fact_errors": ["потеряна дата"], "send_as_is": 3},
                                     "B": {"fact_errors": [], "send_as_is": 8}, "C": {"fact_errors": [], "send_as_is": 6}},
                      "ranking": ["B", "C", "A"], "comment": "к"}
            lib.write_text(jdir / "answers" / "q01.json", "```json\n%s\n```" % json.dumps(answer, ensure_ascii=False))
            first = batches.collect_judge(d / "run", d / "batch", judge_name)
            again = batches.collect_judge(d / "run", d / "batch", judge_name)
            rows = [json.loads(x) for x in (d / "run" / "judgments.jsonl").read_text(encoding="utf-8").splitlines()]
        for name in ("ours", "ilyautov"):
            self.assertNotIn(name, seen)
        self.assertIn("Вариант один.", seen)
        self.assertEqual((first["added"], again["added"], len(rows)), (1, 0, 1))
        self.assertEqual(rows[0]["ranking"], [key["B"], key["C"], key["A"]])
        self.assertEqual(rows[0]["candidates"][key["A"]]["fact_errors"], ["потеряна дата"])
        self.assertEqual(rows[0]["judge"], judge_name)



class EvalPatternsTest(unittest.TestCase):
    """R-PATTERN-COUNT: per pattern and system, survived of source texts and introduced ones."""

    def test_removed_kept_and_introduced(self):
        sources = {"a": "Важно отметить, что цена 300 рублей.", "b": "Цена 300 рублей.", "c": "Важно отметить."}
        outputs = {"good": {"a": "Цена 300 рублей.", "b": "Цена 300 рублей."},
                   "bad": {"a": "Важно отметить: цена 300 рублей.", "b": "Стоит отметить, что цена 300 рублей.",
                           "c": "Важно отметить."}}
        row = patterns.survival(sources, outputs)["important_to_note"]
        self.assertEqual(row["in_sources"], 2)
        self.assertEqual(row["good"], {"survived": 0, "of": 1, "introduced": 0})
        self.assertEqual(row["bad"], {"survived": 2, "of": 2, "introduced": 1})

    def test_hedges_and_real_ranges_are_not_patterns(self):
        text = "В целом впечатление хорошее. Отвечаете за качество от приёмки молока до выпуска сыра."
        table = patterns.survival({"x": text}, {"s": {"x": text}})
        self.assertTrue(all(row["in_sources"] == 0 for row in table.values()))

    def test_ne_pro_contrast_with_or_without_eto(self):
        src = {"x": "Ozon — не про «душу», а про цифры.", "y": "Это не про деньги."}
        self.assertEqual(patterns.survival(src, {})["ne_pro"]["in_sources"], 2)

    def test_assistant_utm_but_not_author_utm(self):
        table = patterns.survival({"x": "https://a.ru/?utm_source=openai https://b.ru/?utm_source=newsletter"}, {})
        self.assertEqual(table["assistant_utm"]["in_sources"], 1)


if __name__ == "__main__":
    unittest.main()
