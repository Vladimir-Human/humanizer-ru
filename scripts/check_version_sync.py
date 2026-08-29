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
    print("OK version-sync: __version__ == SKILL.md (%s)" % init)
    return 0


def _selftest():
    import tempfile
    fails = 0
    # позитив: совпадают
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "src", "humanizer_ru"))
    os.makedirs(os.path.join(d, "scripts"))
    open(os.path.join(d, "src", "humanizer_ru", "__init__.py"),
         "w", encoding="utf-8").write('__version__ = "9.9.9"\n')
    open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8").write(
        '---\nname: x\nmetadata:\n  version: "9.9.9"\n'
        '  last_reviewed: "x"\n---\n')
    # подменяем пути через monkeypatch
    global INIT, SKILL
    old_init, old_skill = INIT, SKILL
    INIT = os.path.join(d, "src", "humanizer_ru", "__init__.py")
    SKILL = os.path.join(d, "SKILL.md")
    i, s = _versions()
    if i != "9.9.9" or s != "9.9.9":
        print("ПРОВАЛ selftest positive: i=%s s=%s" % (i, s))
        fails += 1
    # негатив: рассинхрон
    open(os.path.join(d, "src", "humanizer_ru", "__init__.py"),
         "w", encoding="utf-8").write('__version__ = "9.9.8"\n')
    i2, s2 = _versions()
    if i2 == s2:
        print("ПРОВАЛ selftest negative: рассинхрон не пойман")
        fails += 1
    INIT, SKILL = old_init, old_skill
    import shutil
    shutil.rmtree(d)
    if fails:
        print("САМОПРОВЕРКА: провалов %d" % fails)
        return 1
    print("САМОПРОВЕРКА: 2/2 PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(run())
