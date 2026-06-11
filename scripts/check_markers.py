#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Прогон регулярных выражений из references/chatbot-artifacts.md
по проверочным образцам из references/test-fixtures.md.

Каждое выражение проходит три уровня:
  1. Прямой образец  — выражение обязано сработать.
  2. Отрицательный   — похожий, но не машинный текст; срабатывать не должно.
  3. Граничный       — пустая строка и многократные совпадения; без падений.

Только стандартная библиотека. Запуск:  python3 scripts/check_markers.py
Код возврата 0 — все проверки пройдены, 1 — есть провалы.

При добавлении нового выражения в chatbot-artifacts.md сюда добавляется
блок с образцами, а парные образцы — в references/test-fixtures.md.
Ни одно работающее правило не удаляется (см. принцип в test-fixtures.md).
"""

import re
import sys

# name: (выражение, прямые образцы, отрицательные образцы, [многократный образец, ожидаемое число])
CASES = {
    # --- A.1. Метки внутреннего цитирования OpenAI ---
    "contentReference": (
        r":contentReference\[oaicite:\d+\]\{index=\d+\}",
        ["Согласно отчёту :contentReference[oaicite:0]{index=0}, рынок вырос на 12%.",
         ":contentReference[oaicite:42]{index=42}"],
        ["Это просто ссылка на oaicite (упоминание термина в статье об ИИ).",
         "Документация: содержит [oaicite:N] как пример формата."],
        (":contentReference[oaicite:0]{index=0} и :contentReference[oaicite:1]{index=1} и :contentReference[oaicite:2]{index=2}", 3),
    ),
    "oai_citation": (
        r"oai_citation:\d+‡",
        ["Источник oai_citation:5‡Wikipedia говорит, что…", "oai_citation:0‡"],
        ["oai_citation без числа после двоеточия"],
        None,
    ),
    "oaicite_short": (
        r"oaicite:\d+",
        ["усечённая ссылка oaicite:7"],
        ["oaicite без двоеточия и числа"],
        None,
    ),
    # --- A.2. Метки веб-поиска OpenAI ---
    "turn_search": (
        r"turn\d+search\d+",
        ["Согласно turn0search0, тема актуальна.", "turn3search12 в середине предложения"],
        ["turn left and search again", "turnaround search"],
        ("turn0search0 turn1search1 turn2search2", 3),
    ),
    "turn_fetch": (
        r"turn\d+fetch\d+",
        ["[turn0fetch0] в скобках"],
        ["turn fetch the file"],
        None,
    ),
    # --- A.3. Метки UTM от чат-ботов ---
    "utm_chatgpt": (
        r"[?&]utm_source=chatgpt\.com",
        ["https://example.com/article?utm_source=chatgpt.com",
         "https://example.com/?id=5&utm_source=chatgpt.com",
         "?utm_source=chatgpt.com&other=1"],
        ["utm_source=chatgpt.com упомянут в статье об отслеживании",
         "https://example.com/?utm_source=other.com"],
        None,
    ),
    "utm_openai": (
        r"[?&]utm_source=openai",
        ["https://docs.example.com/?utm_source=openai"],
        ["OpenAI utm_source без знака ? или &"],
        None,
    ),
    # --- A.4. Метки прикрепления и карточек ---
    "attached_file": (
        r"attached_file:\/\/",
        ["См. attached_file:///tmp/upload.pdf"],
        ["Файл прикреплён, см. attached file (по-русски)"],
        None,
    ),
    "grok_card": (
        r"grok_card:\/\/",
        ["grok_card://1234567890"],
        ["карточка Grok без специфичной разметки"],
        None,
    ),
    "vertexaisearch": (
        r"vertexaisearch\.cloud\.google\.com/grounding-api-redirect",
        ["https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbCdEf"],
        ["vertexaisearch.cloud.google.com без пути",
         "https://cloud.google.com/vertex-ai-search"],
        None,
    ),
    # --- A.5. Прочие маркеры разметки ---
    "attributableIndex": (
        r"\battributableIndex\b",
        ['{"attributableIndex": 0}'],
        ["слово attributable в обычном тексте о праве и атрибуции",
         "attributableIndexes (с окончанием)"],
        None,
    ),
    "citation_n": (
        r"\[citation:\d+\]",
        ["Согласно исследованию [citation:3], результаты неоднозначны."],
        ["[citation needed] (Википедийный шаблон)"],
        None,
    ),
    # --- A.6. Маркеры новых платформ (v2.5) ---
    "copilot_caret": (
        r"\[\^\d+\^\]",
        ["Рынок вырос на 12%[^1^] по данным отчёта.", "[^10^]"],
        ["Обычная сноска Markdown[^1] определена ниже."],
        ("[^1^][^2^][^10^]", 3),
    ),
    "assistants_source": (
        r"【\d+(?::\d+)?†source】",
        ["Согласно политике【1†source】, доступ разрешён.", "【4:2†source】"],
        ["Декоративные уголки 【примечание】 без кинжала."],
        None,
    ),
    "cite_turn": (
        r"citeturn\d+[a-z]+\d+",
        ["Текст citeturn0file0 со ссылкой.", "citeturn2search5 в середине строки"],
        ["Прошу процитировать, затем turn to page 5."],
        ("citeturn0file0 citeturn2search5", 2),
    ),
    "sandbox_link": (
        r"\]\(sandbox:/mnt/data/",
        ["[Скачать отчёт](sandbox:/mnt/data/report.xlsx)"],
        ["Развернули окружение sandbox на /mnt/data сервера."],
        ("[A](sandbox:/mnt/data/a.csv) [B](sandbox:/mnt/data/b.csv)", 2),
    ),
    # --- A.7. Невидимые и служебные символы (v2.6) ---
    "openai_pua": (
        "[\ue200-\ue204]",
        ["Amazon Nova даёт ряд возможностей \ue200cite\ue202turn0search3\ue201.",
         "скрытый блок \ue203служебная пометка\ue204 в тексте"],
        ["Обычный текст без служебных символов.",
         "Символ иконки \ue000 из шрифтового набора (другая часть PUA)"],
        ("\ue200cite\ue202turn0search3\ue201", 3),
    ),
    "think_tag": (
        r"</?think>",
        ["<think>Сначала разберу условия задачи…</think> Ответ: 42.",
         "хвост рассуждения…</think> Итоговый ответ ниже."],
        ["Я думаю (think), что это норма.",
         "Тег <thinking> другого формата здесь не считается."],
        ("<think>а</think>", 2),
    ),
    # --- A.8. Сцепки «Источник+цифра» (v2.7) ---
    "source_plus_chain": (
        r"[A-Za-zА-Яа-яЁё)]\+\d+[A-ZА-ЯЁ]",
        ["Стандарт создан комитетом ISO. IT Governance+3ISO+3ISO+3. Он входит в семейство…",
         "адаптирован к облачным средам. Microsoft Learn+3Google Cloud+3."],
        ["стандарт C++11 и C++14 поддерживаются",
         "формула x+1 в каждой строке",
         "оценка 5+ за контрольную",
         "Wikipedia+1."],
        ("Wikipedia+1Реестр+2Архив+3", 2),
    ),
}


def main() -> int:
    fails = 0
    for name, (pattern, positives, negatives, multi) in CASES.items():
        rx = re.compile(pattern)
        for s in positives:
            if not rx.search(s):
                print(f"ПРОВАЛ {name}: прямой образец не пойман: {s!r}")
                fails += 1
        for s in negatives:
            if rx.search(s):
                print(f"ПРОВАЛ {name}: ложное срабатывание на: {s!r}")
                fails += 1
        if rx.search(""):
            print(f"ПРОВАЛ {name}: срабатывание на пустой строке")
            fails += 1
        if multi is not None:
            text, expected = multi
            got = len(rx.findall(text))
            if got != expected:
                print(f"ПРОВАЛ {name}: многократный образец — ожидалось {expected}, найдено {got}")
                fails += 1

    total = len(CASES)
    if fails:
        print(f"\nИтог: {total} выражений, провалов: {fails}.")
        return 1
    print(f"Итог: {total} из {total} выражений проходят все проверки.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
