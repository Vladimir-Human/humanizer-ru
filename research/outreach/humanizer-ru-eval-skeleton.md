# Черновик открытого benchmark `humanizer-ru-eval`

**Статус: не создавать и не публиковать до v3.4.0.** Это спецификация
нейтрального сравнительного набора, не рейтинг «обхода» детекторов.

## Предлагаемая структура

```text
humanizer-ru-eval/
  README.md
  LICENSE
  manifests/
    v1.json
  corpus/
    ai/
      provider-anonymized/
    human/
      public-domain/
      licensed/
  sources/
    registry.json
  expectations/
    hard-artifacts.json
    contextual-artifacts.json
  tools/
    run_eval.py
    validate_registry.py
  results/
    candidate-name/v1.json
```

## Реестр corpus

Каждая запись `sources/registry.json` должна содержать: `id`, `kind` (`ai` или
`human`), язык, жанр, лицензию/основание публикации, immutable source URL или
локальный digest, дату доступа, способ копирования, удаление персональных
данных и ожидаемую категорию. Для ИИ-текста отдельно: известный сервис только
если подтверждён, режим, промпт, дата, raw-output и отметка о UI/DOM-слое.

## Методика

1. Заморозить manifest с хешами corpus до запуска кандидатов.
2. Запускать кандидата без сетевого доступа и без модификации исходных файлов.
3. Считать отдельно hard-artifact recall, contextual precision/recall,
   false-positive rate на human corpus и долю результатов `needs-review`.
4. Публиковать raw matches, версию кандидата, команду, digest manifest и
   ошибки запуска; не публиковать personal data или непроверяемую атрибуцию
   модели.
5. Не суммировать мягкие языковые признаки в «процент ИИ» и не превращать
   benchmark в средство обхода детекторов.

## Одна воспроизводимая команда

```sh
python3 tools/run_eval.py --manifest manifests/v1.json --candidate /path/to/candidate
```

Результат должен быть JSON в `results/<candidate>/<version>.json` с числом
записей, совпадений по категориям, false positives, пропусками и полным
digest входного manifest. Конкурент может добавить собственный runner только
если сохраняет эту схему результата.
