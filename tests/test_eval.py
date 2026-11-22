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

    def test_share_interval_tells_noise_from_a_real_gap(self):
        # 4.1.7: a 46% share on 24 texts is reported with its 95% interval, which holds 50%.
        def rows_for(wins_of_x, n=24, judges=("argon", "kimi", "muse")):
            return [{"id": "t%02d" % i, "judge": j, "ranking": ["x", "y"] if i < wins_of_x else ["y", "x"]}
                    for i in range(n) for j in judges]
        ids = {"t%02d" % i for i in range(24)}
        lo, hi = report.share_interval(rows_for(11), ids, "x", "y")
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        lo, hi = report.share_interval(rows_for(22), ids, "x", "y")
        self.assertGreater(lo, 0.5)
        # same judgments, same interval; the share inside it is the one aggregate reports
        self.assertEqual(report.share_interval(rows_for(11), ids, "x", "y"),
                         report.share_interval(rows_for(11), ids, "x", "y"))
        self.assertTrue(lo <= 22 / 24 <= hi)
        # rank judges are respected and one text cannot give an interval
        self.assertIsNone(report.share_interval(rows_for(1, n=1), {"t00"}, "x", "y"))
        self.assertIsNone(report.share_interval(rows_for(11), ids, "x", "y", rank_judges={"nobody"}))
        self.assertIn("не отличить от 50%", report._with_interval(0.46, (0.3, 0.6)))
        self.assertIn("выше 50%", report._with_interval(0.9, (0.8, 0.97)))

    def test_agreed_wins_need_every_pass_and_sign_test_is_exact(self):
        # 4.2.0 rule: a win counts only when both shuffles put ours above; a split is a tie.
        def row(tid, rnd, rank, judge="opus"):
            return {"id": tid, "judge": judge, "round": rnd, "ranking": rank}
        rows = [row("a", 0, ["x", "y"]), row("a", 1, ["x", "y"]),      # win
                row("b", 0, ["x", "y"]), row("b", 1, ["y", "x"]),      # split: tie
                row("c", 0, ["y", "x", "z"]), row("c", 1, ["z", "y", "x"]),  # loss
                row("d", 0, ["x", "y"]), row("d", 1, ["y", "x"], judge="sol")]
        self.assertEqual(report.agreed_record(rows, {"a", "b", "c", "d"}, "x", "y"),
                         {"wins": 1, "losses": 1, "ties": 2, "texts": 4})
        # Sol only votes on facts: with rank judges = opus, text d is decided by opus alone
        self.assertEqual(report.agreed_record(rows, {"a", "b", "c", "d"}, "x", "y", rank_judges={"opus"}),
                         {"wins": 2, "losses": 1, "ties": 1, "texts": 4})
        # exact one-sided binomial: 17 of 24 is the first count below 0.05 (README: 71%)
        self.assertAlmostEqual(report.sign_test(17, 7), 536155 / 2 ** 24)
        self.assertGreater(report.sign_test(16, 8), 0.05)
        self.assertEqual(report.critical_wins(24), 17)
        self.assertIsNone(report.critical_wins(4))  # 4 of 4 is p = 1/16: four texts can never decide
        self.assertEqual(report.sign_test(0, 0), 1.0)

    def test_release_gates_two_and_three(self):
        rows = [{"id": t, "judge": "opus", "round": r, "ranking": ["ours", "ours417"]} for t in ("f01", "f02") for r in (0, 1)]
        src = "Встреча 12 марта в 10:00, взнос 500 ₽."
        outputs = {("ours", "f01"): src, ("ours417", "f01"): src, ("ours", "f02"): src, ("ours417", "f02"): src,
                   ("ours", "wn1"): src, ("ours417", "wn1"): "Встреча в марте, взнос 500 ₽."}
        sources = {"f01": src, "f02": src, "wn1": src}
        table, _, _ = report.aggregate(rows, {"f01", "f02"}, outputs, sources)
        result = {"groups": {"ai": {"ids": ["f01", "f02"], "table": table}, "human": {"ids": ["wn1"]}}}
        gates = report.release_gates(result, rows, outputs, sources, "ours", "ours417")
        self.assertEqual([g[1] for g in gates], [True, True])
        self.assertIn("2:0", gates[0][2])
        # the previous version keeps the facts on the human text and ours loses one: gate 3 fails
        outputs[("ours", "wn1")], outputs[("ours417", "wn1")] = outputs[("ours417", "wn1")], src
        gates = report.release_gates(result, rows, outputs, sources, "ours", "ours417")
        self.assertFalse(gates[1][1])
        # without the previous version in the run there is nothing to gate
        self.assertEqual(report.release_gates(result, rows, outputs, sources, "ours", "ours410"), [])
        # a run without judges still gets its human-text table from the outputs
        table, _, _ = report.aggregate([], {"wn1"}, outputs, sources)
        self.assertEqual(sorted(table), ["ours", "ours417"])
        self.assertIsNone(table["ours"]["mean_position"])


class EvalDshRouteTest(unittest.TestCase):
    """R-EVAL-DSH: only the owner's free routes, no paid fallback, nothing booked, plain reply."""

    def test_executor_without_tools_gets_every_skill_file_in_the_prompt(self):
        # 4.1.7: the DSH route refuses tool calls, so run_systems puts the references in the prompt.
        files = {"SKILL.md": "Правила.", "references/patterns.md": "Признаки.", "references/examples.md": "Примеры."}
        system = rs.PREAMBLE.format(files="SKILL.md, references/examples.md, references/patterns.md", skill="Правила.")
        inline = rs.inline_system(system, files)
        self.assertNotIn("read_file", inline)
        self.assertIn('<файл path="references/patterns.md">\nПризнаки.\n</файл>', inline)
        self.assertLess(inline.index("examples.md\">"), inline.index("patterns.md\">"))
        self.assertEqual(rs.inline_system("Просто просьба.", {}), "Просто просьба.")
        self.assertEqual(rs.inline_system(system, {"SKILL.md": "Правила."}), system)

    def test_task_text_rules_then_system_then_user(self):
        text = lib.dsh_task_text([{"role": "user", "content": "USER-REQ"}, {"role": "system", "content": "SYS-INSTR"}])
        self.assertTrue(text.startswith(lib.DSH_RULES))
        self.assertLess(text.index("SYS-INSTR"), text.index("USER-REQ"))
        with self.assertRaises(ValueError):
            lib.dsh_task_text([{"role": "assistant", "content": "x"}])
        with self.assertRaises(ValueError):
            lib.dsh_task_text([{"role": "tool", "content": "x"}])

    def test_task_text_writes_out_an_earlier_answer(self):
        # M5 on 2026-11-09: the interview's third turn (answer + the author's reply) failed on the
        # dsh route in 11 of 24 jobs, since only system and user messages were taken.
        text = lib.dsh_task_text([{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q1"},
                                  {"role": "assistant", "content": "A1"}, {"role": "user", "content": "Q2"}])
        self.assertTrue(text.startswith(lib.DSH_RULES))
        order = [text.index(x) for x in ("SYS", lib.DSH_TURNS["user"] + "\nQ1", lib.DSH_TURNS["assistant"] + "\nA1",
                                         lib.DSH_LAST + "\nQ2")]
        self.assertEqual(order, sorted(order))
        with self.assertRaises(ValueError):
            lib.dsh_task_text([{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}])

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
        self.assertIn("--bare", cmd)  # R-BARE-EXECUTOR: the installed skill must not answer for a participant
        self.assertEqual(cmd[cmd.index("--model") + 1], "agentrouter-astra/gpt-6.1-sol")
        self.assertEqual((msg["content"], usage["cost"], usage["listed_cost"]), ("текст", 0.0, 0.0123))
        ledger.assert_not_called()

    def test_plan_quota_closes_the_route_without_retries(self):
        # 09.11: after the MiniMax Token Plan ended, a run retried 24 calls 3 times each.
        quota = {"ok": False, "failKind": None, "stderrTail": [
            'dsh: RATE_LIMIT: 429: {"type":"rate_limit_error","message":"已达到 Token Plan 用量上限：请升级"}']}
        reply = mock.Mock(stdout=json.dumps(quota), stderr="", returncode=0)
        msgs = [{"role": "user", "content": "x"}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lib, "CACHE_DIR", Path(d)), \
                mock.patch.object(lib, "EXHAUSTED", set()), mock.patch.object(lib.time, "sleep") as sleep, \
                mock.patch.object(lib.subprocess, "run", return_value=reply) as run:
            with self.assertRaises(lib.QuotaExhausted):
                lib.chat("dsh:minimax/MiniMax-M3.1-Flash", msgs)
            self.assertEqual(run.call_count, 1)  # no retries
            with self.assertRaises(lib.BudgetExceeded):  # run_systems stops on it
                lib.chat("dsh:minimax/MiniMax-M3.1-Flash", msgs)
            self.assertEqual(run.call_count, 1)  # nothing sent after the quota ended
            sleep.assert_not_called()
        # The bridge itself refuses a route whose quota it remembers (R-QUOTA-STOP): same stop, no retries.
        refused = {"ok": False, "state": "refused", "error": "minimax/MiniMax-M3.1-Flash: its plan quota has run out"}
        reply = mock.Mock(stdout=json.dumps(refused), stderr="", returncode=2)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lib, "CACHE_DIR", Path(d)), \
                mock.patch.object(lib, "EXHAUSTED", set()), mock.patch.object(lib.time, "sleep"), \
                mock.patch.object(lib.subprocess, "run", return_value=reply) as run:
            with self.assertRaises(lib.QuotaExhausted):
                lib.chat("dsh:minimax/MiniMax-M3.1-Flash", msgs)
            self.assertEqual(run.call_count, 1)

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
        self.assertIn("Do not run scripts or commands and do not read any other files.", bodies[0])

    def test_prepare_run_with_scripts_for_gate_four(self):
        # 4.2.0 gate 4: the executor gets the real skill scripts and may run only them.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            lib.write_text(d / "texts" / "q01.txt", "Исходник.")
            ours = next(s for s in lib.read_json(lib.EVAL_DIR / "systems.json") if s["name"] == "ours")
            lib.write_text(d / "texts" / "q02.txt", "Второй.")
            tasks = batches.prepare_run([ours], [["q01"], ["q02"]], d / "batch", d / "run", d / "texts", "exec",
                                        scripts=True)
            body, body2 = (t.read_text(encoding="utf-8") for t in tasks)
            system = (d / "batch" / "ours" / "system.txt").read_text(encoding="utf-8")
            copied = sorted(p.name for p in (d / "batch" / "ours" / "skill" / "scripts").iterdir())
            cfg = lib.read_json(d / "run" / "config.json")
        self.assertIn("except the skill scripts named below", body)
        self.assertIn((d / "batch" / "ours" / "skill").as_posix() + "/scripts/check_facts.py", body)
        # Cross-review 09.11. F4: each batch has its own temp folder. F5: the system prompt no longer
        # says the scripts cannot run.
        self.assertIn((d / "batch" / "tmp" / "ours" / "batch1").as_posix(), body)
        self.assertIn((d / "batch" / "tmp" / "ours" / "batch2").as_posix(), body2)
        self.assertNotIn("batch2", body)
        self.assertNotIn("запустить нельзя", system)
        self.assertIn((d / "batch" / "ours" / "skill").as_posix() + "/scripts", system)
        self.assertEqual(copied, ["check_facts.py", "clean_paste.py", "lint_style.py", "rules.json"])
        self.assertTrue(cfg["scripts"])

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
            batches.prepare_judge(d / "run", d / "texts", d / "batch", judge_name, ["q01"], 6, rnd=1)
            lib.write_text(d / "batch" / "judge-claude-code-opus-5.5-r1" / "answers" / "q01.json",
                           json.dumps(answer, ensure_ascii=False))
            second = batches.collect_judge(d / "run", d / "batch", judge_name, rnd=1)
            rows = [json.loads(x) for x in (d / "run" / "judgments.jsonl").read_text(encoding="utf-8").splitlines()]
        for name in ("ours", "ilyautov"):
            self.assertNotIn(name, seen)
        self.assertIn("Вариант один.", seen)
        self.assertEqual((first["added"], again["added"], second["added"], len(rows)), (1, 0, 1, 2))
        self.assertEqual([r["round"] for r in rows], [0, 1])
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


class EvalProbesTest(unittest.TestCase):
    """V-M-EVAL-PROBES: each oracle holds on a correct edit and fails on the edit that breaks
    the rule it stands for; the real probe bank is well formed."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("eval_probes", EVAL / "probes.py")
        cls.probes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.probes)

    def ok(self, probe, out):
        return all(self.probes.score_one(probe, out).values())

    def test_notes_after_the_last_rule_are_not_the_edit(self):
        # R-NOTES-NOT-TEXT (09.11, after the bare probe run): «Три вопроса» and a quoted source
        # phrase in the notes were scored as an added number and an added quote.
        src = "Я давно хотел поделиться своим опытом перехода в IT. Это был непростой путь."
        probe = {"id": "t", "rule": "interview", "text": src, "facts": True, "asks": True}
        good = ("Давно хотел рассказать, как перешёл в IT. Путь был непростой.\n\n---\n\n"
                "- Убрал «Это был… путь, который…».\n- Три вопроса:\n  1. Сколько времени занял переход?")
        self.assertTrue(self.ok(probe, good))
        invented = good.replace("Путь был непростой.", "За 2 года путь был непростой.")
        self.assertFalse(self.ok(probe, invented))  # a number added to the text itself still fails

    def test_legal_probe_keeps_the_phrase_at_a_sentence_start(self):
        # Cross-review 10.11 F2: the pr40 amendment made «нарушает мои права» case-sensitive, so a split
        # sentence starting «Нарушает мои права…» failed with every fact in place.
        pr40 = next(p for p in self.probes.lib.read_json(self.probes.PROBES) if p["id"] == "pr40")
        split = ("Прошу в установленном законом порядке вернуть уплаченные за товар денежные средства в размере "
                 "6 990 рублей, поскольку товар имеет существенный недостаток. Нарушает мои права как "
                 "потребителя именно этот недостаток.")
        self.assertTrue(self.ok(pr40, split))
        self.assertFalse(self.ok(pr40, split.replace("Нарушает мои права", "Это плохо")))

    def test_apology_probes_keep_the_names_and_drop_the_filler(self):
        # Cross-review 10.11 F1: the genres.md line on names in a shortened apology came from holdout4 f14;
        # its dev cases are the apology_names probes.
        bank = {p["id"]: p for p in self.probes.lib.read_json(self.probes.PROBES)}
        pr61 = bank["pr61"]
        good = ("Здравствуйте, Марина! Простите за долгое ожидание в мастерской «Синий ключ» на Садовой. "
                "Мастер уже вернул вам 500 рублей за срочный ремонт.")
        self.assertTrue(self.ok(pr61, good))
        self.assertFalse(self.ok(pr61, good.replace(" в мастерской «Синий ключ» на Садовой", "")))
        self.assertFalse(self.ok(pr61, pr61["text"]))  # the filler left in place fails too
        self.assertEqual(sum(1 for p in bank.values() if p["rule"] == "apology_names"), 4)

    def test_split_notes_cuts_only_the_answer_own_rule(self):
        split = self.probes.lib.split_notes
        self.assertEqual(split("Текст.\n---\n- заметка"), ("Текст.", "- заметка"))
        self.assertEqual(split("Без заметок."), ("Без заметок.", ""))
        src = "Часть 1.\n---\nЧасть 2."
        self.assertEqual(split("Часть первая.\n---\nЧасть вторая.", src), ("Часть первая.\n---\nЧасть вторая.", ""))
        self.assertEqual(split("Часть 1.\n---\nЧасть 2.\n\n---\n- заметка", src), ("Часть 1.\n---\nЧасть 2.", "- заметка"))
        # Cross-review 09.11 (F1, F4): the edit removed a chat wrapper with its own "---" lines
        # (holdout4 f01, f03, f19 ...) and added one "---" before its notes: still cut.
        wrapped = "Вот пост:\n---\nСкидка 20% до воскресенья.\n---\nПара замечаний:\n- можно добавить эмодзи"
        self.assertEqual(split("Скидка 20% до воскресенья.\n\n---\n- Три вопроса: 1. Сколько лет кафе?", wrapped),
                         ("Скидка 20% до воскресенья.", "- Три вопроса: 1. Сколько лет кафе?"))
        self.assertEqual(split("Скидка 20% до воскресенья.\n---\nСверка скриптом: 1 число на месте", wrapped)[1],
                         "Сверка скриптом: 1 число на месте")
        # A source's own last section, kept or rewritten as prose, is never cut.
        two = "Итоги года.\n---\nВ 2025 году открыли 3 филиала и наняли 40 человек."
        self.assertEqual(split("Итоги года.\n---\nЗа 2025 год появились 3 филиала и 40 новых сотрудников.", two)[1], "")
        # A kept bulleted section of the source is the source's tail, not notes.
        rules = "Правила:\n---\n- вход до 22:00\n- дети до 7 лет бесплатно"
        self.assertEqual(split("Правила.\n---\n- вход до 22:00\n- дети до 7 лет — бесплатно", rules)[1], "")

    def test_split_notes_reads_what_the_tail_talks_about(self):
        # Cross-review 09.11, round 2. F1: notes that open with prose after a removed wrapper.
        split = self.probes.lib.split_notes
        wrapped = "Вот текст:\n---\nЗавтрак в «Крошке» с 8 утра.\n---\nЧто учтено: тон дружелюбный."
        self.assertEqual(split("Завтрак в «Крошке» с 8 утра.\n\n---\n\nУбрал обёртку, длина 683 знака.", wrapped),
                         ("Завтрак в «Крошке» с 8 утра.", "Убрал обёртку, длина 683 знака."))
        # F2: a source section rewritten in new words stays text, so invented hours are seen and
        # a kept term is not lost.
        hours = "Вход свободный.\n---\n- Работаем ежедневно."
        self.assertEqual(split("Вход свободный.\n---\n- Заходите каждый день с 9:00 до 21:00.", hours)[1], "")
        probe = {"id": "h", "rule": "no_add", "text": hours, "facts": True}
        self.assertFalse(self.ok(probe, "Вход свободный.\n---\n- Заходите каждый день с 9:00 до 21:00."))
        term = "Условия доставки.\n---\n- Срок: 3 дня."
        self.assertTrue(self.ok({"id": "d", "rule": "no_add", "text": term, "facts": True},
                                "Условия доставки.\n---\n- На доставку заказа требуется 3 дня."))
        # F3: merged sections whose last part is a list made of the source's own words.
        src = ("Вступление с суммой 450 ₽.\n\n---\n\nУсловия: скидка 20% действует только в приложении "
               "и только для новых карт до 30 ноября.")
        self.assertEqual(split("Вступление с суммой 450 ₽.\n\n---\n\n- только в приложении\n- до 30 ноября", src)[1], "")
        # Notes that quote the source a lot are still notes: quotes do not count as source words.
        quoting = "Это был непростой путь, который многому меня научил."
        self.assertEqual(split("Путь был непростой.\n---\n- Убрал «который многому меня научил».", quoting)[1],
                         "- Убрал «который многому меня научил».")
        # A text's own closing question after a separator the edit added is text (it3 n23).
        poll = "Закрывать ли проезд к набережной по выходным? Голосуйте в нашем канале."
        self.assertEqual(split("Новость.\n---\nЗакрывать ли проезд к набережной по выходным? Голосуйте в канале.",
                               poll)[1], "")
        # Notes longer than NOTE_MAX_CHARS are a section, not 1-3 short points.
        self.assertEqual(split("Текст.\n---\n" + "Убрал повтор. " * 100, "Текст.")[1], "")

    def test_oracles_read_the_edit_and_asks_reads_the_notes(self):
        # Cross-review 09.11 (F3): «Убрал слово "шедевр"» in the notes must not fail drop:шедевр,
        # and a phrase kept only in the notes must not pass keep; questions live in the notes.
        probe = {"id": "t", "rule": "x", "text": "Этот фильм настоящий шедевр. Сходите на него.",
                 "drop": ["шедевр"], "keep": ["Сходите"]}
        self.assertTrue(self.ok(probe, "Хороший фильм. Сходите на него.\n\n---\n- Убрал «шедевр»."))
        self.assertFalse(self.ok(probe, "Хороший фильм.\n\n---\n- «Сходите на него» убрал."))
        asks = {"id": "a", "rule": "interview", "text": "Было интересно.", "asks": True}
        self.assertTrue(self.ok(asks, "Было интересно.\n\n---\n- Что именно понравилось?"))

    def test_bank_is_well_formed(self):
        bank = json.loads((EVAL / "corpus" / "probes.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(bank), 60)
        self.assertEqual(len({p["id"] for p in bank}), len(bank))
        rules = {p["rule"] for p in bank}
        self.assertGreaterEqual(len(rules), 15)
        for p in bank:
            oracles = [k for k in p if k in self.probes.ORACLES]
            self.assertTrue(oracles, p["id"])
            self.assertEqual(set(p) - set(self.probes.ORACLES) - {"id", "rule", "text", "request"}, set(), p["id"])
            # A probe that demands a change gives the unedited source no free pass.
            demands = p["rule"] in ("no_add", "gram_dash", "false_contrast", "chat_wrapper", "interview")
            if demands and any(k in p for k in ("drop", "asks", "bold_less")):
                self.assertFalse(self.ok(p, p["text"]), p["id"])

    def test_keep_and_keep_any_ignore_case_and_yo(self):
        p = {"text": "x", "keep": ["Соколов"], "keep_any": [["по словам", "считает"]]}
        self.assertTrue(self.ok(p, "Как считает Ирина СОКОЛОВА, ходьба полезна."))
        self.assertFalse(self.ok(p, "Ходьба полезна."))
        self.assertTrue(self.ok({"text": "x", "keep": ["тёмная"]}, "темная тема"))

    def test_drop_and_keep_re_are_regexes(self):
        p = {"text": "x", "drop": ["не просто\\b[^.!?]{0,80},\\s*а\\b"], "keep_re": ["[Кк]эш\\s+—"]}
        self.assertTrue(self.ok(p, "Кэш — быстрая память. Кофейня с 40 местами."))
        self.assertFalse(self.ok(p, "Кэш — быстрая память. Это не просто кофейня, а место встреч."))
        self.assertFalse(self.ok(p, "Кэш является быстрой памятью."))

    def test_facts_oracle_catches_lost_and_added_facts(self):
        # A lost hedge is only a "check" for check_facts, so probes name hedges in keep_any.
        p = {"text": "Ремонт займёт примерно три недели, стоимость 4 500 рублей.", "facts": True,
             "keep_any": [["примерно", "около"]]}
        self.assertTrue(self.ok(p, "Ремонт займёт примерно три недели и обойдётся в 4 500 рублей."))
        self.assertFalse(self.ok(p, "Ремонт займёт три недели и обойдётся в 4 500 рублей."), "hedge lost")
        self.assertFalse(self.ok(p, "Ремонт займёт примерно три недели и обойдётся в 5 000 рублей."))
        self.assertFalse(self.ok({"text": "Курс по Excel.", "facts": True}, "В курсе 12 уроков по Excel."))

    def test_yo_asks_lists_bold_counts_similarity_length(self):
        P = self.probes
        self.assertTrue(all(P.score_one({"text": "Артём Королёв", "yo": True}, "Шеф Артём Королёв").values()))
        self.assertFalse(all(P.score_one({"text": "Артём Королёв", "yo": True}, "Шеф Артем Королев").values()))
        self.assertTrue(self.ok({"text": "Кофейня.", "asks": True}, "Кофейня.\n\n---\nКакой у вас фирменный напиток?"))
        self.assertFalse(self.ok({"text": "Кофейня?", "asks": True}, "Кофейня?"))
        steps = "1. Раз.\n2) Два.\n- три\n**Шаг 4.** Четыре"
        self.assertTrue(self.ok({"text": "x", "list_items": 4}, steps))
        self.assertFalse(self.ok({"text": "x", "list_items": 4}, "Раз, два, три и четыре."))
        self.assertTrue(self.ok({"text": "**a** **b**", "bold_less": True}, "**a** b"))
        self.assertFalse(self.ok({"text": "**a**", "bold_less": True}, "**a**"))
        self.assertTrue(self.ok({"text": "x", "min_count": [["20%", 2]]}, "20% и снова 20%"))
        self.assertFalse(self.ok({"text": "x", "min_count": [["20%", 2]]}, "20%"))
        legal = "Арендатор обязуется вносить арендную плату не позднее 5 числа каждого месяца."
        self.assertTrue(self.ok({"text": legal, "min_similarity": 0.9}, legal))
        self.assertFalse(self.ok({"text": legal, "min_similarity": 0.9}, "Платите аренду до пятого."))
        self.assertFalse(self.ok({"text": "Скидки до 31 января, до 40%.", "min_len_ratio": 0.4}, "ГОТОВО"))

    def test_summary_counts_runs_and_spread(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            bank = {p["id"]: p for p in json.loads((EVAL / "corpus" / "probes.json").read_text(encoding="utf-8"))}
            good = bank["pr20"]["text"]
            for rnd, text in (("r0", good), ("r1", "Мы отключаем API.")):
                path = run_dir / "probes" / "ours" / rnd / "pr20.txt"
                path.parent.mkdir(parents=True)
                path.write_text(text, encoding="utf-8")
            s = self.probes.summarize(run_dir)
            cell = s["table"]["ours"]["false_contrast"]
            self.assertEqual((cell["passed"], cell["total"], cell["per_run"], cell["spread"]), (1, 2, [1, 0], 1))
            self.assertIn("pr20 keep:не весь", s["fails"]["ours"])
            self.assertIn("| false_contrast | 1/2 (1, 0) |", self.probes.render(s, "t"))


class EvalNewMeasuresTest(unittest.TestCase):
    """4.2.0 measures: frequency candidates, interview gate, voice gate (README «Замер 4.2.0»)."""

    def test_log_odds_leans_to_the_side_that_uses_a_phrase(self):
        import style_freq as sf
        ai = [sf.doc_ngrams("Стоит отметить, что матч прошёл в Палермо.") for _ in range(20)]
        hu = [sf.doc_ngrams("Матч прошёл в Палермо и закончился 9:1.") for _ in range(20)]
        z = sf.log_odds(ai, hu)
        # 20 of 20 texts against 0 of 20: z = 3.67 with 0.5 added to every cell
        self.assertGreater(z["стоит отметить"][0], 3)
        self.assertLess(z["закончился"][0], -3)
        self.assertAlmostEqual(z["стоит отметить"][0], max(v[0] for v in z.values()))  # tied with its own words
        self.assertAlmostEqual(z["палермо"][0], 0.0, places=6)  # both sides: no lean
        self.assertEqual(z["стоит отметить"][1:], (20, 0))  # document counts, not repeats
        self.assertNotIn("9", " ".join(sf.doc_ngrams("Счёт 9:1, 2 гола.")))  # numbers are topic, not style

    def test_receipt_line_and_its_counts(self):
        # Gate 4 (M4): the line is found in the notes and its numbers are compared with check_facts.
        import receipt_eval as re_
        src = "Скидка 20% до 30 ноября. Пишите Анне."
        good = "Скидка 20% до 30 ноября. Пишите Анне.\n\n---\n- Убрал повтор.\nСверка скриптом: 1 число, 1 дата, 1 имя на месте"
        r = re_.score_one(src, good)
        self.assertEqual(r["stated"], {"number": 1, "date": 1, "name": 1})
        self.assertTrue(r["counts_match"])
        self.assertEqual(r["script_errors"], [])
        wrong = re_.score_one(src, good.replace("1 число", "3 числа"))
        self.assertFalse(wrong["counts_match"])
        self.assertEqual(wrong["wrong_counts"], {"number": (3, 1)})
        none = re_.score_one(src, "Скидка до 30 ноября. Пишите Анне.")
        self.assertEqual((none["line"], none["counts_match"]), ("", False))
        self.assertIn("20%", none["script_errors"])
        # Since 4.2.0 the agent copies the script's own line; it is compared word for word.
        copied = "Скидка 20% до 30 ноября. Пишите Анне.\n\n---\n- Сверка скриптом: 1 число, 1 дата, 1 имя или название на месте."
        r = re_.score_one(src, copied)
        self.assertEqual(r["expected"], "Сверка скриптом: 1 число, 1 дата, 1 имя или название на месте.")
        self.assertTrue(r["same_line"])
        self.assertFalse(re_.score_one(src, good)["same_line"])  # retold, not copied
        lost = re_.score_one(src, "Скидка до 30 ноября. Пишите Анне.\n\n---\n"
                                  "Сверка скриптом: в исходнике 1 число, 1 дата, 1 имя или название; в правке нет: 20%")
        self.assertTrue(lost["same_line"])
        why = re_.score_one(src, "Скидка до 30 ноября. Пишите Анне.\n\n---\n"
                                 "Сверка скриптом: в исходнике 1 число, 1 дата, 1 имя; в правке нет только 20% из приписки бота")
        self.assertEqual((why["same_line"], why["facts_ok"]), (False, True))  # reworded, facts right
        self.assertFalse(re_.score_one(src, "Скидка до 30 ноября. Пишите Анне.\n\n---\n"
                                            "Сверка скриптом: 1 число, 1 дата, 1 имя на месте")["facts_ok"])
        # probes-ours-2026-11-10 ours/r1/pr58, no terminal: an honest «not run» note is not a receipt line.
        self.assertEqual(re_.receipt_line("Текст.\n\n---\n- Сверка скриптом не проводилась: команды не "
                                          "запускаются."), "")
        self.assertTrue(re_.receipt_line("Текст.\n\n---\n- Сверка скриптом: 2 числа на месте."))

    def test_probe_config_keeps_every_participant(self):
        # Cross-review 09.11 (F4): the chat/prompt run overwrote the record of ours/ours417.
        import probes as pb
        old = {"executor": "dsh:minimax/MiniMax-M3.1-Flash", "systems": ["ours", "ours417"], "repeat": 2}
        new = pb.merge_config(old, ["chat"], "dsh:agentrouter-astra/gpt-6.1-sol", 1)
        self.assertEqual(set(new["by_system"]), {"ours", "ours417", "chat"})
        self.assertEqual(new["by_system"]["ours"]["executor"], "dsh:minimax/MiniMax-M3.1-Flash")
        self.assertEqual(new["by_system"]["chat"], {"executor": "dsh:agentrouter-astra/gpt-6.1-sol", "repeat": 1})
        self.assertEqual(pb.merge_config(new, ["ours"], "x", 3)["by_system"]["chat"]["repeat"], 1)

    def test_frontier_scorer_reads_the_edit_without_its_notes(self):
        # Frontier arm (eval/README, 09.11 21:00 UTC): facts and style of the edit, notes cut first.
        import frontier_eval as fe
        src = "Скидка 20% до 30 ноября. Подробнее: https://kolos.ru/?utm_source=chatgpt.com"
        clean = fe.score_text(src, "Скидка 20% до 30 ноября. Подробнее: https://kolos.ru/\n\n---\n"
                                   "Сверка скриптом: 1 число, 1 дата, 1 ссылка на месте.")
        self.assertEqual(clean["errors"], [])
        self.assertTrue(clean["receipt"])
        self.assertEqual(clean["lint_score"], 0.0)
        dirty = fe.score_text(src, "Скидка до 30 ноября. Подробнее: https://kolos.ru/?utm_source=chatgpt.com")
        self.assertIn(["lost", "число", "20%"], dirty["errors"])
        self.assertGreater(dirty["lint_score"], 0)
        s = fe.summarize({"a": clean, "b": dirty})
        self.assertEqual((s["texts_with_errors"], s["errors"], s["receipts"]), (["b"], 1, 1))

    def test_frontier_scorer_lists_the_chat_wrapper_apart(self):
        # Cross-review 10.11 F3: values from the chat's own head and tail («Готовый пост (≈683 знака)»,
        # «в лимит 1200») counted as lost facts of the edit.
        import frontier_eval as fe
        src = ("Готовый пост (≈683 знака):\n\n---\n\nСкидка 20% до 30 ноября в кафе «Клён».\n\n---\n\n"
               "Объём в лимит 1200 знаков.")
        self.assertEqual(fe.text_part(src), "Скидка 20% до 30 ноября в кафе «Клён».")
        self.assertEqual(fe.text_part("Без черты 5 раз."), "Без черты 5 раз.")
        sections = "# Памятка\n\nШаг 1: 5 минут.\n\n---\n\n## После\n\nЕщё 7 пунктов, длинный раздел текста."
        self.assertEqual(fe.text_part(sections), sections)  # «---» between sections is text
        self.assertEqual(fe.text_part("Текст письма, 3 пункта.\n\n---\n\nЕсли нужно, могу сделать короче."),
                         "Текст письма, 3 пункта.")
        r = fe.score_text(src, "Скидка 20% до 30 ноября в кафе «Клён».")
        self.assertEqual(r["errors"], [])
        self.assertTrue(r["wrapper"])
        lost = fe.score_text(src, "Скидка до 30 ноября в кафе «Клён».")
        self.assertIn(["lost", "число", "20%"], lost["errors"])
        self.assertNotIn(["lost", "число", "20%"], lost["wrapper"])
        self.assertEqual(fe.summarize({"a": r, "b": lost})["errors"], 1)

    def test_run_sets_are_a_comma_list(self):
        # Plan v3 M3: holdout4 with the six saved chatbot answers, without traps (they are in M2).
        index = lib.read_json(lib.EVAL_DIR / "corpus" / "index.json")
        h4 = ",".join(["f%02d" % i for i in range(1, 37)] + ["r%02d" % i for i in range(1, 7)])
        ids = rs.select_ids(index, "holdout4,test", h4)
        self.assertEqual(len(ids), 42)
        self.assertEqual(len(rs.select_ids(index, "holdout4")), 42)  # 36 + 6 traps, as before
        self.assertTrue({"h01", "h06"} <= set(rs.select_ids(index, "holdout4")))
        with self.assertRaises(SystemExit):
            rs.select_ids(index, "holdout4,nosuchset")

    def test_pairs_index_names_the_model_that_wrote_each_pair(self):
        # Cross-review 09.11 (F6): gen rebuilt index.json from the current MODELS, so an old pair of
        # another model got the new label.
        import style_freq as sf
        with tempfile.TemporaryDirectory() as d:
            pairs = Path(d)
            lib.write_text(pairs / "wn01.txt", "старая пара\n")
            lib.write_text(pairs / "wn09.txt", "пара без записи\n")
            lib.write_json(pairs / "index.json", {"wn01": "dsh:old/model"})
            rows = [{"id": "wn01", "revision": 1}, {"id": "wn02", "revision": 2}]
            with mock.patch.object(sf, "PAIRS", pairs), mock.patch.object(sf, "pool_rows", return_value=rows), \
                    mock.patch.object(sf, "MODELS", ("dsh:new/model",)), \
                    mock.patch.object(sf, "_one", side_effect=lambda r, m: (r["id"], "новая\n")):
                sf.gen(1)
            index = lib.read_json(pairs / "index.json")
        self.assertEqual(index, {"wn01": "dsh:old/model", "wn02": "dsh:new/model"})

    def test_interview_questions_and_invented_facts(self):
        import interview_eval as iv
        answer = "Кофейня на Ленина.\n\n---\n- Что вы обжариваете сами?\n- Во сколько открываетесь?"
        self.assertEqual(iv.questions(answer), ["- Что вы обжариваете сами?", "- Во сколько открываетесь?"])
        self.assertEqual(iv.questions("Кофейня на Ленина."), [])
        # Cross-review 09.11 (F1, m5 ours/iv08): a question put as a request («Уточните …») with no «?»
        # was not a question, so the author never answered and the third turn was not checked.
        ask = ("Квартира в центре.\n\n---\n- Прилагательные заменил.\n- Уточните квартиру: сколько комнат, этаж.\n"
               "- Если есть подробности, скажите, и я впишу.")
        self.assertEqual(iv.questions(ask), ["- Уточните квартиру: сколько комнат, этаж."])
        self.assertEqual(iv.questions("Текст.\n\n---\n1. **Назовите** адрес и часы работы."),
                         ["1. **Назовите** адрес и часы работы."])
        added = iv._added("Кофейня на Ленина.", "Кофейня на Ленина, 14, с 8:00. Хозяйка Марина.")
        self.assertEqual(sorted(a.split(": ")[1] for a in added), ["14", "8:00", "Марина"])
        # what the author answered is not invented
        self.assertEqual(iv._added("Кофейня на Ленина.\n\nЛенина, 14; с 8:00; хозяйка Марина.",
                                   "Кофейня на Ленина, 14, с 8:00. Хозяйка Марина."), [])

    def test_voice_split_keeps_sample_and_target_apart(self):
        import voice_eval as ve
        text = "\n\n".join(("Абзац %d. " % i) + "слово " * 100 for i in range(30))
        sample, held, _ = ve.parts(text)
        n = lambda t: len(ve.voice_profile.WORD_RX.findall(t))
        self.assertTrue(600 <= n(sample) <= ve.SAMPLE_WORDS and 1100 <= n(held) <= ve.HELD_WORDS, (n(sample), n(held)))
        self.assertFalse(set(sample.split("\n\n")) & set(held.split("\n\n")))
        self.assertEqual(ve._body("Текст правки.\n\n---\n- заметка"), "Текст правки.")


class EvalOfflineFixesTest(unittest.TestCase):
    """G-EVAL-UNIT: deterministic offline tests for evallib, fetch_human, report, receipt_eval,
    interview_eval, probes, batches, patterns, frontier_eval, lint_calibrate, run_systems, judge,
    style_freq, and build_corpus."""

    def test_evallib_bom_crlf_ledger_and_openrouter_chat(self):
        import concurrent.futures
        import io as _io
        import urllib.error

        # CRLF split_notes keeps no \r in text or notes.
        text, notes = lib.split_notes("Текст правки.\r\n\r\n---\r\n- Убрал штамп.\r\n", "Исходник.")
        self.assertEqual((text, notes), ("Текст правки.", "- Убрал штамп."))
        self.assertNotIn("\r", text + notes)

        # UTF-8 BOM handled transparently by read_text and read_json.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bom.json"
            p.write_bytes(b"\xef\xbb\xbf" + '{"k": "привет"}'.encode("utf-8"))
            self.assertEqual(lib.read_json(p), {"k": "привет"})

            # Thread-safe Ledger with unique temp files and cap enforcement.
            led_path = Path(d) / "spend.json"
            with mock.patch.object(lib, "CACHE_DIR", Path(d)), mock.patch.object(lib, "LEDGER", led_path):
                led = lib.Ledger(cap=0.5)
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(lambda _: led.add("t", 0.05), range(6)))
                self.assertAlmostEqual(lib.read_json(led_path)["total"], 0.3, places=4)
                led.add("t", 0.25)
                with self.assertRaises(lib.BudgetExceeded):
                    led.check()

            # Mocked OpenRouter chat: retries 500, fails immediately on 401, books usage.cost.
            ok_body = json.dumps({"choices": [{"message": {"content": "ответ"}}], "usage": {"cost": 0.02}}).encode("utf-8")

            class _Resp:
                def __enter__(self):
                    return _io.BytesIO(ok_body)

                def __exit__(self, *a):
                    return False

            err500 = urllib.error.HTTPError("https://x", 500, "err", {}, _io.BytesIO(b"boom"))
            err401 = urllib.error.HTTPError("https://x", 401, "auth", {}, _io.BytesIO(b"bad key"))
            led_path2 = Path(d) / "spend2.json"
            with mock.patch.dict("os.environ", {"FAL_KEY": "test-key"}), \
                    mock.patch.object(lib, "CACHE_DIR", Path(d)), mock.patch.object(lib, "LEDGER", led_path2), \
                    mock.patch.object(lib, "_LEDGER", None), mock.patch.object(lib.time, "sleep"), \
                    mock.patch.object(lib.urllib.request, "urlopen", side_effect=[err500, _Resp()]) as uo:
                msg, usage = lib.chat("openai/test", [{"role": "user", "content": "hi"}], tag="unit")
                self.assertEqual((msg["content"], usage["cost"]), ("ответ", 0.02))
                self.assertEqual(uo.call_count, 2)
                self.assertAlmostEqual(lib.read_json(led_path2)["total"], 0.02, places=4)
            with mock.patch.dict("os.environ", {"FAL_KEY": "test-key"}), \
                    mock.patch.object(lib, "CACHE_DIR", Path(d)), mock.patch.object(lib, "LEDGER", led_path2), \
                    mock.patch.object(lib, "_LEDGER", None), mock.patch.object(lib.time, "sleep"), \
                    mock.patch.object(lib.urllib.request, "urlopen", side_effect=[err401]) as uo:
                with self.assertRaises(RuntimeError):
                    lib.chat("openai/test", [{"role": "user", "content": "hi"}], tag="unit")
                self.assertEqual(uo.call_count, 1)  # 401 stops immediately

        with mock.patch.dict("os.environ", {"DSH_TASK": "/custom/dsh-task.mjs"}):
            self.assertEqual(lib._default_dsh_task(), Path("/custom/dsh-task.mjs"))

    def test_fetch_human_paragraphs_handles_thumbcaption_div_depth(self):
        import fetch_human as fh
        html_doc = (
            "<p>Первый абзац<sup>[1]</sup> текста.</p>"
            '<div class="thumbcaption">Подпись к фото <div class="inner">вложенный блок</div> хвост</div>'
            "<p>Второй абзац после картинки.</p>"
            "<table><tr><td><p>Таблица пропущена</p></td></tr></table>"
            "<p>Третий абзац.</p>"
        )
        p = fh._Paragraphs()
        p.feed(html_doc)
        self.assertEqual(p.paras, ["Первый абзац текста.", "Второй абзац после картинки.", "Третий абзац."])
        self.assertEqual(p.skip, 0)

    def test_build_corpus_helpers(self):
        import build_corpus as bc
        self.assertEqual(bc.strip_header("\ufeffВопрос: x\nОтвет модели:\nСтрока.\n"), "Строка.\n")
        self.assertEqual(bc.strip_header("\ufeffПросто текст.\n"), "Просто текст.\n")
        self.assertIn("?utm_source=chatgpt.com", bc.inject("См. https://example.ru/a тут.", "utm"))
        self.assertIn(":contentReference[oaicite:0]{index=0}", bc.inject("Раз. Два. Три. Четыре.", "contentref"))
        self.assertIn("\u200b", bc.inject(" ".join(["слово"] * 10), "zwsp"))
        rows = [{"id": "wn%d" % i, "revision": i} for i in range(40)]
        self.assertEqual(len(bc.human_wikinews(rows)), 20)
        self.assertEqual(bc.human_wikinews(rows), bc.human_wikinews(list(reversed(rows))))

    def test_report_edge_cases_and_main_end_to_end(self):
        # String/None/bool fact_errors, None candidate, bool send_as_is, text_similarity alongside similarity.
        rows = [
            {"id": "t1", "judge": "j1", "round": 0, "ranking": ["ours", "rival"],
             "candidates": {
                 "ours": {"fact_errors": "нет", "send_as_is": True},
                 "rival": {"fact_errors": "потеряна дата", "send_as_is": 7},
                 "ghost": None,
             }},
            {"id": "t1", "judge": "j2", "round": 0, "ranking": ["ours", "rival"],
             "candidates": {
                 "ours": {"fact_errors": [None, False, "—"], "send_as_is": 8},
                 "rival": {"fact_errors": ["потеряна дата"], "send_as_is": 6},
             }},
        ]
        src = "Цена 500 рублей."
        outputs = {
            ("ours", "t1"): "Цена 500 рублей.\n\n---\n- Убрал повтор и штамп.",
            ("rival", "t1"): "Цена 500 рублей.",
        }
        table, _, _ = report.aggregate(rows, {"t1"}, outputs, {"t1": src})
        self.assertEqual(table["ours"]["texts_with_fact_errors"], [])
        self.assertEqual(table["rival"]["texts_with_fact_errors"], ["t1"])
        self.assertEqual(table["ours"]["send_as_is"], 8.0)  # bool True ignored
        self.assertLess(table["ours"]["similarity"], 1.0)  # raw similarity preserved
        self.assertEqual(table["ours"]["text_similarity"], 1.0)  # note-stripped similarity added alongside

        # Windows-safe slug for --judges without slash.
        self.assertEqual(report._out_slug("dsh:minimax"), "summary-dsh-minimax")
        self.assertNotIn(":", report._out_slug("dsh:a:b"))

        # main() end-to-end: errors-only coverage gap, non-dir inside outputs/, BOM judgments, mean_position=None, $0 label.
        with tempfile.TemporaryDirectory() as d:
            ed = Path(d)
            lib.write_json(ed / "corpus" / "index.json", [{"id": "t1", "kind": "generated", "set": "dev"}])
            lib.write_text(ed / "corpus" / "texts" / "t1.txt", "Цена 500 рублей.\n")
            run_dir = ed / "results" / "r1"
            lib.write_text(run_dir / "outputs" / "ours" / "t1.txt", "Цена 500 рублей.\n")
            lib.write_text(run_dir / "outputs" / "rival" / "t1.txt", "Цена 500 рублей.\n")
            lib.write_text(run_dir / "outputs" / "README.txt", "stray file\n")
            lib.write_json(run_dir / "config.json", {"executor": "dsh:minimax", "texts": ["t1"], "systems": ["ours", "rival"]})
            # All judge rows failed -> gaps must be ["t1"], not [].
            (run_dir / "judgments.jsonl").write_bytes(
                b"\xef\xbb\xbf" + (json.dumps({"id": "t1", "judge": "j1", "error": "unparsed", "cost": 0.0}) + "\n").encode("utf-8"))
            with mock.patch.object(lib, "EVAL_DIR", ed), mock.patch.object(lib, "CACHE_DIR", ed / ".cache"), \
                    mock.patch.object(lib, "LEDGER", ed / ".cache" / "spend.json"), mock.patch.object(lib, "_LEDGER", None):
                rc = report.main(["--run", "r1"])
            self.assertEqual(rc, 0)
            summary = lib.read_json(run_dir / "summary.json")
            self.assertEqual(summary["coverage_gaps"], ["t1"])
            md = lib.read_text(run_dir / "summary.md")
            self.assertIn("$0.00", md)

    def test_receipt_eval_all_seven_forms_strict_missing_and_main(self):
        import receipt_eval as re_
        line = "Сверка скриптом: 2 числа, 1 дата, 3 имени, 1 ссылка, 1 телефон, 2 цитаты, 1 отрицание на месте."
        self.assertEqual(re_.stated_counts(line), {
            "number": 2, "date": 1, "name": 3, "url": 1, "phone": 1, "quote": 2, "negation": 1,
        })
        # Dash & quote normalization in same_line().
        self.assertTrue(re_.same_line('Сверка скриптом: «А» — 1 число', 'Сверка скриптом: "А" - 1 число.'))
        # Strict 'в правке нет:' guard: missing "1" must NOT match "1 число" in counts prefix!
        src = "В списке 1."
        lie = "В списке.\n\n---\nСверка скриптом: 1 число на месте."
        self.assertFalse(re_.score_one(src, lie)["facts_ok"])
        honest = "В списке.\n\n---\nСверка скриптом: в исходнике 1 число; в правке нет: 1"
        self.assertTrue(re_.score_one(src, honest)["facts_ok"])
        # Receipt leaked in body (no ---) is flagged in_body and not counted as notes receipt.
        body_leak = "В списке 1.\nСверка скриптом: 1 число на месте."
        res_leak = re_.score_one(src, body_leak)
        self.assertEqual(res_leak["line"], "")
        self.assertTrue(res_leak["in_body"])
        # Missing outputs dir returns exit code 1.
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lib, "EVAL_DIR", Path(d)):
            self.assertEqual(re_.main(["--run", "missing", "--system", "ours"]), 1)

    def test_interview_eval_source_aware_cta_guard_and_score(self):
        import interview_eval as iv
        # Ad CTA without '---' is NOT an interview question to the author.
        self.assertEqual(iv.questions("Ищете хороший кофе?\nУкажите промокод COFFEE при заказе."), [])
        # Source with its own '---' section containing '?' is NOT stripped as notes!
        src = "Акция.\n---\nУкажите промокод или остались вопросы?"
        self.assertEqual(iv.questions(src, src), [])
        # merge_config preserves previous systems.
        cfg = iv.merge_config({"executor": "e1", "author": "a1", "systems": ["ours"]}, ["ours417"], "e2", "a2")
        self.assertEqual(set(cfg["by_system"]), {"ours", "ours417"})
        # Missing interview dir returns 1; valid run scores cleanly.
        with tempfile.TemporaryDirectory() as d:
            ed = Path(d)
            with mock.patch.object(lib, "EVAL_DIR", ed):
                self.assertEqual(iv.score("nope"), 1)
            cases_path = ed / "interview.json"
            lib.write_json(cases_path, [{"id": "iv01", "text": "Уютная кофейня.", "sheet": ["Адрес: Ленина, 5"]}])
            rec = {"id": "iv01", "turn1": "Кофейня.\n\n---\n- На какой улице вы находитесь?",
                   "answers": "На Ленина, 5.", "turn3": "Кофейня на Ленина, 5.\n\n---\n- Добавил адрес."}
            lib.write_json(ed / "results" / "r1" / "interview" / "ours" / "iv01.json", rec)
            with mock.patch.object(lib, "EVAL_DIR", ed), mock.patch.object(iv, "CASES", cases_path):
                self.assertEqual(iv.score("r1"), 0)
            scored = lib.read_json(ed / "results" / "r1" / "interview" / "interview.json")
            self.assertEqual(scored["table"]["ours"], {"cases": 1, "asked": 1, "invented": 0})

    def test_probes_yo_asks_bold_list_natural_sort_and_disjoint_rules(self):
        import probes as pb
        # всё -> все homograph is not a false failure; inflected тёплый -> теплым IS caught.
        self.assertTrue(pb.score_one({"text": "Скидка на всё до среды.", "yo": True}, "Скидка на все товары до среды.")["yo"])
        self.assertFalse(pb.score_one({"text": "Тёплый салат.", "yo": True}, "Подают с теплым салатом.")["yo"])
        # asks: body '?' without notes fails; source '?' removed + notes '?' passes; ASK_RX after --- passes.
        self.assertFalse(pb.score_one({"text": "Кофейня.", "asks": True}, "Ищете кофе?")["asks"])
        self.assertTrue(pb.score_one({"text": "Кофейня?", "asks": True}, "Кофейня.\n\n---\n- Какой адрес?")["asks"])
        self.assertTrue(pb.score_one({"text": "Кофейня.", "asks": True}, "Кофейня.\n\n---\n- Назовите адрес.")["asks"])
        # LIST_RX handles bolded **1.** items.
        self.assertTrue(pb.score_one({"text": "x", "list_items": 2}, "**1.** Раз.\n**2.** Два.")["list_items"])
        # render() unions rules across systems with disjoint rules; natural sort orders r2 before r10.
        summary = {
            "table": {
                "sysA": {"rule1": {"passed": 1, "total": 1, "per_run": [1], "spread": 0},
                         "_all": {"passed": 1, "total": 1, "per_run": [1], "spread": 0}},
                "sysB": {"rule2": {"passed": 1, "total": 1, "per_run": [1], "spread": 0},
                         "_all": {"passed": 1, "total": 1, "per_run": [1], "spread": 0}},
            },
            "fails": {},
        }
        md = pb.render(summary, "test")
        self.assertIn("| rule1 |", md)
        self.assertIn("| rule2 |", md)
        bank = {p["id"]: p for p in lib.read_json(pb.PROBES)}
        good_pr20 = bank["pr20"]["text"]
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            for rnd, txt in (("r0", good_pr20),
                             ("r2", good_pr20),
                             ("r10", "Мы отключаем API.")):
                lib.write_text(run_dir / "probes" / "ours" / rnd / "pr20.txt", txt)
            s = pb.summarize(run_dir)
            self.assertEqual(s["table"]["ours"]["false_contrast"]["per_run"], [1, 1, 0])
        # New embedded_quote and strengthened injection probes exist in probes.json.
        self.assertEqual(sum(1 for p in bank.values() if p["rule"] == "embedded_quote"), 4)
        self.assertGreaterEqual(sum(1 for p in bank.values() if p["rule"] == "injection"), 8)

    def test_batches_blank_lines_and_patterns_note_stripping(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            jdir = d / "batch" / "judge-j1"
            lib.write_json(d / "batch" / "judge-j1-keys.json", {"t1": {"A": "ours"}})
            lib.write_text(jdir / "answers" / "t1.json", '{"candidates": {"A": {"fact_errors": []}}, "ranking": ["A"]}')
            # Existing judgments.jsonl with BOM and blank lines must not crash collect_judge.
            (d / "run").mkdir(parents=True)
            (d / "run" / "judgments.jsonl").write_bytes(b"\xef\xbb\xbf\n\n")
            res = batches.collect_judge(d / "run", d / "batch", "j1")
            self.assertEqual(res["added"], 1)

            # patterns.main() strips notes before counting patterns (R-NOTES-NOT-TEXT).
            ed = d / "eval"
            lib.write_text(ed / "corpus" / "texts" / "t1.txt", "Это не просто кофе, а ритуал.\n")
            lib.write_text(ed / "results" / "r1" / "outputs" / "ours" / "t1.txt",
                           "Хороший кофе.\n\n---\n- Убрал «не просто кофе, а ритуал».\n")
            with mock.patch.object(lib, "EVAL_DIR", ed):
                self.assertEqual(patterns.main(["--run", "r1"]), 0)
            md = lib.read_text(ed / "results" / "r1" / "patterns.md")
            self.assertIn("| ne_prosto | #2 | 1 | 0/1 (+0) |", md)

    def test_frontier_single_compare_and_missing_dir(self):
        import frontier_eval as fe
        import receipt_eval as re_
        with mock.patch.object(re_.check_facts, "compare", wraps=re_.check_facts.compare) as spy:
            fe.score_text("Скидка 20%.", "Скидка 20%.")
            self.assertEqual(spy.call_count, 1)  # no duplicate compare when text_part == source
        with tempfile.TemporaryDirectory() as d, mock.patch.object(lib, "EVAL_DIR", Path(d)):
            self.assertEqual(fe.main(["--run", "r1", "--systems", "ours"]), 1)

    def test_lint_calibrate_holdout_isolation_and_dry_run(self):
        import lint_calibrate as lc
        with tempfile.TemporaryDirectory() as d:
            corpus = Path(d)
            human_rows = [{"id": "wn%02d" % i, "revision": i} for i in range(25)]
            lib.write_json(corpus / "human" / "index.json", human_rows)
            for r in human_rows:
                lib.write_text(corpus / "human" / (r["id"] + ".txt"), "Обычная новость без штампов.\n")
            lib.write_json(corpus / "index.json", [
                {"id": "d1", "kind": "generated", "set": "dev"},
                {"id": "f1", "kind": "generated", "set": "holdout4"},
                {"id": "h5_01", "kind": "generated", "set": "holdout5"},
                {"id": "h01", "kind": "trap", "set": "test"},
                {"id": "h6_13", "kind": "trap", "set": "holdout6"},
            ])
            for tid, txt in (("d1", "DEV_TEXT"), ("f1", "H4_TEXT"), ("h5_01", "H5_SECRET"),
                             ("h01", "TRAP_TEXT"), ("h6_13", "H6_TRAP")):
                lib.write_text(corpus / "texts" / (tid + ".txt"), txt)
            with mock.patch.object(lc, "CORPUS", corpus):
                g = lc.groups()
            dev_group = g["Модели: исходники прошлых наборов (dev–holdout3)"]
            self.assertEqual(dev_group, ["DEV_TEXT"])
            self.assertNotIn("H5_SECRET", dev_group)
            ctrl_group = g["Люди: контроль (набор human и ловушки)"]
            self.assertEqual(ctrl_group, ["TRAP_TEXT"])
            self.assertNotIn("H6_TRAP", ctrl_group)
            m = lc.measure(["Обычная новость.", "Важно отметить, что это уникальный шанс."], lc.lint_style.load_rules())
            self.assertEqual(m["texts"], 2)
            out_dir = Path(d) / "out"
            with mock.patch.object(lc, "CORPUS", corpus):
                self.assertEqual(lc.main(["--dry-run", "--out", str(out_dir)]), 0)
            self.assertFalse(out_dir.exists())

    def test_run_systems_tool_loop_merge_config_and_judge_multi_brace(self):
        # run_one handles read_file with skill/ prefix and returns final answer.
        replies = [
            ({"content": "", "tool_calls": [{"id": "c1", "function": {"arguments": '{"path": "skill/references/a.md"}'}}]},
             {"cost": 0.01, "prompt_tokens": 10, "completion_tokens": 5}),
            ({"content": "Готовый текст правки."}, {"cost": 0.02, "prompt_tokens": 20, "completion_tokens": 10}),
        ]
        with mock.patch.object(lib, "chat", side_effect=replies):
            text, meta = rs.run_one("m", "sys", {"references/a.md": "Правило."}, "Исходник.")
        self.assertEqual(text, "Готовый текст правки.\n")
        self.assertEqual(meta["files_read"], ["references/a.md"])
        merged = rs.merge_config({"systems": ["ours"], "texts": ["t1"]}, "exec", "dev", ["t2"], ["chat"])
        self.assertEqual(merged["systems"], ["ours", "chat"])
        self.assertEqual(merged["texts"], ["t1", "t2"])

        # judge.parse does not greedily merge separate {...} blocks.
        multi = 'Заметка: {проверь формат}\n{"candidates": {"A": {"fact_errors": []}}, "ranking": ["A"]}\nКонец {ок}.'
        parsed = judge.parse(multi)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["ranking"], ["A"])

    def test_style_freq_reraises_budget_and_supports_dry_run(self):
        import style_freq as sf
        with tempfile.TemporaryDirectory() as d:
            pairs = Path(d) / "pairs"
            rows = [{"id": "wn01", "revision": 1, "title": "T"}]
            with mock.patch.object(sf, "PAIRS", pairs), mock.patch.object(sf, "pool_rows", return_value=rows), \
                    mock.patch.object(sf, "_one", side_effect=lib.QuotaExhausted("quota ended")):
                with self.assertRaises(lib.BudgetExceeded):
                    sf.gen(1)
            human = Path(d) / "human"
            lib.write_text(pairs / "wn01.txt", "Важно отметить, что снег пошёл.\n")
            lib.write_text(human / "wn01.txt", "Снег пошёл утром.\n")
            lib.write_json(pairs / "index.json", {"wn01": sf.MODELS[0]})
            out = Path(d) / "out"
            with mock.patch.object(sf, "PAIRS", pairs), mock.patch.object(sf, "HUMAN", human):
                self.assertEqual(sf.rank(1, 0.0, 10, out_dir=out, dry_run=True), 0)
                self.assertFalse(out.exists())
                self.assertEqual(sf.rank(1, 0.0, 10, out_dir=out, dry_run=False), 0)
                self.assertTrue((out / "candidates.json").exists())

    def test_judge_build_strips_notes_preserves_source_sections_and_keeps_body_receipt(self):
        # R-NOTES-NOT-TEXT: blind judge bundles strip post-'---' editor notes & receipt lines
        # while keeping source '---' sections and leaving body-leaked lines without '---' visible.
        src_sections = "Часть 1.\n---\nВ 2025 году открыли 3 филиала."
        outputs = {
            "ours": "Часть 1.\n---\nВ 2025 году открыли 3 филиала.\n\n---\n- Убрал штамп.\nСверка скриптом: 2 числа на месте.",
            "kept_src": "Часть 1.\n---\nЗа 2025 год открыли 3 филиала.",
            "body_leak": "Часть 1. В 2025 году открыли 3 филиала.\nСверка скриптом: 2 числа на месте.",
        }
        block, key = judge.build("t1", outputs, "j1", 0, source=src_sections)
        by_sys = {}
        for lab, sys_name in key.items():
            marker = '<вариант id="%s">\n' % lab
            chunk = block.split(marker, 1)[1].split("\n</вариант>", 1)[0]
            by_sys[sys_name] = chunk
        # Post-'---' editor notes and receipt are stripped while the source's own '---' section stays.
        self.assertEqual(by_sys["ours"], "Часть 1.\n---\nВ 2025 году открыли 3 филиала.")
        self.assertNotIn("Убрал штамп", by_sys["ours"])
        self.assertNotIn("Сверка скриптом:", by_sys["ours"])
        # Source's own '---' section without editor notes is preserved intact.
        self.assertEqual(by_sys["kept_src"], "Часть 1.\n---\nЗа 2025 год открыли 3 филиала.")
        # Body-leaked receipt without '---' is NOT stripped.
        self.assertIn("Сверка скриптом: 2 числа на месте.", by_sys["body_leak"])

        # batches.prepare_judge passes source through to judge.build so bundles match.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            lib.write_text(d / "texts" / "t1.txt", src_sections + "\n")
            for s, txt in outputs.items():
                lib.write_text(d / "run" / "outputs" / s / "t1.txt", txt + "\n")
            batches.prepare_judge(d / "run", d / "texts", d / "batch", "j1", ["t1"], 6)
            bundle = lib.read_text(d / "batch" / "judge-j1" / "bundles" / "t1.md")
            self.assertNotIn("Убрал штамп", bundle)
            self.assertEqual(bundle.count("Сверка скриптом:"), 1)  # only body_leak keeps it
            self.assertIn("За 2025 год открыли 3 филиала.", bundle)

    def test_report_trap_threshold_scales_for_2_and_6_traps(self):
        def run_case(n_traps: int, bad_count: int):
            with tempfile.TemporaryDirectory() as d:
                ed = Path(d)
                trap_ids = ["tr%02d" % i for i in range(n_traps)]
                index = [{"id": "a1", "kind": "generated", "set": "dev"}] + [
                    {"id": tid, "kind": "trap", "set": "dev"} for tid in trap_ids
                ]
                lib.write_json(ed / "corpus" / "index.json", index)
                for row in index:
                    lib.write_text(ed / "corpus" / "texts" / (row["id"] + ".txt"), "Текст %s 100 рублей.\n" % row["id"])
                run_dir = ed / "results" / "r1"
                for s in ("ours", "prompt"):
                    for row in index:
                        lib.write_text(run_dir / "outputs" / s / (row["id"] + ".txt"), "Текст %s 100 рублей.\n" % row["id"])
                lib.write_json(run_dir / "config.json", {"executor": "dsh:minimax", "texts": [r["id"] for r in index],
                                                         "systems": ["ours", "prompt"]})
                jrows = []
                for row in index:
                    tid = row["id"]
                    is_bad = tid in trap_ids[:bad_count]
                    for j in ("j1", "j2"):
                        jrows.append({
                            "id": tid, "judge": j, "round": 0, "ranking": ["ours", "prompt"], "cost": 0.0,
                            "candidates": {
                                "ours": {"fact_errors": ["ошибка"] if is_bad else [], "send_as_is": 8},
                                "prompt": {"fact_errors": [], "send_as_is": 6},
                            },
                        })
                lib.write_text(run_dir / "judgments.jsonl", "\n".join(json.dumps(r, ensure_ascii=False) for r in jrows) + "\n")
                with mock.patch.object(lib, "EVAL_DIR", ed), mock.patch.object(lib, "CACHE_DIR", ed / ".cache"), \
                        mock.patch.object(lib, "LEDGER", ed / ".cache" / "spend.json"), mock.patch.object(lib, "_LEDGER", None):
                    rc = report.main(["--run", "r1"])
                self.assertEqual(rc, 0)
                summary = lib.read_json(run_dir / "summary.json")
                return next(th for th in summary["thresholds"] if th["name"].startswith("Ловушки:"))

        # n_traps == 2: requires 2 из 2 (2/2 passes, 1/2 fails).
        t2_ok = run_case(2, 0)
        self.assertEqual((t2_ok["name"], t2_ok["ok"], t2_ok["value"]),
                         ("Ловушки: без ошибок смысла хотя бы 2 из 2", True, "2 из 2"))
        t2_bad = run_case(2, 1)
        self.assertEqual((t2_bad["name"], t2_bad["ok"], t2_bad["value"]),
                         ("Ловушки: без ошибок смысла хотя бы 2 из 2", False, "1 из 2"))
        # n_traps == 6: preserves 5 из 6 (5/6 passes, 4/6 fails).
        t6_ok = run_case(6, 1)
        self.assertEqual((t6_ok["name"], t6_ok["ok"], t6_ok["value"]),
                         ("Ловушки: без ошибок смысла хотя бы 5 из 6", True, "5 из 6"))
        t6_bad = run_case(6, 2)
        self.assertEqual((t6_bad["name"], t6_bad["ok"], t6_bad["value"]),
                         ("Ловушки: без ошибок смысла хотя бы 5 из 6", False, "4 из 6"))

    def test_select_ids_isolates_holdout_traps(self):
        # Holdout sets with their own traps (e.g. holdout6) neither leak into other holdouts nor pull test traps.
        index = lib.read_json(lib.EVAL_DIR / "corpus" / "index.json")
        h4_ids = rs.select_ids(index, "holdout4")
        self.assertEqual(len(h4_ids), 42)
        self.assertNotIn("h6_13", h4_ids)
        self.assertNotIn("h6_14", h4_ids)
        h6_ids = rs.select_ids(index, "holdout6")
        self.assertEqual(len(h6_ids), 14)
        self.assertIn("h6_13", h6_ids)
        self.assertIn("h6_14", h6_ids)
        self.assertNotIn("h01", h6_ids)


if __name__ == "__main__":
    unittest.main()
