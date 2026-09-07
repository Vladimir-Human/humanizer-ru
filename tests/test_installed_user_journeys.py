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


def console_exe(name):
    """Консольная точка входа установленной поставки (рядом с её python)."""
    exe = name + (".exe" if os.name == "nt" else "")
    return os.path.join(os.path.dirname(PY), exe)


def installed_contract():
    """Контракт из данных УСТАНОВЛЕННОЙ поставки (не из дерева репо)."""
    proc = run(console_exe("humanizer-scan"), ["--contract"])
    return json.loads(proc.stdout)


def write_tmp(td, name, text):
    path = os.path.join(td, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


@SKIP_INSTALLED
class EditorJourneyTests(unittest.TestCase):
    """Редактор/преподаватель: находка, объяснение, безопасный отказ,
    сохранность защищённых областей, явная очистка."""

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

    def test_explicit_cleanup_found_cleaned_verified(self):
        # Основной сценарий продукта на установленной поставке:
        # нашёл -> очистил -> проверил (консольный humanizer-clean).
        contract = installed_contract()
        cmds = {t["command"] for t in contract["tools"]}
        self.assertIn("humanizer-clean", cmds,
                      "явная очистка отсутствует в установленном контракте")
        with tempfile.TemporaryDirectory() as td:
            p = write_tmp(td, "art.txt", MARKER_LINE)
            proc = run(console_exe("humanizer-clean"), ["--json", "--", p])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            f0 = json.loads(proc.stdout)["files"][0]
            self.assertGreaterEqual(f0["before_check"]["count"], 1)
            self.assertEqual(f0["after_check"]["count"], 0)
            self.assertNotIn("contentReference", f0["text"])


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

    def test_console_entry_points_exist_and_answer(self):
        # Реальные console entry points установленной поставки, не только
        # python -m: состав — из контракта установленных данных.
        contract = installed_contract()
        for t in contract["tools"]:
            exe = console_exe(t["command"])
            self.assertTrue(os.path.isfile(exe),
                            "нет точки входа %s" % t["command"])
        for name in ("humanizer-scan", "humanizer-markers",
                     "humanizer-polish", "humanizer-detect"):
            proc = run(console_exe(name), ["--version"])
            self.assertEqual(proc.returncode, 0, name)
            self.assertRegex(proc.stdout.strip(), r"^\d+\.\d+\.\d+$")

    def test_console_flag_like_filename_after_ddash(self):
        # Имя файла, похожее на флаг, — путь (регрессия машинного ввода
        # на установленной поставке, граница «--»).
        with tempfile.TemporaryDirectory() as td:
            write_tmp(td, "--class", MARKER_LINE)
            proc = run(console_exe("humanizer-markers"),
                       ["--scan", "--json", "--", "--class"], cwd=td)
            self.assertEqual(proc.returncode, 1)
            env = json.loads(proc.stdout)
            self.assertEqual(env["files"][0]["file"], "--class")
            self.assertGreaterEqual(env["files"][0]["count"], 1)


@SKIP_INSTALLED
class AssistantJourneyTests(unittest.TestCase):
    """Пользователь ассистента: MCP initialize/tools/list/call, плохой
    запрос, следующий успешный."""

    def _session(self, requests):
        input_text = "\n".join(json.dumps(r) for r in requests) + "\n"
        return run(PY, ["-m", "humanizer_ru.mcp_server"], input_text=input_text)

    def test_mcp_flow(self):
        contract = installed_contract()
        expected_tools = sorted(t["command"].replace("-", "_")
                                for t in contract["tools"])
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
        if "humanizer_clean" in expected_tools:
            # Явная очистка через MCP: находка -> очищенный текст -> отчёт.
            requests.append(
                {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                 "params": {"name": "humanizer_clean",
                            "arguments": {"text": MARKER_LINE}}})
        proc = self._session(requests)
        lines = [ln for ln in proc.stdout.split("\n") if ln.strip()]
        by_id = {}
        for ln in lines:
            msg = json.loads(ln)
            if "id" in msg:
                by_id[msg["id"]] = msg
        tools = by_id[2]["result"]["tools"]
        # Состав инструментов — из установленного контракта (единый
        # источник), а не зашитое число: аддитивный инструмент не ломает
        # сценарий, расхождение с контрактом — ломает.
        self.assertEqual(sorted(t["name"] for t in tools), expected_tools)
        self.assertFalse(by_id[3].get("result", {}).get("isError"))
        self.assertIn("error", by_id[4])
        self.assertEqual(by_id[4]["error"]["code"], -32602)
        # После ошибки входа сессия продолжает обслуживать валидные
        # вызовы (discovery/call/error/recovery).
        self.assertFalse(by_id[5].get("result", {}).get("isError"))
        if 6 in by_id:
            res6 = by_id[6]["result"]
            self.assertFalse(res6.get("isError"))
            f0 = res6["structuredContent"]["files"][0]
            self.assertNotIn("contentReference", f0["text"])
            self.assertEqual(f0["after_check"]["count"], 0)


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