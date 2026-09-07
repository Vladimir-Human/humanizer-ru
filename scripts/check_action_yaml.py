#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_action_yaml.py — гейт: action/action.yml и workflows парсятся как YAML.

Опубликованный 3.16.0 содержал экшен, не парсившийся: Python в heredoc
в колонке 1 обрывал literal-блок. Ни один гейт этого не ловил (аудит
веером моделей 2026-08-28). Второй урок того же класса: имя шага с
двоеточием без кавычек («name: Контракт выпуска: подпись…») — валидный
текст, но невалидный YAML («mapping values are not allowed here»);
GitHub отклоняет весь workflow-файл, и каждый push получает нулевой
startup-failure, а workflow_dispatch — 422. Локальные запуски шага при
этом не ломаются, поэтому нужен именно парсер.

Проверяются action/action.yml и все .github/workflows/*.yml|*.yaml:
лёгкий парсинг через PyYAML (если установлен) или собственные проверки
отступов literal-блока и «: » в незакавыченных значениях.

CLI:
    python3 scripts/check_action_yaml.py            # проверка репозитория
    python3 scripts/check_action_yaml.py --selftest # PASS/FAIL

Коды: 0 — YAML валиден; 1 — ошибка парсинга или провал самопроверки;
2 — action/action.yml отсутствует. Только стандартная библиотека.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ACTION = os.path.join(ROOT, "action", "action.yml")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def _parse_yaml(path):
    """Парсинг одного YAML-файла. Предпочитает PyYAML; fallback —
    проверки отступов literal-блока run: | и «: » в незакавыченных
    значениях (не парсят полностью, но ловят классические поломки)."""
    base = os.path.basename(path)
    try:
        import yaml  # noqa: E402
    except ImportError:
        return (_check_literal_indent(path, base)
                + _check_plain_scalars(path, base))
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return [] if isinstance(data, dict) else [
            "%s: корень не mapping (тип %s)" % (base, type(data).__name__)]
    except Exception as exc:
        return ["%s: YAML-ошибка: %s" % (base, str(exc)[:200])]


def _check_literal_indent(path, base=None):
    """Fallback без PyYAML: блок `run: |` — все непустые строки после
    него обязаны иметь отступ не меньше отступа первой строки блока."""
    base = base or os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    errs = []
    i = 0
    while i < len(lines):
        if re.match(r"\s*(?:-\s+)?run:\s*\|", lines[i]):
            block_indent = None
            i += 1
            while i < len(lines):
                stripped = lines[i].rstrip("\n")
                if not stripped.strip():
                    i += 1
                    continue
                indent = len(stripped) - len(stripped.lstrip())
                if block_indent is None:
                    block_indent = indent
                elif indent < block_indent and stripped.strip():
                    errs.append("%s:%d: строка блока run в колонке %d"
                                " (нужно >= %d)"
                                % (base, i + 1, indent, block_indent))
                i += 1
            continue
        i += 1
    return errs


def _check_plain_scalars(path, base=None):
    """Fallback без PyYAML: «: » (или конечное «:») внутри незакавыченного
    значения mapping-строки — YAML-ошибка «mapping values are not allowed
    here». Так ломается, например, `- name: Заголовок: с двоеточием` без
    кавычек. Строки внутри literal-блоков (run: |) пропускаются."""
    base = base or os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    errs = []
    in_block = False
    block_indent = 0
    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if in_block:
            if indent >= block_indent:
                continue
            in_block = False
        m = re.match(r"\s*(?:-\s+)?[A-Za-z0-9_.\-]+:(\s|$)", line)
        if not m:
            continue
        value = line[m.end():].strip()
        if value.startswith("|") or value.startswith(">"):
            in_block = True
            block_indent = indent + 1
            continue
        if not value or value.startswith("#"):
            continue
        if value[0] in "'\"[{&*":
            continue
        cut = value.find(" #")
        if cut >= 0:
            value = value[:cut]
        if ": " in value or value.endswith(":"):
            errs.append("%s:%d: «: » в незакавыченном значении — YAML не "
                        "парсится, нужны кавычки: %s"
                        % (base, lineno, line.strip()[:70]))
    return errs


def _targets():
    """action.yml + все workflow-файлы репозитория."""
    targets = []
    if os.path.isdir(WORKFLOWS):
        for name in sorted(os.listdir(WORKFLOWS)):
            if name.endswith((".yml", ".yaml")):
                targets.append(os.path.join(WORKFLOWS, name))
    return targets


def run():
    if not os.path.isfile(ACTION):
        print("нет action/action.yml", file=sys.stderr)
        return 2
    targets = [ACTION] + _targets()
    failures = []
    for path in targets:
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for e in _parse_yaml(path):
            failures.append("[FAIL] %s: %s" % (rel, e))
    if failures:
        for f in failures:
            print(f)
        print("ИТОГ: ошибок %d — YAML экшена/workflows не парсится"
              % len(failures))
        return 1
    print("OK action.yml и workflows (%d файлов): YAML валиден" % len(targets))
    return 0


def _selftest():
    import tempfile
    passed = 0
    failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    def tmp(text):
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w",
                                         delete=False, encoding="utf-8") as fh:
            fh.write(text)
        return fh.name

    # негативный: heredoc в колонке 1 (поломка 3.16.0)
    p = tmp("name: x\nruns:\n  using: composite\n  steps:\n"
            "    - run: |\n"
            "        set -e\n"
            "        python3 - x <<'PY'\n"
            "import os\n"
            "PY\n")
    case("heredoc в колонке 1 пойман", bool(_parse_yaml(p)))
    os.unlink(p)

    # позитивный: чистый
    p = tmp("name: x\nruns:\n  using: composite\n  steps:\n"
            "    - run: |\n        echo hi\n")
    case("чистый YAML проходит", not _parse_yaml(p))
    os.unlink(p)

    # негативный: двоеточие в незакавыченном имени шага (поломка
    # release-check: GitHub отклоняет файл, startup-failure на каждый push)
    p = tmp("jobs:\n  j:\n    steps:\n"
            "      - name: Контракт выпуска: подпись тега\n"
            "        run: echo hi\n")
    case("«: » в имени шага пойман (parse)", bool(_parse_yaml(p)))
    case("«: » в имени шага пойман (fallback)",
         bool(_check_plain_scalars(p)))
    os.unlink(p)

    # позитивный: то же имя в кавычках
    p = tmp('jobs:\n  j:\n    steps:\n'
            '      - name: "Контракт выпуска: подпись тега"\n'
            '        run: echo hi\n')
    case("имя в кавычках проходит (parse)", not _parse_yaml(p))
    case("имя в кавычках проходит (fallback)",
         not _check_plain_scalars(p))
    os.unlink(p)

    # позитивный: fallback не ложится на block-скаляры и комментарии
    p = tmp("steps:\n"
            "  - name: Обычное имя\n"
            "    run: |\n"
            "      echo 'текст: с двоеточием'\n"
            "  - uses: actions/checkout@abc123 # v7: комментарий\n"
            "    with:\n"
            "      fetch-depth: 0   # примечание: не значение\n")
    case("block-скаляр и комментарии не flagged (fallback)",
         not _check_plain_scalars(p))
    case("block-скаляр и комментарии проходят (parse)", not _parse_yaml(p))
    os.unlink(p)

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(run())
