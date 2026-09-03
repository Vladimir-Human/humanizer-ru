#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Независимые unittest-тесты мягких признаков из scripts/scan_soft_signals.py.

Перенос встроенного --selftest (106 кейсов) в обычные тесты без вызова
scan_soft_signals.selftest(). Модуль импортируется безопасно: при импорте
исполняются только объявления и компиляция REGISTRY, а main() и selftest()
спрятаны под `if __name__ == "__main__"`.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

if os.path.isdir(SCRIPTS):
    # Дерево репозитория: канон — scripts/ (установленный пакет может быть
    # старее рабочего дерева).
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import scan_soft_signals as ss  # noqa: E402
else:
    # sdist вне дерева: копия из пакета побайтово равна scripts/
    # (гейт scripts/check_pkg_sync.py).
    from humanizer_ru import scan_soft_signals as ss  # noqa: F401


def _fires(det, text):
    """Тот же смысл, что и в selftest: признак сработал, а не просто найден."""
    return len(det["finder"](text, text.splitlines() or [""])) >= det["min_hits"]


def _det_by_id(det_id):
    return ss.REGISTRY[[d["id"] for d in ss.REGISTRY].index(det_id)]


def _silent_main(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return ss.main(argv)


class TestSoftSignals(unittest.TestCase):
    def test_every_detector_fires_on_positive(self):
        for det in ss.REGISTRY:
            with self.subTest(detector=det["id"]):
                self.assertTrue(_fires(det, det["pos"]), det["id"])

    def test_every_detector_silent_on_negative(self):
        for det in ss.REGISTRY:
            with self.subTest(detector=det["id"]):
                self.assertFalse(_fires(det, det["neg"]), det["id"])

    def test_harness_catches_dead_detector(self):
        dead = dict(ss.REGISTRY[0])
        dead["finder"] = ss._make_phrase_finder(
            ["\u00a7\u00a7\u043d\u0435\u0442-\u0442\u0430\u043a\u043e\u0439-\u0444\u0440\u0430\u0437\u044b\u00a7\u00a7"]
        )
        self.assertFalse(_fires(dead, dead["pos"]))

    def test_pattern_counted_once_per_text(self):
        rep = ss.analyze(
            "Эксперты считают одно. Эксперты считают другое. "
            "Эксперты считают третье."
        )
        self.assertEqual(rep["features_total"], 1)
        self.assertTrue(rep["findings"])
        self.assertEqual(rep["findings"][0]["count"], 3)

    def test_recommendation_thresholds(self):
        cases = (
            ("одна категория, 3+ признака -> форматная правка без вердикта",
             "авторство не определялось" in ss._recommend(3, 1)),
            ("ровно 2 из >=2 категорий -> навигатор без авто-правки",
             "навигатор" in ss._recommend(2, 2) and "авто-правка не применяется" in ss._recommend(2, 2)),
            ("0-1 признак -> не править", "не править" in ss._recommend(1, 1)),
            ("3-5 из >=2 категорий -> выборочная правка",
             "выборочная" in ss._recommend(4, 2)),
            ("6+ из >=2 категорий -> переписывание",
             "переписывание" in ss._recommend(7, 3)),
        )
        for name, ok in cases:
            with self.subTest(case=name):
                self.assertTrue(ok, name)

    def test_synthetic_ai_text(self):
        ai_like = (
            "Отличный вопрос! Безусловно, крайне важно раскрыть потенциал "
            "синергии. Более того, по сути это не просто инструмент, а "
            "новый подход. Он не только быстрый, но и удобный.\n\n"
            "Однако стоит отметить, что эксперты считают проект уникальным "
            "и инновационным. В заключение хочется отметить: будущее "
            "выглядит светлым. Надеюсь, это поможет!"
        )
        rep = ss.analyze(ai_like)
        self.assertGreaterEqual(rep["features_total"], 6)
        self.assertGreaterEqual(rep["categories_total"], 2)
        self.assertIn("переписывание", rep["recommendation"])

    def test_short_human_text_has_zero_features(self):
        human = ("Утром мы пошли на рынок. Купили хлеба и молока. Дождь так "
                 "и не начался, зато к обеду распогодилось.")
        self.assertEqual(ss.analyze(human)["features_total"], 0)

    def test_genre_suppression(self):
        triples = _det_by_id("rule_of_three")["pos"]
        academ = _det_by_id("est_avoidance")["pos"]
        legal = ss.analyze("Стороны осуществляют деятельность на основании договора.",
                           genre="legal")
        cases = (
            ("нейтральный жанр: тройки считаются",
             any(f["id"] == "rule_of_three" for f in ss.analyze(triples)["findings"])),
            ("художественный жанр: тройки не считаются",
             not any(f["id"] == "rule_of_three"
                     for f in ss.analyze(triples, genre="fiction")["findings"])),
            ("академический жанр: «является» не считается",
             not any(f["id"] == "est_avoidance"
                     for f in ss.analyze(academ, genre="academic")["findings"])),
            ("юридический жанр: мягкие признаки не считаются",
             legal["features_total"] == 0 and "класс" not in legal["note"]
             and "check_markers" in legal["note"]),
        )
        for name, ok in cases:
            with self.subTest(case=name):
                self.assertTrue(ok, name)

    def test_markdown_traces_plain_text_mode(self):
        md = _det_by_id("markdown_traces")["pos"]
        self.assertFalse(
            any(f["id"] == "markdown_traces" for f in ss.analyze(md)["findings"]),
            "без --plain-text следы Markdown не считаются")
        self.assertTrue(
            any(f["id"] == "markdown_traces"
                for f in ss.analyze(md, plain_text=True)["findings"]),
            "с --plain-text следы Markdown считаются")

    def test_json_report_round_trip(self):
        ai_like = self._ai_like_text()
        dumped = json.loads(json.dumps(ss.analyze(ai_like), ensure_ascii=False))
        self.assertEqual(dumped["features_total"], ss.rep0_total(ai_like))

    # Данные для нескольких кейсов повторяются; методом, а не атрибутом, чтобы
    # не загрязнять печать unittest.
    @staticmethod
    def _ai_like_text():
        return (
            "Отличный вопрос! Безусловно, крайне важно раскрыть потенциал "
            "синергии. Более того, по сути это не просто инструмент, а "
            "новый подход. Он не только быстрый, но и удобный.\n\n"
            "Однако стоит отметить, что эксперты считают проект уникальным "
            "и инновационным. В заключение хочется отметить: будущее "
            "выглядит светлым. Надеюсь, это поможет!"
        )

    def test_academic_phrase_excludes(self):
        acad = ("Следует отметить, что более того, в контексте задачи стоит "
                "погрузиться в детали доказательства.")
        sig2 = ("Метод играет важную роль в сходимости. "
                "Результат знаменует собой новый этап.")
        cases = (
            ("нейтральный жанр видит машинную лексику",
             any(d["id"] == "ai_lexicon" for d in ss.analyze(acad)["findings"])),
            ("academic: «погрузиться» исключён из лексики",
             all(d["id"] != "ai_lexicon"
                 for d in ss.analyze(acad, genre="academic")["findings"])),
            ("academic: «играет важную роль» не доводит значимость до порога",
             any(d["id"] == "significance" for d in ss.analyze(sig2)["findings"])
             and all(d["id"] != "significance"
                     for d in ss.analyze(sig2, genre="academic")["findings"])),
        )
        for name, ok in cases:
            with self.subTest(case=name):
                self.assertTrue(ok, name)

    def test_rule_of_three_counterexamples(self):
        quad = ("На конференции будут доклады, дискуссии, мастер-классы "
                "и нетворкинг. И доклады, дискуссии, мастер-классы и воркшопы. "
                "Снова доклады, дискуссии, мастер-классы и воркшопы.")
        intro = ("Безусловно, подход включает анализ, разработку и тестирование. "
                 "Конечно, план включает анализ, разработку и внедрение. "
                 "Разумеется, цикл включает анализ, разработку и проверку.")
        intro_mid = ("Формат включает доклады, конечно, дискуссии, мастер-классы "
                     "и нетворкинг. Формат включает доклады, конечно, дискуссии, "
                     "мастер-классы и нетворкинг. Формат включает доклады, "
                     "конечно, дискуссии, мастер-классы и нетворкинг.")
        intro_k = ("К сожалению, план включает анализ, разработку и внедрение. "
                   "Итак, цикл включает анализ, разработку и проверку. "
                   "Следовательно, процесс включает анализ, разработку и сдачу.")
        intro_full = ("Во-первых, план включает анализ, разработку и внедрение. "
                      "Во-вторых, цикл включает анализ, разработку и проверку. "
                      "По моему мнению, процесс включает анализ, разработку и "
                      "сдачу. К счастью для всех, работа включает анализ, "
                      "разработку и тесты. В программе – конечно, доклады, "
                      "дискуссии и мастер-классы.")
        indent_fence = ("Обычный параграф без разметки.\n"
                        "    ```\n"
                        "    Будут доклады, дискуссии и нетворкинг. Ждём "
                        "инновации, вдохновение и инсайты. Обещают еду, музыку "
                        "и призы.\n"
                        "    ```\nХвост.")
        tab_fence = ("\t```\n"
                     "Будут доклады, дискуссии и нетворкинг.\n"
                     "\t```\n"
                     "Ждём инновации, вдохновение и инсайты. Обещают еду, "
                     "музыку и призы.")
        list_fence = ("- пункт с кодом:\n\n"
                      "    ```\n"
                      "    Будут доклады, дискуссии и нетворкинг.\n"
                      "    ```\n")
        nested_fence = ("````markdown\n```\nБудут доклады, дискуссии и "
                        "нетворкинг.\n```\n````\nХвост.")
        quartet_a = "Мы рады нашему счастью, успехам, здоровью и благополучию."
        quartet_b = "Мы рады нашему урожаю, успехам, здоровью и благополучию."
        years = ("в 2019, 2020 и 2021 годах. В 2019, 2020 и 2021 годах. "
                 "За 2019, 2020 и 2021 годы.")
        fenced = ("```bash\n# главный раздел\n### подобласть без второго уровня\n"
                  "```\nОбычный текст без заголовков.")
        cases = (
            ("четвёрки не считаются правилом трёх",
             "rule_of_three" not in ss.analyze(quad)["categories"].get("языковая", [])
             and all(d["id"] != "rule_of_three" for d in ss.analyze(quad)["findings"])),
            ("вводное слово перед тройкой не маскирует правило трёх",
             any(d["id"] == "rule_of_three" for d in ss.analyze(intro)["findings"])),
            ("четвёрка с вводным внутри не считается тройкой",
             all(d["id"] != "rule_of_three" for d in ss.analyze(intro_mid)["findings"])),
            ("составные вводные перед тройкой не маскируют её",
             any(d["id"] == "rule_of_three" for d in ss.analyze(intro_k)["findings"])),
            ("полные дефисные и многословные вводные и en dash не гасят тройку",
             any(d["id"] == "rule_of_three" for d in ss.analyze(intro_full)["findings"])),
            ("отступ 4 пробела — не забор: проза внутри видна детекторам",
             any(d["id"] == "rule_of_three" for d in ss.analyze(indent_fence)["findings"])),
            ("таб-забор — не забор: проза вокруг него видна (CommonMark 2.1)",
             any(d["id"] == "rule_of_three" for d in ss.analyze(tab_fence)["findings"])),
            ("забор внутри пункта списка маскируется (CommonMark 5.2)",
             all(d["id"] != "rule_of_three" for d in ss.analyze(list_fence)["findings"])),
            ("вложенный ``` не закрывает внешний ```` забор",
             all(d["id"] != "rule_of_three" for d in ss.analyze(nested_fence)["findings"])),
            ("четвёрка «счастью, … и благополучию» не считается тройкой",
             all(d["id"] != "rule_of_three" for d in ss.analyze(quartet_a)["findings"])),
            ("четвёрки «счастью» и «урожаю» обрабатываются одинаково",
             [d["id"] for d in ss.analyze(quartet_a)["findings"]]
             == [d["id"] for d in ss.analyze(quartet_b)["findings"]]),
            ("перечисления годов не считаются правилом трёх",
             all(d["id"] != "rule_of_three" for d in ss.analyze(years)["findings"])),
            ("заголовки внутри блоков кода не дают #21",
             all(d["id"] not in ("heading_hierarchy", "title_case")
                 for d in ss.analyze(fenced)["findings"])),
        )
        for name, ok in cases:
            with self.subTest(case=name):
                self.assertTrue(ok, name)

    def test_suppress_registry_consistency(self):
        ids = [d["id"] for d in ss.REGISTRY]
        for genre, suppressed in ss.SUPPRESS.items():
            if suppressed is None:
                continue
            for det_id in suppressed:
                with self.subTest(genre=genre, detector=det_id):
                    self.assertIn(det_id, ids)
        fic = ss.analyze(
            "Утро было такое — свежее, прозрачное, тонкое. Город ещё "
            "спал — только редкие шаги отдавались эхом.", genre="fiction")
        with self.subTest(case="художка: тире-детектор подавлен"):
            self.assertNotIn("emdash_bold", fic["categories"].get("структурная", []))
            self.assertTrue(all(d["id"] != "emdash_bold" for d in fic["findings"]))

    def test_max_cats_gate(self):
        sig_pos = next(d["pos"] for d in ss.REGISTRY if d["cat"] == "содержательная")
        lex_pos = next(d["pos"] for d in ss.REGISTRY if d["cat"] == "языковая")
        chat_pos = next(d["pos"] for d in ss.REGISTRY if d["cat"] == "коммуникативная")
        two_text = sig_pos + " " + lex_pos
        one_text = chat_pos
        with self.subTest(case="образец для max-cats даёт две категории"):
            self.assertEqual(ss.analyze(two_text)["categories_total"], 2)
        with self.subTest(case="образец для max-cats даёт одну категорию"):
            self.assertEqual(ss.analyze(one_text)["categories_total"], 1)
        with tempfile.TemporaryDirectory() as td:
            p_two = os.path.join(td, "two.txt")
            p_one = os.path.join(td, "one.txt")
            with open(p_two, "w", encoding="utf-8") as fh:
                fh.write(two_text)
            with open(p_one, "w", encoding="utf-8") as fh:
                fh.write(one_text)
            with self.subTest(case="--max-cats 1: две категории валят проверку"):
                self.assertEqual(_silent_main([p_two, "--max-cats", "1"]), 1)
            with self.subTest(case="--max-cats 1: одна категория проходит"):
                self.assertEqual(_silent_main([p_one, "--max-cats", "1"]), 0)
            with self.subTest(case="--max-cats 0: порог выключен"):
                self.assertEqual(_silent_main([p_two, "--max-cats", "0"]), 0)


if __name__ == "__main__":
    unittest.main()
