#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_gate_mutations.py — гейты убивают подтверждённых мутантов.

Таблица «мутант -> проверяемое свойство -> ожидаемый отказ -> факт»:

| Мутант | Свойство | Ожидаемый отказ | Факт |
|---|---|---|---|
| shutil.which -> None (node «исчез») | паритет JS-стороны обязателен | check() возвращает ошибку, main rc!=0 | test_no_node_is_fail_not_skip |
| CASES[assistants_source][0] -> '(a+)+$' | исключение ReDoS содержательное, не именное | имя в nested_patterns(), гейт rc!=0 | test_pattern_swap_under_exempt_name |
| гомоглифная таблица только латиница->кириллица | оператор мутации меняет вход | _mut != CLEAN, selftest ловит | test_homoglyph_* |
| [\p{M}] в классе переноса \w | паритет Python/JS по фактической семантике | py_to_js не содержит \p{M} | test_word_class_without_M |
"""
import contextlib
import io
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): гейты живут в scripts/ и demo/")
if REPO_ONLY:
    for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src"),
               os.path.join(ROOT, "demo")):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    import check_demo_parity as CDP  # noqa: E402
    import check_markers as cm  # noqa: E402
    import check_perf_regex as CPR  # noqa: E402
    import check_robustness as CRB  # noqa: E402
    import generate_js_rules as G  # noqa: E402
else:  # pragma: no cover — sdist без scripts/
    CDP = cm = CPR = CRB = G = None


@SKIP_OUTSIDE
class NoNodeRefusalTests(unittest.TestCase):
    """Мутант: node «исчез» из окружения (shutil.which -> None)."""

    def test_no_node_is_fail_not_skip(self):
        saved = CDP.shutil.which
        CDP.shutil.which = lambda *a, **k: None
        try:
            errors = CDP.check(CDP.ROOT)
        finally:
            CDP.shutil.which = saved
        self.assertTrue(any("node недоступен" in e for e in errors),
                        "непроверенная JS-сторона не дала ошибку гейта")

    def test_no_node_main_refuses(self):
        saved = CDP.shutil.which
        CDP.shutil.which = lambda *a, **k: None
        try:
            rc = CDP.main([])
        finally:
            CDP.shutil.which = saved
        self.assertNotEqual(rc, 0, "main вернул 0 при непроверенной JS-стороне")


@SKIP_OUTSIDE
class NameExemptMutantTests(unittest.TestCase):
    """Мутант: квадратичный паттерн под именем из прежнего белого списка."""

    def test_pattern_swap_under_exempt_name(self):
        saved = cm.CASES["assistants_source"]
        cm.CASES["assistants_source"] = ["(a+)+$"] + list(saved[1:])
        try:
            self.assertIn("assistants_source", CPR.nested_patterns(),
                          "исключение по имени пережило подмену паттерна")
        finally:
            cm.CASES["assistants_source"] = saved

    def test_clean_signatures_still_safe(self):
        self.assertEqual(CPR.nested_patterns(), [],
                         "содержательное правило дало ложную тревогу на "
                         "чистых сигнатурах")

    def test_bounded_probe_ok(self):
        ok, _msg = CPR.bounded_probe(timeout_s=60)
        self.assertTrue(ok)


@SKIP_OUTSIDE
class HomoglyphMutationTests(unittest.TestCase):
    """Мутант: оператор мутации не меняет применимый вход."""

    def test_homoglyph_changes_cyrillic_clean(self):
        rng = random.Random(20260907)
        self.assertNotEqual(CRB._mut("homoglyph", CRB.CLEAN, rng), CRB.CLEAN,
                            "гомоглифная мутация не меняет кириллический вход")

    def test_homoglyph_mutant_creates_no_hits(self):
        rng = random.Random(20260907)
        self.assertFalse(CRB._hits(CRB._mut("homoglyph", CRB.CLEAN, rng)))

    def test_every_operator_changes_its_applicable_input(self):
        rng = random.Random(20260907)
        probes = _mutation_probes()
        for kind, probe in probes.items():
            self.assertNotEqual(CRB._mut(kind, probe, rng), probe,
                                "оператор %s не меняет применимый вход" % kind)


def _mutation_probes():
    return {
        "homoglyph": CRB.CLEAN,
        "punctuation": "Источник: живой текст без артефактов.",
        "linebreak": CRB.CLEAN,
        "nfc-nfkc": "и\u0306 живой текст без артефактов.",
        "translit": "живой текст code слово",
        "word-smart": 'живой текст "цитата" слово',
        "html-convert": "живой текст & слово",
        "zero-width": CRB.CLEAN,
        "telegram-pdf": "живой  текст с двойным пробелом",
    }

    def test_canonical_samples_still_detected(self):
        samples = CRB.json_samples()
        pos = sum(1 for s in samples.values() if CRB._hits(s))
        self.assertEqual(pos, len(samples))


@SKIP_OUTSIDE
class GeneratorClassTests(unittest.TestCase):
    """Мутант: возврат \p{M} в класс переноса Python \w."""

    def test_word_class_without_M(self):
        src, flags = G.py_to_js("\\w+")
        self.assertEqual(src, "[\\p{L}\\p{N}_]+")
        self.assertIn("u", flags)
        src2, _flags2 = G.py_to_js("\\w \\W")
        self.assertNotIn("\\p{M}", src2)

    def test_service_worker_precaches_cleaner_assets(self):
        sw = G.build_sw("markers", "index", "engine", "sample",
                        "css", "favicon", "manifest", "rules", "cleaner")
        static = json.loads(sw.split("const STATIC = ", 1)[1].split(";", 1)[0])
        self.assertEqual(set(static), {
            "./", "./index.html", "./brand.css", "./markers.js",
            "./engine.js", "./sample.js", "./favicon.svg", "./manifest.json",
            "./cleaner-rules.js", "./cleaner.js",
        })
        self.assertEqual(len(static), len(set(static)))

    def test_service_worker_digest_covers_every_precached_asset(self):
        values = ["markers", "index", "engine", "sample", "css", "favicon",
                  "manifest", "rules", "cleaner"]
        baseline = G.build_sw(*values)
        for i, value in enumerate(values):
            changed = list(values)
            changed[i] = value + " changed"
            mutated = G.build_sw(*changed)
            self.assertNotEqual(baseline.split("\n", 3)[1],
                                mutated.split("\n", 3)[1],
                                "service-worker cache digest ignores asset %d" % i)

    def test_service_worker_generation_hashes_disk_assets(self):
        # Isolated output proves main() passes the disk contents to build_sw;
        # mutating only build_sw's argument test would miss a forgotten read.
        assets = ("index.html", "engine.js", "sample.js", "brand.css",
                  "favicon.svg", "manifest.json", "cleaner-rules.js",
                  "cleaner.js")
        with tempfile.TemporaryDirectory(prefix="demo-sw-") as directory:
            root = Path(directory)
            for name in assets:
                (root / name).write_bytes(name.encode("utf-8"))
            registry = root / "markers.v1.json"
            registry.write_bytes(b'{"count": 0}')
            with mock.patch.multiple(G, HERE=directory, IN=str(registry),
                                     OUT=str(root / "markers.js")), \
                    mock.patch.object(G, "build_js", return_value="markers"), \
                    contextlib.redirect_stdout(io.StringIO()):
                G.main()
                baseline = (root / "sw.js").read_text(encoding="utf-8")
                for name in assets:
                    with self.subTest(asset=name):
                        (root / name).write_bytes((name + " changed").encode("utf-8"))
                        G.main()
                        mutated = (root / "sw.js").read_text(encoding="utf-8")
                        self.assertNotEqual(baseline.splitlines()[1],
                                            mutated.splitlines()[1])
                        (root / name).write_bytes(name.encode("utf-8"))

    def test_service_worker_activation_keeps_foreign_caches(self):
        """Activation may remove only stale caches owned by this demo."""
        node = __import__("shutil").which("node")
        if node is None:
            self.fail("Node.js is required for service-worker regression tests")
        source = G.build_sw("markers", "index", "engine", "sample",
                            "css", "favicon", "manifest", "rules", "cleaner")
        harness = r'''const vm = require("vm");
const source = JSON.parse(process.argv[1]);
const current = source.match(/const CACHE = "([^"]+)"/)[1];
const listeners = {};
const deleted = [];
let activation;
const context = vm.createContext({
  self: { addEventListener(type, fn) { listeners[type] = fn; },
          skipWaiting() {} },
  clients: { claim() {} },
  caches: {
    keys() { return Promise.resolve(["humanizer-ru-old", "other-app-v1", current]); },
    delete(key) { deleted.push(key); return Promise.resolve(true); },
    open() { return Promise.resolve({ addAll() {} }); }
  }, Promise
});
vm.runInContext(source, context);
listeners.activate({ waitUntil(p) { activation = p; } });
activation.then(() => process.stdout.write(JSON.stringify(deleted)));
'''
        proc = __import__("subprocess").run(
            [node, "-e", harness, json.dumps(source)], cwd=ROOT,
            text=True, encoding="utf-8", capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), ["humanizer-ru-old"])

    def test_service_worker_fetch_isolated_and_status_is_fresh(self):
        """Fetch must not read a foreign cache or cache mutable status.json."""
        node = __import__("shutil").which("node")
        if node is None:
            self.fail("Node.js is required for service-worker regression tests")
        source = G.build_sw("markers", "index", "engine", "sample",
                            "css", "favicon", "manifest", "rules", "cleaner")
        harness = r'''const vm = require("vm");
const source = JSON.parse(process.argv[1]);
const listeners = {};
const calls = [];
const cache = {
  match(req) { calls.push(["cache.match", req.url]); return Promise.resolve(); },
  put(req) { calls.push(["cache.put", req.url]); return Promise.resolve(); }
};
let responseNo = 0;
function fetchStub(req) {
  calls.push(["fetch", req.url]);
  const id = ++responseNo;
  return Promise.resolve({id, clone() { return {id}; }});
}
const context = vm.createContext({
  self: { addEventListener(type, fn) { listeners[type] = fn; },
          skipWaiting() {} }, clients: { claim() {} },
  caches: { open() { calls.push(["cache.open"]); return Promise.resolve(cache); },
           keys() { return Promise.resolve([]); }, delete() { return Promise.resolve(true); } },
  fetch: fetchStub, URL, Promise
});
vm.runInContext(source, context);
async function dispatch(url) {
  let result;
  listeners.fetch({request: {method: "GET", url},
                  respondWith(p) { result = p; }});
  return result;
}
(async () => {
  await dispatch("https://example.test/app/index.html");
  await dispatch("https://example.test/app/status.json");
  process.stdout.write(JSON.stringify(calls));
})();
'''
        proc = __import__("subprocess").run(
            [node, "-e", harness, json.dumps(source)], cwd=ROOT,
            text=True, encoding="utf-8", capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        calls = json.loads(proc.stdout)
        self.assertIn(["cache.open"], calls)
        self.assertIn(["cache.match", "https://example.test/app/index.html"], calls)
        self.assertIn(["cache.put", "https://example.test/app/index.html"], calls)
        self.assertEqual(
            [entry for entry in calls if entry[0] == "fetch"],
            [["fetch", "https://example.test/app/index.html"],
             ["fetch", "https://example.test/app/status.json"]])
        self.assertNotIn(["cache.match", "https://example.test/app/status.json"], calls)
        self.assertNotIn(["cache.put", "https://example.test/app/status.json"], calls)


if __name__ == "__main__":
    unittest.main()
