# CONSILIUM-REPORT — humanizer-ru v3.5.0-consilium

Дата: 2026-07-21. Эталон: тег v3.4.0. База: commit 8f70f65 (ветка
research/v3.5.0-deep-research). Консилиум: 5 независимых прогонов (4 внешних
варианта + собственный) арбитражными субагентами.

## Матрица оценок

| Вариант | Балл | Вердикт | Ключевой факт прогона |
|---|---|---|---|
| **v3.5.0-consilium (8f70f65, база)** | **99/100** | **БАЗА** | 38/38 markers, 38/38 parity, 14/14 registry, 19/19 docs, corpus+eval green, 0 ручных правок |
| fable-5 | 88/100 | PASS условно | NO_NEW_MARKERS, check_registry_freshness 8/8, нужны 2 правки README-тегов |
| sol-5-6 | 59/100 | НЕ БАЗА | apply не обновляет metadata version → check_docs FAIL; release-preflight step всегда FAIL |
| fable-5-2 | 56/100 | НЕ БАЗА | self-scan CI FAIL (4 маркера в собственных доках); недоказанный utm_copilot primary |
| grok-4.5 | 34/100 | FAIL | деструктивный: 5 workflow → echo-заглушки, references/*.md → стабы, CHANGELOG стёрт, mojibake |

## База и обоснование

**База — собственный v3.5.0 (8f70f65).** Независимый арбитр поставил 99/100:
все 12 валидаторов зелёные без правок, инварианты выполнены, 2 новых маркера
с immutable-источниками и fixtures, честное документирование ограничений.
Ни один внешний вариант не прошёл инварианты без правок; fable-5 ближе всех,
но требует ручных правок и не добавляет нового доказательного содержания.

## Перенесённые улучшения

| Элемент | Откуда | Почему | Состояние |
|---|---|---|---|
| `scripts/check_release.py` | sol-5-6 | Детерминированная сборка ZIP с allowlist (исключает research/, tests/, .github/, eval/), защитой от traversal/secrets/duplicates, 11 selftest. У базы был только inline release-check.yml без упаковки архива. | Перенесён, selftest 11/11, подключён в validators.yml + release-check.yml |

Перенос `check_registry_freshness.py` из fable-5 **отклонён**: my
`check_fixture_sources.py` уже имеет freshness-warn (>180 дней) и запрет
«ЗАДАЧА»; добавление re_verified потребовало бы schema-change всех 14 записей
ради marginal-выигрыша. Записано в GAPS как future work.

## Отброшенное

| Элемент | Откуда | Почему |
|---|---|---|
| overlay целиком | fable-5-2 | docs-only, self-scan CI FAIL, недоказанный primary claim |
| patch целиком | fable-5 | fable-5 добавил registry-freshness, но база уже покрывает; README-теги не обновлены (check_docs FAIL) |
| apply_v3.4.1.py | sol-5-6 | не обновляет metadata version → check_docs FAIL; CRLF-нормализация ломает LF |
| release-preflight.yml PUA-скан шаг | sol-5-6 | всегда FAIL (fixture содержит PUA-маркеры → check_markers exit 1); но check_release.py из того же варианта взят |
| полный репо-снимок | grok-4.5 | 5 workflow заменены на echo-заглушки; references/*.md заменены на 149-байтные стабы; CHANGELOG стёрт; mojibake ломает check_corpus; check_docs selftest 19→5 (регрессия покрытия) |

## Финальные проверки (ветка release/v3.5.0-consilium)

| Проверка | Результат |
|---|---|
| check_markers.py | 38/38 |
| check_markers.py --parity | 38/38 |
| check_spec.py --selftest | 14/14 |
| check_spec.py --strict | 0 warnings |
| check_fixture_sources.py --selftest | 16/16 |
| check_fixture_sources.py registry | 14/14 (2 warnings видимы) |
| count_style_markers.py --selftest | 9/9 |
| check_docs.py --selftest | 19/19 |
| check_docs.py | 0 ошибок |
| check_corpus.py --selftest | 3/3 |
| check_corpus.py | human 0, raw BOM, boundary OK |
| check_release.py --selftest | 11/11 |
| eval/run_eval.py | 24 файла, 0 hash-mismatch, 0 FP, 2 boundary OK |
| py_compile (8 файлов) | OK |

## Архив

- Файл: `dist/humanizer-ru.zip` (allowlist: SKILL.md + README* + CHANGELOG + PERSONA + SECURITY* + LICENSE + references/ + scripts/; без research/, tests/, .github/, eval/)
- SHA-256: `3595d80b5ce4027e8a937ca52d85535a0a4ec705c6be9debe3ebe27917649d96`
- Сборка детерминированная (FIXED_TIME, sorted, compresslevel=9); A/B байтово идентичны.
- Smoke-test установки: распакован в `~/.claude/skills/`, `~/.codex/skills/`, `~/.agents/skills/` (во временном HOME) — SKILL.md в корне, frontmatter корректен (name=humanizer-ru, version=3.5.0), check_markers.py 38/38 из установленной копии.

## Draft PR

Push ветки release/v3.5.0-consilium и draft PR в main — после green CI.

## Ручные шаги владельца

1. Review и merge PR.
2. Создать подписанный GPG-тег v3.5.0 на merge-commit.
3. Опубликовать GitHub Release из research/RELEASE-DRAFT-v3.5.0.md.
4. Проверить skills.sh переиндексацию и Trust Hub/Socket/Snyk.
