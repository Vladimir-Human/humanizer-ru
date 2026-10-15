# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The repository checks pass on the real tree and fail on broken copies; the zip has
#          the layout Claude.ai expects.
# LINKS: V-M-CHECK-REPO; V-M-BUILD-ZIP.
# END_MODULE_CONTRACT
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


check_repo = _load("check_repo")
build_zip = _load("build_zip")


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

    def test_zip_layout(self):
        out = self.tmp / "skill.zip"
        build_zip.build(out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        self.assertIn("humanizer-ru/SKILL.md", names)
        self.assertTrue(all(n.startswith("humanizer-ru/") and n.isascii() for n in names))
        self.assertFalse(any("__pycache__" in n for n in names))


if __name__ == "__main__":
    unittest.main()
