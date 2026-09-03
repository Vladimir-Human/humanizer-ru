#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_contract.py — гейт машинного контракта (Фаза 2.4).

Проверяет:
  1. `contract.v1.json` структурно валиден и несёт все инструменты пакета.
  2. Живые выводы `--json` инструментов соответствуют конверту контракта:
     {tool, schema, files}; имя инструмента и версия схемы совпадают с
     записью контракта.
  3. У каждого инструмента в контракте есть файл скрипта.

Самопроверка — с негативными кейсами (битый конверт, чужое имя, дрейф
версии схемы).

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
}


def load_contract() -> dict:
    with open(CONTRACT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


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
        js = t.get("json_schema")
        if not isinstance(js, int) or isinstance(js, bool) or js < 1:
            errors.append("%s: json_schema обязан быть целым >= 1 — все четыре "
                          "инструмента дают --json-конверт" % cmd)
        script = t.get("script")
        if not script or not os.path.isfile(os.path.join(ROOT, *script.split("/"))):
            errors.append("%s: скрипт не найден (%s)" % (cmd, script))
    missing = set(EXPECTED_TOOLS) - seen
    for cmd in sorted(missing):
        errors.append("инструмент не описан в контракте: %s" % cmd)
    return errors


def envelope_errors(payload, command: str, schema_version: int) -> list[str]:
    """Валидация конверта {tool, schema, files} для живого вывода."""
    errors = []
    if not isinstance(payload, dict):
        return ["вывод не объект"]
    for key in ("tool", "schema", "files"):
        if key not in payload:
            errors.append("нет поля %s" % key)
    if payload.get("schema") != schema_version:
        errors.append("версия схемы %r != %r из контракта"
                      % (payload.get("schema"), schema_version))
    files = payload.get("files")
    if not isinstance(files, list):
        errors.append("files обязан быть списком")
    elif not files:
        errors.append("files пуст — градуированный ответ обязан быть непустым")
    else:
        for entry in files:
            if not isinstance(entry, dict) or "file" not in entry:
                errors.append("запись в files без поля file")
    return errors


def live_check() -> list[str]:
    """Запуск --json инструментов на фикстуре и сверка с контрактом."""
    errors = []
    try:
        doc = load_contract()
    except (OSError, json.JSONDecodeError) as exc:
        return ["контракт не читается: %r" % exc]
    schemas = {t["command"]: t.get("json_schema") for t in doc.get("tools", [])}
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
            proc = subprocess.run(argv, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=120,
                                  encoding="utf-8", errors="replace")
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
        errors.extend("%s: %s" % (command, e)
                      for e in envelope_errors(payload, command, schemas.get(command)))

    # out-of-scope: английский и пустой вход — status out-of-scope, код 0.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="contract-scope-") as td:
        en = os.path.join(td, "en.txt")
        empty = os.path.join(td, "empty.txt")
        with open(en, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("Plain English text without any Russian words at all.\n")
        with open(empty, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("")
        for label, path in (("английский", en), ("пустой", empty)):
            proc = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                 "--json", path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
                encoding="utf-8", errors="replace")
            try:
                payload = json.loads(proc.stdout)
                status = payload["files"][0].get("status")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                status = None
            if proc.returncode != 0 or status != "out-of-scope":
                errors.append("scan на %s входе: ожидался status out-of-scope "
                              "при коде 0, получено %r (код %d)"
                              % (label, status, proc.returncode))
        # Конверт ошибки: нечитаемый файл с --json — валидный JSON с error,
        # код 2 (stdout не пустой: агент всегда получает разобранный ответ).
        missing = os.path.join(td, "does-not-exist.txt")
        for command, script in (("humanizer-scan", "scan_soft_signals.py"),
                                ("humanizer-polish", "polish.py"),
                                ("humanizer-detect", "detect_conj.py"),
                                ("humanizer-markers", "check_markers.py")):
            argv = [sys.executable, os.path.join(ROOT, "scripts", script)]
            if command == "humanizer-markers":
                argv.append("--scan")
            argv += ["--json", missing]
            proc = subprocess.run(argv, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=120,
                                  encoding="utf-8", errors="replace")
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

    # --version: установленные команды называют версию пакета (cli.py);
    # в дереве репозитория проверяется через PYTHONPATH=src.
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
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    good = {"tool": "humanizer-polish", "schema": 1,
            "files": [{"file": "a.md", "changed": False}]}
    case("валидный конверт проходит", envelope_errors(good, "humanizer-polish", 1) == [])
    bad_keys = {"tool": "humanizer-polish", "files": [{"file": "a.md"}]}
    case("конверт без версии схемы валится",
         any("schema" in e for e in envelope_errors(bad_keys, "humanizer-polish", 1)))
    bad_ver = {"tool": "humanizer-polish", "schema": 2, "files": [{"file": "a.md"}]}
    case("дрейф версии схемы валится",
         any("версия схемы" in e for e in envelope_errors(bad_ver, "humanizer-polish", 1)))
    empty_files = {"tool": "humanizer-polish", "schema": 1, "files": []}
    case("пустой ответ валится (градуированный ответ не пуст)",
         any("пуст" in e for e in envelope_errors(empty_files, "humanizer-polish", 1)))

    try:
        doc = load_contract()
        case("контракт читается и структурно валиден", contract_errors(doc) == [])
        case("все четыре инструмента описаны",
             {t["command"] for t in doc.get("tools", [])} == set(EXPECTED_TOOLS))
        case("все четыре инструмента несут json_schema >= 1",
             all(isinstance(t.get("json_schema"), int)
                 and not isinstance(t.get("json_schema"), bool)
                 and t["json_schema"] >= 1
                 for t in doc.get("tools", [])))
    except (OSError, json.JSONDecodeError):
        case("контракт читается и структурно валиден", False)
        case("все четыре инструмента описаны", False)
        case("все четыре инструмента несут json_schema >= 1", False)

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
