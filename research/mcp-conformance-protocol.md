# Протокол проверки MCP-conformance (v3.18.0, 2026-09-03)

Статус: проверка stdlib-сервера `scripts/mcp/humanizer_mcp.py` перед
выпуском v3.18.0. Правило одного прохода плана v2 (батч 2) соблюдено:
stdlib-реализация закрыла conformance за один проход, переход на
официальный SDK как optional extra `humanizer-ru[mcp]` не понадобился.

Среда: Windows, Python 3.13 (системный и чистые venv), node/npx из PATH,
дерево ветки release v3.18.0 (коммит измерения — см. снимок
`eval/facts/self-audit.v1.json` и журнал версий).

## 1. Conformance в репозитории (гейты и тесты)

Команды и результаты на момент проверки:

```sh
python3 scripts/check_mcp.py --selftest
# САМОПРОВЕРКА check_mcp: 4 из 4 PASS; негатив: подделанные ответы ловятся

python3 scripts/check_mcp.py
# MCP: conformance-ядро зелёное, схемы = контракт

python3 scripts/mcp/humanizer_mcp.py --selftest
# САМОПРОВЕРКА humanizer_mcp: 15 из 15 PASS (живые вызовы включены)

python3 -m unittest discover -s tests -p "test_mcp_conformance.py"
# Ran 13 tests ... OK

python3 scripts/check_release.py --sdist-test
# PROBES OK: точка входа humanizer-mcp + initialize-roundtrip в чистом venv
```

Покрытое: initialize (матрица версий 2025-06-18, 2025-03-26,
2024-11-05; неподдерживаемая версия отвечает последней поддерживаемой);
notifications/initialized и notifications/cancelled без ответа; framing
— newline-delimited, один ответ на строку, id эхо; tools/list побайтово
равен схемам, сгенерированным из contract.v1.json; tools/call для всех
четырёх инструментов: находка маркеров (CLI-код 1) — успешный tool
result с isError false, structuredContent валиден относительно
outputSchema контракта (мини-валидатор check_contract), out-of-scope на
английском входе, режимы polish (strip/preserve-markup/typographic),
жанры scan/detect, идемпотентный двойной вызов; ошибки JSON-RPC: -32700
(битый JSON, id null), -32600 (не-объект), -32601 (неизвестный метод),
-32602 (неизвестный инструмент, отсутствующий text, значение вне enum,
лишний параметр); ping — пустой result.

## 2. Независимый клиент A: официальный Python SDK (пакет `mcp`)

```sh
python -m venv <venv>
<venv>/Scripts/python -m pip install mcp
# клиент: mcp.ClientSession + mcp.client.stdio.stdio_client против
# scripts/mcp/humanizer_mcp.py (PYTHONPATH=src)
```

Результат (2026-09-03):

```text
SDK initialize: server=humanizer-ru-mcp version=3.18.0 protocol=2025-06-18
SDK capabilities.tools: True
SDK tools/list: ["humanizer_detect", "humanizer_markers", "humanizer_polish", "humanizer_scan"]
SDK tools/call markers: isError=False tool=humanizer-markers count=2
SDK tools/call polish typographic: isError=False guillemets=True
SDK unknown tool -> ошибка клиента: MCPError
```

Честная нота: первый запуск зонда упал на именах атрибутов самого SDK
(pydantic snake_case — server_info, is_error, structured_content; на
проводе JSON остаётся camelCase). Это ошибка одноразового
клиентского зонда, а не сервера: initialize к тому моменту уже прошёл.
После правки зонда — чисто.

## 3. Независимый клиент B: MCP Inspector (CLI)

```sh
npx -y @modelcontextprotocol/inspector --cli python scripts/mcp/humanizer_mcp.py --method tools/list
npx -y @modelcontextprotocol/inspector --cli python scripts/mcp/humanizer_mcp.py \
  --method tools/call --tool-name humanizer_markers --tool-arg text="<проба с contentReference>"
```

Результат (2026-09-03): обе команды rc 0; tools/list — четыре
инструмента с генерируемыми схемами и аннотациями; tools/call —
`isError: false`, structuredContent — конверт `{tool, schema, files}`,
count 1 на пробном тексте (одна метка contentReference).

Честная нота: кириллица в `--tool-arg` через npx CLI на Windows дошла до
сервера в консольной кодировке (в фрагменте отчёта виден байтовый
артефакт отображения). Это артефакт передачи аргументов тестовым
харнессом, а не дефект сервера: тот же текст через SDK приходит чистым
UTF-8 (count 2 — contentReference и utm-метка), JSON-конверт валиден в
обоих случаях, коды и поля совпадают.

## 4. Вывод

Сервер на стандартной библиотеке закрыл conformance-критерии за один
проход: гейты репозитория, 13 conformance-тестов, sdist-зонд и реальные
вызовы из двух независимых клиентов (официальный Python SDK и MCP
Inspector). Оснований для перехода на официальный SDK как optional extra
нет. Воспроизведение: команды разделов 1—3; сетевые шаги (pip install
mcp, npx) требуют доступа в интернет, остальное — локально.
