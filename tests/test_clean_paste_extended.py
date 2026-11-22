#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Extended unit, CLI-hardening, ReDoS and Python<->JS parity tests for clean_paste.py
#          and site/check/engine.js (RuSlop.cleanPaste): 2025-2026 chat leaks, NFC accented Latin
#          homoglyphs, Turkish İ/ı and TextDecoder BOM parity, linear fenced & multi-backtick
#          inline code parsing, flag/keycap/ZWJ fixes, and atomic/safe CLI behavior.
# SCOPE: stdlib unittest; node is optional locally and present on CI.
# LINKS: M-CLEAN-PASTE; M-SITE-CHECK; R-PASTE; R-DETECTOR-RISK; V-M-CLEAN-PASTE; V-M-SITE-CHECK.
# END_MODULE_CONTRACT
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "humanizer-ru" / "scripts"
SITE = ROOT / "site" / "check"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load("clean_paste")
ls = _load("lint_style")


class CleanPasteExtendedTest(unittest.TestCase):
    def test_double_colon_content_reference_and_optional_index(self):
        text, counts = cp.clean(
            "Факт::contentReference[oaicite:0]{index=0} и ещё [oaicite:1]{index=1} и :contentReference[oaicite:2]."
        )
        self.assertEqual(text, "Факт и ещё и.")
        self.assertEqual(counts, {"contentReference": 2, "oaicite": 1})

    def test_nfc_accented_latin_homoglyphs_and_non_russian_guards(self):
        src = "бéлый зáмок, дóм, рýбль, всë, Ëлка, Áрмия, Éсли, Óпыт, Ýтро."
        cleaned, counts = cp.clean(src)
        self.assertEqual(cleaned, "бе\u0301лый за\u0301мок, до\u0301м, ру\u0301бль, всё, Ёлка, А\u0301рмия, Е\u0301сли, О\u0301пыт, У\u0301тро.")
        self.assertEqual(counts, {"homoglyph": 10})
        self.assertEqual(cp.clean(cleaned), (cleaned, {}))
        self.assertEqual(ls.lint(cleaned, ls.load_rules())["metrics"]["mixed_script"]["value"], 0.0)
        # Pure Latin, hyphenated Latin-Cyrillic, non-homoglyph LAT_EXT, U+202F and non-Russian Cyrillic stay intact.
        for untouched in (
            "café и café-бар и üбар и üaбар.",
            "текст\u202fнейросети и 100\u202f₽ и 10\u2009м.",
            "Сербские и казахские буквы: ѕвезда, још, һава, Үлкен.",
        ):
            self.assertEqual(cp.clean(untouched), (untouched, {}), untouched)

    def test_2025_2026_chat_leaks_and_claude_xml_tags(self):
        src = (
            "Факт [cite: 1-3] [cite: 1, 2-4] [cite: 1–3] [citation: 1] [web: 2] [attached_file: 1] "
            "【1, 2†source】 【1-3†L1-5】."
        )
        cleaned, counts = cp.clean(src)
        self.assertEqual(cleaned, "Факт.")
        self.assertEqual(counts, {"cite": 6, "source-token": 2})

        steps = (
            "Инструменты citeturn0product1 citeturn0finance0 citeturn0map2 citeturn0sports1 "
            "citeturn0weather0 citeturn0local3 citeturn0code1 citeturn0calc2 citeturn0browser0."
        )
        cleaned_s, counts_s = cp.clean(steps)
        self.assertEqual(cleaned_s, "Инструменты.")
        self.assertEqual(counts_s, {"oaicite": 9})

        long_pua = "Начало \ue200" + "x" * 350 + "\ue201 конец."
        self.assertEqual(cp.clean(long_pua), ("Начало конец.", {"oaicite": 1}))

        xml = (
            'Claude <antml:cite index="1-1">важный факт</antml:cite> и '
            '<cite index="2-3">другой факт</cite>, но <cite>Война и мир</cite> и '
            '<cite index="1">a <cite index="2">b</cite> c</cite> и <cite index="9">обрыв.'
        )
        cleaned_x, counts_x = cp.clean(xml)
        self.assertEqual(cleaned_x, "Claude важный факт и другой факт, но <cite>Война и мир</cite> и a b c и обрыв.")
        self.assertEqual(counts_x, {"cite": 6})
        self.assertEqual(cp.clean(cleaned_x), (cleaned_x, {}))

    def test_format_chars_strikethrough_utm_flag_and_leading_keycap(self):
        src = "Формат \u206a\u206b\u206c\u206d\u206e\u206f\ufffc и ~~https://a.ru/?utm_source=chatgpt.com~~."
        self.assertEqual(cp.clean(src), ("Формат  и ~~https://a.ru/~~.", {"invisible": 7, "utm": 1}))
        # in_flag stays True across 0xFE0F right after 0x1F3F3; duplicate 0xFE0F still strips.
        flag_ok = "🏳️\U000e0067\U000e0062\U000e007f и 🏳️\u200d🌈"
        self.assertEqual(cp.clean(flag_ok), (flag_ok, {}))
        self.assertEqual(cp.clean("🏳️\ufe0f\U000e0067\U000e0062\U000e007f"), ("🏳️", {"invisible": 4}))
        # Leading \ufe0f\u20e3 is stripped (empty left_c must not match "0123456789#*").
        self.assertEqual(cp.clean("\ufe0f\u20e3"), ("\u20e3", {"invisible": 1}))
        self.assertEqual(cp.clean("1\ufe0f\u20e3"), ("1\ufe0f\u20e3", {}))

    def test_fences_and_multi_backtick_escaped_inline_code(self):
        for untouched in (
            '   ```python\n   x = "cиcтeмa"\n   ```',
            "~~~python\nx = 'cиcтeмa'\n~~~",
            "````python\n```\nx = 'cиcтeмa'\n```\n````",
            "Код ``fn `cиcтeмa` `` и ``const s = `a\u2062b` `` тут.",
            "Код \\\\`cиcтeмa` тут.",
            "Код ```cиcтeмa `x` utm_source=chatgpt.com``` тут.",
        ):
            self.assertEqual(cp.clean(untouched), (untouched, {}), untouched)
        # Escaped backticks are not inline code, so homoglyph inside is repaired.
        self.assertEqual(cp.clean("Напиши \\`cиcтeмa\\`"), ("Напиши \\`система\\`", {"homoglyph": 1}))
        # Info string does not inflate Latin count: short Russian markdown/typescript prose fences are cleaned,
        # while genuine Python code with a Cyrillic string literal stays intact.
        self.assertEqual(cp.clean("```markdown\nДа [cite: 1]\n```"), ("```markdown\nДа\n```", {"cite": 1}))
        self.assertEqual(cp.clean("```typescript\ncиcтeмa 500 р.\n```"), ("```typescript\nсистема 500 р.\n```", {"homoglyph": 1}))
        self.assertEqual(cp.clean("```markdown\ns = 'а\u2062б'\n```"), ("```markdown\ns = 'аб'\n```", {"invisible": 1}))
        self.assertEqual(cp.clean("```python\nx = 'cиcтeмa'\n```\n"), ("```python\nx = 'cиcтeмa'\n```\n", {}))


class CleanPasteCliHardeningTest(unittest.TestCase):
    def run_cli(self, *args, input_bytes=None, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "clean_paste.py"), *args],
            input=input_bytes, capture_output=True, env=env,
        )

    def test_stdin_utf8_under_cp1251_console(self):
        env = dict(os.environ, PYTHONIOENCODING="cp1251")
        env.pop("PYTHONUTF8", None)
        res = self.run_cli("-", input_bytes="Иван\u200b получил 100 руб.\r\n".encode("utf-8"), env=env)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertEqual(res.stdout, "Иван получил 100 руб.\r\n".encode("utf-8"))

    def test_help_and_bad_flag_combinations(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertEqual(self.run_cli("-", "--in-place", input_bytes=b"ok").returncode, 2)
        self.assertEqual(self.run_cli("a.txt", "--in-place", "--check").returncode, 2)
        self.assertEqual(self.run_cli("a.txt", "--encoding", "no-such-enc").returncode, 2)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cp.main(["bad\x00path.txt"]), 2)

    def test_check_json_exit_zero_no_backup_encoding_and_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sample.txt"
            p.write_bytes("Текст\u200b\r\nВторая\r\n".encode("utf-8"))

            # --check reports rc=1 without modifying file or printing text.
            chk = self.run_cli(str(p), "--check")
            self.assertEqual(chk.returncode, 1)
            self.assertEqual(chk.stdout, b"")
            self.assertIn(b"\xe2\x80\x8b", p.read_bytes())

            # --check --json prints JSON summary to stdout.
            chk_j = self.run_cli(str(p), "--check", "--json", "--exit-zero")
            self.assertEqual(chk_j.returncode, 0, chk_j.stderr)
            payload = json.loads(chk_j.stdout.decode("utf-8"))
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["counts"], {"invisible": 1})
            self.assertNotIn("text", payload)

            # Plain --json includes cleaned text.
            plain_j = self.run_cli(str(p), "--json")
            self.assertEqual(plain_j.returncode, 1)
            payload2 = json.loads(plain_j.stdout.decode("utf-8"))
            self.assertEqual(payload2["text"], "Текст\r\nВторая\r\n")

            # --in-place --no-backup rewrites atomically without creating .bak.
            ip = self.run_cli(str(p), "--in-place", "--no-backup", "--exit-zero")
            self.assertEqual(ip.returncode, 0, ip.stderr)
            self.assertEqual(p.read_bytes(), "Текст\r\nВторая\r\n".encode("utf-8"))
            self.assertFalse(Path(str(p) + ".bak").exists())

            # Clean file returns 0.
            self.assertEqual(self.run_cli(str(p), "--check").returncode, 0)

            # --encoding cp1251 reads/writes cp1251 files cleanly.
            win = Path(td) / "win.txt"
            win.write_bytes("Текст [cite: 1].".encode("cp1251"))
            self.assertEqual(self.run_cli(str(win)).returncode, 2)
            enc_res = self.run_cli(str(win), "--encoding", "cp1251", "--in-place", "--no-backup")
            self.assertEqual(enc_res.returncode, 1, enc_res.stderr)
            self.assertEqual(win.read_bytes().decode("cp1251"), "Текст.")

            # Read-only target fails cleanly with rc=2 (never rc=1).
            ro = Path(td) / "ro.txt"
            ro.write_bytes("Текст\u200b".encode("utf-8"))
            os.chmod(ro, stat.S_IREAD)
            try:
                ro_res = self.run_cli(str(ro), "--in-place", "--no-backup")
                # On privileged runners os.replace might succeed; if it fails it must exit 2.
                if ro_res.returncode != 1:
                    self.assertEqual(ro_res.returncode, 2, ro_res.stderr)
            finally:
                os.chmod(ro, stat.S_IWRITE | stat.S_IREAD)

    def test_in_place_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "link.txt"
            p.write_text("Текст\u200b", encoding="utf-8")
            with mock.patch.object(Path, "is_symlink", return_value=True), contextlib.redirect_stderr(io.StringIO()):
                rc = cp.main([str(p), "--in-place"])
            self.assertEqual(rc, 2)
            self.assertIn("\u200b", p.read_text(encoding="utf-8"))


class CleanPasteJsParityAndRedosTest(unittest.TestCase):
    def _require_node(self):
        node = shutil.which("node")
        if not node:
            if os.environ.get("REQUIRE_NODE") == "1":
                self.fail("REQUIRE_NODE=1 is set but node was not found in PATH")
            self.skipTest("node missing")
        return node

    def test_wave2_js_parity_turkish_i_bom_and_new_leaks(self):
        node = self._require_node()
        samples = [
            "Факт::contentReference[oaicite:0]{index=0} и [oaicite:1]{index=1} и :contentReference[oaicite:2].",
            "бéлый зáмок, дóм, рýбль, всë, Ëлка, Áрмия, Éсли, Óпыт, Ýтро, café, café-бар, üбар, üaбар.",
            "Факт [cite: 1-3] [cite: 1, 2-4] [cite: 1–3] [citation: 1] [web: 2] [attached_file: 1] 【1, 2†source】.",
            "citeturn0product1 citeturn0finance0 citeturn0map2 citeturn0sports1 citeturn0weather0 citeturn0local3 citeturn0code1 citeturn0calc2 citeturn0browser0",
            "Начало \ue200" + "a" * 350 + "\ue201 конец.",
            'Claude <antml:cite index="1-1">факт</antml:cite> и <cite index="2-3">ещё</cite> и <cite>HTML</cite> и <cite index="1">a <cite index="2">b</cite> c</cite> и <cite index="9">обрыв.',
            "Формат \u206a\u206b\u206c\u206d\u206e\u206f\ufffc и ~~https://a.ru/?utm_source=chatgpt.com~~",
            "https://example.com/?utm_source=%EF%BB%BFchatgpt.com",
            "[cİte: 1] [cıte: 1] [cİte_start] [oaİcİte:1] cİteturn0search1 [cİtatİon:1] [attached_fİle:1] contentReference[oaİcİte:0]{İndex=0}",
            '<cİte İndex="1">текст</cİte> <antml:cİte İndex="1">х</antml:cİte>',
            "🏳️\U000e0067\U000e0062\U000e007f и 🏳️\ufe0f\U000e0067\U000e0062\U000e007f и \ufe0f\u20e3 и 1\ufe0f\u20e3",
            '   ```python\n   x = "cиcтeмa"\n   ```\n~~~python\nx = \'cиcтeмa\'\n~~~\nКод ``fn `cиcтeмa` `` и \\`cиcтeмa\\`.',
            "```markdown\nДа [cite: 1]\n```\n```typescript\ncиcтeмa 500 р.\n```\n```markdown\ns = 'а\u2062б'\n```",
            "текст\u202fнейросети и ѕвезда и још и һава и Үлкен.",
        ]
        script = (
            'const engine = require(process.argv[1]);'
            'const samples = JSON.parse(require("node:fs").readFileSync(0, "utf8"));'
            'process.stdout.write(JSON.stringify(samples.map(s => {const r = engine.cleanPaste(s); const r2 = engine.cleanPaste(r.text); return {r, r2};})));'
        )
        res = subprocess.run([node, "-e", script, str(SITE / "engine.js")],
                             input=json.dumps(samples), capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        for sample, item in zip(samples, json.loads(res.stdout)):
            want_text, want_counts = cp.clean(sample)
            with self.subTest(sample=sample[:45]):
                self.assertEqual(item["r"]["text"], want_text)
                self.assertEqual(item["r"]["counts"], want_counts)
                self.assertEqual(item["r2"]["text"], want_text)
                self.assertEqual(item["r2"]["counts"], {})
        # Explicit TextDecoder BOM parity check: Python and JS both leave %EF%BB%BFchatgpt.com untouched.
        bom_url = "https://example.com/?utm_source=%EF%BB%BFchatgpt.com"
        self.assertEqual(cp.clean(bom_url), (bom_url, {}))

    def test_adversarial_redos_bounds_python_and_js(self):
        probes = [
            "[cite" * 2000 + "_start]" * 2000,
            "```python\n" * 12000,
            "````python\n" * 5000 + "```\n" * 5000,
            "`` " + "` " * 50000,
            '<cite index="1">' * 10000,
            '"' + ' "a"' * 25000,
        ]
        rules = ls.load_rules()
        for probe in probes:
            t0 = time.perf_counter()
            cp.clean(probe)
            ls.lint(probe, rules)
            self.assertLess(time.perf_counter() - t0, 2.0, probe[:30])
        node = self._require_node()
        js = (
            'const fs = require("node:fs");'
            'const eng = require(process.argv[1]);'
            'const rules = eng.loadRules(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));'
            'const probes = JSON.parse(fs.readFileSync(0, "utf8"));'
            'const times = probes.map(p => {const t0 = performance.now(); eng.cleanPaste(p); eng.lint(p, rules); return (performance.now() - t0) / 1000;});'
            'process.stdout.write(JSON.stringify(times));'
        )
        res = subprocess.run([node, "-e", js, str(SITE / "engine.js"), str(SCRIPTS / "rules.json")],
                             input=json.dumps(probes), capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        for dt in json.loads(res.stdout):
            self.assertLess(dt, 1.0)


if __name__ == "__main__":
    unittest.main()
