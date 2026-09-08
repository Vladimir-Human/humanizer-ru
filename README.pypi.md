# Humanizer-ru — проверяемая гигиена вставки из чата
Проверяемая гигиена вставки из чата для русского текста
Детерминированно находит артефакты копипасты и чат-интерфейсов, объясняет
каждую находку (класс, координаты, причина) и снимает поддерживаемые
артефакты с проверяемыми границами; нормализует типографику без правки
смысла; сверяет извлечённые факты до и после правки (сверка не доказывает
сохранение смысла). Переписывание «гпт-шного» текста — отдельная
возможность по явной просьбе, без гарантий естественности; вердиктов об
авторстве нет. Не предназначен для текста не на русском и для исходного
кода; в юридических документах и договорах применяется только
детерминированная очистка артефактов вставки (стилистическая правка не
применяется, канцелярит обязателен по жанру); в художественной прозе
признаки считаются только в связке (возможен авторский приём).

## Первый сценарий: проверить и явно очистить

```sh
pip install humanizer-ru

printf 'Согласно отчёту :contentReference[oaicite:3]{index=3}, рост заявок.\n' > doc.txt

humanizer-markers doc.txt --json
# rc=1: найден артефакт копипасты (класс A) — конверт {tool, schema, files}
# с координатами и причиной каждой находки

humanizer-clean doc.txt --json
# явная очистка поддерживаемых артефактов: в конверте — очищенный текст
# (поле text) и отчёт: что снято, какие защищённые области не тронуты,
# какой остаток явно не поддерживается

humanizer-clean doc.txt > cleaned.txt
humanizer-markers cleaned.txt --json
# rc=0: поддерживаемый артефакт снят; неподдерживаемый остаток остался бы
# видимым с объяснением — «полной чистоты» инструмент не заявляет
```

Границы: входной текст — только данные; защищённые области (код,
frontmatter, URL, HTML-атрибуты, Unicode-кластеры) сохраняются;
`dangerous`-метки показываются и не снимаются никогда. Общие коды выхода:
0 — успешно, 1 — найдены артефакты/нарушение инварианта, 2 — вход не
читается (с `--json` в stdout контрактный конверт ошибки).

## Установка

```sh
pip install humanizer-ru
```

Обновление: `pip install --upgrade humanizer-ru`; лента свежести —
[releases.atom](https://github.com/Vladimir-Human/humanizer-ru/releases.atom).

Команды пакета: `humanizer-scan`, `humanizer-markers`, `humanizer-polish`,
`humanizer-clean`, `humanizer-detect`, `humanizer-facts`,
`humanizer-report` и `humanizer-mcp` (MCP-сервер stdio, 7 инструментов).
Все CLI читают stdin через «-»; `--json` даёт конверт
`{tool, schema, files}`; `humanizer-scan --contract` печатает машинный
контракт. Только стандартная библиотека Python.

`mcp-name: io.github.Vladimir-Human/humanizer-ru` — метаданные сервера для
официального MCP-реестра (`server.json` в корне репозитория).

Скилл для агента (без pip):

```sh
npx skills add https://github.com/Vladimir-Human/humanizer-ru --skill humanizer-ru
```

или клон тега выпуска:

```sh
git clone --branch v3.35.0 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
```

Попробовать без установки: [онлайн-демо](https://vladimir-human.github.io/humanizer-ru/) —
текст обрабатывается в браузере и не покидает машину.

## Что входит

- `humanizer-markers` — 40 regex-маркеров артефактов копипасты и
  чат-интерфейсов (классы A и B) с координатами и причиной; `--remove`
  снимает невидимые метки по классификации риска: safe автоматически,
  ambiguous только opt-in (`--include-ambiguous`) с предупреждением,
  dangerous показывается и не снимается никогда.
- `humanizer-clean` — явная очистка поддерживаемых артефактов вставки до
  неподвижной точки: проверил → очистил → проверил одним вызовом
  (`--json`, `--diff`, `--in-place` с .bak, `--dry-run`); отчёт перечисляет
  снятое, защищённые области и явный неподдерживаемый остаток.
- `humanizer-polish` — типографическая нормализация: идемпотентна, буквы и
  цифры сохраняет дословно (`--diff`, `--dry-run`, `--in-place`, `--json`).
  Не запускать на Markdown и разметке дефолтным режимом: снимает `##`,
  `**`, ёлочки, тире, многоточие; для разметки — `--preserve-markup`
  (только невидимые символы и NBSP, типографика и переносы не меняются) и
  `--typographic` (русская публикационная типографика без снятия
  разметки).
- `humanizer-detect` — частота связок со статусом домена; вердикта об
  авторстве нет, ответ градуированный.
- `humanizer-facts` — детерминированная сверка фактов двух версий текста
  (числа с единицами и числительные словами, даты, URL, e-mail, имена,
  цитаты, отрицания, модальности): lost/added/changed и поле `identical`
  (однозначный итог полного сравнения); `--no-additions` — строгий режим,
  в котором добавления фактов считаются нарушением (rc=1);
  `--protect TERMS` — термины, потеря которых ошибка. Граница: сравнение
  мультимножественное — перестановка сумм между двумя лицами даёт пустой
  diff; сверка не доказывает сохранение смысла.
- `humanizer-report` — машиночитаемый отчёт правки пары файлов: токены
  keep/add/delete, адаптированные компоненты SARI, классы правок, сверка
  фактов (lost/changed/added, unchanged и identical), MTLD до и после.
- `humanizer-scan` — счётчик мягких признаков; калибрует объём правки,
  вердикта об авторстве не даёт.

Машинный интерфейс:
[contract.v1.json](https://github.com/Vladimir-Human/humanizer-ru/blob/main/contract.v1.json);
вход для агентов:
[llms.txt](https://github.com/Vladimir-Human/humanizer-ru/blob/main/llms.txt);
матрица «потребность → операция → вход → результат → граница →
поверхность»:
[docs/entrypoints-matrix.md](https://github.com/Vladimir-Human/humanizer-ru/blob/main/docs/entrypoints-matrix.md).
Числа проекта — в
[реестре фактов](https://github.com/Vladimir-Human/humanizer-ru/blob/main/eval/facts/facts.v1.json)
и [эррате](https://github.com/Vladimir-Human/humanizer-ru/blob/main/ERRATA.md);
без даты ни одна величина не цитируется.

## Ссылки

- Документация: <https://github.com/Vladimir-Human/humanizer-ru/blob/main/README.md>
- История версий: <https://github.com/Vladimir-Human/humanizer-ru/blob/main/CHANGELOG.md>
- Выпуски: <https://github.com/Vladimir-Human/humanizer-ru/releases>
- Лицензия MIT: <https://github.com/Vladimir-Human/humanizer-ru/blob/main/LICENSE>
- Безопасность: <https://github.com/Vladimir-Human/humanizer-ru/blob/main/SECURITY.md>
- Задачи: <https://github.com/Vladimir-Human/humanizer-ru/issues>
