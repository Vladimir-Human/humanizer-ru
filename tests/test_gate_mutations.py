#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_gate_mutations.py — гейты убивают подтверждённых мутантов.

Таблица «мутант -> проверяемое свойство -> ожидаемый отказ -> факт»:

| Мутант | Свойство | Ожидаемый отказ | Факт |
|---|---|---|---|
| shutil.which -> None (node «исчез») | паритет JS-стороны обязателен | check() возвращает ошибку, main rc!=0 | test_no_node_is_fail_not_skip |
| CASES[assistants_source][0] -> '(a+)+$' | исключение ReDoS содержательное, не именное | имя в nested_patterns(), гейт rc!=0 | test_pattern_swap_under_exempt_name |
| гомоглифная таблица только латиница->кириллица | оператор мутации меняет вход | _mut != CLEAN, selftest ловит | test_homoglyph_* |
| [\p{M}] в классе переноса \w | паритет Python/JS по фактической семантике | py_to_js не содержит \p{M} | test_word_class_without_M |
"""
import contextlib
import io
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): гейты живут в scripts/ и demo/")
if REPO_ONLY:
    for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src"),
               os.path.join(ROOT, "demo")):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    import check_demo_parity as CDP  # noqa: E402
    import check_markers as cm  # noqa: E402
    import check_perf_regex as CPR  # noqa: E402
    import check_robustness as CRB  # noqa: E402
    import generate_js_rules as G  # noqa: E402
else:  # pragma: no cover — sdist без scripts/
    CDP = cm = CPR = CRB = G = None


@SKIP_OUTSIDE
class NoNodeRefusalTests(unittest.TestCase):
    """Мутант: node «исчез» из окружения (shutil.which -> None)."""

    def test_no_node_is_fail_not_skip(self):
        saved = CDP.shutil.which
        CDP.shutil.which = lambda *a, **k: None
        try:
            errors = CDP.check(CDP.ROOT)
        finally:
            CDP.shutil.which = saved
        self.assertTrue(any("node недоступен" in e for e in errors),
                        "непроверенная JS-сторона не дала ошибку гейта")

    def test_no_node_main_refuses(self):
        saved = CDP.shutil.which
        CDP.shutil.which = lambda *a, **k: None
        try:
            rc = CDP.main([])
        finally:
            CDP.shutil.which = saved
        self.assertNotEqual(rc, 0, "main вернул 0 при непроверенной JS-стороне")


@SKIP_OUTSIDE
class NameExemptMutantTests(unittest.TestCase):
    """Мутант: квадратичный паттерн под именем из прежнего белого списка."""

    def test_pattern_swap_under_exempt_name(self):
        saved = cm.CASES["assistants_source"]
        cm.CASES["assistants_source"] = ["(a+)+$"] + list(saved[1:])
        try:
            self.assertIn("assistants_source", CPR.nested_patterns(),
                          "исключение по имени пережило подмену паттерна")
        finally:
            cm.CASES["assistants_source"] = saved

    def test_clean_signatures_still_safe(self):
        self.assertEqual(CPR.nested_patterns(), [],
                         "содержательное правило дало ложную тревогу на "
                         "чистых сигнатурах")

    def test_bounded_probe_ok(self):
        ok, _msg = CPR.bounded_probe(timeout_s=60)
        self.assertTrue(ok)


@SKIP_OUTSIDE
class HomoglyphMutationTests(unittest.TestCase):
    """Мутант: оператор мутации не меняет применимый вход."""

    def test_homoglyph_changes_cyrillic_clean(self):
        rng = random.Random(20260907)
        self.assertNotEqual(CRB._mut("homoglyph", CRB.CLEAN, rng), CRB.CLEAN,
                            "гомоглифная мутация не меняет кириллический вход")

    def test_homoglyph_mutant_creates_no_hits(self):
        rng = random.Random(20260907)
        self.assertFalse(CRB._hits(CRB._mut("homoglyph", CRB.CLEAN, rng)))

    def test_every_operator_changes_its_applicable_input(self):
        rng = random.Random(20260907)
        probes = _mutation_probes()
        for kind, probe in probes.items():
            self.assertNotEqual(CRB._mut(kind, probe, rng), probe,
                                "оператор %s не меняет применимый вход" % kind)


def _mutation_probes():
    return {
        "homoglyph": CRB.CLEAN,
        "punctuation": "Источник: живой текст без артефактов.",
        "linebreak": CRB.CLEAN,
        "nfc-nfkc": "и\u0306 живой текст без артефактов.",
        "translit": "живой текст code слово",
        "word-smart": 'живой текст "цитата" слово',
        "html-convert": "живой текст & слово",
        "zero-width": CRB.CLEAN,
        "telegram-pdf": "живой  текст с двойным пробелом",
    }

    def test_canonical_samples_still_detected(self):
        samples = CRB.json_samples()
        pos = sum(1 for s in samples.values() if CRB._hits(s))
        self.assertEqual(pos, len(samples))


@SKIP_OUTSIDE
class GeneratorClassTests(unittest.TestCase):
    """Мутант: возврат \p{M} в класс переноса Python \w."""

    def test_word_class_without_M(self):
        src, flags = G.py_to_js("\\w+")
        self.assertEqual(src, "[\\p{L}\\p{N}_]+")
        self.assertIn("u", flags)
        src2, _flags2 = G.py_to_js("\\w \\W")
        self.assertNotIn("\\p{M}", src2)

    def test_service_worker_precaches_cleaner_assets(self):
        sw = G.build_sw("markers", "index", "engine", "sample",
                        "css", "favicon", "manifest", "rules", "cleaner")
        static = json.loads(sw.split("const STATIC = ", 1)[1].split(";", 1)[0])
        self.assertEqual(set(static), {
            "./", "./index.html", "./brand.css", "./markers.js",
            "./engine.js", "./sample.js", "./favicon.svg", "./manifest.json",
            "./cleaner-rules.js", "./cleaner.js",
        })
        self.assertEqual(len(static), len(set(static)))

    def test_service_worker_digest_covers_every_precached_asset(self):
        values = ["markers", "index", "engine", "sample", "css", "favicon",
                  "manifest", "rules", "cleaner"]
        baseline = G.build_sw(*values)
        for i, value in enumerate(values):
            changed = list(values)
            changed[i] = value + " changed"
            mutated = G.build_sw(*changed)
            self.assertNotEqual(baseline.split("\n", 3)[1],
                                mutated.split("\n", 3)[1],
                                "service-worker cache digest ignores asset %d" % i)

    def test_service_worker_generation_hashes_disk_assets(self):
        # Isolated output proves main() passes the disk contents to build_sw;
        # mutating only build_sw's argument test would miss a forgotten read.
        assets = ("index.html", "engine.js", "sample.js", "brand.css",
                  "favicon.svg", "manifest.json", "cleaner-rules.js",
                  "cleaner.js")
        with tempfile.TemporaryDirectory(prefix="demo-sw-") as directory:
            root = Path(directory)
            for name in assets:
                (root / name).write_bytes(name.encode("utf-8"))
            registry = root / "markers.v1.json"
            registry.write_bytes(b'{"count": 0}')
            with mock.patch.multiple(G, HERE=directory, IN=str(registry),
                                     OUT=str(root / "markers.js")), \
                    mock.patch.object(G, "build_js", return_value="markers"), \
                    contextlib.redirect_stdout(io.StringIO()):
                G.main()
                baseline = (root / "sw.js").read_text(encoding="utf-8")
                for name in assets:
                    with self.subTest(asset=name):
                        (root / name).write_bytes((name + " changed").encode("utf-8"))
                        G.main()
                        mutated = (root / "sw.js").read_text(encoding="utf-8")
                        self.assertNotEqual(baseline.splitlines()[1],
                                            mutated.splitlines()[1])
                        (root / name).write_bytes(name.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
