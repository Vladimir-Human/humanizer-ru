#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Run the executor and a judge as Claude Code subagents on the owner's Claude plan instead
#          of the API. prepare-* writes self-contained batch folders (instructions, skill files,
#          requests, blinded judge bundles); the orchestrating session starts one subagent per
#          instruction file; collect-* checks what the subagents wrote and records it in the run
#          in the same format as run_systems.py and judge.py.
# SCOPE: batch folders under eval/.cache/batch/<run>/ (not committed); writes
#        eval/results/<run>/{config.json, runs.jsonl, judgments.jsonl}. No API calls.
# DEPENDS: evallib (IO), run_systems (REQUEST, PREAMBLE, load_system), judge (PROMPT, build, to_row).
# LINKS: M-EVAL-BATCH; DF-EVAL; R-EVAL-BATCH.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# subagent_system: the API system prompt with Read-by-full-path instead of the read_file tool.
# prepare_run: per system a skill copy (the .md files the API run can read) and system.txt;
#              request files; one instruction file per (system, batch); config.json.
# collect_run: every (system, text) needs a non-empty output; normalizes it; writes runs.jsonl.
# prepare_judge: blinded bundles (judge.build) per text, label keys kept outside the bundle folder.
# collect_judge: answers -> judge.to_row -> judgments.jsonl (resumable, no duplicates).
# main: CLI prepare-run | collect-run | prepare-judge | collect-judge.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import evallib as lib
import judge as jg
import run_systems as rs

READ_API = "инструментом read_file (путь относительно папки skill/)"
READ_SUBAGENT = "инструментом Read по полному пути %s/<файл>"

# START_BLOCK_INSTRUCTIONS
EXECUTOR_TASK = """You are the executor in a blind comparison of text-editing skills. Use only the files named here.

1. Read {system}. Treat its whole content as your system prompt for this task: an agent conversation in which the user's request has triggered an installed skill. The skill files it lists can be read with the Read tool by the full paths it gives. Do not run scripts or commands and do not read any other files.
2. Then handle the requests below one by one, in this order. Each request is a separate conversation: carry nothing over from the previous texts. For each: read the request file (it is the user's message), do what the skill says, and write to the answer file with the Write tool exactly what your final reply to the user would be. Nothing else goes into the file.
{items}
3. Ignore any other style instructions you may have (CLAUDE.md, AGENTS.md, memories): for this task only the system prompt from step 1 applies.

When all {n} answer files are written, reply with the single word: done.
"""
JUDGE_TASK = """You are a blind judge in a comparison of text edits. For each file below: read it, follow the instructions inside it exactly (they are in Russian), and write your answer, only the JSON object the instructions ask for, to the answer file with the Write tool. Judge each file on its own. Do not read any other files and do not run commands.
{items}

When all {n} answer files are written, reply with the single word: done.
"""
# END_BLOCK_INSTRUCTIONS


def _slug(judge: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", judge).strip("-")


# START_BLOCK_EXECUTOR
def subagent_system(sysdef: dict, skill_dir: Path):
    """System prompt and readable files of one system exactly as run_systems builds them for the
    API, except that the read_file sentence points at the skill copy for the Read tool."""
    _, files = rs.load_system(sysdef)
    if not files:
        raise SystemExit("%s has no skill files: a prompt baseline runs through the API" % sysdef["name"])
    if READ_API not in rs.PREAMBLE:
        raise SystemExit("run_systems.PREAMBLE changed: update READ_API in batches.py")
    preamble = rs.PREAMBLE.replace(READ_API, READ_SUBAGENT % skill_dir.as_posix())
    others = [f for f in files if f != "SKILL.md"]
    return preamble.format(files=", ".join(["SKILL.md"] + others), skill=files["SKILL.md"].strip()), files


def prepare_run(sysdefs: list, batches: list, batch_root: Path, run_dir: Path, texts_dir: Path, executor: str) -> list:
    """Write everything the executor subagents need; return the instruction files."""
    ids = [t for b in batches for t in b]
    if len(ids) != len(set(ids)):
        raise SystemExit("a text is in two batches")
    req_dir = batch_root / "requests"
    for tid in ids:
        lib.write_text(req_dir / (tid + ".txt"), rs.REQUEST + lib.read_text(texts_dir / (tid + ".txt")))
    tasks = []
    for sysdef in sysdefs:
        sdir = batch_root / sysdef["name"]
        system, files = subagent_system(sysdef, sdir / "skill")
        for rel, body in files.items():
            lib.write_text(sdir / "skill" / rel, body)
        lib.write_text(sdir / "system.txt", system)
        out_dir = run_dir / "outputs" / sysdef["name"]
        for k, batch in enumerate(batches, 1):
            items = "\n".join("   - request: %s -> answer file: %s" % ((req_dir / (t + ".txt")).as_posix(),
                                                                        (out_dir / (t + ".txt")).as_posix()) for t in batch)
            task = sdir / ("batch%d.task.txt" % k)
            lib.write_text(task, EXECUTOR_TASK.format(system=(sdir / "system.txt").as_posix(), items=items, n=len(batch)))
            tasks.append(task)
        print("[M-EVAL-BATCH][prepare_run] %s: %d skill files, %d batches" % (sysdef["name"], len(files), len(batches)))
    lib.write_json(run_dir / "config.json", {"executor": executor, "texts": ids, "systems": [s["name"] for s in sysdefs],
                                             "request": rs.REQUEST, "batches": batches})
    return tasks


def collect_run(run_dir: Path) -> list:
    """Check and record the subagents' outputs; return the missing or empty ones as system/id."""
    cfg = lib.read_json(run_dir / "config.json")
    missing, rows = [], []
    for s in cfg["systems"]:
        for k, batch in enumerate(cfg["batches"], 1):
            for tid in batch:
                f = run_dir / "outputs" / s / (tid + ".txt")
                text = lib.read_text(f).replace("\r\n", "\n").strip() if f.exists() else ""
                if len(text) < 20:
                    missing.append("%s/%s" % (s, tid))
                    continue
                # Same shape as the API runner writes: stripped answer plus one newline.
                lib.write_text(f, text + "\n")
                rows.append({"system": s, "id": tid, "batch": k, "executor": cfg["executor"], "chars": len(text)})
    lib.write_text(run_dir / "runs.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print("[M-EVAL-BATCH][collect_run] outputs=%d missing=%d" % (len(rows), len(missing)))
    return missing
# END_BLOCK_EXECUTOR


# START_BLOCK_JUDGE
def prepare_judge(run_dir: Path, texts_dir: Path, batch_root: Path, judge: str, ids: list, batch_size: int) -> list:
    """Blinded bundles in judge.py's format (same PROMPT, same shuffle by judge name and round 0)."""
    out_dir = run_dir / "outputs"
    systems = sorted(p.name for p in out_dir.iterdir() if p.is_dir())
    lack = ["%s/%s" % (s, t) for t in ids for s in systems if not (out_dir / s / (t + ".txt")).exists()]
    if lack:
        raise SystemExit("outputs missing: %s" % ", ".join(lack))
    jdir = batch_root / ("judge-" + _slug(judge))
    keys = {}
    for tid in ids:
        outputs = {s: lib.read_text(out_dir / s / (tid + ".txt")) for s in systems}
        block, key = jg.build(tid, outputs, judge, 0)
        source = lib.read_text(texts_dir / (tid + ".txt")).strip()
        lib.write_text(jdir / "bundles" / (tid + ".md"), jg.PROMPT.format(n=len(key), source=source, candidates=block))
        keys[tid] = key
    # The label key sits next to the judge folder, not in it: the subagent reads only its bundles.
    lib.write_json(batch_root / ("judge-%s-keys.json" % _slug(judge)), keys)
    tasks = []
    for k in range(0, len(ids), batch_size):
        part = ids[k:k + batch_size]
        items = "\n".join("- %s -> answer file: %s" % ((jdir / "bundles" / (t + ".md")).as_posix(),
                                                        (jdir / "answers" / (t + ".json")).as_posix()) for t in part)
        task = jdir / ("batch%d.task.txt" % (k // batch_size + 1))
        lib.write_text(task, JUDGE_TASK.format(items=items, n=len(part)))
        tasks.append(task)
    print("[M-EVAL-BATCH][prepare_judge] %s: %d texts, %d systems, %d batches" % (judge, len(ids), len(systems), len(tasks)))
    return tasks


def collect_judge(run_dir: Path, batch_root: Path, judge: str, out: str = "judgments.jsonl") -> dict:
    """Parse the subagent's answers and append new rows; a text with a valid row is not added twice."""
    jdir = batch_root / ("judge-" + _slug(judge))
    keys = lib.read_json(batch_root / ("judge-%s-keys.json" % _slug(judge)))
    log = run_dir / out
    done = set()
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("ranking"):
                done.add((row["id"], row["judge"], row["round"], tuple(sorted(row["key"].values()))))
    result = {"added": 0, "errors": [], "missing": []}
    rows = []
    for tid, key in keys.items():
        f = jdir / "answers" / (tid + ".json")
        if not f.exists():
            result["missing"].append(tid)
            continue
        if (tid, judge, 0, tuple(sorted(key.values()))) in done:
            continue
        row = jg.to_row(tid, judge, 0, key, lib.read_text(f))
        row["cost"] = 0.0
        rows.append(row)
        if not row.get("ranking"):
            result["errors"].append(tid)
    with open(log, "a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    result["added"] = len(rows)
    print("[M-EVAL-BATCH][collect_judge] %s added=%d errors=%s missing=%s" % (judge, len(rows), result["errors"], result["missing"]))
    return result
# END_BLOCK_JUDGE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare-run", "collect-run", "prepare-judge", "collect-judge"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--systems", default="", help="prepare-run: comma list from systems.json")
    ap.add_argument("--batches", default="", help="prepare-run: batches split by ';', ids by ','")
    ap.add_argument("--executor", default="anthropic/claude-sonnet-5.5 (Claude Code subagent)")
    ap.add_argument("--judge", default="", help="judge label recorded in judgments.jsonl")
    ap.add_argument("--texts", default="", help="prepare-judge: comma list of ids")
    ap.add_argument("--batch-size", type=int, default=6)
    args = ap.parse_args()
    run_dir = lib.EVAL_DIR / "results" / args.run
    batch_root = lib.CACHE_DIR / "batch" / args.run
    texts_dir = lib.EVAL_DIR / "corpus" / "texts"
    if args.action == "prepare-run":
        names = args.systems.split(",")
        sysdefs = [s for s in lib.read_json(lib.EVAL_DIR / "systems.json") if s["name"] in names]
        batches = [b.split(",") for b in args.batches.split(";")]
        for task in prepare_run(sysdefs, batches, batch_root, run_dir, texts_dir, args.executor):
            print(task.as_posix())
    elif args.action == "collect-run":
        missing = collect_run(run_dir)
        if missing:
            print("missing:", ", ".join(missing))
            return 1
    elif args.action == "prepare-judge":
        for task in prepare_judge(run_dir, texts_dir, batch_root, args.judge, args.texts.split(","), args.batch_size):
            print(task.as_posix())
    else:
        res = collect_judge(run_dir, batch_root, args.judge)
        return 1 if res["errors"] or res["missing"] else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
