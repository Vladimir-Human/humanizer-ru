# AGENTS.md — для агентов, которые правят этот репозиторий

humanizer-ru — навык (Agent Skill), который переписывает русский ИИ-текст по-человечески,
чистит технические следы и сверяет факты. Всё, что получает пользователь, лежит в `skills/humanizer-ru/`.

## Карта

| Путь | Что это |
|---|---|
| `skills/humanizer-ru/SKILL.md` | инструкция для агента, главный файл продукта |
| `skills/humanizer-ru/references/` | `patterns.md` (примеры и границы), `examples.md` (тексты целиком), `genres.md` (жанры и ВКР/статьи), `interview.md` (вопросы автору), `detectors.md` (ИИ-детекторы и «Антиплагиат») |
| `skills/humanizer-ru/scripts/` | `check_facts.py`, `clean_paste.py`, `lint_style.py`, `rules.json`: только стандартная библиотека Python 3.8+, офлайн |
| `prompt/chat.md` | сжатый промпт для веб-чатов (до 4000 знаков между маркерами `prompt:start`/`prompt:end`, синхронизирован с `site/sverka/prompt.txt`) |
| `site/` | офлайн-страницы на GitHub Pages (`index.html`, `check/` с `engine.js`/`rules.json`/`facts.js`, `sverka/` с `notes.js`/`prompt.txt`, `sw.js`, `llms.txt`, `robots.txt`, `sitemap.xml`); строгий CSP `default-src 'none'` |
| `eval/` | слепое сравнение с другими навыками, пробы правил, калибровка линтера и человеческие контроли |
| `scripts/` | `check_repo.py` (целостность репо, манифестов, `site/` и `.grace/`), `check_scripts.py` (свойства и `--against`), `check_site_facts.py` (полный паритет Python ↔ JS), `build_zip.py` (архив для Claude.ai в `dist/humanizer-ru-skill.zip`), `build_directory.py` (дерево для каталога Anthropic) |
| `tests/` | тесты скриптов, JS-паритета, браузерного UX, репозитория и `eval/` |
| `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `gemini-extension.json` | манифесты плагинов (Claude Code, Codex, Cursor, Gemini CLI); `icon.png` и ссылки в `.claude-plugin/plugin.json` читает каталог плагинов Anthropic |
| ветка `directory` | только плагин (15 файлов, без `eval/`, `scripts/`, `tests/` и этих заметок): её читает портал каталога Anthropic; собирает `scripts/build_directory.py`; имя плагина в ней `humanizer-russian` |
| `dist/humanizer-ru-skill.zip` | неотслеживаемый локальный артефакт релиза (в `.gitignore`), пересобирается `scripts/build_zip.py` при выпуске |
| `.grace/` | требования, граф модулей и карта проверок (GRACE) |

## Правила

1. Меняешь поведение навыка — прогони сравнение (`eval/README.md`) хотя бы на dev-наборе / пробах и
   сравни с прошлым итогом. Правка, которая ухудшает итог, не принимается.
2. **Строгая изоляция отложенных наборов (`R-HOLDOUT`):** НИКОГДА не читай, не выводи в лог и не
   подбирай правила по текстам `holdout5` (`eval/corpus/texts/h5_*`, `eval/results/holdout5-*`) и
   `holdout4`. `scripts/check_scripts.py` и `scripts/check_site_facts.py` по умолчанию скрывают
   текстовые детали `holdout5` (печатают только агрегатные счётчики и падают при регрессии).
3. `SKILL.md` держи коротким: новое правило заменяет старое, а не добавляется сверху. Примеры — в
   `references/`. Каждая пара «Было → Стало» в `references/` обязана сохранять факты (`R-REFERENCES-KEEP-FACTS`).
4. Скрипты навыка — только чистая стандартная библиотека Python без сети и сторонних процессов
   (`R-TEXT-ONLY`, проверяется AST-allowlist в `check_repo.py`). Новый случай — тест в `tests/`.
5. **Паритет Python ↔ JS:** любое изменение `check_facts.py` синхронно переносится в `site/check/facts.js`,
   изменение `lint_style.py` или `clean_paste.py` — в `site/check/engine.js`, изменение `rules.json` —
   в `site/check/rules.json` (побайтово), изменение `eval/evallib.py:split_notes` — в `site/sverka/notes.js`,
   изменение `prompt/chat.md` — в `site/sverka/prompt.txt`.
6. Версия меняется одновременно в `SKILL.md`, `.claude-plugin/*.json`, `.codex-plugin/plugin.json`,
   `.cursor-plugin/plugin.json`, `gemini-extension.json`, `CHANGELOG.md`, `.grace/context/requirements.xml`,
   `site/index.html` (`softwareVersion`) и `site/llms.txt`; `python scripts/check_repo.py` это проверяет.
7. Переводы строк LF, без BOM и невидимых символов в файлах навыка; в `skills/` не должно оставаться
   `.bak`/`.swp`/`.DS_Store`/`Thumbs.db`.
8. Не запускать локальные нейросетевые модели (`R-NO-LOCAL-NN`, решение владельца).
9. Меняешь поведение скрипта — обнови контракт в коде, `.grace/` и `REVIEW.md` (если промах прошёл
   мимо тестов — добавь триггер диффа в `REVIEW.md`).
10. После каждого выпуска пересобери `dist/humanizer-ru-skill.zip` для GitHub Release и ветку
    `directory` (ниже). Каталог Anthropic читает ветку `directory`, а не `main`: в `main` лежат
    `eval/` (читает `FAL_KEY`), заметки с путём к иконке и >1800 файлов, за что портал придерживает
    плагин. Ни один файл дерева, кроме `plugin.json`, не называет иконку. В дереве скрипт подставляет
    в `plugin.json` имя `humanizer-russian` (только `name` и `displayName`). В `main` и в установке
    через GitHub имя прежнее (`humanizer-ru`).
    **Статус ветки `directory`:** заявка подана 29.10.2026 (коммит `f63efc2`, v4.1.6; портал проверяет
    ветку раз в 6 часов, «Auto-publish: Doesn't apply for now» — каждую версию читает ревьюер
    Anthropic). Пока заявка на проверке, **в `directory` ничего не коммить и не пушить без слова
    владельца**; локально проверяй только сухой сборкой во временную папку (`$env:TEMP` / `mktemp -d`).

Перед коммитом (на Windows обязательно `-t tests`!):

```sh
python scripts/check_repo.py
python -m unittest discover -s tests -t tests -v
python scripts/check_site_facts.py
```

Меняешь скрипт навыка — ещё `python scripts/check_scripts.py --against main`: свойства на всех
текстах `eval/` должны выполняться, регрессий на `holdout5` быть не должно (0 `clean -> error`,
текст скрыт по `R-HOLDOUT`), а каждую новую публичную ошибку сверки прочитай глазами (ложная
тревога на старых правках — дефект скрипта, а не правки).

Ветка `directory` (только после выпуска и с согласия владельца, из чистого `main`; нужен git 2.42+).
Первый раз вместо `add` с веткой: `git worktree add --orphan -b directory "$WT"`.

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
скринами: запиши их в `G-DIRECTORY-PORTAL`.

Версия 3 (исследования, гейты, пакет PyPI, MCP) — в ветке `legacy-v3`, в `main` её не возвращать.
