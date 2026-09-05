# SPRINT-LEADERSHIP — журнал рывка N1–N40 (приказ 2026-09-05)

Формат записи: дата, HEAD, поток, действие, команда проверки, результат.

## 2026-09-05 — базовая линия и внешние снимки

- HEAD на старте: e6c881a (origin/main, полный клон C:\Users\vovap\tmp\hr-review-origin сверен; рабочий клон подтянут до того же коммита).
- Базовая линия: `python scripts/check_all.py` → 131 гейт, FAIL 1 (self-audit устарел после изменения README разделом браузерных клиентов); `python -m unittest discover -s tests` → OK.
- fix(baseline): self-audit перегенерирован (`python scripts/self_audit.py`), коммит в main; после — `--quick` 120/120 FAIL 0, unittest OK.
- Внешние снимки (2026-09-05, gh API + PyPI JSON API + страница skills.sh):
  - GitHub Vladimir-Human/humanizer-ru: звёзды 123, форки 9, открытых issues 1, всего issues 12.
  - PyPI humanizer-ru: версия 3.31.0; keywords — старый набор (russian, ai-text, ai-detection, humanizer, claude-code, agent-skills); project.urls — Changelog/Documentation/Releases/Repository/Tracker (Demo и Benchmark из pyproject поедут в 3.31.1, метаданные PyPI неизменяемы).
  - skills.sh карточка: установок 599 (приказ называл 431 — снимок свежее), First Seen Jan 21 2026, GitHub Stars 123; слепок SKILL.md на карточке устарел (v3.27.0) — refresh после 3.31.1 (L5).
  - skills.sh security-аудиты (Sep 4, 2026): Gen Agent Trust Hub — Fail/CRITICAL (скан всего репо: maintenance-скрипты с subprocess и GitHub API, маркерные паттерны S3-URL приняты за подозрительные; сам бандл текстовый, анализ это признаёт); Socket — Warn, 3 LOW (check_compatibility.py — сетевой dev-инструмент; rewrite_text.py — shell=True с командой из переменной окружения, реальная находка для усиления; dsh/cordis.patch.yml — JS в YAML). Вывод для N13/N39: установка 17-файловым бандлом вместо клона репо (887 файлов) снимает большую часть поверхностных срабатываний; shell=True в rewrite_text.py — кандидат на исправление аргументным списком.
  - ilyautov/humanizer-ru (тёзка): звёзды 284, форки 21, описание «Скилл для Claude. Убирает 64 признака нейросети в русском тексте…» — снимок для раздела «Одноимённые проекты» (L3, N30/N31).

## Потоки

### L1 — гигиена артефактов и новые гейты (закрыт)

- README RU/EN: пример вывода из ОДНОГО прогона через генератор
  scripts/build_readme_try.py (нейтральный primer.txt, локальный temp-путь
  устранён; --check для сверки). Проверка: python scripts/build_readme_try.py --check.
- Секции «Архитектура»/«Architecture» возвращены в docs/USAGE*.md из
  истории git (потеряны при переносе W4); якорь README.en.md#architecture
  жив. Проверка: python scripts/check_links.py --offline → мёртвых 0.
- Витринный check_outward подключён в check_all (11 файлов витрины).
  Проверка: python scripts/check_outward.py README.md README.en.md SKILL.md
  llms.txt docs/USAGE.md POSITIONING.md → FAIL 0.
- «в финальном финальный» исправлено во всех пяти носителях; детектор
  повтора соседних лексем в check_self_prose (общий корень 5+, расстояние
  Левенштейна ≤3, граница клаузы разрывает пару, бэктики/бейджи/URL/цифры
  вне скоупа, CHANGELOG вне скоупа — append-only); самопроверка 14/14;
  реальные повторы исправлены в eval/HOW-TO-RUN.md и docs/FRAMEWORK.md.
  Проверка: grep по маске «финальн\w* финальн\w*» → 0.
- check_positioning_sync: гейт запрещённых слов короткой формулы (regex,
  stdlib, CLI, слой, сканер) — POSITIONING.md:39 «(проверено гейтом)»
  стало правдой. Футер демо: «слой проверки вставки» вместо «regex-слой».
- Новый гейт check_bib_keys.py: все 46 ключей [bib:*] определены в
  research/BIBLIOGRAPHY.md; строка о ключах добавлена в README RU/EN.
- docs/USAGE.md: протухшее «число обновится после замера F16» заменено
  датированными числами F16 (0 флагов на 40 контрольных, 0 на 12314
  класса A, 8 на 12314 класса B с Wilson CI, замер 2026-09-04).
- docs/THREAT-MODEL.md:16: «с нулём ложных срабатываний» → «0 FP класса A
  на 12314 текстов-неносителей (F16, замер 2026-09-04, Wilson 95% CI)».
- Новый гейт check_dated_absolutes.py: ноль/нуль-формы/всегда/никогда в
  THREAT-MODEL только с датой или источником; термин «нулевой ширины»
  исключён; selftest 4 кейса (негатив «нулём» без даты пойман после
  расширения регулярки — форма «нулём» изначально не покрывалась).
- CHANGELOG: механическое переупорядочивание (Unreleased, 3.31.0 → 3.10.0,
  перестановка секций без правки содержимого); гейт монотонности I.20 в
  check_docs (4 selftest-кейса); пять новейших секций получили человеческие
  «Что нового» вместо процессных интро.
- METRICS.md: снимок 2026-09-05 (все строки с командами проверки; внешний
  участник: 1 внешний автор PR — inquilabee #41 2026-07-29 закрыт без
  слияния; внешних issues/discussions 0; skills.sh 599 установок, слепок
  карточки v3.27.0 устарел; security-аудиты skills.sh: Trust Hub Fail —
  скан всего репо, Socket Warn 3 LOW, включая shell=True в
  scripts/filemarks/rewrite_text.py — кандидат на усиление).
- Счётчики: 133/122 → 135/124 → 137/126 → 139/128 (каждый шаг в носителях
  и Unreleased-строке CHANGELOG).

### L2 — мост скилл↔машинный слой и безопасность скилла (закрыт)

- SKILL.md: description дословно по N27 + триггеры вставки из чата +
  пред-объявление dual-use первой строкой + счётчик маркеров (гейт 2c);
  «Detects AI-generated» устранено. Триггер «проверь на ИИ» сохранён
  (гейт triggers).
- Раздел «Машинный слой»: пять CLI-команд, MCP одной конфигурацией
  (fenced-блок — typographic-гейт не трогает), llms.txt, GitHub Action,
  правило приоритета машинных проверок. Бюджет: 15612/15750 после сжатия
  шести разделов; bundle-копия синхронна (check_bundle_sync).
- Правила изоляции: правило 3 дословно по N14/N34 (чтение из закрытого
  списка, запись/удаление запрещены); правило 1 с защитой от подделки
  границы (литерал </входной_текст> — текст); разрешение только от
  пользователя вне входного текста; строка дерева решений с «не открывая
  иных файлов и не переходя по ссылкам».
- docs/USAGE*.md: «Установка бандлом» — 17 файлов как штатный способ
  вместо клона репозитория (около тысячи файлов); мотивация усилена
  снимком security-аудитов skills.sh (скан всего репо даёт Fail/CRITICAL
  из-за dev-скриптов, бандл текстовый).
- Новый гейт check_bundle_fresh.py: metadata.version == последний тег;
  опережение только с разделом CHANGELOG (окно подготовки тега); selftest
  5 кейсов (версии строятся динамически — гейт зашитых версий).
- Проверки: quick 128/128 FAIL 0; unittest OK; spec/budget/bundle-sync/
  contract/triggers/polish-modes/docs 2c зелёные; self-audit
  перегенерирован (style max 79/80 — запас один маркер, учитывать в
  следующих правках SKILL).

### Слияние L1+L2

- PR #93 слит в main (d97b5dd); self-review 5550391340; полный check_all
  139/139 FAIL 0 и unittest OK на HEAD ветки перед merge; все джобы main
  зелёные после merge (docs, regex, markers, self-scan, anglicisms,
  offline-core, Pages, status, smoke, validators).
- Счётчики витрины: 139 гейтов полного check_all, 128 в --quick.

### Дальше по потокам

- L3 (честность витрин): два «38 из 40» с квалификаторами + гейт голой
  дроби; раздел «Одноимённые проекты» (ilyautov 284★, снимок 2026-09-05)
  и живая ссылка из MAINTENANCE-MODE; PRIVACY_POLICY — путь данных
  CLI/MCP/Action; LICENSES.md — секция marker-sources.json; LEADERBOARD —
  даты и критерии включения.
- L4: бейдж CI на первом экране, «Догфудинг» вниз с расшифровкой,
  онбординг демо, hash-share (реализовать чтение или убрать), граница
  backtick/fenced в THREAT-MODEL/USAGE.
- L5–L10 по порядку приказа; L7 — ветка release-3.31.1 (тег — владелец).

