# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Unit tests for the skill helpers: check_facts.py and clean_paste.py.
# SCOPE: positive and negative cases for each kind of fact and artifact.
# DEPENDS: unittest; scripts loaded by path from skills/humanizer-ru/scripts.
# LINKS: V-M-CHECK-FACTS; V-M-CLEAN-PASTE.
# END_MODULE_CONTRACT
import importlib.util
import itertools
import random
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

    def test_hedge_said_another_way_is_not_lost(self):
        # 4.1.6: «около» → «примерно», «не менее» → «минимум», «свыше» → «более» keep the hedge.
        for a, b in (("Пришло около 40 человек.", "Пришло примерно 40 человек."),
                     ("Срок не менее 5 дней.", "Срок минимум 5 дней."),
                     ("Вес не более 3 кг.", "Вес максимум 3 кг."),
                     ("Заказов свыше 200.", "Заказов более 200.")):
            r = cf.compare(a, b)
            self.assertEqual([c for c in r["checks"] if c["kind"] == "hedge"], [], (a, b))
        # another meaning of the hedge is still a check: «не менее 5» → «не более 5»
        r = cf.compare("Срок не менее 5 дней.", "Срок не более 5 дней.")
        self.assertTrue(any(c["kind"] == "hedge" for c in r["checks"]))

    def test_swapped_amounts_in_one_sentence(self):
        # 4.1.6: the example of SKILL.md. A list in one sentence binds each number to the name
        # of its own clause; before it the sentence had two names and bound nothing.
        a = "Анна получила 30 000, Борис 50 000."
        for b in ("Анна получила 50 000, Борис 30 000.",
                  "Борис получил 30 000, Анна — 50 000.",
                  "Анне выделили 50 000, Борису — 30 000."):
            self.assertIn("swap", kinds(cf.compare(a, b)), b)
        a = "Анна Иванова получила 30 000 рублей, Борис Петров — 50 000 рублей."
        self.assertIn("swap", kinds(cf.compare(a, "Иванова получила 50 000 рублей, Петров — 30 000 рублей.")))
        a = "В Москве 12 офисов, в Казани 3 офиса."
        self.assertIn("swap", kinds(cf.compare(a, "В Москве 3 офиса, в Казани 12 офисов.")))

    def test_same_bindings_in_another_order_are_not_a_swap(self):
        a = "Анна получила 30 000, Борис 50 000."
        for b in ("Борис получил 50 000 рублей, Анна — 30 000.",
                  "Анна получила 30 000 рублей. Борис — 50 000.",
                  "Получили: Борис — 50 000, Анна — 30 000."):
            self.assertEqual(cf.compare(a, b)["errors"], [], b)
        # the same sum for both is bound to both
        same = "Анна получила 30 000, Борис тоже 30 000."
        self.assertEqual(cf.compare(same, "Борис получил 30 000, Анна тоже 30 000.")["errors"], [])
        # a clause with no name or with two names binds nothing
        a = "Анна, которая работает в Казани, получила 30 000, а Борис 50 000."
        self.assertEqual(cf.compare(a, "Борис получил 50 000, а Анна, которая работает в Казани, — 30 000.")["errors"], [])
        self.assertEqual(cf.compare("Анна и Борис получили по 30 000, Вера 50 000.",
                                    "Вера получила 50 000, а Анна и Борис по 30 000.")["errors"], [])
        # a row of names with one number is not a list of bindings: «по 100» is not Вера's alone
        a = "Анна получила 30 000. Вера получила 7. Анна, Борис, Вера — все получили по 100."
        b = "Анна получила 30 000. Вера получила 7. Все получили по 100: Анна, Борис, Вера."
        self.assertEqual(cf.compare(a, b)["errors"], [])

    def test_generated_enumerations(self):
        # «Name amount» lists in one sentence, written in nine shapes: the same bindings in another
        # order or shape are no error, two amounts exchanged are one. Lists that join the last two
        # items with «и» are not generated: their items share a clause and the script does not
        # tell them apart yet (CHANGELOG 4.1.6). A lead-in names everyone in mid-sentence, because
        # the script reads a capitalised word at the start of a sentence as a name only if it
        # knows it from elsewhere.
        people = [("Анна", "Анне", True), ("Борис", "Борису", False), ("Вера", "Вере", True),
                  ("Глеб", "Глебу", False), ("Дарья", "Дарье", True), ("Егор", "Егору", False),
                  ("Жанна", "Жанне", True), ("Захар", "Захару", False)]
        amounts = ["30 000", "50 000", "7 000", "12 500", "450", "1 200", "95", "2 400", "18 000", "640"]

        def verb(p):
            return "получила" if p[2] else "получил"

        def got(p):
            return "%s %s" % (p[0], verb(p))

        def first_verb_only(ps):
            return ", ".join(("%s %s рублей" % (got(p), x)) if i == 0 else ("%s %s рублей" % (p[0], x))
                             for i, (p, x) in enumerate(ps)) + "."

        shapes = {
            "elided verb": first_verb_only,
            "verb each": lambda ps: ", ".join("%s %s рублей" % (got(p), x) for p, x in ps) + ".",
            "dash": lambda ps: ", ".join("%s — %s рублей" % (p[0], x) for p, x in ps) + ".",
            "semicolon": lambda ps: "; ".join("%s — %s рублей" % (p[0], x) for p, x in ps) + ".",
            "dative": lambda ps: ", ".join(("%s выплатили %s рублей" % (p[1], x)) if i == 0 else
                                           ("%s %s рублей" % (p[1], x)) for i, (p, x) in enumerate(ps)) + ".",
            "number first": lambda ps: ", ".join("%s рублей %s %s" % (x, verb(p), p[0]) for p, x in ps) + ".",
            "sentences": lambda ps: " ".join("%s %s рублей." % (got(p), x) for p, x in ps),
            "bullets": lambda ps: "Итоги:\n" + "\n".join("- %s: %s рублей" % (p[0], x) for p, x in ps),
            "parentheses": lambda ps: ", ".join("%s (%s рублей)" % (p[0], x) for p, x in ps) + ".",
        }
        rng = random.Random(4106)
        for _ in range(300):
            k = rng.choice((2, 3, 4))
            pairs = list(zip(rng.sample(people, k), rng.sample(amounts, k)))
            lead = "Выплаты за октябрь по сотрудникам %s.\n" % ", ".join(p[0] for p, _ in pairs)
            from_shape, to_shape = rng.choice(sorted(shapes)), rng.choice(sorted(shapes))
            before = lead + shapes[from_shape](pairs)
            moved = pairs[:]
            rng.shuffle(moved)
            after = lead + shapes[to_shape](moved)
            self.assertEqual(cf.compare(before, after)["errors"], [], "%s -> %s\n%s\n%s" % (from_shape, to_shape, before, after))
            i, j = rng.sample(range(k), 2)
            wrong = pairs[:]
            wrong[i], wrong[j] = (pairs[i][0], pairs[j][1]), (pairs[j][0], pairs[i][1])
            rng.shuffle(wrong)
            after = lead + shapes[to_shape](wrong)
            self.assertIn("swap", kinds(cf.compare(before, after)), "%s -> %s\n%s\n%s" % (from_shape, to_shape, before, after))

    def test_one_hedge_left_does_not_cover_two_lost(self):
        # «около 40 … примерно 40» → «40 … примерно 40»: the first hedge is gone, and the synonym
        # that is left belongs to the second number.
        a = "Первый этап длится около 40 минут, второй — примерно 40 минут."
        hedge = lambda r: [c for c in r["checks"] if c["kind"] == "hedge"]
        self.assertEqual(len(hedge(cf.compare(a, "Первый этап длится 40 минут, второй — примерно 40 минут."))), 1)
        # each said another way: nothing is lost
        self.assertEqual(hedge(cf.compare(a, "Первый этап длится примерно 40 минут, второй — приблизительно 40 минут.")), [])
        # two mentions that became one are the «fewer» check, not also a lost hedge
        merged = cf.compare("Первый этап длится около 40 минут, второй тоже около 40 минут.",
                            "Каждый этап длится около 40 минут.")
        self.assertEqual(hedge(merged), [])

    def test_hedges_are_counted_mention_by_mention(self):
        # Three hedged mentions of 40 need three hedges of that meaning in the edit, also when one
        # of the words is repeated: «около 40 … примерно 40 … около 40» → «40 … примерно 40 … примерно 40».
        hedge = lambda r: [c for c in r["checks"] if c["kind"] == "hedge"]
        a = "Первый этап длится около 40 минут, второй примерно 40 минут, третий около 40 минут."
        lost = hedge(cf.compare(a, "Первый этап длится 40 минут, второй примерно 40 минут, третий примерно 40 минут."))
        self.assertEqual(len(lost), 1)
        self.assertIn("«около»", lost[0]["detail"])
        self.assertEqual(hedge(cf.compare(
            a, "Первый этап длится примерно 40 минут, второй приблизительно 40 минут, третий порядка 40 минут.")), [])
        # the same word lost at one of its two mentions
        b = "Первый этап длится около 40 минут, второй тоже около 40 минут."
        self.assertEqual(len(hedge(cf.compare(b, "Первый этап длится 40 минут, второй тоже около 40 минут."))), 1)
        # «не менее чем 6» is a hedge that says «минимум»; «не старше 14 дней» says «не более 14 дней»
        self.assertEqual(hedge(cf.compare("Нужно минимум 6 часов.", "Нужно не менее чем 6 часов.")), [])
        self.assertEqual(len(hedge(cf.compare("Нужно не менее чем 6 часов.", "Нужно 6 часов."))), 1)
        self.assertEqual(hedge(cf.compare("Результат действителен не более 14 дней.", "Результат не старше 14 дней.")), [])

    def test_marks_moved_between_a_hedge_and_its_number_do_not_lose_it(self):
        # In the edit, bold and italic marks between the hedge and the number do not hide the hedge
        # (d08 of the corpus: «**минимум 2 человека**» → «минимум **2 человека**»). A hedge that is
        # really gone, changed, or cut off from the number by a comma is still a check.
        hedge = lambda r: [c for c in r["checks"] if c["kind"] == "hedge"]
        a = "Запрошены ревьюеры: **минимум 2 человека**, один из другой команды.\n"
        for edit in ("Запрошены ревьюеры: минимум **2 человека**, один из другой команды.\n",
                     "Запрошены ревьюеры: **минимум** 2 человека, один из другой команды.\n",
                     "Запрошены ревьюеры: минимум *2 человека*, один из другой команды.\n"):
            self.assertEqual(hedge(cf.compare(a, edit)), [], edit)
        for edit in ("Запрошены ревьюеры: **2 человека**, один из другой команды.\n",
                     "Запрошены ревьюеры: максимум **2 человека**, один из другой команды.\n",
                     "Запрошены ревьюеры: минимум, **2 человека**, один из другой команды.\n"):
            self.assertEqual(len(hedge(cf.compare(a, edit))), 1, edit)

    def test_two_people_who_share_a_word_are_two_owners(self):
        # «Анна Иванова» and «Анна Петрова» have a first name and nothing else in common: a mention
        # by the surname is one of them, and the amounts of the two can be exchanged.
        a = "В отделе Анна Иванова и Анна Петрова. Иванова получила 30 рублей. Петрова получила 50 рублей."
        intro = "В отделе Анна Иванова и Анна Петрова. "
        self.assertIn("swap", kinds(cf.compare(a, intro + "Иванова получила 50 рублей. Петрова получила 30 рублей.")))
        self.assertEqual(cf.compare(a, intro + "Петрова получила 50 рублей. Иванова получила 30 рублей.")["errors"], [])
        # in one sentence, and with the surname shared instead of the first name
        b = "Анна Иванова получила 30 рублей, Анна Петрова — 50 рублей."
        self.assertIn("swap", kinds(cf.compare(b, "Анна Иванова получила 50 рублей, Анна Петрова — 30 рублей.")))
        c = "Анна Иванова получила 30 рублей, Борис Иванов — 50 рублей."
        self.assertIn("swap", kinds(cf.compare(c, "Анна Иванова получила 50 рублей, Борис Иванов — 30 рублей.")))
        # a word that fits both of them names nobody: no owner, no swap (the lost surnames are another error)
        self.assertNotIn("swap", kinds(cf.compare(b, "Анна получила 30 рублей, Анна — 50 рублей.")))
        # Анна Петрова shares a word with each of the others, so only «Борис» and «Иванова» tell people apart
        d = "В отделе Анна Иванова, Анна Петрова и Борис Петров. Анна Иванова получила 30000 рублей, Борис Петров — 50000 рублей."
        self.assertEqual(cf.compare(d, d.replace("Борис Петров — 50000", "Петров — 50000"))["errors"], [])

    def test_a_sender_named_in_full_is_not_a_receiver(self):
        # «от Бориса Петрова»: both words name the sender, not only the first
        a = "Анна получила 30 000 от Бориса Петрова, Борис Петров — 50 000."
        self.assertIn("swap", kinds(cf.compare(a, "Анна получила 50 000 от Бориса Петрова, Борис Петров — 30 000.")))
        b = "Анна получила 30 рублей, Борис — 50 рублей; Анна получила 70 рублей, которые перечислил Борис Петров, как и договаривались."
        c = "Анна получила 30 рублей, Борис — 50 рублей; Анна получила, как и договаривались, от Бориса Петрова 70 рублей."
        self.assertEqual(cf.compare(b, c)["errors"], [])
        # with a patronymic, and the case forms of one person («Анна Иванова», «от Анны Ивановой») are one person
        d = "Анна получила 30 000 от Бориса Андреевича Петрова, Борис Петров — 50 000."
        self.assertIn("swap", kinds(cf.compare(d, "Анна получила 50 000 от Бориса Андреевича Петрова, Борис Петров — 30 000.")))
        e = "Выплаты: Анна Иванова, Борис Петров. Анна Иванова получила 30000 рублей, Борис Петров получил 50000 рублей от Анны Ивановой."
        self.assertIn("swap", kinds(cf.compare(e, e.replace("Анна Иванова получила 30000", "Иванова получила 50000")
                                               .replace("получил 50000", "получил 30000"))))

    def test_generated_senders_and_shared_names(self):
        # Items with a sender after «от» or in a clause of their own, receivers named in full or by
        # the surname, people who share a first name or a surname: the same facts told another way
        # are no error, two amounts exchanged are one.
        people = {"anna": ("Анна Иванова", "Анны Ивановой", "а"), "boris": ("Борис Петров", "Бориса Петрова", ""),
                  "vera": ("Вера Орлова", "Веры Орловой", "а"), "gleb": ("Глеб Волков", "Глеба Волкова", ""),
                  "boris3": ("Борис Андреевич Петров", "Бориса Андреевича Петрова", "")}

        def item(shape, receiver, surname_only, amount, sender):
            name = people[receiver][0].split()[-1] if surname_only else people[receiver][0]
            got = "получил" + people[receiver][2]
            return {1: "%s %s %s рублей от %s" % (name, got, amount, people[sender][1]),
                    2: "%s %s от %s %s рублей" % (name, got, people[sender][1], amount),
                    3: "%s — %s рублей от %s" % (name, amount, people[sender][1]),
                    4: "%s %s %s рублей, которые перечислил %s" % (name, got, amount, people[sender][0])}[shape]

        rng = random.Random(4107)
        quads = [q for q in itertools.product(people, repeat=4)
                 if q[0] != q[1] and q[2] != q[3] and q[0] != q[2] and q[1] != q[3]
                 and not {"boris", "boris3"} <= set(q)]
        for r1, r2, s1, s2 in rng.sample(quads, 40):
            lead = "Выплаты: %s. " % ", ".join(people[p][0] for p in dict.fromkeys((r1, r2, s1, s2)))
            before = lead + "%s, %s." % (item(1, r1, False, "30000", s1), item(1, r2, False, "50000", s2))
            for (sh1, sh2), surname_only in itertools.product(((2, 2), (3, 4), (4, 1), (1, 3)), (False, True)):
                for amounts, expect_swap in (("30000 50000", False), ("50000 30000", True)):
                    x, y = amounts.split()
                    after = lead + "%s, %s." % (item(sh1, r1, surname_only, x, s1), item(sh2, r2, surname_only, y, s2))
                    got = kinds(cf.compare(before, after))
                    self.assertEqual("swap" in got, expect_swap, "\n%s\n%s" % (before, after))

    def test_a_sender_is_not_the_one_who_gets_the_amount(self):
        a = "Анна получила 30 рублей, Борис — 50 рублей; Анна получила, как и договаривались, от Бориса 70 рублей."
        b = "Анна получила 30 рублей, Борис — 50 рублей; Анна получила 70 рублей, которые перечислил Борис, как и договаривались."
        self.assertEqual(cf.compare(a, b)["errors"], [])
        # the amounts of the items still count
        self.assertIn("swap", kinds(cf.compare(a, a.replace("30 рублей", "50 рублей", 1).replace("— 50 рублей", "— 30 рублей", 1))))
        # a list where each item says who sent the money: the receiver is the first name of an item
        c = "Анна получила 30 000 от Глеба, Вера — 7 000 от Дарьи."
        self.assertEqual(cf.compare(c, "Вера получила 7 000 от Дарьи, Анна — 30 000 от Глеба.")["errors"], [])
        self.assertIn("swap", kinds(cf.compare(c, "Анна получила 7 000 от Дарьи, Вера — 30 000 от Глеба.")))

    def test_a_person_named_by_first_name_surname_or_both_is_one_owner(self):
        a = "В отделе Анна Иванова и Борис Петров. Анна получила 30 000, Борис — 50 000."
        # the same bindings, one person named by the surname: no error
        self.assertEqual(cf.compare(a, "В отделе Анна Иванова и Борис Петров. Иванова получила 30 000, Борис — 50 000.")["errors"], [])
        # amounts exchanged, both people named by the surname: an error
        self.assertIn("swap", kinds(cf.compare(a, "В отделе Анна Иванова и Борис Петров. Иванова получила 50 000, Петров — 30 000.")))

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


    # 4.1.4: defects found by a property run over the eval texts and by two model bug hunts.
    def errs(self, a, b):
        return {(e["kind"], e["what"]) for e in cf.compare(a, b)["errors"]}

    def test_versions_weekdays_and_inline_code_are_facts(self):
        self.assertIn(("lost", "число"), self.errs("Версия 2.1.3 вышла.", "Версия 2.1.4 вышла."))
        self.assertIn(("lost", "дата"), self.errs("Встреча в среду.", "Встреча в четверг."))
        self.assertEqual(self.errs("Рабочая среда готова.", "Окружение готово."), set())
        self.assertIn(("lost", "код"), self.errs("Код: `npm run build`", "Код: `npm run dev`"))
        r = cf.compare("Запуск: `make`", "Запуск: make")
        self.assertEqual(r["errors"], [])
        self.assertIn(("unquoted", "код"), {(c["kind"], c["what"]) for c in r["checks"]})

    def test_phones_and_links_compare_by_meaning(self):
        self.assertEqual(self.errs("Звоните: +7 (999) 123-45-67.", "Телефон 8 999 123 45 67."), set())
        self.assertIn(("lost", "телефон"), self.errs("Звоните: +7 999 123-45-67.", "Звоните: +7 999 123-45-68."))
        self.assertEqual(self.errs("Сайт: https://zerno.ru/", "Сайт https://Zerno.ru"), set())
        self.assertIn(("lost", "ссылка"), self.errs("https://example.ru/A", "https://example.ru/a"))
        self.assertEqual(cf.compare("Хост https://[::1]/ доступен.", "Хост https://[::1]/ доступен.")["errors"], [])

    def test_numbers_keep_precision_units_and_ranges(self):
        self.assertIn(("lost", "число"), self.errs("Цена 100000,01 ₽.", "Цена 100000,02 ₽."))
        self.assertIn(("unit", "единица"), self.errs("Пришло 30 тыс. человек.", "Пришло 30 тыс. рублей."))
        self.assertIn(("unit", "единица"), self.errs("Цена пять рублей.", "Цена пять долларов."))
        for a, b in (("Цена 1,50 ₽.", "Цена 1.50 ₽."), ("С 2020 г. работаем.", "С 2020 года работаем."),
                     ("Встреча в 16:00.", "Встреча в 16 часов."), ("С 5 по 7 марта.", "5–7 марта."),
                     ("В группе двадцать один человек.", "В группе 21 человек."),
                     ("Подожди одну минуту.", "Подожди 1 минуту.")):
            self.assertEqual(self.errs(a, b), set(), a)
        r = cf.compare("Держит тепло 6 часов.", "Держит тепло 6.")
        self.assertIn(("unit", "единица"), {(c["kind"], c["what"]) for c in r["checks"]})

    def test_month_without_day_is_a_date(self):
        self.assertIn(("lost", "дата"), self.errs("Встреча в марте 2026.", "Встреча в апреле 2026."))
        self.assertEqual(self.errs("Сдача в марте.", "Сдать нужно в марте."), set())

    def test_negations_with_prepositions_and_added_ones(self):
        self.assertIn(("inverted", "отрицание"), self.errs("Оплата не на карту.", "Оплата на карту."))
        self.assertIn(("inverted", "отрицание"), self.errs("Здесь нельзя курить.", "Здесь можно курить."))
        r = cf.compare("Мы храним данные.", "Мы не храним данные.")
        self.assertIn(("inverted", "отрицание"), {(c["kind"], c["what"]) for c in r["checks"]})
        # "не X, а Y" is the pattern a rewrite removes: the contrast is a check, not an error.
        r = cf.compare("Переезд в марте, а не в феврале.", "Переезд в марте, хотя планировали в феврале.")
        self.assertEqual(r["errors"], [])
        self.assertEqual(self.errs("Никаких дрожжей и сахара.", "Ни дрожжей, ни сахара."), set())

    def test_full_names_still_bind_numbers(self):
        a = "Анна Иванова получила 30 рублей. Борис Петров получил 50 рублей."
        b = "Анна Иванова получила 50 рублей. Борис Петров получил 30 рублей."
        self.assertIn(("swap", "привязка"), self.errs(a, b))

    def test_short_names_and_cyrillic_acronyms(self):
        self.assertEqual(self.errs("Письмо для Ани.", "Написал Ане."), set())
        self.assertIn(("lost", "имя или название"), self.errs("Компания из США открыла офис.", "Компания открыла офис."))
        self.assertEqual(self.errs("Павел пришёл, ждём Павла.", "Ждём Павла."), set())
        self.assertEqual(self.errs("Отдайте заявление в УК дома.", "Отдайте заявление в управляющую компанию."), set())

    def test_direct_speech_is_word_for_word(self):
        self.assertIn(("lost", "цитата"), self.errs("Он сказал: «Мы запустили проект».", "Он сказал: «Мы запустим проект»."))

    def test_report_agrees_in_gender(self):
        text = cf.render(cf.compare("Звоните: +7 999 123-45-67.", "Звоните нам."))
        self.assertIn("потерян телефон", text)

    # 4.1.5: findings of the cross-review of 4.1.4 (GPT-6.1 Sol, Gemini 4 Argon), each rerun first.
    def test_ip_addresses_and_versions_are_whole_tokens(self):
        self.assertIn(("lost", "число"), self.errs("Адрес 10.0.10.1.", "Адрес 10.0.10.2."))
        r = cf.compare("Версия 2.1.10 вышла.", "Версия 2.1.11 вышла.")
        self.assertIn("2.1.10", {e["detail"] for e in r["errors"]})
        self.assertEqual(self.errs("Срок 01.02.26.", "Срок 1 февраля 2026."), set())

    def test_link_path_keeps_its_trailing_slash(self):
        self.assertIn(("lost", "ссылка"), self.errs("См. https://a.ru/api/item/", "См. https://a.ru/api/item"))

    def test_month_needs_a_month_ending(self):
        self.assertNotIn(("lost", "дата"), self.errs("Позвали Марту.", "Позвали Анну."))
        self.assertEqual(self.errs("Восстание декабристов.", "Восстание дворян."), set())
        self.assertIn(("lost", "дата"), self.errs("Между маем и июнем.", "В июне."))

    def test_ban_said_another_way_is_only_a_check(self):
        # 25 fresh rewrites (DeepSeek texts, Haiku edits): the ban stayed as «не готовим».
        r = cf.compare("Суп нельзя приготовить без сливок, альтернатива — кокосовое молоко.",
                       "Без сливок суп не готовим. Вместо них можно взять кокосовое молоко.")
        self.assertEqual(r["errors"], [])
        self.assertIn(("inverted", "отрицание"), {(c["kind"], c["what"]) for c in r["checks"]})

    def test_long_interview_answer_is_direct_speech(self):
        # The same fresh set: an interview answer of 110 characters was rewritten and went unseen.
        a = ("Интервью.\n\n— «Мы ожидали окупаемость 18 месяцев, а получили 14. Экономия появилась не сразу,"
             " а через квартал после запуска».\n")
        b = ("Интервью.\n\n— «Ждали окупаемость за 18 месяцев, вышло за 14. Экономия появилась не сразу,"
             " а через квартал после запуска».\n")
        self.assertIn(("lost", "цитата"), self.errs(a, b))

    def test_surname_alone_still_binds_the_number(self):
        a = "Анна Иванова получила 30 рублей. Борис Петров получил 50 рублей."
        b = "Анна и Борис пришли. Иванова получила 50 рублей. Петров получил 30 рублей."
        self.assertIn(("swap", "привязка"), self.errs(a, b))


class CleanPasteTest(unittest.TestCase):
    def test_utm_tail_in_markup_html_and_before_invisible(self):
        for src, want in (("Сайт https://a.ru/x?utm_source=chatgpt.com\u200b готов.", "Сайт https://a.ru/x готов."),
                          ("**https://a.ru/p?utm_source=chatgpt.com**", "**https://a.ru/p**"),
                          ("https://a.ru/p?utm_source=chatgpt.com&amp;id=1", "https://a.ru/p?id=1"),
                          ("https://a.ru/p?id=1&amp;utm_source=chatgpt.com", "https://a.ru/p?id=1"),
                          ("Сайт www.a.ru/x?utm_source=chatgpt.com", "Сайт www.a.ru/x"),
                          ("Хост https://[::1]/ доступен.", "Хост https://[::1]/ доступен.")):
            self.assertEqual(cp.clean(src)[0], want, src)

    def test_cite_start_keeps_the_space_and_code_is_untouched(self):
        self.assertEqual(cp.clean("Текст [cite_start]первый[cite: 1].")[0], "Текст первый.")
        code = '`print("[cite: 1]")` и\n```bash\ncurl https://a.ru/p?utm_source=chatgpt.com\n```\n'
        self.assertEqual(cp.clean(code), (code, {}))
        prose = "```markdown\nПривет, это пост про кофе :contentReference[oaicite:1]{index=1}.\n```\n"
        self.assertEqual(cp.clean(prose)[0], "```markdown\nПривет, это пост про кофе.\n```\n")

    def test_code_block_with_windows_line_endings_is_untouched(self):
        code = "```bash\r\ncurl https://a.ru/p?utm_source=chatgpt.com\r\n```\r\n"
        self.assertEqual(cp.clean(code), (code, {}))

    def test_in_place_keeps_windows_line_endings(self):
        tmp = ROOT / "tests" / "_tmp_cp"
        tmp.mkdir(exist_ok=True)
        try:
            f = tmp / "a.txt"
            f.write_bytes("Текст\u200b\r\nВторая\r\n".encode("utf-8"))
            subprocess.run([sys.executable, str(SCRIPTS / "clean_paste.py"), str(f), "--in-place"], capture_output=True)
            self.assertEqual(f.read_bytes(), "Текст\r\nВторая\r\n".encode("utf-8"))
        finally:
            for p in tmp.glob("*"):
                p.unlink()
            tmp.rmdir()

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
