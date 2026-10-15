#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Build dist/humanizer-ru-skill.zip for Claude.ai upload and manual installs:
#          one top-level folder humanizer-ru/ with SKILL.md, references/ and scripts/.
# SCOPE: packaging only; Latin file names, LF endings, no caches.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-BUILD-ZIP; V-M-BUILD-ZIP.
# END_MODULE_CONTRACT
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "skills" / "humanizer-ru"


def build(out: Path) -> list:
    out.parent.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(SRC.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            arc = "humanizer-ru/" + p.relative_to(SRC).as_posix()
            if not arc.isascii():
                raise SystemExit("не-ASCII имя файла в архиве: %s" % arc)
            info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if p.suffix == ".py" else 0o644) << 16
            zf.writestr(info, p.read_bytes())
            names.append(arc)
    return names


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "humanizer-ru-skill.zip"
    names = build(out)
    print("%s: %d файлов" % (out, len(names)))
    for n in names:
        print("  " + n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
