# humanizer-ru
Находит следы машинного текста в русском и объясняет их вам

![Терминал humanizer-markers подсвечивает следы машинного текста и объясняет причину каждого флага](assets/hero.svg)

[![License: MIT](https://img.shields.io/github/license/Vladimir-Human/humanizer-ru)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/humanizer-ru?label=PyPI&color=blue)](https://pypi.org/project/humanizer-ru/)
[![CI](https://img.shields.io/github/actions/workflow/status/Vladimir-Human/humanizer-ru/regex-check.yml?branch=main&label=CI)](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml?query=branch%3Amain)

## Кому это нужно

- Редактору и преподавателю: проверить текст перед публикацией: `humanizer-markers --scan файл.md`.
- Разработчику и CI: гейт вставки из чат-интерфейсов: [action и контракт](contract.v1.json).
- Пользователю ИИ-ассистента: та же проверка внутри агентной среды: [MCP одной конфигурацией](#mcp-одной-конфигурацией) или [демо](https://vladimir-human.github.io/humanizer-ru/).

## Попробовать за 30 секунд

- [Демо в браузере](https://vladimir-human.github.io/humanizer-ru/): ничего не устанавливать, текст не покидает браузер.
- В терминале:

```text
pip install humanizer-ru
humanizer-markers --scan primer.txt
  primer.txt:1 [contentReference] Согласно отчёту :contentReference[oaicite:3]{index=3}, рост заявок за неделю 12%: https://
  primer.txt:1 [utm_chatgpt] Согласно отчёту :contentReference[oaicite:3]{index=3}, рост заявок за неделю 12%: https://
  primer.txt:2 [zero_width] Данные подтверждены ассистентом​, подробности в чате.
```

### MCP одной конфигурацией

```json
{
  "mcpServers": {
    "humanizer-ru": { "command": "humanizer-mcp" }
  }
}
```

## Что это НЕ делает

- Переписанный текст: теоретический потолок детекции при парафразе [bib:sadasivan2023]; парафраз обнуляет детекторы [bib:dipper2023].
- Нативно-гладкий машинный текст без артефактов: документная граница там же [bib:sadasivan2023]; популяционная детекция возможна только на больших выборках [bib:chakraborty2023], вердикт по документу не заявляется.
- Короткий текст: сигналов меньше, чем слов, водяной знак и статистика требуют длины [bib:anthropic2026wm], [bib:synthid2024].
- Водяные знаки без ключа: distortion-free знак не виден стороннему наблюдателю по построению [bib:kuditipudi2023]; криптографическая неотличимость без ключа [bib:cgz2023]; детектор SynthID-Text требует ключ разработчика [bib:synthid2024]; Anthropic подтверждает: без ключа знак не проверяется, детектор-API в закрытом preview [bib:anthropic2026wm].

- Не помогает там, где ИИ запрещён: сдача работ там, где ИИ запрещён (экзамены, учебные задания, конкурсы «только человек»); полный список — prohibited_uses в contract.v1.json.

- Ключи [bib:…] раскрыты в [research/BIBLIOGRAPHY.md](research/BIBLIOGRAPHY.md).
- polish не запускать на Markdown и разметке: снимает ##, **, ёлочки, тире; для разметки — режим --preserve-markup.

## Почему можно доверять

- [Методология и бенчмарк: числа с доверительными интервалами](research/F8-UMBRELLA-2026.md).
- [Публичный бенчмарк: таблица с CI, командами воспроизведения и колонкой «где мы хуже»](demo/benchmark/index.html).
- [Модель угроз и границы детектора](docs/THREAT-MODEL.md).
- [Парити-гейт Python и JS правил](.github/workflows/regex-check.yml).
- [Самоаудит: числа, статусы и эррата](eval/facts/self-audit.v1.json).
- Статус последнего успешного прогона main: [docs/status.json](docs/status.json) (обновляется только зелёным прогоном).

## Установка скилла в браузерные клиенты

- Демо работает без установки: https://vladimir-human.github.io/humanizer-ru/ — текст не покидает браузер.
- Claude.ai и Claude Code: добавьте скилл из каталога `dsh/skills/humanizer-ru` по инструкции установки в [docs/USAGE.md](docs/USAGE.md#установка-за-30-секунд).
- Агентные клиенты с поддержкой agentskills.io (opencode, DeepSeek Harness): распакуйте текстовый бандл из архива релиза.
- Браузерное расширение отклонено: новый поверхностный контур (permissions, store review) не окупается; очередь идей — [research/BACKLOG.md](research/BACKLOG.md).

## Одноимённые проекты

На GitHub есть скиллы с тем же именем и другим содержанием. Снимок 2026-09-05
(проверка: `gh repo view <владелец>/humanizer-ru --json stargazerCount`):

- [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) — 284 звезды: позиционирование «убирает признаки нейросети», публичного реестра чисел нет.
- [smixs/humanizer-ru](https://github.com/smixs/humanizer-ru) — 148 звёзд: детерминированный линтер; единственный тёзка, включённый в [LEADERBOARD.md](LEADERBOARD.md) как кандидат (парный прогон 2026-09-03).
- Этот проект — проверяемая гигиена вставки из чат-интерфейсов: каждое число из детерминированных снимков и [реестра фактов](eval/facts/facts.v1.json), границы — в [THREAT-MODEL](docs/THREAT-MODEL.md), ложные срабатывания — в [бенчмарке](demo/benchmark/index.html).

Пришли по имени — выбирайте по способу проверки, а не по звёздам.

## Цифры проекта

- 58 паттернов машинного письма и 40 regex-маркеров (классы A и B).
- Записи доказательств: 38 из 40 маркеров (реестр research/fixtures/marker-sources.json).
- Гейты: 139 гейтов полного check_all (128 в --quick); фикстуры в tests/fixtures/, документация сверяется check_docs.py, персона описана в PERSONA.md.

Почему так называется: имя унаследовано от первой функции, снимавшей
слой копипасты после чат-бота и возвращавшей тексту человеческий вид.
Вторая функция продукта: диагностика, подсветить машинные следы и
объяснить причину каждого флага, без вердиктов об авторстве. Обе
функции работают офлайн, текст не покидает вашу машину.

Классовая разбивка FP, exploratory, вне предрега F16: класс A: 0 случаев на 12314 текстов-неносителей; класс B: 8 случаев на 12314, то есть 0.00065, Wilson 95% CI от 0.0003 до 0.0013; контрольный набор 40 текстов: флагов 0; тяжёлый домен S4 legal и official, n=381, дефицит объёма зафиксирован в предреге: 18 случаев на 381, то есть 0.0472, Wilson 95% CI от 0.0301 до 0.0734; знаменатели: 12354 полный корпус F16, 12314 validation-страта.

## Подробнее

- [Что ему давать и как переписывать](docs/USAGE.md#что-ему-давать)
- [Установка вручную и использование](docs/USAGE.md#использование)
- [Архитектура и паттерны](docs/USAGE.md#архитектура)
- [Безопасность и отличия версий](docs/USAGE.md#безопасность)
- [Источники](docs/USAGE.md#источники)

## Regex-маркеры: классы A и B

Класс A — жёсткие артефакты копипасты: служебные ссылки и метки цитирования
чат-интерфейсов. Класс B — контекстные индикаторы: невидимые символы,
скрытая раскладка, placeholder-поля; одного совпадения B недостаточно.
Класс маркеров — `copypaste_artifacts`; ретайр маркера возможен только по
провалу на своём классе, статусы и даты — в `markers.v1.json`.


## История изменений

История изменений — в [CHANGELOG.md](CHANGELOG.md) и на [GitHub Releases](https://github.com/Vladimir-Human/humanizer-ru/releases).


## Лицензия

MIT


## Статус проекта
[![Версия](https://img.shields.io/github/v/release/Vladimir-Human/humanizer-ru?label=%D0%B2%D0%B5%D1%80%D1%81%D0%B8%D1%8F&color=blue)](https://github.com/Vladimir-Human/humanizer-ru/releases)
[![Skills.sh](https://img.shields.io/badge/skills.sh-%D0%BA%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3-blueviolet)](https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru)
[![Догфудинг](https://img.shields.io/badge/%D1%81%D0%B2%D0%BE%D0%B8_%D0%B4%D0%B5%D1%82%D0%B5%D0%BA%D1%82%D0%BE%D1%80%D1%8B-%D0%BE%D1%82%D1%87%D1%91%D1%82-brightgreen)](https://github.com/Vladimir-Human/humanizer-ru/blob/main/eval/facts/self-audit.v1.json)

Догфудинг — проект проверяет собственные тексты собственными правилами: порог маркеров стиля в файлах поставки сверяется гейтом `scripts/check_own_style.py` (текущий максимум выводится в его запуске).
