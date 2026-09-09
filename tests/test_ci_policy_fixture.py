import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CiPolicyFixtureTests(unittest.TestCase):
    def test_class_a_fixture_is_blocking_signal(self):
        fixture = os.path.join(ROOT, "tests", "fixtures", "ci-policy-cases.md")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "check_markers.py"),
             "--scan", fixture], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("contentReference", proc.stdout)


if __name__ == "__main__":
    unittest.main()
