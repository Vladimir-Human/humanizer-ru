#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_parity.py — демо и CLI дают одинаковый счёт на фикстуре.

Раньше демо (постатейный подсчёт в браузере) и CLI (подавление вложенных
дублей в check_markers._line_matches) давали разный счёт на одном тексте
(например, 3 против 2 на вставке с :contentReference[oaicite:N]{index=N}).
Сопоставление вынесено в общий слой demo/engine.js (точный порт семантики
CLI); гейт сверяет три стороны на фиксированной фикстуре:

  1. CLI: scripts/check_markers.py --scan --json <фикстура> — фактический
     счёт и состав маркеров равны эталону tests/fixtures/demo-parity/
     expected.json (эталон перезаписывается только осознанно, вместе с
     изменением маркеров).
  2. demo/sample.js (кнопка «Вставить образец») байт-в-байт равен
     фикстуре — демо показывает тот же текст, который проверяет гейт.
  3. JS-сторона: node исполняет demo/engine.js + demo/markers.js +
     demo/sample.js и даёт тот же счёт и состав (если node недоступен,
     сторона печатается как SKIP — в CI node есть).

Запуск:
    python3 scripts/check_demo_parity.py
    python3 scripts/check_demo_parity.py --selftest

Коды: 0 — паритет цел; 1 — расхождение; 2 — ошибка входа.
Только стандартная библиотека (node — опциональная внешняя проверка).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FX_DIR = os.path.join(ROOT, "tests", "fixtures", "demo-parity")
SAMPLE_TXT = os.path.join(FX_DIR, "sample.txt")
EXPECTED = os.path.join(FX_DIR, "expected.json")
SAMPLE_JS = os.path.join(ROOT, "demo", "sample.js")
ENGINE_JS = os.path.join(ROOT, "demo", "engine.js")
MARKERS_JS = os.path.join(ROOT, "demo", "markers.js")

_SAMPLE_RE = re.compile(
    r"const HUMANIZER_SAMPLE = (\"(?:[^\"\\]|\\.)*\");", re.S)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _cli_result(root):
    """Фактический прогон CLI на фикстуре: (rc, count, markers)."""
    sample = os.path.join(root, "tests", "fixtures", "demo-parity", "sample.txt")
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "scripts", "check_markers.py"),
         "--scan", "--json", sample],
        capture_output=True, encoding="utf-8", errors="replace", cwd=root)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ValueError("CLI --json не вернул JSON: %s" % proc.stderr[:200])
    entry = data["files"][0]
    markers = [{"line": m["line"], "marker": m["marker"], "class": m["class"],
                "shadow": m["shadow"]} for m in entry["markers"]]
    return proc.returncode, entry["count"], markers


def _sample_js_text(root):
    text = _read(os.path.join(root, "demo", "sample.js"))
    m = _SAMPLE_RE.search(text)
    if not m:
        raise ValueError("demo/sample.js: константа HUMANIZER_SAMPLE не найдена")
    return json.loads(m.group(1))


def _node_result(root):
    """Счёт JS-стороны через node; None, если node недоступен."""
    node = shutil.which("node")
    if not node:
        return None
    runner = """
const fs = require('fs');
const path = require('path');
const root = process.argv[2];
global.window = global;  // markers.js пишет window.HUMANIZER_MARKERS
eval(fs.readFileSync(path.join(root, 'demo', 'markers.js'), 'utf8'));
const engine = require(path.join(root, 'demo', 'engine.js'));
const sample = require(path.join(root, 'demo', 'sample.js'));
const rules = window.HUMANIZER_MARKERS.rules.map(function (r) {
  return {id: r.id, class: r.class, source: r.source, flags: r.flags};
});
const ms = engine.scanText(sample, rules);
const byLine = {};
ms.forEach(function (m) {
  const key = m.line + ':' + m.rule;
  byLine[key] = (byLine[key] || 0) + 1;
});
console.log(JSON.stringify({count: ms.length,
  markers: ms.map(function (m) {
    return {line: m.line, marker: m.rule, class: m.cls};
  })}));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(runner)
        runner_path = fh.name
    try:
        proc = subprocess.run([node, runner_path, root],
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=60)
        if proc.returncode != 0:
            raise ValueError("node-прогон демо упал: %s" % proc.stderr[:300])
        return json.loads(proc.stdout)
    finally:
        os.unlink(runner_path)


def check(root) -> list:
    errors = []
    try:
        rc, count, markers = _cli_result(root)
    except (OSError, ValueError) as exc:
        return ["CLI-сторона не исполнена: %s" % exc]
    try:
        expected = json.loads(_read(os.path.join(
            root, "tests", "fixtures", "demo-parity", "expected.json")))
    except (OSError, ValueError) as exc:
        return ["эталон не читается: %s" % exc]
    if rc != expected.get("cli_rc"):
        errors.append("CLI rc=%d != эталон %s" % (rc, expected.get("cli_rc")))
    if count != expected.get("count"):
        errors.append("CLI count=%d != эталон %s — состав маркеров изменился "
                      "без перезаписи эталона" % (count, expected.get("count")))
    if markers != expected.get("markers"):
        errors.append("CLI markers != эталон (состав/порядок)")
    try:
        js_sample = _sample_js_text(root)
        txt_sample = _read(os.path.join(
            root, "tests", "fixtures", "demo-parity", "sample.txt"))
    except (OSError, ValueError) as exc:
        errors.append("sample.js/sample.txt не читаются: %s" % exc)
        js_sample = txt_sample = None
    if js_sample is not None and js_sample != txt_sample:
        errors.append("demo/sample.js != tests/fixtures/demo-parity/sample.txt "
                      "— кнопка «Вставить образец» показывает не тот текст")
    try:
        node = _node_result(root)
    except (OSError, ValueError) as exc:
        errors.append("JS-сторона: %s" % exc)
        node = "error"
    if node is None:
        print("SKIP: node недоступен — JS-сторона не сверена (в CI node есть)")
    elif node != "error":
        if node.get("count") != count:
            errors.append("демо count=%s != CLI count=%d — подавление "
                          "вложенных дублей разъехалось"
                          % (node.get("count"), count))
        cli_pairs = sorted((m["line"], m["marker"]) for m in markers)
        js_pairs = sorted((m["line"], m["marker"]) for m in node.get("markers", []))
        if cli_pairs != js_pairs:
            errors.append("демо состав %s != CLI состав %s"
                          % (js_pairs, cli_pairs))
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    case("боевой прогон: паритет цел", check(ROOT) == [])
    # Негатив: расхождение эталона видно (имитация через временное дерево).
    with tempfile.TemporaryDirectory(prefix="demo-parity-") as td:
        for rel in ("scripts/check_markers.py", "demo/sample.js",
                    "demo/engine.js", "demo/markers.js",
                    "tests/fixtures/demo-parity/sample.txt",
                    "tests/fixtures/demo-parity/expected.json"):
            src = os.path.join(ROOT, rel.replace("/", os.sep))
            dst = os.path.join(td, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        # Подменяем эталонный счёт — гейт обязан увидеть расхождение.
        exp_path = os.path.join(td, "tests", "fixtures", "demo-parity",
                                "expected.json")
        exp = json.loads(_read(exp_path))
        exp["count"] = exp["count"] + 1
        with open(exp_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(exp, fh, ensure_ascii=False)
        case("подменённый эталон ловится", check(td) != [])
        # Возвращаем эталон и дрейфуем sample.js — кнопка «Вставить образец»
        # обязана показывать тот же текст, что проверяет гейт.
        exp["count"] = exp["count"] - 1
        with open(exp_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(exp, fh, ensure_ascii=False)
        with open(os.path.join(td, "demo", "sample.js"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write('const HUMANIZER_SAMPLE = "дрейф текста";\n')
        case("дрейф sample.js ловится", check(td) != [])
    print("САМОПРОВЕРКА check_demo_parity: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return selftest()
    errors = check(ROOT)
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("ДЕМО-ПАРИТЕТ: расхождений %d" % len(errors))
        return 1
    print("ДЕМО-ПАРИТЕТ: демо и CLI дают одинаковый счёт на фикстуре")
    return 0


if __name__ == "__main__":
    sys.exit(main())
