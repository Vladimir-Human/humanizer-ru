# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The repository checks pass on the real tree and fail on broken copies; the zip has
#          the layout Claude.ai expects; the tree for the plugin directory is the plugin and
#          nothing else, and its check can fail; every Было -> Стало pair and inline arrow in
#          references/ keeps all facts without banned/retracted citations.
# LINKS: V-M-CHECK-REPO; V-M-BUILD-ZIP; V-M-BUILD-DIRECTORY; V-M-CHECK-SCRIPTS; V-M-EVAL-4.3.0;
#        R-REFERENCES-KEEP-FACTS; R-TEXT-ONLY; R-DIRECTORY; R-HOLDOUT; R-DETECTOR-RISK.
# END_MODULE_CONTRACT
import collections
import importlib.util
import io
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


# The seven passes of an interlaced image: x start, y start, x step, y step (from the PNG standard).
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _rows(width, height, interlace=0):
    """The unpacked data of a grayscale 8-bit image of black pixels, each row with its filter byte.
    The pixels of every pass are counted one by one, not by the formula check_repo uses."""
    data = b""
    for x0, y0, dx, dy in (ADAM7 if interlace else ((0, 0, 1, 1),)):
        across = sum(1 for x in range(width) if x >= x0 and (x - x0) % dx == 0)
        down = sum(1 for y in range(height) if y >= y0 and (y - y0) % dy == 0)
        if across and down:
            data += (b"\x00" * (1 + across)) * down
    return data


def _png(width, height, rows=None, interlace=0, color=0, depth=8, plte=False):
    """A real grayscale PNG of black pixels. `rows` replaces the unpacked image data, to fake a
    file whose data do not fit its header; the other arguments bend the header."""
    if rows is None:
        rows = _rows(width, height, interlace)
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + (_chunk(b"PLTE", b"\0\0\0") if plte else b"")
            + _chunk(b"IDAT", zlib.compress(rows)) + _chunk(b"IEND", b""))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


check_repo = _load("check_repo")
build_zip = _load("build_zip")
build_directory = _load("build_directory")
check_scripts = _load("check_scripts")
check_site_facts = _load("check_site_facts")


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for rel in ("skills", ".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            shutil.copytree(ROOT / rel, self.tmp / rel)
        for rel in ("CHANGELOG.md", "gemini-extension.json"):
            shutil.copy(ROOT / rel, self.tmp / rel)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_require_node_when_set(self):
        if os.environ.get("REQUIRE_NODE"):
            self.assertIsNotNone(shutil.which("node"), "REQUIRE_NODE is set but node is missing on PATH")

    def test_real_tree_is_clean(self):
        self.assertEqual(check_repo.check(ROOT), [])

    def test_version_mismatch_is_caught(self):
        p = self.tmp / ".claude-plugin" / "plugin.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["version"] = "0.0.1"
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("plugin.json" in x for x in check_repo.check(self.tmp)))

    def test_cursor_and_gemini_manifest_versions_are_checked(self):
        for rel in (".cursor-plugin/plugin.json", "gemini-extension.json"):
            p = self.tmp / rel
            saved = p.read_text(encoding="utf-8")
            data = json.loads(saved)
            data["version"] = "0.0.1"
            p.write_text(json.dumps(data), encoding="utf-8")
            with self.subTest(manifest=rel):
                self.assertTrue(any(x.startswith(rel) for x in check_repo.check(self.tmp)))
            p.write_text(saved, encoding="utf-8")

    def test_grace_requirements_version_is_checked(self):
        # 4.1.7: requirements.xml said 4.1.1 while the release was 4.1.6.
        self.assertEqual(check_repo.check(self.tmp), [])  # no .grace/ in the copy: nothing to compare
        req = self.tmp / ".grace" / "context" / "requirements.xml"
        req.parent.mkdir(parents=True)
        req.write_text((ROOT / ".grace" / "context" / "requirements.xml").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(check_repo.check(self.tmp), [])
        req.write_text('<requirements project="humanizer-ru" version="4.1.1"></requirements>', encoding="utf-8")
        self.assertTrue(any("requirements.xml" in x for x in check_repo.check(self.tmp)))

    def test_grace_xml_and_id_integrity_is_checked(self):
        shutil.copytree(ROOT / ".grace", self.tmp / ".grace")
        self.assertEqual(check_repo.check(self.tmp), [])
        # Corrupt XML is caught.
        g = self.tmp / ".grace" / "graph" / "index.xml"
        saved_g = g.read_text(encoding="utf-8")
        g.write_text("<graph><unclosed>", encoding="utf-8")
        self.assertTrue(any("ошибка XML" in x for x in check_repo.check(self.tmp)))
        # Duplicate module ID is caught.
        g.write_text(saved_g.replace("</modules>", '<module id="M-SKILL" file="x" purpose="x" depends="none" exports="x" /></modules>'),
                     encoding="utf-8")
        self.assertTrue(any("дублирующийся id M-SKILL" in x for x in check_repo.check(self.tmp)))
        g.write_text(saved_g, encoding="utf-8")
        # Unknown requirement in verification/index.xml is caught.
        v = self.tmp / ".grace" / "verification" / "index.xml"
        saved_v = v.read_text(encoding="utf-8")
        v.write_text(saved_v.replace('requirements="R-DIRECTORY"', 'requirements="R-NO-SUCH-REQ"'), encoding="utf-8")
        self.assertTrue(any("R-NO-SUCH-REQ" in x for x in check_repo.check(self.tmp)))
        v.write_text(saved_v, encoding="utf-8")
        # Dangling LINKS: token in Python code is caught.
        s = self.tmp / "skills" / "humanizer-ru" / "scripts" / "lint_style.py"
        saved_s = s.read_text(encoding="utf-8")
        s.write_text(saved_s.replace("M-LINT-STYLE;", "M-LINT-STYLE; V-M-NO-SUCH;"), encoding="utf-8")
        self.assertTrue(any("V-M-NO-SUCH" in x for x in check_repo.check(self.tmp)))
        s.write_text(saved_s, encoding="utf-8")

    def test_stdlib_ast_check_blocks_network_and_third_party(self):
        s = self.tmp / "skills" / "humanizer-ru" / "scripts" / "lint_style.py"
        saved = s.read_text(encoding="utf-8")
        for snippet, expect in (
            ("import urllib.request\n", "urllib.request"),
            ("from urllib import request\n", "urllib.request"),
            ("import subprocess\n", "subprocess"),
            ("import torch\n", "torch"),
            ("eval('1')\n", "eval()"),
        ):
            s.write_text(saved + "\n" + snippet, encoding="utf-8")
            with self.subTest(snippet=snippet.strip()):
                self.assertTrue(any(expect in x and "R-TEXT-ONLY" in x for x in check_repo.check(self.tmp)))
        s.write_text(saved, encoding="utf-8")

    def test_manifest_schema_junk_and_size_cap_are_checked(self):
        # Junk file inside skills/ is caught.
        bak = self.tmp / "skills" / "humanizer-ru" / "SKILL.md.bak"
        bak.write_text("backup\n", encoding="utf-8")
        self.assertTrue(any("мусорный файл" in x for x in check_repo.check(self.tmp)))
        bak.unlink()
        # File > 256 KiB inside skills/ is caught.
        big = self.tmp / "skills" / "humanizer-ru" / "references" / "huge.md"
        big.write_bytes(b"a" * (256 * 1024 + 1))
        self.assertTrue(any("превышает предел" in x for x in check_repo.check(self.tmp)))
        big.unlink()
        # Wrong name/license or BOM in codex manifest is caught.
        cp = self.tmp / ".codex-plugin" / "plugin.json"
        saved = cp.read_bytes()
        data = json.loads(saved.decode("utf-8"))
        data["license"] = "Apache-2.0"
        cp.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))
        probs = check_repo.check(self.tmp)
        self.assertTrue(any("UTF-8 BOM" in x for x in probs))
        self.assertTrue(any("license должен быть MIT" in x for x in probs))
        cp.write_bytes(saved)

    def test_missing_reference_is_caught(self):
        (self.tmp / "skills" / "humanizer-ru" / "references" / "patterns.md").unlink()
        self.assertTrue(any("patterns.md" in x for x in check_repo.check(self.tmp)))

    def test_crlf_and_invisible_are_caught(self):
        p = self.tmp / "skills" / "humanizer-ru" / "references" / "examples.md"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n", 1) + "\u200b".encode("utf-8"))
        problems = check_repo.check(self.tmp)
        self.assertTrue(any("CRLF" in x for x in problems))
        self.assertTrue(any("невидимые" in x for x in problems))

    def test_site_rules_copy_and_chat_prompt_length(self):
        # 4.2.0: the browser checker reads site/check/rules.json; the chat prompt must fit 4000 characters.
        shutil.copytree(ROOT / "site", self.tmp / "site")
        shutil.copytree(ROOT / "prompt", self.tmp / "prompt")
        self.assertEqual(check_repo.check(self.tmp), [])
        rules = self.tmp / "skills" / "humanizer-ru" / "scripts" / "rules.json"
        rules.write_text(rules.read_text(encoding="utf-8").replace('"many": 5.0', '"many": 6.0'), encoding="utf-8")
        self.assertTrue(any("site/check/rules.json" in x for x in check_repo.check(self.tmp)))
        shutil.copy(rules, self.tmp / "site" / "check" / "rules.json")
        chat = self.tmp / "prompt" / "chat.md"
        chat.write_text(chat.read_text(encoding="utf-8").replace("<!-- prompt:end -->", "я" * 1000 + "\n<!-- prompt:end -->"), encoding="utf-8")
        too_long = [x for x in check_repo.check(self.tmp) if "4000" in x]
        self.assertEqual(len(too_long), 1)
        self.assertIn("prompt/chat.md: промпт длиннее 4000 знаков", too_long[0])
        # The fact-check page copies its own prompt.txt: a stale copy is caught.
        self.assertTrue(any("site/sverka/prompt.txt" in x for x in check_repo.check(self.tmp)))

    def test_site_csp_links_version_and_sitemap_are_checked(self):
        shutil.copytree(ROOT / "site", self.tmp / "site")
        self.assertEqual(check_repo.check(self.tmp), [])
        ver = check_repo.frontmatter((ROOT / "skills" / "humanizer-ru" / "SKILL.md").read_text(encoding="utf-8"))["version"]
        idx = self.tmp / "site" / "index.html"
        saved_idx = idx.read_text(encoding="utf-8")
        # External script & unsafe-eval CSP & stale softwareVersion & broken local link
        idx.write_text(saved_idx.replace("default-src 'none'", "default-src 'self' 'unsafe-eval'")
                       .replace(f'"softwareVersion":"{ver}"', '"softwareVersion":"4.0.0"')
                       .replace("</body>", '<script src="https://cdn.example/x.js"></script><a href="no-such-page.html">x</a></body>'),
                       encoding="utf-8")
        probs = check_repo.check(self.tmp)
        self.assertTrue(any("default-src 'none'" in x for x in probs))
        self.assertTrue(any("unsafe-eval" in x for x in probs))
        self.assertTrue(any("внешний ресурс" in x for x in probs))
        self.assertTrue(any("no-such-page.html" in x for x in probs))
        self.assertTrue(any("softwareVersion" in x for x in probs))
        idx.write_text(saved_idx, encoding="utf-8")
        # Stale version in llms.txt & missing sitemap path
        llms = self.tmp / "site" / "llms.txt"
        llms.write_text(llms.read_text(encoding="utf-8").replace(f"v{ver}", "v4.1.0"), encoding="utf-8")
        sm = self.tmp / "site" / "sitemap.xml"
        sm.write_text(sm.read_text(encoding="utf-8").replace("/llms.txt", "/missing.txt"), encoding="utf-8")
        probs = check_repo.check(self.tmp)
        self.assertTrue(any("site/llms.txt" in x for x in probs))
        self.assertTrue(any("site/sitemap.xml" in x for x in probs))

    def _plugin_json(self, **changes):
        p = self.tmp / ".claude-plugin" / "plugin.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for key, value in changes.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        p.write_text(json.dumps(data), encoding="utf-8")

    def test_icon_must_be_a_square_png_for_the_directory(self):
        # What Anthropic's plugin directory reads: a square PNG of 512 to 2048 px under 2 MB.
        icon = self.tmp / ".claude-plugin" / "icon.png"
        icon.unlink()
        self.assertTrue(any("файла иконки нет" in x for x in check_repo.check(self.tmp)))
        whole = _png(1024, 1024)
        damaged = bytearray(whole)
        damaged[45] ^= 0xFF  # inside the image data: the CRC of the chunk no longer fits
        for raw, expect in ((_png(100, 100), "от 512 до 2048"), (_png(3000, 3000), "от 512 до 2048"),
                            (_png(1024, 512), "1024x512"), (b"GIF89a" + b"\0" * 40, "должна быть PNG"),
                            (whole[:33], "должна быть PNG"),  # cut after IHDR
                            (whole[:-12], "должна быть PNG"),  # no IEND chunk
                            (whole + b"junk", "должна быть PNG"),  # something after IEND
                            (bytes(damaged), "должна быть PNG"),
                            (_png(1024, 1024, rows=b"\x00\x00"), "должна быть PNG"),  # data of a 1x1 image
                            # the same with seven passes: the exact size of the data is known there too
                            (_png(1024, 1024, interlace=1, rows=b"\x00\x00"), "должна быть PNG"),
                            (_png(1024, 1024, rows=_rows(1024, 1024) + b"\x00"), "должна быть PNG"),  # a byte too many
                            (_png(1024, 1024, interlace=1, rows=_rows(1024, 1024, 1)[:-1]), "должна быть PNG"),
                            (_png(1024, 1024, rows=b"\x05" + _rows(1024, 1024)[1:]), "должна быть PNG"),  # filter type 5
                            (_png(1024, 1024, color=2, depth=4), "должна быть PNG"),  # no such colour type and depth
                            (_png(1024, 1024, interlace=2), "должна быть PNG"),
                            (_png(1024, 1024, color=3), "должна быть PNG"),  # a palette image without a palette
                            (b"\0" * (2 * 1024 * 1024), "больше 2 МБ")):
            icon.write_bytes(raw)
            self.assertTrue(any(expect in x for x in check_repo.check(self.tmp)), expect)
        for fine in (_png(1024, 1024), _png(1024, 1024, interlace=1), _png(1024, 1024, color=3, plte=True)):
            icon.write_bytes(fine)
            self.assertEqual(check_repo.check(self.tmp), [])
        self._plugin_json(icon=None)
        self.assertTrue(any("нет поля icon" in x for x in check_repo.check(self.tmp)))
        self._plugin_json(icon="../icon.png")
        self.assertTrue(any("файла иконки нет" in x for x in check_repo.check(self.tmp)))

    def test_listing_links_must_be_https(self):
        self._plugin_json(supportUrl="http://example.com/issues")
        self.assertTrue(any("supportUrl" in x for x in check_repo.check(self.tmp)))
        self._plugin_json(supportUrl="https://example.com/issues", documentationUrl=None)
        self.assertTrue(any("documentationUrl" in x for x in check_repo.check(self.tmp)))

    def test_zip_layout_hygiene_and_cli_help(self):
        out = self.tmp / "skill.zip"
        build_zip.build(out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        self.assertIn("humanizer-ru/SKILL.md", names)
        self.assertTrue(all(n.startswith("humanizer-ru/") and n.isascii() for n in names))
        self.assertFalse(any("__pycache__" in n for n in names))
        # Junk files (.bak/.swp/.DS_Store) are skipped; CRLF is refused.
        skill_copy = self.tmp / "skills" / "humanizer-ru"
        (skill_copy / "SKILL.md.bak").write_text("junk\n", encoding="utf-8")
        (skill_copy / ".DS_Store").write_bytes(b"junk")
        out2 = self.tmp / "skill2.zip"
        names2 = build_zip.build(out2, src=skill_copy)
        self.assertFalse(any(n.endswith(".bak") or n.endswith(".DS_Store") for n in names2))
        (skill_copy / "SKILL.md").write_bytes((skill_copy / "SKILL.md").read_bytes().replace(b"\n", b"\r\n", 1))
        with self.assertRaises(SystemExit):
            build_zip.build(self.tmp / "bad.zip", src=skill_copy)
        # --help exits 0 cleanly on build_zip and build_directory.
        for mod in (build_zip, build_directory):
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                mod.main(["--help"])
            self.assertEqual(ctx.exception.code, 0)


def _load_skill(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "skills" / "humanizer-ru" / "scripts" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def reference_pairs(patterns: str, examples: str, genres: str = "", detectors: str = ""):
    """Every «Было → Стало» pair of the references:
    - one-line pairs in patterns.md (including «A» / «B» and «Стало: «A» или «B»»)
    - multiline bullet «Было:\n...» -> «Стало: «...»» blocks in patterns.md (#15)
    - quoted blocks in examples.md
    - inline «Before» → «After» pairs in genres.md and detectors.md.
    «Стало» lines that only describe the action («удалить абзац») are not pairs."""
    pairs = []
    # Single-line Было -> Стало, with optional «/ «...»» or «или [просто ]«...»» alternatives.
    rx = re.compile(
        r"^Было: «(.+?)»(?: / «(.+?)»)?\n"
        r"Стало: «(.+?)»(?:(?: / | или (?:просто )?)«(.+?)»)?",
        re.M,
    )
    for m in rx.finditer(patterns):
        pairs.append(("patterns: " + m.group(1)[:40], m.group(1), m.group(3)))
        if m.group(4):
            before2 = m.group(2) if m.group(2) else m.group(1)
            pairs.append(("patterns: " + before2[:40], before2, m.group(4)))

    # Multiline Было:\n...\n\nСтало: «...» (e.g. patterns.md #15).
    ml_rx = re.compile(r"^Было:\n((?:[^\n]+\n)+?)\nСтало: «(.+?)»", re.M)
    for m in ml_rx.finditer(patterns):
        before = m.group(1).strip()
        pairs.append(("patterns (multiline): " + before[:40], before, m.group(2)))

    def unquote(block):
        return "\n".join(line[2:] if line.startswith("> ") else line[1:] for line in block.splitlines())

    for sec in re.split(r"^## ", examples, flags=re.M)[1:]:
        m = re.search(r"Было:\n\n((?:>.*\n)+)\nСтало:\n\n((?:>.*\n)+)", sec)
        if m:
            pairs.append(("examples: " + sec.split("\n")[0], unquote(m.group(1)), unquote(m.group(2))))

    arrow_rx = re.compile(r"«([^»\n]+)»\s*→\s*«([^»\n]+)»")
    for label, text in (("genres", genres), ("detectors", detectors)):
        for before, after in arrow_rx.findall(text):
            pairs.append(("%s: %s" % (label, before[:40]), before, after))
    return pairs


# Verified arXiv papers cited in README/docs (audit-detectors-2026 verified all 9 real & non-retracted).
VERIFIED_ARXIV_IDS = frozenset({
    "2410.23728", "2509.21269", "2611.00359", "2605.19516", "2405.07940",
    "2506.07001", "2501.03437", "2606.25152", "2510.02319",
})
# Broken or retracted/banned citations that must never reappear in docs or references.
BANNED_CITATION_PATTERNS = (
    "kakya-model-ii-detectora-poteryala-tekst",  # broken misspelled Antiplagiat URL
)
ARXIV_RX = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arXiv[:\s]+)(\d{4}\.\d{4,5})", re.I)


def find_bad_citations(text: str) -> list:
    hits = [pat for pat in BANNED_CITATION_PATTERNS if pat in text]
    for aid in ARXIV_RX.findall(text):
        if aid not in VERIFIED_ARXIV_IDS:
            hits.append("unverified/banned arXiv:" + aid)
    return hits


class ReferencesTest(unittest.TestCase):
    """R-REFERENCES-KEEP-FACTS & V-M-EVAL-4.3.0: the examples teach the executor by imitation, so an
    example that invents a fact or shifts scope/modality/negation teaches those mistakes; docs and
    references must cite zero banned or unverified/retracted papers."""

    def setUp(self):
        self.cf = _load_skill("check_facts")
        ref = ROOT / "skills" / "humanizer-ru" / "references"
        self.patterns = (ref / "patterns.md").read_text(encoding="utf-8")
        self.examples = (ref / "examples.md").read_text(encoding="utf-8")
        self.genres = (ref / "genres.md").read_text(encoding="utf-8")
        self.detectors = (ref / "detectors.md").read_text(encoding="utf-8")

    def bad(self, before, after):
        r = self.cf.compare(before, after)
        return r["errors"] + [
            c for c in r["checks"]
            if c["kind"] in ("added", "scope", "modality", "negation", "inverted")
        ]

    def test_every_example_keeps_the_facts_and_adds_none(self):
        pairs = reference_pairs(self.patterns, self.examples, self.genres, self.detectors)
        self.assertGreaterEqual(len(pairs), 28)
        self.assertGreaterEqual(sum(1 for p in pairs if p[0].startswith("examples")), 5)
        self.assertTrue(any(p[0].startswith("patterns (multiline)") for p in pairs))
        self.assertTrue(any(p[0].startswith("genres:") for p in pairs))
        self.assertTrue(any(p[0].startswith("detectors:") for p in pairs))
        for where, before, after in pairs:
            self.assertEqual(self.bad(before, after), [], where)

    def test_an_invented_fact_or_shift_in_an_example_is_caught(self):
        for old, new in (("Стало: «В курсе 12 уроков по Excel: от формул до сводных таблиц.»",
                          "Стало: «В курсе 14 уроков по Excel: от формул до сводных таблиц.»"),
                         ("Стало: «Вышла версия 2.4.»", "Стало: «Вышла версия 2.5.»"),
                         ("Стало: «Заявку на отпуск подают на портале HR не позднее чем за две недели.»",
                          "Стало: «Заявку на отпуск подают на портале HR не позднее чем за три недели.»")):
            self.assertEqual(self.patterns.count(old), 1, old)
            broken = reference_pairs(self.patterns.replace(old, new), self.examples)
            self.assertTrue(any(self.bad(b, a) for _, b, a in broken), new)
        # Scope, modality, and negation shifts are also caught by bad().
        self.assertTrue(self.bad("Работает для сервиса.", "Работает для каждого сервиса."))
        self.assertTrue(self.bad("Вы можете прийти в любой магазин.", "Приходите в любой магазин."))
        self.assertTrue(self.bad("На стоимость не повлияет.", "На стоимость не меняется."))
        # Multiline & 'или «...»' alternatives are parsed by reference_pairs().
        alt = reference_pairs("Было: «A 5.»\nСтало: «A 5.» или «A 6.»\n", "")
        self.assertEqual(len(alt), 2)
        self.assertTrue(self.bad(alt[1][1], alt[1][2]))

    def test_zero_banned_or_retracted_citations(self):
        targets = [
            ROOT / "skills" / "humanizer-ru" / "SKILL.md",
            ROOT / "README.md",
            ROOT / "README.en.md",
            ROOT / "prompt" / "chat.md",
        ]
        targets += sorted((ROOT / "skills" / "humanizer-ru" / "references").glob("*.md"))
        targets += sorted((ROOT / "site").rglob("*.html"))
        targets += sorted((ROOT / "site").rglob("*.txt"))
        for path in targets:
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                self.assertEqual(find_bad_citations(path.read_text(encoding="utf-8")), [])
        # The check itself can fail on broken/unverified citations.
        self.assertTrue(find_bad_citations("https://antiplagiat.ru/news/kakya-model-ii-detectora-poteryala-tekst/"))
        self.assertTrue(find_bad_citations("See arXiv 9999.99999 for details."))


class DirectoryTest(unittest.TestCase):
    """The tree for Anthropic's plugin directory: the plugin and nothing else, links that resolve."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _repo(self, name, extra=None):
        """A small repository root: the plugin, plus files the directory must not get."""
        root = self.tmp / name
        files = {
            ".claude-plugin/plugin.json": json.dumps({"name": "x", "displayName": "x", "author": {"name": "x"},
                                                      "repository": "https://github.com/o/r.git",
                                                      "icon": "./.claude-plugin/icon.png", "skills": "./skills/"},
                                                     indent=2),
            ".claude-plugin/icon.png": b"\x89PNG\r\n\x1a\n\0",
            "README.md": "# r\n",
            "README.en.md": "# r\n",
            "LICENSE": "MIT\n",
            "skills/humanizer-ru/SKILL.md": "skill\n",
            "AGENTS.md": "names .claude-plugin/icon.png\n",
            "eval/evallib.py": "FAL_KEY\n",
        }
        files.update(extra or {})
        for rel, data in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return root

    def test_real_tree_is_the_plugin_and_nothing_else(self):
        out = self.tmp / "tree"
        names = build_directory.build(out)
        self.assertEqual(build_directory.verify(out), [])
        self.assertEqual({n.split("/")[0] for n in names},
                         {".claude-plugin", "skills", "README.md", "README.en.md", "LICENSE"})
        self.assertEqual(sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()), names)
        self.assertIn("skills/humanizer-ru/SKILL.md", names)
        manifest = build_directory.MANIFEST
        for rel in names:  # the skill and the icon are the repository's own files
            if rel not in build_directory.DOCS and rel != manifest:
                self.assertEqual((out / rel).read_bytes(), (ROOT / rel).read_bytes(), rel)
        # the manifest differs in the two name lines and nowhere else
        was = (ROOT / manifest).read_text(encoding="utf-8").split("\n")
        now = (out / manifest).read_text(encoding="utf-8").split("\n")
        self.assertEqual(len(was), len(now))
        self.assertEqual([b.strip() for a, b in zip(was, now) if a != b],
                         ['"name": "%s",' % build_directory.DIRECTORY_NAME,
                          '"displayName": "%s",' % build_directory.DIRECTORY_NAME])
        self.assertEqual(json.loads("\n".join(now)).get("name"), "humanizer-russian")
        self.assertEqual(json.loads("\n".join(was)).get("name"), "humanizer-ru")  # main keeps its name

    def test_readme_link_to_eval_becomes_absolute(self):
        out = self.tmp / "tree"
        build_directory.build(out)
        for rel in build_directory.DOCS:
            text = (out / rel).read_text(encoding="utf-8")
            self.assertNotIn("](eval/", text)
            self.assertIn("](https://github.com/Vladimir-Human/humanizer-ru/tree/main/eval/)", text)

    def test_links_that_leave_the_tree_become_absolute(self):
        root = self._repo("repo", {"docs/guide.md": "x\n"})
        names = set(build_directory.listing(root))

        def fix(text):
            return build_directory.rewrite_links(text, "README.md", root, "https://github.com/o/r", names)
        self.assertEqual(fix("[a](eval/)"), "[a](https://github.com/o/r/tree/main/eval/)")
        self.assertEqual(fix('[a](docs/guide.md#top "t")'),
                         '[a](https://github.com/o/r/blob/main/docs/guide.md#top "t")')
        for same in ("[a](README.en.md)", "[a](skills/humanizer-ru/)", "[a](https://x.org/p)", "[a](mailto:a@b.c)",
                     "[a](#top)", "```\n[a](eval/)\n```"):
            self.assertEqual(fix(same), same)
        with self.assertRaises(SystemExit):  # a link to nothing is a bug, not something to hide
            fix("[a](no/such/path)")
        with self.assertRaises(SystemExit):  # and so is one that climbs out of the repository
            fix("[a](../repo/README.md)")

    def test_inline_backtick_code_spans_are_skipped_by_link_checks(self):
        # Cross-platform POSIX regression (SKILL.md:104 `![](...)`): inline code spans must never
        # be parsed as markdown/HTML links, while links outside inline code on the same line must be.
        seen = []
        sample = (
            "Пример `![](...)` и ``[x](nope.md)`` и `<img src=\"missing.png\">` и `<a href=\"missing\">x</a>`.\n"
            "Смешанная строка `![](...)` [broken](no-such-file.md) и ``[y](skip.md)`` <a href=\"real-bad.html\">x</a>.\n"
            "Одиночный ` не закрыт: [unmatched](still-checked.md).\n"
            "Ссылка с кодом в подписи: [`code-label`](ok-label.md).\n"
        )
        build_directory.map_links(sample, lambda t: (seen.append(("md", t)), t)[1])
        build_directory._scan_extra_md_links(sample, lambda t: seen.append(("extra", t)))
        self.assertEqual(seen, [
            ("md", "no-such-file.md"),
            ("md", "still-checked.md"),
            ("md", "ok-label.md"),
            ("extra", "real-bad.html"),
        ])

        # Verify end-to-end through build + verify: inline code examples pass, mixed broken links fail.
        root_ok = self._repo("repo_code_ok", {
            "skills/humanizer-ru/SKILL.md": (
                "Не вставляй `![](...)`, ``[x](nope.md)``, `<img src=\"missing.png\">` и `<a href=\"missing\">x</a>`.\n"
            ),
        })
        out_ok = self.tmp / "tree_code_ok"
        build_directory.build(out_ok, root_ok)
        self.assertEqual(build_directory.verify(out_ok, root_ok), [])

        root_bad = self._repo("repo_code_bad", {
            "skills/humanizer-ru/SKILL.md": (
                "Ок `![](...)`, а это [broken](no-such-file.md) и ``[x](nope.md)`` <a href=\"bad.html\">x</a>.\n"
            ),
        })
        out_bad = self.tmp / "tree_code_bad"
        build_directory.build(out_bad, root_bad)
        probs = "\n".join(build_directory.verify(out_bad, root_bad))
        self.assertIn("no-such-file.md", probs)
        self.assertIn("bad.html", probs)
        self.assertNotIn("nope.md", probs)
        self.assertNotIn("...", probs)

    def test_directory_name_replaces_only_the_two_name_fields(self):
        sample = ('{\n  "name": "humanizer-ru",\n  "displayName": "humanizer-ru",\n'
                  '  "author": {"name": "Vladimir-Human", "url": "https://github.com/Vladimir-Human"},\n'
                  '  "homepage": "https://github.com/Vladimir-Human/humanizer-ru"\n}\n')
        got = build_directory.rename_plugin(sample)
        self.assertEqual(got, sample.replace('"name": "humanizer-ru"', '"name": "humanizer-russian"')
                         .replace('"displayName": "humanizer-ru"', '"displayName": "humanizer-russian"'))
        self.assertIn('"author": {"name": "Vladimir-Human"', got)  # the publisher is not renamed
        self.assertIn("Vladimir-Human/humanizer-ru\"", got)  # the links keep the repository name
        with self.assertRaises(SystemExit):  # a manifest without displayName is not guessed at
            build_directory.rename_plugin(sample.replace('  "displayName": "humanizer-ru",\n', ""))
        with self.assertRaises(SystemExit):  # nor one with the key twice
            build_directory.rename_plugin(sample.replace('  "homepage"', '  "name": "again",\n  "homepage"'))

    def test_caches_junk_and_a_folder_with_files_are_refused(self):
        root = self._repo("repo", {"skills/humanizer-ru/scripts/__pycache__/a.cpython-312.pyc": b"x",
                                   "skills/humanizer-ru/scripts/b.pyc": b"x",
                                   "skills/humanizer-ru/SKILL.md.bak": b"bak",
                                   "skills/humanizer-ru/.DS_Store": b"ds",
                                   "skills/humanizer-ru/Thumbs.db": b"tb"})
        out = self.tmp / "tree"
        names = build_directory.build(out, root)
        self.assertFalse(any(n.endswith((".pyc", ".bak", ".DS_Store", "Thumbs.db")) or "__pycache__" in n for n in names))
        self.assertEqual(build_directory.verify(out, root), [])  # the small tree itself is clean
        with self.assertRaises(SystemExit):
            build_directory.build(out, root)  # the folder is no longer empty

    def test_broken_trees_are_caught(self):
        # The check must be able to fail: each defect is put into a clean tree and must be named.
        def write(rel, data):
            return lambda out: (out / rel).write_bytes(data)
        many = {"skills/humanizer-ru/f%d.md" % i: "x\n" for i in range(520)}
        cases = [
            ("a file that is not part of the plugin", None, write("AGENTS.md", b"x\n"), "лишний файл"),
            ("a missing file", None, lambda out: (out / "LICENSE").unlink(), "файла нет"),
            ("CRLF line endings", None, write("README.md", b"# r\r\n"), "CRLF"),
            ("a text file that names the icon", None, write("skills/humanizer-ru/SKILL.md", b"see icon.png\n"), "иконки"),
            ("a link to nowhere", None, write("README.md", b"[a](nowhere.md)\n"), "ссылка"),
            ("an HTML link to nowhere", None, write("README.md", b'<a href="missing.html">x</a>\n'), "ссылка"),
            ("an HTML img to nowhere", None, write("README.md", b'<img src="missing.png">\n'), "ссылка"),
            ("a reference link to nowhere", None, write("README.md", b"[ref]: missing.md\n"), "ссылка"),
            ("a secret string FAL_KEY", None, write("skills/humanizer-ru/SKILL.md", b"use FAL_KEY\n"), "запрещённую строку"),
            ("a network API string urllib.request", None, write("skills/humanizer-ru/SKILL.md", b"urllib.request\n"), "запрещённую строку"),
            ("a changed icon", None, write(".claude-plugin/icon.png", b"\x89PNG\r\n\x1a\n\0\1"), "иконка отличается"),
            ("a manifest that points at a missing folder", None, lambda out: shutil.rmtree(out / "skills"), "ведёт на"),
            ("a manifest with the repository's own name", None,
             lambda out: (out / build_directory.MANIFEST).write_text(
                 (out / build_directory.MANIFEST).read_text(encoding="utf-8").replace(
                     build_directory.DIRECTORY_NAME, "x"), encoding="utf-8"), "не совпадает с plugin.json"),
            ("a manifest that differs by more than the name", None,
             lambda out: (out / build_directory.MANIFEST).write_text(
                 (out / build_directory.MANIFEST).read_text(encoding="utf-8").replace(
                     "https://github.com/o/r.git", "https://example.com/r"), encoding="utf-8"), "не совпадает с plugin.json"),
            ("a file over 256 KiB", {"skills/humanizer-ru/big.md": "x" * (256 * 1024 + 1)}, None, "больше 256"),
            ("a binary that is not the icon", {"skills/humanizer-ru/blob.bin": b"\0\1"}, None, "двоичный"),
            ("more files than the portal screens", many, None, "только первые"),
        ]
        for i, (what, extra, mutate, expected) in enumerate(cases):
            root = self._repo("repo%d" % i, extra)
            out = self.tmp / ("tree%d" % i)
            build_directory.build(out, root)
            if mutate:
                mutate(out)
            self.assertIn(expected, "\n".join(build_directory.verify(out, root)), what)
        # Prose word "subprocesses" must NOT trigger the bare subprocess check.
        root_ok = self._repo("repo_ok", {"README.en.md": "Spawns no subprocesses.\n"})
        out_ok = self.tmp / "tree_ok"
        build_directory.build(out_ok, root_ok)
        self.assertEqual(build_directory.verify(out_ok, root_ok), [])


class CheckScriptsTest(unittest.TestCase):
    TEXTS = {"Встреча 14 ноября в 19:00, билеты от 1200 руб. на сайте https://a.ru/p?id=1 уже в продаже.\n": "t1",
             "Запуск: `npm run build`, отвечает Анна Иванова, телефон +7 999 123-45-67.\n": "t2"}

    def setUp(self):
        self.cf = check_scripts.load("check_facts", check_scripts.SCRIPTS / "check_facts.py")
        self.cp = check_scripts.load("clean_paste", check_scripts.SCRIPTS / "clean_paste.py")

    def test_properties_hold_on_the_real_scripts(self):
        self.assertEqual(check_scripts.properties(self.TEXTS, self.cf, self.cp), {})

    def test_properties_skips_code_spans_and_catches_real_leaks(self):
        # Inline code string literals, trailing fenced code blocks and emoji ZWJ clusters must not
        # be mutated by garbage injection, while real clean_paste leaks on prose are still caught.
        code_texts = {
            "Команда `cmd 'hello'` и текст `run \"arg\"` готовы.\n": "inline_lit",
            "Пример запуска:\n```python\ns = 'abc'\n```\n": "trailing_fence",
            "```python\ns = 'abc'\n```\n": "only_fence",
            "Семья \U0001f468\u200d\U0001f469\u200d\U0001f467 приехала 10 марта.\n": "emoji_zwj",
        }
        self.assertEqual(check_scripts.properties(code_texts, self.cf, self.cp), {})
        # A broken cleaner that fails to strip garbage from prose still fails on mixed prose+code.
        broken_cp = SimpleNamespace(
            clean=lambda t: (t, {}),
            _code_fence_spans=self.cp._code_fence_spans,
            _inline_code_spans=self.cp._inline_code_spans,
        )
        fails = check_scripts.properties({"Команда `cmd 'hello'` и текст готовы.\n": "mixed"}, self.cf, broken_cp)
        self.assertIn("garbage left after clean", fails)

    def test_broken_scripts_are_caught(self):
        # The check must be able to fail: each broken script breaks the property it should.
        fails = check_scripts.properties(self.TEXTS, self.cf, SimpleNamespace(clean=lambda t: (t + "!", {"x": 1})))
        self.assertIn("second clean changes text", fails)
        fails = check_scripts.properties(self.TEXTS, self.cf, SimpleNamespace(clean=lambda t: (t, {})))
        self.assertIn("garbage left after clean", fails)
        noisy = SimpleNamespace(compare=lambda a, b: {
            "errors": [] if a == b else [{"kind": "lost", "what": "число", "detail": "1"}], "checks": []})
        self.assertIn("CRLF changes facts", check_scripts.properties(self.TEXTS, noisy, self.cp))

    def test_holdout5_is_redacted_and_regression_exits_nonzero(self):
        # R-HOLDOUT: holdout5 prose details are never printed to stdout; clean->error fails non-zero.
        self.assertTrue(check_scripts.is_holdout5("holdout5-2026-11-17", "h5_01"))
        self.assertTrue(check_scripts.is_holdout5("results/holdout5-2026-11-17/outputs/ours/h5_01.txt"))
        self.assertFalse(check_scripts.is_holdout5("final3", "m01"))
        self.assertTrue(check_site_facts.is_holdout5("holdout5-2026-11-17/outputs/ours/h5_01.txt"))
        self.assertFalse(check_site_facts.is_holdout5("final3/outputs/ours/m01.txt"))
        fake_rows = [
            ("+", "holdout5-2026-11-17", "ours", "h5_01", "lost", "число", "SECRET_HOLDOUT_SPAN"),
            ("+", "final3", "ours", "m01", "lost", "число", "PUBLIC_SPAN"),
        ]
        buf = io.StringIO()
        with mock.patch.object(check_scripts, "eval_texts", return_value={}), \
                mock.patch.object(check_scripts, "against",
                                  return_value=(fake_rows, collections.Counter({"ours": 2}), collections.Counter(),
                                                collections.Counter({"ours": 2}), 1, 0)), \
                redirect_stdout(buf):
            rc = check_scripts.main(["--against", "main"])
        out = buf.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("PUBLIC_SPAN", out)
        self.assertNotIn("SECRET_HOLDOUT_SPAN", out)
        self.assertIn("holdout5 (redacted, R-HOLDOUT)", out)


if __name__ == "__main__":
    unittest.main()
