# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The repository checks pass on the real tree and fail on broken copies; the zip has
#          the layout Claude.ai expects; the tree for the plugin directory is the plugin and
#          nothing else, and its check can fail.
# LINKS: V-M-CHECK-REPO; V-M-BUILD-ZIP; V-M-BUILD-DIRECTORY; V-M-CHECK-SCRIPTS.
# END_MODULE_CONTRACT
import importlib.util
import json
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

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


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for rel in ("skills", ".claude-plugin", ".codex-plugin"):
            shutil.copytree(ROOT / rel, self.tmp / rel)
        shutil.copy(ROOT / "CHANGELOG.md", self.tmp / "CHANGELOG.md")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_real_tree_is_clean(self):
        self.assertEqual(check_repo.check(ROOT), [])

    def test_version_mismatch_is_caught(self):
        p = self.tmp / ".claude-plugin" / "plugin.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["version"] = "0.0.1"
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("plugin.json" in x for x in check_repo.check(self.tmp)))

    def test_missing_reference_is_caught(self):
        (self.tmp / "skills" / "humanizer-ru" / "references" / "patterns.md").unlink()
        self.assertTrue(any("patterns.md" in x for x in check_repo.check(self.tmp)))

    def test_crlf_and_invisible_are_caught(self):
        p = self.tmp / "skills" / "humanizer-ru" / "references" / "examples.md"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n", 1) + "\u200b".encode("utf-8"))
        problems = check_repo.check(self.tmp)
        self.assertTrue(any("CRLF" in x for x in problems))
        self.assertTrue(any("невидимые" in x for x in problems))

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

    def test_zip_layout(self):
        out = self.tmp / "skill.zip"
        build_zip.build(out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        self.assertIn("humanizer-ru/SKILL.md", names)
        self.assertTrue(all(n.startswith("humanizer-ru/") and n.isascii() for n in names))
        self.assertFalse(any("__pycache__" in n for n in names))


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
            ".claude-plugin/plugin.json": json.dumps({"name": "x", "repository": "https://github.com/o/r.git",
                                                      "icon": "./.claude-plugin/icon.png", "skills": "./skills/"}),
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
        for rel in names:  # the skill, the manifest and the icon are the repository's own files
            if rel not in build_directory.DOCS:
                self.assertEqual((out / rel).read_bytes(), (ROOT / rel).read_bytes(), rel)

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

    def test_caches_and_a_folder_with_files_are_refused(self):
        root = self._repo("repo", {"skills/humanizer-ru/scripts/__pycache__/a.cpython-312.pyc": b"x",
                                   "skills/humanizer-ru/scripts/b.pyc": b"x"})
        out = self.tmp / "tree"
        names = build_directory.build(out, root)
        self.assertFalse(any("pyc" in n or "__pycache__" in n for n in names))
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
            ("a changed icon", None, write(".claude-plugin/icon.png", b"\x89PNG\r\n\x1a\n\0\1"), "иконка отличается"),
            ("a manifest that points at a missing folder", None, lambda out: shutil.rmtree(out / "skills"), "ведёт на"),
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


class CheckScriptsTest(unittest.TestCase):
    TEXTS = {"Встреча 14 ноября в 19:00, билеты от 1200 руб. на сайте https://a.ru/p?id=1 уже в продаже.\n": "t1",
             "Запуск: `npm run build`, отвечает Анна Иванова, телефон +7 999 123-45-67.\n": "t2"}

    def setUp(self):
        self.cf = check_scripts.load("check_facts", check_scripts.SCRIPTS / "check_facts.py")
        self.cp = check_scripts.load("clean_paste", check_scripts.SCRIPTS / "clean_paste.py")

    def test_properties_hold_on_the_real_scripts(self):
        self.assertEqual(check_scripts.properties(self.TEXTS, self.cf, self.cp), {})

    def test_broken_scripts_are_caught(self):
        # The check must be able to fail: each broken script breaks the property it should.
        fails = check_scripts.properties(self.TEXTS, self.cf, SimpleNamespace(clean=lambda t: (t + "!", {"x": 1})))
        self.assertIn("second clean changes text", fails)
        fails = check_scripts.properties(self.TEXTS, self.cf, SimpleNamespace(clean=lambda t: (t, {})))
        self.assertIn("garbage left after clean", fails)
        noisy = SimpleNamespace(compare=lambda a, b: {
            "errors": [] if a == b else [{"kind": "lost", "what": "число", "detail": "1"}], "checks": []})
        self.assertIn("CRLF changes facts", check_scripts.properties(self.TEXTS, noisy, self.cp))


if __name__ == "__main__":
    unittest.main()
