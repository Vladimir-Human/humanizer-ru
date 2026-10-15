#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Run every compared system on every corpus text with one executor model, the way an
#          agent uses a triggered skill: SKILL.md in the system prompt, other skill files
#          readable through a read_file tool, scripts unavailable. Same user request for all.
# SCOPE: writes eval/results/<run>/outputs/<system>/<id>.txt and runs.jsonl; resumable.
# DEPENDS: evallib (chat, ledger), eval/systems.json, eval/corpus/index.json + texts,
#          eval/.cache/systems/<name>/ (fetch_systems.py) and skills/humanizer-ru for "ours".
# LINKS: M-EVAL-RUN; DF-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# REQUEST: the user message shared by all systems.
# load_system: system prompt + readable files for one system.
# run_one: tool loop (read_file) until a final answer; returns text and metadata.
# main: CLI --run --set --systems --texts --executor --workers.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import evallib as lib

REPO = lib.EVAL_DIR.parent
REQUEST = "Очеловечь этот текст. В ответе дай только готовый текст, без пояснений и комментариев.\n\n"
PREAMBLE = (
    "Ты — ИИ-ассистент в агентной среде вроде Claude Code. У пользователя установлен навык "
    "(Agent Skill) из папки skill/. Запрос пользователя вызвал этот навык; ниже его основной файл "
    "SKILL.md. Следуй инструкциям навыка.\n"
    "Файлы навыка: {files}. Любой из них можно прочитать инструментом read_file "
    "(путь относительно папки skill/). Скрипты навыка в этой среде запустить нельзя: если навык "
    "предлагает проверку скриптом, сделай её сам.\n\n<SKILL.md>\n{skill}\n</SKILL.md>"
)
TOOLS = [{"type": "function", "function": {
    "name": "read_file",
    "description": "Read a file of the installed skill by its path relative to the skill folder.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]


def load_system(sysdef: dict):
    if sysdef["kind"] == "prompt":
        return sysdef["system"], {}
    root = REPO / sysdef["path"] if sysdef["kind"] == "local" else lib.CACHE_DIR / "systems" / sysdef["name"]
    files = {}
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        files[rel] = p.read_text(encoding="utf-8")
    skill = files.get("SKILL.md")
    if skill is None:
        raise SystemExit("no SKILL.md for %s in %s" % (sysdef["name"], root))
    others = [f for f in files if f != "SKILL.md"]
    system = PREAMBLE.format(files=", ".join(["SKILL.md"] + others), skill=skill.strip())
    return system, files


# START_CONTRACT: run_one
# PURPOSE: One executor conversation for (system, text) with a bounded read_file tool loop.
# INPUTS: executor model id, system prompt, readable files, source text.
# OUTPUTS: (final text, meta dict: steps, files_read, cost, tokens).
# SIDE_EFFECTS: API calls booked in the ledger under tag "run".
# END_CONTRACT: run_one
def run_one(model: str, system: str, files: dict, text: str):
    sys_msg = {"role": "system", "content": [{"type": "text", "text": system,
                                               "cache_control": {"type": "ephemeral"}}]}
    messages = [sys_msg, {"role": "user", "content": REQUEST + text}]
    meta = {"steps": 0, "files_read": [], "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
    for _ in range(8):
        msg, usage = lib.chat(model, messages, tools=TOOLS if files else None, max_tokens=16000, tag="run")
        meta["steps"] += 1
        meta["cost"] += float(usage.get("cost") or 0)
        meta["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        meta["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip() + "\n", meta
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            try:
                path = json.loads(call["function"].get("arguments") or "{}").get("path", "")
            except json.JSONDecodeError:
                path = ""
            path = path.replace("\\", "/").lstrip("./").removeprefix("skill/")
            meta["files_read"].append(path)
            body = files.get(path, "Файл не найден. Доступны: " + ", ".join(sorted(files)))
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": body})
    raise RuntimeError("tool loop did not finish")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--set", default="test", choices=["dev", "test", "holdout", "all"])
    ap.add_argument("--systems", default="")
    ap.add_argument("--texts", default="")
    ap.add_argument("--executor", default="anthropic/claude-sonnet-5.5")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    index = lib.read_json(lib.EVAL_DIR / "corpus" / "index.json")
    # Traps (human and legal texts) belong to every public comparison, the holdout one included.
    ids = [t["id"] for t in index if args.set == "all" or t["set"] == args.set
           or (args.set == "holdout" and t["kind"] == "trap")]
    if args.texts:
        ids = [i for i in ids if i in args.texts.split(",")]
    systems = lib.read_json(lib.EVAL_DIR / "systems.json")
    if args.systems:
        systems = [s for s in systems if s["name"] in args.systems.split(",")]
    run_dir = lib.EVAL_DIR / "results" / args.run
    lib.write_json(run_dir / "config.json", {"executor": args.executor, "set": args.set, "texts": ids,
                                             "systems": [s["name"] for s in systems], "request": REQUEST})
    log = run_dir / "runs.jsonl"

    for sysdef in systems:
        system, files = load_system(sysdef)
        todo = [i for i in ids if not (run_dir / "outputs" / sysdef["name"] / (i + ".txt")).exists()]

        def work(tid, sysdef=sysdef, system=system, files=files):
            src = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (tid + ".txt"))
            try:
                # An empty final message is a harness failure, not the skill's answer: retry once.
                for attempt in range(2):
                    out, meta = run_one(args.executor, system, files, src)
                    meta["attempts"] = attempt + 1
                    if len(out.strip()) >= 20:
                        break
                else:
                    raise RuntimeError("empty answer twice")
            except lib.BudgetExceeded:
                raise
            except Exception as exc:  # keep going; the gap shows up in the report
                return tid, None, {"error": repr(exc)[:300]}
            lib.write_text(run_dir / "outputs" / sysdef["name"] / (tid + ".txt"), out)
            return tid, out, meta

        # First text alone so the prompt cache is written before the parallel calls read it.
        batches = [todo[:1], todo[1:]]
        for batch in batches:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for tid, out, meta in pool.map(work, batch):
                    meta.update({"system": sysdef["name"], "id": tid})
                    with open(log, "a", encoding="utf-8", newline="\n") as fh:
                        fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
                    print("%-9s %s %s $%.4f files=%s" % (sysdef["name"], tid, "ERR " + meta["error"] if out is None else "ok",
                                                        meta.get("cost", 0), ",".join(meta.get("files_read", []))))
    print("spend so far $%.4f" % lib.ledger().data["total"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
