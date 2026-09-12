"""Atomic UTF-8 writes preserve permissions and leave failures reversible."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "src").is_dir():
    sys.path.insert(0, str(ROOT / "src"))
from humanizer_ru import polish, text_layer


class AtomicTextWriteTests(unittest.TestCase):
    def test_exact_bytes_and_permissions(self):
        for module in (polish, text_layer):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as td:
                target = Path(td) / "draft.txt"
                target.write_bytes(b"original")
                if os.name != "nt":
                    target.chmod(0o600)
                text = "RU: \u0442\u0435\u043a\u0441\u0442\r\nEN: text\n"
                module._safe_write_text(target, text)
                self.assertEqual(target.read_bytes(), text.encode("utf-8"))
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                backup = Path(td) / "draft.txt.bak"
                module._safe_write_text(backup, "original")
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
                self.assertEqual({p.name for p in Path(td).iterdir()},
                                 {"draft.txt", "draft.txt.bak"})

    def test_replace_failure_keeps_original_and_removes_temp(self):
        for module in (polish, text_layer):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as td:
                target = Path(td) / "draft.txt"
                target.write_bytes(b"original")
                with mock.patch.object(module.os, "replace", side_effect=OSError("busy")):
                    with self.assertRaises(OSError):
                        module._safe_write_text(target, "replacement")
                self.assertEqual(target.read_bytes(), b"original")
                self.assertEqual(list(Path(td).iterdir()), [target])

    @unittest.skipIf(os.name == "nt", "POSIX symlink fixtures; Windows needs elevated symlink rights")
    def test_symlink_target_or_parent_is_rejected(self):
        for module in (polish, text_layer):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                target = root / "original.txt"
                target.write_bytes(b"original")
                link = root / "link.txt"
                link.symlink_to(target)
                alias = root / "alias"
                alias.symlink_to(root, target_is_directory=True)
                for destination in (link, alias / target.name):
                    with self.assertRaises(OSError):
                        module._safe_write_text(destination, "replacement")
                self.assertEqual(target.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
