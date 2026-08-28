/* Автогенерация из markers.v1.json скриптом generate_js_rules.py. */
const HUMANIZER_MARKERS = {
  "schema_version": "markers.v1",
  "count": 40,
  "rules": [
    {
      "id": "contentReference",
      "class": "A",
      "description": "Внутренняя метка ссылки в выводе ChatGPT",
      "source": ":contentReference\\[oaicite:\\d+\\]\\{index=\\d+\\}",
      "flags": "g"
    },
    {
      "id": "oai_citation",
      "class": "A",
      "description": "Альтернативный формат внутренней ссылки",
      "source": "oai_citation:\\d+‡",
      "flags": "g"
    },
    {
      "id": "oaicite_short",
      "class": "A",
      "description": "Внутренняя метка ссылки в выводе ChatGPT",
      "source": "oaicite:\\d+",
      "flags": "g"
    },
    {
      "id": "turn_search",
      "class": "A",
      "description": "Идентификатор результата поиска во внутренних ссылках ChatGPT",
      "source": "turn\\d+search\\d+",
      "flags": "g"
    },
    {
      "id": "turn_fetch",
      "class": "A",
      "description": "Идентификатор загруженной страницы",
      "source": "turn\\d+fetch\\d+",
      "flags": "g"
    },
    {
      "id": "turn_file",
      "class": "A",
      "description": "Идентификатор фрагмента файла из инструмента file_search; в тексте всплывает как `fileciteturn0file2` или сдвоенный `fileciteturn0file2turn0file6`",
      "source": "turn\\d+file\\d+",
      "flags": "g"
    },
    {
      "id": "ref_name_search",
      "class": "B",
      "description": "Имя сноски в вики-разметке: числовой префикс + имя внутреннего инструмента. Оно может остаться при копировании ответа агента с веб-поиском",
      "source": "<ref\\b[^>]{0,500}\\bname=[\\\"']\\d+(?:search|fetch|file|image|news|video|ref)\\d+[\\\"']",
      "flags": "g"
    },
    {
      "id": "utm_chatgpt",
      "class": "A",
      "description": "OpenAI ChatGPT (веб и приложение)",
      "source": "[?&]utm_source=chatgpt\\.com",
      "flags": "g"
    },
    {
      "id": "utm_openai",
      "class": "A",
      "description": "Инструменты OpenAI (общий формат API)",
      "source": "[?&]utm_source=openai",
      "flags": "g"
    },
    {
      "id": "utm_copilot",
      "class": "A",
      "description": "Microsoft Copilot",
      "source": "[?&]utm_source=copilot\\.com",
      "flags": "g"
    },
    {
      "id": "grok_referrer",
      "class": "B",
      "description": "xAI Grok",
      "source": "[?&]referrer=grok\\.com",
      "flags": "g"
    },
    {
      "id": "attached_file",
      "class": "A",
      "description": "OpenAI ChatGPT при загрузке файлов",
      "source": "attached_file:\\/\\/",
      "flags": "g"
    },
    {
      "id": "grok_card",
      "class": "A",
      "description": "xAI Grok при ссылке на карточку записи в X (бывший Twitter)",
      "source": "grok_card:\\/\\/",
      "flags": "g"
    },
    {
      "id": "grok_render_json",
      "class": "A",
      "description": "xAI Grok: JSON-разметка карточек цитирования вместо ссылки",
      "source": "grok_render_citation_card_json",
      "flags": "g"
    },
    {
      "id": "vertexaisearch",
      "class": "A",
      "description": "Google Gemini, ссылки веб-поиска с привязкой к источникам",
      "source": "vertexaisearch\\.cloud\\.google\\.com/grounding-api-redirect",
      "flags": "g"
    },
    {
      "id": "attributableIndex",
      "class": "A",
      "description": "Внутренние поля разметки в JSON-ответах при использовании инструментов",
      "source": "\\battributableIndex\\b",
      "flags": "g"
    },
    {
      "id": "citation_n",
      "class": "A",
      "description": "Стиль Perplexity и других поисковых ИИ",
      "source": "\\[citation:\\d+\\]",
      "flags": "g"
    },
    {
      "id": "copilot_caret",
      "class": "A",
      "description": "Microsoft Copilot и Bing: сноска-ссылка при копировании ответа",
      "source": "\\[\\^\\d+\\^\\]",
      "flags": "g"
    },
    {
      "id": "assistants_source",
      "class": "A",
      "description": "OpenAI Assistants (поиск по файлам): метка цитаты, скобки-уголки + кинжал",
      "source": "【\\d+(?::\\d+)?†source】",
      "flags": "g"
    },
    {
      "id": "cite_turn",
      "class": "A",
      "description": "ChatGPT: служебная метка цитаты, попавшая в текст при копировании из потока",
      "source": "citeturn\\d+[a-z]+\\d+",
      "flags": "g"
    },
    {
      "id": "sandbox_link",
      "class": "A",
      "description": "ChatGPT (анализ данных): сломанная ссылка на скачивание файла из контейнера",
      "source": "\\]\\(sandbox:/mnt/data/",
      "flags": "g"
    },
    {
      "id": "openai_pua",
      "class": "B",
      "description": "OpenAI ChatGPT: служебные разделители цитат и скрытых блоков",
      "source": "[-]",
      "flags": "g"
    },
    {
      "id": "openai_pua_short",
      "class": "B",
      "description": "OpenAI ChatGPT: короткая форма сноски — только номер, ограждённый невидимыми символами",
      "source": "[]",
      "flags": "g"
    },
    {
      "id": "think_tag",
      "class": "A",
      "description": "DeepSeek R1 и наследники, другие открытые модели с режимом рассуждения (через API и локальный запуск)",
      "source": "^\\s*</?think>|</think>\\s*$",
      "flags": "gm"
    },
    {
      "id": "source_plus_chain",
      "class": "A",
      "description": "OpenAI ChatGPT: ошибка отрисовки сносок",
      "source": "[A-Za-zА-Яа-яЁё)]\\+\\d+(?=[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё&.\\-]*(?: [A-ZА-ЯЁ][A-Za-zА-Яа-яЁё&.\\-]*){0,3}\\+\\d)",
      "flags": "g"
    },
    {
      "id": "gemini_cite_start",
      "class": "A",
      "description": "Google Gemini: внутренняя метка начала цитируемого фрагмента при анализе PDF",
      "source": "\\[cite_start\\]",
      "flags": "g"
    },
    {
      "id": "gemini_cite_n",
      "class": "A",
      "description": "Google Gemini: ссылка на фрагмент источника; с v3.2 выражение покрывает и перечисление нескольких фрагментов через запятую",
      "source": "\\[[Cc]ite:\\s?\\d+(?:,\\s?\\d+)*\\]",
      "flags": "g"
    },
    {
      "id": "gemini_span",
      "class": "A",
      "description": "Google Gemini: внутренние span-метки границ фрагментов; всплывают при копировании ответа с подсветкой источников",
      "source": "\\[span_\\d+\\][\\[(](?:start_span|end_span)[\\])]",
      "flags": "g"
    },
    {
      "id": "zero_width",
      "class": "B",
      "description": "Наблюдались у ряда моделей (обзорные источники весны 2025; атрибуция конкретной версии не подтверждена); расширение класса — публичный разбор watermarks-remover, 2026-08-13",
      "source": "[​‌‎‏‪-‮⁠-⁤⁦-⁩﻿￹-￻]|(?<![🀀-🫿☀-➿️🇦-🇿])‍(?![🀀-🫿☀-➿️🇦-🇿])",
      "flags": "gu"
    },
    {
      "id": "writing_block",
      "class": "A",
      "description": "Writing-разметка; атрибуция версии не подтверждена",
      "source": ":::\\w+\\{variant",
      "flags": "g"
    },
    {
      "id": "deepseek_line_ref",
      "class": "A",
      "description": "DeepSeek и производные модели: ссылка на строки источника",
      "source": "【\\d+†L\\d+(?:-L?\\d+)?】",
      "flags": "g"
    },
    {
      "id": "grok_card_tag",
      "class": "A",
      "description": "xAI Grok: XML-тег карточки цитирования после сноски",
      "source": "<grok-card\\b[^>]*\\bcitation_card\\b",
      "flags": "g"
    },
    {
      "id": "turn_other",
      "class": "A",
      "description": "Идентификаторы из других инструментов ChatGPT: изображения, новости, видео, ссылки на источники; всплывают при копировании ответов с мультимедиа",
      "source": "turn\\d+(?:image|news|video|ref)\\d+",
      "flags": "g"
    },
    {
      "id": "attached_web_bracket",
      "class": "A",
      "description": "Perplexity (с осени 2025; возможно и другие поисковые ИИ): скобочная форма ссылок на прикреплённые файлы и веб-результаты в конце предложений",
      "source": "\\[(?:attached_file|web):\\d+\\]",
      "flags": "g"
    },
    {
      "id": "perplexity_s3",
      "class": "A",
      "description": "Perplexity: ссылки на Amazon S3-bucket с этим идентификатором в адресе; всплывают при копировании ответа с привязкой к источникам",
      "source": "ppl-ai-file-upload",
      "flags": "g"
    },
    {
      "id": "generated_ref_id",
      "class": "A",
      "description": "ChatGPT: редкая служебная метка сгенерированного идентификатора ссылки, всплывает при сбое отрисовки цитат",
      "source": "citegenerated-reference-identifier",
      "flags": "g"
    },
    {
      "id": "placeholder_url",
      "class": "B",
      "description": "Placeholder-URL из шаблонных ответов: ИИ выдаёт структуру ссылки, которую пользователь должен заполнить, но публикует без правки",
      "source": "\\b(?:INSERT_SOURCE_URL(?:_\\d+)?|URL_HERE|PASTE_\\w+_URL_HERE)\\b",
      "flags": "g"
    },
    {
      "id": "placeholder_date",
      "class": "B",
      "description": "Placeholder-дата из шаблонных ответов: ИИ подставляет заглушку вместо неизвестной даты (чаще всего — «дата обращения» в списке литературы)",
      "source": "\\b(?:19|20)\\d{2}-(?:0[1-9]|1[0-2]|[Xx]{2})-[Xx]{2}\\b",
      "flags": "g"
    },
    {
      "id": "invisible_layout",
      "class": "B",
      "description": "Публичный разбор классов меток watermarks-remover, 2026-08-13; классовое описание, атрибуция конкретных моделей не подтверждена",
      "source": "­|[  　]|(?<![🀀-🫿☀-➿🇦-🇿©®‼⁉™ℹ↔-↙↩-↪⌚-⌛⌨⏏⏩-⏺Ⓜ▪-◾⤴-⤵⬀-⯿〰〽㊗㊙])[︀-️](?![🀀-🫿☀-➿🇦-🇿⃣])",
      "flags": "gu"
    },
    {
      "id": "unicode_tags",
      "class": "B",
      "description": "Стеганографические инструменты (SteganoPrompt, arXiv:2605.16336, AIES 2026): нагрузка кодируется как `chr(0xE0000 + ord(c))` и вставляется в видимый текст; модель, получившая промпт дословно, переносит метку в ответ",
      "source": "(?<![🏴🏳️󠀀-󠁿])[󠀀-󠁿]",
      "flags": "gu"
    }
  ]
};
window.HUMANIZER_MARKERS = HUMANIZER_MARKERS;
