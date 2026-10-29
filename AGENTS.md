# AGENTS.md — для агентов, которые правят этот репозиторий

humanizer-ru — навык (Agent Skill), который переписывает русский ИИ-текст по-человечески
и сверяет факты. Всё, что получает пользователь, лежит в `skills/humanizer-ru/`.

## Карта

| Путь | Что это |
|---|---|
| `skills/humanizer-ru/SKILL.md` | инструкция для агента, главный файл продукта |
| `skills/humanizer-ru/references/` | примеры «было → стало» и границы признаков |
| `skills/humanizer-ru/scripts/` | `check_facts.py`, `clean_paste.py`: только стандартная библиотека Python |
| `eval/` | слепое сравнение с другими навыками на русских ИИ-текстах |
| `scripts/` | проверка репозитория, проверка скриптов навыка на текстах замеров, сборка архива для Claude.ai, сборка дерева для каталога Anthropic |
| `tests/` | тесты скриптов и проверки репозитория |
| `.claude-plugin/`, `.codex-plugin/` | манифесты плагинов; `icon.png` и ссылки в `plugin.json` читает каталог плагинов Anthropic |
| ветка `directory` | только плагин (10 файлов, без `eval/`, `scripts/`, `tests/` и этих заметок): её читает портал каталога Anthropic; собирает `scripts/build_directory.py` |
| `.grace/` | требования, граф модулей и карта проверок (GRACE) |

## Правила

1. Меняешь поведение навыка — прогони сравнение (`eval/README.md`) хотя бы на dev-наборе и
   сравни с прошлым итогом. Правка, которая ухудшает итог, не принимается.
2. SKILL.md держи коротким: новое правило заменяет старое, а не добавляется сверху.
   Примеры — в `references/`.
3. Скрипты навыка без внешних зависимостей. Новый случай — тест в `tests/`.
4. Версия меняется одновременно в SKILL.md, `.claude-plugin/*.json`, `.codex-plugin/plugin.json`
   и CHANGELOG; `python scripts/check_repo.py` это проверяет.
5. Переводы строк LF, без невидимых символов в файлах навыка.
6. Не запускать локальные нейросетевые модели (решение владельца).
7. Меняешь поведение скрипта — обнови контракт в коде и `.grace/`.
8. После каждого выпуска пересобери ветку `directory` (ниже). Каталог Anthropic читает её, а не
   main: в main лежат `eval/` (читает `FAL_KEY`), заметки с путём к иконке и 1800 файлов, за что
   портал придерживает плагин. Ни один файл дерева, кроме `plugin.json`, не называет иконку.

Перед коммитом:

```sh
python scripts/check_repo.py
python -m unittest discover -s tests
```

Меняешь скрипт навыка — ещё `python scripts/check_scripts.py --against main`: свойства на всех
текстах `eval/` должны выполняться, а каждую новую ошибку сверки прочитай глазами (ложная
тревога на старых правках — дефект скрипта, а не правки).

Ветка `directory` (после выпуска, из чистого main; нужен git 2.42+). Первый раз вместо `add` с веткой:
`git worktree add --orphan -b directory "$WT"`.

```sh
TREE=$(mktemp -d)/tree; WT=$(mktemp -d)/wt
python scripts/build_directory.py "$TREE"
claude plugin validate "$TREE" --profile directory --strict
git fetch origin directory && git worktree add -B directory "$WT" origin/directory
git -C "$WT" rm -r -q --ignore-unmatch . && cp -r "$TREE"/. "$WT"/
git -C "$WT" add -A && git -C "$WT" commit -m "directory: humanizer-ru X.Y.Z, собрано из main $(git rev-parse --short HEAD)"
git -C "$WT" push origin directory && git worktree remove --force "$WT"
```

Дальше владелец нажимает Validate на портале (Repository `Vladimir-Human/humanizer-ru`, Branch or
tag `directory`) и отправляет плагин. Проверка портала на этой ветке ещё не записана в
`.grace/verification/index.xml` (G-DIRECTORY-PORTAL): после его запуска запиши итог.

Версия 3 (исследования, гейты, пакет PyPI, MCP) — в ветке `legacy-v3`, в main её не возвращать.
