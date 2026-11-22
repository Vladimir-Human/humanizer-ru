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
#        The tree's plugin.json gets the directory's own name (DIRECTORY_NAME): the portal holds
#        the name humanizer-ru as a look-alike of other plugins named humanizer, and passes
#        humanizer-russian (portal Validate, 2026-10-29). main and the GitHub marketplace keep
#        humanizer-ru.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-BUILD-DIRECTORY; V-M-BUILD-DIRECTORY; R-DIRECTORY.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# listing: the files of the plugin tree (relative paths with /) for a repository root.
# map_links: apply a function to the target of every inline markdown link outside code fences and inline code spans.
# rewrite_links: a relative link that leaves the tree becomes an absolute link to main on GitHub.
# rename_plugin: plugin.json text with name and displayName set to DIRECTORY_NAME, every other byte kept.
# build: write the tree into an empty folder (refusing symlinks/out-of-tree paths), return the file list.
# verify: list of problems for a built tree (files that should not be there or are missing, CRLF,
#         binaries, secret/network API strings, inline/HTML/reference links that lead nowhere,
#         a plugin.json that differs from the repository's by more than the name, the icon named
#         in another file, the directory's limits).
# main: CLI `build_directory.py <out>`; --help exits 0, clean exits 0, problems exit 1.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".claude-plugin/plugin.json"
FILES = (MANIFEST, ".claude-plugin/icon.png", "README.md", "README.en.md", "LICENSE")
SKILL = "skills/humanizer-ru"
DOCS = ("README.md", "README.en.md")  # the files whose links are made to resolve inside the tree
DIRECTORY_NAME = "humanizer-russian"  # plugin name and displayName in the tree, see SCOPE
LINK_REF = "main"
MAX_FILES = 512  # the portal screens the first 512 files by path
MAX_BYTES = 256 * 1024  # and reads a file that is not an image only up to this size
SKIP_SUFFIXES = frozenset({".pyc", ".bak", ".swp"})
SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db"})
LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
HTML_LINK = re.compile(r'<(?:a|img)\b[^>]*?\b(?:href|src)=["\']([^"\']+)["\']', re.I)
REF_LINK = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?")
OUTSIDE = re.compile(r"(?:[a-z][a-z0-9+.-]*:|#|/)", re.I)  # https:, mailto:, #anchor, /from-root
FORBIDDEN_STRINGS = re.compile(r"\b(?:FAL_KEY|API_KEY|os\.environ|urllib\.request|subprocess|socket)\b")


# START_BLOCK_LINKS
# Inline links `[text](target "title")` and images are rewritten by map_links; verify() additionally
# scans HTML `<a>`/`<img>` and reference-style `[label]: target` links so no broken link slips past.
# Both helpers skip fenced code blocks and CommonMark inline backtick code spans in O(N) linear time.
def _split_inline_code(line: str) -> list:
    """Split a non-fenced Markdown line into (is_code, text) segments in O(N) time."""
    if "`" not in line:
        return [(False, line)]
    runs = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            j = i + 1
            while j < n and line[j] == "`":
                j += 1
            runs.append((i, j, j - i))
            i = j
        else:
            i += 1
    by_len: dict = {}
    for idx, (_s, _e, rlen) in enumerate(runs):
        by_len.setdefault(rlen, []).append(idx)
    heads = {rlen: 0 for rlen in by_len}

    parts = []
    pos = 0
    r_idx = 0
    r_cnt = len(runs)
    while r_idx < r_cnt:
        s, _e, rlen = runs[r_idx]
        idx_list = by_len[rlen]
        h = heads[rlen]
        while h < len(idx_list) and idx_list[h] <= r_idx:
            h += 1
        heads[rlen] = h
        if h < len(idx_list):
            close_idx = idx_list[h]
            _cs, ce, _clen = runs[close_idx]
            if s > pos:
                parts.append((False, line[pos:s]))
            parts.append((True, line[s:ce]))
            pos = ce
            r_idx = close_idx + 1
        else:
            r_idx += 1
    if pos < n:
        parts.append((False, line[pos:]))
    return parts


def map_links(text: str, fn) -> str:
    out, fenced = [], False
    for line in text.split("\n"):
        if re.match(r"\s{0,3}(```|~~~)", line):
            fenced = not fenced
        elif not fenced:
            segs = _split_inline_code(line)
            line = "".join(
                seg if is_code else LINK.sub(lambda m: m.group(1) + fn(m.group(2)) + m.group(3), seg)
                for is_code, seg in segs
            )
        out.append(line)
    return "\n".join(out)


def _scan_extra_md_links(text: str, fn) -> None:
    """Scan HTML <a href>/<img> and reference-style [label]: target links outside code fences and inline code."""
    fenced = False
    for line in text.split("\n"):
        if re.match(r"\s{0,3}(```|~~~)", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        prose = "".join(" " if is_code else seg for is_code, seg in _split_inline_code(line))
        for m in HTML_LINK.finditer(prose):
            fn(m.group(1))
        rm = REF_LINK.match(prose)
        if rm:
            fn(rm.group(1))


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
def _check_safe_src(path: Path, root: Path) -> None:
    if path.is_symlink():
        raise SystemExit("символическая ссылка запрещена в дереве каталога: %s" % path)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise SystemExit("файл выходит за пределы репозитория: %s" % path)


def rename_plugin(text: str) -> str:
    """plugin.json for the directory: name and displayName replaced, every other byte kept."""
    for key in ("name", "displayName"):
        # two spaces and the key at the start of the line: the author's "name" sits inside a line
        text, n = re.subn(r'^(  "%s": ")[^"]*(")' % key, r"\g<1>%s\g<2>" % DIRECTORY_NAME, text, flags=re.M)
        if n != 1:
            raise SystemExit("%s: поле %s должно быть одно, а найдено %d" % (MANIFEST, key, n))
    return text


def listing(root: Path) -> list:
    names: list = list(FILES)
    for p in sorted((root / SKILL).rglob("*")):
        if p.is_symlink():
            raise SystemExit("символическая ссылка запрещена в дереве каталога: %s" % p)
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix in SKIP_SUFFIXES or p.name in SKIP_NAMES:
            continue
        _check_safe_src(p, root)
        names.append(p.relative_to(root).as_posix())
    return sorted(names)


def build(out: Path, root: Path = ROOT) -> list:
    if out.exists() and any(out.iterdir()):
        raise SystemExit("%s не пуста: дерево собирается только в пустую папку" % out)
    names = listing(root)
    base = re.sub(r"(\.git)?/*$", "", json.loads((root / MANIFEST).read_text(encoding="utf-8"))["repository"])
    keep = set(names)
    for rel in names:
        src = root / rel
        if src.is_symlink():
            raise SystemExit("символическая ссылка запрещена в дереве каталога: %s" % rel)
        if not src.is_file():
            raise SystemExit("нет файла %s" % rel)
        _check_safe_src(src, root)
        data = src.read_bytes()
        if rel in DOCS:
            data = rewrite_links(data.decode("utf-8"), rel, root, base, keep).encode("utf-8")
        elif rel == MANIFEST:
            data = rename_plugin(data.decode("utf-8")).encode("utf-8")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return names
# END_BLOCK_BUILD


# START_BLOCK_VERIFY
def verify(out: Path, root: Path = ROOT) -> list:
    problems = []
    found = []
    for p in sorted(out.rglob("*")):
        if p.is_symlink():
            problems.append("%s: символическая ссылка запрещена" % p.relative_to(out).as_posix())
            continue
        if p.is_file():
            found.append(p.relative_to(out).as_posix())
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
    try:
        source = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        source = {}
    if plugin != dict(source, name=DIRECTORY_NAME, displayName=DIRECTORY_NAME):
        problems.append("%s: не совпадает с plugin.json репозитория, допустимо отличие только в name и displayName (%s)"
                        % (MANIFEST, DIRECTORY_NAME))
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
        text = raw.decode("utf-8", "replace")
        bad_tok = FORBIDDEN_STRINGS.search(text)
        if bad_tok:
            problems.append("%s: содержит запрещённую строку %s (секрет или сетевой/процессный API)" % (rel, bad_tok.group(0)))
        if rel.endswith(".md"):
            checker = look(rel)
            map_links(text, checker)
            _scan_extra_md_links(text, checker)
    return problems
# END_BLOCK_VERIFY


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Собрать дерево плагина для каталога Anthropic (ветка directory) в пустую папку.")
    ap.add_argument("out", help="Путь к пустой папке для собранного дерева")
    args = ap.parse_args(argv)
    out = Path(args.out)
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
