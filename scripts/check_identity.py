#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_identity.py — гейт машиночитаемой идентичности продукта.

`identity.v1.json` — устойчивые факты продукта (имя, идентичность,
область, лицензия, URL-якоря, точка входа MCP, инструменты, запрещённые
заявления). Гейт сверяет файл с носителями и запрещает дрейф:

  1. структура identity.v1.json (schema_version, id, product-поля);
  2. имя продукта одинаково в identity, pyproject.toml, contract.v1.json,
     SKILL.md (frontmatter), dsh/package.json, gemini-extension.json и
     плагин-манифестах;
  3. identity-строка дословно равна contract product.identity (два
     канона запрещены);
  4. список tools = командам contract.v1.json;
  5. MCP: entry «humanizer-mcp» есть в [project.scripts] pyproject и в
     llms.txt; protocol_versions = списку сервера
     (scripts/mcp/humanizer_mcp.py);
  6. URL-якоря: demo-хост присутствует в SKILL.md и README.md; репозиторий
     и лента releases.atom — в llms.txt;
  7. запрещённые заявления (claims_forbidden) не встречаются в витринных
     носителях дословно (отрицания в llms.txt сформулированы иначе и под
     проверку не попадают);
  8. identity.v1.json входит в данные пакета (pyproject package-data +
     копия src/humanizer_ru/identity.v1.json побайтово равна корневой).

Запуск:
    python3 scripts/check_identity.py             # проверка
    python3 scripts/check_identity.py --selftest

Коды: 0 — идентичность синхронна; 1 — дрейф; 2 — вход не читается.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDENTITY_REL = "identity.v1.json"
SHOWCASE_CARRIERS = ["README.md", "README.en.md", "README.pypi.md",
                     "llms.txt", "SKILL.md"]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _read_json(rel):
    return json.loads(_read(rel))


def _name_from_pyproject(text):
    m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def _skill_name(text):
    m = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
    return m.group(1) if m else None


def check() -> list:
    errors = []
    try:
        ident = _read_json(IDENTITY_REL)
    except (OSError, ValueError) as exc:
        return ["identity.v1.json не читается: %r" % exc]
    if ident.get("schema_version") != "identity.v1":
        errors.append("schema_version != identity.v1")
    if ident.get("id") != "humanizer-ru-identity":
        errors.append("id != humanizer-ru-identity")
    product = ident.get("product")
    if not isinstance(product, dict):
        return errors + ["нет блока product"]
    for field in ("name", "identity", "scope", "language", "license",
                  "repository", "demo", "llms", "pypi", "releases_feed",
                  "mcp", "tools"):
        if not product.get(field):
            errors.append("product.%s отсутствует или пуст" % field)
    if not isinstance(ident.get("claims_forbidden"), list) \
            or not ident["claims_forbidden"]:
        errors.append("claims_forbidden должен быть непустым списком")
    name = product.get("name")

    # 2. Имя во всех носителях. dsh/package.json несёт имя вендор-бандла
    #    (product-name + суффикс "-dsh") — это документированное исключение.
    carriers = {
        "pyproject.toml": _name_from_pyproject(_read("pyproject.toml")),
        "contract.v1.json": _read_json("contract.v1.json")
            .get("product", {}).get("name"),
        "SKILL.md": _skill_name(_read("SKILL.md")),
        "gemini-extension.json": _read_json("gemini-extension.json")
            .get("name"),
        ".claude-plugin/plugin.json": _read_json(".claude-plugin/plugin.json")
            .get("name"),
    }
    for rel, val in carriers.items():
        if val != name:
            errors.append("имя в %s: %r != identity %r" % (rel, val, name))
    dsh_name = _read_json("dsh/package.json").get("name")
    if dsh_name not in (name, name + "-dsh"):
        errors.append("имя в dsh/package.json: %r != %r и != %r"
                      % (dsh_name, name, name + "-dsh"))

    # 3. identity-строка = contract product.identity.
    c_ident = _read_json("contract.v1.json").get("product", {}).get("identity")
    if c_ident != product.get("identity"):
        errors.append("product.identity != contract product.identity "
                      "(два канона запрещены)")

    # 4. tools = командам контракта.
    c_tools = [t.get("command") for t in
               _read_json("contract.v1.json").get("tools", [])]
    if sorted(product.get("tools", [])) != sorted(c_tools):
        errors.append("tools != командам contract.v1.json: %r != %r"
                      % (product.get("tools"), c_tools))

    # 5. MCP.
    mcp = product.get("mcp") or {}
    pyproject = _read("pyproject.toml")
    if mcp.get("entry") not in pyproject:
        errors.append("pyproject [project.scripts]: нет точки входа %r"
                      % mcp.get("entry"))
    llms = _read("llms.txt")
    if mcp.get("entry") and mcp["entry"] not in llms:
        errors.append("llms.txt: нет команды подключения %r" % mcp.get("entry"))
    sys.path.insert(0, os.path.join(HERE, "mcp"))
    try:
        import humanizer_mcp
        if list(mcp.get("protocol_versions", [])) != \
                list(humanizer_mcp.PROTOCOL_VERSIONS):
            errors.append("protocol_versions != списку сервера MCP")
    except ImportError as exc:
        errors.append("сервер MCP не импортируется: %r" % exc)

    # 6. URL-якоря.
    demo_host = "vladimir-human.github.io/humanizer-ru"
    for rel in ("SKILL.md", "README.md"):
        if demo_host not in _read(rel):
            errors.append("%s: нет demo-хоста %s" % (rel, demo_host))
    if product.get("repository", "").replace("https://github.com/", "") \
            .rstrip("/") not in llms:
        errors.append("llms.txt: нет ссылки на репозиторий")
    if "releases.atom" not in llms:
        errors.append("llms.txt: нет ленты releases.atom (обновляемость)")

    # 7. Запрещённые заявления.
    for rel in SHOWCASE_CARRIERS:
        text = _read(rel).lower()
        for claim in ident.get("claims_forbidden", []):
            if claim.lower() in text:
                errors.append("%s: несёт запрещённое заявление «%s»"
                              % (rel, claim))

    # 8. Данные пакета.
    if "identity.v1.json" not in pyproject:
        errors.append("pyproject package-data: нет identity.v1.json")
    src_copy = os.path.join(ROOT, "src", "humanizer_ru", "identity.v1.json")
    if not os.path.isfile(src_copy):
        errors.append("в пакете нет копии identity.v1.json")
    else:
        with open(os.path.join(ROOT, IDENTITY_REL), "rb") as fh:
            root_bytes = fh.read()
        with open(src_copy, "rb") as fh:
            pkg_bytes = fh.read()
        if root_bytes.replace(b"\r\n", b"\n") != \
                pkg_bytes.replace(b"\r\n", b"\n"):
            errors.append("копия identity.v1.json в пакете рассинхронизирована")
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name_, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name_)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    errs = check()
    case("реальная идентичность синхронна", errs == [])
    if errs:
        for e in errs[:5]:
            print("   ->", e)
    # Негативы на копии дерева: подмена имени и запрещённое заявление.
    import shutil
    import tempfile
    td = tempfile.mkdtemp(prefix="identity-selftest-")
    global ROOT
    old_root = ROOT
    try:
        for rel in (IDENTITY_REL, "pyproject.toml", "contract.v1.json",
                    "SKILL.md", "dsh/package.json", "gemini-extension.json",
                    ".claude-plugin/plugin.json", "llms.txt", "README.md",
                    "README.en.md", "README.pypi.md"):
            src = os.path.join(old_root, rel)
            dst = os.path.join(td, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        os.makedirs(os.path.join(td, "scripts", "mcp"), exist_ok=True)
        shutil.copyfile(os.path.join(old_root, "scripts", "mcp",
                                     "humanizer_mcp.py"),
                        os.path.join(td, "scripts", "mcp", "humanizer_mcp.py"))
        os.makedirs(os.path.join(td, "src", "humanizer_ru"), exist_ok=True)
        shutil.copyfile(os.path.join(old_root, "src", "humanizer_ru",
                                     "identity.v1.json"),
                        os.path.join(td, "src", "humanizer_ru",
                                     "identity.v1.json"))
        ROOT = td
        # негатив 1: дрейф имени в identity
        p = os.path.join(td, IDENTITY_REL)
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["product"]["name"] = "humanizer-en"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        case("дрейф имени ловится (негатив)",
             any("имя" in e for e in check()))
        doc["product"]["name"] = "humanizer-ru"
        # негатив 2: запрещённое заявление в README
        doc["claims_forbidden"].append("пример запрещённой фразы xyzz")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        with open(os.path.join(td, "README.md"), "a", encoding="utf-8") as fh:
            fh.write("\nПример запрещённой фразы xyzz в витрине.\n")
        case("запрещённое заявление ловится (негатив)",
             any("запрещённое" in e for e in check()))
        # негатив 3: рассинхрон копии пакета
        with open(os.path.join(td, "src", "humanizer_ru", "identity.v1.json"),
                  "a", encoding="utf-8") as fh:
            fh.write("\n")
        case("рассинхрон пакетной копии ловится (негатив)",
             any("рассинхронизирована" in e for e in check()))
    finally:
        ROOT = old_root
        shutil.rmtree(td, ignore_errors=True)
    print("САМОПРОВЕРКА check_identity: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Сверка identity.v1.json с носителями (дрейф запрещён).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errors = check()
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("ИДЕНТИЧНОСТЬ: расхождений %d" % len(errors))
        return 1
    print("ИДЕНТИЧНОСТЬ: identity.v1.json синхронен с носителями")
    return 0


if __name__ == "__main__":
    sys.exit(main())
