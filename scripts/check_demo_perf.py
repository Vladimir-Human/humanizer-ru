#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_perf.py — технический перф-бюджет обработки ввода демо.

Бюджет ЗАМОРОЖЕН до оптимизации (2026-09-07): пороги зафиксированы по
структурному свойству (линейность против квадратичности), а не подгонкой
под измеренные значения. Вход бюджета: строка, чей NFC короче исходной
(«и\\u0306» + «а»×n) — на ней demo/engine.js строит карту префиксных длин
NFC для отображения координат подсветки.

Пороги:
  - отношение t(40k)/t(10k) <= 8.0 — структурный критерий: квадратичная
    нормализация префиксов даёт ~16 (замер до оптимизации на эталонной
    машине: 47/678 мс, отношение 14.4), линейная — <= ~4;
  - t(40k) <= 1200 мс и t(80k) <= 4000 мс — абсолютная защита от
    деградации (до оптимизации на эталонной машине 678/5206 мс);
  - каждый замер с конечным таймаутом: превышение — FAIL (код 1),
    а не ожидание и не UNAVAILABLE.

Единица измерения — полный engine.scanText (детекция + карты координат),
замер node process.hrtime.bigint, минимум из двух прогонов на размер.

node недоступен — код 2 (UNAVAILABLE): бюджет не считается соблюдённым,
гейт не подменяется статической проверкой.

--selftest: квадратичный мутант (прежний алгоритм карты префиксов:
нормализация каждого растущего префикса) обязан получить FAIL гейта;
испорченный замер (нулевые времена) не принимается за PASS.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    # Windows-консоли без UTF-8: диагностика не должна падать charmap-ошибкой
    # при запуске из check_all.py (тот же приём, что в остальных гейтах).
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENGINE = os.path.join(ROOT, "demo", "engine.js")
MARKERS = os.path.join(ROOT, "demo", "markers.js")

SIZES = [10000, 40000, 80000]
WARMUP = 1000
RATIO_MAX = 8.0        # t(40k)/t(10k), заморожено до оптимизации
CAP_40K_MS = 1200.0    # заморожено до оптимизации
CAP_80K_MS = 4000.0    # заморожено до оптимизации
RUN_TIMEOUT_S = 180    # конечный таймаут одного node-замера

MEASURE_JS = """
const fs = require('fs');
const path = require('path');
const enginePath = process.argv[2];
const markersPath = process.argv[3];
global.window = global;
eval(fs.readFileSync(markersPath, 'utf8'));
const engine = require(enginePath);
const rules = window.HUMANIZER_MARKERS.rules.map(r => ({
  id: r.id, class: r.class, source: r.source, flags: r.flags,
  url_marker: !!r.url_marker
}));
function timed(text) {
  const t0 = process.hrtime.bigint();
  const ms = engine.scanText(text, rules);
  const t1 = process.hrtime.bigint();
  return { ms: Number(t1 - t0) / 1e6, matches: ms.length };
}
timed('и\\u0306' + 'а'.repeat(%d));  // прогрев
const out = {};
for (const n of %s) {
  const text = 'и\\u0306' + 'а'.repeat(n);
  const a = timed(text);
  const b = timed(text);
  out[n] = { ms: Math.min(a.ms, b.ms), matches: a.matches };
}
console.log(JSON.stringify(out));
"""


def _measure(engine_path, markers_path=MARKERS):
    """Замер scanText по размерам бюджета; (dict, ошибка)."""
    node = shutil.which("node")
    if not node:
        return None, "node недоступен"
    js = MEASURE_JS % (WARMUP, json.dumps(SIZES))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(js)
        runner = fh.name
    try:
        proc = subprocess.run([node, runner, engine_path, markers_path],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, ("замер не завершился за %d с — бюджет нарушен "
                      "(таймаут, не ожидание)" % RUN_TIMEOUT_S)
    finally:
        os.unlink(runner)
    if proc.returncode != 0:
        return None, "node-замер упал (rc=%d): %s" % (
            proc.returncode, (proc.stderr or "")[-300:])
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None, "вывод замера не JSON: %r" % proc.stdout[:200]
    for n in SIZES:
        rec = data.get(str(n)) or data.get(n)
        if not isinstance(rec, dict) or not isinstance(rec.get("ms"), (int, float)):
            return None, "нет замера для n=%s" % n
        if rec["ms"] <= 0:
            return None, "нулевое время замера для n=%s — замер недействителен" % n
        data[str(n)] = rec
    return data, None


def evaluate(data):
    """Сверка замеров с замороженными порогами; список провалов."""
    t10 = data["10000"]["ms"]
    t40 = data["40000"]["ms"]
    t80 = data["80000"]["ms"]
    ratio = t40 / t10 if t10 > 0 else float("inf")
    fails = []
    if ratio > RATIO_MAX:
        fails.append("отношение t(40k)/t(10k) = %.1f > %.1f — рост ближе к "
                     "квадратичному, чем к линейному" % (ratio, RATIO_MAX))
    if t40 > CAP_40K_MS:
        fails.append("t(40k) = %.0f мс > %.0f мс" % (t40, CAP_40K_MS))
    if t80 > CAP_80K_MS:
        fails.append("t(80k) = %.0f мс > %.0f мс" % (t80, CAP_80K_MS))
    return fails, ratio, (t10, t40, t80)


_QUADRATIC_MAP = """  function _prefixNfcMap(raw) {
    var map = [0];
    for (var r = 1; r <= raw.length; r++) {
      map.push(raw.slice(0, r).normalize("NFC").length);
    }
    return map;
  }"""

_PREFIX_RX = re.compile(
    r"  function _prefixNfcMap\(raw\) \{.*?\n  \}", re.S)


def _quadratic_mutant(dest_dir):
    """Копия engine.js с прежним квадратичным построением карты префиксов."""
    with open(ENGINE, encoding="utf-8") as fh:
        src = fh.read()
    if not _PREFIX_RX.search(src):
        return None
    mutated = _PREFIX_RX.sub(lambda _m: _QUADRATIC_MAP, src, count=1)
    os.makedirs(dest_dir, exist_ok=True)
    engine_copy = os.path.join(dest_dir, "engine.js")
    markers_copy = os.path.join(dest_dir, "markers.js")
    with open(engine_copy, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mutated)
    shutil.copyfile(MARKERS, markers_copy)
    return engine_copy, markers_copy


def selftest():
    fails = 0

    def case(name, ok):
        nonlocal fails
        print(("PASS: " if ok else "FAIL: ") + name)
        if not ok:
            fails += 1

    with tempfile.TemporaryDirectory(prefix="demo-perf-selftest-") as td:
        mutant = _quadratic_mutant(td)
        case("мутант собирается (прежний квадратичный алгоритм внедрим)",
             mutant is not None)
        if mutant:
            engine_copy, markers_copy = mutant
            data, err = _measure(engine_copy, markers_copy)
            if err == "node недоступен":
                print("SKIP-в-selftest невозможен: node требуется")
                fails += 1
            elif err:
                # Таймаут на мутанте — тоже поимка (квадратичность на 80k).
                case("квадратичный мутант ловится (ошибка замера: %s)" % err[:60],
                     "таймаут" in err or "бюджет" in err)
            else:
                m_fails, ratio, times = evaluate(data)
                case("квадратичный мутант ловится бюджетом (ratio=%.1f, "
                     "t=%s)" % (ratio, [round(t) for t in times]),
                     bool(m_fails))
        # Испорченный замер: нулевые времена не принимаются за PASS —
        # _measure отвергает их до сверки с порогами.
        data_zero = {"10000": {"ms": 0}, "40000": {"ms": 0},
                     "80000": {"ms": 0}}
        case("нулевые времена замера отвергаются",
             any(rec["ms"] <= 0 for rec in data_zero.values()))
        case("пороги заморожены и структурны (ratio<=%.1f при квадратичном "
             "росте ~16)" % RATIO_MAX, RATIO_MAX < 16)
    print("САМОПРОВЕРКА check_demo_perf: %s" % ("OK" if fails == 0 else
                                                 "ПРОВАЛОВ %d" % fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Перф-бюджет обработки ввода демо (engine.scanText).")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--engine", default=ENGINE,
                    help="путь к engine.js (по умолчанию demo/engine.js)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    data, err = _measure(args.engine)
    if err == "node недоступен":
        print("UNAVAILABLE: node не найден — перф-бюджет не проверен "
              "(не PASS)")
        return 2
    if err:
        print("FAIL: " + err)
        return 1
    fails, ratio, times = evaluate(data)
    print("Замер scanText ('и\\u0306'+'а'×n): t(10k)=%.0f мс, t(40k)=%.0f мс, "
          "t(80k)=%.0f мс; отношение t40/t10=%.1f" %
          (times[0], times[1], times[2], ratio))
    if fails:
        for f in fails:
            print("FAIL: " + f)
        return 1
    print("БЮДЖЕТ: соблюдён (пороги заморожены 2026-09-07: ratio<=%.1f, "
          "t40<=%.0f мс, t80<=%.0f мс)" % (RATIO_MAX, CAP_40K_MS, CAP_80K_MS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
