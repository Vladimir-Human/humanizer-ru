#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Check the skill scripts on real texts before a commit that changes them. Properties
#          that must hold on any text (an unchanged text has no errors, line endings and paste
#          garbage change no facts, cleaning twice changes nothing) are run over every eval text;
#          --against REF reruns check_facts of REF and of the working tree on every eval edit and
#          lists the errors that appeared or vanished, so a new false alarm is seen before release.
# SCOPE: offline, stdlib only, no API calls; reads eval/corpus/texts and eval/results/*/outputs.
#        The comparison is information for a person: every new error row must be read.
# DEPENDS: Python 3.8+ standard library; git (only for --against).
# LINKS: M-CHECK-SCRIPTS; R-FACTS; R-PASTE; V-M-CHECK-SCRIPTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load: path -> module (a dataclass module needs its sys.modules entry).
# eval_texts / eval_pairs: unique texts; (run, system, name, source, edit) for each eval edit.
# properties: texts, check_facts, clean_paste -> {property: [failures]}.
# against: ref -> rows of errors that appeared (+) or vanished (-) and per-system flip counts.
# main: CLI `check_scripts.py [--against REF] [--rows FILE] [--show N]`; exit 1 if a property fails.
# END_MODULE_MAP
"""Проверка скриптов навыка на текстах замеров.

    python scripts/check_scripts.py                    # свойства на всех текстах eval/
    python scripts/check_scripts.py --against v4.1.4   # и сравнение ошибок check_facts с версией из git

Код выхода: 0 — свойства выполнены, 1 — есть нарушения (сравнение на код не влияет).
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "humanizer-ru" / "scripts"
EVAL = ROOT / "eval"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# START_BLOCK_DATA
def eval_texts() -> Dict[str, str]:
    """Every source and every edit of past runs, each distinct text once: {text: its path}."""
    paths = sorted((EVAL / "corpus" / "texts").glob("*.txt")) + sorted((EVAL / "results").glob("*/outputs/*/*.txt"))
    out: Dict[str, str] = {}
    for p in paths:
        out.setdefault(p.read_text(encoding="utf-8"), str(p.relative_to(EVAL)))
    return out


def eval_pairs():
    for out in sorted((EVAL / "results").glob("*/outputs/*/*.txt")):
        src = EVAL / "corpus" / "texts" / out.name
        if src.exists():
            yield (out.parent.parent.parent.name, out.parent.name, out.stem,
                   src.read_text(encoding="utf-8"), out.read_text(encoding="utf-8"))
# END_BLOCK_DATA


# START_BLOCK_PROPERTIES
INVISIBLE = [chr(c) for c in (0x200B, 0x2060, 0xFEFF, 0x00AD)]
CITATIONS = [" :contentReference[oaicite:3]{index=3}", " " + chr(0x3010) + "4" + chr(0x2020) + "source" + chr(0x3011),
             " [cite: 2]"]


def _errors(report) -> list:
    return [(e["kind"], e["what"], e["detail"]) for e in report["errors"]][:3]


# START_CONTRACT: properties
# PURPOSE: Run the invariants of both scripts over the texts.
# INPUTS: texts {text: name}; cf, cp: check_facts and clean_paste modules (a test passes broken ones).
# OUTPUTS: {property: [(name, detail)]}; an empty dict means every property held.
# SIDE_EFFECTS: none (a fixed random seed picks where garbage goes).
# END_CONTRACT: properties
def properties(texts: Dict[str, str], cf, cp) -> Dict[str, list]:
    fails: Dict[str, list] = collections.defaultdict(list)
    rnd = random.Random(7)
    for text, name in texts.items():
        try:
            r = cf.compare(text, text)
            if r["errors"] or r["checks"]:
                fails["same text has errors or checks"].append((name, _errors(r) or r["checks"][:2]))
            for label, variant in (("CRLF", text.replace("\n", "\r\n")), ("BOM", chr(0xFEFF) + text),
                                   ("NBSP", text.replace(" ", chr(0xA0))), ("blank lines", text.rstrip() + "\n\n")):
                r = cf.compare(text, variant)
                if r["errors"]:
                    fails["%s changes facts" % label].append((name, _errors(r)))
            cleaned, _ = cp.clean(text)
            again, counts = cp.clean(cleaned)
            if again != cleaned:
                fails["second clean changes text"].append((name, counts))
            r = cf.compare(text, cleaned)
            if r["errors"]:
                fails["clean loses facts"].append((name, _errors(r)))
            # Paste garbage put into a clean text must come out exactly: invisible characters inside
            # words, a citation token at the end (the end is never inside code, where it would stay).
            words = cleaned.split(" ")
            if len(words) > 3:
                for _ in range(3):
                    i = rnd.randrange(len(words))
                    j = rnd.randrange(len(words[i]) + 1)
                    words[i] = words[i][:j] + rnd.choice(INVISIBLE) + words[i][j:]
                dirty = " ".join(words)
                body = dirty.rstrip()
                dirty = body + rnd.choice(CITATIONS) + dirty[len(body):]
                result, _ = cp.clean(dirty)
                if result != cleaned:
                    at = next((k for k, (x, y) in enumerate(zip(cleaned, result)) if x != y),
                              min(len(cleaned), len(result)))
                    fails["garbage left after clean"].append((name, repr(result[max(0, at - 30):at + 30])))
        except Exception:  # a crash on a real text is a failure of its own, not the end of the run
            fails["crash"].append((name, traceback.format_exc().splitlines()[-1]))
    return dict(fails)
# END_BLOCK_PROPERTIES


# START_BLOCK_AGAINST
def against(ref: str):
    """Errors of check_facts at REF and in the working tree on every eval edit."""
    src = subprocess.run(["git", "-C", str(ROOT), "show", "%s:skills/humanizer-ru/scripts/check_facts.py" % ref],
                         capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check_facts_ref.py"
        path.write_bytes(src)
        old = load("check_facts_ref", path)
    new = load("check_facts_new", SCRIPTS / "check_facts.py")
    rows: List[tuple] = []
    flips, unflips, total = collections.Counter(), collections.Counter(), collections.Counter()
    for run, system, name, source, edit in eval_pairs():
        total[system] += 1
        before = {(e["kind"], e["what"], e["detail"]) for e in old.compare(source, edit)["errors"]}
        after = {(e["kind"], e["what"], e["detail"]) for e in new.compare(source, edit)["errors"]}
        rows += [("+", run, system, name) + e for e in sorted(after - before)]
        rows += [("-", run, system, name) + e for e in sorted(before - after)]
        flips[system] += bool(after and not before)
        unflips[system] += bool(before and not after)
    return rows, flips, unflips, total
# END_BLOCK_AGAINST


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--against", metavar="REF", help="git ref to compare check_facts errors with (v4.1.4, main)")
    ap.add_argument("--rows", metavar="FILE", help="write every changed error row to this JSON file")
    ap.add_argument("--show", type=int, default=40, help="changed error rows to print (default 40)")
    args = ap.parse_args(argv)

    cf = load("check_facts", SCRIPTS / "check_facts.py")
    cp = load("clean_paste", SCRIPTS / "clean_paste.py")
    texts = eval_texts()
    fails = properties(texts, cf, cp)
    print("[M-CHECK-SCRIPTS][BLOCK_PROPERTIES] texts=%d failed_properties=%d" % (len(texts), len(fails)))
    for prop, items in fails.items():
        print("  %s: %d" % (prop, len(items)))
        for item in items[:5]:
            print("    %s" % (item,))

    if args.against:
        rows, flips, unflips, total = against(args.against)
        print("[M-CHECK-SCRIPTS][BLOCK_AGAINST] ref=%s edits=%d added=%d removed=%d" % (
            args.against, sum(total.values()), sum(r[0] == "+" for r in rows), sum(r[0] == "-" for r in rows)))
        print("  clean -> error: %s" % dict(+flips))
        print("  error -> clean: %s" % dict(+unflips))
        for row in rows[:args.show]:
            print("  " + " | ".join(row))
        if len(rows) > args.show:
            print("  ... %d more (--show, --rows)" % (len(rows) - args.show))
        if args.rows:
            Path(args.rows).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
