# Финальная зачистка PR #26

Дата: 2026-07-17. Объект: PR #26, ветка `release/v3.4.0-deep-research`.

## Результаты

| Задача | Результат |
|---|---|
| Model claims | В `llm-fingerprints.md` проверены все заданные строки версий: найдено 0, переформулировано 0, удалено 0 - файл уже был evidence-first. Вне него четыре активные точки документации с неподтверждёнными версиями/каталогами переформулированы, удалено 0 regex или паттернов; исторический CHANGELOG не используется как источник текущих доказательств. |
| Registry warnings | Для `generated_ref_id` и `deepseek_line_ref` независимый immutable primary-источник не найден. Warnings сохранены, поимённо внесены в AUDIT и получили `warning_disposition`; повышение до primary запрещено. |
| Le Chat | Основание: 4/15, UI/DOM не равен скопированному тексту. Переоткрытие: воспроизводимый текстовый артефакт в обычном копировании, затем новый протокол из 15 прогонов. |
| PERSONA | Основание: A=5/B=1/C=2, вопросы неравны, задержка не измерялась. Переоткрытие: предзарегистрированный 5x3, проверяющий все три критерия. |
| Outreach | Подготовлены только неотправляемые черновики в `research/outreach/`; отправка запрещена до публикации v3.4.0. |

## Облачный CI

Финальный содержательный commit `81cea6a`: шесть jobs в пяти workflow имеют
статус SUCCESS.

- regex-check: https://github.com/Vladimir-Human/humanizer-ru/actions/runs/29583182283
- self-scan: https://github.com/Vladimir-Human/humanizer-ru/actions/runs/29583181768
- no-anglicisms: https://github.com/Vladimir-Human/humanizer-ru/actions/runs/29583181755
- validators (spec + registry): https://github.com/Vladimir-Human/humanizer-ru/actions/runs/29583181750
- docs-check: https://github.com/Vladimir-Human/humanizer-ru/actions/runs/29583181759

## Ручной чек-лист владельца

1. Проверить и слить PR #26.
2. На слитом commit создать **подписанный GPG** тег `v3.4.0`.
3. Создать GitHub Release по `research/RELEASE-DRAFT-v3.4.0.md`.
4. Убедиться, что skills.sh подхватил `v3.4.0`, а Gen Agent Trust Hub, Socket и Snyk зелёные.
5. Только после этого использовать соответствующие черновики из `research/outreach/`.

Не создавать тег, Release или внешние сообщения до шагов 1-4.

---

## Приписка от 2026-07-26 (версия 3.7.0)

Историческая часть отчёта выше не переписывается: она описывает состояние
перед выпуском 3.4.0. Одно уточнение к пункту 5: каталог `research/outreach/`
в репозиторий так и не был закоммичен, поэтому ссылаться на черновики из него
нельзя — их в дереве нет. Пункт остаётся невыполнимым в текущем виде.
