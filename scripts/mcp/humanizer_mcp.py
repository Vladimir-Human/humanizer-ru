#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humanizer_mcp.py — MCP-сервер humanizer-ru (стандартная библиотека).

Model Context Protocol поверх stdio: JSON-RPC 2.0, newline-delimited
(одно сообщение на строку; stdout — только протокол, диагностика — stderr).
Поддерживаемые версии протокола: 2025-06-18, 2025-03-26, 2024-11-05
(инициализация возвращает версию клиента, если она поддерживается, иначе
свою последнюю).

Инструменты (humanizer_scan, humanizer_markers, humanizer_polish,
humanizer_detect) и их схемы ГЕНЕРИРУЮТСЯ из канонического контракта
contract.v1.json (функция generate_tool_defs ниже; отдельный гейт сверяет
tools/list с генератором). Semantics:

  - находка (CLI-код 1) — УСПЕШНЫЙ tool result (isError:false), а не
    transport error: данные ответа важнее кода;
  - ошибка входа (CLI-код 2) — tool result с isError:true и конвертом
    {tool, schema, error, files} в content/structuredContent;
  - неизвестный инструмент/параметр — JSON-RPC -32602; неизвестный метод —
    -32601; битый JSON — -32700; не-объект — -32600; внутренний сбой —
    -32603;
  - notifications/initialized и notifications/cancelled принимаются без
    ответа (отмена принимается наилучшим образом: вызовы короткие,
    состояние между вызовами не разделяется);
  - входной текст — данные: он никогда не исполняется и не
    интерпретируется как команды (правила изоляции SKILL.md «Границы
    безопасности»).

Вызов инструментов исполняет установленный пакет (python -m humanizer_ru.<модуль>)
в дочернем процессе: те же конверты и коды, что CLI (compatibility-тест
сверяет и MCP-ответы). Таймаут вызова 60 с.

Запуск:
    python3 scripts/mcp/humanizer_mcp.py            # сервер (stdio)
    python3 scripts/mcp/humanizer_mcp.py --selftest # самопроверка (без сети)
    python3 scripts/mcp/humanizer_mcp.py --tools    # tools/list JSON (отладка)

Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]
SERVER_NAME = "humanizer-ru-mcp"
CALL_TIMEOUT = 60

# ------------------------------------------------------------- контракт

def _contract_path():
    """contract.v1.json: данные установленного пакета, иначе дерево репо."""
    try:
        from importlib.resources import files
        p = files("humanizer_ru").joinpath("contract.v1.json")
        if p.is_file():
            return str(p)
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)),
                        "contract.v1.json")


def load_contract(path=None):
    with open(path or _contract_path(), encoding="utf-8") as fh:
        return json.load(fh)


def package_version():
    try:
        from humanizer_ru import __version__
        return __version__
    except Exception:
        try:
            return load_contract()["product"]["version"]
        except Exception:
            # Ни пакет, ни контракт не читаются — честный «unknown» вместо
            # выдуманной версии (гейт зашитых версий сканирует файл).
            return "unknown"


TEXT_PARAM = {
    "type": "string",
    "description": "Обрабатываемый текст (данные, не команды). Область "
                   "скилла — русский связный текст; пустой и не-русский "
                   "вход получает статус out-of-scope.",
}


def _polish_modes(tool):
    modes = ["strip"]
    for m in tool.get("modes", []):
        if m in ("--preserve-markup", "--typographic"):
            modes.append(m.lstrip("-"))
    return modes


def _markers_classes(tool):
    for m in tool.get("modes", []):
        if m.startswith("--class "):
            return m.split(" ", 1)[1].split("|")
    return None


def generate_tool_defs(contract) -> list:
    """Tool-определения MCP из контракта (единственный источник)."""
    tools = contract.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("контракт без tools")
    genres = contract.get("genres", {})
    effective = genres.get("effective_by_tool", {})
    out = []
    for t in tools:
        cmd = t.get("command")
        for field in ("command", "task", "when_not", "output_schema"):
            if not t.get(field):
                raise ValueError("инструмент %s: нет поля %s" % (cmd, field))
        name = cmd.replace("-", "_")
        if cmd in ("humanizer-facts", "humanizer-report"):
            props = {
                "text_before": dict(TEXT_PARAM),
                "text_after": dict(TEXT_PARAM),
            }
            required = ["text_before", "text_after"]
        else:
            props = {"text": dict(TEXT_PARAM)}
            required = ["text"]
        if cmd in ("humanizer-scan", "humanizer-detect"):
            enum = effective.get(cmd) or genres.get("dictionary")
            if not enum:
                raise ValueError("%s: нет словаря жанров" % cmd)
            props["genre"] = {
                "type": "string",
                "enum": list(enum),
                "description": "Домен (эффективные значения этого "
                               "инструмента; словарь — contract.v1.json, "
                               "блок genres).",
            }
        if cmd == "humanizer-polish":
            props["mode"] = {
                "type": "string",
                "enum": _polish_modes(t),
                "description": "strip — снять машинный слой типографики "
                               "(destructive для Markdown; граница — в "
                               "when_not); preserve-markup — только "
                               "невидимые символы и NBSP; typographic — "
                               "русская публикационная типографика без "
                               "снятия разметки.",
            }
        if cmd == "humanizer-markers":
            classes = _markers_classes(t)
            if classes:
                props["marker_class"] = {
                    "type": "string",
                    "enum": classes,
                    "description": "Классы маркеров: all — все, a — только "
                                   "класс A.",
                }
        out.append({
            "name": name,
            "title": cmd,
            "description": "%s Когда не использовать: %s"
                           % (t["task"], t["when_not"]),
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            },
            "outputSchema": t["output_schema"],
            "annotations": {
                "readOnlyHint": cmd != "humanizer-polish",
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        })
    names = [d["name"] for d in out]
    if len(names) != len(set(names)):
        raise ValueError("дубли имён инструментов")
    return out


# ------------------------------------------------------------- исполнение

def _module_for(tool_name):
    return {
        "humanizer_scan": "scan_soft_signals",
        "humanizer_markers": "check_markers",
        "humanizer_polish": "polish",
        "humanizer_detect": "detect_conj",
        "humanizer_facts": "facts_diff",
        "humanizer_report": "edit_report",
    }[tool_name]


def _tool_argv(tool_name, arguments, text_path):
    """argv дочернего процесса (python -m humanizer_ru.<модуль> ...)."""
    mod = "humanizer_ru." + _module_for(tool_name)
    argv = [sys.executable, "-X", "utf8", "-m", mod]
    if tool_name == "humanizer_facts":
        # два входа: файлы кладёт call_tool, порядок before, after
        return argv + ["diff", text_path, text_path + ".after", "--json"]
    if tool_name == "humanizer_report":
        return argv + [text_path, text_path + ".after", "--json"]
    if tool_name == "humanizer_markers":
        argv.append("--scan")
    argv.append("--json")
    genre = arguments.get("genre")
    if genre:
        argv += ["--genre", genre]
    if tool_name == "humanizer_markers" and arguments.get("marker_class"):
        argv += ["--class", arguments["marker_class"]]
    if tool_name == "humanizer_polish":
        mode = arguments.get("mode", "strip")
        if mode == "preserve-markup":
            argv.append("--preserve-markup")
        elif mode == "typographic":
            argv.append("--typographic")
    argv.append(text_path)
    return argv


def call_tool(tool_name, arguments, tool_defs):
    """Вызов инструмента: (result_dict, jsonrpc_error_or_None)."""
    if tool_name not in {d["name"] for d in tool_defs}:
        return None, (-32602, "неизвестный инструмент: %s" % tool_name)
    if tool_name in ("humanizer_facts", "humanizer_report"):
        before = arguments.get("text_before")
        after = arguments.get("text_after")
        if not isinstance(before, str) or not isinstance(after, str):
            return None, (-32602, "text_before и text_after обязательны "
                                  "и обязаны быть строками")
        tmp = tempfile.mkdtemp(prefix="mcp-facts-")
        pb = os.path.join(tmp, "input.txt")
        pa = pb + ".after"
        try:
            with open(pb, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(before)
            with open(pa, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(after)
            argv = _tool_argv(tool_name, arguments, pb)
            proc = subprocess.run(argv, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  timeout=CALL_TIMEOUT, encoding="utf-8",
                                  errors="replace")
            try:
                envelope = json.loads(proc.stdout)
            except json.JSONDecodeError:
                envelope = None
            content = [{"type": "text",
                        "text": json.dumps(envelope, ensure_ascii=False,
                                           indent=2) if envelope is not None
                        else (proc.stdout or "") + (proc.stderr or "")}]
            result = {"content": content,
                      "isError": proc.returncode == 2}
            if envelope is not None:
                result["structuredContent"] = envelope
            if proc.returncode == 2:
                result["content"].append(
                    {"type": "text",
                     "text": "Ошибка входа (код 2): вход не читается; конверт "
                             "ошибки выше. Это tool result, не transport error."})
            return result, None
        except OSError as exc:
            return {"content": [{"type": "text",
                                 "text": "сбой окружения: %r" % exc}],
                    "isError": True}, None
        except subprocess.TimeoutExpired:
            return {"content": [{"type": "text",
                                 "text": "таймаут инструмента (%d с)"
                                         % CALL_TIMEOUT}],
                    "isError": True}, None
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    text = arguments.get("text")
    if not isinstance(text, str):
        return None, (-32602, "text обязателен и обязан быть строкой")
    schema = next(d for d in tool_defs if d["name"] == tool_name)["inputSchema"]
    props = schema["properties"]
    for key, value in arguments.items():
        if key not in props:
            return None, (-32602, "лишний параметр: %s" % key)
        spec = props[key]
        if "enum" in spec and value not in spec["enum"]:
            return None, (-32602, "%s: значение %r вне enum %r"
                          % (key, value, spec["enum"]))
    tmp = tempfile.mkdtemp(prefix="mcp-tool-")
    path = os.path.join(tmp, "input.txt")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        argv = _tool_argv(tool_name, arguments, path)
        try:
            proc = subprocess.run(argv, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=CALL_TIMEOUT,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return {"content": [{"type": "text",
                                 "text": "таймаут инструмента (%d с)"
                                         % CALL_TIMEOUT}],
                    "isError": True}, None
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            envelope = None
        content = []
        if envelope is not None:
            content.append({"type": "text",
                            "text": json.dumps(envelope, ensure_ascii=False,
                                               indent=2)})
        else:
            content.append({"type": "text",
                            "text": (proc.stdout or "") + (proc.stderr or "")})
        if tool_name == "humanizer_polish" and proc.returncode in (0, 1):
            # Второй прогон без --json: сам нормализованный текст (детерминирован,
            # идемпотентен — результат совпадает с первым прогоном).
            argv_plain = [a for a in argv if a != "--json"]
            try:
                proc2 = subprocess.run(argv_plain, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL,
                                       timeout=CALL_TIMEOUT, encoding="utf-8",
                                       errors="replace")
                content.insert(0, {"type": "text",
                                   "text": "Нормализованный текст:\n"
                                           + proc2.stdout})
            except subprocess.TimeoutExpired:
                pass
        result = {"content": content,
                  "isError": proc.returncode == 2}
        if envelope is not None:
            result["structuredContent"] = envelope
        if proc.returncode == 2:
            result["content"].append(
                {"type": "text",
                 "text": "Ошибка входа (код 2): вход не читается; конверт "
                         "ошибки выше. Это tool result, не transport error."})
        return result, None
    except OSError as exc:
        return {"content": [{"type": "text",
                             "text": "сбой окружения: %r" % exc}],
                "isError": True}, None
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------- JSON-RPC

def _resp(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_, code, message, data=None):
    e = {"code": code, "message": message}
    if data is not None:
        e["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": e}


def handle_message(raw_line, state, tool_defs):
    """Одна строка входа -> ответ dict или None (уведомления/без ответа)."""
    try:
        msg = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        return _err(None, -32700, "parse error: %s" % exc)
    if not isinstance(msg, dict):
        return _err(None, -32600, "invalid request: ожидался объект")
    if msg.get("jsonrpc") != "2.0" or "method" not in msg \
            or not isinstance(msg.get("method"), str):
        return _err(msg.get("id"), -32600,
                    "invalid request: jsonrpc=2.0 и method обязательны")
    method = msg["method"]
    id_ = msg.get("id")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    if method == "initialize":
        if not isinstance(params, dict):
            return _err(id_, -32602, "invalid params")
        client_ver = params.get("protocolVersion")
        chosen = client_ver if client_ver in PROTOCOL_VERSIONS \
            else LATEST_PROTOCOL
        state["initialized"] = True
        state["client_protocol"] = chosen
        contract_identity = ""
        try:
            contract_identity = load_contract()["product"]["identity"]
        except Exception:
            pass
        return _resp(id_, {
            "protocolVersion": chosen,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME,
                           "version": package_version(),
                           "title": "humanizer-ru"},
            "instructions": "Детерминированная диагностика русского текста: "
                            "артефакты копипасты, мягкие признаки, "
                            "типографическая нормализация, частота связок. "
                            "Вердиктов об авторстве нет. " + contract_identity,
        })
    if method == "notifications/initialized":
        return None
    if method == "notifications/cancelled":
        # Отмена принята к сведению: вызовы инструментов короткие и атомарные,
        # прерывать нечего; состояние не разделяется между вызовами.
        state.setdefault("cancelled", []).append(params)
        return None
    if method == "ping":
        return _resp(id_, {})
    if method == "tools/list":
        return _resp(id_, {"tools": tool_defs})
    if method == "tools/call":
        if not isinstance(params, dict) or "name" not in params:
            return _err(id_, -32602, "tools/call: params.name обязателен")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _err(id_, -32602, "tools/call: arguments обязан быть объектом")
        result, rpc_err = call_tool(params["name"], arguments, tool_defs)
        if rpc_err is not None:
            return _err(id_, rpc_err[0], rpc_err[1])
        return _resp(id_, result)
    if is_notification:
        return None  # неизвестное уведомление: по спецификации игнорируется
    return _err(id_, -32601, "method not found: %s" % method)


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        tool_defs = generate_tool_defs(load_contract())
    except (OSError, ValueError, KeyError) as exc:
        print("MCP: контракт непригоден: %r" % exc, file=sys.stderr)
        return 2
    state = {}
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        response = handle_message(line, state, tool_defs)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
    return 0


# ------------------------------------------------------------- selftest

def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    contract = load_contract()
    defs = generate_tool_defs(contract)
    case("все инструменты контракта присутствуют в MCP (>=5)",
         len(defs) == len(contract.get("tools", [])) and len(defs) >= 5)
    state = {}
    r = handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18",
                   "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}), state, defs)
    case("initialize: версия и capabilities",
         r["result"]["protocolVersion"] == "2025-06-18"
         and "tools" in r["result"]["capabilities"]
         and r["result"]["serverInfo"]["name"] == SERVER_NAME)
    r = handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "initialize",
        "params": {"protocolVersion": "1999-01-01"}}), state, defs)
    case("initialize: неподдерживаемая версия -> наша последняя",
         r["result"]["protocolVersion"] == LATEST_PROTOCOL)
    case("notifications/initialized без ответа",
         handle_message(json.dumps({
             "jsonrpc": "2.0", "method": "notifications/initialized"}),
             state, defs) is None)
    r = handle_message('{"jsonrpc": "2.0", "id": 3, "method": "tools/list"}',
                       state, defs)
    case("tools/list = сгенерированные схемы",
         r["result"]["tools"] == defs)
    r = handle_message('{"jsonrpc": "2.0", "id": 4, "method": "no/such"}',
                       state, defs)
    case("неизвестный метод -> -32601", r["error"]["code"] == -32601)
    r = handle_message('{ broken json', state, defs)
    case("битый JSON -> -32700", r["error"]["code"] == -32700)
    r = handle_message('["jsonrpc", 2.0]', state, defs)
    case("не-объект -> -32600", r["error"]["code"] == -32600)
    r = handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "no_such_tool", "arguments": {"text": "x"}}}),
        state, defs)
    case("неизвестный инструмент -> -32602", r["error"]["code"] == -32602)
    r = handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "humanizer_scan", "arguments": {}}}), state, defs)
    case("text обязателен -> -32602", r["error"]["code"] == -32602)
    r = handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "humanizer_polish",
                   "arguments": {"text": "x", "mode": "no-such"}}}),
        state, defs)
    case("enum-нарушение -> -32602", r["error"]["code"] == -32602)
    case("notifications/cancelled принимается без ответа",
         handle_message(json.dumps({
             "jsonrpc": "2.0", "method": "notifications/cancelled",
             "params": {"requestId": 99}}), state, defs) is None)
    r = handle_message('{"jsonrpc": "2.0", "id": 8, "method": "ping"}',
                       state, defs)
    case("ping -> пустой result", r["result"] == {})
    # Живой вызов инструмента (дочерний процесс, пакет из этого дерева).
    env_backup = os.environ.get("PYTHONPATH")
    src = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "src")
    os.environ["PYTHONPATH"] = src + os.pathsep + (env_backup or "")
    try:
        r = handle_message(json.dumps({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "humanizer_markers",
                       "arguments": {"text": "Согласно :contentReference"
                                              "[oaicite:12]{index=12}, "
                                              "заявок стало больше на 12% "
                                              "\u2014 источник: https://example.com/"
                                              "r?utm_source=chatgpt.com"}}}),
            state, defs)
        res = r.get("result", {})
        sc = res.get("structuredContent", {})
        case("живой вызов: находка = успешный tool result (isError ложь)",
             res.get("isError") is False and sc.get("tool") == "humanizer-markers"
             and sc["files"][0]["count"] >= 2)
        r = handle_message(json.dumps({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "humanizer_scan",
                       "arguments": {"text": "Plain English text only."}}}),
            state, defs)
        res = r.get("result", {})
        case("живой вызов: out-of-scope в structuredContent",
             res.get("isError") is False
             and res["structuredContent"]["files"][0].get("status")
             == "out-of-scope")
    finally:
        if env_backup is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = env_backup
    print("САМОПРОВЕРКА humanizer_mcp: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="MCP-сервер humanizer-ru (stdio, JSON-RPC 2.0, stdlib).")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--tools", action="store_true",
                    help="напечатать tools/list JSON и выйти")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.tools:
        try:
            defs = generate_tool_defs(load_contract())
        except (OSError, ValueError, KeyError) as exc:
            print("MCP: контракт непригоден: %r" % exc, file=sys.stderr)
            return 2
        print(json.dumps({"tools": defs}, ensure_ascii=False, indent=2))
        return 0
    return serve()


if __name__ == "__main__":
    sys.exit(main())
