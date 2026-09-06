#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Четыре пользовательских сценария (аудит L8): редактор/преподаватель,
разработчик/CI, ассистент через MCP, внешний контрибьютор. Smoke-проверки
без чистой установки: установка покрыта гейтом --sdist-test, здесь поведение
интерфейсов на текущем дереве."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args):
    return subprocess.run([sys.executable, "-X", "utf8", *args],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


class EditorScenarioTests(unittest.TestCase):
    """Редактор/преподаватель: папка текстов, находки и ошибки проверки,
    режим проверки не меняет файлы, «не вердикт об авторстве» на месте."""

    def test_folder_with_unreadable_file_is_partial(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "clean.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write("Обычный черновик без артефактов.\n")
            with open(os.path.join(td, "broken.txt"), "wb") as fh:
                fh.write(bytes([0x80, 0x81, 0x82]))
            before = open(os.path.join(td, "clean.txt"), "rb").read()
            r = run_cli(os.path.join(ROOT, "scripts", "scan_folder.py"),
                        td, "--format", "md")
            self.assertEqual(r.returncode, 1)
            self.assertIn("с ошибками проверки: 1", r.stdout)
            self.assertIn("не вердикт", r.stdout)
            after = open(os.path.join(td, "clean.txt"), "rb").read()
            self.assertEqual(before, after)


class CiScenarioTests(unittest.TestCase):
    """Разработчик/CI: коды выхода и JSON задокументированы, отказ проверки
    не выглядит зелёным."""

    def test_codes_and_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            clean = os.path.join(td, "clean.txt")
            with open(clean, "w", encoding="utf-8") as fh:
                fh.write("Обычный текст.\n")
            r = run_cli(os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                        clean, "--json")
            self.assertEqual(r.returncode, 0)
            env = json.loads(r.stdout)
            self.assertEqual(env["schema"], 1)
            marked = os.path.join(td, "marked.txt")
            with open(marked, "w", encoding="utf-8") as fh:
                fh.write("текст https://example.com/r?utm_source=openai\n")
            r = run_cli(os.path.join(ROOT, "scripts", "check_markers.py"),
                        "--scan", marked)
            self.assertEqual(r.returncode, 1)
            r = run_cli(os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                        os.path.join(td, "no-such.txt"), "--json")
            self.assertEqual(r.returncode, 2)
            env = json.loads(r.stdout)
            self.assertIn("error", env)


class McpScenarioTests(unittest.TestCase):
    """Ассистент через MCP: initialize -> list -> call -> плохой запрос ->
    list; сессия жива, ответ структурный."""

    @classmethod
    def setUpClass(cls):
        # дочерние процессы MCP идут через python -m humanizer_ru.*:
        # пакет должен находиться в пути (абсолютный PYTHONPATH, как в
        # selftest сервера); в реальной поставке пакет установлен pip.
        cls._old_pp = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep + \
            (cls._old_pp or "")

    @classmethod
    def tearDownClass(cls):
        if cls._old_pp is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = cls._old_pp

    def test_session_flow(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "mcp"))
        import humanizer_mcp as m
        defs = m.generate_tool_defs(m.load_contract())
        state = {}
        out = []
        for msg in ({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18"}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "humanizer_scan",
                                "arguments": {"text": "Обычный текст."}}},
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": [], "arguments": {}}},
                    {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}):
            out.append(m.handle_message(json.dumps(msg), state, defs))
        self.assertIn("result", out[0])
        self.assertEqual(len(out[1]["result"]["tools"]), 6)
        self.assertIn("structuredContent", out[2]["result"])
        self.assertEqual(out[3]["error"]["code"], -32602)
        self.assertIn("result", out[4])


class ContributorScenarioTests(unittest.TestCase):
    """Внешний контрибьютор: быстрый прогон в CONTRIBUTING, приёмка в
    шаблоне мелкой задачи, вход для сообщения о проблеме."""

    def test_entry_points_exist(self):
        contrib = open(os.path.join(ROOT, "CONTRIBUTING.md"),
                       encoding="utf-8").read()
        self.assertIn("Быстрый прогон", contrib)
        small = open(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE",
                                  "small-task.yml"), encoding="utf-8").read()
        self.assertIn("Приёмка", small)
        problem = open(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE",
                                    "problem-report.yml"),
                       encoding="utf-8").read()
        for field in ("Версия или коммит", "Команда или действие",
                      "Ожидание", "Фактический результат",
                      "Безопасный минимальный пример"):
            self.assertIn(field, problem)


if __name__ == "__main__":
    unittest.main()
