# Журнал распространения

Дата снятия сведений: 2026-09-06 (API/страницы каталогов). Статусы сняты
доступными средствами; черновик не считается отправленной заявкой, отправка
не считается принятием.

| Канал | URL | Статус на 2026-09-06 | Что подтверждает |
|---|---|---|---|
| skills.sh (каталог скиллов) | https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru | листинг жив, счётчик установок 603 (снимок 2026-09-06); карточка показывает SKILL v3.31.1 при актуальном SKILL.md 3.32.1 в репозитории — сторонний индексатор отстаёт, на стороне проекта источник корректен; сторонние статусы безопасности на карточке (Trust Hub Fail, Socket Warn, Snyk Pass) — данные сторонних сканеров, причина статуса Trust Hub не установлена, уязвимостью проекта не считается | установка одной командой npx skills add |
| Glama (каталог MCP) | https://glama.ai/mcp/servers/Vladimir-Human/humanizer-ru | листинг жив (страница 200, заголовок «humanizer-ru by Vladimir-Human»), размещён владельцем 2026-09-06; карточка несёт все шесть MCP-инструментов (scan, markers, polish, detect, facts, report) — состав совпадает с contract.v1.json и tools/list (снимок 2026-09-06) | MCP-конфигурация из каталога |
| awesome-mcp-servers | https://github.com/punkpeye/awesome-mcp-servers/pull/13565 | заявка отправлена, OPEN | внешняя витрина MCP; принятие не требуется для работы |
| awesome-ai-plugins | https://github.com/hashgraph-online/awesome-ai-plugins/pull/244 | заявка отправлена 2026-09-06 (ответ на приглашение в issue #119), OPEN; описание — одно предложение по документированному позиционированию (детерминированная офлайн-диагностика и безопасная очистка следов вставки из чата; без вердиктов об авторстве); личный вход владельца не потребовался | внешняя витрина плагинов; принятие не требуется для работы |
| Smithery | https://smithery.ai | заявка не отправлена: публикация требует OAuth-входа сопровождающего (OWNER-TODO) | — |
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
- 2026-09-07: выпуск 3.34.0 опубликован — по прямому приказу владельца
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
  владельца: публикация выполнена 07:56:36Z под зафиксированным
  одноразовым исключением; повторная публикация того же выпуска
  (сторона PyPI после сбоя CI) признана завершением публикации, а не
  новым выпуском (scripts/check_release.py, --pre-release-interval).
- 2026-09-07: статус KPI не изменился — новых внешних обращений о
  реальном использовании нет; окно наблюдения до 2026-10-06, PENDING.

- 2026-09-08: выпуск 3.35.0 опубликован. Правило интервала публикаций
  (>= 86400 с) ОТМЕНЕНО приказом владельца от 2026-09-08 и удалено из
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
