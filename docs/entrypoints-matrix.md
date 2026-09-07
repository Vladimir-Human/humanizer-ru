# Точки входа и носители обещаний — реестр и матрица

Единый реестр публичных носителей, через которые агент или человек
находит продукт, и матрица «потребность -> операция -> вход -> результат
-> граница -> поверхность». Источник фактов — `contract.v1.json`
(операции, коды выхода, границы) и `POSITIONING.md` (формулы
позиционирования); этот документ их пересказывает для людей и агентов,
а машинную сверку носителей выполняют гейты:

- `scripts/check_positioning_sync.py` — формулы позиционирования
  дословно во всех поверхностях, включая карточки плагинов и агентов;
- `scripts/check_identity.py` — идентичность, якоря URL, состав
  инструментов и запрещённые заявления (включая старое обещание
  «естественности») во всех действующих носителях;
- `scripts/check_contract.py` — операции, коды выхода, схемы;
- `scripts/check_live_distribution.py` — живые поверхности
  (PyPI, реестр MCP, Pages, GitHub) против локального канона.

## Матрица: потребность -> операция

| Потребность | Операция | Вход | Результат | Граница (честно) | Поверхности |
|---|---|---|---|---|---|
| Найти артефакты вставки из чата | `humanizer-markers` | текст или файлы | находки с классом A/B и причиной; rc 0/1 | отсутствие маркеров не доказывает авторство человека | CLI, пакет, MCP, action, демо |
| Снять невидимые метки текстового слоя | `humanizer-markers --remove` | файлы | safe снимается автоматически, ambiguous — только opt-in, dangerous — никогда | контейнерные файлы (PNG/DOCX/PDF) — `scripts/filemarks` в репозитории | CLI, пакет |
| Явно дочистить поддерживаемые артефакты | `humanizer-clean` | текст или файлы | очищенный текст + отчёт (классы, инварианты); rc 0/1/2 | снимает только поддерживаемые артефакты; смысл и факты не правит | CLI, пакет, MCP |
| Нормализовать типографику без правки смысла | `humanizer-polish` | текст или файлы | нормализованный текст; режимы preserve-markup/typographic | лексика и смысл не меняются; дефолтный режим снимает разметку | CLI, пакет, MCP, action |
| Проверить текст на следы машинного происхождения | `humanizer-detect` | текст | частоты связок, статус домена | вердикта об авторстве нет; эвристика, не доказательство | CLI, пакет, MCP |
| Сверить факты до/после правки | `humanizer-facts` | пара текстов | lost/added/changed + identical; `--no-additions` — строгий режим | сравнение мультимножественное: набор фактов != отношения (перестановка сумм даёт пустой diff) | CLI, пакет, MCP |
| Машиночитаемый отчёт правки | `humanizer-report` | пара файлов | токены keep/add/delete, SARI-компоненты, facts, MTLD | отчёт информативен: rc 0 при любом содержимом, кроме ошибки входа | CLI, пакет, MCP |
| Переписать стилистически | текстовое ядро SKILL.md | текст + явная просьба | переписанный текст | только по явной просьбе; гарантий естественности и сохранения смысла нет; вердиктов об авторстве нет | скилл-бандл (SKILL.md + references/) |

## Реестр публичных носителей

| Носитель | Файл / место | Что несёт | Сверяющий гейт |
|---|---|---|---|
| README (RU/EN/PyPI) | `README.md`, `README.en.md`, `README.pypi.md` | первый экран, счётчики, формулы | check_readme_first_screen, check_readme_parity, check_docs, check_identity |
| llms.txt | `llms.txt` (копия на Pages и в `.well-known/`) | маршрутизатор задач для агентов | check_identity, check_pages_router |
| Скилл-бандл | `SKILL.md` + `references/` (корень и `dsh/skills/humanizer-ru/`) | текстовое ядро, дерево решений | check_bundle_sync, check_own_style, check_examples |
| Контракт | `contract.v1.json` (корень + пакет) | операции, коды выхода, схемы, границы | check_contract, check_pkg_sync |
| Идентичность | `identity.v1.json` (корень + пакет) | устойчивые факты продукта, запрещённые заявления | check_identity |
| Позиционирование | `POSITIONING.md` | формулы (единый источник) | check_positioning_sync |
| Карточка Codex | `.codex-plugin/plugin.json` | описание, interface, defaultPrompt | check_positioning_sync, check_identity |
| Карточка OpenAI-агента | `agents/openai.yaml` | short_description, default_prompt | check_positioning_sync, check_identity |
| Карточка Gemini | `gemini-extension.json` | описание | check_positioning_sync, check_identity |
| Плагин Claude | `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | описание, версия | check_positioning_sync, check_identity |
| Плагин Cursor | `.cursor-plugin/plugin.json` | описание, версия | check_positioning_sync, check_identity |
| DSH-бандл | `dsh/package.json` + `dsh/skills/**` | описание, вендор скилла | check_positioning_sync, check_bundle_sync |
| MCP-сервер | `server.json`, `scripts/mcp/humanizer_mcp.py` (пакет `humanizer_ru.mcp_server`) | 7 инструментов, схемы из контракта | check_mcp, check_pkg_sync |
| PyPI | `humanizer-ru` (wheel + sdist) | пакет, console-входы, metadata | check_pypi_metadata, check_live_distribution |
| Реестр MCP | `io.github.Vladimir-Human/humanizer-ru` | запись server + пакет pypi | check_live_distribution |
| GitHub Pages | `vladimir-human.github.io/humanizer-ru/` | демо, status.json, машинные документы | check_demo_*, check_pages_router, check_live_distribution |
| GitHub Action | `action/action.yml` | детекция/фикс в CI чужих репозиториев | check_action_yaml, tests/test_action_* |
| Команды-шорткаты | `commands/*.md` | промпты явных команд (humanize — переписывание по явной просьбе) | — (промпт команды, не обещание продукта) |
| Внешние каталоги | skills.sh, Glama | снимки описаний (обновляются внешней стороной) | dated-снимки в research/external-feedback |

Исторические ошибки носителей не затираются: исправления фиксируются
в CHANGELOG, а снятые обещания — в `claims_forbidden` identity.v1.json,
чтобы гейт ловил их повторное появление в любом действующем носителе.
