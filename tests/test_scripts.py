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

    def test_polite_pronoun_and_line_break_are_not_facts(self):
        self.assertEqual(cf.compare("Поздравляем Вас и желаем Вашего успеха.", "Поздравляем и желаем успеха.")["errors"], [])
        self.assertEqual(cf.compare("Вариант 3\n\nНоябрь — время книг.", "Ноябрь — время книг.")["errors"], [])
        self.assertIn("lost", kinds(cf.compare("Сдача 3 ноября.", "Сдача в ноябре.")))
        self.assertIn("lost", kinds(cf.compare("Офис в Вашингтоне закрыт.", "Офис закрыт.")))

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
        text, _ = cp.clean("См. https://a.ru/p?utm_source=chatgpt.com и https://b.ru/q?id=1&utm_source=x.")
        self.assertEqual(text, "См. https://a.ru/p и https://b.ru/q?id=1.")
        text, _ = cp.clean("https://a.ru/p?utm_source=x&id=1")
        self.assertEqual(text, "https://a.ru/p?id=1")

    def test_several_utm_params_in_one_pass(self):
        text, counts = cp.clean("https://example.org/?utm_source=a&utm_medium=b&id=42#top")
        self.assertEqual(text, "https://example.org/?id=42#top")
        self.assertEqual(counts["utm"], 2)
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
