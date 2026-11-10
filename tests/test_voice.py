#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Tests of voice_profile.py (R-VOICE): readable features, the distance tells authors apart
#          on real public-domain prose (eval/corpus/voice), differences name what to change, a short
#          sample is flagged, the CLI reads a sample or a saved profile.
# SCOPE: stdlib unittest; the author test reads eval/corpus/voice and is skipped without it.
# LINKS: M-VOICE-PROFILE; V-M-VOICE-PROFILE; R-VOICE.
# END_MODULE_CONTRACT
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "eval" / "voice_profile.py"
VOICE = ROOT / "eval" / "corpus" / "voice"

_spec = importlib.util.spec_from_file_location("voice_profile", SCRIPT)
vp = importlib.util.module_from_spec(_spec)
sys.modules["voice_profile"] = vp
_spec.loader.exec_module(vp)

SHORT = "Пришёл. Увидел. Ушёл. Всё. " * 40
LONG = ("Когда мы приехали в город, который давно хотели увидеть, оказалось, что гостиница, "
        "забронированная заранее, закрыта на ремонт, и пришлось искать другую до самой ночи. ") * 14


class FeaturesTest(unittest.TestCase):
    def test_sentence_length_punctuation_and_yo(self):
        f = vp.features("Это ёлка. Это ель — дерево! Правда?")
        self.assertEqual(f["sentence_mean"], 2.0)  # 2, 3 and 1 words
        self.assertGreater(f["punct"]["dash"], 0)
        self.assertEqual(f["yo_share"], round(1 / (1 + "Это ёлка. Это ель — дерево! Правда?".lower().count("е")), 3))

    def test_same_text_is_at_distance_zero_and_short_sample_is_flagged(self):
        prof = vp.build(LONG)
        self.assertEqual(prof["warning"], "")
        self.assertEqual(vp.distance(prof, LONG)["distance"], 0.0)
        self.assertIn("короткий", vp.build("Две фразы. Всего.")["warning"])

    def test_differences_say_what_to_change(self):
        res = vp.distance(vp.build(SHORT), LONG)
        self.assertTrue(any(line.startswith("фразы длиннее") for line in res["differences"]), res["differences"])
        self.assertGreater(res["distance"], 0.3)


class AuthorTest(unittest.TestCase):
    def test_each_author_sample_is_closest_to_the_same_author(self):
        # Requirement: the distance must tell the author's manner from others' on ~700-word samples.
        if not (VOICE / "index.json").exists():
            self.skipTest("eval/corpus/voice missing")
        sys.path.insert(0, str(ROOT / "eval"))
        import voice_eval  # noqa: E402  (eval helpers: the same split as the gate)
        parts = {slug: voice_eval.parts((VOICE / (slug + ".txt")).read_text(encoding="utf-8"))
                 for slug, _, _ in voice_eval.AUTHORS}
        for a, (sample, _, _) in parts.items():
            dist = {b: vp.distance(vp.build(held), sample)["distance"] for b, (_, held, _) in parts.items()}
            with self.subTest(author=a):
                self.assertEqual(min(dist, key=dist.get), a, dist)


class CliTest(unittest.TestCase):
    def test_stdin_is_read_as_utf8_whatever_the_console(self):
        # 4.2.0: sys.stdin decodes with the console code page on Windows (cp1251).
        import os
        env = dict(os.environ, PYTHONIOENCODING="cp1251")
        env.pop("PYTHONUTF8", None)
        with tempfile.TemporaryDirectory() as d:
            sample = Path(d) / "s.txt"
            sample.write_text(LONG, encoding="utf-8")
            res = subprocess.run([sys.executable, str(SCRIPTS_VOICE := SCRIPT), "distance", str(sample), "-", "--json"],
                                 input=LONG.encode("utf-8"), capture_output=True, env=env)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(json.loads(res.stdout.decode("cp1251"))["-"]["distance"], 0.0)

    def test_build_then_distance_from_profile_or_sample(self):
        with tempfile.TemporaryDirectory() as d:
            sample, text, prof = Path(d) / "s.txt", Path(d) / "t.txt", Path(d) / "p.json"
            sample.write_text(LONG, encoding="utf-8")
            text.write_text(SHORT, encoding="utf-8")
            run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], capture_output=True, text=True, encoding="utf-8")
            built = run("build", str(sample))
            self.assertEqual(built.returncode, 0)
            prof.write_text(built.stdout, encoding="utf-8")
            a = json.loads(run("distance", str(prof), str(text), "--json").stdout)
            b = json.loads(run("distance", str(sample), str(text), "--json").stdout)
            self.assertEqual(a[str(text)]["distance"], b[str(text)]["distance"])
            self.assertEqual(run("distance", str(sample), str(Path(d) / "нет.txt")).returncode, 2)


if __name__ == "__main__":
    unittest.main()
