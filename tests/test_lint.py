#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Tests of the style linter (R-LINT-STYLE): every phrase rule fires on a sign from the
#          SKILL.md table and stays silent on its near miss; quotes and code blocks are skipped;
#          metrics, levels and the CLI; rules.json is portable to JavaScript, and site/check/engine.js
#          gives the same report as lint_style.py on the same texts (run through node when present).
# SCOPE: stdlib unittest; node is optional locally and present on the CI runner.
# LINKS: M-LINT-STYLE; V-M-LINT-STYLE; R-LINT-STYLE.
# END_MODULE_CONTRACT
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "humanizer-ru" / "scripts"
SITE = ROOT / "site" / "check"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


lint_style = _load("lint_style")
clean_paste = _load("clean_paste")
RULES = lint_style.load_rules()

# rule id -> (text with the sign, near miss without it); signs from the SKILL.md table.
CASES = {
    "chat_wrapper": ("Конечно! Вот текст поста:\n\nОткрылись.", "Конечно, мы придём в субботу."),
    "assistant_context": ("По имеющейся у меня информации, магазин работает.", "По имеющейся информации, магазин работает."),
    "paste_garbage": ("Ссылка: https://a.ru/?utm_source=chatgpt.com", "Ссылка: https://a.ru/?utm_source=vk"),
    "empty_opener": ("Важно отметить, что срок — 10 дней.", "Важно: срок 10 дней."),
    "false_contrast": ("Это не просто кофе, а ритуал.", "Это кофе, а не чай."),
    "ne_tolko_no_i": ("Курс не только для новичков, но и для опытных.", "Курс только для новичков."),
    "inflated": ("Логистика играет ключевую роль в бизнесе.", "Логистика занимает два дня."),
    "symbolism": ("Отель расположен в самом сердце города.", "Отель расположен в центре города."),
    "unique": ("Это уникальный шанс.", "Это единственный шанс."),
    "kantselyarit": ("Данный товар осуществляет нагрев.", "По данным Росстата, цены выросли на 5%."),
    "yavlyaetsya": ("Москва является столицей.", "Москва — столица."),
    "calque": ("Компания столкнулась с новыми вызовами.", "Число вызовов скорой выросло."),
    "odnako_comma": ("Цена выросла. Однако, спрос не упал.", "Цена выросла. Однако спрос не упал."),
    "significance_tail": ("Магазин открылся, подчёркивая важность района.", "Магазин открылся в среду."),
    "anonymous_authority": ("Эксперты отмечают рост цен.", "Экономист Иван Петров отмечает рост цен."),
    "triad": ("Это быстро, удобно и надёжно.", "Это быстро и удобно."),
    "moral_ending": ("Сезон шёл трудно.\n\nТаким образом, мы закрыли сезон.", "Мы закрыли сезон таким образом, чтобы сохранить людей."),
    "teaser": ("Результат? Рост продаж на 20%.", "Результат: рост продаж на 20%."),
    "metatext": ("В этой статье мы рассмотрим пять способов.", "В этой статье пять способов."),
    "empty_general": ("Мы предлагаем широкий спектр услуг.", "Мы предлагаем три услуги."),
    "connector_opener": ("Цены выросли.\n\nКроме того, сократился выбор.", "Цены выросли, кроме того, сократился выбор."),
    "bold_label": ("**Важно:** приходите к 10:00.", "Приходите к **10:00**."),
    "hedge_cascade": ("Это может потенциально снизить риск.", "Это может снизить риск."),
    "business_pathos": ("Мы рады сообщить об открытии.", "Мы открылись 5 мая."),
    "template_politeness": ("Надеемся на понимание!", "Просим прощения за шум."),
}

MIXED = ("Конечно! Вот вариант текста:\r\n\r\n## Наш Сервис\r\n\r\n**Важно:** сервис — это не просто инструмент, "
         "а помощник 🚀. Он быстрый, удобный и надёжный.\r\n\r\n```\r\nВажно отметить — код не проверяется\r\n```\r\n\r\n"
         "Кроме того, «важно отметить» в кавычках не считается\u200b.\r\n\r\nНадеюсь, это поможет! ✅")


def ids(text):
    return {h["id"]: h["count"] for h in lint_style.lint(text, RULES)["hits"]}


class RulesFileTest(unittest.TestCase):
    def test_rules_are_portable_to_javascript(self):
        # JS has no Unicode \w and no inline flags; \b is expanded by both engines the same way.
        seen = set()
        for rule in RULES["phrases"]:
            self.assertNotIn(rule["id"], seen)
            seen.add(rule["id"])
            self.assertTrue(0 <= rule["sign"] <= 19 and rule["name"] and rule["hint"], rule["id"])
            self.assertTrue(set(rule.get("flags", "i")) <= {"i", "m"}, rule["id"])
            for bad in ("\\w", "\\W", "(?P", "(?i", "(?m", "(?s", "\\\\b", "\\A", "\\Z"):
                self.assertNotIn(bad, rule["re"], rule["id"])
        self.assertEqual(seen, set(CASES), "every rule needs a case here and every case a rule")

    def test_invisible_characters_are_the_ones_clean_paste_removes(self):
        self.assertEqual(sorted(clean_paste.INVISIBLE), RULES["metrics"]["invisible"]["codepoints"])

    def test_site_copy_of_rules_is_identical(self):
        if not (SITE / "rules.json").exists():
            self.skipTest("site/check not built yet")
        self.assertEqual((SITE / "rules.json").read_bytes(), (SCRIPTS / "rules.json").read_bytes())


class PhraseRulesTest(unittest.TestCase):
    def test_each_rule_fires_on_its_sign_and_not_on_the_near_miss(self):
        for rid, (hit, miss) in CASES.items():
            with self.subTest(rule=rid):
                self.assertIn(rid, ids(hit))
                self.assertNotIn(rid, ids(miss))

    def test_upper_case_and_yo_variants(self):
        self.assertIn("empty_opener", ids("ДАВАЙТЕ РАЗБЕРЁМСЯ."))
        self.assertIn("empty_opener", ids("давайте разберемся"))

    def test_cyrillic_word_boundary(self):
        # "является" inside a longer word is not the word; Python and JS see the same boundary
        self.assertNotIn("yavlyaetsya", ids("Непоявляется такое слово."))
        self.assertNotIn("kantselyarit", ids("Бизнес-данные выросли."))

    def test_quotes_and_code_blocks_are_not_checked(self):
        self.assertEqual(ids("Он сказал: «Важно отметить, что мы рады сообщить»."), {})
        self.assertEqual(ids('Штамп "важно отметить" встречается часто.'), {})
        self.assertEqual(ids("```\nВажно отметить\n```"), {})
        self.assertIn("empty_opener", ids("Важно отметить, что «это» так."))

    def test_examples_carry_line_numbers(self):
        rep = lint_style.lint("Первая строка.\n\nВажно отметить, что это вторая.", RULES)
        self.assertEqual(rep["hits"][0]["examples"], [{"text": "Важно отметить", "line": 3}])


class MetricsTest(unittest.TestCase):
    def metric(self, text, key):
        return lint_style.lint(text, RULES)["metrics"][key]

    def test_dashes_ranges_and_line_start_dialogue_are_not_counted(self):
        self.assertEqual(self.metric("Цены 10–20 ₽.\n— Привет, — сказал он.", "dash_per_1000")["value"],
                         round(1000 / len("Цены 10–20 ₽.\n— Привет, — сказал он."), 3))
        dashy = "Мы — команда. Цель — рост. Путь — долгий. Итог — успех."
        self.assertTrue(self.metric(dashy, "dash_per_1000")["over"])

    def test_metronome_rhythm_needs_enough_sentences(self):
        same = " ".join("Мы делаем отличную работу каждый день." for _ in range(8))
        self.assertTrue(self.metric(same, "sentence_cv")["over"])
        self.assertTrue(self.metric(same, "same_opener_share")["over"])
        self.assertIsNone(self.metric("Одна фраза. Вторая фраза.", "sentence_cv")["value"])
        varied = ("Да. Мы открылись в мае после долгого ремонта старого здания на углу. Ждём. "
                  "Цены остались прежними, кроме кофе. Заходите! Работаем с девяти утра до десяти вечера без выходных. "
                  "Парковка есть. Можно с собакой, если она на поводке.")
        self.assertFalse(self.metric(varied, "sentence_cv")["over"])

    def test_bold_headings_emoji_invisible(self):
        md = "## Раз\n**А** и **Б**\n## Два\n**В** и **Г**\n## Три\nтекст"
        self.assertTrue(self.metric(md, "bold_per_line")["over"])
        self.assertTrue(self.metric(md, "heading_share")["over"])
        self.assertTrue(self.metric("Ура 🚀🚀 ✅", "emoji_per_1000")["over"])
        self.assertEqual(self.metric("сло\u200bво\ufeff", "invisible")["value"], 2.0)
        self.assertFalse(self.metric("слово", "invisible")["over"])

    def test_levels(self):
        human = ("Футболисты сборной Италии в домашнем матче переиграли команду Армении. Встреча прошла в "
                 "Палермо и завершилась со счётом 9:1. Дублями отметились Иммобиле и Дзаньоло.")
        rep = lint_style.lint(human, RULES)
        self.assertEqual(rep["level"], "нет")
        rep = lint_style.lint(MIXED, RULES)
        self.assertEqual(rep["level"], "много")
        self.assertEqual(rep["metrics"]["invisible"]["value"], 1.0)
        self.assertNotIn("код не проверяется", json.dumps(rep, ensure_ascii=False))
        self.assertIn("Это оценка стиля, а не авторства", lint_style.render(rep))


class CliTest(unittest.TestCase):
    def run_cli(self, *args, text=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "lint_style.py"), *args], input=text,
                              capture_output=True, text=True, encoding="utf-8")

    def test_json_exit_codes_and_bad_input(self):
        res = self.run_cli("-", "--json", text="Важно отметить, что всё готово.")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(json.loads(res.stdout)["hits"][0]["id"], "empty_opener")
        self.assertEqual(self.run_cli("-", "--max-score", "1", text="Важно отметить, что всё готово.").returncode, 1)
        self.assertEqual(self.run_cli(str(ROOT / "нет-такого-файла.txt")).returncode, 2)


class JsParityTest(unittest.TestCase):
    def test_engine_js_gives_the_same_report(self):
        node = shutil.which("node")
        if not node or not (SITE / "cli.js").exists():
            self.skipTest("node or site/check/cli.js missing")
        texts = [hit for hit, _ in CASES.values()] + [miss for _, miss in CASES.values()] + [
            MIXED, "", "Одна фраза.", "Итог\u00a0— рост. Цель\u00a0— выручка. Путь — долгий. Мы — команда.", "сло\u200bво 😀 «цитата — важно отметить»",
            " ".join("Мы делаем отличную работу каждый день." for _ in range(8))]
        res = subprocess.run([node, str(SITE / "cli.js"), str(SCRIPTS / "rules.json")], input=json.dumps(texts),
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        js = json.loads(res.stdout)
        self.assertEqual(len(js), len(texts))
        for text, got in zip(texts, js):
            want = lint_style.lint(text, RULES)
            with self.subTest(text=text[:40]):
                self.assertEqual(got["hits"], want["hits"])
                self.assertEqual((got["chars"], got["words"], got["level"]), (want["chars"], want["words"], want["level"]))
                self.assertAlmostEqual(got["score"], want["score"], places=1)
                for key, m in want["metrics"].items():
                    self.assertEqual(got["metrics"][key]["over"], m["over"], key)
                    if m["value"] is None:
                        self.assertIsNone(got["metrics"][key]["value"], key)
                    else:
                        self.assertAlmostEqual(got["metrics"][key]["value"], m["value"], places=2, msg=key)


if __name__ == "__main__":
    unittest.main()
