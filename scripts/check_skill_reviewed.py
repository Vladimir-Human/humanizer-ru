#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_skill_reviewed.py — last_reviewed скилла не старее даты
последнего изменения содержательного файла скилла.

В 3.16.1 CHANGELOG заявлял актуализацию last_reviewed, поле оставалось
старым (2026-08-13) — ни один гейт не поймал. Здесь: frontmatter
last_reviewed сравнивается с mtime последнего коммита SKILL.md и
references/*.md (если last_reviewed раньше — несходство: скилл заявил
«пересмотрен», а файлы правлены позже).

CLI:
    python3 scripts/check_skill_reviewed.py            # проверка репозитория
    python3 scripts/check_skill_reviewed.py --selftest # PASS/FAIL

Коды: 0 — дата корректна; 1 — рассинхрон или провал самопроверки;
2 — файлы не найдены. Только стандартная библиотека.
"""
import datetime
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "SKILL.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

_REVIEWED_RX = re.compile(r'^\s*last_reviewed:\s*["\'](\d{4}-\d{2}-\d{2})["\']',
                           re.MULTILINE)


def _git_date(path):
    """Дата последнего коммита, касающегося файла (ISO YYYY-MM-DD)."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", path],
            cwd=ROOT, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return proc.stdout.strip()[:10]
    except Exception:
        return None


def run():
    if not os.path.isfile(SKILL):
        print("нет SKILL.md", file=sys.stderr)
        return 2
    with open(SKILL, encoding="utf-8") as fh:
        text = fh.read()
    m = _REVIEWED_RX.search(text)
    if not m:
        print("[FAIL] SKILL.md: last_reviewed не найден в frontmatter")
        return 1
    reviewed = m.group(1)
    # Дата последнего изменения по SKILL.md и всем references/*.md
    # (докстринг обещает обе зоны; основной объём скилла — справочники,
    # и last_reviewed, моложе их правки, обязан ронять гейт).
    import glob as _g
    watched = [SKILL] + sorted(_g.glob(
        os.path.join(ROOT, "references", "*.md")))
    latest = None
    latest_path = None
    for path in watched:
        d = _git_date(path)
        if d is None:
            d = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
        if latest is None or d > latest:
            latest = d
            latest_path = path
    if reviewed < latest:
        print("[FAIL] last_reviewed=%s старее даты коммита %s=%s"
              % (reviewed, os.path.relpath(latest_path, ROOT), latest))
        return 1
    print("OK skill-reviewed: last_reviewed=%s >= коммит=%s"
          % (reviewed, latest))
    return 0


def _selftest():
    import tempfile
    import shutil
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "scripts"))
    # вне git — fallback на mtime
    global SKILL, ROOT
    old_skill, old_root = SKILL, ROOT
    ROOT = d
    SKILL = os.path.join(d, "SKILL.md")
    # позитив: reviewed сегодня
    today = datetime.date.today().isoformat()
    open(SKILL, "w", encoding="utf-8").write(
        '---\nname: x\nmetadata:\n  version: "9.9.9"\n'
        '  last_reviewed: "%s"\n---\n' % today)
    fails = 0
    if run() != 0:
        print("ПРОВАЛ selftest positive")
        fails += 1
    # негатив: reviewed в прошлом году
    open(SKILL, "w", encoding="utf-8").write(
        '---\nname: x\nmetadata:\n  version: "9.9.9"\n'
        '  last_reviewed: "2024-01-01"\n---\n')
    if run() == 0:
        print("ПРОВАЛ selftest negative: старая дата не поймана")
        fails += 1
    SKILL, ROOT = old_skill, old_root
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
