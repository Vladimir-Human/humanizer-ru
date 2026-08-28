#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_action_yaml.py — гейт: action/action.yml парсится как YAML.

Опубликованный 3.16.0 содержал экшен, не парсившийся: Python в heredoc
в колонке 1 обрывал literal-блок. Ни один гейт этого не ловил (аудит
веером моделей 2026-08-28). Здесь — лёгкий парсинг через PyYAML (если
установлен) или собственная проверка отступов literal-блока.

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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def _parse_yaml(path):
    """Парсинг action.yml. Предпочитает PyYAML; fallback — проверка
    отступов literal-блока run: | (не парсит полностью, но ловит
    классическую поломку: содержимое блока в колонке 1 обрывает блок)."""
    try:
        import yaml  # noqa: E402
    except ImportError:
        return _check_literal_indent(path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return [] if isinstance(data, dict) else [
            "action.yml: корень не mapping (тип %s)" % type(data).__name__]
    except Exception as exc:
        return ["action.yml: YAML-ошибка: %s" % str(exc)[:200]]


def _check_literal_indent(path):
    """Fallback без PyYAML: блок `run: |` — все непустые строки после
    него обязаны иметь отступ не меньше отступа первой строки блока."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    errs = []
    i = 0
    while i < len(lines):
        if re.match(r"\s*run:\s*\|", lines[i]):
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
                    errs.append("action.yml:%d: строка блока run в колонке %d"
                                " (нужно >= %d)" % (i + 1, indent, block_indent))
                i += 1
            continue
        i += 1
    return errs


def run():
    if not os.path.isfile(ACTION):
        print("нет action/action.yml", file=sys.stderr)
        return 2
    errs = _parse_yaml(ACTION)
    rel = os.path.relpath(ACTION, ROOT)
    if errs:
        for e in errs:
            print("[FAIL] %s: %s" % (rel, e))
        print("ИТОГ: ошибок %d — action.yml не парсится как YAML" % len(errs))
        return 1
    print("OK action.yml: YAML валиден")
    return 0


def _selftest():
    import tempfile
    fails = 0
    # негативный: heredoc в колонке 1 (поломка 3.16.0)
    broken = ("name: x\nruns:\n  using: composite\n  steps:\n"
              "    - run: |\n"
              "        set -e\n"
              "        python3 - x <<'PY'\n"
              "import os\n"
              "PY\n")
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w",
                                     delete=False, encoding="utf-8") as fh:
        fh.write(broken)
        tmp_broken = fh.name
    errs = _parse_yaml(tmp_broken)
    os.unlink(tmp_broken)
    if not errs:
        print("ПРОВАЛ selftest: сломанный YAML не пойман")
        fails += 1
    # позитивный: чистый
    clean = ("name: x\nruns:\n  using: composite\n  steps:\n"
             "    - run: |\n        echo hi\n")
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w",
                                     delete=False, encoding="utf-8") as fh:
        fh.write(clean)
        tmp_clean = fh.name
    errs2 = _parse_yaml(tmp_clean)
    os.unlink(tmp_clean)
    if errs2:
        print("ПРОВАЛ selftest: чистый YAML не прошёл: %s" % errs2)
        fails += 1
    if fails:
        print("САМОПРОВЕРКА: провалов %d" % fails)
        return 1
    print("САМОПРОВЕРКА: 2/2 PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(run())
