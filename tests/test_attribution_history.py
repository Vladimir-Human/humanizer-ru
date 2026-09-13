"""Attribution must use current reachable history and distinguish missing data."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_attribution.py"
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location("attribution_history", SCRIPT)
    attribution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(attribution)


@unittest.skipUnless(SCRIPT.exists(), "repository attribution gate is not part of sdist")
class AttributionHistoryTests(unittest.TestCase):
    def test_anchor_matches_published_tag_and_is_reachable(self):
        tag = subprocess.run(
            ["git", "rev-parse", attribution.ANCHOR_LABEL + "^{commit}"],
            cwd=ROOT, capture_output=True, text=True)
        if tag.returncode:
            shallow = subprocess.check_output(
                ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True)
            if shallow.strip() == "true":
                self.skipTest("release tag unavailable in shallow checkout")
        self.assertEqual(tag.returncode, 0, tag.stderr)
        self.assertEqual(attribution.ANCHOR, tag.stdout.strip())
        self.assertTrue(attribution.history_available())

    def test_existing_orphan_is_not_available_history(self):
        with patch.object(attribution, "_git", side_effect=[
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 1, "", "")]):
            self.assertFalse(attribution.history_available())

    def test_missing_anchor_in_full_checkout_is_failure(self):
        with patch.object(attribution, "history_available", return_value=False), \
                patch.object(attribution, "_git", return_value=
                             subprocess.CompletedProcess([], 0, "false\n", "")):
            self.assertTrue(attribution.governance_errors())
            self.assertTrue(attribution.commits_after_anchor_errors())

    def test_shallow_history_is_explicitly_unverified(self):
        output = io.StringIO()
        with patch.object(attribution, "history_available", return_value=False), \
                patch.object(attribution, "_git", return_value=
                             subprocess.CompletedProcess([], 0, "true\n", "")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(attribution.governance_errors(), [])
            self.assertEqual(attribution.commits_after_anchor_errors(), [])
        self.assertIn("SKIP", output.getvalue())

    def test_failed_slice_read_is_not_success(self):
        with patch.object(attribution, "history_available", return_value=True), \
                patch.object(attribution, "anchor_slice_count", return_value=None):
            self.assertTrue(attribution.governance_errors())


if __name__ == "__main__":
    unittest.main()
