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


def _struct_line(line):
    """Похожа ли строка на структуру YAML (ключ mapping, элемент списка,
    комментарий), а не на текст literal-блока."""
    s = line.lstrip()
    if s.startswith("#"):
        return True
    if re.match(r"-(\s|$)", s):
        return True
    return bool(re.match(r"(?:[A-Za-z0-9_.\-]+|\"[^\"]*\"|'[^']*'):(\s|$)", s))


_KEY_RX = re.compile(r"(\s*)(?:-\s+)?([A-Za-z0-9_.\-]+):(\s|$)")


def _check_literal_indent(path, base=None):
    """Ограниченный stdlib-анализ (НЕ полная проверка YAML) блоков `run: |`.

    Содержимое literal-блока — строки глубже колонки ключа `run`; блок
    заканчивает первая строка на уровне ключа или выше, если она похожа
    на структуру YAML (ключ, элемент списка, комментарий). Строка на
    уровне ключа или выше БЕЗ структуры — классическая поломка (heredoc
    в колонке 1 обрывает блок) — ошибка. Строки внутри блока с отступом
    меньше первой строки содержимого (но глубже ключа) — ошибка отступа.
    Корректная последовательность «run: | -> вложенные строки -> соседний
    ключ -> следующий шаг» не отвергается: прежняя реализация читала весь
    остаток файла как содержимое блока и давала ложный отказ.
    """
    base = base or os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    errs = []
    i = 0
    while i < len(lines):
        m = re.match(r"(\s*)(?:-\s+)?run:\s*\|", lines[i])
        if m:
            key_col = lines[i].index("run:")
            block_indent = None
            i += 1
            while i < len(lines):
                stripped = lines[i].rstrip("\n")
                if not stripped.strip():
                    i += 1
                    continue
                indent = len(stripped) - len(stripped.lstrip())
                if indent <= key_col:
                    if _struct_line(stripped):
                        break  # конец блока: следующая структура YAML
                    errs.append("%s:%d: строка после блока run: | в колонке "
                                "%d — не содержимое блока (нужно > %d) и не "
                                "структура YAML (literal-блок оборван)"
                                % (base, i + 1, indent, key_col))
                    i += 1
                    continue
                if block_indent is None:
                    block_indent = indent
                elif indent < block_indent:
                    errs.append("%s:%d: строка блока run в колонке %d "
                                "(нужно >= %d)"
                                % (base, i + 1, indent, block_indent))
                i += 1
            continue
        i += 1
    return errs


def _check_plain_scalars(path, base=None):
    """Ограниченный stdlib-анализ (НЕ полная проверка YAML): «: » (или
    конечное «:») внутри незакавыченного значения mapping-строки —
    YAML-ошибка «mapping values are not allowed here». Так ломается,
    например, `- name: Заголовок: с двоеточием` без кавычек. Строки
    внутри literal-блоков (run: |) пропускаются: блок заканчивается
    строкой на уровне ключа или выше — соседний ключ после блока
    проверяется (прежде весь хвост файла считался содержимым блока)."""
    base = base or os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    errs = []
    in_block = False
    block_key_col = 0
    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if in_block:
            if indent > block_key_col:
                continue
            in_block = False
        m = _KEY_RX.match(line)
        if not m:
            continue
        value = line[m.end():].strip()
        key_col = line.index(m.group(2) + ":")
        if value.startswith("|") or value.startswith(">"):
            in_block = True
            block_key_col = key_col
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
    try:
        import yaml
        branch = "PyYAML %s — полный парсинг" % getattr(yaml, "__version__",
                                                        "?")
    except ImportError:
        branch = ("ограниченный stdlib-анализ (literal-блоки run: | и "
                  "незакавыченные «: »-скаляры) — НЕ полная проверка YAML; "
                  "полная — с установленным PyYAML")
    if failures:
        for f in failures:
            print(f)
        print("ИТОГ: ошибок %d — YAML экшена/workflows не парсится (%s)"
              % (len(failures), branch))
        return 1
    print("OK action.yml и workflows (%d файлов): %s" % (len(targets), branch))
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

    # Регрессия ложного отказа: корректная последовательность «run: |,
    # соседний ключ того же шага, следующий шаг» прежде отвергалась —
    # stdlib-ветвь читала весь остаток файла как содержимое блока.
    p = tmp("jobs:\n  j:\n    steps:\n"
            "      - name: A\n"
            "        run: |\n"
            "          echo a\n"
            "        shell: bash\n"
            "      - run: |\n"
            "          echo b\n")
    case("корректная последовательность шагов проходит (fallback)",
         not _check_literal_indent(p) and not _check_plain_scalars(p))
    case("корректная последовательность шагов проходит (parse)",
         not _parse_yaml(p))
    os.unlink(p)

    # heredoc в колонке 1 ловится и ограниченным анализом, не только
    # PyYAML: строка без структуры на уровне ключа — обрыв literal-блока.
    p = tmp("name: x\nruns:\n  using: composite\n  steps:\n"
            "    - run: |\n"
            "        set -e\n"
            "        python3 - x <<'PY'\n"
            "import os\n"
            "PY\n")
    case("heredoc в колонке 1 пойман (fallback)",
         bool(_check_literal_indent(p)))
    os.unlink(p)

    # Соседний ключ после literal-блока проверяется на «: » (прежде
    # утекал: хвост файла считался содержимым блока).
    p = tmp("steps:\n"
            "  - run: |\n"
            "      echo a\n"
            "    name: Плохое: имя\n")
    case("соседний ключ после блока проверен на «: » (fallback)",
         bool(_check_plain_scalars(p)))
    case("соседний ключ после блока с «: » пойман (parse)",
         bool(_parse_yaml(p)))
    os.unlink(p)

    # Обе ветви на файлах репозитория: одинаковый вердикт (чисто).
    targets_all = [ACTION] + _targets()
    case("файлы репозитория чисты ограниченным stdlib-анализом",
         all(not (_check_literal_indent(t) + _check_plain_scalars(t))
             for t in targets_all))
    try:
        import yaml  # noqa: F401
        case("файлы репозитория чисты PyYAML (согласно со stdlib-анализом)",
             all(not _parse_yaml(t) for t in targets_all))
    except ImportError:
        print("ПРИМЕЧАНИЕ: PyYAML не установлен — сравнение с dev-парсером "
              "не выполнено; ограниченный stdlib-анализ не является полной "
              "проверкой YAML")

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(run())
