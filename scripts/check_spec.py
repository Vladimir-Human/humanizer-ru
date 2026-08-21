#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_spec.py — проверка SKILL.md на соответствие Agent Skills Specification.

Источник требований: https://agentskills.io/specification (снимок от 2026-07-13).
Без внешних зависимостей — только стандартная библиотека Python 3.8+.

Использование:
    python3 scripts/check_spec.py                 # проверяет ./SKILL.md
    python3 scripts/check_spec.py путь/SKILL.md
    python3 scripts/check_spec.py --strict        # WARN по metadata считать ошибками
    python3 scripts/check_spec.py --expect-dir humanizer-ru   # явное имя каталога (для CI)
    python3 scripts/check_spec.py --selftest      # положительные и отрицательные проверки

Коды выхода: 0 — соответствует; 1 — есть нарушения; 2 — ошибка запуска или чтения.
"""
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def split_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None, "файл должен начинаться со строки '---' (YAML-шапка)"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:]), None
    return None, None, "YAML-шапка не закрыта второй строкой '---'"


def _split_top_commas(s):
    parts, cur, q = [], "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == ",":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts]


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in _split_top_commas(inner)] if inner else []
    return v


BLOCK_SCALAR_RE = re.compile(r"^([|>])([+-]?)(\d*)$")


def _fold_block_scalar(header, lines, start, base_indent):
    """Собирает блочный скаляр YAML (|, >, |-, >-, >2 и т. п.).

    Возвращает готовое значение и номер первой строки за блоком. Форма «|»
    сохраняет переводы строк, «>» складывает абзац в одну строку. Пустая
    строка внутри «>» остаётся разделителем абзацев — так же ведёт себя YAML.
    Без этого «description: >-» разбиралось как скаляр «>-» длиной 2 символа,
    и гейт DESC_LEN не мог сработать ни на каком тексте.
    """
    m = BLOCK_SCALAR_RE.match(header)
    style, chomp = m.group(1), m.group(2)
    i, n = start, len(lines)
    body = []
    while i < n:
        raw = lines[i]
        if not raw.strip():
            body.append("")
            i += 1
            continue
        cur = len(raw) - len(raw.lstrip(" "))
        if cur <= base_indent:
            break
        body.append(raw.strip())
        i += 1
    while body and body[-1] == "":
        body.pop()
    if style == "|":
        value = "\n".join(body)
    else:
        chunks, cur = [], []
        for line in body:
            if line:
                cur.append(line)
            else:
                chunks.append(" ".join(cur))
                cur = []
        chunks.append(" ".join(cur))
        value = "\n".join(chunks)
    if chomp == "+":
        value += "\n"
    return value, i


def parse_yaml_block(lines):
    """Мини-парсер подмножества YAML: скаляры, один уровень вложенности, списки."""
    data, errors = {}, []
    i, n = 0, len(lines)

    def indent(s):
        return len(s) - len(s.lstrip(" "))

    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if indent(raw) != 0:
            errors.append("строка %d: неожиданный отступ: %r" % (i + 2, raw.strip()))
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):(.*)$", raw)
        if not m:
            errors.append("строка %d: не удалось разобрать: %r" % (i + 2, raw.strip()))
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest and BLOCK_SCALAR_RE.match(rest):
            data[key], i = _fold_block_scalar(rest, lines, i + 1, 0)
            continue
        if rest:
            data[key] = _scalar(rest)
            i += 1
            continue
        block = {}
        i += 1
        while i < n and (not lines[i].strip() or indent(lines[i]) > 0):
            sub = lines[i]
            if not sub.strip():
                i += 1
                continue
            sm = re.match(r"^\s+([A-Za-z0-9_-]+):(.*)$", sub)
            lm = re.match(r"^\s+-\s*(.*)$", sub)
            if sm:
                skey, srest = sm.group(1), sm.group(2).strip()
                if srest and BLOCK_SCALAR_RE.match(srest):
                    block[skey], i = _fold_block_scalar(srest, lines, i + 1, indent(sub))
                elif srest:
                    block[skey] = _scalar(srest)
                    i += 1
                else:
                    items = []
                    i += 1
                    while i < n and lines[i].strip():
                        lm2 = re.match(r"^\s+-\s*(.*)$", lines[i])
                        if not lm2:
                            break
                        items.append(_scalar(lm2.group(1)))
                        i += 1
                    block[skey] = items
            elif lm:
                errors.append("строка %d: элемент списка вне ключа" % (i + 2))
                i += 1
            else:
                errors.append("строка %d: не удалось разобрать: %r" % (i + 2, sub.strip()))
                i += 1
        data[key] = block
    return data, errors


KNOWN_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def run_checks(text, skill_dir_name, strict=False):
    issues = []  # (level, code, message)
    fm, body, err = split_frontmatter(text)
    if err:
        issues.append(("FAIL", "FRONTMATTER", err))
        return issues
    data, perrors = parse_yaml_block(fm)
    for e in perrors:
        issues.append(("WARN", "YAML", e))

    for k in data:
        if k not in KNOWN_FIELDS:
            issues.append(("WARN", "UNKNOWN_FIELD", "поле '%s' не описано в спецификации" % k))

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append(("FAIL", "NAME_REQUIRED", "обязательное поле 'name' отсутствует или пустое"))
    else:
        if len(name) > 64:
            issues.append(("FAIL", "NAME_LEN", "name длиннее 64 символов: %d" % len(name)))
        if not NAME_RE.match(name):
            issues.append(("FAIL", "NAME_CHARS",
                           "name '%s': допустимы только a-z, 0-9 и дефис; без дефиса в начале/конце и без '--'" % name))
        if skill_dir_name is not None and name != skill_dir_name:
            issues.append(("FAIL", "NAME_DIR",
                           "name '%s' не совпадает с именем каталога скилла '%s'" % (name, skill_dir_name)))

    desc = data.get("description")
    if not isinstance(desc, str) or not desc.strip():
        issues.append(("FAIL", "DESC_REQUIRED", "обязательное поле 'description' отсутствует или пустое"))
    elif len(desc) > 1024:
        issues.append(("FAIL", "DESC_LEN", "description длиннее 1024 символов: %d" % len(desc)))

    comp = data.get("compatibility")
    if comp is not None:
        if not isinstance(comp, str) or not comp.strip():
            issues.append(("FAIL", "COMPAT_EMPTY", "compatibility указан, но пуст или не строка"))
        elif len(comp) > 500:
            issues.append(("FAIL", "COMPAT_LEN", "compatibility длиннее 500 символов: %d" % len(comp)))

    lic = data.get("license")
    if lic is not None and not isinstance(lic, str):
        issues.append(("WARN", "LICENSE_TYPE", "license должен быть короткой строкой"))

    tools = data.get("allowed-tools")
    if tools is not None and not isinstance(tools, str):
        issues.append(("WARN", "TOOLS_TYPE", "allowed-tools должен быть строкой, разделённой пробелами"))

    meta = data.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict):
            issues.append(("FAIL", "META_TYPE", "metadata должен быть словарём ключ-значение"))
        else:
            level = "FAIL" if strict else "WARN"
            for mk, mv in meta.items():
                if not isinstance(mv, str):
                    issues.append((level, "META_VALUE",
                                   "metadata.%s: спецификация рекомендует строковые значения (найдено: %s)"
                                   % (mk, type(mv).__name__)))

    if body is not None and not body.strip():
        issues.append(("WARN", "EMPTY_BODY", "тело SKILL.md после шапки пустое"))
    return issues


class SpecInputError(Exception):
    """Сбой чтения входного файла: отказ инструмента, код возврата 2."""


def run_file(path, strict=False, expect_dir=None):
    # Сбой чтения — отказ инструмента (код 2), как обещает docstring, а не
    # traceback с кодом 1, неотличимым от найденного нарушения.
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise SpecInputError("не удалось прочитать %s: %s" % (path, exc))
    dir_name = expect_dir or os.path.basename(os.path.dirname(os.path.abspath(path)))
    return run_checks(text, dir_name, strict=strict)


def _report(issues):
    fails = [x for x in issues if x[0] == "FAIL"]
    for level, code, msg in issues:
        print("[%s] %s: %s" % (level, code, msg))
    if fails:
        print("РЕЗУЛЬТАТ: НЕ СООТВЕТСТВУЕТ (%d нарушений, %d предупреждений)"
              % (len(fails), len(issues) - len(fails)))
        return 1
    print("РЕЗУЛЬТАТ: СООТВЕТСТВУЕТ (%d предупреждений)" % len(issues))
    return 0


def _selftest():
    GOOD_MIN = "---\nname: demo-skill\ndescription: Проверяет текст. Использовать при проверке.\n---\n\nТело.\n"
    GOOD_FULL = ("---\nname: demo-skill\ndescription: \"Описание навыка.\"\nlicense: MIT\n"
                 "compatibility: Claude Code\nmetadata:\n  author: someone\n  version: \"1.0\"\n"
                 "  tags: [\"a\", \"b\"]\n---\n\nТело.\n")
    cases = [
        # (имя, содержимое, каталог, strict, ожидаем_нарушение, ожидаемый_код_или_None)
        ("минимальный корректный", GOOD_MIN, "demo-skill", False, False, None),
        ("полный с metadata-списком: WARN, не FAIL", GOOD_FULL, "demo-skill", False, False, None),
        ("полный с metadata-списком в --strict: FAIL", GOOD_FULL, "demo-skill", True, True, "META_VALUE"),
        ("нет name", "---\ndescription: x\n---\nт", "demo-skill", False, True, "NAME_REQUIRED"),
        ("заглавные в name", "---\nname: Demo-Skill\ndescription: x\n---\nт", "Demo-Skill", False, True, "NAME_CHARS"),
        ("двойной дефис", "---\nname: demo--skill\ndescription: x\n---\nт", "demo--skill", False, True, "NAME_CHARS"),
        ("дефис в начале", "---\nname: -demo\ndescription: x\n---\nт", "-demo", False, True, "NAME_CHARS"),
        ("name != каталог", "---\nname: demo-skill\ndescription: x\n---\nт", "other-dir", False, True, "NAME_DIR"),
        ("нет description", "---\nname: demo-skill\n---\nт", "demo-skill", False, True, "DESC_REQUIRED"),
        ("description > 1024", "---\nname: demo-skill\ndescription: " + "х" * 1025 + "\n---\nт", "demo-skill", False, True, "DESC_LEN"),
        ("compatibility > 500", "---\nname: demo-skill\ndescription: x\ncompatibility: " + "c" * 501 + "\n---\nт", "demo-skill", False, True, "COMPAT_LEN"),
        ("name длиннее 64", "---\nname: " + "a" * 65 + "\ndescription: x\n---\nт", "a" * 65, False, True, "NAME_LEN"),
        ("нет шапки", "# Просто markdown\n", "demo-skill", False, True, "FRONTMATTER"),
        ("незакрытая шапка", "---\nname: demo-skill\n", "demo-skill", False, True, "FRONTMATTER"),
        # Блочные скаляры: до поддержки «>-» значение было строкой «>-» длиной
        # 2 символа, поэтому DESC_LEN не мог сработать, а DESC_REQUIRED молчал.
        ("description как >- парсится",
         "---\nname: demo-skill\ndescription: >-\n  Проверяет русский текст.\n"
         "  Использовать при проверке.\n---\nт", "demo-skill", False, False, None),
        ("description как >- длиннее 1024 -> DESC_LEN",
         "---\nname: demo-skill\ndescription: >-\n" + "  х" * 600 + "\n---\nт",
         "demo-skill", False, True, "DESC_LEN"),
        ("description как | длиннее 1024 -> DESC_LEN",
         "---\nname: demo-skill\ndescription: |\n" + "  х" * 600 + "\n---\nт",
         "demo-skill", False, True, "DESC_LEN"),
        ("пустой блочный description -> DESC_REQUIRED",
         "---\nname: demo-skill\ndescription: >-\n---\nт", "demo-skill", False, True, "DESC_REQUIRED"),
    ]
    failed = 0
    for label, content, dirname, strict, expect_fail, expect_code in cases:
        issues = run_checks(content, dirname, strict=strict)
        fails = [x for x in issues if x[0] == "FAIL"]
        ok = (bool(fails) == expect_fail) and (expect_code is None or any(c == expect_code for _, c, _ in fails))
        print("%s: %s" % ("PASS" if ok else "FAIL", label))
        if not ok:
            failed += 1
            for x in issues:
                print("    %s %s %s" % x)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(cases) - failed, len(cases)))
    return 1 if failed else 0


def main(argv):
    args = [a for a in argv[1:]]
    if "--selftest" in args:
        return _selftest()
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    expect_dir = None
    if "--expect-dir" in args:
        k = args.index("--expect-dir")
        try:
            expect_dir = args[k + 1]
        except IndexError:
            print("после --expect-dir нужно имя каталога")
            return 2
        del args[k:k + 2]
    path = args[0] if args else "SKILL.md"
    if not os.path.isfile(path):
        print("файл не найден: %s" % path)
        return 2
    try:
        issues = run_file(path, strict=strict, expect_dir=expect_dir)
    except SpecInputError as exc:
        print(exc)
        return 2
    return _report(issues)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
