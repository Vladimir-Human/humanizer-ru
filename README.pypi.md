# Humanizer-ru — нормализация и диагностика русского текста

Находит артефакты копипасты и следы машинной генерации, нормализует
типографику без правки смысла. Переписывание «гпт-шного» текста — по явной
просьбе, без заявлений о качестве результата. Для текста не на русском,
исходного кода, юридических документов и художественной прозы не
предназначен.

## Установка

```sh
pip install humanizer-ru
```

Обновление: `pip install --upgrade humanizer-ru`; лента свежести —
[releases.atom](https://github.com/Vladimir-Human/humanizer-ru/releases.atom).

Команды пакета: `humanizer-polish`, `humanizer-detect`, `humanizer-markers`,
`humanizer-scan`, `humanizer-mcp` (MCP-сервер stdio). Все CLI читают stdin
через «-»; `--json` даёт конверт `{tool, schema, files}`. Только
стандартная библиотека Python.

`mcp-name: io.github.Vladimir-Human/humanizer-ru` — метаданные сервера для
официального MCP-реестра (`server.json` в корне репозитория).

Скилл для агента (без pip):

```sh
npx skills add https://github.com/Vladimir-Human/humanizer-ru --skill humanizer-ru
```

или клон тега выпуска:

```sh
git clone --branch v3.28.0 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
```

Попробовать без установки: [онлайн-демо](https://vladimir-human.github.io/humanizer-ru/) —
текст обрабатывается в браузере и не покидает машину.

## Что входит

- `humanizer-polish` — типографическая нормализация: идемпотентна, буквы и
  цифры сохраняет дословно (`--diff`, `--dry-run`, `--in-place`, `--json`).
  Не запускать на Markdown и разметке: снимает `##`, `**`, ёлочки, тире,
  многоточие; для разметки — `--preserve-markup` (только невидимые
  символы) и `--typographic` (русская публикационная типографика без
  снятия разметки).
- `humanizer-detect` — частота связок со статусом домена; вердикта об
  авторстве нет, ответ градуированный.
- `humanizer-markers` — 40 regex-маркеров артефактов копипасты и
  чат-интерфейсов (классы A и B); `--remove` снимает невидимые метки по
  классификации риска: safe автоматически, ambiguous только opt-in
  (`--include-ambiguous`) с предупреждением, dangerous показывается и не
  снимается никогда.
- `humanizer-scan` — счётчик мягких признаков; калибрует объём правки,
  вердикта об авторстве не даёт.

Запрещённые использования (полный список — блок `prohibited_uses` в
контракте): сдача работ там, где ИИ запрещён; обход систем антиплагиата и
атрибуции; сокрытие факта использования ИИ, когда раскрытие обязательно;
снятие водяных знаков с чужого контента; приписывание машинного текста
другому лицу. Легитимная область — свой текст и честный отчёт.

Машинный интерфейс:
[contract.v1.json](https://github.com/Vladimir-Human/humanizer-ru/blob/main/contract.v1.json);
вход для агентов:
[llms.txt](https://github.com/Vladimir-Human/humanizer-ru/blob/main/llms.txt).
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
