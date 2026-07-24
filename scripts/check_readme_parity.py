#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_readme_parity.py — паритет русской и английской витрины.

Закрывает пробел, найденный при перепроверке 3.6.0: русский и английский
README разошлись, и это никто не ловил. Английская версия сообщала честное
покрытие реестра доказательств, русская — нет.

Правила
-------
1. Числа совпадают: количество паттернов и количество regex-маркеров
   заявлено в обоих файлах и одинаково.
2. Покрытие реестра доказательств («N из 38» / «N of 38») заявлено в обоих
   файлах и одинаково. Молчание считается ошибкой: пропуск неудобного числа
   в одной из версий — это и есть маркетинг вместо отчёта.
3. Обязательные разделы есть в обеих версиях (SECTIONS). Разделы, которые
   намеренно живут только в русской версии, перечислены в RU_ONLY.
4. В витринных файлах нет кружков критичности. Скилл, который называет
   эмодзи-списки маркером машинного текста, не ставит их сам. Правило
   касается только кружков: эмодзи внутри примеров «До» — это иллюстрация
   плохого текста, она нужна.

Запуск:
  python3 scripts/check_readme_parity.py
  python3 scripts/check_readme_parity.py --selftest

Только стандартная библиотека.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OK = "[OK]"
FAIL = "[FAIL]"

RU = "README.md"
EN = "README.en.md"
SKILL = "SKILL.md"

# Кружки критичности. Собраны из кодпоинтов, чтобы самопроверка репозитория
# на собственные маркеры не падала на этом файле.
CIRCLES = (u"\U0001F534", u"\U0001F7E1", u"\U0001F7E2")
CIRCLE_NAMES = {u"\U0001F534": "красный", u"\U0001F7E1": "жёлтый", u"\U0001F7E2": "зелёный"}

SHOWCASE = (RU, EN, SKILL)

# Разделы, обязательные в обеих версиях: (фрагмент RU, фрагмент EN).
SECTIONS = [
    (u"Что ему давать", u"What to give it"),
    (u"Установка за 30 секунд", u"Install in 30 seconds"),
    (u"Установка вручную", u"Manual install"),
    (u"Использование", u"Usage"),
    (u"Что делает", u"What it does"),
    (u"Regex-маркеры", u"Regex markers"),
    (u"Архитектура", u"Architecture"),
    (u"Безопасность", u"Security"),
    (u"Источники", u"Sources"),
    (u"История изменений", u"Changelog"),
    (u"Лицензия", u"License"),
]

# Намеренно только в русской версии: подробные таблицы паттернов и разборы.
RU_ONLY = [
    u"Содержательные паттерны",
    u"Языковые паттерны",
    u"Структурные и стилевые паттерны",
    u"Коммуникативные паттерны",
    u"Подлог источников",
    u"Границы ложного срабатывания",
    u"Отпечатки моделей",
    u"Отличия от английской версии",
]

PATTERNS_RX = re.compile(u"(\\d+)\\s+(?:паттернов|patterns)", re.I)
# Между числом и словом regex бывают определения: «38 проверяемых regex-маркеров»,
# «38 testable regex markers». Допускаем до двух таких слов.
MARKERS_RX = re.compile(
    u"(\\d+)\\s+(?:[^\\W\\d_]+\\s+){0,2}(?:regex|регулярных)[-\\s]?(?:маркеров|markers|выражений)",
    re.I | re.U,
)
COVERAGE_RX = re.compile(u"(\\d+)\\s+(?:из|of)\\s+38", re.I)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def claims(text):
    """Заявленные числа. None означает, что заявления нет вовсе."""
    def one(rx):
        found = set()
        for m in rx.findall(text):
            found.add(int(m))
        return sorted(found) or None
    return {
        "patterns": one(PATTERNS_RX),
        "markers": one(MARKERS_RX),
        "coverage": one(COVERAGE_RX),
    }


def check_numbers(ru_text, en_text):
    errors = []
    ru, en = claims(ru_text), claims(en_text)
    titles = [
        ("patterns", u"количество паттернов"),
        ("markers", u"количество regex-маркеров"),
        ("coverage", u"покрытие реестра доказательств"),
    ]
    for key, title in titles:
        if ru[key] is None:
            errors.append(u"%s: не заявлено %s" % (RU, title))
        if en[key] is None:
            errors.append(u"%s: не заявлено %s" % (EN, title))
        if ru[key] and en[key] and set(ru[key]) != set(en[key]):
            errors.append(u"%s расходится: %s %s, %s %s"
                          % (title, RU, ru[key], EN, en[key]))
    return errors


def check_sections(ru_text, en_text):
    errors = []
    for ru_name, en_name in SECTIONS:
        if ru_name not in ru_text:
            errors.append(u"%s: нет обязательного раздела «%s»" % (RU, ru_name))
        if en_name not in en_text:
            errors.append(u"%s: нет обязательного раздела «%s»" % (EN, en_name))
    return errors


def check_circles(name, text):
    errors = []
    line_no = 0
    for line in text.split("\n"):
        line_no += 1
        for circle in CIRCLES:
            if circle in line:
                errors.append(u"%s:%d кружок критичности (%s) — нужно слово"
                              % (name, line_no, CIRCLE_NAMES[circle]))
                break
    return errors


def check_all(texts):
    """texts: словарь имя -> содержимое. Возвращает список ошибок."""
    errors = []
    errors += check_numbers(texts[RU], texts[EN])
    errors += check_sections(texts[RU], texts[EN])
    for name in SHOWCASE:
        if name in texts:
            errors += check_circles(name, texts[name])
    return errors


# ---------------------------------------------------------------- selftest

GOOD_RU = u"""# Скилл
37 паттернов и 38 regex-маркеров.
Запись доказательств есть у 14 из 38 маркеров.
## Что ему давать
## Установка за 30 секунд
## Установка вручную
## Использование
## Что делает
### Архитектура
### Regex-маркеры: классы A и B
| # | Паттерн | Критичность |
| 1 | Усреднение | высокая |
## Безопасность
## Источники
## История изменений
## Лицензия
"""

GOOD_EN = u"""# Skill
37 patterns and 38 regex markers.
Currently 14 of 38 markers have a full record.
## What to give it
## Install in 30 seconds
## Manual install
## Usage
## What it does
## Architecture
## Regex markers: classes A and B
## Security
## Sources
## Changelog
## License
"""

GOOD_SKILL = u"# Карта\nКритичность: высокая, средняя, низкая.\n"


def _case(name, condition, detail=""):
    mark = OK if condition else FAIL
    tail = (u" — " + detail) if detail and not condition else ""
    print(u"%s %s%s" % (mark, name, tail))
    return bool(condition)


def selftest():
    print("check_readme_parity selftest")
    results = []
    base = {RU: GOOD_RU, EN: GOOD_EN, SKILL: GOOD_SKILL}

    baseline = check_all(base)
    results.append(_case(u"Согласованная витрина проходит",
                         baseline == [], u"; ".join(baseline)))

    bad = dict(base)
    bad[EN] = GOOD_EN.replace(u"37 patterns", u"54 patterns")
    results.append(_case(u"Разное число паттернов отклоняется",
                         any(u"количество паттернов" in e for e in check_all(bad))))

    # Определение между числом и словом regex не должно ломать разбор.
    wordy = dict(base)
    wordy[EN] = GOOD_EN.replace(u"38 regex markers", u"38 testable regex markers")
    results.append(_case(u"Определение перед regex не мешает",
                         check_all(wordy) == [], u"; ".join(check_all(wordy))))

    bad = dict(base)
    bad[EN] = GOOD_EN.replace(u"38 regex markers", u"41 testable regex markers")
    results.append(_case(u"Разное число маркеров отклоняется",
                         any(u"количество regex-маркеров" in e for e in check_all(bad))))

    bad = dict(base)
    bad[EN] = GOOD_EN.replace(u"14 of 38", u"38 of 38")
    results.append(_case(u"Разное покрытие реестра отклоняется",
                         any(u"покрытие реестра" in e for e in check_all(bad))))

    bad = dict(base)
    bad[RU] = GOOD_RU.replace(u"Запись доказательств есть у 14 из 38 маркеров.\n", u"")
    results.append(_case(u"Умолчание о покрытии в одной версии отклоняется",
                         any(u"не заявлено покрытие" in e for e in check_all(bad))))

    bad = dict(base)
    bad[EN] = GOOD_EN.replace(u"## Security\n", u"")
    results.append(_case(u"Пропущенный обязательный раздел отклоняется",
                         any(u"Security" in e for e in check_all(bad))))

    bad = dict(base)
    bad[RU] = GOOD_RU.replace(u"| 1 | Усреднение | высокая |",
                              u"| 1 | Усреднение | " + CIRCLES[0] + u" |")
    results.append(_case(u"Кружок критичности в витрине отклоняется",
                         any(u"кружок критичности" in e for e in check_all(bad))))

    bad = dict(base)
    bad[SKILL] = GOOD_SKILL + CIRCLES[2] + u" низкая\n"
    results.append(_case(u"Кружок в карте скилла отклоняется",
                         any(u"кружок критичности" in e for e in check_all(bad))))

    passed = 0
    for r in results:
        if r:
            passed += 1
    print(u"Итог: %d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    texts = {}
    for name in SHOWCASE:
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            print(u"%s нет файла %s" % (FAIL, name))
            return 1
        texts[name] = read(path)
    errors = check_all(texts)
    for err in errors:
        print(u"%s %s" % (FAIL, err))
    if errors:
        print(u"Ошибок: %d." % len(errors))
        return 1
    print(u"%s Витрина согласована: числа, разделы и оформление критичности." % OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
