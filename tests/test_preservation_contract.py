#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Контракт сохранения защищённых областей в безопасных режимах polish.

Режимы --preserve-markup и --typographic обязаны выполнять обещание:
защищённые области (inline-code с длиной разделителя, fenced-блоки,
YAML-frontmatter, URL, HTML-теги с кавычками атрибутов, ZWJ-кластеры
составных эмодзи) сохраняются байт-в-байт, а список invariants репортит
фактические нарушения сохранения вместо пустого списка при changed:true.
Исторический разрушающий режим (без флагов) не переопределён: он по-
прежнему снимает разметку и типографику — это зафиксировано тестом, чтобы
изменение дефолта не прошло незаметно.

Юнит-часть работает и в sdist (импорт установленного пакета); CLI-часть —
только в репозитории (scripts/ в sdist не входит).
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): интеграционные тесты не запускаются")
for _p in (os.path.join(ROOT, "src"), os.path.join(ROOT, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from humanizer_ru import polish as P  # noqa: E402
from humanizer_ru import protected_regions as PR  # noqa: E402

FAMILY = "\U0001F468\u200d\U0001F469\u200d\U0001F467"
FLAG = "\U0001F3F3\uFE0F\u200d\U0001F308"
URL = "https://example.org/a...b"
TAG = '<a href="x">'

DOC = (
    "---\n"
    'title: "данные..."\n'
    "---\n"
    "## Заголовок — «цитата» **жирный**\u200b\n"
    "Проза \"проза\"... и ссылка %s и %sтекст%s и семья %s и флаг %s\n"
    "```python\n"
    'x = "code..."  # \u200b\n'
    "```\n"
    "Вне `код \"x\"...` конец\u00a0строки\n"
) % (URL, TAG, "</a>", FAMILY, FLAG)


class ProtectedRegionsTests(unittest.TestCase):
    """Единый источник правил защищённых областей."""

    def test_code_span_run_semantics(self):
        self.assertEqual(PR.code_spans("`a b`"), [(1, 4)])
        self.assertEqual(PR.code_spans("``a ` b``"), [(2, 7)])
        self.assertEqual(PR.code_spans("x `abc"), [(3, 6)])

    def test_fenced_convention(self):
        self.assertEqual(
            PR.fenced_line_indices(["т", "```", "к", "```", "т"]), {1, 2, 3})
        self.assertEqual(PR.fenced_line_indices(["a", "```", "b"]), set())
        self.assertEqual(
            PR.fenced_line_indices(["a", "    ```", "b", "    ```"]), set())

    def test_frontmatter(self):
        self.assertEqual(
            PR.frontmatter_line_indices(["---", "k: v", "---", "проза"]),
            {0, 1, 2})
        self.assertEqual(PR.frontmatter_line_indices(["проза", "---"]), set())

    def test_url_and_html_spans(self):
        spans = PR.url_spans("См. %s тут" % URL)
        self.assertEqual(URL, ("См. %s тут" % URL)[spans[0][0]:spans[0][1]])
        tags = PR.html_tag_spans('%sт</a>' % TAG)
        self.assertEqual(TAG, ('%sт</a>' % TAG)[tags[0][0]:tags[0][1]])

    def test_zwj_protection_matches_detector_context(self):
        self.assertEqual(len(PR.zwj_protected_positions(FAMILY)), 2)
        self.assertEqual(len(PR.zwj_protected_positions(FLAG)), 1)
        self.assertEqual(PR.zwj_protected_positions("сло\u200dво"), set())

    def test_remove_invisibles_guards_zwj(self):
        mapping = {"\u200b": "", "\u200d": "", "\u00a0": " "}
        self.assertEqual(PR.remove_invisibles(FAMILY, mapping), FAMILY)
        self.assertEqual(PR.remove_invisibles("сло\u200dво", mapping), "слово")


class SafeModesTests(unittest.TestCase):
    """--preserve-markup и --typographic выполняют обещание сохранения."""

    def test_typographic_preserves_protected_fragments(self):
        out = P.polish(DOC, typographic=True)
        for frag in (URL, TAG, FAMILY, FLAG, '`код "x"...`', 'x = "code..."'):
            self.assertIn(frag, out)
        self.assertIn('title: "данные..."', out)  # frontmatter — данные

    def test_typographic_changes_prose(self):
        # Примеры, которые ДОЛЖНЫ меняться: проза вне защищённых областей.
        out = P.polish(DOC, typographic=True)
        self.assertIn("\u00abпроза\u00bb", out)
        self.assertIn("\u00abцитата\u00bb", out)
        self.assertNotIn("\u200b", out.split("```")[0])
        self.assertIn("конец строки", out)  # NBSP -> пробел в прозе

    def test_preserve_markup_removes_invisibles_in_prose(self):
        out = P.polish(DOC, preserve_markup=True)
        self.assertNotIn("\u200b", out.split("```")[0])
        self.assertIn("конец строки", out)

    def test_preserve_markup_keeps_markup_and_typography(self):
        out = P.polish(DOC, preserve_markup=True)
        self.assertIn("## Заголовок", out)
        self.assertIn("**жирный**", out)
        self.assertIn("\u2014", out)
        self.assertIn("\u00abцитата\u00bb", out)
        self.assertIn('"проза"...', out)  # проза не типографируется

    def test_preserve_markup_protects_code_url_zwj(self):
        out = P.polish(DOC, preserve_markup=True)
        for frag in (URL, TAG, FAMILY, FLAG, '`код "x"...`'):
            self.assertIn(frag, out)
        self.assertIn("x = \"code...\"  # \u200b", out)  # fenced как есть

    def test_modes_idempotent_and_letter_safe(self):
        for kw in ({"typographic": True}, {"preserve_markup": True}):
            out = P.polish(DOC, **kw)
            self.assertEqual(P.polish(out, **kw), out)
            self.assertEqual(P.letters_of(DOC), P.letters_of(out))
            self.assertEqual(P.invariant_problems(DOC, out, **kw), [])

    def test_strip_mode_not_silently_redefined(self):
        # Исторический разрушающий режим сохранён: снимает разметку и
        # русскую типографику, включая ZWJ (документированная граница
        # when_not). Изменение этого поведения должно быть явным.
        out = P.polish(DOC)
        self.assertNotIn("## ", out)
        self.assertNotIn("**", out)
        self.assertNotIn("\u2014", out)
        self.assertNotIn("\u2026", out)
        self.assertNotIn("\u200d", out)

    def test_invariants_report_actual_violations(self):
        clean = P.polish(DOC, typographic=True)
        cases = [
            ("URL", clean.replace(URL, "https://example.org/a\u2026b"), "URL"),
            ("атрибут", clean.replace(TAG, "<a href=\u00abx\u00bb>"), "атрибут"),
            ("ZWJ", clean.replace(FAMILY, FAMILY.replace("\u200d", "")), "ZWJ"),
            ("код", clean.replace('`код "x"...`', '`код "x"\u2026`'), "кода"),
        ]
        for name, broken, needle in cases:
            problems = P.invariant_problems(DOC, broken, typographic=True)
            self.assertTrue(
                any(needle in p for p in problems),
                "нарушение %s не репортится: %s" % (name, problems))
            # Негатив пойман именно сохранением, а не другим инвариантом.
            self.assertFalse(
                any("идемпотентность" in p or "смысловая" in p
                    for p in problems),
                "негатив %s пойман чужим инвариантом" % name)


@SKIP_OUTSIDE
class CliPreservationTests(unittest.TestCase):
    """CLI scripts/polish.py: обещание режима на реальном запуске."""

    POLISH = os.path.join(ROOT, "scripts", "polish.py")

    def _run(self, args, text):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "q.md")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", self.POLISH, path] + args,
                capture_output=True, encoding="utf-8", errors="replace",
                cwd=ROOT)
            after = None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    after = fh.read()
            return proc, path, td, after

    def test_dry_run_typographic_preserves(self):
        proc, _p, _td, _after = self._run(
            ["--dry-run", "--typographic", "--preserve-markup"], DOC)
        self.assertEqual(proc.returncode, 0)
        for frag in (URL, TAG, FAMILY):
            self.assertIn(frag, proc.stdout)

    def test_json_invariants_and_changed(self):
        proc, _p, _td, _after = self._run(
            ["--dry-run", "--typographic", "--json"], DOC)
        env = json.loads(proc.stdout)
        entry = env["files"][0]
        self.assertEqual(env["tool"], "humanizer-polish")
        self.assertTrue(entry["changed"])       # проза приведена
        self.assertEqual(entry["invariants"], [])  # нарушений сохранения нет

    def test_in_place_writes_and_keeps_bak(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "q.md")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(DOC)
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", self.POLISH, path,
                 "--in-place", "--typographic"],
                capture_output=True, encoding="utf-8", errors="replace",
                cwd=ROOT)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(path, encoding="utf-8") as fh:
                after = fh.read()
            with open(path + ".bak", encoding="utf-8") as fh:
                bak = fh.read()
            self.assertEqual(bak, DOC)
            self.assertIn(URL, after)
            self.assertNotIn(path + ".tmp-polish",
                             json.dumps(os.listdir(td)))
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
