#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Catch the mistakes that break installation or confuse the agent: bad SKILL.md
#          frontmatter, versions/names/licenses that disagree between manifests, missing referenced
#          files, junk files, 256 KiB directory cap, non-stdlib imports in skill scripts (R-TEXT-ONLY),
#          CR line endings/BOM/invisible characters, plugin icon and listing links for Anthropic's
#          directory, site/ CSP/offline-link/version/sitemap integrity, and .grace/ XML/ID integrity.
# SCOPE: repository checks only; text quality is measured by eval/, not here. The directory's own
#        validation (`claude plugin validate --profile directory --strict`) runs by hand.
# DEPENDS: Python 3.8+ stdlib.
# LINKS: M-CHECK-REPO; V-M-CHECK-REPO; R-DIRECTORY; R-TEXT-ONLY.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# frontmatter: parse the YAML-ish header of SKILL.md (name, description, license, version).
# png_rows: the rows of each pass of the image data (one pass, or the seven of an interlaced image).
# png_size: bytes -> (width, height) of a whole PNG (chunk CRCs, IHDR first, IEND last, a header a
#          decoder accepts, image data of exactly the declared size), None for anything else.
# check_stdlib_imports: AST check that a skill script uses pure offline stdlib only (R-TEXT-ONLY).
# check_site: CSP, zero external assets, local links, version sync, sitemap and hygiene for site/.
# check_grace: XML parsing, unique IDs, cross-references and Python code LINKS: integrity.
# check: list of problems for a repository root.
# main: CLI; exit 0 when clean, 1 with problems printed.
# END_MODULE_MAP
from __future__ import annotations

import ast
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path("skills") / "humanizer-ru"
MAX_BYTES = 256 * 1024  # Anthropic plugin directory reads non-image files up to 256 KiB
JUNK_SUFFIXES = frozenset({".bak", ".swp"})
JUNK_NAMES = frozenset({".DS_Store", "Thumbs.db"})

# Always-disallowed invisible, bidi override, space-spoofer, and PUA codepoints (excludes emoji
# ZWJ 0x200D, VS16 0xFE0F, NBSP 0x00A0, and non-breaking hyphen 0x2011 used in README/site).
BIDI_AND_SPOOF = frozenset(
    {0x200B, 0x200C, 0x2060, 0xFEFF, 0x00AD, 0x034F, 0x061C, 0x180E, 0x200E, 0x200F,
     0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160}
    | set(range(0x202A, 0x202F))
    | set(range(0x2066, 0x206A))
    | set(range(0xE200, 0xEA03))
)
# Skill files and prompt/chat.md also ban ZWJ (0x200D).
INVISIBLE = BIDI_AND_SPOOF | {0x200D}

# Offline pure-stdlib allowlist for skills/humanizer-ru/scripts/*.py (R-TEXT-ONLY, R-NO-LOCAL-NN).
# Network (urllib.request, http, socket, ssl), subprocess, dynamic loaders and third-party packages are blocked.
STDLIB_ALLOWED = frozenset({
    "__future__", "argparse", "bisect", "codecs", "collections", "copy", "dataclasses",
    "datetime", "decimal", "difflib", "enum", "errno", "fractions", "functools",
    "io", "itertools", "json", "math", "operator", "os", "pathlib", "re",
    "shutil", "statistics", "string", "sys", "tempfile", "textwrap", "time",
    "types", "typing", "unicodedata", "urllib.parse",
})
FORBIDDEN_CALLS = frozenset({"eval", "exec", "__import__"})
FORBIDDEN_OS_ATTRS = frozenset({"system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe",
                                "spawnv", "spawnve", "spawnvp", "spawnvpe", "execl", "execle",
                                "execlp", "execlpe", "execv", "execve", "execvp", "execvpe"})

GRACE_ID_RX = re.compile(r"\b(?:M|R|V|DF|G)-[A-Z0-9][A-Z0-9._-]*[A-Z0-9]\b")
SITE_ORIGIN = "https://vladimir-human.github.io/humanizer-ru/"


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return {}
    lines = m.group(1).splitlines()
    data = {}
    in_meta = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            in_meta = False
            km = re.match(r'^([A-Za-z_][\w-]*):(?:\s*(.*))?$', line)
            if km:
                key, val = km.group(1), (km.group(2) or "").strip()
                if key == "metadata" and not val:
                    in_meta = True
                elif val in (">", "|", ">-", "|-"):
                    parts = []
                    i += 1
                    while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")):
                        parts.append(lines[i].strip())
                        i += 1
                    joiner = " " if val.startswith(">") else "\n"
                    data[key] = joiner.join(p for p in parts if p).strip()
                    continue
                elif key in ("name", "description", "license"):
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                        val = val[1:-1]
                    data[key] = val
        elif in_meta:
            vm = re.match(r'^\s+version:\s*["\']?([\d.]+)["\']?\s*$', line)
            if vm:
                data["version"] = vm.group(1)
        i += 1
    if "version" not in data:
        vm = re.search(r'^\s+version:\s*["\']?([\d.]+)["\']?\s*$', m.group(1), re.M)
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


def _allowed_import(name: str) -> bool:
    if name in STDLIB_ALLOWED:
        return True
    top = name.split(".", 1)[0]
    return top != "urllib" and top in STDLIB_ALLOWED


def check_stdlib_imports(path: Path, rel: str) -> list:
    """AST verify that a skill script imports only offline stdlib modules (R-TEXT-ONLY)."""
    problems = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (OSError, SyntaxError) as exc:
        return ["%s: синтаксическая ошибка: %s" % (rel, exc)]
    os_aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _allowed_import(alias.name):
                    problems.append("%s: запрещённый импорт %s (R-TEXT-ONLY)" % (rel, alias.name))
                if alias.name == "os":
                    os_aliases.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level > 0:
                problems.append("%s: относительный импорт запрещён в скриптах навыка (R-TEXT-ONLY)" % rel)
                continue
            if mod == "urllib":
                for alias in node.names:
                    full = "urllib." + alias.name
                    if full not in STDLIB_ALLOWED:
                        problems.append("%s: запрещённый импорт %s (R-TEXT-ONLY)" % (rel, full))
            elif not _allowed_import(mod):
                problems.append("%s: запрещённый импорт %s (R-TEXT-ONLY)" % (rel, mod))
            elif mod == "os":
                for alias in node.names:
                    if alias.name in FORBIDDEN_OS_ATTRS:
                        problems.append("%s: запрещённый импорт os.%s (R-TEXT-ONLY)" % (rel, alias.name))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                problems.append("%s: запрещённый вызов %s() (R-TEXT-ONLY)" % (rel, node.func.id))
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id in os_aliases and node.func.attr in FORBIDDEN_OS_ATTRS:
                    problems.append("%s: запрещённый вызов %s.%s() (R-TEXT-ONLY)" % (rel, node.func.value.id, node.func.attr))
    return problems


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _check_icon_file(root: Path, icon: str, label: str, problems: list) -> None:
    path = (root / icon).resolve()
    if not _is_inside(path, root) or not path.is_file():
        problems.append("%s: файла иконки нет внутри плагина" % icon)
    elif path.stat().st_size >= 2 * 1024 * 1024:
        problems.append("%s: иконка больше 2 МБ" % icon)
    else:
        size = png_size(path.read_bytes())
        if size is None:
            problems.append("%s: иконка должна быть PNG (целым файлом, не обрезанным)" % icon)
        elif size[0] != size[1] or not 512 <= size[0] <= 2048:
            problems.append("%s: иконка должна быть квадратом от 512 до 2048 px, сейчас %dx%d" % (icon, size[0], size[1]))


def _check_text_hygiene(path: Path, rel: str, problems: list, *, ban_set=None, max_bytes: int = 0) -> None:
    raw = path.read_bytes()
    if b"\r" in raw:
        problems.append("%s: переводы строк CRLF" % rel)
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("%s: UTF-8 BOM в начале файла" % rel)
    if max_bytes and len(raw) > max_bytes:
        problems.append("%s: размер %d байт превышает предел %d байт" % (rel, len(raw), max_bytes))
    if ban_set:
        body = raw.decode("utf-8", "replace")
        bad = sorted({hex(ord(c)) for c in body if ord(c) in ban_set})
        if bad:
            problems.append("%s: невидимые символы %s" % (rel, ", ".join(bad)))


# START_BLOCK_SITE
class _HtmlCheckParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.csp = []
        self.external_assets = []
        self.local_refs = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        ad = {k.lower(): (v or "") for k, v in attrs}
        if t == "meta" and ad.get("http-equiv", "").lower() == "content-security-policy":
            self.csp.append(ad.get("content", ""))
        elif t == "script":
            src = ad.get("src", "").strip()
            if src:
                if re.match(r"^(?:https?:)?//", src, re.I):
                    self.external_assets.append(("script", src))
                elif not re.match(r"^(?:data:|blob:|mailto:|#)", src, re.I):
                    self.local_refs.append(("script", src))
        elif t == "link":
            href = ad.get("href", "").strip()
            rel = ad.get("rel", "").lower().split()
            if href and "canonical" not in rel:
                if re.match(r"^(?:https?:)?//", href, re.I):
                    if "stylesheet" in rel or "preload" in rel or "modulepreload" in rel:
                        self.external_assets.append(("link", href))
                elif not re.match(r"^(?:data:|mailto:|#)", href, re.I):
                    self.local_refs.append(("link", href))
        elif t == "img":
            src = ad.get("src", "").strip()
            if src:
                if re.match(r"^(?:https?:)?//", src, re.I):
                    self.external_assets.append(("img", src))
                elif not re.match(r"^(?:data:|#)", src, re.I):
                    self.local_refs.append(("img", src))
        elif t == "a":
            href = ad.get("href", "").strip()
            if href and not re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", href, re.I):
                self.local_refs.append(("a", href))


def check_site(root: Path, version: str, problems: list) -> None:
    site_dir = root / "site"
    if not site_dir.exists():
        return
    for p in sorted(site_dir.rglob("*")):
        if p.is_file() and p.suffix in (".html", ".js", ".json", ".txt", ".xml"):
            _check_text_hygiene(p, p.relative_to(root).as_posix(), problems, ban_set=BIDI_AND_SPOOF)

    for rel in ("site/index.html", "site/check/index.html", "site/sverka/index.html"):
        hp = root / rel
        if not hp.exists():
            continue
        html_text = hp.read_text(encoding="utf-8")
        parser = _HtmlCheckParser()
        parser.feed(html_text)
        if not parser.csp:
            problems.append("%s: нет meta Content-Security-Policy" % rel)
        else:
            csp = parser.csp[0]
            if "default-src 'none'" not in csp:
                problems.append("%s: CSP должен содержать default-src 'none'" % rel)
            if "unsafe-eval" in csp:
                problems.append("%s: CSP не должен разрешать unsafe-eval" % rel)
            if re.search(r"https?://", csp, re.I):
                problems.append("%s: CSP содержит внешний URL" % rel)
        for kind, url in parser.external_assets:
            problems.append("%s: внешний ресурс <%s> %s запрещён (офлайн-страница)" % (rel, kind, url))
        for kind, target in parser.local_refs:
            clean = target.split("#", 1)[0].split("?", 1)[0]
            if not clean:
                continue
            resolved = (hp.parent / clean).resolve()
            if not _is_inside(resolved, site_dir):
                problems.append("%s: локальная ссылка <%s> %s выходит за пределы site/" % (rel, kind, target))
            elif resolved.is_dir():
                if not (resolved / "index.html").is_file():
                    problems.append("%s: локальная ссылка <%s> %s не имеет index.html" % (rel, kind, target))
            elif not resolved.is_file():
                problems.append("%s: локальная ссылка <%s> %s ведёт на отсутствующий файл" % (rel, kind, target))

    index_html = site_dir / "index.html"
    if index_html.exists() and version:
        text = index_html.read_text(encoding="utf-8")
        m = re.search(r'"softwareVersion"\s*:\s*"([^"]+)"', text)
        if not m or m.group(1) != version:
            problems.append("site/index.html: softwareVersion %s, а в SKILL.md %s" % (m.group(1) if m else None, version))

    llms = site_dir / "llms.txt"
    if llms.exists() and version:
        text = llms.read_text(encoding="utf-8")
        m = re.search(r"\bv(\d+\.\d+\.\d+)\b", text)
        if not m or m.group(1) != version:
            problems.append("site/llms.txt: версия v%s, а в SKILL.md %s" % (m.group(1) if m else None, version))

    sitemap = site_dir / "sitemap.xml"
    if sitemap.exists():
        try:
            sm_root = ET.parse(sitemap).getroot()
        except ET.ParseError as exc:
            problems.append("site/sitemap.xml: ошибка XML: %s" % exc)
        else:
            for elem in sm_root.iter():
                if elem.tag.endswith("loc") and elem.text:
                    loc = elem.text.strip()
                    if loc.startswith(SITE_ORIGIN):
                        sub = loc[len(SITE_ORIGIN):]
                        target = site_dir / sub if sub else site_dir
                        if target.is_dir():
                            ok = (target / "index.html").is_file()
                        else:
                            ok = target.is_file()
                        if not ok or not _is_inside(target, site_dir):
                            problems.append("site/sitemap.xml: путь %s не существует в site/" % loc)
# END_BLOCK_SITE


# START_BLOCK_GRACE
def _unique_ids(elements, label: str, problems: list) -> set:
    seen = set()
    for el in elements:
        eid = el.attrib.get("id", "").strip()
        if not eid:
            problems.append("%s: пустой атрибут id у <%s>" % (label, el.tag))
        elif eid in seen:
            problems.append("%s: дублирующийся id %s" % (label, eid))
        else:
            seen.add(eid)
    return seen


def _split_tokens(val: str) -> list:
    return [t.strip() for t in re.split(r"[,;\s]+", val or "") if t.strip()]


def check_grace(root: Path, version: str, problems: list) -> None:
    grace_dir = root / ".grace"
    if not grace_dir.exists():
        return
    req_path = grace_dir / "context" / "requirements.xml"
    graph_path = grace_dir / "graph" / "index.xml"
    ver_path = grace_dir / "verification" / "index.xml"

    req_root = graph_root = ver_root = None
    req_ids = inv_ids = mod_ids = flow_ids = ver_ids = gap_ids = set()

    if req_path.exists():
        try:
            req_root = ET.parse(req_path).getroot()
        except ET.ParseError as exc:
            problems.append(".grace/context/requirements.xml: ошибка XML: %s" % exc)
        else:
            v = req_root.attrib.get("version")
            if version and v != version:
                problems.append(".grace/context/requirements.xml: версия %s, а в SKILL.md %s" % (v, version))
            req_ids = _unique_ids(list(req_root.findall("requirement")) + list(req_root.findall("rule")),
                                  ".grace/context/requirements.xml", problems)
            inv_ids = _unique_ids(req_root.findall(".//invariant"), ".grace/context/requirements.xml", problems)

    if graph_path.exists():
        try:
            graph_root = ET.parse(graph_path).getroot()
        except ET.ParseError as exc:
            problems.append(".grace/graph/index.xml: ошибка XML: %s" % exc)
        else:
            mod_ids = _unique_ids(graph_root.findall(".//module"), ".grace/graph/index.xml", problems)
            flow_ids = _unique_ids(graph_root.findall(".//flow"), ".grace/graph/index.xml", problems)
            for mod in graph_root.findall(".//module"):
                for dep in re.findall(r"\bM-[A-Z0-9][A-Z0-9._-]*[A-Z0-9]\b", mod.attrib.get("depends", "")):
                    if dep not in mod_ids:
                        problems.append(".grace/graph/index.xml: %s ссылается на неизвестный модуль %s" % (mod.attrib.get("id"), dep))

    if ver_path.exists():
        try:
            ver_root = ET.parse(ver_path).getroot()
        except ET.ParseError as exc:
            problems.append(".grace/verification/index.xml: ошибка XML: %s" % exc)
        else:
            ver_ids = _unique_ids(ver_root.findall("entry"), ".grace/verification/index.xml", problems)
            gap_ids = _unique_ids(ver_root.findall(".//gap"), ".grace/verification/index.xml", problems)

    if req_root is not None and graph_root is not None:
        for inv in req_root.findall(".//invariant"):
            for owner in _split_tokens(inv.attrib.get("owner", "")):
                if owner not in mod_ids:
                    problems.append(".grace/context/requirements.xml: инвариант %s ссылается на неизвестный модуль %s" % (inv.attrib.get("id"), owner))

    if ver_root is not None and graph_root is not None:
        for entry in ver_root.findall("entry"):
            for mod in _split_tokens(entry.attrib.get("module", "")):
                if mod not in mod_ids:
                    problems.append(".grace/verification/index.xml: %s ссылается на неизвестный модуль %s" % (entry.attrib.get("id"), mod))

    if ver_root is not None and req_root is not None:
        valid_reqs = req_ids | inv_ids
        for entry in ver_root.findall("entry"):
            for req_tok in _split_tokens(entry.attrib.get("requirements", "")):
                if req_tok not in valid_reqs:
                    problems.append(".grace/verification/index.xml: %s ссылается на неизвестное требование %s" % (entry.attrib.get("id"), req_tok))

    if req_root is not None and graph_root is not None and ver_root is not None:
        all_ids = req_ids | inv_ids | mod_ids | flow_ids | ver_ids | gap_ids
        for sub in ("skills", "scripts", "eval", "tests"):
            base = root / sub
            if not base.exists():
                continue
            for p in sorted(base.rglob("*.py")):
                if any(part in ("__pycache__", ".cache", "results", "corpus") for part in p.parts):
                    continue
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                in_links = False
                found = []
                for ln in lines[:40]:
                    if "LINKS:" in ln:
                        in_links = True
                        found += GRACE_ID_RX.findall(ln.split("LINKS:", 1)[1])
                    elif in_links:
                        if re.match(r"^\s*#\s+(?:END_|PURPOSE:|SCOPE:|DEPENDS:|START_)", ln) or not ln.lstrip().startswith("#"):
                            in_links = False
                        else:
                            found += GRACE_ID_RX.findall(ln)
                for tok in sorted(set(found)):
                    if tok not in all_ids:
                        problems.append("%s: неизвестный GRACE ID %s в LINKS" % (p.relative_to(root).as_posix(), tok))
# END_BLOCK_GRACE


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
    if fm.get("license") and fm.get("license") != "MIT":
        problems.append("SKILL.md: license должен быть MIT, сейчас %r" % fm.get("license"))
    version = fm.get("version")
    if not version:
        problems.append("SKILL.md: нет metadata.version")

    # START_BLOCK_VERSIONS
    manifests = {
        ".claude-plugin/plugin.json": lambda d: d.get("version"),
        ".claude-plugin/marketplace.json": lambda d: d["plugins"][0].get("version"),
        ".codex-plugin/plugin.json": lambda d: d.get("version"),
        ".cursor-plugin/plugin.json": lambda d: d.get("version"),
        "gemini-extension.json": lambda d: d.get("version"),
    }
    parsed = {}
    for rel, get in manifests.items():
        p = root / rel
        if not p.exists():
            problems.append("нет %s" % rel)
            continue
        _check_text_hygiene(p, rel, problems, max_bytes=MAX_BYTES)
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            v = get(data)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            problems.append("%s не читается: %s" % (rel, exc))
            continue
        parsed[rel] = data
        if v != version:
            problems.append("%s: версия %s, а в SKILL.md %s" % (rel, v, version))
        if data.get("name") != "humanizer-ru":
            problems.append("%s: name должен быть humanizer-ru, сейчас %r" % (rel, data.get("name")))
    changelog = root / "CHANGELOG.md"
    if changelog.exists():
        m = re.search(r"^## \[?(\d+\.\d+\.\d+)", changelog.read_text(encoding="utf-8"), re.M)
        if not m or m.group(1) != version:
            problems.append("CHANGELOG.md: верхняя запись %s, а в SKILL.md %s" % (m.group(1) if m else None, version))
    else:
        problems.append("нет CHANGELOG.md")

    for doc_rel in ("README.md", "README.en.md", "LICENSE"):
        dp = root / doc_rel
        if dp.exists():
            _check_text_hygiene(dp, doc_rel, problems,
                                ban_set=BIDI_AND_SPOOF if doc_rel.endswith(".md") else None,
                                max_bytes=MAX_BYTES)
    # END_BLOCK_VERSIONS

    # START_BLOCK_LISTING
    # Anthropic's plugin directory builds the listing from plugin.json: the icon must be a square
    # PNG or JPEG of 512 to 2048 px under 2 MB (we ship PNG), the links must be https.
    plugin = parsed.get(".claude-plugin/plugin.json") or {}
    if plugin:
        icon = plugin.get("icon")
        if not icon:
            problems.append(".claude-plugin/plugin.json: нет поля icon (иконка для каталога плагинов)")
        else:
            _check_icon_file(root, icon, ".claude-plugin/plugin.json", problems)
        for key in ("documentationUrl", "supportUrl", "homepage", "repository"):
            if key in ("documentationUrl", "supportUrl") or plugin.get(key) is not None:
                if not str(plugin.get(key, "")).startswith("https://"):
                    problems.append(".claude-plugin/plugin.json: %s должен быть ссылкой https://" % key)
        if plugin.get("license") != "MIT":
            problems.append(".claude-plugin/plugin.json: license должен быть MIT, сейчас %r" % plugin.get("license"))
        skills_ref = plugin.get("skills")
        if not isinstance(skills_ref, str) or not _is_inside(root / skills_ref, root) or not (root / skills_ref).is_dir():
            problems.append(".claude-plugin/plugin.json: поле skills (%r) не указывает на папку внутри репозитория" % skills_ref)

    mp = parsed.get(".claude-plugin/marketplace.json") or {}
    if mp and isinstance(mp.get("plugins"), list) and mp["plugins"]:
        p0 = mp["plugins"][0]
        if p0.get("name") != "humanizer-ru":
            problems.append(".claude-plugin/marketplace.json: plugins[0].name должен быть humanizer-ru, сейчас %r" % p0.get("name"))
        if p0.get("source") != "./":
            problems.append(".claude-plugin/marketplace.json: plugins[0].source должен быть './', сейчас %r" % p0.get("source"))
        if p0.get("license") != "MIT":
            problems.append(".claude-plugin/marketplace.json: plugins[0].license должен быть MIT, сейчас %r" % p0.get("license"))

    codex = parsed.get(".codex-plugin/plugin.json") or {}
    if codex:
        if codex.get("license") != "MIT":
            problems.append(".codex-plugin/plugin.json: license должен быть MIT, сейчас %r" % codex.get("license"))
        skills_ref = codex.get("skills")
        if not isinstance(skills_ref, str) or not _is_inside(root / skills_ref, root) or not (root / skills_ref).is_dir():
            problems.append(".codex-plugin/plugin.json: поле skills (%r) не указывает на папку внутри репозитория" % skills_ref)
        for key in ("homepage", "repository"):
            if not str(codex.get(key, "")).startswith("https://"):
                problems.append(".codex-plugin/plugin.json: %s должен быть ссылкой https://" % key)
        iface = codex.get("interface")
        if not isinstance(iface, dict):
            problems.append(".codex-plugin/plugin.json: нет объекта interface")
        else:
            for key in ("displayName", "shortDescription", "developerName"):
                if not str(iface.get(key, "")).strip():
                    problems.append(".codex-plugin/plugin.json: interface.%s пустой" % key)
            if not str(iface.get("websiteURL", "")).startswith("https://"):
                problems.append(".codex-plugin/plugin.json: interface.websiteURL должен быть ссылкой https://")

    cursor = parsed.get(".cursor-plugin/plugin.json") or {}
    if cursor:
        if cursor.get("license") != "MIT":
            problems.append(".cursor-plugin/plugin.json: license должен быть MIT, сейчас %r" % cursor.get("license"))
        for key in ("homepage", "repository"):
            if not str(cursor.get(key, "")).startswith("https://"):
                problems.append(".cursor-plugin/plugin.json: %s должен быть ссылкой https://" % key)
        logo = cursor.get("logo")
        if logo is not None:
            _check_icon_file(root, str(logo), ".cursor-plugin/plugin.json", problems)
        skills_ref = cursor.get("skills")
        if skills_ref is not None:
            if not isinstance(skills_ref, str) or not _is_inside(root / skills_ref, root) or not (root / skills_ref).is_dir():
                problems.append(".cursor-plugin/plugin.json: поле skills (%r) не указывает на папку внутри репозитория" % skills_ref)
    # END_BLOCK_LISTING

    # START_BLOCK_FILES
    for ref in sorted(set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", text))):
        target = ref.split()[0]
        if not (root / SKILL_DIR / target).exists():
            problems.append("SKILL.md ссылается на %s, файла нет" % target)
    for md_file in [skill_md] + sorted((root / SKILL_DIR / "references").glob("*.md")):
        if not md_file.exists():
            continue
        md_text = md_file.read_text(encoding="utf-8")
        for ref in sorted(set(re.findall(r"\]\(((?:references|scripts)/[^)\s#]+)", md_text))):
            if not (root / SKILL_DIR / ref).exists():
                problems.append("%s ссылается на %s, файла нет" % (md_file.relative_to(root).as_posix(), ref))
    for p in sorted((root / "skills").rglob("*")):
        if not p.is_file():
            continue
        if p.suffix in JUNK_SUFFIXES or p.name in JUNK_NAMES:
            problems.append("%s: мусорный файл внутри skills/" % p.relative_to(root).as_posix())
    for p in sorted((root / SKILL_DIR).rglob("*")):
        if not p.is_file() or p.suffix not in (".md", ".py", ".json"):
            continue
        rel = p.relative_to(root).as_posix()
        _check_text_hygiene(p, rel, problems, ban_set=INVISIBLE, max_bytes=MAX_BYTES)
        if p.suffix == ".py" and p.parent.name == "scripts":
            problems.extend(check_stdlib_imports(p, rel))
    # END_BLOCK_FILES

    # START_BLOCK_PORTABLE
    # The browser checker reads its own copy of rules.json; the chat prompt must fit the smallest
    # instruction fields of chat services (4000 characters). Trees without them skip the check.
    rules = root / SKILL_DIR / "scripts" / "rules.json"
    site_rules = root / "site" / "check" / "rules.json"
    if site_rules.exists() and rules.exists() and site_rules.read_bytes() != rules.read_bytes():
        problems.append("site/check/rules.json отличается от %s: скопируйте его" % (SKILL_DIR / "scripts" / "rules.json"))
    chat = root / "prompt" / "chat.md"
    if chat.exists():
        _check_text_hygiene(chat, "prompt/chat.md", problems, ban_set=INVISIBLE)
        raw = chat.read_text(encoding="utf-8")
        if "<!-- prompt:start -->" not in raw or "<!-- prompt:end -->" not in raw:
            problems.append("prompt/chat.md: нет меток <!-- prompt:start --> и <!-- prompt:end -->")
        else:
            body = raw.split("<!-- prompt:start -->", 1)[1].split("<!-- prompt:end -->", 1)[0].strip()
            if len(body) > 4000:
                problems.append("prompt/chat.md: промпт длиннее 4000 знаков (%d)" % len(body))
            # The fact-check page copies the prompt from its own file (GitHub Pages serves site/ only).
            site_prompt = root / "site" / "sverka" / "prompt.txt"
            if site_prompt.exists() and site_prompt.read_text(encoding="utf-8") != body + "\n":
                problems.append("site/sverka/prompt.txt отличается от промпта в prompt/chat.md: скопируйте его")
    # END_BLOCK_PORTABLE

    check_site(root, version or "", problems)
    check_grace(root, version or "", problems)
    return problems


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Проверка целостности репозитория humanizer-ru.")
    ap.add_argument("root", nargs="?", default=str(ROOT), help="Корень репозитория (по умолчанию текущий)")
    args = ap.parse_args(argv)
    problems = check(Path(args.root))
    for p in problems:
        print("ОШИБКА:", p)
    print("Проверка репозитория: %s" % ("ошибок нет" if not problems else "%d ошибок" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
