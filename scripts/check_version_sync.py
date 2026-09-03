#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_version_sync.py — каноничная __version__ пакета совпадает с
версией скилла (SKILL.md frontmatter).

src/humanizer_ru/__init__.py отставал на два выпуска до ручной правки
в 3.16.2: ни один гейт канон с версией скилла не сверял.

CLI:
    python3 scripts/check_version_sync.py            # проверка репозитория
    python3 scripts/check_version_sync.py --selftest # PASS/FAIL

Коды: 0 — версии синхронны; 1 — рассинхрон или провал самопроверки;
2 — файлы не найдены. Только стандартная библиотека.
"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INIT = os.path.join(ROOT, "src", "humanizer_ru", "__init__.py")
SKILL = os.path.join(ROOT, "SKILL.md")
CONTRACT = os.path.join(ROOT, "contract.v1.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

_INIT_RX = re.compile(r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']')
_SKILL_RX = re.compile(r'^\s*version:\s*["\'](\d+\.\d+\.\d+)["\']',
                        re.MULTILINE)


def _versions():
    with open(INIT, encoding="utf-8") as fh:
        m = _INIT_RX.search(fh.read())
        init = m.group(1) if m else None
    with open(SKILL, encoding="utf-8") as fh:
        m = _SKILL_RX.search(fh.read())
        skill = m.group(1) if m else None
    return init, skill


def _contract_version():
    """product.version из contract.v1.json (None — нет поля/файла/не JSON)."""
    import json
    try:
        with open(CONTRACT, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    ver = doc.get("product", {}).get("version")
    if isinstance(ver, str) and re.match(r"^\d+\.\d+\.\d+$", ver):
        return ver
    return None


def run():
    if not os.path.isfile(INIT) or not os.path.isfile(SKILL):
        print("нет %s или %s" % (INIT, SKILL), file=sys.stderr)
        return 2
    init, skill = _versions()
    if init is None:
        print("[FAIL] __init__.py: __version__ не найден")
        return 1
    if skill is None:
        print("[FAIL] SKILL.md: frontmatter version не найден")
        return 1
    if init != skill:
        print("[FAIL] рассинхрон: __version__=%s, SKILL.md version=%s"
              % (init, skill))
        return 1
    contract = _contract_version()
    if contract is None:
        print("[FAIL] contract.v1.json: product.version отсутствует или "
              "вне формы X.Y.Z")
        return 1
    if contract != skill:
        print("[FAIL] рассинхрон: contract product.version=%s, SKILL.md=%s"
              % (contract, skill))
        return 1
    print("OK version-sync: __version__ == SKILL.md == contract (%s)" % init)
    return 0


def _selftest():
    import json
    import tempfile
    fails = 0
    cases = 0
    # позитив: совпадают
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "src", "humanizer_ru"))
    os.makedirs(os.path.join(d, "scripts"))
    open(os.path.join(d, "src", "humanizer_ru", "__init__.py"),
         "w", encoding="utf-8").write('__version__ = "9.9.9"\n')
    open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8").write(
        '---\nname: x\nmetadata:\n  version: "9.9.9"\n'
        '  last_reviewed: "x"\n---\n')
    with open(os.path.join(d, "contract.v1.json"), "w", encoding="utf-8") as fh:
        json.dump({"product": {"version": "9.9.9"}}, fh)
    # подменяем пути через monkeypatch
    global INIT, SKILL, CONTRACT
    old_init, old_skill, old_contract = INIT, SKILL, CONTRACT
    INIT = os.path.join(d, "src", "humanizer_ru", "__init__.py")
    SKILL = os.path.join(d, "SKILL.md")
    CONTRACT = os.path.join(d, "contract.v1.json")
    i, s = _versions()
    cases += 1
    if i != "9.9.9" or s != "9.9.9" or _contract_version() != "9.9.9":
        print("ПРОВАЛ selftest positive: i=%s s=%s c=%s"
              % (i, s, _contract_version()))
        fails += 1
    # негатив: рассинхрон
    open(os.path.join(d, "src", "humanizer_ru", "__init__.py"),
         "w", encoding="utf-8").write('__version__ = "9.9.8"\n')
    i2, s2 = _versions()
    cases += 1
    if i2 == s2:
        print("ПРОВАЛ selftest negative: рассинхрон не пойман")
        fails += 1
    # негатив: дрейф product.version контракта
    open(os.path.join(d, "src", "humanizer_ru", "__init__.py"),
         "w", encoding="utf-8").write('__version__ = "9.9.9"\n')
    with open(CONTRACT, "w", encoding="utf-8") as fh:
        json.dump({"product": {"version": "9.9.8"}}, fh)
    cases += 1
    if _contract_version() == "9.9.9":
        print("ПРОВАЛ selftest contract: дрейф product.version не пойман")
        fails += 1
    # негатив: contract без product.version
    with open(CONTRACT, "w", encoding="utf-8") as fh:
        json.dump({"product": {}}, fh)
    cases += 1
    if _contract_version() is not None:
        print("ПРОВАЛ selftest contract: отсутствие version не поймано")
        fails += 1
    INIT, SKILL, CONTRACT = old_init, old_skill, old_contract
    import shutil
    shutil.rmtree(d)
    if fails:
        print("САМОПРОВЕРКА: провалов %d" % fails)
        return 1
    print("САМОПРОВЕРКА: %d/%d PASS" % (cases, cases))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(run())
