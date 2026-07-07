# Протокол исследования к выпуску v3.1.0 (7 июля 2026)

Независимое исследование ландшафта детекции ИИ-текста и артефактов копирования.
Правило принятия: маркер входит в выпуск только при подтверждении **двумя и более независимыми источниками**, из которых хотя бы один — первичный (страница английской Википедии «Signs of AI writing» в сыром виде, официальная документация, исходный код инструментов).

## Дорожки исследования

1. **Wikipedia EN (первичный источник).** Сырая вики-разметка `Wikipedia:Signs_of_AI_writing` (`action=raw`, снимок от 7 июля 2026, ~189 КБ) прочитана по всем разделам; новые разделы сверены с покрытием v3.0.0.
2. **Wikipedia RU.** «Википедия:Признаки сгенерированности текста» — без существенных обновлений против v3.0.0.
3. **Исходный код инструментов цитирования.** LibreChat `packages/data-provider/src/types/web.ts` — типы ссылок `'search' | 'image' | 'news' | 'video' | 'ref'`.
4. **Веб-аналитика 2026.** Разборы referral-трафика AI-поисковиков в GA4 (lawrencehitches.com, апрель 2026); спецификация атрибуции AI-поиска (geodocs.dev).
5. **Русская экосистема.** ReText.AI — исследование 12 996 ВКР 2013–2025 (retext.ai/ru/blog, май–июнь 2026; Хабр 1051372; CNews 17.06.2026); GigaCheck (developers.sber.ru/portal/products/gigacheck, точность 94,7 %); блог «Антиплагиата».
6. **Научные работы 2025–2026.** Juzek & Ward (ACL 2025, arXiv:2412.11385), Kobak et al. (Science Advances 11:27, 2025), Kousha & Thelwall (ISSI 2025, arXiv:2509.09596) — лексика ИИ; без новых hard-маркеров, контекст для мягких паттернов.

## Принятые маркеры (10) и их источники

| Маркер | Первичный источник | Независимое подтверждение |
|---|---|---|
| `turn\d+(?:image\|news\|video\|ref)\d+` | EN Wiki, раздел «`turn0search0`»: пример `iturn0image0turn0image1…`, `citeturn0news0`; поиск `insource:/turn0(search\|image\|news\|file)[0-9]+/` | LibreChat: `SearchRefType = 'search' \| 'image' \| 'news' \| 'video' \| 'ref'` |
| `[?&]utm_source=copilot\.com` | EN Wiki, раздел «utm_source=»: «Microsoft Copilot may add `utm_source=copilot.com`» | Поисковая ссылка insource там же |
| `[?&]referrer=grok\.com` | EN Wiki, там же: «Grok uses `referrer=grok.com`» | Поисковая ссылка insource там же |
| `grok_render_citation_card_json` | EN Wiki: примеры `[](grok_render_citation_card_json={"cardIds":["3bb883"]})` из реальных правок | Второй пример в той же секции (правка `993eac`) |
| `<grok-card\b[^>]*\bcitation_card\b` | EN Wiki: `<grok-card data-id="e8ff4f" data-type="citation_card">` | Формулировка «XML-styled grok_card tags» + пример правки |
| `【\d+†L\d+(?:-L?\d+)?】` | EN Wiki: «As of June 2025 … specific to DeepSeek and its derivatives», с внешней ссылкой на архив DeepSeek | Примеры реальных правок в обеих формах: `【85†L261-269】` и `【854140639155648†L119-L123】` |
| `\[(?:attached_file\|web):\d+\]` | EN Wiki: «As of fall 2025, tags like `[attached_file:1]` and `[web:1]` … may be Perplexity-specific» | Внешняя ссылка laetusinpraesens.org + пример правки |
| `citegenerated-reference-identifier` | EN Wiki, раздел «`turn0search0`»: перечислена с постоянной ссылкой на правку | Той же природы, что подтверждённые `citeturn`-метки |
| `\b(?:INSERT_SOURCE_URL(?:_\d+)?\|URL_HERE\|PASTE_\w+_URL_HERE)\b` | EN Wiki, «Phrasal templates and placeholder text»: `INSERT_SOURCE_URL_30`, `PASTE_SPOTIFY_TRACK_URL_HERE`, `PASTE_YOUTUBE_VIDEO_URL_HERE` | Скрабберы/детекторы AI-письма на GitHub |
| `\b\d{4}-(?:\d{2}\|[Xx]{2})-[Xx]{2}\b` | EN Wiki, там же: «placeholder dates like `2025-xx-xx` … particularly the access-date parameter»; пример `2022-11-XX` | Два независимых примера реальных правок на странице |

## Принятый мягкий паттерн

**#9a «Академические клише-заполнители»** — ReText.AI (12 996 ВКР: во введениях доля ИИ-текста от 49 %, генерация «по стандартным академическим шаблонам»); GigaCheck/Sber (лексико-синтаксические признаки); блог «Антиплагиата». Только ручная проверка, без regex — обороты нормальны и для человека.

## Самоограничения и честность

- Проверка каждого regex: позитивные, негативные и граничные образцы в `scripts/check_markers.py` (34/34) + самопроверка текстов проекта (self-scan, 0 совпадений).
- Отклонённые кандидаты и причины — в `research/GAPS.md`.
- Ложные срабатывания задокументированы в границах каждого раздела `chatbot-artifacts.md`.
