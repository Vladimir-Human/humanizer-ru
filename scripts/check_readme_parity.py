#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверяет паритет и правдивость русской и английской витрины.

Числа покрытия сверяются не только между README, но и с исполняемыми
источниками истины: REGISTERED_CASES и CASES. Разделы должны быть настоящими
заголовками H2/H3, а не случайными словами в тексте.
"""
import io
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RU, EN, SKILL = "README.md", "README.en.md", "SKILL.md"
SHOWCASE = (RU, EN, SKILL)
OK, FAIL = "[OK]", "[FAIL]"

# Кодпоинты не дают self-scan принять тестовые данные за живые маркеры.
CIRCLES = (u"\U0001F534", u"\U0001F7E1", u"\U0001F7E2")
CIRCLE_NAMES = dict(zip(CIRCLES, (u"красный", u"жёлтый", u"зелёный")))

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
RU_ONLY = [
    u"Содержательные паттерны", u"Языковые паттерны",
    u"Структурные и стилевые паттерны", u"Коммуникативные паттерны",
    u"Подлог источников", u"Границы ложного срабатывания",
    u"Отпечатки моделей", u"Отличия от английской версии",
]

PATTERNS_RX = re.compile(u"(\\d+)\\s+(?:паттернов|patterns)", re.I)
MARKERS_RX = re.compile(
    u"(\\d+)\\s+(?:[^\\W\\d_]+\\s+){0,2}(?:regex|регулярных)"
    u"[-\\s]?(?:маркеров|markers|выражений)", re.I | re.U)
COVERAGE_RX = re.compile(u"(\\d+)\\s+(?:из|of)\\s+(\\d+)", re.I)
HEADING_RX = re.compile(u"^#{2,3}\\s+(.+?)\\s*$", re.M)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _numbers(rx, text):
    return sorted({int(value) for value in rx.findall(text)}) or None


def claims(text):
    return {
        "patterns": _numbers(PATTERNS_RX, text),
        "markers": _numbers(MARKERS_RX, text),
        "coverage": sorted({(int(a), int(b))
                            for a, b in COVERAGE_RX.findall(text)}) or None,
    }


def source_truth():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from check_fixture_sources import REGISTERED_CASES
    from check_markers import CASES
    return len(REGISTERED_CASES), len(CASES)


def headings(text):
    return [re.sub(u"\\s+#+$", u"", item).strip()
            for item in HEADING_RX.findall(text)]


def has_heading(items, fragment):
    return any(fragment in item for item in items)


def check_numbers(ru_text, en_text, expected=None):
    errors = []
    ru, en = claims(ru_text), claims(en_text)
    titles = (("patterns", u"количество паттернов"),
              ("markers", u"количество regex-маркеров"),
              ("coverage", u"покрытие реестра доказательств"))
    for key, title in titles:
        if ru[key] is None:
            errors.append(u"%s: не заявлено %s" % (RU, title))
        if en[key] is None:
            errors.append(u"%s: не заявлено %s" % (EN, title))
        if ru[key] and en[key] and set(ru[key]) != set(en[key]):
            errors.append(u"%s расходится: %s %s, %s %s"
                          % (title, RU, ru[key], EN, en[key]))
    if expected:
        wanted = {tuple(expected)}
        for name, data in ((RU, ru), (EN, en)):
            actual = set(data["coverage"] or [])
            if actual != wanted:
                errors.append(u"%s: покрытие %s, по коду должно быть %s"
                              % (name, sorted(actual), sorted(wanted)))
            markers = set(data["markers"] or [])
            if expected[1] not in markers:
                errors.append(u"%s: число regex-маркеров %s, в CASES их %d"
                              % (name, sorted(markers), expected[1]))
    return errors


def check_sections(ru_text, en_text):
    errors = []
    ru_heads, en_heads = headings(ru_text), headings(en_text)
    for ru_name, en_name in SECTIONS:
        if not has_heading(ru_heads, ru_name):
            errors.append(u"%s: нет заголовка H2/H3 «%s»" % (RU, ru_name))
        if not has_heading(en_heads, en_name):
            errors.append(u"%s: нет заголовка H2/H3 «%s»" % (EN, en_name))
    for name in RU_ONLY:
        if not has_heading(ru_heads, name):
            errors.append(u"%s: нет русского раздела H2/H3 «%s»" % (RU, name))
    return errors


def check_circles(name, text):
    errors = []
    for line_no, line in enumerate(text.split("\n"), 1):
        for circle in CIRCLES:
            if circle in line:
                errors.append(u"%s:%d кружок критичности (%s) — нужно слово"
                              % (name, line_no, CIRCLE_NAMES[circle]))
                break
    return errors


def check_all(texts, expected=None):
    errors = check_numbers(texts[RU], texts[EN], expected)
    errors += check_sections(texts[RU], texts[EN])
    for name in SHOWCASE:
        errors += check_circles(name, texts[name])
    return errors


RU_ONLY_SAMPLE = u"\n".join(u"### " + name for name in RU_ONLY)
GOOD_RU = u"""# Скилл
37 паттернов и 38 regex-маркеров.
Запись доказательств есть у 30 из 38 маркеров.
## Что ему давать
## Установка за 30 секунд
## Установка вручную
## Использование
## Что делает
### Архитектура
### Regex-маркеры: классы A и B
## Безопасность
## Источники
## История изменений
## Лицензия
""" + RU_ONLY_SAMPLE + u"\n"
GOOD_EN = u"""# Skill
37 patterns and 38 regex markers.
Currently 30 of 38 markers have a full record.
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
EXPECTED = (30, 38)


def _has(errors, fragment):
    return any(fragment in error for error in errors)


def _case(name, condition, detail=""):
    print(u"%s %s%s" % (OK if condition else FAIL, name,
          (u" — " + detail) if detail and not condition else ""))
    return bool(condition)


def selftest():
    print("check_readme_parity selftest")
    base = {RU: GOOD_RU, EN: GOOD_EN, SKILL: GOOD_SKILL}
    results = []
    errors = check_all(base, EXPECTED)
    results.append(_case(u"Согласованная витрина проходит", not errors,
                         u"; ".join(errors)))
    wordy = dict(base)
    wordy[EN] = GOOD_EN.replace(u"38 regex markers", u"38 testable regex markers")
    results.append(_case(u"Определение перед regex не мешает",
                         not check_all(wordy, EXPECTED)))
    bad = dict(base); bad[EN] = GOOD_EN.replace(u"37 patterns", u"54 patterns")
    results.append(_case(u"Разное число паттернов отклоняется",
                         _has(check_all(bad, EXPECTED), u"количество паттернов")))
    bad = dict(base); bad[EN] = GOOD_EN.replace(u"38 regex markers", u"41 regex markers")
    results.append(_case(u"Разное число маркеров отклоняется",
                         _has(check_all(bad, EXPECTED), u"regex-маркеров")))
    bad = dict(base)
    bad[RU] = GOOD_RU.replace(u"30 из 38", u"38 из 38")
    bad[EN] = GOOD_EN.replace(u"30 of 38", u"38 of 38")
    results.append(_case(u"Синхронное завышение покрытия отклоняется",
                         _has(check_all(bad, EXPECTED), u"по коду должно быть")))
    bad = dict(base); bad[RU] = GOOD_RU.replace(
        u"Запись доказательств есть у 30 из 38 маркеров.\n", u"")
    results.append(_case(u"Умолчание о покрытии отклоняется",
                         _has(check_all(bad, EXPECTED), u"не заявлено покрытие")))
    bad = dict(base); bad[EN] = GOOD_EN.replace(u"## Security", u"Security")
    results.append(_case(u"Обычный текст вместо заголовка отклоняется",
                         _has(check_all(bad, EXPECTED), u"Security")))
    bad = dict(base); bad[EN] = GOOD_EN.replace(u"## Security", u"###### Security")
    results.append(_case(u"H6 вместо H2/H3 отклоняется",
                         _has(check_all(bad, EXPECTED), u"Security")))
    bad = dict(base); bad[RU] = GOOD_RU.replace(
        u"### Содержательные паттерны", u"### Другое")
    results.append(_case(u"Пропавший русский раздел отклоняется",
                         _has(check_all(bad, EXPECTED), u"Содержательные паттерны")))
    bad = dict(base); bad[RU] = GOOD_RU + CIRCLES[0] + u"\n"
    results.append(_case(u"Кружок в README отклоняется",
                         _has(check_all(bad, EXPECTED), u"кружок критичности")))
    bad = dict(base); bad[SKILL] = GOOD_SKILL + CIRCLES[2] + u"\n"
    results.append(_case(u"Кружок в карте скилла отклоняется",
                         _has(check_all(bad, EXPECTED), u"кружок критичности")))
    passed = sum(results)
    print(u"Итог: %d/%d" % (passed, len(results)))
    return 0 if passed == len(results) else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    texts = {name: read(os.path.join(ROOT, name)) for name in SHOWCASE}
    expected = source_truth()
    errors = check_all(texts, expected)
    for error in errors:
        print(u"%s %s" % (FAIL, error))
    if errors:
        print(u"Ошибок: %d." % len(errors))
        return 1
    print(u"%s Витрина согласована; покрытие по коду: %d из %d."
          % (OK, expected[0], expected[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
