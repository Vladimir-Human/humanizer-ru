#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт бюджета контекста для формата Agent Skills.

Официальная спецификация описывает трёхуровневую загрузку: метаданные читаются
всегда, тело SKILL.md — при активации, файлы references — только по требованию.
Скрипт следит, чтобы верхний уровень не разбухал и поля frontmatter укладывались
в ограничения формата.

Лимиты спецификации (жёсткие):  name <= 64, description <= 1024, compatibility <= 500.
Рекомендации (жёсткие здесь):  тело SKILL.md <= 500 строк и < 5000 токенов.
Предупреждения:  файл references тяжелее 10000 токенов стоит разбить.

Оценка токенов консервативная: для кириллицы берётся 3.0 символа на токен,
для остального — 4.0. Внешние зависимости не используются.
"""
import io
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_BODY_LINES = 500
MAX_BODY_TOKENS = 5000
WARN_REFERENCE_TOKENS = 10000

NAME_RX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def estimate_tokens(text):
    """Консервативная оценка числа токенов без внешних библиотек."""
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u04ff")
    other = len(text) - cyr
    return int(cyr / 3.0 + other / 4.0)


def split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    parts = text.split("\n---", 2)
    if len(parts) < 2:
        return None, text
    head = parts[0][3:]
    body = parts[1]
    if body.startswith("\n"):
        body = body[1:]
    return head, body


def _field(head, key):
    """Значение скалярного поля frontmatter, включая переносы со сдвигом."""
    if head is None:
        return None
    lines = head.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^%s:\s*(.*)$" % re.escape(key), line)
        if not m:
            continue
        value = m.group(1).strip()
        for cont in lines[i + 1:]:
            if not cont.strip():
                break
            if re.match(r"^\S+:", cont) or not cont.startswith((" ", "\t")):
                break
            value += " " + cont.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value
    return None


def check_skill(text, name_hint=None):
    """Возвращает (errors, warnings, stats)."""
    errors, warnings = [], []
    head, body = split_frontmatter(text)
    if head is None:
        return ["нет YAML-frontmatter"], [], {}

    name = _field(head, "name") or ""
    description = _field(head, "description") or ""
    compatibility = _field(head, "compatibility")

    if not name:
        errors.append("name: поле пустое")
    else:
        if len(name) > MAX_NAME:
            errors.append("name: %d символов при лимите %d" % (len(name), MAX_NAME))
        if not NAME_RX.match(name):
            errors.append(
                "name %r: допустимы только a-z, 0-9 и одиночные дефисы внутри" % name
            )

    if not description:
        errors.append("description: поле пустое")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(
            "description: %d символов при лимите %d" % (len(description), MAX_DESCRIPTION)
        )

    if compatibility is not None and len(compatibility) > MAX_COMPATIBILITY:
        errors.append(
            "compatibility: %d символов при лимите %d"
            % (len(compatibility), MAX_COMPATIBILITY)
        )

    body_lines = len(body.rstrip("\n").split("\n"))
    body_tokens = estimate_tokens(body)
    if body_lines > MAX_BODY_LINES:
        errors.append("тело SKILL.md: %d строк при лимите %d" % (body_lines, MAX_BODY_LINES))
    if body_tokens >= MAX_BODY_TOKENS:
        errors.append(
            "тело SKILL.md: ~%d токенов при лимите %d — вынесите часть в references/"
            % (body_tokens, MAX_BODY_TOKENS)
        )
    elif body_tokens > int(MAX_BODY_TOKENS * 0.9):
        warnings.append(
            "тело SKILL.md: ~%d токенов, больше 90%% лимита %d"
            % (body_tokens, MAX_BODY_TOKENS)
        )

    if name_hint and name and name != name_hint:
        errors.append("name %r не совпадает с именем каталога %r" % (name, name_hint))

    stats = {
        "name": name,
        "description": len(description),
        "compatibility": len(compatibility) if compatibility else 0,
        "body_lines": body_lines,
        "body_tokens": body_tokens,
    }
    return errors, warnings, stats


def check_references(root):
    warnings, rows = [], []
    ref_dir = os.path.join(root, "references")
    if not os.path.isdir(ref_dir):
        return warnings, rows
    for fn in sorted(os.listdir(ref_dir)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(ref_dir, fn)
        text = io.open(path, encoding="utf-8").read()
        tok = estimate_tokens(text)
        rows.append((fn, tok))
        if tok > WARN_REFERENCE_TOKENS:
            warnings.append(
                "references/%s: ~%d токенов, стоит разбить на тематические части" % (fn, tok)
            )
    return warnings, rows


SELFTEST_OK = u"""---
name: good-skill
description: "Делает полезное и применяется тогда-то."
---

Тело скилла.
"""


def selftest():
    cases = []
    e, w, s = check_skill(SELFTEST_OK)
    cases.append(("корректный скилл без ошибок", e == [], e))
    cases.append(("имя разобрано", s.get("name") == "good-skill", s))

    e, _, _ = check_skill(SELFTEST_OK.replace("good-skill", "Good-Skill"))
    cases.append(("заглавные в name отловлены", any("name" in x for x in e), e))

    e, _, _ = check_skill(SELFTEST_OK.replace("good-skill", "good--skill"))
    cases.append(("двойной дефис отловлен", any("name" in x for x in e), e))

    e, _, _ = check_skill(SELFTEST_OK.replace("good-skill", "-good"))
    cases.append(("дефис в начале отловлен", any("name" in x for x in e), e))

    long_desc = SELFTEST_OK.replace(u"Делает полезное и применяется тогда-то.", u"а" * 1025)
    e, _, _ = check_skill(long_desc)
    cases.append(("длинный description отловлен", any("description" in x for x in e), e))

    e, _, _ = check_skill(SELFTEST_OK + u"\n".join([u"строка"] * 600))
    cases.append(("длинное тело отловлено", any("строк" in x for x in e), e))

    e, _, _ = check_skill(SELFTEST_OK + u"я" * 40000)
    cases.append(("перерасход токенов отловлен", any("токенов" in x for x in e), e))

    e, _, _ = check_skill(SELFTEST_OK, name_hint="other-dir")
    cases.append(("несовпадение с каталогом отловлено", any("каталог" in x for x in e), e))

    e, _, _ = check_skill(u"без frontmatter")
    cases.append(("отсутствие frontmatter отловлено", e != [], e))

    cases.append(("оценка токенов монотонна", estimate_tokens(u"а" * 300) > estimate_tokens(u"а" * 100), None))

    ok = 0
    for title, passed, detail in cases:
        print("  %s %s" % ("[OK]  " if passed else "[FAIL]", title))
        if not passed:
            print("         детали: %r" % (detail,))
        ok += 1 if passed else 0
    print("Самопроверка: %d/%d" % (ok, len(cases)))
    return 0 if ok == len(cases) else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("-")]
    path = args[0] if args else "SKILL.md"
    root = os.path.dirname(os.path.abspath(path)) or "."
    name_hint = None
    if "--expect-dir" in argv:
        name_hint = argv[argv.index("--expect-dir") + 1]

    text = io.open(path, encoding="utf-8").read()
    errors, warnings, stats = check_skill(text, name_hint=name_hint)
    ref_warnings, rows = check_references(root)
    warnings += ref_warnings

    if stats:
        print(
            "Уровень 2 (тело SKILL.md): %d строк, ~%d токенов из %d"
            % (stats["body_lines"], stats["body_tokens"], MAX_BODY_TOKENS)
        )
        print(
            "Уровень 1 (метаданные): description %d/%d, compatibility %d/%d"
            % (
                stats["description"], MAX_DESCRIPTION,
                stats["compatibility"], MAX_COMPATIBILITY,
            )
        )
    if rows:
        total = sum(t for _, t in rows)
        print("Уровень 3 (references, по требованию): %d файлов, ~%d токенов" % (len(rows), total))

    for w in warnings:
        print("[WARN] %s" % w)
    for e in errors:
        print("[FAIL] %s" % e)
    if errors:
        print("Итог: ошибок %d" % len(errors))
        return 1
    print("Итог: бюджет соблюдён")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
