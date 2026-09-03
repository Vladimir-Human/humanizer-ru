#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conformance-тесты MCP-сервера humanizer-ru (JSON-RPC 2.0 over stdio).

Покрывают критерии v2 3.1: initialize/initialized, версия протокола
(матрица поддерживаемых и неподдерживаемая), capabilities, framing
(newline-delimited, уведомления без ответа), семантика ошибок JSON-RPC
(-32700/-32600/-32601/-32602), cancellation, tools/list = схемам из
контракта, tools/call для всех четырёх инструментов: находка (CLI-код 1)
— успешный tool result, structuredContent соответствует outputSchema
контракта (мини-валидатор check_contract), out-of-scope, режимы polish,
словари жанров.

В дереве репозитория сервер запускается из scripts/mcp/humanizer_mcp.py;
в sdist-контексте — из установленного пакета (python -m
humanizer_ru.mcp_server); если нет ни того ни другого — честный skip.
"""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "scripts", "mcp", "humanizer_mcp.py")
SCRIPTS = os.path.join(ROOT, "scripts")


def _server_argv():
    if os.path.isfile(SERVER):
        return [sys.executable, "-X", "utf8", SERVER]
    try:
        import humanizer_ru.mcp_server  # noqa: F401
        return [sys.executable, "-X", "utf8", "-m", "humanizer_ru.mcp_server"]
    except ImportError:
        return None


def _contract_and_defs():
    """(contract, tool_defs) из канонического источника: дерево репозитория
    (scripts/mcp/humanizer_mcp.py) или установленный пакет (sdist-контекст,
    где дерева скриптов нет)."""
    mcp_dir = os.path.join(ROOT, "scripts", "mcp")
    if os.path.isfile(os.path.join(mcp_dir, "humanizer_mcp.py")):
        if mcp_dir not in sys.path:
            sys.path.insert(0, mcp_dir)
        import humanizer_mcp as mod
    else:
        from humanizer_ru import mcp_server as mod
    contract = mod.load_contract()
    return contract, mod.generate_tool_defs(contract)


ARGV = _server_argv()


def _session(lines, timeout=180):
    payload = "".join(m if m.endswith("\n") else m + "\n" for m in lines)
    env = dict(os.environ)
    src = os.path.join(ROOT, "src")
    if os.path.isdir(src):
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(ARGV, input=payload, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout,
                          encoding="utf-8", errors="replace", env=env,
                          cwd=ROOT)
    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out, proc


def _req(id_, method, params=None):
    m = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        m["params"] = params
    return json.dumps(m, ensure_ascii=False)


def _note(method, params=None):
    m = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        m["params"] = params
    return json.dumps(m, ensure_ascii=False)


_INIT = _req(1, "initialize", {"protocolVersion": "2025-06-18",
                               "capabilities": {},
                               "clientInfo": {"name": "t", "version": "0"}})


@unittest.skipUnless(ARGV, "MCP-сервер недоступен (ни дерево, ни пакет)")
class TestMcpHandshake(unittest.TestCase):
    def test_supported_versions_echoed(self):
        for ver in ("2025-06-18", "2025-03-26", "2024-11-05"):
            with self.subTest(version=ver):
                resps, _ = _session([_req(1, "initialize", {
                    "protocolVersion": ver, "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}})])
                self.assertEqual(resps[0]["result"]["protocolVersion"], ver)

    def test_unsupported_version_falls_back_to_latest(self):
        resps, _ = _session([_req(1, "initialize", {
            "protocolVersion": "1999-01-01", "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"}})])
        self.assertEqual(resps[0]["result"]["protocolVersion"], "2025-06-18")

    def test_capabilities_and_serverinfo(self):
        resps, _ = _session([_INIT])
        r = resps[0]["result"]
        self.assertIn("tools", r["capabilities"])
        self.assertEqual(r["serverInfo"]["name"], "humanizer-ru-mcp")
        self.assertRegex(r["serverInfo"]["version"], r"^\d+\.\d+\.\d+$")

    def test_notifications_get_no_response(self):
        resps, _ = _session([
            _INIT,
            _note("notifications/initialized"),
            _note("notifications/cancelled", {"requestId": 1}),
            _note("notifications/whatever-unknown"),
            _req(2, "ping"),
        ])
        ids = [r.get("id") for r in resps]
        self.assertEqual(ids, [1, 2])  # только запросы


@unittest.skipUnless(ARGV, "MCP-сервер недоступен (ни дерево, ни пакет)")
class TestMcpErrors(unittest.TestCase):
    def test_error_matrix(self):
        resps, _ = _session([
            _INIT,
            _req(2, "no/such"),
            "{ broken",
            '["array"]',
            _req(3, "tools/call", {"name": "ghost", "arguments": {}}),
            _req(4, "tools/call", {"name": "humanizer_scan",
                                   "arguments": {}}),
            _req(5, "tools/call", {"name": "humanizer_polish",
                                   "arguments": {"text": "x",
                                                 "mode": "nope"}}),
            _req(6, "tools/call", {"name": "humanizer_scan",
                                   "arguments": {"text": "x",
                                                 "genre": "nope"}}),
            _req(7, "tools/call", {"name": "humanizer_scan",
                                   "arguments": {"text": "x",
                                                 "extra": 1}}),
        ])
        by = {r.get("id"): r for r in resps}
        self.assertEqual(by[2]["error"]["code"], -32601)
        self.assertIsNone(by[None]["id"])
        self.assertIn(by[None]["error"]["code"], (-32700, -32600))
        for i in (3, 4, 5, 6, 7):
            self.assertEqual(by[i]["error"]["code"], -32602,
                             "запрос %d: ожидался -32602" % i)

    def test_framing_one_line_per_response(self):
        resps, proc = _session([_INIT, _req(2, "tools/list")])
        for r in resps:
            self.assertNotIn("\n", json.dumps(r))
        self.assertEqual(len(resps), 2)
        self.assertEqual(proc.returncode, 0)


@unittest.skipUnless(ARGV, "MCP-сервер недоступен (ни дерево, ни пакет)")
class TestMcpTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract, cls.defs = _contract_and_defs()
        try:
            if SCRIPTS not in sys.path:
                sys.path.insert(0, SCRIPTS)
            import check_contract
            cls.schema_errors = staticmethod(check_contract.schema_errors)
        except ImportError:
            # sdist-контекст: гейт-валидатора в поставке нет — схема
            # structuredContent проверяется conformance-гейтом в дереве
            # (scripts/check_mcp.py), здесь сравнение пропускается.
            cls.schema_errors = staticmethod(lambda value, schema: [])

    def _schema(self, name):
        return next(d["outputSchema"] for d in self.defs if d["name"] == name)

    def test_tools_list_equals_generated(self):
        resps, _ = _session([_INIT, _req(2, "tools/list")])
        by = {r.get("id"): r for r in resps}
        self.assertEqual(by[2]["result"]["tools"], self.defs)

    def test_markers_finding_is_success_result(self):
        text = ("Согласно :contentReference[oaicite:12]{index=12}, заявок "
                "стало больше на 12% — https://example.com/r?utm_source=chatgpt.com")
        resps, _ = _session([_INIT, _req(2, "tools/call", {
            "name": "humanizer_markers", "arguments": {"text": text}})])
        r = resps[1]["result"]
        self.assertIs(r["isError"], False)
        sc = r["structuredContent"]
        self.assertEqual(sc["tool"], "humanizer-markers")
        self.assertGreaterEqual(sc["files"][0]["count"], 2)
        self.assertEqual(self.schema_errors(sc, self._schema("humanizer_markers")),
                         [])

    def test_scan_out_of_scope(self):
        resps, _ = _session([_INIT, _req(2, "tools/call", {
            "name": "humanizer_scan",
            "arguments": {"text": "Plain English only."}})])
        r = resps[1]["result"]
        self.assertIs(r["isError"], False)
        self.assertEqual(r["structuredContent"]["files"][0]["status"],
                         "out-of-scope")
        self.assertEqual(
            self.schema_errors(r["structuredContent"],
                               self._schema("humanizer_scan")), [])

    def test_polish_modes(self):
        src = 'Проза "цитата"... **жирный**\n'
        for mode, expect_guillemets, expect_bold in (
                ("typographic", True, True),
                ("preserve-markup", False, True),
                ("strip", False, False)):
            with self.subTest(mode=mode):
                resps, _ = _session([_INIT, _req(2, "tools/call", {
                    "name": "humanizer_polish",
                    "arguments": {"text": src, "mode": mode}})])
                r = resps[1]["result"]
                self.assertIs(r["isError"], False)
                sc = r["structuredContent"]
                self.assertEqual(
                    self.schema_errors(sc, self._schema("humanizer_polish")),
                    [])
                polished = r["content"][0]["text"]
                self.assertEqual("\u00ab" in polished, expect_guillemets)
                self.assertEqual("**" in polished, expect_bold)

    def test_detect_and_genre(self):
        resps, _ = _session([_INIT, _req(2, "tools/call", {
            "name": "humanizer_detect",
            "arguments": {"text": "Обычный русский текст без дефектов.",
                          "genre": "prose"}})])
        r = resps[1]["result"]
        self.assertIs(r["isError"], False)
        sc = r["structuredContent"]
        self.assertEqual(sc["tool"], "humanizer-detect")
        self.assertEqual(sc["files"][0]["genre"], "prose")
        self.assertEqual(self.schema_errors(sc, self._schema("humanizer_detect")),
                         [])

    def test_marker_class_param(self):
        text = ":contentReference[oaicite:1]{index=1} и ассистентом\u200b"
        resps, _ = _session([_INIT, _req(2, "tools/call", {
            "name": "humanizer_markers",
            "arguments": {"text": text, "marker_class": "a"}})])
        r = resps[1]["result"]
        self.assertIs(r["isError"], False)

    def test_idempotent_double_call(self):
        args = {"name": "humanizer_polish",
                "arguments": {"text": "Текст — с тире…", "mode": "strip"}}
        resps, _ = _session([_INIT, _req(2, "tools/call", args),
                             _req(3, "tools/call", args)])
        a = resps[1]["result"]["structuredContent"]
        b = resps[2]["result"]["structuredContent"]
        # Поле file несёт путь временного каталога вызова — он не часть
        # семантики; сравниваем содержательные поля.
        for env in (a, b):
            for entry in env.get("files", []):
                entry.pop("file", None)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
