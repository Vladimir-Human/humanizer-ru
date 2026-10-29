#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Build the plugin-only tree for Anthropic's plugin directory: the manifest and icon, the
#          skill, both READMEs and the LICENSE. It is committed to the git branch `directory`. The
#          portal's Validate and the later security scan read that branch, so eval/, scripts/,
#          tests/ and the maintainers' notes (they name the icon, read FAL_KEY and add up to more
#          than 1800 files) are not what a reviewer holds the listing for.
# SCOPE: building and checking the tree. Making the branch is the git recipe in AGENTS.md. A README
#        link to a path that is not in the tree becomes an absolute link to that path on main.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-BUILD-DIRECTORY; V-M-BUILD-DIRECTORY; R-DIRECTORY.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# listing: the files of the plugin tree (relative paths with /) for a repository root.
# map_links: apply a function to the target of every inline markdown link outside code fences.
# rewrite_links: a relative link that leaves the tree becomes an absolute link to main on GitHub.
# build: write the tree into an empty folder, return the file list.
# verify: list of problems for a built tree (files that should not be there or are missing, CRLF,
#         binaries, links that lead nowhere, the icon named in another file, the directory's limits).
# main: CLI; exit 0 when the tree is built and clean, 1 with problems printed.
# END_MODULE_MAP
from __future__ import annotations

import json
import posixpath
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".claude-plugin/plugin.json"
FILES = (MANIFEST, ".claude-plugin/icon.png", "README.md", "README.en.md", "LICENSE")
SKILL = "skills/humanizer-ru"
DOCS = ("README.md", "README.en.md")  # the files whose links are made to resolve inside the tree
LINK_REF = "main"
MAX_FILES = 512  # the portal screens the first 512 files by path
MAX_BYTES = 256 * 1024  # and reads a file that is not an image only up to this size
LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
OUTSIDE = re.compile(r"(?:[a-z][a-z0-9+.-]*:|#|/)", re.I)  # https:, mailto:, #anchor, /from-root


# START_BLOCK_LINKS
# The one regex covers inline links `[text](target "title")` and images. The READMEs use no
# reference-style or HTML links; a form this scanner does not see is neither rewritten nor checked,
# so teach it here before using one in a README.
def map_links(text: str, fn) -> str:
    out, fenced = [], False
    for line in text.split("\n"):
        if re.match(r"\s{0,3}(```|~~~)", line):
            fenced = not fenced
        elif not fenced:
            line = LINK.sub(lambda m: m.group(1) + fn(m.group(2)) + m.group(3), line)
        out.append(line)
    return "\n".join(out)


def _resolve(rel: str, target: str) -> str:
    """Path of a relative link target from the repository root, without the #fragment."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(rel), target.partition("#")[0]))


def rewrite_links(text: str, rel: str, root: Path, base: str, names) -> str:
    def fix(target: str) -> str:
        if OUTSIDE.match(target):
            return target
        full = _resolve(rel, target)
        if full in names or any(n.startswith(full + "/") for n in names):
            return target
        src = root / full
        if full == ".." or full.startswith("../") or not src.exists():
            raise SystemExit("%s: ссылка %s ведёт в никуда" % (rel, target))
        path, sep, frag = target.partition("#")
        return "%s/%s/%s/%s%s%s%s" % (base, "tree" if src.is_dir() else "blob", LINK_REF, full,
                                      "/" if path.endswith("/") else "", sep, frag)
    return map_links(text, fix)
# END_BLOCK_LINKS


# START_BLOCK_BUILD
def listing(root: Path) -> list:
    names: list = list(FILES)
    for p in sorted((root / SKILL).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            names.append(p.relative_to(root).as_posix())
    return sorted(names)


def build(out: Path, root: Path = ROOT) -> list:
    if out.exists() and any(out.iterdir()):
        raise SystemExit("%s не пуста: дерево собирается только в пустую папку" % out)
    names = listing(root)
    base = re.sub(r"(\.git)?/*$", "", json.loads((root / MANIFEST).read_text(encoding="utf-8"))["repository"])
    keep = set(names)
    for rel in names:
        if not (root / rel).is_file():
            raise SystemExit("нет файла %s" % rel)
        data = (root / rel).read_bytes()
        if rel in DOCS:
            data = rewrite_links(data.decode("utf-8"), rel, root, base, keep).encode("utf-8")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return names
# END_BLOCK_BUILD


# START_BLOCK_VERIFY
def verify(out: Path, root: Path = ROOT) -> list:
    problems = []
    found = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    want = listing(root)
    for rel in sorted(set(found) - set(want)):
        problems.append("%s: лишний файл, его нет в списке плагина" % rel)
    for rel in sorted(set(want) - set(found)):
        problems.append("%s: файла нет в собранной папке" % rel)
    if len(found) > MAX_FILES:
        problems.append("файлов %d, а каталог проверяет только первые %d" % (len(found), MAX_FILES))

    try:
        plugin = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plugin = {}
        problems.append("%s не читается" % MANIFEST)
    icon = posixpath.normpath(plugin["icon"]) if isinstance(plugin.get("icon"), str) and plugin["icon"] else ""
    for key in ("icon", "skills"):  # the manifest points at files the tree must have
        value = plugin.get(key)
        if isinstance(value, str) and value.startswith("./") and not (out / value).exists():
            problems.append("%s: %s ведёт на %s, а его в дереве нет" % (MANIFEST, key, value))
    if icon and (out / icon).is_file() and (root / icon).is_file() and (out / icon).read_bytes() != (root / icon).read_bytes():
        problems.append("%s: иконка отличается от иконки в репозитории" % icon)

    def look(rel: str):
        def check(target: str) -> str:
            full = _resolve(rel, target)
            if not OUTSIDE.match(target) and (full.startswith("..") or not (out / full).exists()):
                problems.append("%s: ссылка %s не ведёт ни на какой файл дерева" % (rel, target))
            return target
        return check

    for rel in found:
        if rel == icon:
            continue  # an image: its bytes are compared above, the limits below are for text
        raw = (out / rel).read_bytes()
        if b"\0" in raw:
            problems.append("%s: двоичный файл, каталог такие не читает как код" % rel)
        if len(raw) > MAX_BYTES:
            problems.append("%s: больше 256 КиБ, каталог читает файл только до этого размера" % rel)
        if b"\r" in raw:
            problems.append("%s: переводы строк CRLF" % rel)
        # the portal holds the listing for any file that names an image it cannot read as code
        if icon and rel != MANIFEST and posixpath.basename(icon).encode() in raw:
            problems.append("%s: называет файл иконки %s, каталог за это придерживает плагин" % (rel, icon))
        if rel.endswith(".md"):
            map_links(raw.decode("utf-8", "replace"), look(rel))
    return problems
# END_BLOCK_VERIFY


def main() -> int:
    if len(sys.argv) != 2:
        print("Использование: python scripts/build_directory.py <пустая папка для дерева>")
        return 2
    out = Path(sys.argv[1])
    names = build(out)
    problems = verify(out)
    print("%s: %d файлов, %d байт" % (out, len(names), sum((out / n).stat().st_size for n in names)))
    for n in names:
        print("  " + n)
    for p in problems:
        print("ОШИБКА:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
