# CODEPOINT-PROBE-2026 — автопроба невидимых и служебных кодпоинтов (F7')

Инструмент: `tools/codepoint_probe.py` (stdlib, классы zero_width,
bidi_controls, pua, tags, variation_select, invisible_layout, control).
Назначение: автоматическая проба корпуса на следы новых моделей;
кандидаты рассматриваются против реестра доказательств вручную,
автоматически маркерами не становятся.

## Базовый замер (корпус фикстур и справочников)

Команда: `python3 tools/codepoint_probe.py tests/fixtures references research/fixtures --json`

- Файлов просканировано: 37.
- Итоги по классам: bidi_controls 2, control 61, invisible_layout 3, pua 24, tags 31, variation_select 5, zero_width 18.
- Топ файлов: tests/fixtures/encodings/utf16.txt: control 61; tests/fixtures/unicode-tags.txt: tags 22, variation_select 1; tests/fixtures/openai-pua.txt: pua 12; research/fixtures/marker-sources.json: invisible_layout 1, pua 5, tags 2, zero_width 2; tests/fixtures/invisibles/flag_england.txt: tags 7.

Интерпретация: фикстуры намеренно содержат невидимые символы (это их
назначение); замер служит бейзлайном для сравнения будущих корпусов.
Расхождений с ожиданиями нет: классы tags и pua приходят из фикстур
unicode-tags и openai-pua, control — из utf16-фикстуры.
