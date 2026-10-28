#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Catch the mistakes that break installation or confuse the agent: bad SKILL.md
#          frontmatter, versions that disagree between manifests, missing referenced files,
#          CR line endings and invisible characters in the skill files; and what Anthropic's
#          plugin directory reads from plugin.json (a square PNG icon of 512-2048 px under 2 MB,
#          https links to the documentation and to support).
# SCOPE: repository checks only; text quality is measured by eval/, not here. The directory's own
#        validation (`claude plugin validate --profile directory --strict`) runs by hand.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-CHECK-REPO; V-M-CHECK-REPO.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# frontmatter: parse the YAML-ish header of SKILL.md (name, description, version).
# png_rows: the rows of each pass of the image data (one pass, or the seven of an interlaced image).
# png_size: bytes -> (width, height) of a whole PNG (chunk CRCs, IHDR first, IEND last, a header a
#          decoder accepts, image data of exactly the declared size), None for anything else, a PNG
#          cut short or damaged included.
# check: list of problems for a repository root.
# main: CLI; exit 0 when clean, 1 with problems printed.
# END_MODULE_MAP
from __future__ import annotations

import json
import re
import struct
import sys
import zlib
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


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_SAMPLES = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}  # colour type -> values per pixel
PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}  # colour type -> bits
PNG_UNPACK_LIMIT = 2048  # a larger image is judged by its size alone, its data are not unpacked
# The seven passes of an interlaced image (Adam7): x start, y start, x step, y step.
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def png_rows(width: int, height: int, bits: int, interlace: int):
    """(rows, bytes per row) of each pass of the image data: one pass, or the seven of Adam7.
    A row is a filter byte and the pixels of the pass; a pass with no pixels has no rows."""
    for x0, y0, dx, dy in (ADAM7 if interlace else ((0, 0, 1, 1),)):
        across, down = len(range(x0, width, dx)), len(range(y0, height, dy))
        if across and down:
            yield down, 1 + (across * bits + 7) // 8


def png_size(raw: bytes):
    """(width, height) of a whole PNG: every chunk has its CRC, IHDR comes first and IEND last
    with nothing after it, the header is one a decoder accepts, and the image data unpack to
    exactly the size the header declares, every row starting with a filter type from 0 to 4.
    None for anything else, a file cut short or damaged included."""
    if raw[:8] != PNG_SIGNATURE:
        return None
    pos, kinds, header, parts = 8, [], b"", []
    while pos + 12 <= len(raw) and (not kinds or kinds[-1] != b"IEND"):
        length, kind = struct.unpack(">I4s", raw[pos:pos + 8])
        body = raw[pos + 8:pos + 8 + length]
        crc = raw[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4 or struct.unpack(">I", crc)[0] != zlib.crc32(kind + body):
            return None
        kinds.append(kind)
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            parts.append(body)
        pos += 12 + length
    if pos != len(raw) or kinds[:1] != [b"IHDR"] or kinds[-1:] != [b"IEND"] or len(header) != 13 or not parts:
        return None
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", header)
    if not width or not height or depth not in PNG_DEPTHS.get(color, ()) or compression or filtering \
            or interlace not in (0, 1) or (color == 3 and b"PLTE" not in kinds):
        return None
    if width <= PNG_UNPACK_LIMIT and height <= PNG_UNPACK_LIMIT:
        passes = list(png_rows(width, height, PNG_SAMPLES[color] * depth, interlace))
        expected = sum(rows * size for rows, size in passes)
        unpacker = zlib.decompressobj()
        try:
            pixels = unpacker.decompress(b"".join(parts), expected + 1)
        except zlib.error:
            return None
        if not unpacker.eof or unpacker.unused_data or len(pixels) != expected:
            return None
        start = 0
        for rows, size in passes:
            if any(pixels[start + row * size] > 4 for row in range(rows)):
                return None
            start += rows * size
    return width, height


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

    # START_BLOCK_LISTING
    # Anthropic's plugin directory builds the listing from plugin.json: the icon must be a square
    # PNG or JPEG of 512 to 2048 px under 2 MB (we ship PNG), the links must be https.
    try:
        plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plugin = {}  # the version block has already said so
    if plugin:
        icon = plugin.get("icon")
        if not icon:
            problems.append(".claude-plugin/plugin.json: нет поля icon (иконка для каталога плагинов)")
        else:
            path = (root / icon).resolve()
            try:
                path.relative_to(root.resolve())
                inside = True
            except ValueError:
                inside = False
            if not inside or not path.is_file():
                problems.append("%s: файла иконки нет внутри плагина" % icon)
            elif path.stat().st_size >= 2 * 1024 * 1024:
                problems.append("%s: иконка больше 2 МБ" % icon)
            else:
                size = png_size(path.read_bytes())
                if size is None:
                    problems.append("%s: иконка должна быть PNG (целым файлом, не обрезанным)" % icon)
                elif size[0] != size[1] or not 512 <= size[0] <= 2048:
                    problems.append("%s: иконка должна быть квадратом от 512 до 2048 px, сейчас %dx%d" % (icon, size[0], size[1]))
        for key in ("documentationUrl", "supportUrl"):
            if not str(plugin.get(key, "")).startswith("https://"):
                problems.append(".claude-plugin/plugin.json: %s должен быть ссылкой https://" % key)
    # END_BLOCK_LISTING

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
