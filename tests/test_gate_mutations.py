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
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src"),
           os.path.join(ROOT, "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_demo_parity as CDP  # noqa: E402
import check_markers as cm  # noqa: E402
import check_perf_regex as CPR  # noqa: E402
import check_robustness as CRB  # noqa: E402
import generate_js_rules as G  # noqa: E402


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


class GeneratorClassTests(unittest.TestCase):
    """Мутант: возврат \p{M} в класс переноса Python \w."""

    def test_word_class_without_M(self):
        src, flags = G.py_to_js("\\w+")
        self.assertEqual(src, "[\\p{L}\\p{N}_]+")
        self.assertIn("u", flags)
        src2, _flags2 = G.py_to_js("\\w \\W")
        self.assertNotIn("\\p{M}", src2)


if __name__ == "__main__":
    unittest.main()
