#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Extended unit, parity (Python <-> JS), ReDoS/performance, CLI and guardrail tests
#          for skills/humanizer-ru/scripts/check_facts.py and site/check/facts.js.
# SCOPE: stdlib unittest + node subprocess for site/check/facts.js parity.
# DEPENDS: skills/humanizer-ru/scripts/check_facts.py; site/check/facts.js; node on PATH (required if REQUIRE_NODE=1).
# LINKS: V-M-CHECK-FACTS; V-M-SITE-FACTS.
# END_MODULE_CONTRACT
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "humanizer-ru" / "scripts"
FACTS_PY = SCRIPTS / "check_facts.py"
FACTS_JS = ROOT / "site" / "check" / "facts.js"
NODE = shutil.which("node")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cf = _load("check_facts")
cp = _load("clean_paste")

BATCH_JS = """
const Facts = require(process.argv[1]);
const pairs = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const t0 = performance.now();
const out = pairs.map(([b, a]) => {
    const r = Facts.compare(b, a);
    return {r, txt: Facts.render(r), rec: Facts.receipt(r), hint: Facts.receipt_hint(r)};
});
const dt = (performance.now() - t0) / 1000;
process.stdout.write(JSON.stringify({out, dt}));
"""


def _require_node(tc: unittest.TestCase) -> str:
    if NODE:
        return NODE
    if os.environ.get("REQUIRE_NODE") == "1":
        tc.fail("node is missing while REQUIRE_NODE=1")
    tc.skipTest("node is missing")
    return ""


def _run_js_batch(tc: unittest.TestCase, pairs):
    node = _require_node(tc)
    res = subprocess.run(
        [node, "-e", BATCH_JS, str(FACTS_JS)],
        input=json.dumps(pairs, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8",
    )
    tc.assertEqual(res.returncode, 0, res.stderr)
    return json.loads(res.stdout)


def _kinds(res, bucket="errors"):
    return [x["kind"] for x in res[bucket]]


class ExtendedCorrectnessTest(unittest.TestCase):
    def test_suffix_currency_and_num_rx_guards(self):
        # Suffix currency must not steal ₽ from preceding number into next number.
        self.assertEqual(cf.compare("Кофе 500 ₽ 700 ₽.", "Кофе 500 ₽ и 700 ₽.")["errors"], [])
        self.assertEqual(cf.compare("Цена 500₽-700₽.", "Цена 500–700 ₽.")["errors"], [])
        self.assertIn("unit", _kinds(cf.compare("Билет 500 ₽ и 700 $.", "Билет 500 ₽ и 700 €.")))
        # Sign lookbehind: 10%-20% keeps positive 20%, $20 stays $20, 2024 500 stays two numbers.
        self.assertEqual(cf.compare("Скидка 10%-20%.", "Скидка от 10% до 20%.")["errors"], [])
        self.assertEqual(cf.compare("Цена $20.", "Цена 20 долларов.")["errors"], [])
        self.assertEqual(cf.compare("В 2024 500 заявок.", "В 2024 году 500 заявок.")["errors"], [])
        self.assertIn("lost", _kinds(cf.compare("В 2024 500 заявок.", "Всего 2024500 заявок.")))

    def test_weekday_sreda_and_free_guards(self):
        # «среда» = environment must not fire weekday 3.
        for src in ("Мы бережём окружающую среду.", "Городская среда меняется.", "Работаем с разными средами."):
            self.assertEqual(cf.compare(src, "Экология и обстановка важны.")["errors"], [], src)
        # Calendar/schedule «среда» MUST fire weekday 3.
        for src in (
            "Встреча в среду.",
            "Встреча на следующую среду.",
            "Собираемся по средам.",
            "Среда, 5 ноября: отчёт.",
            "Среда: 9:00 открытие.",
            "- Среда: приём документов.",
        ):
            r = cf.compare(src, "Встреча завтра. 5 ноября 9:00.")
            self.assertIn("lost", _kinds(r), src)
        # Weekday extractors respect free() (URLs/emails do not leak weekdays).
        self.assertEqual(cf.compare("Смотрите https://ex.ru/пн-пт и текст.", "Смотрите https://ex.ru/пн-пт.")["errors"], [])

    def test_dates_hedges_and_bounds(self):
        # dd.mm.yyyy carries hedge_before().
        r_inv = cf.compare("Срок до 15.03.2026.", "Срок после 15.03.2026.")
        self.assertIn("inverted", _kinds(r_inv))
        r_eq = cf.compare("Сдать не позже 15.03.2026.", "Сдать не позднее 15 марта 2026.")
        self.assertEqual(r_eq["errors"], [])
        self.assertEqual(r_eq["checks"], [])
        # date_rx rejects versions/times/URLs and day > 31 (month «мая» stays month, no bogus day date).
        self.assertEqual(cf.extract("Вышла версия 1.2.3 мая.").of("date"), [])
        self.assertEqual(cf.extract("В 14:30 мая нет.").of("date"), [])
        self.assertEqual(cf.extract("См. https://ex.ru/12 мая.").of("date"), [])
        self.assertEqual(cf.extract("Число 35 мая не бывает.").of("date"), [])
        self.assertEqual(cf.compare("Вышла версия 1.2.3 мая.", "Вышла версия 1.2.3 в мае.")["errors"], [])

    def test_preposition_s_vs_seconds(self):
        # Preposition «с», uppercase «С», pages «с. текста» must not be seconds.
        for src, dst in (
            ("Тариф 500 с доставкой.", "Тариф 500 рублей с доставкой."),
            ("Прошло 50 с лишним лет.", "Прошло более 50 лет."),
            ("Цена 500 с НДС.", "Цена 500 рублей с НДС."),
            ("Установлена 1 С.", "Установлена система 1 С."),
            ("В отчёте 52 с. текста.", "В отчёте 52 страницы текста."),
        ):
            r = cf.compare(src, dst)
            self.assertNotIn("unit", _kinds(r), src)
        # True seconds stay seconds.
        for src in ("Пауза 10с.", "Пауза 10 с.", "За 10 с до старта.", "Через 10 с после запуска."):
            r = cf.compare(src, "Пауза 10 мин.")
            self.assertIn("unit", _kinds(r), src)

    def test_names_full_stem_fleeting_compounds_and_free(self):
        # No [:5] false merges (Russian & ASCII Latin).
        for a, b in (
            ("Пришёл Денис.", "Пришли деньги."),
            ("Позвонил Александр.", "Позвонил Алексей."),
            ("Приехала Мария.", "Приехала Марина."),
            ("Ответил Виктор.", "Ответила Виктория."),
            ("Написал Олег.", "Написала Ольга."),
            ("Изучаем Python.", "Изучаем PyTorch."),
            ("Купил MacBook.", "Купил MacMini."),
            ("Работает в Google.", "Работает в Oracle."),
        ):
            self.assertIn("lost", _kinds(cf.compare(a, b)), f"{a} -> {b}")
        self.assertTrue(cf.name_match("iPhone", "iPhones"))
        self.assertFalse(cf.name_match("iPhone", "iPad"))
        # Fleeting vowels, э<->а/е transliteration, Latin plural & 1-char typo (len>=6, prefix 4), hyphenated, -ск-.
        for a, b in (
            ("Позвонил Лев.", "Ждём Льва."),
            ("Поезд в Орёл.", "Поезд из Орла."),
            ("Сказал Пётр.", "Спросили Петра."),
            ("Едем в Ростов-на-Дону.", "Живём в Ростове-на-Дону."),
            ("Купил Android-смартфон.", "Купил смартфон на Android."),
            ("Поставки из Китая.", "Китайский поставщик."),
            ("Клуб «Вашингтон Капиталз» выиграл.", "Клуб «Вашингтон Кэпиталз» выиграл."),
            ("Модель Hyundai Sonaya вышла.", "Модель Hyundai Sonata вышла."),
            ("Продажи Apple выросли.", "Продажи Apples выросли."),
        ):
            self.assertEqual(cf.compare(a, b)["errors"], [], f"{a} -> {b}")
        # Slash-separated names are NOT merged into one person.
        r_slash = cf.compare(
            "Итоги для Анна/Борис: Анна получила 30 000 ₽, Борис получил 50 000 ₽.",
            "Итоги: Анна получила 50 000 ₽, Борис получил 30 000 ₽.",
        )
        self.assertIn("swap", _kinds(r_slash))
        # NAME_RX unconditional free(): URL/email tokens never leak as names.
        self.assertEqual(cf.compare("Отчёт на https://ex.ru/Report готов.", "Отчёт на https://ex.ru/Report готов.")["counts"]["name"], 0)
        self.assertEqual(cf.compare("Пишите на Pay@example.ru срочно.", "Пишите на Pay@example.ru.")["counts"]["name"], 0)

    def test_units_si_it_bold_glued_and_oblique_year(self):
        pairs_ok = [
            ("Расход 15 кВт·ч.", "Расход 15 кВтч."),
            ("Скорость 100 Мбит/с.", "Скорость 100 мегабит в секунду."),
            ("Площадь 45 м².", "Площадь 45 кв. м."),
            ("Объём 12 м³.", "Объём 12 куб. м."),
            ("Мощность 9,9 л. с.", "Мощность 9,9\u00a0л.\u00a0с."),
            ("Цена **500** ₽.", "Цена 500 рублей."),
            ("Опыт 5–летний.", "Опыт 5 лет."),
            ("Бюджет 5млн ₽.", "Бюджет 5 000 000 рублей."),
            ("Диск 500ГБ.", "Диск 500 ГБ."),
            ("Квартира 100кв.м.", "Квартира 100 м²."),
            ("Отчёт в 2025 году.", "Отчёт в 2025 г."),
        ]
        for a, b in pairs_ok:
            self.assertEqual(cf.compare(a, b)["errors"], [], f"{a} -> {b}")
        self.assertIn("unit", _kinds(cf.compare("Диск 500ГБ.", "Диск 500 МБ.")))

    def test_ratios_and_time_cue(self):
        # Ratio cue prevents 1:50 from reading as time 1:50.
        self.assertEqual(cf.compare("Масштаб 1:50 на карте.", "Масштаб 1 к 50 на карте.")["errors"], [])
        self.assertEqual(cf.compare("Формат 9 на 16.", "Формат 9:16.")["errors"], [])
        # Reversed ratio is an error even though both numbers survive.
        self.assertIn("lost", _kinds(cf.compare("Счёт матча 7:2.", "Счёт матча 2:7.")))
        self.assertIn("lost", _kinds(cf.compare("Формат 9 на 16.", "Формат 16:9.")))

    def test_hedges_g1_g2_g3_polarity_and_per_mention(self):
        # «не позднее чем за 14 дней» == «минимум за 14 дней» (same lower bound on lead time).
        r_lead = cf.compare("Предупредите не позднее чем за 14 дней.", "Предупредите минимум за 14 дней.")
        self.assertEqual(r_lead["errors"], [])
        self.assertEqual(r_lead["checks"], [])
        # Comparatives as directional hedges.
        self.assertIn("inverted", _kinds(cf.compare("Срок короче 5 дней.", "Срок дольше 5 дней.")))
        self.assertIn("inverted", _kinds(cf.compare("Билет дешевле 500 ₽.", "Билет дороже 500 ₽.")))
        self.assertIn("inverted", _kinds(cf.compare("Возраст старше 18 лет.", "Возраст моложе 18 лет.")))
        # Per-mention check for singleton hedges (до / после / от).
        r_dup = cf.compare("До 10 мая первый этап и до 10 мая второй.", "До 10 мая первый этап, 10 мая второй.")
        self.assertIn("hedge", _kinds(r_dup, "checks"))

    def test_word_no_cont_and_standalone_sender_and_comp_delta(self):
        # Collectives and «вдвое» do not merge with preceding word-number.
        self.assertEqual(cf.compare("Из двадцати двое пришли.", "Из 20 пришли 2.")["errors"], [])
        self.assertEqual(cf.compare("Сто вдвое меньше.", "100 в 2 раза меньше.")["errors"], [])
        # Standalone receiver + sender fallback.
        r_snd = cf.compare(
            "Анна получила от Бориса 30 000 ₽. Вера получила 50 000 ₽.",
            "Анна получила 50 000 ₽. Вера получила 30 000 ₽.",
        )
        self.assertIn("swap", _kinds(r_snd))
        # Comparison delta is not misbound as a swap.
        r_cmp = cf.compare(
            "Анна получила 30 000 ₽, на 20 000 ₽ меньше Бориса. Борис получил 50 000 ₽.",
            "Борис получил 50 000 ₽, а Анна — 30 000 ₽ (на 20 000 ₽ меньше).",
        )
        self.assertEqual(r_cmp["errors"], [])

    def test_quotes_nested_blockquote_speech_dedup_and_crlf(self):
        # 1-level nested guillemets.
        r_nest = cf.compare("Заголовок: «Завод «Красный октябрь» работает».", "Заголовок: «Завод «Красный октябрь» работает».")
        self.assertEqual(r_nest["errors"], [])
        self.assertEqual(r_nest["counts"]["quote"], 1)
        # Blockquote direct speech after colon.
        r_bq = cf.compare("Директор сказал:\n> «Мы закрываем филиал».", "Директор сказал, что планы изменились.")
        self.assertIn("lost", _kinds(r_bq))
        # QUOTE_DIFF (key, speech) dedup: non-speech first (allows case stem), direct speech second (requires exact).
        r_sp = cf.compare("Слово «свобода» часто звучит. Он сказал: «свобода».", "Слово «свободу» часто звучит. Он промолчал.")
        self.assertIn("lost", _kinds(r_sp))
        # CRLF hyphen direct speech & CRLF service regions.
        self.assertIn("lost", _kinds(cf.compare('- "Мы вернёмся завтра"\r\n', "Он пообещал вернуться.\r\n")))
        r_svc = cf.compare("Вот готовый текст:\r\n\r\nЦена 500 ₽.\r\n\r\nЕсли нужно, могу сократить текст до 100 знаков.", "Цена 500 ₽.")
        self.assertEqual(r_svc["errors"], [])

    def test_negations_newlines_clauses_and_additive_a(self):
        # Negation does not cross newline.
        r_nl = cf.compare("Нет.\nМы храним данные.", "Мы храним данные.")
        self.assertNotIn("inverted", _kinds(r_nl))
        # Discourse «Нет, мы храним данные» does not negate «храним».
        r_disc = cf.compare("Мы не храним данные.", "Нет, мы храним данные.")
        self.assertIn("inverted", _kinds(r_disc))
        # Clause boundary «, но» stops negated_at.
        r_no = cf.compare("Мы не продаём данные.", "Мы не звоним, но продаём данные.")
        self.assertIn("inverted", _kinds(r_no))
        # Additive «, а ещё» is NOT contrast.
        r_add = cf.compare("Мы не берём комиссию, а ещё дарим бонус.", "Мы берём комиссию, а ещё дарим бонус.")
        self.assertIn("inverted", _kinds(r_add))

    def test_cross_syntax_footnotes_abbrevs_tables_html_entities_and_fences(self):
        # Footnotes & abbreviations do not turn sentence-initial words into names.
        self.assertEqual(cf.compare("Конец фразы.[^1] Однако план готов.", "Конец фразы.[^1] План готов.")["errors"], [])
        self.assertEqual(cf.compare("По данным [Иванов, 2023]. Однако план готов.", "По данным [Иванов, 2023]. План готов.")["errors"], [])
        self.assertEqual(cf.compare("Итог: 500 руб., Далее список.", "Итог: 500 ₽, далее список.")["errors"], [])
        self.assertEqual(cf.compare("Живёт в г. Казани.", "Живёт в Казани.")["errors"], [])
        # Markdown table headers & multi-word prose cells vs single-word name cell.
        r_hdr = cf.compare("| Тариф | Цена | Срок |\n| --- | --- | --- |\n| Базовый | 500 ₽ | 1 мес |", "Базовый — 500 ₽ на 1 месяц.")
        self.assertEqual(r_hdr["errors"], [])
        r_cell = cf.compare("| Статус | Действие |\n| --- | --- |\n| Срочно | Немедленно сообщить клиенту |", "Срочно: нужно сразу уведомить клиента.")
        self.assertEqual(r_cell["errors"], [])
        r_name_cell = cf.compare("| Роль | Имя | Ставка |\n| --- | --- | --- |\n| Кассир | Смирнов | 30 000 ₽ |", "Кассир получает 30 000 ₽.")
        self.assertIn("lost", _kinds(r_name_cell))
        # 3-column table item swap (text 3rd column >3 words would fail without right.split("|", 1)[0]).
        r_tbl = cf.compare(
            "| Тариф | Цена | Описание |\n| --- | --- | --- |\n"
            "| Базовый | 500 ₽ | Доступ к архиву и базовым урокам |\n"
            "| Про | 900 ₽ | Полный доступ ко всем материалам и поддержке |",
            "| Тариф | Цена | Описание |\n| --- | --- | --- |\n"
            "| Базовый | 900 ₽ | Доступ к архиву и базовым урокам |\n"
            "| Про | 500 ₽ | Полный доступ ко всем материалам и поддержке |",
        )
        self.assertIn("swap", _kinds(r_tbl))
        # HTML tag before sentence-initial word & HTML entities (&nbsp;, &REG;).
        self.assertEqual(cf.compare("<p>Стоимость 500 ₽.</p>", "<p>Цена 500 ₽.</p>")["errors"], [])
        self.assertEqual(cf.compare("Цена 10&nbsp;000&nbsp;₽.", "Цена 10 000 ₽.")["errors"], [])
        self.assertEqual(cf.compare("Бренд&REG; работает.", "Бренд работает.")["errors"], [])
        # Fenced code (<30% Cyrillic and explicit code tag with Russian strings) masked from quotes/modality/tags; markdown prose fence kept.
        py_block = '```python\nmsg = "привет мир пока всегда"\nprint("<div><b>x</b></div>")\n```'
        self.assertEqual(cf.compare(py_block, py_block)["counts"]["quote"], 0)
        md_block = '```markdown\nОн сказал: «Мы уходим».\n```'
        self.assertEqual(cf.compare(md_block, md_block)["counts"]["quote"], 1)
        # Citations & homoglyphs & flag tag & leading VS16+keycap.
        self.assertEqual(
            cf.compare(
                "Факт 500 ₽ ::contentReference[oaicite:1]{index=1} [oaicite:2]{index=2} citeturn0search1 <antml:cite index=\"1\">x</antml:cite>.",
                "Факт 500 ₽ x.",
            )["errors"],
            [],
        )
        self.assertEqual(cf.compare("\ufe0f\u20e3 500 ₽ 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "500 ₽ 🏴󠁧󠁢󠁥󠁮󠁧󠁿")["errors"], [])

    def test_appositives_bindings(self):
        r_sw = cf.compare(
            "Анна, директор, получила 30 000 ₽, Борис, инженер, получил 50 000 ₽.",
            "Анна, директор, получила 50 000 ₽, Борис, инженер, получил 30 000 ₽.",
        )
        self.assertIn("swap", _kinds(r_sw))
        # Guard: conjunction clause between commas does NOT merge as appositive.
        r_ok = cf.compare(
            "Анна ушла, а потом Борис получил 50 000 ₽.",
            "Анна ушла, а Борис получил 50 000 ₽.",
        )
        self.assertEqual(r_ok["errors"], [])

    def test_guardrails(self):
        # Guardrail 1: U+202F between letters is not normalized away by _strip_tracking.
        self.assertEqual(cf._strip_tracking("а\u202fб"), "а\u202fб")
        # Guardrail 2: non-Russian Cyrillic letters (ѕ, ј, һ, Ү) stay intact.
        self.assertEqual(cf._strip_tracking("ѕјһҮ"), "ѕјһҮ")
        # Guardrail 3: unclosed « does NOT cross newline.
        r_unclosed = cf.compare("Он сказал: «начало\nвторая строка».", "Он сказал: начало\nвторая строка.")
        self.assertEqual(r_unclosed["counts"]["quote"], 0)
        # Guardrail 4: inline `500` -> 500 does not lose the number (only code unquoted check).
        r_ic = cf.compare("Код `500` означает ошибку.", "Код 500 означает ошибку.")
        self.assertEqual(r_ic["errors"], [])
        self.assertIn("unquoted", _kinds(r_ic, "checks"))


class ExtendedParityAndPerfTest(unittest.TestCase):
    def test_py_js_parity_all_extended_cases(self):
        pairs = [
            # #30 #1: facts.js lower() \p{Lt} when len >= 256 (quote body >= 256 chars catches dropping \p{Lt}!)
            ("сказал: «" + "а" * 260 + "ǅ».", "сказал: «" + "а" * 260 + "ǆ»."),
            # P0 & feature matrix
            ("Кофе 500 ₽ 700 ₽.", "Кофе 500 ₽ и 700 ₽."),
            ("Клуб Вашингтон Капиталз выиграл.", "Клуб Вашингтон Кэпиталз выиграл."),
            ("Модель Hyundai Sonaya вышла.", "Модель Hyundai Sonata вышла."),
            ("Продажи Apple выросли.", "Продажи Apples выросли."),
            ("Изучаем Python.", "Изучаем PyTorch."),
            ("Купил MacBook.", "Купил MacMini."),
            ("Скидка 10%-20%.", "Скидка от 10% до 20%."),
            ("В 2024 500 заявок.", "Всего 2024500 заявок."),
            ("Мы бережём окружающую среду.", "Экология важна."),
            ("Встреча в среду.", "Встреча завтра."),
            ("Срок до 15.03.2026.", "Срок после 15.03.2026."),
            ("Сдать не позже 15.03.2026.", "Сдать не позднее 15 марта 2026."),
            ("Тариф 500 с доставкой.", "Тариф 500 рублей с доставкой."),
            ("За 10 с до старта.", "За 10 мин до старта."),
            ("Пришёл Денис.", "Пришли деньги."),
            ("Позвонил Александр.", "Позвонил Алексей."),
            ("Приехала Мария.", "Приехала Марина."),
            ("Позвонил Лев.", "Ждём Льва."),
            ("Едем в Ростов-на-Дону.", "Живём в Ростове-на-Дону."),
            ("Купил Android-смартфон.", "Купил смартфон на Android."),
            ("Поставки из Китая.", "Китайский поставщик."),
            ("Мощность 9,9 л. с.", "Мощность 9,9\u00a0л.\u00a0с."),
            ("Цена **500** ₽.", "Цена 500 рублей."),
            ("Бюджет 5млн ₽ и 500ГБ и 100кв.м.", "Бюджет 5 000 000 ₽, 500 ГБ, 100 м²."),
            ("Счёт матча 7:2.", "Счёт матча 2:7."),
            ("Масштаб 1:50.", "Масштаб 1 к 50."),
            ("Формат 9 на 16.", "Формат 16:9."),
            ("Предупредите не позднее чем за 14 дней.", "Предупредите минимум за 14 дней."),
            ("Срок короче 5 дней.", "Срок дольше 5 дней."),
            ("До 10 мая первый этап и до 10 мая второй.", "До 10 мая первый этап, 10 мая второй."),
            ("Из двадцати двое пришли.", "Из 20 пришли 2."),
            ("Анна получила от Бориса 30 000 ₽. Вера получила 50 000 ₽.", "Анна получила 50 000 ₽. Вера получила 30 000 ₽."),
            ("Анна получила 30 000 ₽, на 20 000 ₽ меньше Бориса. Борис получил 50 000 ₽.",
             "Борис получил 50 000 ₽, а Анна — 30 000 ₽ (на 20 000 ₽ меньше)."),
            ("Анна, директор, получила 30 000 ₽, Борис, инженер, получил 50 000 ₽.",
             "Анна, директор, получила 50 000 ₽, Борис, инженер, получил 30 000 ₽."),
            ("Заголовок: «Завод «Красный октябрь» работает».", "Заголовок: «Завод «Красный октябрь» работает»."),
            ("Директор сказал:\n> «Мы закрываем филиал».", "Директор сказал, что планы изменились."),
            ("Слово «свобода» часто звучит. Он сказал: «свобода».", "Слово «свободу» часто звучит. Он промолчал."),
            ("Мы не храним данные.", "Нет, мы храним данные."),
            ("Мы не берём комиссию, а ещё дарим бонус.", "Мы берём комиссию, а ещё дарим бонус."),
            ("Цена 10&nbsp;000&nbsp;₽. Бренд&REG; работает.", "Цена 10 000 ₽. Бренд работает."),
            ("| Тариф | Цена | Описание |\n| --- | --- | --- |\n| Базовый | 500 ₽ | Доступ к архиву и базовым урокам |\n| Про | 900 ₽ | Полный доступ ко всем материалам |",
             "| Тариф | Цена | Описание |\n| --- | --- | --- |\n| Базовый | 900 ₽ | Доступ к архиву и базовым урокам |\n| Про | 500 ₽ | Полный доступ ко всем материалам |"),
            ("Вот готовый текст:\r\n\r\nЦена 500 ₽.\r\n\r\nЕсли нужно, могу сократить текст до 100 знаков.", "Цена 500 ₽."),
            ("\ufe0f\u20e3 500 ₽ 🏴󠁧󠁢󠁥󠁮󠁧󠁿 ::contentReference[oaicite:1]{index=1}", "500 ₽ 🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        ]
        js_data = _run_js_batch(self, pairs)
        for i, ((b, a), got) in enumerate(zip(pairs, js_data["out"])):
            want = cf.compare(b, a)
            self.assertEqual(got["r"], want, f"pair #{i} compare mismatch: {b!r}")
            self.assertEqual(got["txt"], cf.render(want), f"pair #{i} render mismatch")
            self.assertEqual(got["rec"], cf.receipt(want), f"pair #{i} receipt mismatch")
            self.assertEqual(got["hint"], cf.receipt_hint(want), f"pair #{i} hint mismatch")
        # Explicitly verify #30 #1 quote of >= 256 chars with \p{Lt} passes clean in both Py & JS.
        self.assertEqual(js_data["out"][0]["r"]["errors"], [])
        self.assertEqual(js_data["out"][0]["r"]["checks"], [])

    def test_clean_paste_4way_contract_py_and_js(self):
        # 4-way contract: clean_paste.clean == check_facts._strip_tracking, 0 compare errors in Py & JS.
        samples = [
            "Факт [citation: 1-3] и [web: 2, 4].",
            "Факт <cite index='1-2'>текст</cite>.",
            'Факт <cite index="3-4">текст</cite> и обычный <cite>Война и мир</cite>.',
            "Пришёл Дeниc×2.",
            "Он сказал: «Размер cиcтeмa×2».",
            "Он сказал: «Напиши \\`cиcтeмa\\` сейчас».",
            "🏳️\ufe0f\U000e0067\U000e0062\U000e007f 500 ₽",
        ]
        pairs = []
        for s in samples:
            cleaned, _ = cp.clean(s)
            self.assertEqual(cf._strip_tracking(s, keep_stress=True), cleaned, f"_strip_tracking drift on {s!r}")
            pairs.append((s, cleaned))
        # Plain HTML <cite> must survive both clean_paste and _strip_tracking untouched.
        self.assertIn("<cite>Война и мир</cite>", cp.clean(samples[2])[0])
        self.assertIn("<cite>Война и мир</cite>", cf._strip_tracking(samples[2]))
        js_data = _run_js_batch(self, pairs)
        for i, ((b, a), got) in enumerate(zip(pairs, js_data["out"])):
            want = cf.compare(b, a)
            self.assertEqual(want["errors"], [], f"sample #{i} Py errors: {want['errors']}")
            self.assertEqual(got["r"], want, f"sample #{i} Py/JS mismatch: {b!r}")

    def test_adversarial_redos_and_perf_bounds_py_and_js(self):
        # All #26 adversarial PoCs + #29 P8 / #31 P2 stress inputs.
        adv = [
            "Анна 1" + " и 2" * 150 + " и Борис 3",
            "\U0001F600" + "май " * 9000,
            "x" + " " * 50000 + "x",
            "[cite" * 2000 + "_start]" * 2000,
            "```python\n" * 12000,
            " ".join(f"AB{chr(65 + (i % 26))}" for i in range(1600)) + " " + " ".join("слово" for _ in range(1600)),
            ". ".join(f"Анна Имя{i} получила {100 + i}" for i in range(800)),
            "<div>" * 3000 + "текст" + "</div>" * 3000,
            "Анна получила " + ", ".join(str(1000 + i) for i in range(2000)) + ".",
        ]
        pairs = [(s, s) for s in adv]
        t0 = time.perf_counter()
        py_results = [cf.compare(b, a) for b, a in pairs]
        py_dt = time.perf_counter() - t0
        self.assertLess(py_dt, 4.0, f"Python adversarial batch too slow: {py_dt:.2f}s")
        for i, r in enumerate(py_results):
            self.assertEqual(r["errors"], [], f"adv #{i} had errors on identical input")
        js_data = _run_js_batch(self, pairs)
        self.assertLess(js_data["dt"], 3.0, f"JS adversarial batch too slow: {js_data['dt']:.2f}s")
        for i, (want, got) in enumerate(zip(py_results, js_data["out"])):
            self.assertEqual(got["r"], want, f"adv #{i} Py/JS mismatch")


class ExtendedCLITest(unittest.TestCase):
    def _run_cli(self, args, stdin_bytes=None, env=None):
        return subprocess.run(
            [sys.executable, str(FACTS_PY), *args],
            input=stdin_bytes, capture_output=True, env=env,
        )

    def test_help_anywhere_exits_zero(self):
        for args in (["--help"], ["-h"], ["a.txt", "b.txt", "--help"], ["a.txt", "-h"]):
            res = self._run_cli(args)
            self.assertEqual(res.returncode, 0, args)
            self.assertIn("check_facts.py", res.stdout.decode("utf-8"))

    def test_double_dash_and_errors(self):
        # Reject stdin for both files.
        res_both = self._run_cli(["-", "-"])
        self.assertEqual(res_both.returncode, 2)
        # Reject unknown flag, missing encoding value, bogus encoding, NUL path (ValueError -> rc=2).
        self.assertEqual(self._run_cli(["--bogus", "a", "b"]).returncode, 2)
        self.assertEqual(self._run_cli(["a", "b", "--encoding"]).returncode, 2)
        self.assertEqual(self._run_cli(["a", "b", "--encoding="]).returncode, 2)
        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf):
            self.assertEqual(cf.main(["bad\x00path", "b.txt"]), 2)
        self.assertIn("Не могу прочитать файл", err_buf.getvalue())
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "-leading.txt"
            p2 = Path(td) / "after.txt"
            p1.write_text("Цена 500 ₽.", encoding="utf-8")
            p2.write_text("Цена 500 рублей.", encoding="utf-8")
            # `--` allows filenames starting with `-`.
            res_dd = self._run_cli(["--", str(p1), str(p2)])
            self.assertEqual(res_dd.returncode, 0, res_dd.stderr.decode("utf-8", "replace"))
            # Bad encoding exits 2 cleanly.
            self.assertEqual(self._run_cli([str(p1), str(p2), "--encoding", "no-such-enc"]).returncode, 2)
            # cp1251 files decoded via --encoding cp1251 and --encoding=cp1251.
            p_cp = Path(td) / "win.txt"
            p_cp.write_bytes("Цена 500 руб.".encode("cp1251"))
            self.assertEqual(self._run_cli([str(p_cp), str(p_cp)]).returncode, 2)
            self.assertEqual(self._run_cli([str(p_cp), str(p_cp), "--encoding", "cp1251"]).returncode, 0)
            self.assertEqual(self._run_cli([str(p_cp), str(p_cp), "--encoding=cp1251"]).returncode, 0)
            # --json includes receipt and receipt_hint.
            res_json = self._run_cli([str(p1), str(p2), "--json"])
            self.assertEqual(res_json.returncode, 0)
            payload = json.loads(res_json.stdout.decode("utf-8"))
            self.assertIn("receipt", payload)
            self.assertIn("receipt_hint", payload)
            self.assertEqual(payload["receipt"], cf.receipt(payload))
            self.assertEqual(payload["receipt_hint"], cf.receipt_hint(payload))
            # cp1252 PYTHONIOENCODING must not crash when printing Russian stderr.
            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            res_enc = self._run_cli(["-", "-"], env=env)
            self.assertEqual(res_enc.returncode, 2)
            self.assertNotIn(b"UnicodeEncodeError", res_enc.stderr)


if __name__ == "__main__":
    unittest.main()
