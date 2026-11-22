#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Per-rule probes of the skill instruction: short texts that each test one rule of
#          SKILL.md (hedges kept, nothing added, grammatical dash kept, chat wrapper removed,
#          injection ignored, human text left alone, ...) with a deterministic oracle, so a
#          change of the instruction shows which rule got better or worse without a judge.
# SCOPE: reads eval/corpus/probes.json; `run` writes results/<run>/probes/<system>/r<k>/<id>.txt
#        (resumable); `score` writes results/<run>/probes.md and probes.json. No judge, no API
#        calls in `score`.
# DEPENDS: evallib (chat, IO), run_systems (load_system, inline_system, REQUEST),
#          skills/humanizer-ru/scripts/check_facts.py (the "facts" oracle).
# LINKS: M-EVAL-PROBES; R-PROBES; V-M-EVAL-PROBES.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# ORACLES: names of the checks a probe may carry; score_one: (probe, output) -> {check: bool}.
# LIST_RX: a line that starts a list item; norm: lower case, ё -> е, for substring checks.
# run: outputs for systems x repeats with one executor (thread pool, resumable).
# merge_config: probes/config.json keeps who answered for each participant across runs.
# summarize: pass counts per (system, run) and rule, the spread between runs, failed checks.
# render: Markdown table for probes.md.
# main: CLI run | score.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import difflib
import importlib.util
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import evallib as lib
import run_systems as rs

PROBES = lib.EVAL_DIR / "corpus" / "probes.json"
_CF = None


def check_facts():
    global _CF
    if _CF is None:
        path = rs.REPO / "skills" / "humanizer-ru" / "scripts" / "check_facts.py"
        spec = importlib.util.spec_from_file_location("check_facts", path)
        _CF = importlib.util.module_from_spec(spec)
        sys.modules["check_facts"] = _CF
        spec.loader.exec_module(_CF)
    return _CF


# START_BLOCK_ORACLES
ORACLES = ("keep", "keep_any", "keep_re", "drop", "facts", "yo", "asks", "list_items", "bold_less",
           "min_count", "min_similarity", "min_len_ratio")
LIST_RX = re.compile(r"(?m)^[ \t]*(?:(?:\*\*)?\d{1,2}[.)](?:\*\*)?|[-*•–—](?=[ \t])|\*\*\s*Шаг|Шаг\s+\d)")
ASK_RX = re.compile(r"^[\s\-*•\d.)]*(?:\*\*)?(?:уточните|назовите|напишите|подскажите|скажите|расскажите|"
                    r"опишите|укажите|пришлите|ответьте)(?![а-яё])", re.I)
# Ambiguous ё/е homographs where the е-form is a different valid Russian word (e.g. всё -> все, слёз -> слез).
YO_HOMOGRAPHS = frozenset({"все", "слез", "берет", "сел", "мел", "небо", "осел", "ведро"})
_ADJ_END_RX = re.compile(r"(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ом|ем|ую|юю|ых|их|ыми|ими)$", re.I)
_ADJ_ENDS = "ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ом|ем|ую|юю|ых|их|ыми|ими"


def _yo_dropped(src: str, out: str) -> bool:
    """True if a source word written with ё reappears in out with е instead of ё (incl. adjectival
    inflections like тёплый -> теплым, skipping ambiguous homographs like всё/все)."""
    words = {w for w in re.findall(r"[А-Яа-яЁё]+", src) if "ё" in w.lower()}
    for w in words:
        w_low = w.lower()
        w_e = w_low.replace("ё", "е")
        if w_e in YO_HOMOGRAPHS:
            continue
        if re.search(r"(?<![А-Яа-яЁё])%s(?![А-Яа-яЁё])" % re.escape(w_e), out, re.I):
            return True
        m_adj = _ADJ_END_RX.search(w_low)
        if m_adj and "ё" in w_low[:m_adj.start()] and m_adj.start() >= 4:
            stem_e = w_low[:m_adj.start()].replace("ё", "е")
            if re.search(r"(?<![А-Яа-яЁё])%s(?:%s)(?![А-Яа-яЁё])" % (re.escape(stem_e), _ADJ_ENDS), out, re.I):
                return True
    return False


def norm(s: str) -> str:
    return s.lower().replace("ё", "е")


# START_CONTRACT: score_one
# PURPOSE: Apply every oracle a probe carries to one output.
# INPUTS: probe (dict from probes.json), output (str, the executor's reply).
# OUTPUTS: {check name: True if it holds}; a probe passes when all values are True.
# RULES: keep / keep_any are substrings, case and ё-insensitive; keep_re / drop are regexes
#        (multiline, as written); facts = check_facts finds no error and no added fact; yo = no
#        word written with ё in the source appears with е; asks = notes after --- contain a «?» or
#        a request to the author; list_items = at least N lines start a list item.
#        Every oracle reads the edited text without the notes to the author (evallib.split_notes,
#        R-NOTES-NOT-TEXT) except asks, which reads the notes section.
# SIDE_EFFECTS: none.
# END_CONTRACT: score_one
def score_one(probe: dict, output: str) -> dict:
    src, answer = probe["text"], output or ""
    out, notes = lib.split_notes(answer, src)  # «Убрал слово "шедевр"» in the notes is not the edit
    res = {}
    for s in probe.get("keep", []):
        res["keep:%s" % s] = norm(s) in norm(out)
    for group in probe.get("keep_any", []):
        res["keep_any:%s" % "|".join(group)] = any(norm(s) in norm(out) for s in group)
    for rx in probe.get("keep_re", []):
        res["keep_re:%s" % rx] = re.search(rx, out, re.M) is not None
    for rx in probe.get("drop", []):
        res["drop:%s" % rx] = re.search(rx, out, re.M) is None
    if probe.get("facts"):
        r = check_facts().compare(src, out)
        res["facts"] = not r["errors"] and not any(c["kind"] == "added" for c in r["checks"])
    if probe.get("yo"):
        res["yo"] = not _yo_dropped(src, out)
    if probe.get("asks"):
        q_block = notes
        if not q_block:
            lines = answer.replace("\r\n", "\n").rstrip().split("\n")
            rules = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
            if rules:
                tail = "\n".join(lines[rules[-1] + 1:]).strip()
                if tail and len(tail) <= lib.NOTE_MAX_CHARS:
                    stems = lib._stems(lib.NOTE_QUOTE_RX.sub(" ", tail))
                    if not stems or len(stems & lib._stems(src)) / len(stems) < 0.5:
                        if any(ASK_RX.match(ln) for ln in tail.splitlines()):
                            q_block = tail
        res["asks"] = bool(q_block) and ("?" in q_block or any(ASK_RX.match(ln) for ln in q_block.splitlines()))
    if probe.get("list_items"):
        res["list_items"] = len(LIST_RX.findall(out)) >= probe["list_items"]
    if probe.get("bold_less"):
        res["bold_less"] = out.count("**") < src.count("**")
    for s, n in probe.get("min_count", []):
        res["min_count:%s" % s] = out.count(s) >= n
    if "min_similarity" in probe:
        res["min_similarity"] = difflib.SequenceMatcher(None, src, out.strip()).ratio() >= probe["min_similarity"]
    if "min_len_ratio" in probe:
        res["min_len_ratio"] = len(out.strip()) >= probe["min_len_ratio"] * len(src)
    return res
# END_BLOCK_ORACLES


# START_BLOCK_RUN
def run(run_dir: Path, systems: list, executor: str, repeat: int, workers: int, ids=None) -> int:
    probes = [p for p in lib.read_json(PROBES) if not ids or p["id"] in ids]
    sysdefs = {s["name"]: s for s in lib.read_json(lib.EVAL_DIR / "systems.json")}
    jobs = []
    for name in systems:
        system, files = rs.load_system(sysdefs[name])
        if executor.startswith(lib.DSH_PREFIX):
            system = rs.inline_system(system, files)
        for k in range(repeat):
            for p in probes:
                path = run_dir / "probes" / name / ("r%d" % k) / (p["id"] + ".txt")
                if not path.exists():
                    jobs.append((path, system, p))
    print("[M-EVAL-PROBES][BLOCK_RUN] todo=%d executor=%s" % (len(jobs), executor))

    def one(job):
        path, system, p = job
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": p.get("request", rs.REQUEST) + p["text"]}]
        msg, _ = lib.chat(executor, messages, max_tokens=8000, tag="probes")
        text = (msg.get("content") or "").strip()
        if not text:
            raise RuntimeError("empty answer")
        lib.write_text(path, text + "\n")
        return path

    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, j): j for j in jobs}
        for fut in as_completed(futures):
            try:
                fut.result()
            except lib.BudgetExceeded:
                raise
            except Exception as exc:  # one failed probe must not lose the others; a rerun resumes
                failed += 1
                print("[M-EVAL-PROBES][BLOCK_RUN] failed %s: %s" % (futures[fut][0], str(exc)[:200]))
    # One record per participant: a later run with other systems in the same folder (chat and prompt
    # after ours and ours417 on 2026-11-09) used to overwrite who answered the earlier ones.
    cfg_path = run_dir / "probes" / "config.json"
    lib.write_json(cfg_path, merge_config(lib.read_json(cfg_path) if cfg_path.exists() else {},
                                          systems, executor, repeat))
    return failed


def merge_config(cfg: dict, systems: list, executor: str, repeat: int) -> dict:
    """{"by_system": {name: {executor, repeat}}}; an old flat config is read as one record per system."""
    per = dict(cfg.get("by_system") or {s: {"executor": cfg.get("executor"), "repeat": cfg.get("repeat")}
                                        for s in cfg.get("systems", [])})
    per.update({s: {"executor": executor, "repeat": repeat} for s in systems})
    return {"by_system": per}
# END_BLOCK_RUN


# START_BLOCK_SUMMARY
def summarize(run_dir: Path) -> dict:
    probes = {p["id"]: p for p in lib.read_json(PROBES)}
    cells = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # (system, run) -> rule -> [passed, total]
    fails = defaultdict(lambda: defaultdict(int))  # system -> "id check" -> count over runs
    for path in sorted((run_dir / "probes").glob("*/r*/*.txt")):
        system, rnd, pid = path.parent.parent.name, path.parent.name, path.stem
        if pid not in probes:
            continue
        res = score_one(probes[pid], path.read_text(encoding="utf-8"))
        ok = all(res.values())
        cell = cells[(system, rnd)][probes[pid]["rule"]]
        cell[0] += int(ok)
        cell[1] += 1
        for check, good in res.items():
            if not good:
                fails[system]["%s %s" % (pid, check)] += 1
    out = {"cells": {"%s|%s" % k: dict(v) for k, v in cells.items()},
           "fails": {s: dict(v) for s, v in fails.items()}}
    systems = sorted({s for s, _ in cells})
    rules = sorted({r for v in cells.values() for r in v})
    table = {}
    for s in systems:
        runs = sorted((r for ss, r in cells if ss == s),
                      key=lambda r: (0, int(r[1:])) if r.startswith("r") and r[1:].isdigit() else (1, r))
        row = {}
        for rule in rules:
            vals = [cells[(s, r)][rule] for r in runs if rule in cells[(s, r)]]
            passed, total = sum(v[0] for v in vals), sum(v[1] for v in vals)
            per_run = [v[0] for v in vals]
            row[rule] = {"passed": passed, "total": total, "per_run": per_run,
                         "spread": (max(per_run) - min(per_run)) if per_run else 0}
        allp = [sum(cells[(s, r)][rule][0] for rule in cells[(s, r)]) for r in runs]
        row["_all"] = {"passed": sum(allp), "total": sum(sum(v[1] for v in cells[(s, r)].values()) for r in runs),
                       "per_run": allp, "spread": (max(allp) - min(allp)) if allp else 0}
        table[s] = row
    out["table"] = table
    return out


def render(summary: dict, title: str) -> str:
    table = summary["table"]
    systems = sorted(table)
    rules = sorted({r for row in table.values() for r in row if r != "_all"}) if table else []
    lines = ["# Пробы: %s" % title, "",
             "Доля проб, где выполнены все проверки; в скобках — по прогонам.", "",
             "| Правило | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    for rule in rules + ["_all"]:
        cells = []
        for s in systems:
            c = table[s].get(rule)
            cells.append("—" if not c else "%d/%d (%s)" % (c["passed"], c["total"], ", ".join(map(str, c["per_run"]))))
        lines.append("| %s | %s |" % ("всего" if rule == "_all" else rule, " | ".join(cells)))
    lines += ["", "## Невыполненные проверки (число прогонов)", ""]
    for s in systems:
        items = sorted(summary["fails"].get(s, {}).items())
        lines.append("- **%s**: %s" % (s, "; ".join("%s ×%d" % kv for kv in items) or "нет"))
    return "\n".join(lines) + "\n"
# END_BLOCK_SUMMARY


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--run", required=True)
    r.add_argument("--systems", required=True)
    r.add_argument("--executor", required=True)
    r.add_argument("--repeat", type=int, default=2)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--ids", default="")
    s = sub.add_parser("score")
    s.add_argument("--run", required=True)
    args = ap.parse_args()
    run_dir = lib.EVAL_DIR / "results" / args.run
    if args.cmd == "run":
        failed = run(run_dir, [x for x in args.systems.split(",") if x], args.executor, args.repeat,
                     args.workers, [x for x in args.ids.split(",") if x] or None)
        print("[M-EVAL-PROBES][BLOCK_RUN] failed=%d" % failed)
        return 1 if failed else 0
    summary = summarize(run_dir)
    lib.write_json(run_dir / "probes.json", summary)
    lib.write_text(run_dir / "probes.md", render(summary, args.run))
    print(render(summary, args.run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
