# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Unit tests for the skill helpers: check_facts.py and clean_paste.py.
# SCOPE: positive and negative cases for each kind of fact and artifact.
# DEPENDS: unittest; scripts loaded by path from skills/humanizer-ru/scripts.
# LINKS: V-M-CHECK-FACTS; V-M-CLEAN-PASTE.
# END_MODULE_CONTRACT
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "humanizer-ru" / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look the module up while the class is built
    spec.loader.exec_module(mod)
    return mod


cf = _load("check_facts")
cp = _load("clean_paste")


def kinds(result):
    return sorted({e["kind"] for e in result["errors"]})


class CheckFactsTest(unittest.TestCase):
    def test_identical_text_is_clean(self):
        text = "Анна получила 30 000 рублей 5 марта. Переводы на карту не принимаем."
        self.assertEqual(cf.compare(text, text)["errors"], [])

    def test_swapped_amounts_between_people(self):
        a = "Анна получила 30 000 рублей. Борис получил 50 000 рублей."
        b = "Анна получила 50 000 рублей. Борис получил 30 000 рублей."
        self.assertIn("swap", kinds(cf.compare(a, b)))

    def test_number_next_to_the_same_word_as_in_the_original_is_not_a_swap(self):
        # final4 q03: the card was flagged even against itself.
        card = "Термос объёмом 750 мл из стали 18/8.\n\n| Модель | Тропа 750 |\n| Материал | Сталь 18/8 |\n"
        edit = "Термос на 750 мл, сталь 18/8.\n\n| Модель | Тропа 750 |\n| Материал | Сталь 18/8 |\n"
        self.assertEqual(cf.compare(card, card)["errors"], [])
        self.assertEqual(cf.compare(card, edit)["errors"], [])

    def test_lost_and_added_numbers(self):
        r = cf.compare("Ссылка действует 30 дней.", "Ссылка действует 45 дней.")
        self.assertIn("lost", kinds(r))
        self.assertIn("added", kinds(r))

    def test_units_and_number_words_are_normalised(self):
        a = "Капучино стоит 240 рублей, доплата 50 руб."
        b = "Капучино теперь 240 ₽. Доплата за овсяное молоко 50 ₽."
        self.assertEqual(cf.compare(a, b)["errors"], [])
        self.assertEqual(cf.compare("Приехали двое.", "Приехали 2 человека.")["errors"], [])

    def test_time_with_zero_minutes_equals_hour(self):
        self.assertEqual(cf.compare("Ждём с 11 до 16.", "Ждём с 11:00 до 16:00.")["errors"], [])

    def test_unit_change_is_an_error(self):
        self.assertIn("unit", kinds(cf.compare("Держит тепло 6 часов.", "Держит тепло 6 минут.")))

    def test_inverted_negation(self):
        r = cf.compare("Сервис не сохраняет исходный текст.", "Сервис сохраняет исходный текст.")
        self.assertIn("inverted", kinds(r))

    def test_negation_moved_inside_sentence_is_fine(self):
        a = "Довольны не все. Переводы на карту не принимаем."
        b = "Не все довольны. Переводы на карту мы не принимаем."
        self.assertEqual(cf.compare(a, b)["errors"], [])

    def test_lost_name(self):
        r = cf.compare("Согласует Марина Ковалёва из отдела кадров.", "Согласует отдел кадров.")
        self.assertIn("lost", kinds(r))

    def test_name_in_other_case_is_kept(self):
        r = cf.compare("Письмо для Олега Петровича.", "Олег Петрович, добрый день.")
        self.assertEqual(r["errors"], [])

    def test_utm_tail_removal_is_not_a_lost_link(self):
        a = "Сайт: https://example.ru/help?utm_source=chatgpt.com"
        b = "Сайт: https://example.ru/help"
        self.assertEqual(cf.compare(a, b)["errors"], [])

    def test_lost_link(self):
        self.assertIn("lost", kinds(cf.compare("Подробнее: https://example.ru/a", "Подробнее на сайте.")))

    def test_dates(self):
        self.assertIn("lost", kinds(cf.compare("Сдача 14 ноября.", "Сдача 28 ноября.")))
        self.assertEqual(cf.compare("Ярмарка 22–23 ноября.", "Ярмарка пройдёт 22 и 23 ноября.")["errors"], [])

    def test_hedge_loss_is_a_check(self):
        r = cf.compare("Процедура длится около 60 минут.", "Процедура длится 60 минут.")
        self.assertEqual(r["errors"], [])
        self.assertTrue(any(c["kind"] == "hedge" for c in r["checks"]))

    def test_year_of_numeric_date(self):
        self.assertIn("lost", kinds(cf.compare("Срок — 01.02.2026.", "Срок — 01.02.2027.")))
        self.assertEqual(cf.compare("Срок — 01.02.2026.", "Срок: 1 февраля 2026.")["errors"], [])

    def test_compound_number_words(self):
        self.assertEqual(cf.compare("В группе двадцать пять человек.", "В группе 25 человек.")["errors"], [])
        self.assertEqual(cf.compare("Привезли сто двадцать коробок.", "Привезли 120 коробок.")["errors"], [])
        self.assertIn("lost", kinds(cf.compare("В группе двадцать пять человек.", "В группе 20 человек.")))

    def test_utm_with_other_params_is_not_a_lost_link(self):
        a = "Сайт: https://example.org/?utm_source=chatgpt.com&id=42"
        b = "Сайт: https://example.org/?id=42"
        self.assertEqual(cf.compare(a, b)["errors"], [])
        a = "Сайт: https://example.org/?id=42&utm_source=openai"
        self.assertEqual(cf.compare(a, b)["errors"], [])

    def test_lost_author_utm_tag_is_reported(self):
        # R-FACTS + R-PASTE: the author's campaign tags are part of the link.
        a = "Записаться: https://shop.example.ru/sale?utm_source=newsletter&utm_campaign=autumn"
        b = "Записаться: https://shop.example.ru/sale"
        self.assertIn("lost", kinds(cf.compare(a, b)))

    def test_modality_shift_is_a_check(self):
        r = cf.compare("Пользователь может увидеть старые данные. Субботник запланирован на апрель.",
                       "Пользователь увидит старые данные. Субботник пройдёт в апреле.")
        details = " ".join(c["detail"] for c in r["checks"] if c["kind"] == "modality")
        self.assertIn("может", details)
        self.assertIn("план", details)
        same = "Иногда кэш отдаёт старые данные."
        self.assertFalse([c for c in cf.compare(same, same)["checks"] if c["kind"] == "modality"])

    def test_scope_attribution_and_intensifiers_are_checks(self):
        def details(a, b):
            return " ".join(c["detail"] for c in cf.compare(a, b)["checks"] if c["kind"] == "modality")
        self.assertIn("риск", details("Есть риск переделок.", "Работу придётся переделывать."))
        self.assertIn("один из", details("Это один из лучших курсов.", "Это лучший курс."))
        self.assertIn("по данным", details("По словам врача, это безопасно.", "Это безопасно."))
        self.assertIn("главный", details("Температура — ключевой фактор.", "Температура — главный фактор."))
        self.assertEqual(details("Это самый тёплый месяц.", "Это самый тёплый месяц года."), "")

    def test_lost_html_tags_are_errors(self):
        before = "<ul>\n<li><strong>Диагностика</strong> бесплатно</li>\n<li>Запчасти клиента</li>\n</ul>"
        after = "<p>Диагностика бесплатно, запчасти клиента принимаем.</p>"
        res = cf.compare(before, after)
        lost = [e["detail"] for e in res["errors"] if e["what"] == "разметка"]
        self.assertIn("<li> 2 → 0", lost)
        self.assertNotIn("<strong> 1 → 0", lost)  # emphasis may be removed on purpose: a check
        self.assertIn("<strong> 1 → 0", [c["detail"] for c in res["checks"] if c["what"] == "разметка"])
        same = cf.compare(before, before.replace("бесплатно", "бесплатна"))
        self.assertFalse([e for e in same["errors"] if e["what"] == "разметка"])
        # Autolinks are not tags; tag names are case-insensitive.
        links = "Пишите <hr@lapka.ru> или <https://lapka.ru/a>, <https://lapka.ru/b>."
        self.assertFalse([e for e in cf.compare(links, "Пишите hr@lapka.ru.")["errors"] if e["what"] == "разметка"])
        upper = cf.compare("<UL><LI>Раз</LI><LI>Два</LI></UL>", "<p>Раз, два</p>")
        self.assertIn("<li> 2 → 0", [e["detail"] for e in upper["errors"] if e["what"] == "разметка"])
        # Angle brackets in prose and a single tag are not markup to protect.
        self.assertFalse([e for e in cf.compare("Тег <b> жирный", "Тег жирный")["errors"] if e["what"] == "разметка"])

    def test_polite_pronoun_and_line_break_are_not_facts(self):
        self.assertEqual(cf.compare("Поздравляем Вас и желаем Вашего успеха.", "Поздравляем и желаем успеха.")["errors"], [])
        self.assertEqual(cf.compare("Вариант 3\n\nНоябрь — время книг.", "Ноябрь — время книг.")["errors"], [])
        self.assertIn("lost", kinds(cf.compare("Сдача 3 ноября.", "Сдача в ноябре.")))
        self.assertIn("lost", kinds(cf.compare("Офис в Вашингтоне закрыт.", "Офис закрыт.")))

    def test_changed_quote_is_lost(self):
        # Issue #264: the quoted words changed, the report was empty.
        r = cf.compare("Сообщение: «готов к запуску».", "Сообщение: «уже запущен».")
        self.assertIn({"kind": "lost", "what": "цитата", "detail": "«готов к запуску»"}, r["errors"])
        r = cf.compare("Он ответил: \"Пока не готов\".", "Он ответил: «Готов».")
        self.assertIn("lost", kinds(r))
        r = cf.compare("«Мы готовы», — сказал Иван.", "«Мы почти готовы», — сказал Иван.")
        self.assertIn("lost", kinds(r))
        r = cf.compare("«Готовы ли вы?» — спросил Иван.", "«Вы готовы?» — спросил Иван.")
        self.assertIn("lost", kinds(r))

    def test_rephrased_words_in_quotes_inside_a_phrase_are_a_check(self):
        # Terms, irony and examples inside a phrase: rephrasing them is a check, not an error.
        for a, b in (("Всегда откладывали «начать с понедельника»?", "Всё откладывали на понедельник?"),
                     ("Я заменил её на «хочу быть ближе к продукту» — так честнее.", "Я написал, что хочу к продукту.")):
            r = cf.compare(a, b)
            self.assertEqual(r["errors"], [], a)
            self.assertIn(("lost", "цитата"), {(c["kind"], c["what"]) for c in r["checks"]}, a)

    def test_quote_marks_and_case_endings_may_change(self):
        # "…" → «…» is the skill's own typography; a quoted name may take another case.
        self.assertEqual(cf.compare("Он сказал: \"Запуск в среду\".", "Он сказал: «Запуск в среду».")["errors"], [])
        r = cf.compare("Кофейня «Зерно» открылась.", "Открыли кофейню «Зерна» на углу.")
        self.assertEqual([e for e in r["errors"] if e["what"] == "цитата"], [])
        r = cf.compare("Договор с ООО \"Ромашка\" продлён.", "Договор с ООО «Ромашка» продлили.")
        self.assertEqual(r["errors"], [])

    def test_unquoted_and_added_quotes_are_checks(self):
        r = cf.compare("Это так называемый «умный дом».", "Это умный дом.")
        self.assertEqual(r["errors"], [])
        self.assertIn("unquoted", {c["kind"] for c in r["checks"]})
        r = cf.compare("Директор одобрил план.", "Директор сказал: «План хороший».")
        self.assertIn(("added", "цитата"), {(c["kind"], c["what"]) for c in r["checks"]})

    def test_inch_marks_are_not_quotes(self):
        r = cf.compare("Монитор 27\" и ноутбук 15\" в наличии.", "В наличии монитор 27\" и ноутбук 15\".")
        self.assertEqual(r["counts"]["quote"], 0)
        self.assertEqual(r["errors"], [])

    def test_cli_exit_codes(self):
        tmp = ROOT / "tests" / "_tmp_cf"
        tmp.mkdir(exist_ok=True)
        try:
            (tmp / "a.txt").write_text("Цена 240 рублей.", encoding="utf-8")
            (tmp / "b.txt").write_text("Цена 260 рублей.", encoding="utf-8")
            run = lambda x, y: subprocess.run([sys.executable, str(SCRIPTS / "check_facts.py"), str(x), str(y)],
                                              capture_output=True).returncode
            self.assertEqual(run(tmp / "a.txt", tmp / "a.txt"), 0)
            self.assertEqual(run(tmp / "a.txt", tmp / "b.txt"), 1)
            self.assertEqual(run(tmp / "a.txt", tmp / "nope.txt"), 2)
            (tmp / "q1.txt").write_text("Сообщение: «готов к запуску».", encoding="utf-8")
            (tmp / "q2.txt").write_text("Сообщение: «уже запущен».", encoding="utf-8")
            self.assertEqual(run(tmp / "q1.txt", tmp / "q2.txt"), 1)
        finally:
            for p in tmp.glob("*"):
                p.unlink()
            tmp.rmdir()


class CleanPasteTest(unittest.TestCase):
    def test_content_reference(self):
        text, counts = cp.clean("Рост заявок :contentReference[oaicite:3]{index=3}. Дальше.")
        self.assertEqual(text, "Рост заявок. Дальше.")
        self.assertEqual(counts, {"contentReference": 1})

    def test_source_tokens_and_cite(self):
        text, _ = cp.clean("Факт【4:2†source】 и ещё [cite: 1, 2] факт.")
        self.assertEqual(text, "Факт и ещё факт.")

    def test_utm_tail_keeps_link(self):
        # R-PASTE: the assistant's utm_source tail goes, the link and its other parameters stay.
        text, _ = cp.clean("См. https://a.ru/p?utm_source=chatgpt.com и https://b.ru/q?id=1&utm_source=openai.")
        self.assertEqual(text, "См. https://a.ru/p и https://b.ru/q?id=1.")
        text, _ = cp.clean("https://a.ru/p?utm_source=chatgpt.com&id=1")
        self.assertEqual(text, "https://a.ru/p?id=1")

    def test_author_utm_tags_stay(self):
        # R-PASTE (2026-10-21): utm tags the author put in a newsletter are not chat leftovers.
        src = "Записаться: https://shop.example.ru/sale?utm_source=newsletter&utm_campaign=autumn"
        self.assertEqual(cp.clean(src), (src, {}))
        text, counts = cp.clean("https://example.org/?utm_campaign=a&id=42&utm_source=openai#top")
        self.assertEqual(text, "https://example.org/?utm_campaign=a&id=42#top")
        self.assertEqual(counts["utm"], 1)
        self.assertEqual(cp.clean(text), (text, {}))

    def test_invisible_characters(self):
        text, counts = cp.clean("при\u200bвет\u00ad мир\ufeff")
        self.assertEqual(text, "привет мир")
        self.assertEqual(counts["invisible"], 3)

    def test_emoji_joiner_and_nbsp_survive(self):
        family = "\U0001F468\u200d\U0001F469\u200d\U0001F467"
        src = "Семья " + family + " и 240\u00a0₽"
        text, counts = cp.clean(src)
        self.assertEqual(text, src)
        self.assertEqual(counts, {})

    def test_clean_text_untouched(self):
        src = "Обычный текст — с тире, «ёлочками» и ссылкой https://a.ru/x?id=2."
        self.assertEqual(cp.clean(src), (src, {}))


if __name__ == "__main__":
    unittest.main()
