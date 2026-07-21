#!/usr/bin/env python3
"""run_eval.py — нейтральный прогон корпуса humanizer-ru-eval.

Любой скилл-кандидат прогоняет manifest.v1.json одной командой.
По умолчанию использует regex из check_markers.py как reference-кандидат;
через --candidate можно подключить внешний runner-скрипт (stdin: путь к
файлу, stdout: JSON со списком совпадений [{file, line, case}]).

Запуск:
  python3 eval/run_eval.py
  python3 eval/run_eval.py --candidate /path/to/runner.py

Только стандартная библиотека.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.v1.json")

try:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from check_markers import CASES, _inside_backticks, _console_text
except Exception as exc:  # noqa: BLE001
    print("Не удалось импортировать check_markers: %s" % exc, file=sys.stderr)
    CASES = {}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_default(path, compiled):
    hits = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh.read().splitlines(), 1):
            for name, rx in compiled.items():
                for m in rx.finditer(line):
                    if _inside_backticks(line, m.start(), m.end()):
                        continue
                    hits.append({"line": lineno, "case": name,
                                 "fragment": _console_text(line.strip()[:80])})
    return hits


def _scan_candidate(path, runner):
    proc = subprocess.run([sys.executable, runner, path], capture_output=True, text=True)
    if proc.returncode != 0:
        return [{"error": proc.stderr.strip()[:200]}]
    try:
        data = json.loads(proc.stdout)
        return data if isinstance(data, list) else [{"error": "runner returned non-list"}]
    except json.JSONDecodeError:
        return [{"error": "runner returned non-JSON"}]


def run(manifest_path=MANIFEST, candidate=None):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    compiled = {name: re.compile(case[0]) for name, case in CASES.items()} if not candidate else None

    summary = {"manifest_version": manifest.get("version", "?"),
               "candidate": "check_markers.py (reference)" if not candidate else candidate,
               "files": 0, "hash_mismatches": 0,
               "human_hits": 0, "ai_hits": 0, "boundary_expected_ok": 0,
               "boundary_unexpected": 0, "details": []}

    for entry in manifest["corpus"]:
        rel = entry["path"]
        path = os.path.join(ROOT, rel)
        summary["files"] += 1
        if not os.path.isfile(path):
            summary["details"].append({"file": rel, "error": "file missing"})
            continue
        actual = _sha256(path)
        if actual != entry["sha256"]:
            summary["hash_mismatches"] += 1
            summary["details"].append({"file": rel, "error": "hash mismatch",
                                        "expected": entry["sha256"], "actual": actual})
            continue
        if candidate:
            hits = _scan_candidate(path, candidate)
        else:
            hits = _scan_default(path, compiled)
        kind = entry.get("kind")
        expected = entry.get("expected_hits")
        expected_case = entry.get("expected_case")
        actual_names = {h.get("case") for h in hits if "case" in h}
        if kind == "human":
            if hits:
                summary["human_hits"] += len(hits)
                summary["details"].append({"file": rel, "kind": "human",
                                           "hits": hits[:3], "fp": True})
        elif kind == "ai":
            summary["ai_hits"] += len(hits)
        elif kind == "boundary":
            if expected is not None:
                if len(hits) == expected and (not expected_case or expected_case in actual_names):
                    summary["boundary_expected_ok"] += 1
                else:
                    summary["boundary_unexpected"] += 1
                    summary["details"].append({"file": rel, "kind": "boundary",
                                               "expected": expected, "actual": len(hits),
                                               "cases": list(actual_names)})
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--candidate", help="внешний runner-скрипт")
    args = ap.parse_args()
    summary = run(args.manifest, args.candidate)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    problems = summary["hash_mismatches"] + summary["human_hits"] + summary["boundary_unexpected"]
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
