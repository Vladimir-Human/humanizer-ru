#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_mcp.py — гейт MCP-сервера: conformance-ядро и сверка с контрактом.

Проверяет живой сервер `scripts/mcp/humanizer_mcp.py` (или модуль пакета
`humanizer_ru.mcp_server`, если дерева нет — sdist-контекст) scripted-
сессией по stdio:

  1. initialize: protocolVersion из поддерживаемого списка возвращается
     как есть, неподдерживаемый — заменяется последним; capabilities.tools
     присутствует; serverInfo.name/version.
  2. Уведомления (notifications/initialized, notifications/cancelled) не
     получают ответа; ping получает пустой result.
  3. tools/list ПОБАЙТОВО равен схемам, сгенерированным из
     contract.v1.json (generate_tool_defs) — «schemas генерируются из
     канонического контракта; гейт сверяет».
  4. tools/call: находка (CLI-код 1) — успешный tool result (isError
     false), structuredContent валиден относительно outputSchema контракта
     (мини-валидатор check_contract); out-of-scope на английском входе;
     режимы polish (typographic ставит ёлочки); неизвестный инструмент и
     отсутствующий text — -32602; неизвестный метод — -32601; битый JSON —
     -32700; не-объект — -32600.
  5. Framing: каждое сообщение — одна строка JSON с тем же id.

Самопроверка: негативные кейсы на синтетических ответах (оценщик
_evaluate обязан их ловить) + короткая живая сессия.

Запуск:
    python3 scripts/check_mcp.py             # проверка
    python3 scripts/check_mcp.py --selftest

Коды: 0 — conformance-ядро цело; 1 — нарушение; 2 — сервер не запускается.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER_SCRIPT = os.path.join(ROOT, "scripts", "mcp", "humanizer_mcp.py")

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "mcp"))

MARKER_TEXT = ("Согласно отчёту :contentReference[oaicite:12]{index=12}, "
               "число заявок за неделю выросло на 12% — источник: "
               "https://example.com/report?utm_source=chatgpt.com")
EN_TEXT = "Plain English text without any Russian words at all."
RU_TEXT = "Обычный русский текст. Второй абзац без дефектов."


def _server_argv():
    if os.path.isfile(SERVER_SCRIPT):
        return [sys.executable, "-X", "utf8", SERVER_SCRIPT]
    # sdist-контекст: модуль установленного пакета.
    return [sys.executable, "-X", "utf8", "-m", "humanizer_ru.mcp_server"]


def run_session(messages, timeout=180):
    """Кормит сервер списком строк, возвращает список распарсенных ответов."""
    payload = "".join(m if m.endswith("\n") else m + "\n" for m in messages)
    env = dict(os.environ)
    src = os.path.join(ROOT, "src")
    if os.path.isdir(src):
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(_server_argv(), input=payload,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, encoding="utf-8",
                              errors="replace", env=env, cwd=ROOT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("сервер не запустился: %r" % exc)
    responses = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError as exc:
            responses.append({"_framing_error": str(exc), "_line": line})
    return responses, proc


def _req(id_, method, params=None):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, ensure_ascii=False)


def _note(method, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, ensure_ascii=False)


def build_session():
    """Скриптованная conformance-сессия (строки входа)."""
    return [
        _req(1, "initialize", {"protocolVersion": "2025-06-18",
                               "capabilities": {},
                               "clientInfo": {"name": "check_mcp",
                                              "version": "1.0"}}),
        _note("notifications/initialized"),
        _req(2, "tools/list"),
        _req(3, "tools/call", {"name": "humanizer_markers",
                               "arguments": {"text": MARKER_TEXT}}),
        _req(4, "tools/call", {"name": "humanizer_scan",
                               "arguments": {"text": EN_TEXT}}),
        _req(5, "tools/call", {"name": "humanizer_polish",
                               "arguments": {"text": 'Проза "цитата"...',
                                             "mode": "typographic"}}),
        _req(6, "tools/call", {"name": "humanizer_detect",
                               "arguments": {"text": RU_TEXT}}),
        _note("notifications/cancelled", {"requestId": 3}),
        _req(7, "ping"),
        _req(8, "no/such-method"),
        "{ broken json",
        '["not", "an", "object"]',
        _req(9, "tools/call", {"name": "no_such_tool",
                               "arguments": {"text": "x"}}),
        _req(10, "tools/call", {"name": "humanizer_scan", "arguments": {}}),
    ]


def _evaluate(responses, defs):
    """Чистый оценщик: список нарушений conformance-ядра."""
    import check_contract
    errors = []
    by_id = {}
    for r in responses:
        if "_framing_error" in r:
            errors.append("framing: строка не JSON: %s" % r["_framing_error"])
            continue
        if r.get("jsonrpc") != "2.0":
            errors.append("framing: ответ без jsonrpc=2.0")
        if "id" in r:
            by_id[r["id"]] = r
    # Уведомления не должны порождать ответы: сессия из 14 сообщений даёт
    # ровно 12 ответов (10 запросов с id + 2 ошибки с id null на битый JSON
    # и не-объект); лишний ответ — признак нарушения framing/уведомлений.
    if len(responses) > 12:
        errors.append("уведомления порождают лишние ответы (%d)"
                      % len(responses))

    def result(id_):
        r = by_id.get(id_)
        return r.get("result") if r and "result" in r else None

    def err(id_):
        r = by_id.get(id_)
        return r.get("error") if r and "error" in r else None

    init = result(1)
    if not init:
        errors.append("initialize: нет result")
    else:
        if init.get("protocolVersion") != "2025-06-18":
            errors.append("initialize: protocolVersion %r != запрошенной"
                          % init.get("protocolVersion"))
        if "tools" not in (init.get("capabilities") or {}):
            errors.append("initialize: capabilities без tools")
        if (init.get("serverInfo") or {}).get("name") != "humanizer-ru-mcp":
            errors.append("initialize: serverInfo.name не то")
    tl = result(2)
    if not tl or tl.get("tools") != defs:
        errors.append("tools/list != схемам, сгенерированным из контракта")
    m = result(3)
    if not m:
        errors.append("tools/call markers: нет result")
    else:
        if m.get("isError") is not False:
            errors.append("находка маркеров обязана быть успешным tool "
                          "result (isError false), а не ошибкой")
        sc = m.get("structuredContent") or {}
        if sc.get("tool") != "humanizer-markers" or sc["files"][0]["count"] < 2:
            errors.append("markers: конверт/счёт не те (count=%s)"
                          % sc.get("files", [{}])[0].get("count"))
        errors.extend("markers schema: %s" % e
                      for e in check_contract.schema_errors(
                          sc, _schema_for(defs, "humanizer_markers")))
    s = result(4)
    if not s or (s.get("structuredContent", {})
                 .get("files", [{}])[0].get("status")) != "out-of-scope":
        errors.append("scan на английском: ожидался status out-of-scope")
    p = result(5)
    if not p:
        errors.append("polish typographic: нет result")
    else:
        text0 = (p.get("content") or [{}])[0].get("text", "")
        if "\u00ab" not in text0:
            errors.append("polish typographic: ёлочки не поставлены")
        if p.get("isError") is not False:
            errors.append("polish typographic: isError обязан быть false")
    d = result(6)
    if not d or (d.get("structuredContent") or {}).get("tool") \
            != "humanizer-detect":
        errors.append("detect: конверт не тот")
    if result(7) != {}:
        errors.append("ping: ожидался пустой result")
    e8 = err(8)
    if not e8 or e8.get("code") != -32601:
        errors.append("неизвестный метод: ожидался -32601")
    e_null = None
    for r in responses:
        if r.get("id") is None and "error" in r:
            e_null = r["error"]
            break
    if not e_null or e_null.get("code") not in (-32700, -32600):
        errors.append("битый JSON/не-объект: ожидался -32700/-32600 с id null")
    e9 = err(9)
    if not e9 or e9.get("code") != -32602:
        errors.append("неизвестный инструмент: ожидался -32602")
    e10 = err(10)
    if not e10 or e10.get("code") != -32602:
        errors.append("отсутствующий text: ожидался -32602")
    return errors


def _schema_for(defs, name):
    for d in defs:
        if d["name"] == name:
            return d["outputSchema"]
    return {}


def check() -> tuple:
    """(ошибки, отказ-среды)."""
    import humanizer_mcp
    try:
        defs = humanizer_mcp.generate_tool_defs(humanizer_mcp.load_contract())
    except (OSError, ValueError, KeyError) as exc:
        return ["контракт непригоден для генерации схем: %r" % exc], True
    try:
        responses, proc = run_session(build_session())
    except RuntimeError as exc:
        return [str(exc)], True
    if proc.returncode != 0 and not responses:
        return ["сервер завершился с кодом %d без ответов: %s"
                % (proc.returncode, (proc.stderr or "")[-300:])], True
    return _evaluate(responses, defs), False


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    import humanizer_mcp
    defs = humanizer_mcp.generate_tool_defs(humanizer_mcp.load_contract())
    # Негативы на синтетике: оценщик обязан ловить подмены.
    fake = [
        {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "1999-01-01",
            "capabilities": {}, "serverInfo": {"name": "other"}}},
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
        {"jsonrpc": "2.0", "id": 3, "result": {
            "content": [], "isError": True}},
    ]
    errs = _evaluate(fake, defs)
    case("подделанные ответы ловятся (негатив)", len(errs) >= 5)
    ok_resp = [
        {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "humanizer-ru-mcp", "version": "x"}}},
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": defs}},
        {"jsonrpc": "2.0", "id": 3, "result": {
            "content": [{"type": "text", "text": "{}"}], "isError": False,
            "structuredContent": {
                "tool": "humanizer-markers", "schema": 1,
                "files": [{"file": "x", "markers": [
                    {"line": 1, "marker": "contentReference", "class": "A",
                     "fragment": "f", "shadow": False},
                    {"line": 1, "marker": "utm_chatgpt", "class": "A",
                     "fragment": "f", "shadow": False}],
                    "count": 2, "warnings_b": 0}]}}},
        {"jsonrpc": "2.0", "id": 4, "result": {
            "content": [], "isError": False,
            "structuredContent": {
                "tool": "humanizer-scan", "schema": 1,
                "files": [{"file": "en.txt", "status": "out-of-scope",
                           "features_total": 0, "categories_total": 0,
                           "recommendation": "вне области"}]}}},
        {"jsonrpc": "2.0", "id": 5, "result": {
            "content": [{"type": "text", "text": "«цитата»"}],
            "isError": False}},
        {"jsonrpc": "2.0", "id": 6, "result": {
            "content": [], "isError": False,
            "structuredContent": {"tool": "humanizer-detect", "schema": 1,
                                  "files": [{"file": "x"}]}}},
        {"jsonrpc": "2.0", "id": 7, "result": {}},
        {"jsonrpc": "2.0", "id": 8, "error": {"code": -32601, "message": "x"}},
        {"jsonrpc": "2.0", "id": None,
         "error": {"code": -32700, "message": "x"}},
        {"jsonrpc": "2.0", "id": 9, "error": {"code": -32602, "message": "x"}},
        {"jsonrpc": "2.0", "id": 10, "error": {"code": -32602, "message": "x"}},
    ]
    case("корректная сессия проходит оценщик", _evaluate(ok_resp, defs) == [])
    # Живая сессия (короткая): initialize + tools/list.
    responses, proc = run_session([
        _req(1, "initialize", {"protocolVersion": "2024-11-05",
                               "capabilities": {},
                               "clientInfo": {"name": "st", "version": "0"}}),
        _req(2, "tools/list"),
    ], timeout=120)
    by = {r.get("id"): r for r in responses if "id" in r}
    case("живая сессия: версия 2024-11-05 поддерживается",
         by.get(1, {}).get("result", {}).get("protocolVersion")
         == "2024-11-05")
    with open(os.path.join(ROOT, "contract.v1.json"), encoding="utf-8") as fh:
        _n_tools = len(json.load(fh).get("tools", []))
    case("живая сессия: tools/list равен числу инструментов контракта",
         len(by.get(2, {}).get("result", {}).get("tools", [])) == _n_tools
         and _n_tools >= 5)
    print("САМОПРОВЕРКА check_mcp: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Conformance-ядро MCP-сервера и сверка схем с контрактом.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errors, env_fail = check()
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("MCP: нарушений %d" % len(errors))
        return 1
    if env_fail:
        print("MCP: проверка невозможна (среда)", file=sys.stderr)
        return 2
    print("MCP: conformance-ядро зелёное, схемы = контракт")
    return 0


if __name__ == "__main__":
    sys.exit(main())
