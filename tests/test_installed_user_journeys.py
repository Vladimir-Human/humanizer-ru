#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_installed_user_journeys.py — четыре пользовательских пути
на УСТАНОВЛЕННОМ артефакте вне исходного дерева.

Путь интерпретатора установленной поставки берётся из переменной
окружения HUMANIZER_JOURNEY_PYTHON (например, Scripts/python.exe чистой
venv с wheel/sdist). Без неё тесты пропускаются с причиной: установка не
подготовлена (подготовка — действие цикла, а не гейта; доказательство
прогона прикладывается к PR отдельным логом).

Команды запускаются только интерпретатором установленной поставки;
PYTHONPATH исходного дерева не подставляется — импорт идёт из
site-packages установленной версии.
"""
import json
import os
import subprocess
import tempfile
import unittest

PY = os.environ.get("HUMANIZER_JOURNEY_PYTHON") or ""
SKIP_REASON = ("установленная поставка не подготовлена "
               "(HUMANIZER_JOURNEY_PYTHON не задан)")
SKIP_INSTALLED = unittest.skipUnless(bool(PY), SKIP_REASON)

MARKER_LINE = ("Согласно отчёту :" + "contentReference[oaicite:"
               + "3]{index=3}, рост заявок.\n")
CLEAN_LINE = "Обычный русский текст без дефектов.\n"
THINK_OPEN = "<" + "think" + ">"
THINK_CLOSE = "</" + "think" + ">"
FENCED_DOC = ("Проза \"цитата\".\n\n```text\n" + THINK_OPEN
              + "рассуждение внутри кода" + THINK_CLOSE
              + "\n```\n\nКонец.\n")


def run(py, args, cwd=None, input_text=None):
    return subprocess.run([py] + args, capture_output=True, text=True,
                          cwd=cwd, input=input_text, encoding="utf-8",
                          errors="replace")


def write_tmp(td, name, text):
    path = os.path.join(td, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


@SKIP_INSTALLED
class EditorJourneyTests(unittest.TestCase):
    """Редактор/преподаватель: находка, объяснение, безопасный отказ,
    сохранность защищённых областей."""

    def test_finding_and_explanation(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_tmp(td, "t.txt", MARKER_LINE)
            proc = run(PY, ["-m", "humanizer_ru.check_markers", "--scan", p])
            self.assertEqual(proc.returncode, 1)
            self.assertIn("contentReference", proc.stdout)

    def test_safe_refusal_on_unreadable(self):
        proc = run(PY, ["-m", "humanizer_ru.check_markers", "--scan",
                        "нет-такого-файла.txt"])
        self.assertEqual(proc.returncode, 2)

    def test_preservation_in_safe_mode(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_tmp(td, "d.md", FENCED_DOC)
            proc = run(PY, ["-m", "humanizer_ru.polish", "--preserve-markup",
                            "--in-place", p])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(p, encoding="utf-8") as fh:
                after = fh.read()
            self.assertIn("рассуждение внутри кода", after)
            self.assertIn("```text", after)


@SKIP_INSTALLED
class DeveloperJourneyTests(unittest.TestCase):
    """Разработчик/CI: коды выхода clean/marked/unreadable."""

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            clean = write_tmp(td, "clean.txt", CLEAN_LINE)
            marked = write_tmp(td, "marked.txt", MARKER_LINE)
            self.assertEqual(run(PY, ["-m", "humanizer_ru.check_markers",
                                      "--scan", clean]).returncode, 0)
            self.assertEqual(run(PY, ["-m", "humanizer_ru.check_markers",
                                      "--scan", marked]).returncode, 1)
            self.assertEqual(run(PY, ["-m", "humanizer_ru.check_markers",
                                      "--scan",
                                      os.path.join(td, "no.txt")]).returncode,
                             2)

    def test_json_envelope_on_error(self):
        proc = run(PY, ["-m", "humanizer_ru.check_markers", "--scan",
                        "--json", "нет-такого-файла.txt"])
        self.assertEqual(proc.returncode, 2)
        env = json.loads(proc.stdout)
        self.assertEqual(env["tool"], "humanizer-markers")
        self.assertIn("error", env)


@SKIP_INSTALLED
class AssistantJourneyTests(unittest.TestCase):
    """Пользователь ассистента: MCP initialize/tools/list/call, плохой
    запрос, следующий успешный."""

    def _session(self, requests):
        input_text = "\n".join(json.dumps(r) for r in requests) + "\n"
        return run(PY, ["-m", "humanizer_ru.mcp_server"], input_text=input_text)

    def test_mcp_flow(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "journey", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "humanizer_markers",
                        "arguments": {"text": MARKER_LINE}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "humanizer_markers",
                        "arguments": {"text": MARKER_LINE,
                                      "лишний": 1}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "humanizer_markers",
                        "arguments": {"text": CLEAN_LINE}}},
        ]
        proc = self._session(requests)
        lines = [ln for ln in proc.stdout.split("\n") if ln.strip()]
        by_id = {}
        for ln in lines:
            msg = json.loads(ln)
            if "id" in msg:
                by_id[msg["id"]] = msg
        tools = by_id[2]["result"]["tools"]
        self.assertEqual(len(tools), 6)
        self.assertFalse(by_id[3].get("result", {}).get("isError"))
        self.assertIn("error", by_id[4])
        self.assertEqual(by_id[4]["error"]["code"], -32602)
        self.assertFalse(by_id[5].get("result", {}).get("isError"))


@SKIP_INSTALLED
class ContributorJourneyTests(unittest.TestCase):
    """Контрибьютор: установленный артефакт самодиагностируется."""

    def test_installed_selftests_green(self):
        for mod in ("humanizer_ru.facts_diff", "humanizer_ru.polish"):
            proc = run(PY, ["-m", mod, "--selftest"])
            self.assertEqual(proc.returncode, 0,
                             "%s: %s" % (mod, proc.stdout[-300:]))

    def test_import_location_is_site_packages(self):
        proc = run(PY, ["-c", "import humanizer_ru, os; "
                              "print(os.path.dirname("
                              "humanizer_ru.__file__))"])
        where = proc.stdout.strip()
        self.assertIn("site-packages", where.replace("\\", "/"),
                      "пакет импортирован не из установленной поставки: "
                      + where)


if __name__ == "__main__":
    unittest.main()