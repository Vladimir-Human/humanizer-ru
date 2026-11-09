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
        self.assertEqual(copied, ["check_facts.py", "clean_paste.py", "lint_style.py", "rules.json", "voice_profile.py"])
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


if __name__ == "__main__":
    unittest.main()
