# Матрица удаления: какой слой снимает какую метку

Два слоя меток и три слоя инструментов. Честная рамка: снятие — для
контента, которым владеет пользователь; заявлений «доказывает, что текст
написан человеком» проект не делает. Снятие меток — открытая возможность продукта.

| Метка | Слой | Инструмент | Снимается? | Честность |
|---|---|---|---|---|
| Невидимые символы (нулевые пробелы, биди-контролы, невидимые операторы, межстрочные аннотации) | A (текст) | `scripts/check_markers.py` (A.7), `scripts/filemarks/filemarks.py --clean` | да, детерминированно | снятие проверяемо повторным прогоном |
| PUA-разделители цитат ChatGPT (U+E200–E204, U+EA01/EA02) | A (текст) | `scripts/filemarks/filemarks.py --clean` (слой A: `openai_pua`, `openai_pua_short`) | да, детерминированно | граница — иконные шрифты (U+EA01/EA02 теоретически занимают наборы вроде Codename One): маркер ограждает одиночную цифру после точки в конце предложения; при подозрении на иконку — ручная проверка (chatbot-artifacts-markup.md §A.7:29–30) |
| Unicode tag-символы (U+E0000–U+E007F) и default-ignorable (U+206A–F, U+180E, U+034F) | A (текст) | `filemarks --clean` (`TAG_STRIP_RX`) | да, детерминированно | guard эмодзи-флагов: теги после U+1F3F4/U+1F3F3+U+FE0F не трогаются |
| Видимые copy-paste артефакты класса A (turn0…N, citeturn…, oaicite:N, [cite:N], 【N†source】, «Источник+3», utm/referrer-параметры, think-блок и др.) | A (текст) | `filemarks --clean` (`MARKUP_CASES`, `clean_markup`) | да, детерминированно | только параметр из URL, не вся ссылка; think-блок удаляется вместе с содержимым; НЕ снимаются (только inspect): `<ref name=…>`-вики-разметка, sandbox-ссылки, placeholder URL/даты (требуют ручного заполнения) |
| Мягкий перенос, экзотические пробелы, вариационные селекторы вне эмодзи | A (текст) | `invisible_layout`, filemarks | да, детерминированно | — |
| Вложенные медиа (PNG/JPEG в DOCX `word/media/*`, ODT `Pictures/*`, `data:image/…` в HTML/MD/SVG) | контейнеры | `filemarks --clean` (`strip_png`/`strip_jpeg` в памяти, перекодировка data-URI) | да | знак может жить внутри «вычищенного» контейнера; зеркально в inspect — «вложенный носитель с метками» |
| Статистические (token-sampling) метки: SynthID-Text-класс, Kirchenbauer-класс | B (текст) | глубокая перезапись (`rewrite-guide.md`) + `scripts/filemarks/rewrite_text.py` (промпты) + прокси `check_rewrite_delta.py` (остаточный риск) | best-effort | публичного верификатора нет: отчёт обязан говорить «best-effort», а не «снято» |
| Неподдерживаемые бинарные форматы (AVIF/GIF/TIFF/HEIC/JXL) | — | `classify` | отказ кодом 2 | не выдавать ложно-чистый отчёт: явный флаг «unsupported binary format» |
| C2PA/Content Credentials в PNG/JPEG | файлы | `scripts/filemarks/filemarks.py --clean` (чанки caBX/APP11 и др.) | да (жёсткая привязка) | мягкая привязка (пере-прикрепление удалённого манифеста) НЕ снимается — вне скоупа |
| C2PA/XMP/EXIF в SVG/PDF/DOCX/ODT/HTML/MD | контейнеры | filemarks (metadata/xmpmeta/customXml/docProps/frontmatter) | да; PDF best-effort (лучше с exiftool) | урезанный stdlib-режим PDF помечается degraded |
| JPEG APP2/ICC (цветопередача) | файлы | `strip_jpeg` | сохраняется принудительно | снятие ICC меняет цвет изображения — нарушение «не портить живое»; APP2-не-ICC снимается как обычно |
| WebP: EXIF/XMP-чанки (RIFF) | файлы | `filemarks --clean` (`strip_webp`: EXIF/XMP удаляются, ICCP сохраняется) | да, детерминированно | RIFF-чанки парсятся stdlib; ICCP без изменений (цветопередача) |
| PPTX/XLSX: docProps/customXml и вложенные медиа (ppt/media, xl/media) | контейнеры | `filemarks --clean` (`_clean_ooxml`, тот же путь, что DOCX) | да | слой A применяется к телу (presentation.xml/workbook.xml), медиа чистятся рекурсивно |
| Мягкая привязка C2PA (пере-прикрепление манифеста по хэшу контента) | файлы | `filemarks --clean --reencode` (PNG: lossless-переупаковка IDAT — байтовый хэш меняется, пиксели нет) | best-effort (opt-in) | деструктивно: отчёт «байты изменены»; НЕ гарантирует снятие знака; JPEG — только внешним инструментом |
| Пиксельный SynthID в изображениях | вне скоупа | `scripts/filemarks/score_synthid.py` — только ОЦЕНКА внешним скорингом; вызов из `filemarks --inspect --upstream-dir` заполняет поле `synthid` | нет | сторонний исследовательский код, некоммерческая лицензия; не официальный детектор Google; без checkout — честное `synthid: {available: false}` |
| Trigger-phrase/backdoor метки | вне скоупа | — | нет | задокументировано в llm-fingerprints.md |
| Аудио/видео метки | вне скоупа | — | нет | — |

PDF-C2PA-оговорка: `exiftool -all=` (и stdlib-режим) НЕ вынимают вложения AssociatedFiles/JUMBF — только осмотр находит `/AssociatedFiles`/имя `C2PA`. Для снятия таких вложений нужен перевыпуск PDF (qpdf `--object-streams=disable` + пересборка) — опциональный второй инструмент за рамками stdlib-режима.

## Классификация невидимых символов по риску (снятие в тексте)

Текстовый путь снятия — `humanizer-markers --remove` (пакет) и функция
`remove_invisible` в `scripts/filemarks/text_layer.py` (единственный
источник таблицы; публикуемая копия — блок `invisible_classes` в
`markers.v1.json`, гейт `scripts/check_invisible_removal.py`).

- **safe** — невидимые обвязки копипасты: снимаются автоматически.
- **ambiguous** — символы с легитимными источниками: снятие ТОЛЬКО opt-in
  (`--include-ambiguous`), с дифом и предупреждением; спецпробелы
  заменяются обычным пробелом, а не удаляются.
- **dangerous** — структурные и аннотационные: показываются в отчёте и не
  снимаются никогда. Невидимый символ вне таблицы считается dangerous
  (fail-safe). Массовое «удалить всё невидимое» запрещено по построению:
  такого режима нет.

| Диапазон | Класс | Имя | Риск | Действие |
|---|---|---|---|---|
| U+200B | safe | zero-width space | обвязка копипасты чат-интерфейсов | remove |
| U+2060 | safe | word joiner | обвязка копипасты | remove |
| U+FEFF | safe | BOM / ZWNBSP | обвязка копипасты и кодировок | remove |
| U+00AD | safe | soft hyphen | скрытый перенос, ломает поиск и сравнение | remove |
| U+180E | safe | mongolian vowel separator | исторический разделитель, в русском тексте не легитимен | remove |
| U+034F | safe | combining grapheme joiner | невидимая обвязка, в русском тексте не легитимна | remove |
| U+E0000–U+E007F | safe | unicode tag characters | теговые метки поставщиков (OpenAI/Gemini); вне эмодзи-флагов | remove |
| U+E200–U+E204 | safe | openai citation PUA | служебные метки цитирования ChatGPT | remove |
| U+EA01–U+EA02 | safe | openai citation PUA short | обёртки усечённой формы меток ChatGPT | remove |
| U+200C–U+200D | ambiguous | ZWNJ / ZWJ | эмодзи-последовательности и индийские письменности: снятие меняет отображение | opt-in |
| U+200E–U+200F | ambiguous | LRM / RLM | bidi-марки: легитимны в смешанных направлениях | opt-in |
| U+202A–U+202E | ambiguous | bidi embeddings/overrides | риск Trojan Source: показывать диф обязательно | opt-in |
| U+2066–U+2069 | ambiguous | bidi isolates | легитимная bidi-изоляция | opt-in |
| U+206A–U+206F | ambiguous | deprecated format characters | устаревшие форматные; в контейнерных путях снимаются TAG_STRIP | opt-in |
| U+FE00–U+FE0F | ambiguous | variation selectors | эмодзи-вариации: снятие меняет глиф | opt-in |
| U+3164 | ambiguous | hangul filler | корейские филлеры: легитимны в хангыле | opt-in |
| U+FFA0 | ambiguous | hangul filler (halfwidth) | корейские филлеры: легитимны в хангыле | opt-in |
| U+00A0 | ambiguous | no-break space | легитимная типографика (неразрывные сочетания); действие — обычный пробел, не удаление | to-space |
| U+2009 | ambiguous | thin space | типографский узкий пробел; действие — обычный пробел | to-space |
| U+202F | ambiguous | narrow no-break space | типографский узкий неразрывный пробел; действие — обычный пробел | to-space |
| U+2028 | dangerous | line separator | структура текста: снятие склеивает строки | report-only |
| U+2029 | dangerous | paragraph separator | структура текста: снятие склеивает абзацы | report-only |
| U+FFF9–U+FFFB | dangerous | interlinear annotation | межстрочные аннотации: снятие теряет чтение | report-only |

Теговые символы внутри эмодзи-флагов (U+1F3F4 + теги + U+E007F) не
снимаются ни в каком режиме — это легитимные флаги (Англия, Шотландия,
Уэльс); одиночные теги вне флагов снимаются как safe.

## Порядок работы (из watermarks-remover, адаптировано)

Правовая рамка: снятие меток выполняется для контента, которым владеет
пользователь; ответственность за использование результата — на пользователе.
Проект не позиционируется как средство сдачи работ там, где ИИ запрещён, и
не снимает плагиат (совпадение с базой антиплагиата перезаписью не
устраняется); статистические следы снимаются как «лучший эффективный
уровень», без заявлений «не детектируется».

1. Классифицировать вход: текст / изображение / контейнер.
2. Осмотр: `filemarks.py --inspect файл --json`.
3. Слой A — детерминированно: `filemarks.py --clean файл -o файл.cleaned.*`.
4. Слой B — всегда предлагать для прозы: перезапись по `rewrite-guide.md`;
   модель — из другого семейства, чем подозреваемый источник.
5. Слой A повторно на результате.
6. Отчёт: что снято проверяемо (числа), что best-effort, что вне скоупа;
   писать `*.cleaned.*`, а не на месте.
