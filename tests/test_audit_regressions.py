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
import json
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


MCP_ROOT = os.path.join(ROOT, "scripts", "mcp")


class MachineContractTests(unittest.TestCase):
    """L2 (N43/N49/N50): типы name, изоляция serve, структура конверта,
    схема report, совместимость v1 с сохранённым контрактом предыдущего релиза (fixtures/contract-3311.json)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, MCP_ROOT)
        import humanizer_mcp as m
        cls.mcp = m
        cls.defs = m.generate_tool_defs(m.load_contract())
        cls.state = {}
        m.handle_message(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"}}), cls.state, cls.defs)

    def _call(self, name):
        return self.mcp.handle_message(json.dumps({
            "jsonrpc": "2.0", "id": 99, "method": "tools/call",
            "params": {"name": name, "arguments": {}}}), self.state,
            self.defs)

    def test_bad_name_types_rejected(self):
        for bad in ([], {"x": 1}, None, 7):
            r = self._call(bad)
            self.assertEqual(r.get("error", {}).get("code"), -32602, bad)

    def test_session_survives_bad_name(self):
        self._call([])
        r = self.mcp.handle_message(
            '{"jsonrpc": "2.0", "id": 100, "method": "tools/list"}',
            self.state, self.defs)
        self.assertIn("result", r)

    def test_serve_isolates_bad_request(self):
        import io
        inp = io.StringIO(json.dumps({
            "jsonrpc": "2.0", "id": 29, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"}}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 30, "method": "tools/call",
                          "params": {"name": [], "arguments": {}}}) + "\n"
            + '{"jsonrpc": "2.0", "id": 31, "method": "tools/list"}\n')
        out = io.StringIO()
        self.mcp.serve(stdin=inp, stdout=out)
        lines = [json.loads(x) for x in out.getvalue().splitlines() if x]
        self.assertEqual(len(lines), 3)
        self.assertIn("result", lines[0])
        self.assertEqual(lines[1]["error"]["code"], -32602)
        self.assertIn("result", lines[2])

    def test_report_schema_matches_actual_envelope(self):
        import subprocess
        import tempfile
        contract = self.mcp.load_contract()
        rep = next(x for x in contract["tools"]
                   if x.get("command") == "humanizer-report")
        schema = rep["output_schema"]
        self.assertEqual(schema["properties"]["tool"]["enum"],
                         ["humanizer-report"])
        with tempfile.TemporaryDirectory() as td:
            pb = os.path.join(td, "b.txt")
            pa = os.path.join(td, "a.txt")
            with open(pb, "w", encoding="utf-8") as fh:
                fh.write("Текст до правки с числом 12.\n")
            with open(pa, "w", encoding="utf-8") as fh:
                fh.write("Текст до правки с числом 12!\n")
            r = subprocess.run(
                [sys.executable, "-X", "utf8",
                 os.path.join(ROOT, "src", "humanizer_ru", "edit_report.py"),
                 pb, pa, "--json"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            env = json.loads(r.stdout)
        for key in schema["required"]:
            self.assertIn(key, env)
        self.assertEqual(env["tool"], "humanizer-report")
        item_schema = schema["properties"]["files"]["items"]
        for item in env["files"]:
            for key in item_schema["required"]:
                self.assertIn(key, item)
            self.assertIsInstance(item["tokens"]["keep"], int)
            self.assertIsInstance(item["facts"]["unchanged"], bool)

    def test_v1_compatibility_with_saved_contract(self):
        with open(os.path.join(
                ROOT, "tests", "fixtures", "contract-3311.json"),
                encoding="utf-8") as fh:
            old = json.load(fh)
        new = self.mcp.load_contract()
        self.assertEqual(sorted(set(old) - set(new)), [],
                         "удалены ключи верхнего уровня v1")
        pu = new["prohibited_uses"]
        self.assertEqual(pu["status"], "withdrawn")
        self.assertEqual(pu["list"], [])
        self.assertIsInstance(pu, dict)
        old_tools = {x["command"] for x in old["tools"]}
        new_tools = {x["command"] for x in new["tools"]}
        self.assertEqual(old_tools - new_tools, set(),
                         "удалены команды инструментов v1")


class CliRobustnessTests(unittest.TestCase):
    """L2: допустимые коды выхода и конверт на вырожденном входе."""

    def _scan(self, data: bytes):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            pf = os.path.join(td, "t.txt")
            with open(pf, "wb") as fh:
                fh.write(data)
            r = subprocess.run(
                [sys.executable, "-X", "utf8",
                 os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                 pf, "--json"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                errors="replace")
        return r

    def test_non_utf8_input(self):
        # байты вне UTF-8 и без BOM: честный отказ входа (код 2) с конвертом
        # ошибки, а не ложный «проверено без находок»
        payload = bytes([0x80, 0x81, 0x82]) + b"bad bytes"
        r = self._scan(payload + b"\n")
        self.assertEqual(r.returncode, 2)
        env = json.loads(r.stdout)
        self.assertIn("error", env)

    def test_undecodable_bom_input_is_input_error(self):
        # BOM UTF-16 с невалидным телом: честный отказ входа (код 2),
        # а не ложный «проверено без находок»
        r = self._scan(bytes([0xFF, 0xFE, 0x00, 0x81, 0x82]))
        self.assertEqual(r.returncode, 2)
        env = json.loads(r.stdout)
        self.assertIn("error", env)

    def test_empty_input(self):
        r = self._scan(b"")
        self.assertIn(r.returncode, (0, 1))
        env = json.loads(r.stdout)
        self.assertEqual(env["tool"], "humanizer-scan")

    def test_missing_file_is_input_error(self):
        import subprocess
        r = subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
             os.path.join("tests", "fixtures", "no-such-file.txt"), "--json"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        self.assertEqual(r.returncode, 2)
        env = json.loads(r.stdout)
        self.assertIn("error", env)


class BatchCliTests(unittest.TestCase):
    """L3 (N44): коды выхода батча и самопроверка с негативами."""

    def _run(self, *extra):
        import subprocess
        return subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "scripts", "scan_folder.py"), *extra],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace")

    def test_selftest_negative_cases(self):
        r = self._run("--selftest")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("САМОПРОВЕРКА scan_folder", r.stdout)
        self.assertNotIn("FAIL:", r.stdout)

    def test_missing_folder_is_code_2(self):
        r = self._run(os.path.join("tests", "fixtures", "no-such-dir"))
        self.assertEqual(r.returncode, 2)

    def test_clean_folder_is_code_0_and_marked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "a.txt"), "w", encoding="utf-8") as fh:
                fh.write("обычный текст без артефактов и меток\n")
            r = self._run(td, "--format", "md")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("с ошибками проверки: 0", r.stdout)
            self.assertIn("| ok |", r.stdout)


class SkillBoundaryTests(unittest.TestCase):
    """L4 (N34/N48/N13): профили полномочий, запрет вердикта по следам
    вставки, установка без клона dev-репозитория, инъекции как данные."""

    @classmethod
    def setUpClass(cls):
        cls.skill = open(os.path.join(ROOT, "SKILL.md"),
                         encoding="utf-8").read()

    def test_two_profiles_documented(self):
        self.assertIn("Read-only профиль", self.skill)
        self.assertIn("Машинный профиль", self.skill)
        self.assertIn("детерминированная проверка не выполнялась", self.skill)
        self.assertIn("общий Bash-доступ не решение задачи", self.skill)

    def test_no_authorship_verdict_from_traces(self):
        self.assertIn("следы вставки — тоже", self.skill)
        self.assertNotIn("Вердикт «текст написан ИИ» допустим", self.skill)
        self.assertIn("а не авторство всего текста", self.skill)
        self.assertIn("как сведения автора, не как вычисленный результат",
                      self.skill)

    def test_tree_a_branch_is_about_insertion(self):
        self.assertIn("это факт вставки и статус источника, а не авторство"
                      " всего текста", self.skill)

    def test_install_without_dev_clone(self):
        for rel in ("docs/USAGE.md", "docs/USAGE.en.md"):
            doc = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            self.assertNotIn("~/.claude/skills/humanizer-ru", doc)
            self.assertNotIn("git clone --branch", doc)

    def test_injection_fixtures_are_data(self):
        import subprocess
        for name in ("injection-fake-permission.txt",
                     "injection-closing-tag.txt",
                     "injection-tool-result.txt"):
            path = os.path.join(ROOT, "tests", "fixtures", name)
            r = subprocess.run(
                [sys.executable, "-X", "utf8",
                 os.path.join(ROOT, "scripts", "check_markers.py"),
                 "--scan", path],
                cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            self.assertIn(r.returncode, (0, 1), name)
        fake = open(os.path.join(
            ROOT, "tests", "fixtures", "injection-fake-permission.txt"),
            encoding="utf-8").read()
        self.assertIn("utm_source=openai", fake)


class DemoStatusTests(unittest.TestCase):
    """L5 (N46/N33/N4/N38): состояния демо, share-state, null-lag."""

    @classmethod
    def setUpClass(cls):
        cls.html = open(os.path.join(ROOT, "demo", "index.html"),
                        encoding="utf-8").read()

    def test_engine_missing_is_explicit_refusal(self):
        self.assertIn("if (!engineReady())", self.html)
        self.assertIn("проверка не выполнялась", self.html)

    def test_warning_precedes_hash_change(self):
        self.assertLess(self.html.find("Ссылка получит ваш текст"),
                        self.html.find("location.hash = encodeURIComponent(text)"))

    def test_own_text_clears_share_state(self):
        self.assertIn("history.replaceState", self.html)

    def test_byte_limit_after_encoding(self):
        self.assertIn("TextEncoder", self.html)
        self.assertIn("65536", self.html)

    def test_null_lag_distinct_from_zero(self):
        self.assertIn("сведений о релизе нет", self.html)

    def test_write_status_null_lag_without_tags(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "docs"))
            os.makedirs(os.path.join(td, "demo"))
            with open(os.path.join(td, "markers.v1.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"count": 40}, fh)
            env = dict(os.environ, GIT_CONFIG_COUNT="2",
                       GIT_CONFIG_KEY_0="user.name", GIT_CONFIG_VALUE_0="t",
                       GIT_CONFIG_KEY_1="user.email",
                       GIT_CONFIG_VALUE_1="t@example.com")
            subprocess.run(["git", "init", "-q", td], check=True, env=env)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                           cwd=td, check=True, env=env)
            r = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts",
                                              "write_status.py"),
                 "--root", td, "--sha", "abc"],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.load(open(os.path.join(td, "docs", "status.json"),
                                  encoding="utf-8"))
            self.assertIsNone(data["lag_commits"])
            self.assertIsNone(data["published_commit"])


class BenchmarkEvidenceTests(unittest.TestCase):
    """L7 (N25/N30): одноимённые на benchmark-странице, лидерство не
    объявлено, вариант Б приказа поддержан в proposal."""

    @classmethod
    def setUpClass(cls):
        cls.page = open(os.path.join(ROOT, "demo", "benchmark", "index.html"),
                        encoding="utf-8").read()
        cls.leader = open(os.path.join(ROOT, "LEADERBOARD.md"),
                          encoding="utf-8").read()
        cls.proposal = open(os.path.join(ROOT, "docs",
                                          "POSITIONING-PROPOSAL.md"),
                            encoding="utf-8").read()

    def test_same_names_present_with_status(self):
        self.assertIn("ilyautov/humanizer-ru", self.page)
        self.assertIn("smixs/humanizer-ru", self.page)
        self.assertIn("несопоставимо", self.page)

    def test_no_leadership_claim_from_single_comparator(self):
        self.assertIn("лидерство в нише", self.leader)
        self.assertIn("не измерено", self.leader)

    def test_proposal_supports_both_variants(self):
        self.assertIn("Проверяемая гигиена вставки из чата для русского "
                      "текста", self.proposal)
        self.assertIn("Проверка и очистка следов вставки из чата в русском "
                      "тексте", self.proposal)

