#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: The fact check of the checker page (site/check/facts.js) gives the same report as the
#          skill's check_facts.py: the same compare() result and the same Russian text (R-SITE-FACTS).
# SCOPE: pairs = every compare() call made by tests/test_scripts.py (the hand-made edge cases),
#        probe texts against every saved probe answer, corpus texts against every saved eval
#        answer; both engines run on all of them; mismatches are printed with the first difference.
# DEPENDS: node on PATH; site/check/facts-cli.js; skills/humanizer-ru/scripts/check_facts.py.
# LINKS: M-SITE-FACTS; V-M-SITE-FACTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# test_pairs: run tests/test_scripts.py with check_facts.compare wrapped to record its inputs.
# eval_pairs: (source, answer) of every saved answer whose source is known.
# first_diff: the path and both values of the first place where two JSON values differ.
# main: CLI `check_site_facts.py [--every N] [--show K]`; exit 0 same, 1 mismatches, 2 no node.
# END_MODULE_MAP
"""Сверка JS-движка страницы с check_facts.py.
    python scripts/check_site_facts.py             # все пары
    python scripts/check_site_facts.py --every 7   # пары тестов и каждая 7-я пара замеров
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"
CLI = ROOT / "site" / "check" / "facts-cli.js"


def test_pairs() -> list:
    sys.path.insert(0, str(ROOT / "tests"))
    import test_scripts as ts  # noqa: E402
    seen, real = [], ts.cf.compare

    def rec(before, after):
        seen.append((before, after))
        return real(before, after)

    ts.cf.compare = rec
    try:
        suite = unittest.defaultTestLoader.loadTestsFromModule(ts)
        unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    finally:
        ts.cf.compare = real
    return [("test", b, a) for b, a in seen if isinstance(b, str) and isinstance(a, str)]


def eval_pairs() -> list:
    probes = {p["id"]: p["text"] for p in json.loads((EVAL / "corpus" / "probes.json").read_text("utf-8"))}
    out = []
    for f in sorted((EVAL / "results").rglob("*.txt")):
        if "outputs" not in f.parts and "probes" not in f.parts:
            continue
        src = probes.get(f.stem)
        if src is None:
            p = EVAL / "corpus" / "texts" / (f.stem + ".txt")
            src = p.read_text("utf-8") if p.exists() else None
        if src is not None:
            out.append((str(f.relative_to(EVAL / "results")), src, f.read_text("utf-8")))
    return out


def first_diff(a, b, path="$"):
    if type(a) is not type(b):
        return path, a, b
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return "%s.%s" % (path, k), a.get(k, "<нет>"), b.get(k, "<нет>")
            d = first_diff(a[k], b[k], "%s.%s" % (path, k))
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, "%s[%d]" % (path, i))
            if d:
                return d
        return None if len(a) == len(b) else ("%s.length" % path, len(a), len(b))
    return None if a == b else (path, a, b)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=1, help="only every N-th eval pair (test pairs always)")
    ap.add_argument("--show", type=int, default=5)
    args = ap.parse_args(argv)
    node = shutil.which("node")
    if not node or not CLI.exists():
        print("нет node или %s" % CLI)
        return 2
    sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))
    import check_facts as cf  # noqa: E402
    pairs, seen = [], set()
    for label, b, a in test_pairs() + eval_pairs()[::max(1, args.every)]:
        if (b, a) not in seen:
            seen.add((b, a))
            pairs.append((label, b, a))
    want = []
    for _, b, a in pairs:
        r = cf.compare(b, a)
        want.append(json.loads(json.dumps({"result": r, "text": cf.render(r)}, ensure_ascii=False)))
    res = subprocess.run([node, str(CLI)], input=json.dumps([[b, a] for _, b, a in pairs], ensure_ascii=False),
                         capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print("facts-cli.js упал:\n" + res.stderr[-2000:])
        return 1
    got = json.loads(res.stdout)
    bad = [(i, d) for i, (w, g) in enumerate(zip(want, got)) for d in [first_diff(w, g)] if d]
    if len(got) != len(want):
        bad.append((-1, ("$.length", len(want), len(got))))
    print("Пар: %d (из тестов %d). Расхождений: %d." % (len(pairs), sum(1 for p in pairs if p[0] == "test"), len(bad)))
    for i, (path, w, g) in bad[:args.show]:
        label = pairs[i][0] if i >= 0 else "-"
        print("- #%d %s: %s\n    python: %s\n    js:     %s" % (i, label, path, json.dumps(w, ensure_ascii=False)[:300],
                                                            json.dumps(g, ensure_ascii=False)[:300]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
