#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_tool_schemas.py — печать tool-схем MCP из канонического контракта.

Тонкая обёртка: генерация живёт в `humanizer_mcp.py` (единый источник для
сервера и гейтов — дублирование логики здесь привело бы к дрейфу схем).
Схемы генерируются из `contract.v1.json`: имена, описания, границы
«когда не использовать», словари --genre, режимы polish и output_schema
берутся из контракта, а не пишутся вручную (критерий v2 3.1: «schemas
генерируются из канонического контракта; гейт сверяет»).

Запуск:
    python3 scripts/mcp/generate_tool_schemas.py           # JSON в stdout
    python3 scripts/mcp/generate_tool_schemas.py --selftest

Коды: 0 — успех; 1 — контракт непригоден; 2 — ошибка входа.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import humanizer_mcp  # noqa: E402


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    contract = humanizer_mcp.load_contract()
    defs = humanizer_mcp.generate_tool_defs(contract)
    case("четыре инструмента из контракта", len(defs) == 4)
    by = {d["name"]: d for d in defs}
    case("имена — команды с подчёркиванием",
         set(by) == {"humanizer_scan", "humanizer_markers",
                     "humanizer_polish", "humanizer_detect"})
    case("outputSchema = output_schema контракта без изменений",
         all(by[t["command"].replace("-", "_")]["outputSchema"]
             == t["output_schema"] for t in contract["tools"]))
    case("описания собраны из task+when_not контракта",
         all(t["task"] in by[t["command"].replace("-", "_")]["description"]
             and t["when_not"]
             in by[t["command"].replace("-", "_")]["description"]
             for t in contract["tools"]))
    case("genre enum из effective_by_tool",
         by["humanizer_scan"]["inputSchema"]["properties"]["genre"]["enum"]
         == contract["genres"]["effective_by_tool"]["humanizer-scan"])
    case("mode enum polish выведен из modes контракта",
         by["humanizer_polish"]["inputSchema"]["properties"]["mode"]["enum"]
         == ["strip", "preserve-markup", "typographic"])
    case("marker_class выведен из --class a|all",
         by["humanizer_markers"]["inputSchema"]["properties"]
         ["marker_class"]["enum"] == ["a", "all"])
    bad = json.loads(json.dumps(contract))
    del bad["tools"][0]["when_not"]
    try:
        humanizer_mcp.generate_tool_defs(bad)
        case("контракт без when_not валится (негатив)", False)
    except ValueError:
        case("контракт без when_not валится (негатив)", True)
    bad2 = json.loads(json.dumps(contract))
    bad2["tools"].append(dict(bad2["tools"][0]))
    try:
        humanizer_mcp.generate_tool_defs(bad2)
        case("дубль инструмента валится (негатив)", False)
    except ValueError:
        case("дубль инструмента валится (негатив)", True)
    print("САМОПРОВЕРКА generate_tool_schemas: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Печать tool-схем MCP, сгенерированных из contract.v1.json.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--contract", help="путь к контракту (отладка)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        contract = humanizer_mcp.load_contract(args.contract)
        defs = humanizer_mcp.generate_tool_defs(contract)
    except (OSError, ValueError, KeyError) as exc:
        print("ГЕНЕРАЦИЯ: отказ: %r" % exc, file=sys.stderr)
        return 2 if isinstance(exc, OSError) else 1
    print(json.dumps(defs, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
