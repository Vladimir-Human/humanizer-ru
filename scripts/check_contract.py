#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_contract.py — гейт машинного контракта (Фаза 2.4 + housekeeping-патч).

Проверяет:
  1. `contract.v1.json` структурно валиден и несёт все инструменты пакета;
     у каждого инструмента есть реальная JSON-схема вывода (output_schema)
     с const-версией >= 1, а у humanizer-polish — поле transformation и
     честное when_not («не запускать на Markdown и разметке»).
  2. Живые выводы `--json` инструментов соответствуют output_schema из
     контракта (мини-валидатор подмножества JSON Schema: type, properties,
     required, items, const, enum, anyOf, minItems).
  3. Честная граница polish присутствует во всех витринных носителях
     (contract.v1.json, README.md, README.en.md, README.pypi.md, llms.txt)
     и в тексте `polish.py --help`.
  4. Поведение out-of-scope: английский и пустой вход дают status
     «out-of-scope» (не «правка не требуется»); нечитаемый файл с --json
     даёт конверт {tool, schema, error, files} в stdout при коде 2.
  5. У каждого инструмента в контракте есть файл скрипта.

Самопроверка — с негативными кейсами (битый конверт, чужое имя, дрейф
версии схемы, тип не из схемы).

Запуск из корня репозитория:
    python3 scripts/check_contract.py             # проверка
    python3 scripts/check_contract.py --selftest  # самопроверка

Коды: 0 — контракт цел; 1 — нарушение; 2 — ошибка входа.
Только стандартная библиотека.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTRACT_PATH = os.path.join(ROOT, "contract.v1.json")
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "polish")

EXPECTED_TOOLS = {
    "humanizer-polish": ("scripts", "polish.py"),
    "humanizer-detect": ("scripts", "detect_conj.py"),
    "humanizer-markers": ("scripts", "check_markers.py"),
    "humanizer-scan": ("scripts", "scan_soft_signals.py"),
    "humanizer-facts": ("src/humanizer_ru", "facts_diff.py"),
    "humanizer-report": ("src/humanizer_ru", "edit_report.py"),
}

# Честная граница polish: фраза-маркер обязана быть в каждом носителе.
POLISH_WARNING_RU = "не запускать на Markdown"
POLISH_WARNING_EN = "do not run on Markdown"
WARNING_CARRIERS_RU = ["contract.v1.json", "README.md", "README.pypi.md",
                       "llms.txt"]
WARNING_CARRIERS_EN = ["README.en.md"]
# Запрещённые использования: ключевая фраза списка обязана быть в контракте
# и в каждом зеркале (RU/EN/SKILL/llms) — правило v2 3.4.
PROHIBITED_KEY_PHRASE_RU = "сдача работ там, где ИИ запрещён"
PROHIBITED_KEY_PHRASE_EN = "submitting work where AI is prohibited"
PROHIBITED_CARRIERS_RU = ["contract.v1.json", "README.md", "README.pypi.md",
                          "llms.txt", "SKILL.md"]
PROHIBITED_CARRIERS_EN = ["README.en.md"]

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
}


def load_contract() -> dict:
    with open(CONTRACT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------ мини-валидатор

def _type_ok(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = _TYPES.get(name)
    if py is None:
        return True  # неизвестный тип не ограничивает
    if py is bool:
        return isinstance(value, bool)
    if py is dict or py is list or py is str:
        return isinstance(value, py)
    return isinstance(value, py)


def schema_errors(value, schema, where: str = "$") -> list[str]:
    """Валидация значения подмножеством JSON Schema (только stdlib).

    Поддерживаются: type, properties, required, items, const, enum, anyOf,
    minItems. Неизвестные ключи схемы игнорируются (подмножество сознательно
    узкое и документировано в докстринге модуля).
    """
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["%s: схема не объект" % where]
    if "const" in schema and value != schema["const"]:
        errors.append("%s: значение %r != const %r" % (where, value, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: значение %r вне enum %r" % (where, value, schema["enum"]))
    tname = schema.get("type")
    if tname and not _type_ok(value, tname):
        errors.append("%s: тип %s, ожидался %s" % (where, type(value).__name__, tname))
        return errors
    if "anyOf" in schema:
        variants = [schema_errors(value, sub, where) for sub in schema["anyOf"]]
        if all(v for v in variants):
            errors.append("%s: ни один вариант anyOf не подошёл" % where)
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append("%s: нет обязательного поля %s" % (where, req))
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                errors.extend(schema_errors(value[key], sub, "%s.%s" % (where, key)))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: элементов %d < minItems %d"
                          % (where, len(value), schema["minItems"]))
        items = schema.get("items")
        if isinstance(items, dict):
            for i, el in enumerate(value):
                errors.extend(schema_errors(el, items, "%s[%d]" % (where, i)))
    return errors


def contract_errors(doc) -> list[str]:
    errors = []
    if doc.get("schema_version") != "contract.v1":
        errors.append("schema_version должен быть 'contract.v1'")
    if doc.get("id") != "humanizer-ru-contract":
        errors.append("id должен быть 'humanizer-ru-contract'")
    if not isinstance(doc.get("exit_codes"), dict) or not doc["exit_codes"]:
        errors.append("exit_codes обязаны быть непустым объектом")
    if not isinstance(doc.get("graduated_response"), dict):
        errors.append("graduated_response обязан быть объектом")
    tools = doc.get("tools")
    if not isinstance(tools, list) or not tools:
        errors.append("tools обязан быть непустым списком")
        return errors
    seen = set()
    for t in tools:
        cmd = t.get("command")
        if not cmd:
            errors.append("запись инструмента без command")
            continue
        seen.add(cmd)
        if cmd not in EXPECTED_TOOLS:
            errors.append("неизвестный инструмент в контракте: %s" % cmd)
            continue
        for field in ("task", "when_not", "modes"):
            if not t.get(field):
                errors.append("%s: нет поля %s" % (cmd, field))
        os_ = t.get("output_schema")
        if not isinstance(os_, dict):
            errors.append("%s: нет реальной JSON-схемы вывода (output_schema)" % cmd)
        else:
            ver = (os_.get("properties", {}).get("schema", {}) or {}).get("const")
            if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
                errors.append("%s: output_schema.properties.schema.const обязан "
                              "быть целым >= 1" % cmd)
            for req in ("tool", "schema", "files"):
                if req not in os_.get("required", []):
                    errors.append("%s: output_schema без обязательного %s" % (cmd, req))
        if cmd == "humanizer-polish":
            if not t.get("transformation"):
                errors.append("humanizer-polish: нет поля transformation "
                              "(что именно делает трансформация)")
            if POLISH_WARNING_RU.lower() not in str(t.get("when_not", "")).lower():
                errors.append("humanizer-polish: when_not обязан нести «%s»"
                              % POLISH_WARNING_RU)
        script = t.get("script")
        if not script or not os.path.isfile(os.path.join(ROOT, *script.split("/"))):
            errors.append("%s: скрипт не найден (%s)" % (cmd, script))
    missing = set(EXPECTED_TOOLS) - seen
    for cmd in sorted(missing):
        errors.append("инструмент не описан в контракте: %s" % cmd)
    pu = doc.get("prohibited_uses")
    if not isinstance(pu, dict) or not isinstance(pu.get("list"), list) \
            or not pu.get("list"):
        errors.append("нет prohibited_uses: блок с непустым list обязателен")
    else:
        joined = " ".join(str(x) for x in pu["list"]).lower()
        if PROHIBITED_KEY_PHRASE_RU.lower() not in joined:
            errors.append("prohibited_uses.list: нет ключевой фразы «%s»"
                          % PROHIBITED_KEY_PHRASE_RU)
    return errors


def wording_errors() -> list[str]:
    """Честная граница polish во всех витринных носителях (регистронезависимо:
    фраза может начинать предложение)."""
    errors = []
    for rel in WARNING_CARRIERS_RU:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            errors.append("носитель не читается: %s" % rel)
            continue
        if POLISH_WARNING_RU.lower() not in text.lower():
            errors.append("%s: нет честной границы polish («%s»)"
                          % (rel, POLISH_WARNING_RU))
    for rel in WARNING_CARRIERS_EN:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            errors.append("носитель не читается: %s" % rel)
            continue
        if POLISH_WARNING_EN.lower() not in text.lower():
            errors.append("%s: нет честной границы polish («%s»)"
                          % (rel, POLISH_WARNING_EN))
    for rel in PROHIBITED_CARRIERS_RU:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            errors.append("носитель не читается: %s" % rel)
            continue
        if PROHIBITED_KEY_PHRASE_RU.lower() not in text.lower():
            errors.append("%s: нет запрещённых использований («%s»)"
                          % (rel, PROHIBITED_KEY_PHRASE_RU))
    for rel in PROHIBITED_CARRIERS_EN:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            errors.append("носитель не читается: %s" % rel)
            continue
        if PROHIBITED_KEY_PHRASE_EN.lower() not in text.lower():
            errors.append("%s: нет запрещённых использований («%s»)"
                          % (rel, PROHIBITED_KEY_PHRASE_EN))
    return errors


def _run(argv):
    return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120, encoding="utf-8", errors="replace")


def _help_warning_error() -> list[str]:
    proc = _run([sys.executable, os.path.join(ROOT, "scripts", "polish.py"),
                 "--help"])
    if proc.returncode != 0:
        return ["polish --help: код %d" % proc.returncode]
    if POLISH_WARNING_RU.lower() not in proc.stdout.lower():
        return ["polish --help: нет предупреждения «%s»" % POLISH_WARNING_RU]
    return []


def live_check() -> list[str]:
    """Живые прогоны: схемы, out-of-scope, конверт ошибки."""
    errors = []
    try:
        doc = load_contract()
    except (OSError, json.JSONDecodeError) as exc:
        return ["контракт не читается: %r" % exc]
    schemas = {t["command"]: t.get("output_schema")
               for t in doc.get("tools", [])}
    fixture = None
    if os.path.isdir(FIXTURES):
        for name in sorted(os.listdir(FIXTURES)):
            if name.endswith((".md", ".txt")):
                fixture = os.path.join(FIXTURES, name)
                break
    if fixture is None:
        return ["нет фикстуры для живой проверки контракта"]
    probes = [
        ("humanizer-polish", [sys.executable,
                              os.path.join(ROOT, "scripts", "polish.py"),
                              "--json", fixture], (0,)),
        ("humanizer-detect", [sys.executable,
                              os.path.join(ROOT, "scripts", "detect_conj.py"),
                              "--json", "--genre", "auto", fixture], (0,)),
        # markers и scan на чистой фикстуре дают 0, на тексте с маркерами/
        # признаками — 1; оба кода законны (градуированный ответ), конверт
        # обязан быть валидным в любом случае.
        ("humanizer-markers", [sys.executable,
                               os.path.join(ROOT, "scripts", "check_markers.py"),
                               "--scan", "--json", fixture], (0, 1)),
        ("humanizer-scan", [sys.executable,
                            os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                            "--json", fixture], (0, 1)),
    ]
    for command, argv, ok_codes in probes:
        try:
            proc = _run(argv)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append("%s: запуск не удался: %r" % (command, exc))
            continue
        if proc.returncode not in ok_codes:
            errors.append("%s: код %d: %s"
                          % (command, proc.returncode, proc.stderr.strip()[:200]))
            continue
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            errors.append("%s: вывод не JSON: %r" % (command, exc))
            continue
        if payload.get("tool") != command:
            errors.append("%s: в конверте чужое имя %r"
                          % (command, payload.get("tool")))
        schema = schemas.get(command)
        if isinstance(schema, dict):
            errors.extend("%s: %s" % (command, e)
                          for e in schema_errors(payload, schema))
        else:
            errors.append("%s: в контракте нет output_schema" % command)

    # out-of-scope: английский и пустой вход — status out-of-scope, код 0.
    with tempfile.TemporaryDirectory(prefix="contract-scope-") as td:
        en = os.path.join(td, "en.txt")
        empty = os.path.join(td, "empty.txt")
        with open(en, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("Plain English text without any Russian words at all.\n")
        with open(empty, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("")
        for label, path in (("английский", en), ("пустой", empty)):
            proc = _run([sys.executable,
                         os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                         "--json", path])
            try:
                payload = json.loads(proc.stdout)
                status = payload["files"][0].get("status")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                status = None
            if proc.returncode != 0 or status != "out-of-scope":
                errors.append("scan на %s входе: ожидался status out-of-scope "
                              "при коде 0, получено %r (код %d)"
                              % (label, status, proc.returncode))
        # Конверт ошибки: нечитаемый файл с --json — валидный JSON с error, код 2.
        missing = os.path.join(td, "does-not-exist.txt")
        for command, script in (("humanizer-scan", "scan_soft_signals.py"),
                                ("humanizer-polish", "polish.py"),
                                ("humanizer-detect", "detect_conj.py"),
                                ("humanizer-markers", "check_markers.py")):
            argv = [sys.executable, os.path.join(ROOT, "scripts", script)]
            if command == "humanizer-markers":
                argv.append("--scan")
            argv += ["--json", missing]
            proc = _run(argv)
            ok = proc.returncode == 2
            try:
                payload = json.loads(proc.stdout)
                ok = ok and payload.get("tool") == command \
                    and isinstance(payload.get("error"), str) \
                    and isinstance(payload.get("files"), list)
            except json.JSONDecodeError:
                ok = False
            if not ok:
                errors.append("%s: на нечитаемом файле с --json ожидался конверт "
                              "{tool, schema, error, files} в stdout при коде 2 "
                              "(код %d)" % (command, proc.returncode))

    # --version и --contract: точки входа пакета (cli.py) называют версию и
    # печатают контракт из данных пакета; в дереве — через PYTHONPATH=src.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep \
        + env.get("PYTHONPATH", "")
    for entry in ("scan_main", "markers_main", "polish_main", "detect_main"):
        proc = subprocess.run(
            [sys.executable, "-c",
             "from humanizer_ru.cli import %s; import sys; "
             "sys.exit(%s(['--version']))" % (entry, entry)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            encoding="utf-8", errors="replace", env=env, cwd=ROOT)
        ver = proc.stdout.strip()
        if proc.returncode != 0 or not re.match(r"^\d+\.\d+\.\d+$", ver):
            errors.append("cli.%s --version: ожидалась версия X.Y.Z, получено "
                          "%r (код %d)" % (entry, ver, proc.returncode))
        proc = subprocess.run(
            [sys.executable, "-c",
             "from humanizer_ru.cli import %s; import sys; "
             "sys.exit(%s(['--contract']))" % (entry, entry)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            encoding="utf-8", errors="replace", env=env, cwd=ROOT)
        try:
            doc2 = json.loads(proc.stdout)
            ok2 = proc.returncode == 0 \
                and doc2.get("schema_version") == "contract.v1" \
                and len(doc2.get("tools", [])) == len(doc.get("tools", []))
        except json.JSONDecodeError:
            ok2 = False
        if not ok2:
            errors.append("cli.%s --contract: ожидался контракт из данных "
                          "пакета (код %d)" % (entry, proc.returncode))
    # MCP-smoke: сервер отвечает на initialize версией из контракта и несёт
    # четыре инструмента (полное conformance-ядро — scripts/check_mcp.py).
    try:
        sys.path.insert(0, HERE)
        import check_mcp
        responses, _proc = check_mcp.run_session([
            check_mcp._req(1, "initialize",
                           {"protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "contract-smoke",
                                           "version": "0"}}),
            check_mcp._req(2, "tools/list"),
        ], timeout=120)
        by = {r.get("id"): r for r in responses if "id" in r}
        init = (by.get(1) or {}).get("result") or {}
        ver = ((init.get("serverInfo") or {}).get("version"))
        prod_ver = (doc.get("product") or {}).get("version")
        if prod_ver and ver != prod_ver:
            errors.append("MCP-smoke: serverInfo.version %r != contract "
                          "product.version %r" % (ver, prod_ver))
        tools = ((by.get(2) or {}).get("result") or {}).get("tools") or []
        if len(tools) != len(doc.get("tools", [])):
            errors.append("MCP-smoke: tools/list несёт %d инструментов, "
                          "контракт — %d" % (len(tools),
                                             len(doc.get("tools", []))))
    except Exception as exc:  # noqa: BLE001 — smoke не должен валить гейт-скрипт
        errors.append("MCP-smoke не исполнен: %r" % exc)
    errors.extend(_help_warning_error())
    errors.extend(wording_errors())
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    schema = {"type": "object",
              "required": ["tool", "schema", "files"],
              "properties": {
                  "tool": {"const": "humanizer-polish"},
                  "schema": {"const": 1},
                  "files": {"type": "array", "minItems": 1,
                            "items": {"type": "object", "required": ["file"],
                                      "properties": {
                                          "file": {"type": "string"},
                                          "changed": {"type": "boolean"}}}}}}
    good = {"tool": "humanizer-polish", "schema": 1,
            "files": [{"file": "a.md", "changed": False}]}
    case("валидный конверт проходит мини-валидатор", schema_errors(good, schema) == [])
    bad_keys = {"tool": "humanizer-polish", "files": [{"file": "a.md"}]}
    case("конверт без версии схемы валится",
         any("schema" in e for e in schema_errors(bad_keys, schema)))
    bad_ver = {"tool": "humanizer-polish", "schema": 2, "files": [{"file": "a.md"}]}
    case("дрейф версии схемы валится (const)",
         any("const" in e for e in schema_errors(bad_ver, schema)))
    empty_files = {"tool": "humanizer-polish", "schema": 1, "files": []}
    case("пустой ответ валится (minItems — градуированный ответ не пуст)",
         any("minItems" in e for e in schema_errors(empty_files, schema)))
    bad_type = {"tool": "humanizer-polish", "schema": 1,
                "files": [{"file": "a.md", "changed": "нет"}]}
    case("тип поля не из схемы валится",
         any("тип" in e for e in schema_errors(bad_type, schema)))
    bad_name = {"tool": "humanizer-scan", "schema": 1, "files": [{"file": "a"}]}
    case("чужое имя инструмента валится (const)",
         any("const" in e for e in schema_errors(bad_name, schema)))

    try:
        doc = load_contract()
        case("контракт читается и структурно валиден", contract_errors(doc) == [])
        case("все четыре инструмента описаны",
             {t["command"] for t in doc.get("tools", [])} == set(EXPECTED_TOOLS))
        case("все четыре инструмента несут output_schema с const >= 1",
             all(isinstance(t.get("output_schema"), dict)
                 and isinstance((t["output_schema"].get("properties", {})
                                 .get("schema", {}) or {}).get("const"), int)
                 and t["output_schema"]["properties"]["schema"]["const"] >= 1
                 for t in doc.get("tools", [])))
        case("polish несёт transformation и честное when_not",
             any(t.get("command") == "humanizer-polish"
                 and t.get("transformation")
                 and POLISH_WARNING_RU in str(t.get("when_not", ""))
                 for t in doc.get("tools", [])))
        case("prohibited_uses несёт ключевую фразу",
             contract_errors(doc) == [])
        no_pu = json.loads(json.dumps(doc))
        del no_pu["prohibited_uses"]
        case("контракт без prohibited_uses валится (негатив)",
             any("prohibited_uses" in e for e in contract_errors(no_pu)))
    except (OSError, json.JSONDecodeError):
        case("контракт читается и структурно валиден", False)
        case("все четыре инструмента описаны", False)
        case("все четыре инструмента несут output_schema с const >= 1", False)
        case("polish несёт transformation и честное when_not", False)
        case("prohibited_uses несёт ключевую фразу", False)
        case("контракт без prohibited_uses валится (негатив)", False)

    print("САМОПРОВЕРКА check_contract: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return selftest()
    errors = []
    try:
        doc = load_contract()
        errors.extend(contract_errors(doc))
    except (OSError, json.JSONDecodeError) as exc:
        print("КОНТРАКТ: не читается: %r" % exc, file=sys.stderr)
        return 2
    errors.extend(live_check())
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("КОНТРАКТ: нарушений %d" % len(errors))
        return 1
    print("КОНТРАКТ: машинный интерфейс соответствует contract.v1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
