#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Check the skill scripts on real texts before a commit that changes them. Properties
#          that must hold on any text (an unchanged text has no errors, line endings and paste
#          garbage change no facts, cleaning twice changes nothing) are run over every eval text;
#          --against REF reruns check_facts of REF and of the working tree on every eval edit and
#          lists the errors that appeared or vanished, so a new false alarm is seen before release.
#          Holdout5 (h5_*, holdout5*) prose details are redacted by default to protect R-HOLDOUT,
#          printing aggregate counts only and failing non-zero on clean->error regressions.
# SCOPE: offline, stdlib only, no API calls; reads eval/corpus/texts and eval/results/*/outputs.
#        The comparison is information for a person: every new public error row must be read.
# DEPENDS: Python 3.8+ standard library; git (only for --against).
# LINKS: M-CHECK-SCRIPTS; R-FACTS; R-PASTE; R-HOLDOUT; V-M-CHECK-SCRIPTS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load: path -> module (a dataclass module needs its sys.modules entry).
# is_holdout5: detect holdout5 / h5_* paths so prose details are redacted (R-HOLDOUT).
# eval_texts / eval_pairs: unique texts; (run, system, name, source, edit) for each eval edit.
# properties: texts, check_facts, clean_paste -> {property: [failures]}.
# against: ref -> rows of errors that appeared (+) or vanished (-) and per-system flip counts.
# main: CLI `check_scripts.py [--against REF] [--rows FILE] [--show N]`; exit 1 on failure or holdout5 regression.
# END_MODULE_MAP
"""Проверка скриптов навыка на текстах замеров.

    python scripts/check_scripts.py                    # свойства на всех текстах eval/
    python scripts/check_scripts.py --against v4.1.4   # и сравнение ошибок check_facts с версией из git

Код выхода: 0 — свойства выполнены (и нет регрессий на holdout5), 1 — есть нарушения.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import random
import re
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
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def is_holdout5(run_or_path: str, name: str = "") -> bool:
    norm = str(run_or_path).replace("\\", "/").lower()
    stem = str(name).lower()
    if stem.startswith("h5_") or norm.startswith("holdout5") or norm.startswith("h5_"):
        return True
    parts = norm.split("/")
    return any(p.startswith("holdout5") or p.startswith("h5_") for p in parts)


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


def _code_spans(text: str, cp) -> list:
    fence_fn = getattr(cp, "_code_fence_spans", None)
    inline_fn = getattr(cp, "_inline_code_spans", None)
    fences = list(fence_fn(text)) if callable(fence_fn) else []
    inlines = list(inline_fn(text, fences)) if callable(inline_fn) else []
    return sorted(fences + inlines)


def _has_emoji_or_joiner(s: str) -> bool:
    return any(ord(c) in (0x200D, 0xFE0F, 0xFE0E) or ord(c) >= 0x1F000 for c in s)


def _inject_garbage(cleaned: str, cp, rnd: random.Random):
    """Insert INVISIBLE chars and a CITATIONS token strictly outside code spans and emoji ZWJ clusters."""
    code_spans = _code_spans(cleaned, cp)
    eligible = []
    for m in re.finditer(r"\S+", cleaned):
        ws, we = m.span()
        word = m.group(0)
        if "`" in word or "~" in word:
            continue
        if any(s <= we and ws <= e for s, e in code_spans):
            continue
        if _has_emoji_or_joiner(cleaned[max(0, ws - 1):min(len(cleaned), we + 1)]):
            continue
        eligible.append((ws, we))

    inserts = []
    if eligible:
        for _ in range(3):
            ws, we = rnd.choice(eligible)
            pos = rnd.randrange(ws, we + 1)
            inserts.append((pos, 0, rnd.choice(INVISIBLE)))

    body_end = len(cleaned.rstrip())
    cit_pos = None
    if body_end > 0 and not any(s < body_end <= e for s, e in code_spans):
        cit_pos = body_end
    elif eligible:
        cit_pos = eligible[-1][1]
    if cit_pos is not None:
        inserts.append((cit_pos, 1, rnd.choice(CITATIONS)))

    if not inserts:
        return None
    dirty = cleaned
    for pos, _order, tok in sorted(inserts, key=lambda item: (item[0], item[1]), reverse=True):
        dirty = dirty[:pos] + tok + dirty[pos:]
    return dirty


# START_CONTRACT: properties
# PURPOSE: Run the invariants of both scripts over the texts.
# INPUTS: texts {text: name}; cf, cp: check_facts and clean_paste modules (a test passes broken ones).
# OUTPUTS: {property: [(name, detail)]}; an empty dict means every property held.
# SIDE_EFFECTS: none (deterministic per-text sha256 seed picks where garbage goes outside code/emoji).
# END_CONTRACT: properties
def properties(texts: Dict[str, str], cf, cp) -> Dict[str, list]:
    fails: Dict[str, list] = collections.defaultdict(list)
    for text, name in texts.items():
        rnd = random.Random(hashlib.sha256(text.encode("utf-8")).digest())
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
            # Paste garbage put into prose (outside code spans and emoji ZWJ clusters) must come out cleanly.
            dirty = _inject_garbage(cleaned, cp, rnd)
            if dirty is not None:
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
    h5_flips = h5_unflips = 0
    for run, system, name, source, edit in eval_pairs():
        total[system] += 1
        before = {(e["kind"], e["what"], e["detail"]) for e in old.compare(source, edit)["errors"]}
        after = {(e["kind"], e["what"], e["detail"]) for e in new.compare(source, edit)["errors"]}
        rows += [("+", run, system, name) + e for e in sorted(after - before)]
        rows += [("-", run, system, name) + e for e in sorted(before - after)]
        flipped = bool(after and not before)
        unflipped = bool(before and not after)
        flips[system] += flipped
        unflips[system] += unflipped
        if is_holdout5(run, name):
            h5_flips += flipped
            h5_unflips += unflipped
    return rows, flips, unflips, total, h5_flips, h5_unflips
# END_BLOCK_AGAINST


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--against", metavar="REF", help="git ref to compare check_facts errors with (v4.1.4, main)")
    ap.add_argument("--rows", metavar="FILE", help="write every changed error row to this JSON file (holdout5 redacted)")
    ap.add_argument("--show", type=int, default=40, help="changed error rows to print (default 40)")
    args = ap.parse_args(argv)

    cf = load("check_facts", SCRIPTS / "check_facts.py")
    cp = load("clean_paste", SCRIPTS / "clean_paste.py")
    texts = eval_texts()
    fails = properties(texts, cf, cp)
    print("[M-CHECK-SCRIPTS][BLOCK_PROPERTIES] texts=%d failed_properties=%d" % (len(texts), len(fails)))
    for prop, items in fails.items():
        print("  %s: %d" % (prop, len(items)))
        h5_count = sum(1 for name, _ in items if is_holdout5(name))
        public_items = [(name, detail) for name, detail in items if not is_holdout5(name)]
        for item in public_items[:5]:
            print("    %s" % (item,))
        if h5_count:
            print("    <holdout5 redacted (R-HOLDOUT): %d>" % h5_count)

    h5_regressed = False
    if args.against:
        rows, flips, unflips, total, h5_flips, h5_unflips = against(args.against)
        public_rows = [r for r in rows if not is_holdout5(r[1], r[3])]
        h5_rows = [r for r in rows if is_holdout5(r[1], r[3])]
        print("[M-CHECK-SCRIPTS][BLOCK_AGAINST] ref=%s edits=%d added=%d removed=%d" % (
            args.against, sum(total.values()), sum(r[0] == "+" for r in rows), sum(r[0] == "-" for r in rows)))
        print("  clean -> error: %s" % dict(+flips))
        print("  error -> clean: %s" % dict(+unflips))
        if h5_rows or h5_flips or h5_unflips:
            print("  holdout5 (redacted, R-HOLDOUT): added=%d removed=%d clean->error=%d error->clean=%d" % (
                sum(r[0] == "+" for r in h5_rows), sum(r[0] == "-" for r in h5_rows), h5_flips, h5_unflips))
        if h5_flips > 0:
            h5_regressed = True
        for row in public_rows[:args.show]:
            print("  " + " | ".join(row))
        if len(public_rows) > args.show:
            print("  ... %d more (--show, --rows)" % (len(public_rows) - args.show))
        if args.rows:
            safe_rows = [
                (r[:6] + ("<redacted: R-HOLDOUT>",) if is_holdout5(r[1], r[3]) else r)
                for r in rows
            ]
            Path(args.rows).write_text(json.dumps(safe_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if (fails or h5_regressed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
