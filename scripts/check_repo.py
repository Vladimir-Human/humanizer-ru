#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Catch the mistakes that break installation or confuse the agent: bad SKILL.md
#          frontmatter, versions that disagree between manifests, missing referenced files,
#          CR line endings and invisible characters in the skill files.
# SCOPE: repository checks only; text quality is measured by eval/, not here.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-CHECK-REPO; V-M-CHECK-REPO.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# frontmatter: parse the YAML-ish header of SKILL.md (name, description, version).
# check: list of problems for a repository root.
# main: CLI; exit 0 when clean, 1 with problems printed.
# END_MODULE_MAP
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path("skills") / "humanizer-ru"
INVISIBLE = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD}


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    data = {}
    for key in ("name", "description", "license"):
        km = re.search(r'^%s:\s*"?(.*?)"?\s*$' % key, m.group(1), re.M)
        if km:
            data[key] = km.group(1)
    vm = re.search(r'^\s+version:\s*"?([\d.]+)"?\s*$', m.group(1), re.M)
    if vm:
        data["version"] = vm.group(1)
    return data


# START_CONTRACT: check
# PURPOSE: Validate one repository root.
# INPUTS: root (Path).
# OUTPUTS: list of human-readable problems (empty when clean).
# SIDE_EFFECTS: none.
# END_CONTRACT: check
def check(root: Path) -> list:
    problems = []
    skill_md = root / SKILL_DIR / "SKILL.md"
    if not skill_md.exists():
        return ["нет %s" % (SKILL_DIR / "SKILL.md")]
    text = skill_md.read_text(encoding="utf-8")
    fm = frontmatter(text)
    if fm.get("name") != "humanizer-ru":
        problems.append("SKILL.md: name должен быть humanizer-ru, сейчас %r" % fm.get("name"))
    desc = fm.get("description", "")
    if not desc or len(desc) > 1024:
        problems.append("SKILL.md: description пустой или длиннее 1024 символов (%d)" % len(desc))
    version = fm.get("version")
    if not version:
        problems.append("SKILL.md: нет metadata.version")

    # START_BLOCK_VERSIONS
    manifests = {
        ".claude-plugin/plugin.json": lambda d: d.get("version"),
        ".claude-plugin/marketplace.json": lambda d: d["plugins"][0].get("version"),
        ".codex-plugin/plugin.json": lambda d: d.get("version"),
    }
    for rel, get in manifests.items():
        p = root / rel
        if not p.exists():
            problems.append("нет %s" % rel)
            continue
        try:
            v = get(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, KeyError, IndexError) as exc:
            problems.append("%s не читается: %s" % (rel, exc))
            continue
        if v != version:
            problems.append("%s: версия %s, а в SKILL.md %s" % (rel, v, version))
    changelog = root / "CHANGELOG.md"
    if changelog.exists():
        m = re.search(r"^## \[?(\d+\.\d+\.\d+)", changelog.read_text(encoding="utf-8"), re.M)
        if not m or m.group(1) != version:
            problems.append("CHANGELOG.md: верхняя запись %s, а в SKILL.md %s" % (m.group(1) if m else None, version))
    else:
        problems.append("нет CHANGELOG.md")
    # END_BLOCK_VERSIONS

    # START_BLOCK_FILES
    for ref in sorted(set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", text))):
        target = ref.split()[0]
        if not (root / SKILL_DIR / target).exists():
            problems.append("SKILL.md ссылается на %s, файла нет" % target)
    for p in sorted((root / SKILL_DIR).rglob("*")):
        if not p.is_file() or p.suffix not in (".md", ".py"):
            continue
        raw = p.read_bytes()
        rel = p.relative_to(root).as_posix()
        if b"\r" in raw:
            problems.append("%s: переводы строк CRLF" % rel)
        body = raw.decode("utf-8", "replace")
        bad = sorted({hex(ord(c)) for c in body if ord(c) in INVISIBLE})
        if bad:
            problems.append("%s: невидимые символы %s" % (rel, ", ".join(bad)))
    # END_BLOCK_FILES
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    problems = check(root)
    for p in problems:
        print("ОШИБКА:", p)
    print("Проверка репозитория: %s" % ("ошибок нет" if not problems else "%d ошибок" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
