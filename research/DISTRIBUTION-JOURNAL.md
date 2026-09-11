# Журнал распространения

Дата снятия сведений: 2026-09-06 (API/страницы каталогов). Статусы сняты
доступными средствами; черновик не считается отправленной заявкой, отправка
не считается принятием.

| Канал | URL | Статус на 2026-09-06 | Что подтверждает |
|---|---|---|---|
| skills.sh (каталог скиллов) | https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru | листинг жив, счётчик установок 603 (снимок 2026-09-06); карточка показывает SKILL v3.31.1 при актуальном SKILL.md 3.32.1 в репозитории — сторонний индексатор отстаёт, на стороне проекта источник корректен; сторонние статусы безопасности на карточке (Trust Hub Fail, Socket Warn, Snyk Pass) — данные сторонних сканеров, причина статуса Trust Hub не установлена, уязвимостью проекта не считается | установка одной командой npx skills add |
| Glama (каталог MCP) | https://glama.ai/mcp/servers/Vladimir-Human/humanizer-ru | листинг жив (страница 200, заголовок «humanizer-ru by Vladimir-Human»), размещён владельцем 2026-09-06; карточка несёт все шесть MCP-инструментов (scan, markers, polish, detect, facts, report) — состав совпадает с contract.v1.json и tools/list (снимок 2026-09-06) | MCP-конфигурация из каталога |
| awesome-mcp-servers | https://github.com/punkpeye/awesome-mcp-servers/pull/13565 | заявка отправлена, OPEN | внешняя витрина MCP; принятие не требуется для работы |
| awesome-ai-plugins | https://github.com/hashgraph-online/awesome-ai-plugins/pull/244 | заявка отправлена 2026-09-06 (ответ на приглашение в issue #119), OPEN; описание — одно предложение по документированному позиционированию (детерминированная офлайн-диагностика и безопасная очистка следов вставки из чата; без вердиктов об авторстве); личный вход проекта не потребовался | внешняя витрина плагинов; принятие не требуется для работы |
| Smithery | https://smithery.ai | заявка не отправлена: публикация требует OAuth-входа сопровождающего (project follow-ups) | — |
| Discussions #95 | https://github.com/Vladimir-Human/humanizer-ru/discussions/95 | открыт 2026-09-05, ответов внешних пользователей нет | канал первой внешней обратной связи (KPI 30 дней) |
| До/после материал 1 | https://github.com/Vladimir-Human/humanizer-ru/discussions/112 | опубликован 2026-09-06 | невидимый символ снят, числа и ссылка сохранены, команды воспроизведения |
| До/после материал 2 | https://github.com/Vladimir-Human/humanizer-ru/discussions/113 | опубликован 2026-09-06 | батч с нечитаемым файлом: код 1, прочерки и статус partial |

Установки и звёзды каталогов — наблюдение витрин, не спрос пользователей:
внешний KPI засчитывает только issue/discussion от внешнего человека о
реальном использовании (см. план наблюдения в research/SPRINT-LEADERSHIP-2026-09-05.md).

## Наблюдение KPI (30 дней)

Начало наблюдения: 2026-09-06 (дата публикации release 3.32.1 на PyPI,
08:47 UTC). Конец окна: 2026-10-06. Сбор кандидатов:
`python3 scripts/collect_external_feedback.py --since 2026-09-06 --json`
(источники: issues state=all, комментарии issues, discussions с
ответами; каждый источник несёт статус ok/unavailable — «не удалось
получить» отличается от «получено и пусто»; кандидаты помечаются
проверяемыми признаками: внешний автор, не служебная автоматизация,
признаки конкретного описания запуска/результата/проблемы, признак
рекрутинга). Не считаются: сопровождающий, служебные боты, тестовые
обращения, «поставьте звёздочку», каталожные приглашения и рекрутинг,
собственные каталожные PR, установки в smoke-тестах. Решение о зачёте —
человек-сопровождающий с объяснением и ссылкой; ноль допустим как
измерение, не как поддельный успех.

### События окна

- 2026-09-06, issue #119 (https://github.com/Vladimir-Human/humanizer-ru/issues/119,
  автор zerocodefast, внешний): приглашение добавить проект в каталог
  awesome-ai-plugins. НЕ зачтено как KPI-событие: это рекрутинг
  каталога, а не описание реального использования (сигнал solicitation,
  признаки использования отсутствуют). Ответ сопровождения:
  https://github.com/Vladimir-Human/humanizer-ru/issues/119#issuecomment-5560169106
  (описание заявки должно соответствовать документированному
  позиционированию). Канал добавлен в таблицу выше. Продолжение
  2026-09-06: заявка отправлена самостоятельно —
  https://github.com/hashgraph-online/awesome-ai-plugins/pull/244
  (секция Tools & Integrations, одно предложение по позиционированию);
  ссылка оставлена в issue
  (https://github.com/Vladimir-Human/humanizer-ru/issues/119#issuecomment-5561852586).
  На статус KPI не влияет: обращение остаётся рекрутингом каталога.
- Прочих обращений внешних пользователей за 2026-09-06 нет: сбор
  `--since 2026-09-06` дал 13 кандидатов, из них внешних — 1 (указан
  выше); статус KPI — PENDING.
- 2026-09-07: официальный реестр MCP обновлён до опубликованной версии
  пакета: `registry.modelcontextprotocol.io/v0.1/servers/io.github.Vladimir-Human%2Fhumanizer-ru/versions/latest`
  — version 3.33.0, status active (публикация через CI workflow
  publish-mcp.yml, GitHub OIDC, без секретов; запись перечитана обратно).
  Ранее реестр отдавал 3.19.2 с описанием четырёх инструментов — агент,
  устанавливающий по записи реестра, получал устаревший пакет; расхождение
  поймано scripts/check_live_distribution.py и закрыто публикацией.
- 2026-09-07: повторный сбор `--since 2026-09-06` (снимок покрытия
  2026-09-07T04:20:06Z в research/external-feedback/evidence.v1.json):
  источники issues/issue-comments/discussions — ok; кандидатов 14,
  внешних — 1 (issue #119, рекрутинг каталога, не зачтен). Новых
  обращений о реальном использовании нет; статус KPI — PENDING.
  Релиз-кандидат 3.34.0 принят (полный check_all --strict 150/0/0);
  публикация планируется не ранее 2026-09-07T20:51:52Z (интервал ≥24 ч
  от v3.33.0); окно наблюдения не перезапускается выпусками.
- 2026-09-07: выпуск 3.34.0 опубликован — по прямому приказу проекта
  цикла, не дожидаясь открытия 24-часового окна (одноразовое сокращение
  интервала для пары v3.33.0 -> v3.34.0 зафиксировано в
  docs/release-waivers.json и в CHANGELOG 3.34.0; механизм ожидания
  сохранён для будущих выпусков). Состав: GitHub Release
  2026-09-07T07:56:36Z (тег v3.34.0 annotated, подписан опубликованным
  ключом проекта; ассеты humanizer-ru.zip sha256
  feea41535382b66538fc18d8d77adae0b10572ade41d27c085a7af9613aa747b и
  откреплённая подпись .zip.asc, gpg verify — Good signature); PyPI
  3.34.0 (wheel + sdist, Trusted Publishing без долгоживущего токена,
  прогон CI https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34104815270);
  официальный реестр MCP — version 3.34.0, status active (прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34105174899,
  запись перечитана обратно). Проверка релиза по тегу v3.34.0 (прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34108556047):
  150 гейтов check_all --strict FAIL 0 SKIP 0, 394 теста OK, сборка и
  верификация архива, контракт выпуска (подпись тега + опубликованный
  Release) и интервал после публикации — зелёные. Живой снимок
  scripts/check_live_distribution.py: problems [], PyPI 3.34.0 ok,
  реестр 3.34.0 active, пути Pages 200. Запись выше «публикация
  планируется не ранее 2026-09-07T20:51:52Z» заменена приказом
  проекта: публикация выполнена 07:56:36Z под зафиксированным
  одноразовым исключением; повторная публикация того же выпуска
  (сторона PyPI после сбоя CI) признана завершением публикации, а не
  новым выпуском (scripts/check_release.py, --pre-release-interval).
- 2026-09-07: статус KPI не изменился — новых внешних обращений о
  реальном использовании нет; окно наблюдения до 2026-10-06, PENDING.

- 2026-09-08: выпуск 3.35.0 опубликован. Правило интервала публикаций
  (>= 86400 с) ОТМЕНЕНО приказом проекта от 2026-09-08 и удалено из
  проекта целиком (механизмы check_release.py, workflow-шаги,
  docs/release-waivers.json; PR #158, #159; записи отмены в RELEASE.md,
  GOVERNANCE.md раздел 2 пункт 5, AGENTS.md, CHANGELOG 3.35.0;
  отсутствие правила закреплено тестами). Состав публикации:
  GitHub Release 2026-09-08T06:39:44Z
  (https://github.com/Vladimir-Human/humanizer-ru/releases/tag/v3.35.0;
  тег v3.35.0 annotated, подписан опубликованным ключом проекта,
  tagger — автономный контур сопровождения; целевой commit
  e6a396ab75990073c074b763b5b360a6561b85ce; ассет humanizer-ru.zip
  sha256 ef5170c8319b02aae1b0a6f8461769ee15adef5ca8bba6c1d30d135427796b02
  и откреплённая подпись .zip.asc, gpg verify — Good signature;
  детерминированная сборка check_release.py --build). PyPI 3.35.0
  (wheel sha256 e009a7fd2aa96b8469c51a7ca601a6a50dae64f60df45caaa54b442d6aea5f4b,
  sdist sha256 8c5cf68b95026d35b148c25d839f5564046d0a28febfc3b73aaf0b02262288be,
  Trusted Publishing, прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34195646425;
  приёмка публикации впервые включала установленные пользовательские
  сценарии для wheel и sdist — механизм PR #151). Скачанные
  опубликованные байты сверены: sha256 совпали с PyPI, metadata прошли
  check_pypi_metadata, sdist-test на опубликованном sdist — PROBES OK и
  upgrade-smoke 3.34.0 -> 3.35.0; установленные сценарии на скачанном
  wheel — Ran 11, OK, 0 пропусков. Официальный реестр MCP: version
  3.35.0, status active, isLatest true (прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34195646680,
  запись перечитана обратно; установка по записи в чистую venv,
  tools/list — 7 инструментов, схема humanizer_facts несёт
  no_additions). Проверка релиза по тегу (прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34195633124):
  SUCCESS; локальный полный strict на дереве тега — 155 гейтов, FAIL 0,
  SKIP 0. Pages: release-триггер (механизм PR #153) отработал — первый
  деплой с тега отклонён environment-политикой (разрешала только
  ветки), политика дополнена теговым паттерном v* (настройка
  репозитория администрацией, зафиксирована здесь), повторный прогон
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34195646408
  SUCCESS; status.json: published_tag=v3.35.0,
  published_commit=e6a396a, parity ok, tests_passed true;
  check_pages_router --live-pages — целы; check_demo_browser по
  опубликованному URL — все проверки пройдены;
  check_live_distribution --json — rc=0, problems=[], deep_files
  verified. Скан логов четырёх релизных прогонов и diff тега на
  приватные токены — 0 попаданий.
- 2026-09-08: каталоги (датированные снимки 2026-09-08T06:55:57Z):
  skills.sh — основная карточка
  https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru
  ОБНОВЛЕНА до 3.35.0; алиас https://skills.sh/vladimir-human/humanizer-ru
  отдаёт устаревшую 3.25.4 (снимки 2026-09-07T23:12Z и 2026-09-08T06:55Z
  одинаковы) — подана одна содержательная заявка разрешённым механизмом:
  https://github.com/vercel-labs/skills/issues/2173; решение каталога —
  внешнее, статус PENDING. Glama
  https://glama.ai/mcp/servers/@Vladimir-Human/humanizer-ru — страница
  200, карточка несёт 6 инструментов без humanizer_clean (снимок
  устарел относительно контракта 3.35.0); каталог пересобирается
  автоматически, статус PENDING, заявка не подавалась (механизм
  обновления — автоматический).
- 2026-09-08: статус KPI не изменился — новых внешних обращений о
  реальном использовании на момент публикации нет; окно наблюдения до
  2026-10-06, PENDING.

### 2026-09-08. Выпуск 3.35.1 опубликован (патч: публичные metadata и приёмка)

- Источник: main `206f4055245c917793b7cb360512c0a5123fb83d`
  (PR #165, tree `8eb346fd9ba603440558fcd6330a08bdcfe88c83`; полный
  strict на этом дереве — 155 гейтов, FAIL 0, SKIP 0).
- Тег `v3.35.1` подписан существующим GPG-ключом проекта
  (`project signing key`), проверка Good signature локально и
  `check_release.py --release-contract` rc=0. Интервальное правило не
  применялось: отменено приказом проекта от 2026-09-08.
- Release: https://github.com/Vladimir-Human/humanizer-ru/releases/tag/v3.35.1,
  published_at 2026-09-08T11:44:38Z. Архив `humanizer-ru.zip`
  (детерминированная сборка) sha256
  `acfd5b9b284cc88d82ed78f00025e920cd15c8ab112f29b243fb9f6cf280603a`,
  подпись `humanizer-ru.zip.asc` — Good signature.
- CI: release-check, pypi-publish (включая установленные сценарии для
  wheel и sdist и новую браузерную проверку кандидата до публикации),
  publish-mcp, demo-pages — все success.
- PyPI: версия 3.35.1; скачанные артефакты сверены с дайджестами PyPI:
  wheel `bbd1a36e00cc59ff…` match True, sdist `62b6c8c5111c423c…`
  match True, yanked=False, requires_dist=None (stdlib-only);
  `check_pypi_metadata.py` на скачанных — OK, `--live` — OK;
  `--sdist-test` на скачанном sdist: PROBES OK 3.35.1 +
  upgrade-smoke 3.35.0 -> 3.35.1 OK.
- Чистая venv на скачанном wheel: импорт из site-packages, 7 консольных
  точек 3.35.1, контракт 7 инструментов, установленные сценарии
  `Ran 11 tests OK` (0 пропущено).
- Реестр MCP: 3.35.1 status=active isLatest=True; установка по записи
  реестра, initialize protocol 2025-06-18, tools/list — 7 инструментов
  (включая humanizer_clean).
- Pages: деплой release-событием записал статус с устаревшим
  `published_tag=v3.35.0` — гонка распространения свежего тега;
  расхождение поймал усиленный `check_live_distribution.py --json`
  (rc=1, «published_commit != peeled-commit тега»). Актуальный статус
  пересчитан workflow_dispatch (run 34223634340): `--json` rc=0,
  problems []; браузерная проверка опубликованного URL — OK.
  Долговременный фикс (принудительный `git fetch --tags` перед расчётом
  статуса) — PR #166.
- Token-scan логов пяти релизных ранов и diff v3.35.0..v3.35.1:
  секретов не найдено.
- Каталоги (датированные снапшоты 2026-09-08T15, фактическое состояние
  отделено от устаревших внешних копий): PyPI API — 3.35.1; Glama —
  6 уникальных инструментов (humanizer_clean отсутствует, STALE,
  пересчёт сторонний); skills.sh — карточка 3.35.0 (отстаёт на версию),
  alias ранее 3.25.4, заявка vercel-labs/skills#2173 открыта (PENDING;
  содержательная заявка одна — повторные не создавались); Smithery —
  статическая страница без машинных деталей. Внешние решения каталогов —
  внешняя зависимость (PENDING), поставка при этом проверена по
  официальным источникам (PyPI, реестр MCP, Release, Pages).

### 2026-09-08. Раунд каталогов: механизмы актуализации, корректировки, дрейф и его устранение

Датированные снапшоты и сводки механизмов: external/ (sha256 в
manifest.json): glama-mechanics-notes.md, skills-mechanics-notes.md,
smithery-mechanics-notes.md; снапшоты карточек T15-*, T1255Z-*, T1300Z-*.

- Glama: карточка несёт устаревший снимок — 6 инструментов
  (humanizer_clean отсутствует), Protocol revision 2025-11-25 на
  странице схемы (ревизия инспектора каталога, не наша negotiate),
  README-цифры до обновления счётчиков. Механизм (документация
  каталога): авто-sync «at least once per day» + «every new commit
  triggers a full re-run» (методология §1.8); инструменты берутся
  РЕАЛЬНЫМ запуском сервера (Docker build AI-inferred → microVM →
  tools/list). Публичного неаутентифицированного триггера нет;
  Discussions и мгновенный «Sync Server» — за GitHub-входом;
  glama.json — предзаявка (признание = файл + вход). Действие со своей
  стороны: glama.json с maintainers=["Vladimir-Human"] слит в main
  (PR #168, merge e451b79 2026-09-08T13:12:54Z — сам является
  коммит-триггером). Репозиторий к ре-инспекции готов: humanizer-mcp
  в pyproject, stdlib-only, server.json 3.35.1, локальный генератор
  даёт ровно 7 инструментов. Ожидание: суточный цикл; мониторинг
  страницы /schema (маркер — появление humanizer_clean). Риск: если
  снимок не обновится за 24-48 ч — вероятно падение AI-inferred
  build (логи только за логином); запасной план — явный минимальный
  Dockerfile (не применяется заранее).
- skills.sh: КОРРЕКТИРОВКА ПРЕЖНЕЙ ЗАПИСИ. «Alias отдаёт 3.25.4» —
  измерительный артефакт: строка «3.25.4» встречается только в
  path-данных статичной SVG-иконки GitHub (d="m8.35.34 6.25 3.25.4.2v…"),
  регексп по raw HTML принимал её за версию; alias-URL — живая
  страница репозитория (1 skill, 615 installs) без версионной
  карточки (проверено под несколькими UA и в og:image). Аналогично
  «3.97.75» на карточке — path иконки звезды. Заявка
  vercel-labs/skills#2173 (наша) закрыта 2026-09-08 с публичной
  корректировкой (комментарий issuecomment-5586123788). Реальный лаг:
  карточка рендерит blob-снимок SKILL.md версии 3.35.0 (hash
  43a8d6ed9712ca2ccf395bb967411fb232878c4ec4eb80703dc6881afb5f47c1,
  api/download) при 3.35.1 в main; owner-триггера обновления нет
  (#1863), сигнал npx skills add (исполнен 2026-09-08T13:45Z, rc=0)
  снимок не переписал; лаг — экземпляр трекера #780, датум с хешем
  опубликован там (issuecomment-5586124876). В репозитории менять
  нечего; ожидание автоцикла, мониторинг hash снимка.
- Smithery: ПЕРЕВОРОТ КАРТИНЫ. Серверного листинга НЕ существует:
  /servers/Vladimir-Human/humanizer-ru — Next.js-шелл (HTTP 200) с
  клиентским «404: Server Not Found or Removed»; API без ключа:
  запись отсутствует (фильтры repoOwner/repoName и namespace → 0,
  q=humanizer 832 результата — нас нет); редирект со старого
  /server/@… — генерический rewrite. Синхронизации с официальным
  реестром MCP нет (иначе серверная запись существовала бы). Жив
  листинг СКИЛЛА: smithery.ai/skills/vladimir-human/humanizer-ru
  (API-запись id 79a1730d-fcba-4ac6-b05f-e8ba645216f3, createdAt
  2026-09-05T20:40:07Z, gitUrl → поддерево dsh/skills/humanizer-ru,
  listed=true, verified=false) — авто-ингестия каталога из GitHub
  (заявка проектом не отправлялась: project follow-ups/журнал 09-06). Тело
  SKILL.md на странице СВЕЖЕЕ (рендерит 3.35.1, H1 побайтово = HEAD);
  метаданные БД (description, forks=0 при фактических 9) — снимок
  09-05, отстают; обновление — только пересчёт каталога, PUT доступен
  владельцу неймспейса (403/409 без него), claim через GitHub-вход
  отсутствует. Автономно: только чтение и снапшоты; серверная
  публикация (MCPB/CLI) не выполнялась и остаётся опциональным
  пунктом BACKLOG — на поставку не влияет. Ранняя запись «статическая страница без
  машинных деталей» уточнена: это был шелл отсутствующего серверного
  листинга.
- Официальный реестр MCP (первоисточник) актуален: 3.35.1,
  status=active, isLatest=True, tools/list 7 — поставка проверена по
  первоисточнику; отставание зеркал — внешняя зависимость.
- Дрейф и устранение (пункт C): контрольная батарея на main e451b79
  выявила 3 FAIL strict — (1) истинный дрейф репозитория: check_docs
  «новый объект верхнего уровня glama.json» (PR #168 не обновил
  манифест состава корня; CI того PR был path-фильтрован и гейт не
  запускал); (2,3) среда: устаревший локальный dist/ (3.34.0) ронял
  livedist-selftest и sdist-test (dist/ gitignored, в поставку не
  входит). Устранение: PR #169 (манифест check_docs + попутно
  фактический дрейф текстов: docstring MCP-сервера в обеих зеркальных
  копиях и docs/USAGE.md несли «те же шесть» при семи инструментах —
  исправлено на семь с humanizer_clean; зеркала побайтово идентичны,
  check_mcp OK) — MERGED, main 697b094; локальный dist/ очищен.
  Контрольный strict на 697b094 — в delivery/driftcheck-strict-after-fix.log.
- Итоговый реестр: external_pending приведён к фактическим
  формулировкам (Glama — ожидание суточного цикла; skills.sh —
  ожидание автоцикла, #2173 закрыта корректировкой, датум в #780;
  Smithery — серверного листинга нет, скилл-листинг синхронен по
  телу, метаданные — пересчёт); re-verify гейтом rc=0
  (delivery/d12-verify-after-pending-fix.log). 12/12 PASS не менялись.
- Инцидент среды (не дефект продукта): снапшот-скрипт с двоеточием в
  имени файла (strftime %H:%M) записал данные в NTFS alternate data
  stream; снимки пересохранены с именами без двоеточий (T1255Z-*),
  артефакт удалён.

### 2026-09-11. Свип каталога awesome-ai-plugins: 79/100 на main, находки закрыты локально до 98/100 (PR #225)

- Свежий свип каталога hashgraph-online/awesome-ai-plugins (закреплённый
  workflow sweep-open-prs.yml, SHA экшена caba2e96 = plugin-scanner
  3.0.123, mode=scan, min_score=80, fail_on_severity=high,
  trust_repository_policy=false, online=false) отклонил PR #244:
  79/100 (critical:0, high:6, medium:6, low:3, info:6) на клоне ветки по
  умолчанию — job
  https://github.com/hashgraph-online/awesome-ai-plugins/actions/runs/34609031384/job/103294663075.
  Инструкция каталога: rule-level remediate-or-document, пересканировать
  исходник и каталог, запросить re-review при счёте ≥80.
- Локально свип воспроизведён тем же пакетом (plugin-scanner==3.0.123,
  отдельный venv, скан свежего экспорта дерева): базовые 79/100 и состав
  находок совпали с job-логом. Закрытие по правилам — в PR #225 и
  docs/PLUGIN-SCANNER-NOTES.md (секция на правило: триггер, диспозиция,
  подтверждающая команда): high×6 DANGEROUS_DYNAMIC_EXECUTION устранены
  (node-обвязки check_demo_parity/check_demo_perf загружают
  demo/markers.js через require вместо динамического выполнения
  прочитанной строки; selftest'ы обоих гейтов зелёные, мутанты ловятся);
  DEPENDENCY_LOCKFILE_MISSING — uv.lock в корне (нулевой состав,
  runtime-зависимостей нет) и dsh/pnpm-lock.yaml (pnpm 10.28.0,
  --lockfile-only, нулевой состав); SKILLS_DIR_MISSING — skills в
  .codex-plugin/plugin.json переведён на каталог ./dsh/skills
  (байт-синхронная вендорная копия, check_bundle_sync зелёный);
  SECURITY_MD_MISSING/LICENSE_MISSING — dsh/SECURITY.md (границы бандла +
  указатель на корневую политику) и dsh/LICENSE (побайтовая копия
  корневого MIT); DEPENDABOT_MISSING — npm-запись /dsh в корневом
  dependabot.yml плюс пакетная декларация dsh/.github/dependabot.yml;
  info-находки — author объектом и interface-ассеты
  (termsOfServiceURL=текст MIT, composerIcon/logo/screenshots —
  существующие файлы) в codex-манифесте, .codexignore в корне
  (зарегистрирован в TOP_LEVEL_MANIFEST check_docs.py вместе с uv.lock).
  DSH_RUNTIME_APPLY_MISSING (medium, патч-онли бандл dsh/) — оставлен
  задокументированным: правило живо и в 3.0.123, и в 3.0.143, несмотря на
  hol-guard#2862, закрытый completed 2026-09-09; подделывать apply(ctx)
  значило бы искажать устройство бандла.
- Локальный счёт после правок: 98/100 (A) на обоих пинах — 3.0.123 (пин
  каталога) и 3.0.143 (пин hol-plugin-scanner.yml): critical:0, high:0,
  medium:1 (документированная граница), low:0, info:0; код возврата 0 при
  --min-score 80 --fail-on-severity high. Trust 59.2 → 70.93.
  check_all --quick на дереве после rebase на ba7e9b6: 145 гейтов,
  FAIL 0, SKIP 1 (средозависимый, как и до правок).
- Статус: PR #225
  (https://github.com/Vladimir-Human/humanizer-ru/pull/225, метка
  meta/autonomous) — до вычитки человеком и слияния. Свип каталога
  клонирует ветку по умолчанию, поэтому пересканирование и запрос
  re-review по hashgraph-online/awesome-ai-plugins#244 возможны только
  после слияния в main.
