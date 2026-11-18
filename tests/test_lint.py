#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Tests of the style linter and browser studio engine (R-LINT-STYLE, R-RULES-EVIDENCE,
#          R-DETECTOR-RISK, R-PASTE): every phrase rule fires on its sign and stays silent on its
#          near miss; quotes and code blocks are skipped; mixed-script homoglyphs, paragraph
#          burstiness, nominalization chains and invisible watermarks are measured accurately;
#          rules.json is portable to JavaScript, site/check/engine.js gives the exact same report
#          as lint_style.py, and RuSlop.cleanPaste matches clean_paste.clean byte-for-byte.
# SCOPE: stdlib unittest; node is optional locally and present on the CI runner.
# LINKS: M-LINT-STYLE; M-SITE-CHECK; V-M-LINT-STYLE; V-M-SITE-CHECK; R-LINT-STYLE;
#        R-RULES-EVIDENCE; R-DETECTOR-RISK; R-PASTE.
# END_MODULE_CONTRACT
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
import unicodedata
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


def _rules():
    return lint_style.load_rules()


# rule id -> (text with the sign, near miss without it); signs from the SKILL.md table + R-RULES-EVIDENCE.
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
    "cleft_imenno": ("Именно комплексный план определил успех сезона.", "Уточните, каким именно способом оплатить заказ."),
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
    "media_metatext": ("Как отмечается в обзоре, спрос вырос.", "Как ожидается, поезд прибудет в полночь."),
    "empty_general": ("Мы предлагаем широкий спектр услуг.", "Мы предлагаем три услуги."),
    "news_stamp": ("На фоне роста тарифов вопрос остаётся актуальным.", "На светлом фоне видна надпись."),
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
    return {h["id"]: h["count"] for h in lint_style.lint(text, _rules())["hits"]}


class RulesFileTest(unittest.TestCase):
    def test_rules_are_portable_to_javascript(self):
        # JS has no Unicode \w and no inline flags; \b is expanded by both engines the same way.
        rules = _rules()
        seen = set()
        for rule in rules["phrases"]:
            self.assertNotIn(rule["id"], seen)
            seen.add(rule["id"])
            self.assertTrue(0 <= rule["sign"] <= 19 and rule["name"] and rule["hint"], rule["id"])
            self.assertTrue(set(rule.get("flags", "i")) <= {"i", "m"}, rule["id"])
            for bad in ("\\w", "\\W", "(?P", "(?i", "(?m", "(?s", "\\\\b", "\\A", "\\Z"):
                self.assertNotIn(bad, rule["re"], rule["id"])
        self.assertEqual(seen, set(CASES), "every rule needs a case here and every case a rule")

    def test_invisible_characters_are_the_ones_clean_paste_removes(self):
        rules = _rules()
        self.assertEqual(sorted(clean_paste.INVISIBLE), rules["metrics"]["invisible"]["codepoints"])

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

    def test_modern_wrappers_labels_citations_and_contrasts(self):
        # Modern chat wrappers (d11, leap-style size footers) vs real author lines.
        self.assertIn("chat_wrapper", ids("Вот подробный, живой и полезный текст для блога."))
        self.assertIn("chat_wrapper", ids("Текст готов.\n\n*(≈270 знаков с пробелами)*"))
        self.assertIn("chat_wrapper", ids("Если хотите, могу сократить текст вдвое."))
        self.assertNotIn("chat_wrapper", ids("Вот письмо от Microsoft."))
        self.assertNotIn("chat_wrapper", ids("Примечание: вход со двора."))
        self.assertNotIn("chat_wrapper", ids("Если хотите, могу доставить заказ в Казань."))
        # Modern paste tokens (Gemini, Perplexity, Copilot UTM, ChatGPT citeturn/PUA) vs ГОСТ academic citations [14, с. 52].
        self.assertIn("paste_garbage", ids("Факт подтверждён [Cite: 8] и https://a.ru/?utm_source=copilot.com"))
        self.assertIn("paste_garbage", ids("Данные отчёта [citation:2], 【12†L4-9】, citeturn0search3 и \uea012\uea02."))
        self.assertNotIn("paste_garbage", ids("См. работу Иванова [14, с. 52], [3; 7] и https://example.org/citeturn0search1/report."))
        # Unicode NFD decomposed й (и+U+0306), ё (е+U+0308), and Russian stress mark U+0301.
        self.assertIn("calque", ids("Компания встретила ключевои\u0306 вызов сезона."))
        self.assertIn("empty_opener", ids("Даваи\u0306те разбере\u0308мся в деталях."))
        self.assertIn("false_contrast", ids("Это не случаи\u0306ность, а дисциплина."))
        stressed = lint_style.lint("Замо\u0301к на двери сто\u0301ит 500 рубле\u0301й.", _rules())
        self.assertEqual(stressed["words"], 6)
        self.assertEqual(stressed["metrics"]["mixed_script"]["value"], 0.0)
        # Numbered/bulleted list items with period inside bold (d11) vs emphasis inside a sentence.
        self.assertIn("bold_label", ids("1. **Питьевая дисциплина.** Мы пили воду каждый час."))
        self.assertNotIn("bold_label", ids("- **Важно** прийти за десять минут до начала."))
        # Antithesis «это не X, а Y» and inflated attention clichés.
        self.assertIn("false_contrast", ids("Это не случайность, а дисциплина."))
        self.assertIn("inflated", ids("Проект оказался в центре внимания и стал предметом пристального внимания."))

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
        rep = lint_style.lint("Первая строка.\n\nВажно отметить, что это вторая.", _rules())
        self.assertEqual(rep["hits"][0]["examples"], [{"text": "Важно отметить", "line": 3}])


class MetricsTest(unittest.TestCase):
    def metric(self, text, key):
        return lint_style.lint(text, _rules())["metrics"][key]

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

    def test_paragraph_cv_and_nominal_chain_are_info_only_diagnostics(self):
        rules = _rules()
        # Four clone paragraphs trigger paragraph_cv, info-only (does not raise level from «нет»).
        para = "Команда обновила складской учёт за три недели и сократила время сборки заказов вдвое."
        clones = "\n\n".join([para, para, para, para])
        rep = lint_style.lint(clones, rules)
        self.assertTrue(rep["metrics"]["paragraph_cv"]["over"])
        self.assertFalse(rep["metrics"]["paragraph_cv"]["scored"])
        self.assertEqual(rep["level"], "нет")
        self.assertIn("Для сведения: в балл не входит.", lint_style.render(rep))
        self.assertIsNone(self.metric("Один абзац.\n\nВторой абзац.", "paragraph_cv")["value"])
        varied_paras = "\n\n".join([
            "В понедельник мы перевезли склад на новую площадку у кольцевой дороги и подключили сканеры.",
            "За первые пять дней кладовщики собрали две тысячи посылок без пересортицы, проверили адресные этикетки, "
            "настроили весовой контроль на трёх столах упаковки и передали отчёт курьерской службе до шести вечера.",
            "Возвраты сократились вдвое уже к пятнице, а очередь машин у ворот исчезла.",
            "В следующем месяце подключим второй терминал выдачи для оптовых клиентов из соседних городов и обновим график смен.",
        ])
        self.assertFalse(self.metric(varied_paras, "paragraph_cv")["over"])

        # Genitive nominalization chains and noun-heavy / verb-starved ratio vs active prose and comma lists.
        bureaucratic = (
            "Программа предусматривает повышение эффективности обслуживания клиентов и укрепление устойчивости развития отрасли. "
            "Отдел ведёт совершенствование организации взаимодействия подразделений и расширение возможностей использования систем "
            "при сохранении прозрачности формирования отчётности для всех участников рынка в текущем квартале."
        )
        self.assertTrue(self.metric(bureaucratic, "nominal_chain")["over"])
        self.assertFalse(self.metric(bureaucratic, "nominal_chain")["scored"])
        self.assertTrue(self.metric(bureaucratic, "nom_to_verb")["over"])
        self.assertFalse(self.metric(bureaucratic, "nom_to_verb")["scored"])
        active_prose = (
            "В понедельник кладовщики привезли стеллажи, собрали три линии упаковки, подключили сканеры штрихкодов "
            "и к вечеру отправили первые двести посылок без задержек, а во вторник курьеры развезли заказы по магазинам."
        )
        self.assertFalse(self.metric(active_prose, "nom_to_verb")["over"])
        comma_list = ("В доме проверили отопление, водоснабжение, освещение, проветривание и озеленение двора " +
                      "после зимнего ремонта крыши и подвала в присутствии старшего по подъезду и инженера участка " * 3)
        self.assertEqual(self.metric(comma_list, "nominal_chain")["value"], 0.0)

    def test_mixed_script_catches_homoglyphs_and_skips_compounds_code_and_urls(self):
        rules = _rules()
        # Latin and Greek lookalikes inside Russian words + NFC-composed Latin+combining + NFD + LLM mid-word BPE splice.
        spoofed = "Новaя cиcтeмa даёт Οпыт, бe\u0301лый, e\u0308лка и Αнализ cиcτeмoи\u0306 в epicентре событий за 100 pуб."
        rep = lint_style.lint(spoofed, rules)
        ms = rep["metrics"]["mixed_script"]
        self.assertTrue(ms["over"])
        self.assertTrue(ms["scored"])
        self.assertEqual(ms["value"], 9.0)
        rendered = lint_style.render(rep)
        self.assertIn("«Новaя» (стр. 1)", rendered)
        self.assertIn("Подозрительный документ", rendered)
        self.assertNotEqual(rep["level"], "нет")
        self.assertEqual(lint_style.lint("бe\u0301лый", rules)["words"], 1)

        # Legitimate hyphenated compounds (incl. Greek α-частица), digits+units, ×, inline code, fences, URLs, emails -> 0 hits!
        clean_tech = (
            "IT-отдел настроил Wi-Fi, SIM-карту, USB-порт, α-частицу, β-версию и 3D-печать: доза 100мг, размер 160х200, 160x200 и 160×200, "
            "код `cиcтeмa`, почта info@сайт.рф, [описание](./cайт.md) и ссылка HTTPS://ru.wikipedia.org/wiki/Система.\n"
            "```\ncиcтeмa = 1\n```"
        )
        self.assertEqual(self.metric(clean_tech, "mixed_script")["value"], 0.0)
        self.assertEqual(self.metric("См. [cиcтeмa](./doc.md).", "mixed_script")["value"], 1.0)
        self.assertFalse(self.metric(clean_tech, "mixed_script")["over"])

    def test_bold_headings_emoji_invisible(self):
        md = "## Раз\n**А** и **Б**\n## Два\n**В** и **Г**\n## Три\nтекст"
        self.assertTrue(self.metric(md, "bold_per_line")["over"])
        self.assertTrue(self.metric(md, "heading_share")["over"])
        self.assertTrue(self.metric("Ура 🚀🚀 ✅", "emoji_per_1000")["over"])
        self.assertEqual(self.metric("сло\u200bво\ufeff\u2061\U000e0100\ufe00\ufe0f\U000e0061\u034f\u061c\u2800\u3164", "invisible")["value"], 11.0)
        self.assertFalse(self.metric("слово\u202f—\u2009тире ☕\ufe0f 1\ufe0f\u20e3 \U0001f3f4\U000e0067\U000e0062\U000e007f", "invisible")["over"])

    def test_levels(self):
        human = ("Футболисты сборной Италии в домашнем матче переиграли команду Армении. Встреча прошла в "
                 "Палермо и завершилась со счётом 9:1. Дублями отметились Иммобиле и Дзаньоло.")
        rep = lint_style.lint(human, _rules())
        self.assertEqual(rep["level"], "нет")
        rep = lint_style.lint(MIXED, _rules())
        self.assertEqual(rep["level"], "много")
        self.assertEqual(rep["metrics"]["invisible"]["value"], 1.0)
        self.assertNotIn("код не проверяется", json.dumps(rep, ensure_ascii=False))
        self.assertIn("Это оценка стиля, а не авторства", lint_style.render(rep))


class CliTest(unittest.TestCase):
    def run_cli(self, *args, text=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "lint_style.py"), *args], input=text,
                              capture_output=True, text=True, encoding="utf-8")

    def test_stdin_is_read_as_utf8_whatever_the_console(self):
        # 4.2.0: through stdin a Windows console (cp1251) turned the text into mojibake: no signs.
        import os
        env = dict(os.environ, PYTHONIOENCODING="cp1251")
        env.pop("PYTHONUTF8", None)
        res = subprocess.run([sys.executable, str(SCRIPTS / "lint_style.py"), "-", "--json"],
                             input="Важно отметить, что данный продукт готов.".encode("utf-8"), capture_output=True, env=env)
        self.assertEqual(res.returncode, 0)
        hit_ids = {h["id"] for h in json.loads(res.stdout.decode("utf-8"))["hits"]}
        self.assertIn("empty_opener", hit_ids)

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
        rules = _rules()
        para = "Команда обновила складской учёт за три недели и сократила время сборки заказов вдвое."
        bureaucratic = (
            "Программа предусматривает повышение эффективности обслуживания клиентов и укрепление устойчивости развития отрасли. "
            "Отдел ведёт совершенствование организации взаимодействия подразделений и расширение возможностей использования систем "
            "при сохранении прозрачности формирования отчётности для всех участников рынка в текущем квартале."
        )
        texts = [hit for hit, _ in CASES.values()] + [miss for _, miss in CASES.values()] + [
            MIXED, "", "Одна фраза.", "Итог\u00a0— рост. Цель\u00a0— выручка. Путь — долгий. Мы — команда.",
            "сло\u200bво\U000e0105\ufe00\ufe0f\U000e0061 😀 ☕\ufe0f 1\ufe0f\u20e3 \U0001f3f4\U000e0067\U000e0062\U000e007f «цитата — важно отметить»",
            " ".join("Мы делаем отличную работу каждый день." for _ in range(8)),
            "Новaя cиcтeмa даёт Οпыт, бe\u0301лый, e\u0308лка и cиcτeмoи\u0306 в epicентре за 100 pуб. при IT-отделе, α-частице и `cиcтeмa` HTTPS://ru.wikipedia.org/wiki/Система.",
            "Компания встретила ключевои\u0306 вызов на е\u0308лке.\r\nДаваи\u0306те разбере\u0308мся: Замо\u0301к сто\u0301ит 500 рубле\u0301й, citeturn0search3 и \uea012\uea02.",
            "\n\n".join([para, para, para, para]),
            bureaucratic,
            "1. **Питьевая дисциплина.** Мы пили воду каждый час.\n\n*(≈120 знаков)*",
            # Astral surrogate-pair emoji in prose + fences, dash_per_1000 / emoji_per_1000 codepoint denominator, and annotate UTF-16 slices.
            "🥐 — 🎂 — \U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f — пекарня 👨‍👩‍👧‍👦 \U000e0100!",
            "```\n🥐🎂 \U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f\n```\n😀cиcтeмa и важно отметить после блока кода.",
            # Python vs JS \s/\S (U+FEFF, U+0085, U+001E), multiline ^/$ (\r, U+2028, U+2029), İ boundary, and score=1.25 tie-to-even render.
            "Важно\ufeffотметить. Первая.\ufeffВторая.\x85Третья.\x1eЧетвёртая. Пятая. Шестая. Седьмая. Восьмая.",
            "https://a.ru/\ufeffcиcтeмa\rВажно отметить\u2028Кроме того, тест\u2029## Заголовок\u2028продолжение\nвторая\nтретья\nчетвёртая",
            "İважно отметить и Уникальный " + " ".join(["дом"] * 399),
        ]
        corpus_dir = ROOT / "eval" / "corpus" / "texts"
        if corpus_dir.exists():
            texts += [p.read_text(encoding="utf-8") for p in sorted(corpus_dir.glob("*.txt"))[::5]]
        script = (
            'const fs = require("node:fs");'
            'const engine = require(process.argv[1]);'
            'const rules = engine.loadRules(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));'
            'const texts = JSON.parse(fs.readFileSync(0, "utf8"));'
            'process.stdout.write(JSON.stringify(texts.map(t => ({rep: engine.lint(t, rules), txt: engine.render(engine.lint(t, rules)), spans: engine.annotate(t, rules)}))));'
        )
        res = subprocess.run([node, "-e", script, str(SITE / "engine.js"), str(SCRIPTS / "rules.json")],
                             input=json.dumps(texts), capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        js = json.loads(res.stdout)
        self.assertEqual(len(js), len(texts))
        for text, item in zip(texts, js):
            got, got_txt, spans = item["rep"], item["txt"], item["spans"]
            want = lint_style.lint(text, rules)
            want_txt = lint_style.render(want)
            with self.subTest(text=text[:40]):
                self.assertEqual(got["hits"], want["hits"])
                self.assertEqual((got["chars"], got["words"], got["level"]), (want["chars"], want["words"], want["level"]))
                self.assertAlmostEqual(got["score"], want["score"], places=2)
                self.assertEqual(got_txt, want_txt)
                for key, m in want["metrics"].items():
                    self.assertEqual(got["metrics"][key]["over"], m["over"], key)
                    self.assertEqual(got["metrics"][key].get("examples"), m.get("examples"), key)
                    if m["value"] is None:
                        self.assertIsNone(got["metrics"][key]["value"], key)
                    else:
                        self.assertAlmostEqual(got["metrics"][key]["value"], m["value"], places=3, msg=key)
                u16 = unicodedata.normalize("NFC", text).replace("\r\n", "\n").encode("utf-16-le")
                utf16_len = len(u16) // 2
                prev_end = 0
                for sp in spans:
                    self.assertTrue(prev_end <= sp["start"] < sp["end"] <= utf16_len, sp)
                    chunk = u16[sp["start"] * 2:sp["end"] * 2].decode("utf-16-le")
                    if sp["kind"] == "mixed":
                        self.assertTrue(lint_style.LAT_RX.search(chunk) and lint_style.CYR_RX.search(chunk), (sp, chunk))
                    elif sp["kind"] == "invisible":
                        self.assertEqual(len(chunk), 1, (sp, chunk))
                    prev_end = sp["end"]

    def test_astral_emoji_fences_and_100kb_redos_budget(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node missing")
        rules = _rules()
        fenced = "```\n🥐🎂\n```\n😀cиcтeмa и важно отметить"
        py_rep = lint_style.lint(fenced, rules)
        self.assertEqual(py_rep["chars"], len(fenced))
        js_check = (
            'const fs = require("node:fs");'
            'const engine = require(process.argv[1]);'
            'const rules = engine.loadRules(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));'
            'const t = JSON.parse(fs.readFileSync(0, "utf8"));'
            'const norm = t.normalize("NFC").replace(/\\r\\n/g, "\\n");'
            'const spans = engine.annotate(t, rules);'
            'process.stdout.write(JSON.stringify({rep: engine.lint(t, rules), slices: spans.map(s => norm.slice(s.start, s.end))}));'
        )
        res = subprocess.run([node, "-e", js_check, str(SITE / "engine.js"), str(SCRIPTS / "rules.json")],
                             input=json.dumps(fenced), capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertEqual(out["rep"]["chars"], py_rep["chars"])
        self.assertEqual(out["slices"], ["cиcтeмa", "важно отметить"])

        # Worst-case 100 KB inputs (long non-@ runs, blank-line runs, unclosed [cite: spaces, tag runs) stay < 2s.
        for probe in ("a" * 100_000, "   \n" * 25_000, "[cite:" + " " * 99_990 + "X", "\U000e0061" * 50_000):
            t0 = time.perf_counter()
            lint_style.lint(probe, rules)
            self.assertLess(time.perf_counter() - t0, 2.0)
        unclosed_code_quote = "```python\na\u200b'" + "\\'" * 25_000 + "\n```"
        t0 = time.perf_counter()
        clean_paste.clean(unclosed_code_quote)
        self.assertLess(time.perf_counter() - t0, 2.0)

    def test_clean_paste_js_matches_python_byte_for_byte(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node missing")
        samples = [
            "",
            "Чистый русский текст без единого следа: IT-отдел, 160x200, 160х200, См. [14, с. 52] и полета\u202f—\u2009м-ра.",
            "Факт:contentReference[oaicite:2]{index=2} и [oaicite:3] и \ue200cite\ue202turn0search3\ue201, citeturn0search3turn1view2, \uea014\uea02 и 【85†L261-269】.",
            "[cite_start]Начало [Cite: 8, 9] конец [cite_end] плюс [citation:1] [attached_file:2] [web:3] [span_2](start_span) [^4^].",
            "Ссылки: https://a.ru/p?utm_source=chatgpt.com&id=1, **https://b.ru/?utm_source=copilot.com**, "
            "https://c.ru/?a=1&amp;utm_source=claude.ai&amp;b=2, www.d.ru/?utm_source=perplexity.ai\u200b, "
            "(https://ru.wikipedia.org/wiki/Колос_(значения)?utm_source=openai), https://[::1/?utm_source=openai, "
            "авторская https://a.ru/?utm_source=newsletter&utm_campaign=may остаётся.",
            "Невидимые: сло\u200bво\u00ad\ufeff\u2060\u2061\uFFF9\U000e0105\ufe00\ufe0f\U000e0061\ue203\u034f\u061c, актуальность\u2800темы, два\u2800\u200bслова и пробел \u3164\uffa0\u115f\u1160 рядом, ZWJ без эмодзи а\u200dб и а\u200cб, "
            "но семейный эмодзи 👨‍👩‍👧, ☕\ufe0f, 1\ufe0f\u20e3, \U0001f3f4\U000e0067\U000e0062\U000e007f и 🏳️‍🌈 целы.",
            "Омоглифы: Новaя cиcтeмa, c\u200bиcт\u00adeмa, Οпыт, Αнализ, ΓОСТ, ΠΡИΜΕΡ, ΦΟΡΜΑ, cтo\u0301ит и NFD cиcтeмoи\u0306 е\u0308лки дают oпыт за 100 pуб., но epicентре, cиcτeмa, IT-отдел, α-частица, вниманія, порядкѣ, "
            "`cиcтeмa [cite: 1]`, user@cиcтeмa.рф и https://example.com/cиcтeмa не тронуты.\r\nВторая строка CRLF.\r\n",
            "```python\nx = 'cиcтeмa [cite: 1] https://a.ru/?utm_source=openai'\ny = 'a\u2062b\\u200b'\n```\nВне блока: `z = 'a\u2062b'` и cиcтeмa [cite: 1].",
            "```\n```\n```js\na = 'cиcтeмa'\n```\n```markdown\nРусский абзац прозы внутри блока чата, где cиcтeмa [cite: 1] и https://a.ru/?utm_source=openai очищаются.\n```",
            "См. HTTPS://a.ru/Кoлoc?utm_source=chatgpt.com, WWW.a.ru/Кoлoc, https://a\uff0fb.ru/?utm_source=chatgpt.com, "
            "cite\u200bturn0search3, [cite:\u200b 1], https://a.ru/?a=1\u200b&utm_source=chatgpt.com, слово\ufe0f\u200dслово и 😀\u200d\u200b.",
            "См. https://example.org/citeturn0search1/report и [Новaя cиcтeмa](./cайт.md) плюс `r = /\u2062/g`.",
            "```js\nconst\u200b strip = /\u2062/g;\nconst label = `a\u2062b`;\n```\n",
        ]
        corpus_dir = ROOT / "eval" / "corpus" / "texts"
        if corpus_dir.exists():
            samples += [p.read_text(encoding="utf-8") for p in sorted(corpus_dir.glob("*.txt"))]
        script = (
            'const fs = require("node:fs");'
            'const engine = require(process.argv[1]);'
            'const samples = JSON.parse(fs.readFileSync(0, "utf8"));'
            'process.stdout.write(JSON.stringify(samples.map(s => {const r = engine.cleanPaste(s); const r2 = engine.cleanPaste(r.text); return {r, r2};})));'
        )
        res = subprocess.run([node, "-e", script, str(SITE / "engine.js")],
                             input=json.dumps(samples), capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        got_list = json.loads(res.stdout)
        for sample, item in zip(samples, got_list):
            got, got2 = item["r"], item["r2"]
            want_text, want_counts = clean_paste.clean(sample)
            with self.subTest(sample=sample[:45]):
                self.assertEqual(got["text"], want_text)
                self.assertEqual(got["counts"], want_counts)
                self.assertEqual(got2["text"], want_text)
                self.assertEqual(got2["counts"], {})


if __name__ == "__main__":
    unittest.main()
