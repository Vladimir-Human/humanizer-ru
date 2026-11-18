#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The fact-check page (site/sverka) reads an edit the same way as the eval and the skill:
#          notes are cut like evallib.split_notes, facts are compared like check_facts.py, and the
#          prompt it copies is prompt/chat.md (R-SITE-FACTS, R-NOTES-NOT-TEXT, R-PORTABLE-PROMPT).
# SCOPE: runs the page's JavaScript through node; skips when node is missing.
# DEPENDS: node; site/sverka/notes.js; site/check/facts.js; scripts/check_site_facts.py; eval/evallib.py.
# LINKS: V-M-SITE-SVERKA; V-M-SITE-FACTS.
# END_MODULE_CONTRACT
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "scripts"))
import evallib as lib  # noqa: E402

NODE = shutil.which("node")
SPLIT_JS = """
const {splitNotes} = require(process.argv[1]);
const cases = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map(([a, s]) => splitNotes(a, s))));
"""


@unittest.skipUnless(NODE, "node is missing")
class SiteNotesTest(unittest.TestCase):
    def test_notes_js_cuts_like_split_notes_on_every_saved_answer(self):
        import check_site_facts as csf
        cases = [(a, s) for _, s, a in csf.eval_pairs() if "---" in a]
        cases += [  # the hand cases of the eval tests: prose notes, rewritten section, quotes, emoji
            ("Завтрак в «Крошке».\n\n---\n\nУбрал обёртку, длина 683 знака.", "Вот текст:\n---\nЗавтрак.\n---\nЧто учтено"),
            ("Вход свободный.\n---\n- Заходите каждый день с 9:00 до 21:00.", "Вход свободный.\n---\n- Работаем ежедневно."),
            ("Путь был непростой.\n---\n- Убрал «который многому меня научил».", "Это был путь, который многому меня научил."),
            ("Текст.\n---\n" + "Убрал повтор. " * 100, "Текст."),
            ("Текст.\n---\n" + "🙂" * 700 + " убрал", "Текст."),
            ("Без заметок.", ""),
            ("Текст.\n---\n- Что именно понравилось?", ""),
        ]
        res = subprocess.run([NODE, "-e", SPLIT_JS, str(ROOT / "site" / "sverka" / "notes.js")],
                             input=json.dumps(cases, ensure_ascii=False), capture_output=True, text=True,
                             encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr)
        got = json.loads(res.stdout)
        want = [list(lib.split_notes(a, s)) for a, s in cases]
        bad = [i for i, (w, g) in enumerate(zip(want, got)) if w != g]
        self.assertEqual(len(got), len(want))
        self.assertGreater(len(cases), 300)
        self.assertEqual(bad, [], "first: %r" % (cases[bad[0]][0][-200:] if bad else ""))


@unittest.skipUnless(NODE, "node is missing")
class SiteFactsTest(unittest.TestCase):
    def test_facts_js_gives_the_same_report_as_check_facts(self):
        # All hand-made and generated cases of test_scripts.py and every 15th saved eval answer; the full set
        # (about 4700 pairs, 0 mismatches) is `python scripts/check_site_facts.py`.
        import check_site_facts as csf
        self.assertEqual(csf.main(["--every", "15", "--show", "3"]), 0)

    def test_facts_js_wave3_item_swaps_and_100kb_bounds(self):
        js_code = """
        const Facts = require(process.argv[1]);
        const t0 = performance.now();
        const swap = Facts.compare("На выбор два тарифа: Базовый — 500 ₽ и Про — 900 ₽.", "На выбор два тарифа: Базовый — 900 ₽ и Про — 500 ₽.");
        const reord = Facts.compare("На выбор два тарифа: Базовый — 500 ₽ и Про — 900 ₽.", "На выбор два тарифа: Про — 900 ₽ и Базовый — 500 ₽.");
        const big = "1, ".repeat(30000) + "1";
        const bigRes = Facts.compare(big, big);
        const sAnd = "Анна 1" + " и Анна 1".repeat(5000) + " и Борис и Вера 2";
        const sAndRes = Facts.compare(sAnd, sAnd);
        const sComma = Array.from({length: 2000}, (_, i) => `товар${i} ${10 + i}`).join(", ");
        const sCommaRes = Facts.compare(sComma, sComma);
        const sSlot0 = "чай 5, " + Array.from({length: 1200}, (_, i) => `кофе сорта${i} ${10 + i}`).join(", ");
        const sSlot0Res = Facts.compare(sSlot0, sSlot0);
        const unclosed = "```python\\n'" + "\\\\'".repeat(35000) + "\\n```";
        const unclosedRes = Facts.compare(unclosed, unclosed);
        const unclosedDbl = "```python\\n\\\"" + "\\\\\\\"".repeat(35000) + "\\n```";
        const unclosedDblRes = Facts.compare(unclosedDbl, unclosedDbl);
        const dt = (performance.now() - t0) / 1000;
        process.stdout.write(JSON.stringify({
            swap: swap.errors, reord: reord.errors,
            bigErrs: bigRes.errors.length + sAndRes.errors.length + sCommaRes.errors.length + sSlot0Res.errors.length + unclosedRes.errors.length + unclosedDblRes.errors.length,
            dt
        }));
        """
        res = subprocess.run([NODE, "-e", js_code, str(ROOT / "site" / "check" / "facts.js")],
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr)
        got = json.loads(res.stdout)
        self.assertEqual([e["kind"] for e in got["swap"]], ["swap", "swap"])
        self.assertEqual(got["reord"], [])
        self.assertEqual(got["bigErrs"], 0)
        self.assertLess(got["dt"], 2.0)


if __name__ == "__main__":
    unittest.main()
