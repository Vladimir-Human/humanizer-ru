#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_parity.py — демо и CLI дают одинаковый результат.

Раньше демо (постатейный подсчёт в браузере) и CLI (подавление вложенных
дублей в check_markers._line_matches) давали разный счёт на одном тексте
(например, 3 против 2 на вставке с :contentReference[oaicite:N]{index=N}).
Сопоставление вынесено в общий слой demo/engine.js (точный порт семантики
CLI); гейт сверяет стороны на фиксированной фикстуре И на общем наборе
векторов (решения по Unicode-семантике зафиксированы 2026-09-06):

  1. CLI: scripts/check_markers.py --scan --json <фикстура> — фактический
     счёт и состав маркеров равны эталону tests/fixtures/demo-parity/
     expected.json (эталон перезаписывается только осознанно, вместе с
     изменением маркеров).
  2. demo/sample.js (кнопка «Вставить образец») байт-в-байт равен
     фикстуре — демо показывает тот же текст, который проверяет гейт.
  3. JS-сторона: node исполняет demo/engine.js + demo/markers.js +
     demo/sample.js и даёт тот же счёт и состав (если node недоступен,
     сторона печатается как SKIP — в CI node есть).
  4. Векторы паритета: tests/fixtures/demo-parity/vectors.json — общий
     набор входов (теневая нормализация, маскирование URL, Unicode-цифры,
     разделители строк Python splitlines, code spans, fenced-блоки,
     координаты в кодовых точках при астральных символах). Каждая сторона
     обязана совпасть и с эталоном вектора, и друг с другом по полям
     (marker, class, line, start, end, shadow).

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
VECTORS = os.path.join(FX_DIR, "vectors.json")
SAMPLE_JS = os.path.join(ROOT, "demo", "sample.js")
ENGINE_JS = os.path.join(ROOT, "demo", "engine.js")
MARKERS_JS = os.path.join(ROOT, "demo", "markers.js")

_SAMPLE_RE = re.compile(
    r"const HUMANIZER_SAMPLE = (\"(?:[^\"\\]|\\.)*\");", re.S)

# Поля сверки паритета: идентификатор, класс, номер строки, явно
# определённые координаты (кодовые точки внутри строки) и признак тени.
_MARK_FIELDS = ("marker", "class", "line", "start", "end", "shadow")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _marker_tuple(m):
    return tuple(m.get(k) for k in ("line", "marker", "class", "shadow",
                                    "start", "end"))


def _cli_scan_text(root, text):
    """Прогон CLI --scan --json по тексту (временный файл): список маркеров."""
    with tempfile.TemporaryDirectory(prefix="demo-parity-cli-") as td:
        path = os.path.join(td, "v.txt")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        proc = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "check_markers.py"),
             "--scan", "--json", path],
            capture_output=True, encoding="utf-8", errors="replace", cwd=root)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise ValueError("CLI --json не вернул JSON: %s" % proc.stderr[:200])
        entry = data["files"][0]
        return proc.returncode, entry["count"], entry["markers"]


def _cli_result(root):
    """Фактический прогон CLI на фикстуре: (rc, count, markers)."""
    text = _read(os.path.join(root, "tests", "fixtures", "demo-parity",
                              "sample.txt"))
    return _cli_scan_text(root, text)


def _sample_js_text(root):
    text = _read(os.path.join(root, "demo", "sample.js"))
    m = _SAMPLE_RE.search(text)
    if not m:
        raise ValueError("demo/sample.js: константа HUMANIZER_SAMPLE не найдена")
    return json.loads(m.group(1))


_NODE_RUNNER = """
const fs = require('fs');
const path = require('path');
const root = process.argv[2];
const vecFile = process.argv[3];
global.window = global;  // markers.js пишет window.HUMANIZER_MARKERS
eval(fs.readFileSync(path.join(root, 'demo', 'markers.js'), 'utf8'));
const engine = require(path.join(root, 'demo', 'engine.js'));
const rules = window.HUMANIZER_MARKERS.rules.map(function (r) {
  return {id: r.id, class: r.class, source: r.source, flags: r.flags,
          url_marker: !!r.url_marker};
});
function scan(text) {
  const ms = engine.scanText(text, rules);
  return ms.map(function (m) {
    return {line: m.line, marker: m.rule, class: m.cls,
            shadow: !!m.shadow, start: m.cpStart, end: m.cpEnd};
  });
}
const out = {};
if (fs.existsSync(path.join(root, 'demo', 'sample.js'))) {
  const sample = require(path.join(root, 'demo', 'sample.js'));
  out.__sample__ = scan(sample);
}
const vectors = JSON.parse(fs.readFileSync(vecFile, 'utf8'));
for (const v of vectors) { out[v.name] = scan(v.text); }
// Подсветка: абсолютные офсеты прямых находок режут исходный текст на
// заявленный фрагмент (для строк без NFC-изменений длины и без тени).
const hl = [];
for (const v of vectors) {
  const ms = engine.scanText(v.text, rules);
  for (const m of ms) {
    if (!m.shadow && v.text.normalize('NFC') === v.text &&
        v.text.substring(m.start, m.end) !== m.text) {
      hl.push(v.name + ':' + m.rule);
    }
  }
}
out.__highlight_mismatch__ = hl;
console.log(JSON.stringify(out));
"""


def _node_results(root, vectors):
    """Счёт JS-стороны через node; None, если node недоступен."""
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(_NODE_RUNNER)
        runner_path = fh.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(vectors, fh, ensure_ascii=False)
        vec_path = fh.name
    try:
        proc = subprocess.run([node, runner_path, root, vec_path],
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120)
        if proc.returncode != 0:
            raise ValueError("node-прогон демо упал: %s" % proc.stderr[:300])
        return json.loads(proc.stdout)
    finally:
        os.unlink(runner_path)
        os.unlink(vec_path)


def _load_vectors(root):
    with open(os.path.join(root, "tests", "fixtures", "demo-parity",
                           "vectors.json"), encoding="utf-8") as fh:
        return json.load(fh)


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
        errors.append("CLI markers != эталон (состав/порядок/координаты)")
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
        vectors = _load_vectors(root)
    except (OSError, ValueError) as exc:
        return errors + ["векторы паритета не читаются: %s" % exc]
    cli_vectors = {}
    for v in vectors:
        try:
            _rc, _cnt, vmarkers = _cli_scan_text(root, v["text"])
        except (OSError, ValueError) as exc:
            errors.append("вектор %s: CLI-сторона не исполнена: %s"
                          % (v["name"], exc))
            continue
        cli_vectors[v["name"]] = vmarkers
        expect = [tuple(e.get(k) for k in _MARK_FIELDS) for e in v["expect"]]
        got = [_marker_tuple(m) for m in vmarkers]
        # Порядок полей эталона (marker, class, line, start, end, shadow)
        # приводится к порядку CLI-кортежа (line, marker, class, shadow,
        # start, end) — сверяются наборы полей, не их раскладка.
        expect_reordered = [(e[2], e[0], e[1], e[5], e[3], e[4])
                            for e in expect]
        if got != expect_reordered:
            errors.append("вектор %s: CLI %s != эталон %s"
                          % (v["name"], got, expect_reordered))
    try:
        node = _node_results(root, vectors)
    except (OSError, ValueError) as exc:
        errors.append("JS-сторона: %s" % exc)
        node = "error"
    if node is None:
        print("SKIP: node недоступен — JS-сторона не сверена (в CI node есть)")
    elif node != "error":
        if node.get("__sample__") is not None:
            if len(node["__sample__"]) != count:
                errors.append("демо count=%s != CLI count=%d — подавление "
                              "вложенных дублей разъехалось"
                              % (len(node["__sample__"]), count))
            cli_pairs = sorted(_marker_tuple(m) for m in markers)
            js_pairs = sorted(_marker_tuple(m) for m in node["__sample__"])
            if cli_pairs != js_pairs:
                errors.append("демо состав %s != CLI состав %s"
                              % (js_pairs, cli_pairs))
        hl = node.get("__highlight_mismatch__") or []
        if hl:
            errors.append("подсветка демо: абсолютные офсеты не режут текст "
                          "на заявленный фрагмент: %s" % hl)
        for v in vectors:
            got = node.get(v["name"])
            if got is None:
                errors.append("вектор %s: JS-сторона не вернула результат"
                              % v["name"])
                continue
            js_tuples = [_marker_tuple(m) for m in got]
            cli_tuples = [_marker_tuple(m)
                          for m in cli_vectors.get(v["name"], [])]
            expect = [tuple(e.get(k) for k in _MARK_FIELDS) for e in v["expect"]]
            expect_reordered = [(e[2], e[0], e[1], e[5], e[3], e[4])
                                for e in expect]
            if js_tuples != expect_reordered:
                errors.append("вектор %s: JS %s != эталон %s"
                              % (v["name"], js_tuples, expect_reordered))
            if js_tuples != cli_tuples:
                errors.append("вектор %s: JS %s != CLI %s"
                              % (v["name"], js_tuples, cli_tuples))
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    case("боевой прогон: паритет цел", check(ROOT) == [])
    # Негативы: расхождение эталона, дрейф sample.js, порча вектора и
    # порча engine.js видны гейту (имитация во временном дереве).
    rels = ("scripts/check_markers.py", "demo/sample.js",
            "demo/engine.js", "demo/markers.js",
            "tests/fixtures/demo-parity/sample.txt",
            "tests/fixtures/demo-parity/expected.json",
            "tests/fixtures/demo-parity/vectors.json")
    with tempfile.TemporaryDirectory(prefix="demo-parity-") as td:
        for rel in rels:
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
            json.dump(exp, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        with open(os.path.join(td, "demo", "sample.js"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write('const HUMANIZER_SAMPLE = "дрейф текста";\n')
        case("дрейф sample.js ловится", check(td) != [])
        with open(os.path.join(td, "demo", "sample.js"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write('const HUMANIZER_SAMPLE = %s;\n'
                     % json.dumps(_sample_js_text(ROOT), ensure_ascii=False))
        # Порча эталона вектора (номер строки) ловится.
        vec_path = os.path.join(td, "tests", "fixtures", "demo-parity",
                                "vectors.json")
        vec = json.loads(_read(vec_path))
        target = next(v for v in vec if v["name"] == "line-separator-u2028")
        target["expect"][0]["line"] = 1
        with open(vec_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(vec, fh, ensure_ascii=False, indent=2)
        case("порча эталона вектора ловится", check(td) != [])
        target["expect"][0]["line"] = 2
        with open(vec_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(vec, fh, ensure_ascii=False, indent=2)
        # Порча engine.js (теневые находки выдаются за прямые) ловится
        # вектором zwsp-glue.
        eng_path = os.path.join(td, "demo", "engine.js")
        eng = _read(eng_path)
        broken = eng.replace("shadow: true, text:", "shadow: false, text:")
        if broken == eng:
            broken = eng.replace("shadow: true", "shadow: false")
        with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(broken)
        case("порча engine.js (тень->прямая) ловится", check(td) != [])
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
    print("ДЕМО-ПАРИТЕТ: демо и CLI дают одинаковый счёт на фикстуре "
          "и на векторах паритета")
    return 0


if __name__ == "__main__":
    sys.exit(main())
