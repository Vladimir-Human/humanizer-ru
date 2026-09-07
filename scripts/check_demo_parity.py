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
     demo/sample.js и даёт тот же счёт и состав; недоступность node —
     FAIL обязательной проверки (непроверенная JS-сторона не может
     давать зелёный статус и parity:"ok" в Pages-workflow).
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
// Подсветка: абсолютные офсеты режут исходный текст на заявленный
// фрагмент — для прямых находок дословно (включая строки с
// NFC-изменениями длины), для теневых — после удаления невидимых
// символов (координаты тени отображаются в исходную строку).
const hl = [];
const INV = new RegExp("[\\u00ad\\u061c\\u034f\\u1680\\u180b-\\u180e" +
  "\\u200b-\\u200f\\u202a-\\u202e\\u205f\\u2060-\\u2069\\u206a-\\u206f" +
  "\\u3000\\ufe00-\\ufe0f\\ufeff\\ufff9-\\ufffb\\u{e0000}-\\u{e007f}]", "gu");
for (const v of vectors) {
  const ms = engine.scanText(v.text, rules);
  for (const m of ms) {
    const slice = v.text.substring(m.start, m.end);
    INV.lastIndex = 0;
    const norm = m.shadow ? slice.replace(INV, "") : slice;
    if (norm !== m.text) {
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


def _nfc_table_check(root) -> int:
    """Сверка встроенной таблицы не-стартеров NFC с unicodedata (0 — целая)."""
    gen = os.path.join(root, "demo", "generate_nfc_table.py")
    proc = subprocess.run([sys.executable, gen, "--check"],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          cwd=root, timeout=300)
    return proc.returncode


_EQUIV_NODE = r"""
const engine = require(process.argv[2]);
function naivePrefix(raw) {
  var m = [0];
  for (var r = 1; r <= raw.length; r++) {
    m.push(raw.slice(0, r).normalize('NFC').length);
  }
  return m;
}
const INV = new RegExp("[\u00ad\u061c\u034f\u1680\u180b-\u180e" +
  "\u200b-\u200f\u202a-\u202e\u205f\u2060-\u2069\u206a-\u206f" +
  "\u3000\ufe00-\ufe0f\ufeff\ufff9-\ufffb\u{e0000}-\u{e007f}]", "gu");
const corpus = [
  '', 'a', 'abc', 'и\u0306', 'и\u0306'.repeat(50), 'а\u0301а\u0302а\u0300',
  '\u1100\u1161', '\u1100\u1161\u11A8', '가각간', '\u2126', '\u2126\u0301',
  'A\u0301\u0302\u0303', '\u0301\u0302\u0300', '\u{E0061}', 'x\u{E0061}y',
  '\u{1F600}', '\u{1F600}\u0301', '\u{1F3F3}\uFE0F\u200D\u{1F308}',
  '\u{1D167}\u{1D168}x', '\uFDF0', 'е\u0308\u0301', '\r\n\u0301x',
  '\u2126\u0301\u03c9', '\u034Fx', 'a\u200Bb\u200Cc',
  '\u{E0061}\u{E0062}и\u0306\u{1F600}\u0301'
];
const bad = [];
corpus.forEach(function (t, i) {
  const got = engine._prefixNfcMap(t);
  const want = naivePrefix(t);
  if (got.length !== want.length ||
      got.some(function (v, j) { return v !== want[j]; })) {
    bad.push({ case: 'prefix#' + i, problem: 'карта != наивное определение' });
  }
  const kept = engine._shadowKeptMap(t);
  const shadow = t.replace(INV, '');
  if (kept.length !== shadow.length) {
    bad.push({ case: 'kept#' + i, problem: 'длина != длина теневой строки' });
  } else {
    let recon = '';
    for (const idx of kept) { recon += t.charAt(idx); }
    if (recon !== shadow) {
      bad.push({ case: 'kept#' + i, problem: 'реконструкция != теневая строка' });
    }
  }
  for (let j = 1; j < kept.length; j++) {
    if (kept[j] <= kept[j - 1]) {
      bad.push({ case: 'kept#' + i, problem: 'карта не монотонна' });
      break;
    }
  }
});
console.log(JSON.stringify(bad));
"""


def _maps_equivalence(root):
    """Сверка карт координат engine.js с наивным определением (node).

    Возвращает список строк-расхождений; None — node недоступен (основная
    JS-сверка уже считает недоступность отказом, не SKIP).
    """
    node = shutil.which("node")
    if not node:
        return None
    engine_path = os.path.join(root, "demo", "engine.js")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(_EQUIV_NODE)
        runner_path = fh.name
    try:
        proc = subprocess.run([node, runner_path, engine_path],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=120)
        if proc.returncode != 0:
            return ["node-сверка карт упала (rc=%d): %s"
                    % (proc.returncode, (proc.stderr or "")[-200:])]
        bad = json.loads(proc.stdout.strip() or "[]")
        return ["%s: %s" % (b.get("case"), b.get("problem")) for b in bad]
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return ["node-сверка карт не исполнена: %s" % exc]
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
        # Непроверенная JS-сторона — не зелёный статус: обязательный путь
        # (CI, поставка) обязан отказать, иначе Pages-workflow запишет
        # parity:"ok" поверх непроверенного состояния.
        errors.append("JS-сторона не сверена: node недоступен — обязательная "
                      "проверка паритета не выполнена (это FAIL, не SKIP)")
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
    # Таблица не-стартеров NFC (автогенерация demo/generate_nfc_table.py):
    # безопасность сегментного построения карты префиксов держится на ней.
    if _nfc_table_check(root) != 0:
        errors.append("таблица не-стартеров NFC в demo/engine.js расходится "
                      "с unicodedata — перегенерировать: python3 "
                      "demo/generate_nfc_table.py")
    # Эквивалентность карт координат наивному определению (астральные
    # символы, комбинируемые последовательности, хангыль, синглетоны):
    # start/end (UTF-16 исходного текста) и cpStart/cpEnd (кодовые точки
    # NFC/теневой строки) обязаны оставаться точным отображением.
    eq = _maps_equivalence(root)
    if eq is None:
        pass  # node недоступен — ошибка уже добавлена основной JS-сверкой
    elif eq:
        errors.append("карты координат engine.js != наивное определение: %s"
                      % "; ".join(eq[:6]))
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
            "demo/generate_nfc_table.py", "demo/nfc_nonstarters.json",
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
        with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(eng)
        # Порча класса переноса Python \w в markers.js (возврат \p{M},
        # которого в Python \w нет) ловится комбинируемым вектором.
        bs = chr(92)
        mk_path = os.path.join(td, "demo", "markers.js")
        mk = _read(mk_path)
        broken_mk = mk.replace(bs + bs + "p{L}" + bs + bs + "p{N}_]",
                               bs + bs + "p{L}" + bs + bs + "p{N}"
                               + bs + bs + "p{M}_]")
        if broken_mk == mk:
            print("FAIL: не найдена точка подмены класса переноса")
            failed += 1
        else:
            with open(mk_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(broken_mk)
            case("порча класса переноса w в markers.js ловится",
                 check(td) != [])
        # Возврат charAt-обхода в теневую карту (прежний дефект: астральный
        # невидимый символ оставался в карте обеими суррогатными единицами,
        # координаты теневых находок съезжали на 2 юнита) ловится вектором
        # astral-tag-inside-marker через сверку исходного среза.
        eng2 = _read(eng_path)
        broken_shadow = eng2.replace(
            "SHADOW_TEST_RX.test(raw.substr(r, len))",
            "SHADOW_TEST_RX.test(raw.charAt(r))")
        if broken_shadow == eng2:
            print("FAIL: не найдена точка подмены теневой карты")
            failed += 1
        else:
            with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(broken_shadow)
            case("возврат charAt-обхода теневой карты ловится",
                 check(td) != [])
            with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(eng2)
        # Порча таблицы не-стартеров NFC ловится сверкой блока engine.js
        # с JSON-каноном (детерминированно, не зависит от unicodedata среды).
        eng3 = _read(eng_path)
        broken_table = eng3.replace("NFC_NONSTARTERS = [[768,846],",
                                    "NFC_NONSTARTERS = [[768,847],", 1)
        if broken_table == eng3:
            print("FAIL: не найдена точка подмены таблицы NFC")
            failed += 1
        else:
            with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(broken_table)
            case("порча таблицы не-стартеров NFC ловится", check(td) != [])
            with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(eng3)
        # Отказ от стартер-границы (флеш на каждом символе) ломает карту
        # префиксов на комбинируемых последовательностях — ловится сверкой
        # эквивалентности с наивным определением.
        eng4 = _read(eng_path)
        broken_seg = eng4.replace(
            "if (r > segStart && _isNfcStarter(raw.codePointAt(r))) {",
            "if (r > segStart) {", 1)
        if broken_seg == eng4:
            print("FAIL: не найдена точка подмены стартер-границы")
            failed += 1
        else:
            with open(eng_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(broken_seg)
            case("отказ от стартер-границы NFC ловится", check(td) != [])
    # Самопроверка генератора таблицы NFC (структура канона, негативы
    # порчи блока и подмены канона) — часть обязательного пути.
    gen = os.path.join(ROOT, "demo", "generate_nfc_table.py")
    proc = subprocess.run([sys.executable, gen, "--selftest"],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          cwd=ROOT, timeout=300)
    case("selftest генератора таблицы NFC зелёный", proc.returncode == 0)
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
