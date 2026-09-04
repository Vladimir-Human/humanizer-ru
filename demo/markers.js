/* Автогенерация из markers.v1.json скриптом generate_js_rules.py. */
const HUMANIZER_MARKERS = {
  "schema_version": "markers.v1",
  "count": 40,
  "meta": {
    "rules_version": "markers.v1",
    "markers_count": 40,
    "build_date": "2026-08-26"
  },
  "rules": [
    {
      "id": "contentReference",
      "class": "A",
      "description": "Внутренняя метка ссылки в выводе ChatGPT",
      "source": ":contentReference\\[oaicite:\\d+\\]\\{index=\\d+\\}",
      "flags": "g",
      "explain": {
        "name": "Служебная метка ссылки ChatGPT",
        "why": "Внутренний токен ответа ассистента, который интерфейс не снял при копировании; в рукописном тексте таких меток не бывает.",
        "advice": "Снимите метку полировкой или удалите токен вручную."
      }
    },
    {
      "id": "oai_citation",
      "class": "A",
      "description": "Альтернативный формат внутренней ссылки",
      "source": "oai_citation:\\d+‡",
      "flags": "g",
      "explain": {
        "name": "Сноска ответа ассистента",
        "why": "Формат цитирования из чат-интерфейса, человек так сноски не оформляет.",
        "advice": "Удалите сноску или оформите по своему стилю."
      }
    },
    {
      "id": "oaicite_short",
      "class": "A",
      "description": "Внутренняя метка ссылки в выводе ChatGPT",
      "source": "oaicite:\\d+",
      "flags": "g",
      "explain": {
        "name": "Усечённая сноска ассистента",
        "why": "Короткая форма служебной цитаты ответа модели.",
        "advice": "Удалите токен вместе с квадратными скобками."
      }
    },
    {
      "id": "turn_search",
      "class": "A",
      "description": "Идентификатор результата поиска во внутренних ссылках ChatGPT",
      "source": "turn\\d+search\\d+",
      "flags": "g",
      "explain": {
        "name": "Метка поискового хода агента",
        "why": "След агентного поиска в ответе: человек не нумерует ходы поиска.",
        "advice": "Удалите метку хода."
      }
    },
    {
      "id": "turn_fetch",
      "class": "A",
      "description": "Идентификатор загруженной страницы",
      "source": "turn\\d+fetch\\d+",
      "flags": "g",
      "explain": {
        "name": "Метка загрузки источника агентом",
        "why": "Служебная отметка шага агента по чтению страницы.",
        "advice": "Удалите метку шага."
      }
    },
    {
      "id": "turn_file",
      "class": "A",
      "description": "Идентификатор фрагмента файла из инструмента file_search; в тексте всплывает как `fileciteturn0file2` или сдвоенный `fileciteturn0file2turn0file6`",
      "source": "turn\\d+file\\d+",
      "flags": "g",
      "explain": {
        "name": "Метка файлового хода агента",
        "why": "Служебная отметка обращения агента к файлу.",
        "advice": "Удалите метку обращения."
      }
    },
    {
      "id": "ref_name_search",
      "class": "B",
      "description": "Имя сноски в вики-разметке: числовой префикс + имя внутреннего инструмента. Оно может остаться при копировании ответа агента с веб-поиском",
      "source": "<ref\\b[^>]{0,500}\\bname=[\\\"']\\d+(?:search|fetch|file|image|news|video|ref)\\d+[\\\"']",
      "flags": "g",
      "explain": {
        "name": "Именованная ссылка поискового ответа",
        "why": "Именованный токен ссылки из поискового ответа ассистента.",
        "advice": "Замените на обычную ссылку или удалите."
      }
    },
    {
      "id": "utm_chatgpt",
      "class": "A",
      "description": "OpenAI ChatGPT (веб и приложение)",
      "source": "[?&]utm_source=chatgpt\\.com",
      "flags": "g",
      "explain": {
        "name": "utm-метка провайдера чата",
        "why": "Ссылка помечена параметром источника трафика чат-интерфейса.",
        "advice": "Уберите utm-параметры из ссылки."
      }
    },
    {
      "id": "utm_openai",
      "class": "A",
      "description": "Инструменты OpenAI (общий формат API)",
      "source": "[?&]utm_source=openai",
      "flags": "g",
      "explain": {
        "name": "utm-метка OpenAI",
        "why": "Параметр ссылки выдаёт вставку из интерфейса OpenAI.",
        "advice": "Уберите utm-параметры."
      }
    },
    {
      "id": "utm_copilot",
      "class": "A",
      "description": "Microsoft Copilot",
      "source": "[?&]utm_source=copilot\\.com",
      "flags": "g",
      "explain": {
        "name": "utm-метка Copilot",
        "why": "Параметр ссылки выдаёт вставку из Copilot.",
        "advice": "Уберите utm-параметры."
      }
    },
    {
      "id": "grok_referrer",
      "class": "B",
      "description": "xAI Grok",
      "source": "[?&]referrer=grok\\.com",
      "flags": "g",
      "explain": {
        "name": "Реферер Grok в ссылке",
        "why": "Ссылка несёт служебный реферер интерфейса Grok.",
        "advice": "Удалите параметр реферера."
      }
    },
    {
      "id": "attached_file",
      "class": "A",
      "description": "OpenAI ChatGPT при загрузке файлов",
      "source": "attached_file:\\/\\/",
      "flags": "g",
      "explain": {
        "name": "Метка прикреплённого файла",
        "why": "След вставки из прикреплённого документа в чате.",
        "advice": "Удалите метку вставки."
      }
    },
    {
      "id": "grok_card",
      "class": "A",
      "description": "xAI Grok при ссылке на карточку записи в X (бывший Twitter)",
      "source": "grok_card:\\/\\/",
      "flags": "g",
      "explain": {
        "name": "Карточка ответа Grok",
        "why": "Служебная карточка интерфейса Grok, попавшая в текст.",
        "advice": "Удалите карточку."
      }
    },
    {
      "id": "grok_render_json",
      "class": "A",
      "description": "xAI Grok: JSON-разметка карточек цитирования вместо ссылки",
      "source": "grok_render_citation_card_json",
      "flags": "g",
      "explain": {
        "name": "JSON-блок рендера Grok",
        "why": "Технический блок рендера ответа Grok.",
        "advice": "Удалите технический блок."
      }
    },
    {
      "id": "vertexaisearch",
      "class": "A",
      "description": "Google Gemini, ссылки веб-поиска с привязкой к источникам",
      "source": "vertexaisearch\\.cloud\\.google\\.com/grounding-api-redirect",
      "flags": "g",
      "explain": {
        "name": "Ссылка заземления Vertex AI",
        "why": "Служебный адрес заземления поиска Gemini/Vertex.",
        "advice": "Удалите служебный адрес."
      }
    },
    {
      "id": "attributableIndex",
      "class": "A",
      "description": "Внутренние поля разметки в JSON-ответах при использовании инструментов",
      "source": "\\battributableIndex\\b",
      "flags": "g",
      "explain": {
        "name": "Индекс атрибуции ответа",
        "why": "Служебный индекс атрибуции из ответа модели.",
        "advice": "Удалите индекс."
      }
    },
    {
      "id": "citation_n",
      "class": "A",
      "description": "Стиль Perplexity и других поисковых ИИ",
      "source": "\\[citation:\\d+\\]",
      "flags": "g",
      "explain": {
        "name": "Нумерованная цитата ответа",
        "why": "Нумерация цитат из ответа ассистента, не рукописная.",
        "advice": "Переделайте сноски под свой стиль."
      }
    },
    {
      "id": "copilot_caret",
      "class": "A",
      "description": "Microsoft Copilot и Bing: сноска-ссылка при копировании ответа",
      "source": "\\[\\^\\d+\\^\\]",
      "flags": "g",
      "explain": {
        "name": "Каретный токен Copilot",
        "why": "Служебный символ-маркер интерфейса Copilot.",
        "advice": "Удалите токен."
      }
    },
    {
      "id": "assistants_source",
      "class": "A",
      "description": "OpenAI Assistants (поиск по файлам): метка цитаты, скобки-уголки + кинжал",
      "source": "【\\d+(?::\\d+)?†source】",
      "flags": "g",
      "explain": {
        "name": "Блок источника Answers",
        "why": "Служебный блок источника из интерфейса ассистента.",
        "advice": "Удалите блок источника."
      }
    },
    {
      "id": "cite_turn",
      "class": "A",
      "description": "ChatGPT: служебная метка цитаты, попавшая в текст при копировании из потока",
      "source": "citeturn\\d+[a-z]+\\d+",
      "flags": "g",
      "explain": {
        "name": "Цитата с номером хода",
        "why": "Связка цитаты и хода диалога, характерная только для чат-вывода.",
        "advice": "Удалите связку."
      }
    },
    {
      "id": "sandbox_link",
      "class": "A",
      "description": "ChatGPT (анализ данных): сломанная ссылка на скачивание файла из контейнера",
      "source": "\\]\\(sandbox:/mnt/data/",
      "flags": "g",
      "explain": {
        "name": "Ссылка песочницы",
        "why": "Адрес временной песочницы ассистента, вне чата бесполезен.",
        "advice": "Удалите ссылку песочницы."
      }
    },
    {
      "id": "openai_pua",
      "class": "B",
      "description": "OpenAI ChatGPT: служебные разделители цитат и скрытых блоков",
      "source": "[-]",
      "flags": "g",
      "explain": {
        "name": "Символ приватной области OpenAI",
        "why": "Символ из приватной области, которым интерфейс помечает блоки.",
        "advice": "Удалите невидимый символ."
      }
    },
    {
      "id": "openai_pua_short",
      "class": "B",
      "description": "OpenAI ChatGPT: короткая форма сноски — только номер, ограждённый невидимыми символами",
      "source": "[]",
      "flags": "g",
      "explain": {
        "name": "Короткая форма PUA-метки",
        "why": "Усечённый служебный символ разметки ответа.",
        "advice": "Удалите символ."
      }
    },
    {
      "id": "think_tag",
      "class": "A",
      "description": "DeepSeek R1 и наследники, другие открытые модели с режимом рассуждения (через API и локальный запуск)",
      "source": "^\\s*</?think>|</think>\\s*$",
      "flags": "gm",
      "explain": {
        "name": "Тег размышления модели",
        "why": "След внутреннего рассуждения модели, попавший в вывод.",
        "advice": "Удалите тег."
      }
    },
    {
      "id": "source_plus_chain",
      "class": "A",
      "description": "OpenAI ChatGPT: ошибка отрисовки сносок",
      "source": "[A-Za-zА-Яа-яЁё)]\\+\\d+(?=[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё&.\\-]*(?: [A-ZА-ЯЁ][A-Za-zА-Яа-яЁё&.\\-]*){0,3}\\+\\d)",
      "flags": "g",
      "explain": {
        "name": "Цепочка источников ответа",
        "why": "Служебная цепочка источников агентного ответа.",
        "advice": "Удалите цепочку."
      }
    },
    {
      "id": "gemini_cite_start",
      "class": "A",
      "description": "Google Gemini: внутренняя метка начала цитируемого фрагмента при анализе PDF",
      "source": "\\[cite_start\\]",
      "flags": "g",
      "explain": {
        "name": "Начало цитаты Gemini",
        "why": "Служебная граница цитирования ответа Gemini.",
        "advice": "Удалите границу."
      }
    },
    {
      "id": "gemini_cite_n",
      "class": "A",
      "description": "Google Gemini: ссылка на фрагмент источника; с v3.2 выражение покрывает и перечисление нескольких фрагментов через запятую",
      "source": "\\[[Cc]ite:\\s?\\d+(?:,\\s?\\d+)*\\]",
      "flags": "g",
      "explain": {
        "name": "Нумерация цитат Gemini",
        "why": "Служебные номера цитат ответа Gemini.",
        "advice": "Удалите номера."
      }
    },
    {
      "id": "gemini_span",
      "class": "A",
      "description": "Google Gemini: внутренние span-метки границ фрагментов; всплывают при копировании ответа с подсветкой источников",
      "source": "\\[span_\\d+\\][\\[(](?:start_span|end_span)[\\])]",
      "flags": "g",
      "explain": {
        "name": "Пролёт цитирования Gemini",
        "why": "Служебный пролёт цитирования ответа Gemini.",
        "advice": "Удалите пролёт."
      }
    },
    {
      "id": "zero_width",
      "class": "B",
      "description": "Наблюдались у ряда моделей (обзорные источники весны 2025; атрибуция конкретной версии не подтверждена); расширение класса — публичный разбор watermarks-remover, 2026-08-13",
      "source": "[​‌‎‏‪-‮⁠-⁤⁦-⁩﻿￹-￻]|(?<![🀀-🫿☀-➿️🇦-🇿])‍(?![🀀-🫿☀-➿️🇦-🇿])",
      "flags": "gu",
      "explain": {
        "name": "Невидимый символ нулевой ширины",
        "why": "Невидимые символы часто остаются при копировании из чатов и PDF; читатель их не видит, а след остаётся.",
        "advice": "Снимите невидимые символы полировкой."
      }
    },
    {
      "id": "writing_block",
      "class": "A",
      "description": "Writing-разметка; атрибуция версии не подтверждена",
      "source": ":::\\w+\\{variant",
      "flags": "g",
      "explain": {
        "name": "Блок письменного вывода",
        "why": "Служебная обёртка блока письменного вывода модели.",
        "advice": "Удалите обёртку."
      }
    },
    {
      "id": "deepseek_line_ref",
      "class": "A",
      "description": "DeepSeek и производные модели: ссылка на строки источника",
      "source": "【\\d+†L\\d+(?:-L?\\d+)?】",
      "flags": "g",
      "explain": {
        "name": "Построчная ссылка ответа",
        "why": "Служебные построчные ссылки ответа DeepSeek.",
        "advice": "Удалите построчные ссылки."
      }
    },
    {
      "id": "grok_card_tag",
      "class": "A",
      "description": "xAI Grok: XML-тег карточки цитирования после сноски",
      "source": "<grok-card\\b[^>]*\\bcitation_card\\b",
      "flags": "g",
      "explain": {
        "name": "Тег карточки Grok",
        "why": "Служебный тег карточки интерфейса Grok.",
        "advice": "Удалите тег."
      }
    },
    {
      "id": "turn_other",
      "class": "A",
      "description": "Идентификаторы из других инструментов ChatGPT: изображения, новости, видео, ссылки на источники; всплывают при копировании ответов с мультимедиа",
      "source": "turn\\d+(?:image|news|video|ref)\\d+",
      "flags": "g",
      "explain": {
        "name": "Метка прочего хода",
        "why": "Служебная метка прочего шага агентного ответа.",
        "advice": "Удалите метку."
      }
    },
    {
      "id": "attached_web_bracket",
      "class": "A",
      "description": "Perplexity (с осени 2025; возможно и другие поисковые ИИ): скобочная форма ссылок на прикреплённые файлы и веб-результаты в конце предложений",
      "source": "\\[(?:attached_file|web):\\d+\\]",
      "flags": "g",
      "explain": {
        "name": "Скобка веб-вставки",
        "why": "Служебная скобка вставки из веб-источника в чате.",
        "advice": "Удалите скобку вставки."
      }
    },
    {
      "id": "perplexity_s3",
      "class": "A",
      "description": "Perplexity: ссылки на Amazon S3-bucket с этим идентификатором в адресе; всплывают при копировании ответа с привязкой к источникам",
      "source": "ppl-ai-file-upload",
      "flags": "g",
      "explain": {
        "name": "Адрес хранилища Perplexity",
        "why": "Служебный адрес временного хранилища ответа Perplexity.",
        "advice": "Удалите адрес хранилища."
      }
    },
    {
      "id": "generated_ref_id",
      "class": "A",
      "description": "ChatGPT: редкая служебная метка сгенерированного идентификатора ссылки, всплывает при сбое отрисовки цитат",
      "source": "citegenerated-reference-identifier",
      "flags": "g",
      "explain": {
        "name": "Сгенерированный идентификатор ссылки",
        "why": "Сгенерированный идентификатор ссылки из ответа модели.",
        "advice": "Удалите идентификатор."
      }
    },
    {
      "id": "placeholder_url",
      "class": "B",
      "description": "Placeholder-URL из шаблонных ответов: ИИ выдаёт структуру ссылки, которую пользователь должен заполнить, но публикует без правки",
      "source": "\\b(?:INSERT_SOURCE_URL(?:_\\d+)?|URL_HERE|PASTE_\\w+_URL_HERE)\\b",
      "flags": "g",
      "explain": {
        "name": "Заглушка ссылки",
        "why": "Заглушка вида INSERT_\" + \"SOURCE_URL: модель не подставила адрес, а след остался.",
        "advice": "Подставьте реальный источник или удалите заглушку."
      }
    },
    {
      "id": "placeholder_date",
      "class": "B",
      "description": "Placeholder-дата из шаблонных ответов: ИИ подставляет заглушку вместо неизвестной даты (чаще всего — «дата обращения» в списке литературы)",
      "source": "\\b(?:19|20)\\d{2}-(?:0[1-9]|1[0-2]|[Xx]{2})-[Xx]{2}\\b",
      "flags": "g",
      "explain": {
        "name": "Заглушка даты",
        "why": "Заглушка даты из шаблона ответа модели.",
        "advice": "Подставьте реальную дату или удалите заглушку."
      }
    },
    {
      "id": "invisible_layout",
      "class": "B",
      "description": "Публичный разбор классов меток watermarks-remover, 2026-08-13; классовое описание, атрибуция конкретных моделей не подтверждена",
      "source": "­|[  　]|(?<![🀀-🫿☀-➿🇦-🇿©®‼⁉™ℹ↔-↙↩-↪⌚-⌛⌨⏏⏩-⏺Ⓜ▪-◾⤴-⤵⬀-⯿〰〽㊗㊙])[︀-️](?![🀀-🫿☀-➿🇦-🇿⃣])",
      "flags": "gu",
      "explain": {
        "name": "Невидимые символы разметки",
        "why": "Невидимые управляющие символы разметки (направления письма, переносы): законны в редких случаях, но после чатов обычно случайны.",
        "advice": "Проверьте происхождение текста и снимите символы полировкой."
      }
    },
    {
      "id": "unicode_tags",
      "class": "B",
      "description": "Стеганографические инструменты (SteganoPrompt, arXiv:2605.16336, AIES 2026): нагрузка кодируется как `chr(0xE0000 + ord(c))` и вставляется в видимый текст; модель, получившая промпт дословно, переносит метку в ответ",
      "source": "(?<![🏴🏳️󠀀-󠁿])[󠀀-󠁿]",
      "flags": "gu",
      "explain": {
        "name": "Unicode-теги",
        "why": "Символы блока Tags: почти всегда след инструментальной обработки текста.",
        "advice": "Удалите теговые символы."
      }
    }
  ]
};
window.HUMANIZER_MARKERS = HUMANIZER_MARKERS;
