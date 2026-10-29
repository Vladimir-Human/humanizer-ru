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
| ветка `directory` | только плагин (10 файлов, без `eval/`, `scripts/`, `tests/` и этих заметок): её читает портал каталога Anthropic; собирает `scripts/build_directory.py`; имя плагина в ней `humanizer-russian` |
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
   В дереве скрипт подставляет в `plugin.json` имя `humanizer-russian` (только `name` и
   `displayName`): `humanizer-ru` портал придерживает как похожее на плагины `humanizer`, а это
   имя прошло проверку имён (портал, 29.10). В main и в установке через GitHub имя прежнее.
   Каталог следит за этой веткой и сканирует каждый её новый коммит (по расписанию или по
   webhook): коммит в `directory` и есть выпуск в каталог, поэтому кладёшь туда только собранное
   скриптом и только после выпуска на GitHub. Заявка подана 29.10.2026 (коммит `f63efc2`, ветку
   каталог проверяет раз в 6 часов). Портал пишет «Auto-publish: Doesn't apply for now»: пока
   каждую версию публикует ревьюер Anthropic, то есть новый коммит в `directory` читает человек.
   Пока заявка на проверке, в `directory` ничего не коммить без слова владельца: что новый коммит
   сделает с идущей проверкой, неизвестно.

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
git -C "$WT" add -A && git -C "$WT" commit -m "humanizer-ru X.Y.Z: plugin-only tree built from main $(git rev-parse --short HEAD)"
git -C "$WT" push origin directory && git worktree remove --force "$WT"
```

Дальше владелец нажимает Validate на портале (Repository `Vladimir-Human/humanizer-ru`, Branch or
tag `directory`) и отправляет плагин. Validate на `directory @ f63efc2` и подача записаны в
`.grace/verification/index.xml`. Результат скана после подачи и решение ревьюера владелец приносит
скриншотами: запиши их в G-DIRECTORY-PORTAL.

Версия 3 (исследования, гейты, пакет PyPI, MCP) — в ветке `legacy-v3`, в main её не возвращать.
