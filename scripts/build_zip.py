#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Build dist/humanizer-ru-skill.zip for Claude.ai upload and manual installs:
#          one top-level folder humanizer-ru/ with SKILL.md, references/ and scripts/.
# SCOPE: packaging only; Latin file names, LF endings, no caches/junk, no symlinks or out-of-tree
#        files, deterministic timestamps, atomic write.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-BUILD-ZIP; V-M-BUILD-ZIP.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# build: collect files under SRC (refusing symlinks, out-of-tree paths, CRLF and non-ASCII names)
#        and write a deterministic zip atomically.
# main: CLI `build_zip.py [OUT]`; --help exits 0.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "skills" / "humanizer-ru"
SKIP_SUFFIXES = frozenset({".pyc", ".bak", ".swp"})
SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db"})


def _check_safe_path(p: Path, root: Path) -> None:
    if p.is_symlink():
        raise SystemExit("символическая ссылка запрещена в архиве: %s" % p)
    try:
        p.resolve().relative_to(root.resolve())
    except ValueError:
        raise SystemExit("файл выходит за пределы папки навыка: %s" % p)


def build(out: Path, src: Path = SRC) -> list:
    out.parent.mkdir(parents=True, exist_ok=True)
    src_root = src.resolve()
    entries = []
    for p in sorted(src.rglob("*")):
        if p.is_symlink():
            raise SystemExit("символическая ссылка запрещена в архиве: %s" % p)
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix in SKIP_SUFFIXES or p.name in SKIP_NAMES:
            continue
        _check_safe_path(p, src_root)
        arc = "humanizer-ru/" + p.relative_to(src).as_posix()
        if not arc.isascii():
            raise SystemExit("не-ASCII имя файла в архиве: %s" % arc)
        raw = p.read_bytes()
        if b"\r" in raw:
            raise SystemExit("переводы строк CRLF в архиве запрещены: %s" % arc)
        entries.append((arc, p.suffix, raw))

    names = []
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=out.parent, prefix=".tmp-", suffix=".zip", delete=False) as fh:
            tmp_path = Path(fh.name)
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arc, suffix, raw in entries:
                info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if suffix == ".py" else 0o644) << 16
                zf.writestr(info, raw)
                names.append(arc)
        os.replace(tmp_path, out)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
    return names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Собрать ZIP-архив навыка humanizer-ru для Claude.ai.")
    ap.add_argument("out", nargs="?", default=str(ROOT / "dist" / "humanizer-ru-skill.zip"),
                    help="Путь к выходному архиву (по умолчанию dist/humanizer-ru-skill.zip)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    names = build(out)
    print("%s: %d файлов" % (out, len(names)))
    for n in names:
        print("  " + n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
