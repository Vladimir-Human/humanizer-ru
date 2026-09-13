#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for MCP input validation and JSON-RPC object boundaries."""

import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
MIRROR = os.path.join(ROOT, "scripts", "mcp", "humanizer_mcp.py")
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from humanizer_ru import mcp_server as m  # noqa: E402


class TestMcpValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = m.generate_tool_defs(m.load_contract())

    def test_validate_args_rejects_wrong_primitive_types_before_argv(self):
        cases = (
            ("humanizer_facts", {
                "text_before": "до", "text_after": "после",
                "no_additions": "false",
            }),
            ("humanizer_facts", {
                "text_before": ["до"], "text_after": "после",
            }),
            ("humanizer_polish", {
                "text": "текст", "language": ["ru"],
            }),
            ("humanizer_scan", {
                "text": "текст", "genre": False,
            }),
        )
        for tool_name, arguments in cases:
            with self.subTest(tool=tool_name, arguments=arguments):
                error = m._validate_args(tool_name, arguments, self.defs)
                self.assertIsNotNone(error)
                self.assertEqual(error[0], -32602)
        self.assertIsNone(m._validate_args(
            "humanizer_facts", {"text_before": "до", "text_after": "после",
                                 "no_additions": False}, self.defs))

    def test_validate_args_requires_schema_required_fields(self):
        error = m._validate_args("humanizer_facts", {}, self.defs)
        self.assertEqual(error[0], -32602)

    def test_invalid_type_is_rejected_before_argv_construction(self):
        built = []
        original = m._tool_argv
        m._tool_argv = lambda *args, **kwargs: built.append(True)
        try:
            _result, rpc_error = m.call_tool(
                "humanizer_facts",
                {"text_before": "до", "text_after": "после",
                 "no_additions": "false"},
                self.defs)
        finally:
            m._tool_argv = original
        self.assertEqual(rpc_error[0], -32602)
        self.assertEqual(built, [])

    def test_explicit_non_object_params_are_rejected(self):
        malformed = ([], "", None, 1, True)
        for params in malformed:
            with self.subTest(params=params):
                response = m.handle_message(
                    json.dumps({"jsonrpc": "2.0", "id": 1,
                                "method": "tools/list", "params": params}),
                    {}, self.defs)
                self.assertEqual(response["error"]["code"], -32602)

    def test_explicit_non_object_arguments_are_rejected(self):
        malformed = ([], "", None, 1, True)
        for arguments in malformed:
            with self.subTest(arguments=arguments):
                response = m.handle_message(
                    json.dumps({"jsonrpc": "2.0", "id": 1,
                                "method": "tools/call",
                                "params": {"name": "humanizer_scan",
                                            "arguments": arguments}}),
                    {"initialized": True}, self.defs)
                self.assertEqual(response["error"]["code"], -32602)

    def test_invalid_requests_do_not_dispatch_and_session_continues(self):
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}]
        for value in ([], "", None, 0, False, ["ru"], {"nested": 1}):
            # The dictionary is a valid params object but an invalid language.
            if not isinstance(value, dict):
                for method in ("initialize", "tools/list", "tools/call"):
                    requests.append({"jsonrpc": "2.0", "id": len(requests) + 1,
                                     "method": method, "params": value})
                requests.append({
                    "jsonrpc": "2.0", "id": len(requests) + 1,
                    "method": "tools/call",
                    "params": {"name": "humanizer_clean", "arguments": value},
                })
            requests.append({
                "jsonrpc": "2.0", "id": len(requests) + 1,
                "method": "tools/call",
                "params": {"name": "humanizer_clean",
                           "arguments": {"text": "Текст", "language": value}},
            })
        requests.append({
            "jsonrpc": "2.0", "id": len(requests) + 1,
            "method": "tools/call",
            "params": {"name": "humanizer_facts",
                       "arguments": {"text_before": "до", "text_after": "после",
                                     "no_additions": "false"}},
        })
        requests.append({"jsonrpc": "2.0", "id": len(requests) + 1,
                         "method": "ping"})
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n"
                          for r in requests)
        output = io.StringIO()
        with mock.patch.object(m, "_tool_argv") as build_argv:
            self.assertEqual(m.serve(io.StringIO(payload), output), 0)
            build_argv.assert_not_called()
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r["id"] for r in responses],
                         [r["id"] for r in requests])
        self.assertIn("result", responses[0])
        for response in responses[1:-1]:
            with self.subTest(request_id=response["id"]):
                self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(responses[-1]["result"], {})

    def test_stdio_uses_utf8_despite_cp1251_environment(self):
        text = "Проверка текста: Ёжик 🦔 читает книгу."
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": []},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "humanizer_clean", "arguments": ""}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "humanizer_clean", "arguments": {"text": text}}},
            {"jsonrpc": "2.0", "id": 5, "method": "ping"},
        ]
        # Send actual UTF-8 bytes, not ASCII JSON escapes or locale-encoded text.
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n"
                          for r in requests).encode("utf-8")
        env = dict(os.environ, PYTHONIOENCODING="cp1251", PYTHONUTF8="0")
        if os.path.isdir(SRC):
            env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
        entrypoints = [[sys.executable, "-m", "humanizer_ru.mcp_server"]]
        if REPO_ONLY:
            entrypoints.append([sys.executable, MIRROR])
        for argv in entrypoints:
            with self.subTest(entrypoint=argv):
                proc = subprocess.run(argv, input=payload, capture_output=True,
                                      env=env, cwd=ROOT, timeout=90)
                self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
                self.assertEqual(proc.stderr, b"")
                responses = [json.loads(line) for line in
                             proc.stdout.decode("utf-8").splitlines()]
                self.assertEqual([r["id"] for r in responses], [1, 2, 3, 4, 5])
                self.assertEqual(responses[1]["error"]["code"], -32602)
                self.assertEqual(responses[2]["error"]["code"], -32602)
                result = responses[3]["result"]
                self.assertIs(result["isError"], False)
                self.assertEqual(result["structuredContent"]["files"][0]["text"],
                                 text)
                self.assertEqual(result["content"][0]["text"],
                                 "Очищенный текст:\n" + text)
                self.assertEqual(responses[4]["result"], {})

    @unittest.skipUnless(REPO_ONLY, "source/script mirror exists only in checkout")
    def test_mcp_source_and_mirror_are_byte_identical(self):
        source = os.path.join(ROOT, "src", "humanizer_ru", "mcp_server.py")
        with open(source, "rb") as fh:
            source_digest = hashlib.sha256(fh.read()).digest()
        with open(MIRROR, "rb") as fh:
            mirror_digest = hashlib.sha256(fh.read()).digest()
        self.assertEqual(source_digest, mirror_digest)


if __name__ == "__main__":
    unittest.main()
