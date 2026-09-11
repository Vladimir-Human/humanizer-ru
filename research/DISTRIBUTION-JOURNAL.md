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
- 2026-09-11: спрос и витрина — день внешних действий и первой авторской
  публикации. Owner-only метрики GitHub (traffic/views: 1304 просмотра,
  490 уникальных за 14 дней; referrers: Google 420/229, github.com 171/61,
  yandex.ru 9/7, web.telegram 5/2; clones 15122/1552 — ряд загрязнён
  собственным CI, оговорка METRICS.md в силе; команды:
  `gh api repos/Vladimir-Human/humanizer-ru/traffic/{views,clones,popular/referrers}`).
  skills.sh: 633 установки (снимок страницы 11.09; 603 на 06.09).
  Звёзды 123, последняя 04.09; KPI-окно без изменений: внешних обращений
  о реальном использовании нет, PENDING. Тёзка ilyautov/humanizer-ru:
  333 звезды, 21 форк (`gh api repos/ilyautov/humanizer-ru`, 11.09) —
  снимок в README «Одноимённые проекты» обновлён до 2026-09-11.
- 2026-09-11: каналы. Topics репозитория расширены до 20 (добавлены mcp,
  claude-code, cursor; снятые 08.09 вводящие теги не возвращались).
  Внешние нитки: ilyautov/humanizer-ru#57 — принят публичный бенчмарк
  (comment 5636044084; после ответа второй стороны о формате открыт
  протокол у нас — issue #220: заморозка корпуса sha256, команда
  воспроизведения на каждое число, публикация неудобных результатов,
  отказ от вердиктов об авторстве); issue #119 — статус-апдейт по свежему
  свипу каталога awesome-ai-plugins (comment 5636044451; свип 11.09:
  79/100 при пороге 80, remediation rule-level находок начата).
- 2026-09-11: первая авторская публикация проекта. Статья «Два
  humanizer-ru: я отозвал свою лучшую метрику и зову тёзку на бенчмарк»
  опубликована на Pages:
  https://vladimir-human.github.io/humanizer-ru/articles/two-humanizer-ru/
  (HTTP 200, 11.09; числа из реестра фактов и ERRATA, humanizer-scan по
  телу — 0 признаков, check_outward — 0 FAIL). Три пояснительные страницы
  под поисковые запросы артефактов вставки: /oaicite/, /invisible/, /utm/
  (все HTTP 200; sitemap.xml и robots.txt обновлены; live-проверка:
  `python3 scripts/check_pages_router.py --live-pages` — PASS). Анонс:
  Discussions #224. Авторские каналы (Habr, vc.ru, Telegram) остаются
  заблокированными отсутствием учётных записей; материалы готовы
  (контент-пакет 11.09: статья, серия из 4 постов, стартер канала).
- 2026-09-11: слиты PR #221 (согласованность витрины), #222 (SEO-страницы
  и статья), #223 (числа первого экрана README), dependabot #217–#219
  (actions/checkout v7, actions/upload-artifact v7,
  ai-plugin-scanner-action v1.2.651). main ba7e9b6, push-CI 9/9 SUCCESS.

- 2026-09-11: выпуск 3.36.0 опубликован по постоянному поручению
  (GOVERNANCE.md раздел 2 пункт 5). Состав: GitHub Release
  2026-09-11T18:13:39Z
  (https://github.com/Vladimir-Human/humanizer-ru/releases/tag/v3.36.0;
  тег v3.36.0 annotated, подписан опубликованным ключом проекта
  023E1F146B59348F, git verify-tag — Good signature; целевой commit
  7cd87b1; ассет humanizer-ru.zip 745710 байт, sha256
  2297fd3ec92d5df19daeb5ce18bef33d12d88268af6942df74d8dfe91682bda1 —
  локальная сборка check_release.py --build равна верификации --verify;
  откреплённая подпись .zip.asc). Приёмка до тега: check_all --strict
  156 гейтов FAIL 0 SKIP 0, unittest 480 OK, sdist-test в чистом venv
  (Ran 450 tests OK, skipped=140) c upgrade-smoke 3.35.2 -> 3.36.0.
  PyPI 3.36.0 — Trusted Publishing OIDC (прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34632087911);
  официальный реестр MCP — version 3.36.0 (прогон CI
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34632087625);
  release-check на теге SUCCESS (прогон
  https://github.com/Vladimir-Human/humanizer-ru/actions/runs/34631935076).
  Перечитывание поверхностей в тот же день: PyPI info.version 3.36.0
  (https://pypi.org/pypi/humanizer-ru/json), реестр MCP 3.36.0,
  Pages status.json published_tag v3.36.0 / lag_commits 0 после
  повторного workflow_dispatch (гонка деплоя: push-прогон записал статус
  за 35 секунд до распространения тега — пересчёт штатным механизмом),
  check_live_distribution rc=0, check_pages_router --live-pages PASS.
  Смоук чистой venv опубликованного пакета: восемь входов 3.36.0,
  коды выхода по контракту (артефакт 1, нечитаемый вход 2 с JSON-конвертом
  в stdout, чистый текст 0), --language en снимает oacite из английского
  текста. Дефект, пойманный релизным гейтом и исправленный в этом выпуске:
  test_ci_policy_fixture падал в sdist вместо корректного пропуска
  (конвенция skipUnless(REPO_ONLY) восстановлена).
- 2026-09-11: каталог awesome-ai-plugins — remediation rule-level находок
  слит в main (PR #225, bc17d2b): локальный счёт пином каталога
  (plugin-scanner 3.0.123) 79/100 -> 98/100 (A), 0 critical / 0 high /
  1 medium (документированная граница патч-онли бандла), подтверждено
  вторым пином 3.0.143; re-review запрошен комментарием
  https://github.com/hashgraph-online/awesome-ai-plugins/pull/244#issuecomment-5638656478.
  Листинг не заявляется до свипа каталога с порогом >= 80.
- 2026-09-11 (вечер): внешние авторские каналы — по прямому поручению
  владельца («полная автономия», «заполни и отправь») снята блокировка
  «публикация только владельцем»; сессии площадок предоставлены владельцем
  в управляемом браузере. Habr: первая внешняя авторская статья «Два
  humanizer-ru: я отозвал свою лучшую метрику и зову тёзку на бенчмарк»
  отправлена в песочницу, https://habr.com/ru/sandbox/303744/ (статус:
  премодерация; хабы Машинное обучение / Open source / Открытые данные,
  жанр Ретроспектива). Подготовка: панель из шести LLM-редакторов
  (варианты, синтез, слепая оценка, red-team), итоговый текст —
  humanizer-markers 0 (rc=0), humanizer-scan 1 мягкий структурный признак
  (прямые кавычки — типографика по приказу владельца), check_outward
  0 FAIL / 0 WARN; фактическая ошибка черновика («набрано за два с
  половиной месяца» при возрасте репозитория 5,3 месяца) поймана панелью
  и исправлена до публикации; версия в тексте обновлена до 3.36.0.
  Smithery: skill-листинг существует и актуален —
  https://smithery.ai/skills/Vladimir-Human/humanizer-ru (синхронизация
  SKILL.md из GitHub, на странице v3.36.0; публичная проверка 11.09).
  В ходе вечерней сессии по ошибке создан дубликат листинга в личном
  пространстве (режим GitHub-URL отдавал 500, загрузка бандла прошла);
  дубликат удалён владельцем в тот же вечер, единственный листинг —
  под пространством Vladimir-Human. MCP-серверный листинг на Smithery не
  создавался: платформа требует hosted upstreamUrl, что несовместимо с
  офлайн-позиционированием продукта (текст не покидает машину);
  ограничение зафиксировано, обход не заявляется.
  awesome-claude-code: обнаружена существующая открытая заявка #2212
  (12.07.2026, validation-passed) — дублирующая заявка #2814 закрыта
  валидатором площадки по правилу «одна открытая заявка на автора»;
  в #2212 обновлён Description свежими числами (40 маркеров, 38 записей
  доказательств, 633 установки skills.sh на 11.09.2026), ревалидация
  бота — passed (комментарий 19:11 UTC). vc.ru: отложено (лимит запросов
  площадки в сессии); Telegram: не запускался по решению владельца.
  Статусы каналов: Habr — на премодерации; Smithery skill — LIVE;
  awesome-claude-code — OPEN/validation-passed (ожидание мейнтейнера);
  awesome-ai-plugins #244 — ожидается свип каталога после bc17d2b.