#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Прогон регулярных выражений из references/chatbot-artifacts.md
по проверочным образцам из tests/test-fixtures.md.

Каждое выражение проходит три уровня:
  1. Прямой образец  — выражение обязано сработать.
  2. Отрицательный   — похожий, но не машинный текст; срабатывать не должно.
  3. Граничный       — пустая строка и многократные совпадения; без падений.

Только стандартная библиотека. Запуск:  python3 scripts/check_markers.py
Код возврата 0 — все проверки пройдены, 1 — есть провалы.

При добавлении нового выражения в chatbot-artifacts.md сюда добавляется
блок с образцами, а парные образцы — в tests/test-fixtures.md.
Ни одно работающее правило не удаляется (см. принцип в tests/test-fixtures.md).
"""

import glob
import json
import re
import unicodedata
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

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
    "turn_file": (
        r"turn\d+file\d+",
        ["Вывод обрывается метками fileciteturn0file2turn0file6 в конце.",
         "одиночная метка turn0file11 после цитаты"],
        ["turn the file over", "return file 5 to the archive"],
        ("fileciteturn0file2turn0file6", 2),
    ),
    "ref_name_search": (
        r"<ref\b[^>]{0,500}\bname=[\"']\d+(?:search|fetch|file|image|news|video|ref)\d+[\"']",
        [
            '<ref name="0search12">',
            '<ref name="2file0">',
            '<ref name="1news4" />',
        ],
        [
            '<ref name="search12">',
            '<ref name="source12">',
            '<ref name="turn0search0">',
            'ref name="0search12" без тега ref',
        ],
        ('<ref name="0search0"> <ref name="0search1"> <ref name="2file3">', 3),
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
    "utm_copilot": (
        r"[?&]utm_source=copilot\.com",
        ["https://example.com/?utm_source=copilot.com",
         "https://example.com/?id=7&utm_source=copilot.com"],
        ["utm_source=copilot.com упомянут в статье об отслеживании",
         "https://example.com/?utm_source=chatgpt.com"],
        None,
    ),
    "grok_referrer": (
        r"[?&]referrer=grok\.com",
        ["https://x.com/post?referrer=grok.com",
         "https://example.com/?id=1&referrer=grok.com"],
        ["referrer=grok.com упомянут без URL-параметра",
         "https://example.com/?referrer=other.com"],
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
    "grok_render_json": (
        r"grok_render_citation_card_json",
        ['[](grok_render_citation_card_json={"cardIds":["3bb883"]})'],
        ["grok render citation card json обсуждают в документации"],
        ('[](grok_render_citation_card_json={"cardIds":["1"]}) [](grok_render_citation_card_json={"cardIds":["2"]})', 2),
    ),
    "vertexaisearch": (
        r"vertexaisearch\.cloud\.google\.com/grounding-api-redirect",
        # Схема https:// в образце опущена намеренно: выражению нужен host+path
        # самой приметы, а полный URL в поставляемом файле сканеры безопасности
        # принимают за канал раздачи. Подлинная форма — в research/ и tests/,
        # они в архив скилла не входят.
        ["ссылка vertexaisearch.cloud.google.com/grounding-api-redirect/AbCdEf в тексте"],
        ["vertexaisearch.cloud.google.com без пути",
         "обычная страница продукта cloud.google.com/vertex-ai-search"],
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
    # Короткая форма сноски ChatGPT: одиночная цифра, ограждённая U+EA01/U+EA02 (v3.2)
    "openai_pua_short": (
        "[\uea01\uea02]",
        ["известная по ролям в сериале.\uea012\uea02",
         "высокий рейтинг на агрегаторе.\uea015\uea02 Следующее предложение."],
        ["Обычный текст без служебных символов с цифрой 2 в конце.",
         "Символ иконки \ue000 из шрифтового набора (другая часть PUA)",
         "Служебный разделитель \ue200 из длинной формы (своё выражение openai_pua)"],
        ("Первое.\uea012\uea02 Второе.\uea013\uea02", 4),
    ),
    # Только на границе строки. Упоминание тега внутри связного предложения
    # («у модели есть служебный тег <think>») — это текст О reasoning-моделях,
    # а не их вывод. Осознанная потеря recall в середине строки: цена за то,
    # чтобы техническая статья не помечалась как машинная.
    "think_tag": (
        r"(?m)^\s*</?think>|</think>\s*$",
        ["<think>Сначала разберу условия задачи…</think> Ответ: 42.",
         "</think> Итоговый ответ ниже."],
        ["Я думаю (think), что это норма.",
         "Тег <thinking> другого формата здесь не считается.",
         "У некоторых моделей есть служебный тег <think> для черновика."],
        ("<think>а</think>", 2),
    ),
    # --- A.8. Сцепки «Источник+цифра» (v2.7) ---
    # Требуются не меньше двух сегментов «+число»: одиночная склейка вида
    # «Excel+1С» встречается в живой речи об офисных программах и тарифах.
    # Цена сужения: одиночную склейку выражение больше не ловит, её ищут глазами.
    "source_plus_chain": (
        r"[A-Za-zА-Яа-яЁё)]\+\d+(?=[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё&.\-]*"
        r"(?: [A-ZА-ЯЁ][A-Za-zА-Яа-яЁё&.\-]*){0,3}\+\d)",
        ["Стандарт создан комитетом ISO. IT Governance+3ISO+3ISO+3. Он входит в семейство…",
         "адаптирован к облачным средам. Microsoft Learn+3Google Cloud+3."],
        ["стандарт C++11 и C++14 поддерживаются",
         "формула x+1 в каждой строке",
         "оценка 5+ за контрольную",
         "Wikipedia+1.",
         "связка Excel+1С в резюме",
         "пакет Word+2Excel для офиса",
         "тариф Про+3Максимум на месяц",
         "Excel+1С и формула x+1 рядом"],
        ("Wikipedia+1Реестр+2Архив+3", 2),
    ),
    # --- A.9. Метки цитирования Gemini (v2.9) ---
    "gemini_cite_start": (
        r"\[cite_start\]",
        ["[cite_start]Компания основана в 1994 году и с тех пор…",
         "Вывод содержит [cite_start] в середине строки."],
        ["функция cite_start() в коде без скобок вокруг",
         "[cite start] с пробелом вместо подчёркивания"],
        ("[cite_start]Первое. [cite_start]Второе.", 2),
    ),
    "gemini_cite_n": (
        r"\[[Cc]ite:\s?\d+(?:,\s?\d+)*\]",
        ["Выручка выросла на 12% [cite: 8] по итогам года.",
         "Согласно отчёту [Cite: 12], план выполнен.",
         "Работала с клиентами в медицине и недвижимости [cite: 19, 20, 21]."],
        ["[citation needed] (Википедийный шаблон)",
         "[citation:3] — метка DeepSeek, у неё своё выражение",
         "команда \\cite{ivanov2024} в LaTeX"],
        ("[cite: 1][cite: 2][Cite: 3]", 3),
    ),
    # --- A.9 доп. span-метки Gemini (v3.5) ---
    "gemini_span": (
        r"\[span_\d+\][\[(](?:start_span|end_span)[\])]",
        ["Альбом вышел[span_2](start_span) в августе 1986[span_2](end_span).",
         "Форма заголовка раздела: [span_1][start_span]",
         "Текст [span_12](start_span)фрагмент[span_12](end_span) целиком."],
        ["[span_2] без start_span/end_span",
         "[start_span] без номера span",
         "[span_A](start_span) — буква вместо номера"],
        ("[span_3](start_span)Альбом[span_3](end_span) и [span_4](start_span)сингл[span_4](end_span)", 4),
    ),
    # --- A.10. Символы нулевой ширины (v2.9) ---
    # ZWJ (U+200D) — легальный символ составных эмодзи: семья, флаги,
    # профессии. Он считается маркером только вне эмодзи-контекста;
    # остальные символы нулевой ширины ловятся как раньше.
    "zero_width": (
        # Биди-контролы (U+200E/200F, U+202A–U+202E, U+2066–U+2069),
        # невидимые операторы (U+2061–U+2064) и межстрочные аннотации
        # (U+FFF9–U+FFFB) — тот же класс скрытой разметки, что и нулевые
        # пробелы: в скопированном тексте они не возникают сами (v3.11,
        # классы меток watermarks-remover, публичный разбор 2026-08-13).
        "[\u200b\u200c\u200e\u200f\u202a-\u202e\u2060-\u2064"
        "\u2066-\u2069\ufeff\ufff9-\ufffb]|"
        "(?<![\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\U0001F1E6-\U0001F1FF])"
        "\u200d"
        "(?![\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\U0001F1E6-\U0001F1FF])",
        ["\u0421\u043b\u043e\u0432\u043e\u200b\u0440\u0430\u0437\u043e\u0440\u0432\u0430\u043d\u043e \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u043c \u043d\u0443\u043b\u0435\u0432\u043e\u0439 \u0448\u0438\u0440\u0438\u043d\u044b.",
         "\u041d\u0435\u0432\u0438\u0434\u0438\u043c\u044b\u0439 \u0441\u043e\u0435\u0434\u0438\u043d\u0438\u0442\u0435\u043b\u044c\u2060\u0432\u043d\u0443\u0442\u0440\u0438 \u0442\u0435\u043a\u0441\u0442\u0430.",
         "\u041c\u0435\u0442\u043a\u0430\ufeff\u043f\u043e\u0441\u0440\u0435\u0434\u0438 \u0441\u0442\u0440\u043e\u043a\u0438.",
         "\u0441\u043b\u043e\u200d\u0432\u043e \u0441 \u0441\u043e\u0435\u0434\u0438\u043d\u0438\u0442\u0435\u043b\u0435\u043c \u0432\u043d\u0443\u0442\u0440\u0438 \u043a\u0438\u0440\u0438\u043b\u043b\u0438\u0446\u044b"],
        ["\u041e\u0431\u044b\u0447\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0441 \u043e\u0431\u044b\u0447\u043d\u044b\u043c\u0438 \u043f\u0440\u043e\u0431\u0435\u043b\u0430\u043c\u0438.",
         "\u0423\u0437\u043a\u0438\u0439 \u043d\u0435\u0440\u0430\u0437\u0440\u044b\u0432\u043d\u044b\u0439 \u043f\u0440\u043e\u0431\u0435\u043b\u202f\u043d\u0435 \u0432\u0445\u043e\u0434\u0438\u0442 \u0432 \u0432\u044b\u0440\u0430\u0436\u0435\u043d\u0438\u0435 (\u0440\u0443\u0447\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430).",
         "\u0441\u0435\u043c\u044c\u044f \U0001F468\u200d\U0001F469\u200d\U0001F467 \u0432 \u043f\u043e\u0434\u043f\u0438\u0441\u0438 \u043a \u0444\u043e\u0442\u043e",
         "\u0444\u043b\u0430\u0433 \U0001F3F3\uFE0F\u200d\U0001F308 \u0432 \u0447\u0430\u0442\u0435",
         "\u043a\u043e\u0441\u043c\u043e\u043d\u0430\u0432\u0442 \U0001F469\u200d\U0001F680 \u043d\u0430 \u0430\u0432\u0430\u0442\u0430\u0440\u043a\u0435"],
        ("\u0430\u200b\u0431\u200c\u0432\u200d\u0433", 3),
    ),
    # --- A.11. Блоки «writing» ChatGPT (v3.0) ---
    "writing_block": (
        r":::\w+\{variant",
        [':::writing{variant="document" id="68427"}',
         'Черновик письма ниже. :::writing{variant="email" id="51724"}',
         ':::écriture{variante="document" id="28471"}'],
        [":::note — директива Docusaurus без атрибута variant",
         ':::tip{title="Совет"} — атрибут другой',
         "обычное троеточие в конце фразы..."],
        (':::writing{variant="email" id="11111"} текст ::: :::writing{variant="chat_message" id="22222"}', 2),
    ),
    # --- A.12. DeepSeek/derivative line references (v3.1) ---
    "deepseek_line_ref": (
        r"【\d+†L\d+(?:-L?\d+)?】",
        ["В 2024 году кампания выросла【85†L261-269】.",
         "Альбом вышел【854†L119-123】 в 2024 году.",
         "【854†L119-L123】 — форма с L после дефиса."],
        ["OpenAI Assistants метка 【1†source】 ловится другим выражением.",
         "Декоративные уголки 【примечание】 без строк.",
         "Обычная сноска [1] не должна срабатывать."],
        ("【29†L582-589】【32†L142-149】", 2),
    ),
    # --- A.4 доп. Grok XML-тег (v3.1) ---
    "grok_card_tag": (
        r"<grok-card\b[^>]*\bcitation_card\b",
        ['<grok-card data-id="e8ff4f" data-type="citation_card">',
         '\u0422\u0435\u043a\u0441\u0442...<grok-card data-id="abc" data-type="citation_card">'],
        ["<grok-card> \u0431\u0435\u0437 \u0430\u0442\u0440\u0438\u0431\u0443\u0442\u0430 citation_card",
         "\u043e\u0431\u044b\u0447\u043d\u044b\u0439 XML-\u0442\u0435\u0433 <div>"],
        None,
    ),
    # --- A.2 доп. turn image/news/video/ref (v3.1) ---
    "turn_other": (
        r"turn\d+(?:image|news|video|ref)\d+",
        ["\u0424\u043e\u0442\u043e turn0image0 \u0432 \u0442\u0435\u043a\u0441\u0442\u0435.", "turn0news0 \u0432 \u0441\u0435\u0440\u0435\u0434\u0438\u043d\u0435", "turn0video0", "turn0ref0"],
        ["turn left and image again", "turnaround news"],
        ("turn0image0 turn0news0 turn0video0", 3),
    ),
    # --- A.5 доп. скобочная форма ссылок инструментов (v3.1) ---
    "attached_web_bracket": (
        r"\[(?:attached_file|web):\d+\]",
        ["\u0421\u043c. [attached_file:1] \u0432 \u043e\u0442\u0432\u0435\u0442\u0435.", "\u0426\u0438\u0442\u0430\u0442\u0430 [web:3] \u0438\u0437 \u043f\u043e\u0438\u0441\u043a\u0430."],
        ["[attach:1] \u0434\u0440\u0443\u0433\u043e\u0439 \u0444\u043e\u0440\u043c\u0430\u0442", "\u043e\u0431\u044b\u0447\u043d\u0430\u044f \u0441\u043d\u043e\u0441\u043a\u0430 [1]"],
        ("[attached_file:1][web:2][web:3]", 3),
    ),
    # --- A.5 доп. S3-ссылки Perplexity (v3.5) ---
    "perplexity_s3": (
        r"ppl-ai-file-upload",
        # Схема https:// в образцах опущена намеренно: выражению нужен только
        # идентификатор бакета ppl-ai-file-upload, а полный адрес S3 в
        # поставляемом файле сканеры безопасности принимают за канал раздачи
        # файлов. Подлинная форма приметы — в tests/fixtures/perplexity-s3.txt
        # и в реестре research/fixtures/marker-sources.json; они в архив скилла
        # не входят. Отрицательный образец сохраняет смысл: другой бакет
        # (other-bucket) на том же сервисе под выражение не подпадает.
        ["Источник: ссылка на бакет ppl-ai-file-upload в пути (сервис s3.amazonaws)",
         "Ссылка на бакет ppl-ai-file-upload после имени сервиса s3.amazonaws в списке литературы."],
        ["упоминание ppl ai file upload с пробелами",
         "обычная ссылка на другой бакет other-bucket на сервисе s3.amazonaws"],
        None,
    ),
    # --- A.6 доп. generated-reference-identifier (v3.1) ---
    "generated_ref_id": (
        r"citegenerated-reference-identifier",
        ["\u0422\u0435\u043a\u0441\u0442 citegenerated-reference-identifier \u0432 \u0432\u044b\u0432\u043e\u0434\u0435."],
        ["generated reference identifier \u0447\u0435\u0440\u0435\u0437 \u043f\u0440\u043e\u0431\u0435\u043b"],
        None,
    ),
    # --- A.5 доп. placeholder URLs (v3.1) ---
    "placeholder_url": (
        r"\b(?:INSERT_SOURCE_URL(?:_\d+)?|URL_HERE|PASTE_\w+_URL_HERE)\b",
        ["\u0412\u0441\u0442\u0430\u0432\u044c\u0442\u0435 INSERT_SOURCE_URL_30 \u0441\u044e\u0434\u0430.", "\u0421\u043c. URL_HERE \u0432 \u0448\u0430\u0431\u043b\u043e\u043d\u0435.", "PASTE_SPOTIFY_TRACK_URL_HERE"],
        ["insert source url \u0432 \u043e\u0431\u044b\u0447\u043d\u043e\u0439 \u0444\u0440\u0430\u0437\u0435", "\u0432\u0441\u0442\u0430\u0432\u044c\u0442\u0435 URL \u0441\u044e\u0434\u0430"],
        ("INSERT_SOURCE_URL URL_HERE PASTE_TRACK_URL_HERE", 3),
    ),
    # --- A.5 доп. placeholder-даты (v3.1) ---
    # Год ограничен формами 19xx/20xx, месяц — 01-12 либо XX. Складские и
    # товарные номера вида «1234-56-xx», «3985-77-XX» под выражение больше не
    # попадают; невозможный месяц («2025-13-XX») тоже отсекается.
    "placeholder_date": (
        r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2]|[Xx]{2})-[Xx]{2}\b",
        ["дата обращения: 2025-XX-XX.",
         "|date=2022-11-XX |publisher=…",
         "access-date=2025-xx-xx"],
        ["обычная дата 2025-11-30 не срабатывает",
         "артикул 2025-XX-XXL не срабатывает",
         "диапазон 2024-2025 без дня",
         "код изделия 1234-56-xx",
         "серия 3985-77-XX",
         "невозможный месяц 2025-13-XX"],
        ("2025-XX-XX и 2022-11-XX в одном списке литературы", 2),
    ),
    # --- B. Невидимая раскладка: мягкий перенос, наборные пробелы,
    # вариационные селекторы вне эмодзи (v3.11) ---
    # Класс B: каждый символ встречается и в легальной вёрстке, но в
    # скопированном тексте это артефакт. NBSP (U+00A0) и узкий NBSP
    # (U+202F) не входят — это норма русской типографики; VS16 (U+FE0F)
    # в эмодзи легален и пропускается тем же правилом, что ZWJ в A.7.
    "invisible_layout": (
        # Наборные пробелы U+2000–U+200A в маркер НЕ входят: они легитимны
        # в оцифрованных русских классиках (Викитека: тонкий пробел U+2009
        # в Перельмане) — человеческий корпус это поймал сразу. Остаются
        # только пробелы, которых в русской типографике не бывает.
        # Гард селекторов: VS15/VS16 легальны после любой эмодзи-базы
        # (Extended_Pictographic), а не только после блоков
        # U+1F000–U+1FAFF / U+2600–U+27BF: клавиатура U+2328, часы
        # U+231A–U+231B, стрелки U+2194–U+2199, звёзды U+2B00–U+2BFF,
        # геометрия U+25AA–U+25FE и др. дают эмодзи-презентацию только с
        # селектором. Кейкап-клавиши «1️⃣» = база-цифра + VS16 + U+20E3
        # защищены правой стороной гарда (ограничитель U+20E3 в
        # lookahead); бродячий VS16 после цифры без ограничителя —
        # по-прежнему артефакт. Без этого гард стрипал селектор из ⌨️
        # и 1️⃣, ломая эмодзи (кейс прогона Q3 суперпозиции, 2026-08-28).
        "\u00ad|[\u1680\u205f\u3000]|"
        "(?<![\U0001F000-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF"
        "\u00A9\u00AE\u203C\u2049\u2122\u2139"
        "\u2194-\u2199\u21A9-\u21AA\u231A-\u231B\u2328\u23CF"
        "\u23E9-\u23FA\u24C2\u25AA-\u25FE\u2934-\u2935"
        "\u2B00-\u2BFF\u3030\u303D\u3297\u3299])"
        "[\ufe00-\ufe0f]"
        "(?![\U0001F000-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF\u20E3])",
        ["мягкий перенос сло\u00adво",
         "огхамский пробел: а\u1680б",
         "идеографический пробел: а\u3000б",
         "средний математический пробел: а\u205fб",
         "вариационный селектор вне эмодзи: текст\ufe0f."],
        ["обычный неразрывный пробел\u00a0внутри предложения",
         "узкий неразрывный пробел\u202fпосле числа",
         "наборный пробел: а\u2002б",
         "тонкий пробел: а\u2009б",
         "сердце ❤\ufe0f и солнце ☀\ufe0f в чате",
         "светофор 🚦 без селектора",
         "клавиатура \u2328\ufe0f рядом с текстом",
         "наручные часы \u231a\ufe0f и песочные \u231b\ufe0f",
         "звезда \u2b50\ufe0f и стрелка \u2194\ufe0f",
         "клавиша 1\ufe0f\u20e3 и решётка #\ufe0f\u20e3",
         "радужный флаг \U0001F3F3\ufe0f\u200d\U0001F308"],
        ("а\u00adб и в\u1680г и д\ufe0fе", 3),
    ),
    # I.28: скрытая ASCII-нагрузка в блоке Unicode Tags (U+E0000–U+E007F).
    # Источник уровня P: arXiv:2605.16336v2 (AIES 2026, SteganoPrompt) —
    # печатная ASCII-строка кодируется как chr(0xE0000 + ord(c)) и
    # переживает копипаст; модель-пересказчик переносит метку в ответ.
    # Класс B: легитимный источник — флаги-эмодзи (U+1F3F4 или
    # U+1F3F3+FE0F + теги + отмена U+E007F); guard повторяет TAG_STRIP_RX
    # из filemarks/text_layer.py: тег, которому предшествует флаг или другой
    # тег (внутри последовательности), не считается.
    "unicode_tags": (
        "(?<![\U0001F3F4\U0001F3F3\ufe0f\U000E0000-\U000E007F])"
        "[\U000E0000-\U000E007F]",
        ["скрытая метка в ответе: \U000E0041\U000E0049 и продолжение текста",
         "конец предложения.\U000E0074\U000E0065\U000E0073\U000E0074 следующая строка"],
        ["флаг Англии \U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F в тексте",
         "радужный флаг \U0001F3F3\ufe0f\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F рядом",
         "обычный текст без невидимых символов"],
        ("метка одна \U000E0041\U000E0042 и метка две \U000E0043\U000E0044", 2),
    ),
}

# Класс кейса: "A" — даёт вердикт «машинный текст» сам по себе,
# "B" — контекстный маркер, который сам по себе вердикта не даёт
# (предупреждение, не падает под гейт --scan --class a).
# Источник классов: references/chatbot-artifacts*.md (пометки «(класс B)»)
# и markers.v1.json (генерируется scripts/export_markers.py). Маркер без
# пометки класса — класс A. Класс должен совпадать с ФАКТИЧЕСКИМ выводом
# export_markers.py; целостность проверяется в main().
CLASS_OF = {
    # --- Класс B: контекстные маркеры (не дают вердикта сами по себе) ---
    "ref_name_search": "B",
    "grok_referrer": "B",
    "openai_pua": "B",
    "openai_pua_short": "B",
    "zero_width": "B",
    "placeholder_url": "B",
    "placeholder_date": "B",
    "invisible_layout": "B",
    "unicode_tags": "B",
    # --- Класс A: все остальные 31 кейс ---
    "contentReference": "A",
    "oai_citation": "A",
    "oaicite_short": "A",
    "turn_search": "A",
    "turn_fetch": "A",
    "turn_file": "A",
    "utm_chatgpt": "A",
    "utm_openai": "A",
    "utm_copilot": "A",
    "attached_file": "A",
    "grok_card": "A",
    "grok_render_json": "A",
    "vertexaisearch": "A",
    "attributableIndex": "A",
    "citation_n": "A",
    "copilot_caret": "A",
    "assistants_source": "A",
    "cite_turn": "A",
    "sandbox_link": "A",
    "think_tag": "A",
    "source_plus_chain": "A",
    "gemini_cite_start": "A",
    "gemini_cite_n": "A",
    "gemini_span": "A",
    "writing_block": "A",
    "deepseek_line_ref": "A",
    "grok_card_tag": "A",
    "turn_other": "A",
    "attached_web_bracket": "A",
    "perplexity_s3": "A",
    "generated_ref_id": "A",
}


# Теневой набор невидимых/форматных символов слоя A: zero-width, биди-
# контролы, невидимые операторы, межстрочные аннотации, мягкий перенос,
# экзотические пробелы, монгольские гласные, арабский знак, tag-символы и
# вариационные селекторы. Вставка любого из них внутрь маркера класса A
# раньше разбивала совпадение: «turn0<U+200B>search0» давал лишь класс B
# (zero_width), и гейт --class a проходил (аудит 2026-08-28). Теневая копия
# строки без этих символов сканируется теми же выражениями; совпадение в
# тени считается находкой. Класс A не расширяется — реестр не раздувается.
_SHADOW_INVISIBLES = re.compile(
    "[\u00ad\u061c\u034f\u1680\u180b-\u180e\u200b-\u200f"
    "\u202a-\u202e\u205f\u2060-\u2069\u206a-\u206f\u3000"
    "\ufe00-\ufe0f\ufeff\ufff9-\ufffb\U000e0000-\U000e007f]")


URL_MASK_RX = re.compile(r"(?:https?://|www\.)[^\s<>«»\"')\]]+")
URL_MARKER_HINTS = ("utm", "card", "url", "link")


def _mask_urls(line: str) -> str:
    """Заменяет URL-спаны пробелами той же длины: позиции сохранены,
    не-URL маркеры не ловят артефакты внутри чужих ссылок (F9)."""
    def rep(m):
        return " " * (m.end() - m.start())
    return URL_MASK_RX.sub(rep, line)


def _is_url_marker(name: str) -> bool:
    if any(h in name for h in URL_MARKER_HINTS):
        return True
    pat = CASES[name][0] if name in CASES else ""
    return ("http" in pat or "www" in pat or "referrer" in pat
            or "vertex" in pat or "grounding" in pat)


def _case_since():
    out = {}
    try:
        import json as _json
        fp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "research", "fixtures", "marker-sources.json")
        for rec in _json.load(open(fp, encoding="utf-8")):
            name = rec.get("case")
            if name:
                out[name] = rec.get("accessed", "")
    except Exception:
        pass
    return out


CASE_SINCE = _case_since()


def _backtick_prefix(line: str) -> list:
    """Префиксные количества `обратных кавычек` — один проход на строку.

    Возвращает (prefix, total): prefix[i] — число бэктиков в line[:i];
    проверка «совпадение внутри кавычек» сводится к двум чтениям массива
    вместо пересчёта срезов на каждое совпадение (раньше — квадратично
    на минифицированных однострочниках из десятков тысяч совпадений).
    """
    prefix = [0] * (len(line) + 1)
    count = 0
    for i, ch in enumerate(line):
        if ch == "`":
            count += 1
        prefix[i + 1] = count
    return prefix, count


def _inside_backticks(prefix: list, total: int, start: int, end: int) -> bool:
    """Совпадение внутри `обратных кавычек` — это документация, не артефакт."""
    return prefix[start] % 2 == 1 and (total - prefix[end]) >= 1


def _line_matches(line: str, compiled: dict) -> list:
    """Совпадения всех выражений в строке без вложенных дублей.

    Одна примета может совпасть с несколькими выражениями сразу:
    «citeturn0file0» ловится и cite_turn, и turn_file, а полная форма
    «:contentReference[oaicite:0]{index=0}» — ещё и усечённой oaicite_short.
    В отчёте это раздувало счёт: один артефакт печатался два-три раза.
    Совпадение, целиком лежащее внутри более длинного совпадения другого
    выражения, отбрасывается; пересечения без вложенности (PUA-разделители
    вокруг turn-метки) сохраняются. На вердикт это не влияло — любое
    совпадение класса A достаточно, — но счёт в отчёте был завышен.
    Дедупликация линейная: сортировка по (началу, длине) и однопроходное
    слияние — квадратичный вариант на 100-КБ строке из невидимых
    символов работал минутами (независимый аудит 2026-08-28).
    """
    line = unicodedata.normalize("NFC", line)
    masked = _mask_urls(line)
    prefix, total_bt = _backtick_prefix(line)
    found = []
    for name, rx in compiled.items():
        use = line if _is_url_marker(name) else masked
        for m in rx.finditer(use):
            if _inside_backticks(prefix, total_bt, m.start(), m.end()):
                continue
            found.append((m.start(), m.end(), name))
    # Сортировка по началу, при равном начале — более длинное первым:
    # контейнер совпадения всегда встречается раньше содержимого.
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept = []
    cover_start = cover_end = -1
    for start, end, name in found:
        if (cover_start <= start and end <= cover_end
                and (end - start) < (cover_end - cover_start)):
            continue
        kept.append((start, end, name))
        if end > cover_end:
            cover_start, cover_end = start, end
    kept.sort()
    return kept


def _decode_bytes(data: bytes, encoding=None):
    """F13: BOM-детект + utf-8 strict + эвристика cp1251/KOI8-R."""
    if encoding:
        return data.decode(encoding, errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    cp = data.count(b"\xe9") + data.count(b"\xf3") + data.count(b"\xe0")
    ko = data.count(b"\xcb") + data.count(b"\xcf") + data.count(b"\xc1")
    return data.decode("koi8-r" if ko > cp else "cp1251", errors="replace")


def _console_text(text: str, encoding=None) -> str:
    """Сохраняет диагностику читаемой и на консолях без поддержки PUA/BOM."""
    encoding = encoding or sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="backslashreplace").decode(encoding)


def _fenced_lines(lines: list) -> set:
    """Номера строк внутри ЗАКРЫТЫХ блоков кода (``` и ~~~).

    Документация маркеров в справочниках живёт в fenced-блоках; раньше
    --scan видел однострочные бэктики, но не блочные, и <think>…</think>
    внутри примера кода давал ложные срабатывания think_tag
    Незакрытый забор не маскирует остаток файла:
    содержимое после него продолжает проверяться (как в
    scan_soft_signals._fenced_lines). Отступ до трёх пробелов допускается.
    """
    inside = set()
    fence_char = None
    fence_len = 0
    open_line = None
    for n, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if len(line) - len(stripped) > 3:
            continue
        if fence_char is None:
            if stripped.startswith("```"):
                fence_char, open_line = "`", n
                fence_len = len(stripped) - len(stripped.lstrip("`"))
            elif stripped.startswith("~~~"):
                fence_char, open_line = "~", n
                fence_len = len(stripped) - len(stripped.lstrip("~"))
            continue
        close_len = len(stripped) - len(stripped.lstrip(fence_char))
        if (close_len >= fence_len
                and stripped.rstrip() == fence_char * close_len):
            for k in range(open_line, n + 1):
                inside.add(k)
            fence_char, open_line, fence_len = None, None, 0
    return inside


def scan(paths: list, as_json: bool = False, versions: bool = False) -> int:
    """Прогон всех выражений по произвольным файлам.

    Запуск:  python3 scripts/check_markers.py --scan файл1 [файл2 …]
             python3 scripts/check_markers.py --scan --class a файл1 …
             python3 scripts/check_markers.py --scan файл1 --class a …
             python3 scripts/check_markers.py --scan --json файл1 …
    «-» в списке файлов читает stdin (UTF-8) и обозначается <stdin>.
    Текстовый режим печатает каждое совпадение в формате
    «файл:строка [имя] фрагмент»; --json печатает конверт контракта
    {tool: "humanizer-markers", schema: 1, files: [...]} — по записи на
    файл: file, markers (line, marker, class, fragment, shadow), count,
    warnings_b. В --json текстовые строки совпадений не печатаются:
    stdout обязан быть чистым JSON.
    Совпадения внутри обратных кавычек пропускаются (документация выражений),
    вложенные дубли одного артефакта схлопываются (см. _line_matches).
    Код возврата 0 — чисто, 1 — найдены маркеры, 2 — файл не читается.

    Флаг --class {a|all} (по умолчанию all — обратная совместимость):
      all — текущее поведение: любые совпадения дают код возврата 1.
      a   — код возврата определяется только совпадениями класса A.
            Совпадения класса B печатаются строкой «[B, предупреждение] …»
            и на код возврата не влияют; в итоге раздельно считаются
            «маркеров класса A» и «предупреждений класса B».
    Ограничение: файлы читаются строго как UTF-8;
    файл в cp1251/другой кодировке даёт код 2 с явным сообщением, а не
    молчаливый пропуск или мусорные совпадения.
    """
    class_filter = "all"
    remaining = list(paths)
    if "--class" in remaining:
        idx = remaining.index("--class")
        if idx + 1 >= len(remaining) or remaining[idx + 1] not in ("a", "all"):
            print("--class ожидает значение 'a' или 'all'", file=sys.stderr)
            return 2
        class_filter = remaining[idx + 1]
        del remaining[idx:idx + 2]
    compiled = {name: re.compile(case[0]) for name, case in CASES.items()}
    found = 0
    class_b_warnings = 0
    json_files = []
    for path in remaining:
        label = "<stdin>" if path == "-" else path
        try:
            if path == "-":
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
                lines = sys.stdin.read().splitlines()
            else:
                with open(path, "rb") as fh:
                    lines = _decode_bytes(fh.read()).splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Не удалось прочитать {path}: {exc}", file=sys.stderr)
            if as_json:
                json_files.append({"file": label, "markers": [], "count": 0,
                                   "warnings_b": 0, "error": str(exc)})
                print(json.dumps({"tool": "humanizer-markers", "schema": 1,
                                  "files": json_files,
                                  "error": "вход не читается (код 2)"},
                                 ensure_ascii=False, indent=2))
            return 2
        entry = {"file": label, "markers": [], "count": 0, "warnings_b": 0}
        if not any(line.strip() for line in lines):
            # Градуированный ответ на пустом входе: поиск структурных
            # артефактов не отказывает, но честный статус входа виден.
            entry["scope_note"] = "вне области: пустой вход"
        blocked = _fenced_lines(lines)
        for lineno, line in enumerate(lines, 1):
            if lineno in blocked:
                continue
            direct = _line_matches(line, compiled)
            for _start, _end, name in direct:
                cls = CLASS_OF.get(name, "A")
                fragment = _console_text(line.strip()[:90])
                if class_filter == "a" and cls == "B":
                    class_b_warnings += 1
                    entry["warnings_b"] += 1
                    if not as_json:
                        print(f"[B, предупреждение] {label}:{lineno} [{name}] {fragment}")
                else:
                    found += 1
                    entry["count"] += 1
                    if not as_json:
                        print(f"{label}:{lineno} [{name}] {fragment}")
                entry["markers"].append({"line": lineno, "marker": name,
                                         "class": cls, "fragment": fragment,
                                         "shadow": False})
                if versions:
                    entry["markers"][-1]["since"] = CASE_SINCE.get(name, "")
            # Теневой проход: те же выражения по строке без невидимых
            # символов — ловит маркер, разбитый вставкой (turn0<U+200B>…).
            # Находки, уже пойманные напрямую, повторно не печатаются.
            shadow = _SHADOW_INVISIBLES.sub("", line)
            if shadow != line:
                direct_names = {n for _s, _e, n in direct}
                for _start, _end, name in _line_matches(shadow, compiled):
                    if name in direct_names:
                        continue
                    cls = CLASS_OF.get(name, "A")
                    fragment = _console_text(shadow.strip()[:90])
                    if class_filter == "a" and cls == "B":
                        class_b_warnings += 1
                        entry["warnings_b"] += 1
                        if not as_json:
                            print(f"[B, предупреждение] {label}:{lineno} [{name}] "
                                  f"(теневой) {fragment}")
                    else:
                        found += 1
                        entry["count"] += 1
                        if not as_json:
                            print(f"{label}:{lineno} [{name}] (теневой) {fragment}")
                    entry["markers"].append({"line": lineno, "marker": name,
                                             "class": cls, "fragment": fragment,
                                             "shadow": True})
                    if versions:
                        entry["markers"][-1]["since"] = CASE_SINCE.get(name, "")
        json_files.append(entry)
    if as_json:
        print(json.dumps({"tool": "humanizer-markers", "schema": 1,
                          "files": json_files}, ensure_ascii=False, indent=2))
        return 1 if found else 0
    if class_filter == "a":
        print(f"\nМаркеров класса A: {found}; предупреждений класса B: {class_b_warnings}.")
        return 1 if found else 0
    if found:
        print(f"\nНайдено маркеров: {found}.")
        return 1
    print("Маркеров не найдено.")
    return 0


def main() -> int:
    fails = 0
    # Целостность CLASS_OF ↔ CASES: для каждого кейса есть класс, и в
    # CLASS_OF нет лишних ключей. Рассинхрон — явный ПРОВАЛ гейта.
    missing_class = [name for name in CASES if name not in CLASS_OF]
    extra_class = [name for name in CLASS_OF if name not in CASES]
    bad_value = [name for name, cls in CLASS_OF.items()
                 if name in CASES and cls not in ("A", "B")]
    for name in missing_class:
        print(f"ПРОВАЛ CLASS_OF: нет класса для кейса {name}")
        fails += 1
    for name in extra_class:
        print(f"ПРОВАЛ CLASS_OF: лишний ключ {name} (нет в CASES)")
        fails += 1
    for name in bad_value:
        print(f"ПРОВАЛ CLASS_OF: кейс {name} имеет недопустимый класс {CLASS_OF[name]!r}")
        fails += 1
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

    if _console_text("\ufeff", "ascii") != r"\ufeff":
        print("ПРОВАЛ scan: невидимый символ не экранируется для ASCII-консоли")
        fails += 1

    # Отчёт --scan не должен печатать один артефакт дважды из-за вложенных
    # выражений — и обязан сохранять пересечения без вложенности
    # (PUA-разделители рядом с turn-меткой считаются отдельно).
    compiled_all = {name: re.compile(case[0]) for name, case in CASES.items()}
    for text, expected in (
        (":contentReference[oaicite:0]{index=0}", 1),
        ("fileciteturn0file2turn0file6", 2),
        ("\ue200cite\ue202turn0search3\ue201", 4),
        ("обычная строка без примет", 0),
    ):
        got = len(_line_matches(text, compiled_all))
        if got != expected:
            print("ПРОВАЛ scan-дедупликация: ожидалось %d, найдено %d для %r"
                  % (expected, got, _console_text(text[:40])))
            fails += 1

    # Теневой скан: маркер класса A, разбитый невидимым символом, ловится
    # в тени; легальные эмодзи (ZWJ/VS16) ложных теневых находок не дают.
    for text, should_find in (
        ("turn0\u200bsearch0", True),
        ("link?utm_source=chat\u200bgpt.com", True),
        ("Клавиатура \u2328\ufe0f и радуга \U0001f3f3\ufe0f\u200d\U0001f308", False),
        ("обычный текст без маркеров и без невидимых", False),
    ):
        shadow = _SHADOW_INVISIBLES.sub("", text)
        names = {n for _s, _e, n in _line_matches(shadow, compiled_all)}
        direct_names = {n for _s, _e, n in _line_matches(text, compiled_all)}
        shadow_only = bool(names - direct_names)
        if shadow_only != should_find:
            print("ПРОВАЛ теневой скан: %r — теневых находок %s, ожидалось %s"
                  % (_console_text(text[:40]), shadow_only, should_find))
            fails += 1

    total = len(CASES)
    if fails:
        print(f"\nИтог: {total} выражений, провалов: {fails}.")
        return 1
    print(f"Итог: {total} из {total} выражений проходят все проверки.")
    return 0


def _canon_pattern(text: str) -> str:
    """Каноническая форма для сравнения regex в коде и в markdown-таблицах."""
    text = text.replace("\\|", "|").replace('\\"', '"').replace("\\'", "'")
    out = []
    for c in text:
        o = ord(c)
        if o < 128:
            out.append(c)
        elif o <= 0xFFFF:
            out.append("\\u%04x" % o)
        else:
            out.append("\\U%08x" % o)
    return "".join(out)


def parity(*md_paths: str) -> int:
    """Проверка md↔py паритета: каждое выражение CASES задокументировано в справочнике.

    Справочник разбит на семейство файлов `references/chatbot-artifacts*.md`;
    без явно переданных путей читаются все файлы семейства, и каждое выражение
    обязано найтись хотя бы в одном.
    В markdown-таблицах вертикальная черта экранируется как `\\|`, а невидимые
    символы записаны escape-последовательностями, поэтому обе стороны
    нормализуются через _canon_pattern. Код возврата 0 — все выражения
    задокументированы, 1 — есть недокументированные (regex без описания),
    2 — файлы семейства не найдены или не читаются.
    """
    if not md_paths:
        md_paths = tuple(sorted(glob.glob("references/chatbot-artifacts*.md")))
    if not md_paths:
        print("Не найдены файлы references/chatbot-artifacts*.md", file=sys.stderr)
        return 2
    parts = []
    for md_path in md_paths:
        try:
            with open(md_path, encoding="utf-8") as fh:
                parts.append(_canon_pattern(fh.read()))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Не удалось прочитать {md_path}: {exc}", file=sys.stderr)
            return 2
    doc = "\n".join(parts)
    missing, drift = [], []
    for name, case in CASES.items():
        pat = _canon_pattern(case[0])
        if pat not in doc:
            missing.append(name)
            continue
        # Файл, упоминающий кейс как идентификатор (полный спан в
        # обратных кавычках), обязан нести его точное выражение: порча
        # одной из дублированных строк роняет гейт, а не проходит за
        # счёт целого двойника в соседнем файле. Упоминания имени
        # внутри литералов и прозы не считаются (урок rev6: имена
        # кейсов входят в сами маркеры вроде `:contentReference[...`).
        id_ref = "`" + name + "`"
        for md_path, part in zip(md_paths, parts):
            # Проверка построчная: каждая табличная строка, называющая
            # кейс полным идентификатором, обязана нести его точное
            # выражение в этой же строке. Корректный паттерн в прозе
            # того же файла испорченную строку не оправдывает (rev7),
            # а порча единственной строки не прячется за двойником.
            for line in part.splitlines():
                if line.lstrip().startswith("|") and id_ref in line \
                        and pat not in line:
                    drift.append((name, md_path))
    for name in missing:
        print(f"ПРОВАЛ parity: {name} отсутствует в {', '.join(md_paths)}")
    for name, md_path in drift:
        print(f"ПРОВАЛ parity: табличная строка с {name} в {md_path} "
              f"не несёт точного выражения")
    if missing or drift:
        print(f"Паритет: {len(CASES) - len(missing)}/{len(CASES)} задокументировано.")
        return 1
    print(f"Паритет: все {len(CASES)} выражений задокументированы "
          f"в {len(md_paths)} файлах семейства chatbot-artifacts.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        # scan() разбирает --class {a|all} сам, поэтому передаём весь хвост;
        # --json снимается здесь (конверт контракта вместо текстовых строк).
        rest = sys.argv[2:]
        as_json = "--json" in rest
        use_versions = "--versions" in rest
        if as_json:
            rest = [a for a in rest if a not in ("--json", "--versions")]
        sys.exit(scan(rest, as_json=as_json, versions=use_versions))
    if len(sys.argv) > 1 and sys.argv[1] == "--parity":
        sys.exit(parity(*sys.argv[2:]))
    sys.exit(main())
