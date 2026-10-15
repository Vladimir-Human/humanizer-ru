#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Turn judgments and fact checks into the comparison table and the pass/fail verdict
#          against the usefulness thresholds of the remake.
# SCOPE: reads eval/results/<run>/{outputs,judgments.jsonl}; writes summary.md and summary.json.
# DEPENDS: evallib; skills/humanizer-ru/scripts/check_facts.py (imported by path).
# LINKS: M-EVAL-REPORT; DF-EVAL; V-M-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load: judgments with a valid ranking, corpus index, outputs.
# aggregate: per-system positions, first places, pairwise wins, send_as_is, fact flags.
# thresholds: the four usefulness criteria for "ours".
# render: Markdown summary.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import sys
from collections import Counter, defaultdict

import evallib as lib

REPO = lib.EVAL_DIR.parent
_spec = importlib.util.spec_from_file_location("check_facts", REPO / "skills/humanizer-ru/scripts/check_facts.py")
check_facts = importlib.util.module_from_spec(_spec)
sys.modules["check_facts"] = check_facts  # dataclasses look the module up while the class is built
_spec.loader.exec_module(check_facts)


def aggregate(rows, ids, outputs, sources):
    systems = sorted({s for r in rows for s in r["ranking"]})
    pos = defaultdict(list)
    first = defaultdict(int)
    wins = defaultdict(lambda: [0, 0])  # (a, b) -> [a above b, comparisons]
    send = defaultdict(list)
    fact_votes = defaultdict(lambda: [0, 0])  # (system, id) -> [passes with errors, passes]
    fact_notes = defaultdict(list)
    for r in rows:
        if r["id"] not in ids:
            continue
        rank = r["ranking"]
        for i, s in enumerate(rank):
            pos[s].append(i + 1)
        first[rank[0]] += 1
        for i, a in enumerate(rank):
            for b in rank[i + 1:]:
                wins[(a, b)][0] += 1
                wins[(a, b)][1] += 1
                wins[(b, a)][1] += 1
        for s, c in (r.get("candidates") or {}).items():
            if isinstance(c.get("send_as_is"), (int, float)):
                send[s].append(float(c["send_as_is"]))
            errs = [e for e in (c.get("fact_errors") or []) if str(e).strip() and str(e).strip().lower() not in ("нет", "-", "—")]
            fact_votes[(s, r["id"])][1] += 1
            if errs:
                fact_votes[(s, r["id"])][0] += 1
                fact_notes[(s, r["id"])].append("; ".join(map(str, errs)))
    script = {}
    for s in systems:
        for tid in ids:
            out = outputs.get((s, tid))
            if out is None:
                continue
            res = check_facts.compare(sources[tid], out)
            script[(s, tid)] = res["errors"]
    table = {}
    for s in systems:
        flagged = [tid for tid in ids if fact_votes[(s, tid)][1] and
                   fact_votes[(s, tid)][0] * 2 >= fact_votes[(s, tid)][1] and fact_votes[(s, tid)][0] >= 2]
        table[s] = {
            "mean_position": round(sum(pos[s]) / len(pos[s]), 2) if pos[s] else None,
            "first_places": first[s],
            "passes": len(pos[s]),
            "send_as_is": round(sum(send[s]) / len(send[s]), 2) if send[s] else None,
            "texts_with_fact_errors": flagged,
            "script_errors": {tid: e for (ss, tid), e in script.items() if ss == s and e},
            "similarity": round(sum(difflib.SequenceMatcher(None, sources[t], outputs[(s, t)]).ratio()
                                    for t in ids if (s, t) in outputs) / max(1, sum(1 for t in ids if (s, t) in outputs)), 3),
        }
    pair = {"%s>%s" % k: round(v[0] / v[1], 3) for k, v in wins.items() if v[1]}
    notes = {"%s|%s" % k: v for k, v in fact_notes.items()}
    return table, pair, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--ours", default="ours")
    ap.add_argument("--baseline", default="prompt")
    ap.add_argument("--judgments", default="judgments.jsonl")
    args = ap.parse_args()
    run_dir = lib.EVAL_DIR / "results" / args.run
    index = {t["id"]: t for t in lib.read_json(lib.EVAL_DIR / "corpus" / "index.json")}
    rows = [json.loads(l) for l in (run_dir / args.judgments).read_text(encoding="utf-8").splitlines() if l.strip()]
    errors = [r for r in rows if not r.get("ranking")]
    rows = [r for r in rows if r.get("ranking")]
    outputs, sources = {}, {}
    for d in (run_dir / "outputs").iterdir():
        for f in d.glob("*.txt"):
            outputs[(d.name, f.stem)] = lib.read_text(f)
    all_ids = sorted({r["id"] for r in rows})
    for tid in all_ids:
        sources[tid] = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (tid + ".txt"))
    groups = {
        "ai": [t for t in all_ids if index[t]["kind"] in ("generated", "real")],
        "trap": [t for t in all_ids if index[t]["kind"] == "trap"],
    }
    # Coverage: every text of the run must have the same number of valid judge passes,
    # otherwise the thresholds are reported as unverified instead of passed.
    cfg = lib.read_json(run_dir / "config.json") if (run_dir / "config.json").exists() else {}
    expected = cfg.get("texts") or all_ids
    passes = Counter(r["id"] for r in rows)
    full = max(passes.values()) if passes else 0
    gaps = sorted(t for t in expected if passes.get(t, 0) < full)
    result = {"run": args.run, "judge_errors": len(errors), "groups": {}, "coverage_gaps": gaps}
    md = ["# Итоги сравнения: %s" % args.run, ""]
    if gaps:
        md += ["**Неполное покрытие:** у текстов %s меньше %d оценок; пороги ниже не проверены." % (", ".join(gaps), full), ""]
    cfg_path = run_dir / "config.json"
    if cfg_path.exists():
        cfg = lib.read_json(cfg_path)
        md.append("Исполнитель: `%s`. Судьи: %s. Проходов судей с ответом: %d, без ответа: %d." % (
            cfg.get("executor"), ", ".join(sorted({r["judge"] for r in rows})), len(rows), len(errors)))
        md.append("")
    for gname, ids in groups.items():
        if not ids:
            continue
        table, pair, notes = aggregate(rows, set(ids), outputs, sources)
        result["groups"][gname] = {"ids": ids, "table": table, "pairwise": pair, "fact_notes": notes}
        title = "ИИ-тексты" if gname == "ai" else "Ловушки (человеческие тексты и закон)"
        md += ["## %s: %d текстов" % (title, len(ids)), "",
               "| Система | Среднее место | 1-е места | Готов к отправке, 1–10 | Тексты с ошибкой фактов (судьи) | Ошибки скрипта сверки | Сходство с исходником |",
               "|---|---|---|---|---|---|---|"]
        for s in sorted(table, key=lambda x: table[x]["mean_position"] or 99):
            t = table[s]
            md.append("| %s | %s | %d из %d | %s | %d | %d | %.2f |" % (
                s, t["mean_position"], t["first_places"], t["passes"], t["send_as_is"],
                len(t["texts_with_fact_errors"]), len(t["script_errors"]), t["similarity"]))
        md.append("")
        if args.ours in table:
            md.append("Доля проходов, где `%s` выше соперника:" % args.ours)
            md.append("")
            for s in sorted(table):
                if s != args.ours and ("%s>%s" % (args.ours, s)) in pair:
                    md.append("- %s: %.0f%%" % (s, 100 * pair["%s>%s" % (args.ours, s)]))
            md.append("")
    # Thresholds for ours (AI texts + traps).
    ai = result["groups"].get("ai", {})
    tr = result["groups"].get("trap", {})
    if ai and args.ours in ai["table"]:
        t = ai["table"][args.ours]
        competitors = [s for s in ai["table"] if s not in (args.ours, args.baseline, "old_v3")]
        best = max(competitors, key=lambda s: -ai["table"][s]["mean_position"]) if competitors else None
        n_err = len(t["texts_with_fact_errors"]) + (len(tr["table"][args.ours]["texts_with_fact_errors"]) if tr else 0)
        checks = [
            ("Ошибок фактов не больше 1 на весь корпус (по большинству судей)", n_err <= 1, "%d" % n_err),
            ("Выше простой просьбы хотя бы в 60% проходов", ai["pairwise"].get("%s>%s" % (args.ours, args.baseline), 0) >= 0.6,
             "%.0f%%" % (100 * ai["pairwise"].get("%s>%s" % (args.ours, args.baseline), 0))),
        ]
        if best:
            share = ai["pairwise"].get("%s>%s" % (args.ours, best), 0)
            checks.append(("Не хуже лучшего конкурента (%s): не меньше 50%%" % best, share >= 0.5, "%.0f%%" % (100 * share)))
        if tr and args.ours in tr["table"]:
            tt = tr["table"][args.ours]
            ok_traps = sum(1 for tid in tr["ids"] if tid not in tt["texts_with_fact_errors"])
            checks.append(("Ловушки: без ошибок фактов хотя бы 5 из 6", ok_traps >= 5, "%d из %d" % (ok_traps, len(tr["ids"]))))
        md += ["## Пороги полезности", "", "| Условие | Итог | Значение |", "|---|---|---|"]
        for name, ok, val in checks:
            verdict = "не проверено" if gaps else ("выполнено" if ok else "не выполнено")
            md.append("| %s | %s | %s |" % (name, verdict, val))
        md.append("")
        result["thresholds"] = [{"name": n, "ok": (None if gaps else ok), "value": v} for n, ok, v in checks]
    md.append("Расходы на API за все прогоны: $%.2f." % lib.ledger().data["total"])
    lib.write_text(run_dir / "summary.md", "\n".join(md) + "\n")
    lib.write_json(run_dir / "summary.json", result)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
