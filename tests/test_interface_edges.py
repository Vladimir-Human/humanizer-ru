#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Граничные машинные входы CLI и MCP (воспроизведены 2026-09-06).

Проверено и закреплено:
  1. --json без файлов: stdout — JSON-конверт контракта с честным
     scope_note (самопроверка выражений), а не человекочитаемый текст;
  2. неизвестный аргумент с --json: код 2 и конверт ошибки в stdout
     (правило error_rule: агент всегда получает разобранный JSON);
  3. граница «--» уважается: «--version» после «--» — операнд (файл),
     а не запрос версии; до «--» — по-прежнему версия;
  4. MCP-уведомление (нет id) не получает ответа — в том числе ping:
     никакого «id: null» в stdout;
  5. повреждённый дочерний конверт с ключами неверных типов
     ({"tool": [], "schema": "bad"}) не принимается как корректный:
     isError true, structuredContent отсутствует;
  6. суррогат в id запроса не роняет сервер (краш не подтверждён —
     закреплено фактическое поведение: сессия продолжается);
  7. векторы паритета CLI/демо (tests/fixtures/demo-parity/vectors.json)
     проходят штатным гейтом.

Юнит-часть работает и в sdist (импорт установленного пакета); часть
прогонов — только в репозитории.
"""
import json
import os
import shutil
import subprocess
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): интеграционные тесты не запускаются")
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from humanizer_ru import __version__  # noqa: E402
from humanizer_ru import mcp_server  # noqa: E402

MCP_CHILD = os.path.join(ROOT, "scripts", "mcp", "humanizer_mcp.py")


def _run_cli(main_name, argv, timeout=120):
    code = ("import sys; sys.path.insert(0, %r);"
            "from humanizer_ru.cli import %s;"
            "sys.exit(%s(%r))") % (SRC, main_name, main_name, argv)
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                       capture_output=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def _mcp_session(lines, timeout=120):
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    p = subprocess.run([sys.executable, "-X", "utf8", MCP_CHILD],
                       input="\n".join(lines) + "\n",
                       capture_output=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, env=env, timeout=timeout)
    out = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
    return p.returncode, out, p.stderr or ""


INIT = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18",
                              "capabilities": {},
                              "clientInfo": {"name": "edges", "version": "0"}}})


class CliJsonEdgeTests(unittest.TestCase):
    """--json всегда даёт конверт; граница «--» уважается."""

    def test_json_without_files_is_envelope(self):
        rc, out, _err = _run_cli("markers_main", ["--json"])
        self.assertEqual(rc, 0)
        env = json.loads(out)
        self.assertEqual(env["tool"], "humanizer-markers")
        self.assertEqual(env["schema"], 1)
        entry = env["files"][0]
        self.assertEqual(entry["file"], "<выражения>")
        self.assertIn("нет файлов", entry["scope_note"])

    def test_unknown_arg_with_json_gives_envelope(self):
        rc, out, _err = _run_cli("markers_main",
                                 ["--json", "--нет-такого-флага"])
        self.assertEqual(rc, 2)
        env = json.loads(out)
        self.assertEqual(env["tool"], "humanizer-markers")
        self.assertIn("код 2", env["error"])

    def test_ddash_makes_version_an_operand(self):
        rc, out, _err = _run_cli("markers_main", ["--json", "--", "--version"])
        self.assertEqual(rc, 2)
        env = json.loads(out)
        self.assertEqual(env["files"][0]["file"], "--version")
        rc2, out2, _e2 = _run_cli("scan_main", ["--json", "--", "--version"])
        self.assertEqual(rc2, 2)
        self.assertIn("--version", out2)

    def test_version_flag_before_ddash_still_works(self):
        rc, out, _err = _run_cli("markers_main", ["--version"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), __version__)


class McpEnvelopeTests(unittest.TestCase):
    """Конверт дочернего процесса проверяется по типам, а не по ключам."""

    def test_bad_envelope_types_rejected(self):
        proc = types.SimpleNamespace(
            returncode=0, stdout='{"tool": [], "schema": "bad"}', stderr="")
        result, envelope = mcp_server._result_from_proc(proc)
        self.assertIsNone(envelope)
        self.assertTrue(result["isError"])
        self.assertNotIn("structuredContent", result)

    def test_good_envelope_accepted(self):
        proc = types.SimpleNamespace(
            returncode=0,
            stdout='{"tool": "humanizer-scan", "schema": 1, "files": []}',
            stderr="")
        result, envelope = mcp_server._result_from_proc(proc)
        self.assertIsNotNone(envelope)
        self.assertFalse(result["isError"])


@SKIP_OUTSIDE
class McpSessionTests(unittest.TestCase):
    """Уведомления без ответа; суррогат в id не роняет сессию."""

    def test_ping_notification_gets_no_response(self):
        ping = json.dumps({"jsonrpc": "2.0", "method": "ping"})
        lst = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        rc, out, _err = _mcp_session([INIT, ping, lst])
        self.assertEqual(rc, 0)
        self.assertEqual(len(out), 2, "уведомление ping получило ответ")
        ids = [json.loads(ln).get("id") for ln in out]
        self.assertEqual(ids, [1, 2])
        self.assertNotIn(None, ids)

    def test_request_ping_still_answered(self):
        ping = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"})
        rc, out, _err = _mcp_session([INIT, ping])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out[1])["result"], {})

    def test_surrogate_id_does_not_crash_session(self):
        # Краш на суррогате в id не подтверждён: закрепляем фактическое
        # поведение — сервер отвечает и продолжает сессию.
        surr = '{"jsonrpc": "2.0", "id": "\\ud800", "method": "tools/list"}'
        lst = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        rc, out, _err = _mcp_session([INIT, surr, lst])
        self.assertEqual(rc, 0)
        self.assertEqual(len(out), 3)


@SKIP_OUTSIDE
class VectorParityTests(unittest.TestCase):
    """Векторы паритета CLI/демо проходят штатным гейтом."""

    def test_parity_gate_green(self):
        proc = subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "scripts", "check_demo_parity.py")],
            capture_output=True, encoding="utf-8", errors="replace",
            cwd=ROOT, timeout=300)
        self.assertEqual(proc.returncode, 0,
                         (proc.stdout or "")[-800:] + (proc.stderr or "")[-400:])

    def test_vectors_fixture_wellformed(self):
        path = os.path.join(ROOT, "tests", "fixtures", "demo-parity",
                            "vectors.json")
        with open(path, encoding="utf-8") as fh:
            vectors = json.load(fh)
        self.assertGreaterEqual(len(vectors), 10)
        names = [v["name"] for v in vectors]
        self.assertEqual(len(names), len(set(names)))
        for v in vectors:
            self.assertIsInstance(v["text"], str)
            for e in v["expect"]:
                self.assertEqual(
                    sorted(e), ["class", "end", "line", "marker", "shadow",
                                "start"])

    def test_cyr_glue_detected_by_cli(self):
        # Регрессия границы: склейка с кириллицей ловится (явные
        # lookaround-классы вместо \\b).
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "v.txt")
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write("вставкаattributableIndex вставка")
            proc = subprocess.run(
                [sys.executable, "-X", "utf8",
                 os.path.join(ROOT, "scripts", "check_markers.py"),
                 "--scan", "--json", p],
                capture_output=True, encoding="utf-8", errors="replace",
                cwd=ROOT, timeout=120)
            data = json.loads(proc.stdout)
            names = [m["marker"] for m in data["files"][0]["markers"]]
            self.assertIn("attributableIndex", names)


if __name__ == "__main__":
    unittest.main()
