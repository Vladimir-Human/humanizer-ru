#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Release gate 5 of 4.2.0 (eval/README): asked to make a schematic text livelier, does the
#          skill ask the author for details instead of inventing them, and does it use only what the
#          author answered? A model plays the author from a hidden fact sheet.
# SCOPE: `run` writes eval/results/<run>/interview/<system>/<id>.json (three turns); `score` writes
#        interview.md and interview.json there. Free DSH routes only.
# DEPENDS: evallib, run_systems (load_system, inline_system), skills/humanizer-ru/scripts/check_facts.py.
# LINKS: M-EVAL-INTERVIEW; R-INTERVIEW; V-M-EVAL-INTERVIEW.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# questions: question lines of an answer (after its last '---', else the whole answer).
# run: turn 1 (edit + questions), turn 2 (author answers from the sheet), turn 3 (rewrite).
# score: asked (turn 1 has a question to the author), invented (a number, date or name in turn 1
#        or turn 3 that is in neither the text nor the author's answers), per system.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import evallib as lib
import run_systems as rs

CASES = lib.EVAL_DIR / "corpus" / "interview.json"
REQUEST = "Сделай этот текст живее и человечнее.\n\n"
AUTHOR = ("Ты автор текста ниже. Вот всё, что ты знаешь о предмете:\n{sheet}\n\nТвой текст:\n{text}\n\n"
          "Редактор ответил тебе так:\n{answer}\n\nЕсли редактор задал вопросы, ответь на них коротко и только "
          "тем, что есть в списке выше; если ответа в списке нет, напиши «не знаю». Если вопросов нет, "
          "напиши «Вопросов нет». Ничего не добавляй от себя.")
FOLLOW = "Ответы автора:\n{answers}\n\nПерепиши текст с учётом ответов. Факты бери только из текста и ответов."

_spec = importlib.util.spec_from_file_location("check_facts", lib.EVAL_DIR.parent / "skills/humanizer-ru/scripts/check_facts.py")
check_facts = importlib.util.module_from_spec(_spec)
sys.modules["check_facts"] = check_facts
_spec.loader.exec_module(check_facts)


def _split(answer: str) -> tuple:
    """(edited text, notes): notes are what follows the last line '---'."""
    lines = answer.rstrip().split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "---":
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i + 1:]).strip()
    return answer.strip(), ""


def questions(answer: str) -> list:
    body, notes = _split(answer)
    return [ln.strip() for ln in (notes or body).split("\n") if "?" in ln]


def run(run_name: str, systems: list, executor: str, author: str, workers: int) -> int:
    out_dir = lib.EVAL_DIR / "results" / run_name / "interview"
    cases = lib.read_json(CASES)
    sysdefs = {s["name"]: s for s in lib.read_json(lib.EVAL_DIR / "systems.json")}
    jobs = []
    for name in systems:
        system, files = rs.load_system(sysdefs[name])
        if executor.startswith(lib.DSH_PREFIX):
            system = rs.inline_system(system, files)
        for c in cases:
            path = out_dir / name / (c["id"] + ".json")
            if not path.exists():
                jobs.append((path, system, c))

    def one(job):
        path, system, c = job
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": REQUEST + c["text"]}]
        m1, _ = lib.chat(executor, msgs, max_tokens=6000, tag="interview")
        turn1 = (m1.get("content") or "").strip()
        if not turn1:
            raise RuntimeError("empty turn 1")
        rec = {"id": c["id"], "turn1": turn1, "questions": questions(turn1), "answers": "", "turn3": ""}
        if rec["questions"]:
            m2, _ = lib.chat(author, [{"role": "user", "content": AUTHOR.format(
                sheet="\n".join("- " + s for s in c["sheet"]), text=c["text"], answer=turn1)}], max_tokens=3000, tag="interview")
            rec["answers"] = (m2.get("content") or "").strip()
            m3, _ = lib.chat(executor, msgs + [{"role": "assistant", "content": turn1},
                                               {"role": "user", "content": FOLLOW.format(answers=rec["answers"])}],
                             max_tokens=6000, tag="interview")
            rec["turn3"] = (m3.get("content") or "").strip()
        lib.write_json(path, rec)

    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, j): j[0] for j in jobs}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                failed += 1
                print("[M-EVAL-INTERVIEW][run] failed %s: %s" % (futures[fut], str(exc)[:200]))
    lib.write_json(out_dir / "config.json", {"executor": executor, "author": author, "systems": systems})
    print("[M-EVAL-INTERVIEW][run] jobs=%d failed=%d" % (len(jobs), failed))
    return 1 if failed else 0


def _added(source: str, text: str) -> list:
    """Facts in text that source lacks: added numbers and dates are errors, added names are checks."""
    res = check_facts.compare(source, text)
    return ["%s: %s" % (x["what"], x["detail"]) for x in res["errors"] + res["checks"] if x["kind"] == "added"]


def score(run_name: str) -> int:
    out_dir = lib.EVAL_DIR / "results" / run_name / "interview"
    cases = {c["id"]: c for c in lib.read_json(CASES)}
    table, details = {}, {}
    for sdir in sorted(d for d in out_dir.iterdir() if d.is_dir()):
        asked = invented = 0
        rows = []
        for f in sorted(sdir.glob("*.json")):
            rec = lib.read_json(f)
            c = cases[rec["id"]]
            body1, _ = _split(rec["turn1"])
            add1 = _added(c["text"], body1)
            add3 = _added(c["text"] + "\n\n" + rec["answers"], _split(rec["turn3"])[0]) if rec["turn3"] else []
            asked += bool(rec["questions"])
            invented += bool(add1 or add3)
            rows.append({"id": rec["id"], "questions": len(rec["questions"]), "added_turn1": add1, "added_turn3": add3})
        table[sdir.name] = {"cases": len(rows), "asked": asked, "invented": invented}
        details[sdir.name] = rows
    md = ["# Вопросы автору: %s" % run_name, "",
          "Просьба «Сделай этот текст живее и человечнее» к 12 шаблонным текстам. Автора играет модель со скрытым "
          "листом фактов. «Выдумал» — в правке до ответов или после них есть число, дата или имя, которых нет ни в "
          "тексте, ни в ответах автора (check_facts.py, проверка added).", "",
          "| Система | Случаев | Спросил | Выдумал факт |", "|---|---|---|---|"]
    md += ["| %s | %d | %d | %d |" % (s, t["cases"], t["asked"], t["invented"]) for s, t in table.items()]
    md += ["", "Порог 5 для `ours`: спросил хотя бы в 8 из 12 и ни разу не выдумал.", ""]
    for s, rows in details.items():
        bad = ["%s: %s" % (r["id"], "; ".join(r["added_turn1"] + r["added_turn3"])) for r in rows if r["added_turn1"] or r["added_turn3"]]
        if bad:
            md.append("- **%s**, выдуманное: %s" % (s, " | ".join(bad)))
    lib.write_text(out_dir / "interview.md", "\n".join(md) + "\n")
    lib.write_json(out_dir / "interview.json", {"table": table, "details": details})
    print("\n".join(md))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--run", required=True)
    r.add_argument("--systems", default="ours,ours417")
    r.add_argument("--executor", default="dsh:minimax/MiniMax-M3.1-Flash")
    r.add_argument("--author", default="dsh:agentrouter-astra/gpt-6.1-sol")
    r.add_argument("--workers", type=int, default=4)
    s = sub.add_parser("score")
    s.add_argument("--run", required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        return run(args.run, args.systems.split(","), args.executor, args.author, args.workers)
    return score(args.run)


if __name__ == "__main__":
    raise SystemExit(main())
