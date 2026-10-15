#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Turn judgments and fact checks into the comparison table and the pass/fail verdict
#          against the usefulness thresholds of the remake.
# SCOPE: reads eval/results/<run>/{outputs,judgments.jsonl}; writes summary.md and summary.json
#        (--out renames them; --judges keeps only the passes of the named judges).
# DEPENDS: evallib; skills/humanizer-ru/scripts/check_facts.py (imported by path).
# LINKS: M-EVAL-REPORT; DF-EVAL; V-M-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load: judgments with a valid ranking, corpus index, outputs.
# aggregate: per-system positions, first places, pairwise wins, send_as_is, fact flags.
# fact_flag: one vote per judge, the error counts on a majority of judges.
# thresholds: usefulness criteria for "ours" (rule set 2, see README).
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


def _equal_weight(per_judge: dict):
    """Mean of per-judge means: every judge (lab) weighs the same, however many passes it made."""
    means = [sum(v) / len(v) for v in per_judge.values() if v]
    return sum(means) / len(means) if means else None


# START_CONTRACT: fact_flag
# PURPOSE: Decide whether a (system, text) has a meaning error from the judges' passes.
# INPUTS: {judge: [flagged passes, all passes]} for one system output.
# OUTPUTS: (majority: bool, any_judge: bool).
# RULE: a judge votes "error" when it flagged at least half of its passes; the error counts
#       when a strict majority of judges vote so (2 of 3, both of 2). With one judge only
#       (selection runs) the old pass rule applies: at least half of the passes and at least 2.
# END_CONTRACT: fact_flag
def fact_flag(votes: dict):
    voted = [j for j, (bad, n) in votes.items() if n and bad * 2 >= n]
    if len(votes) == 1:
        bad, n = next(iter(votes.values()))
        return bool(n and bad * 2 >= n and bad >= 2), bool(voted)
    return len(voted) * 2 > len(votes), bool(voted)


def aggregate(rows, ids, outputs, sources):
    systems = sorted({s for r in rows for s in r["ranking"]})
    pos = defaultdict(lambda: defaultdict(list))  # system -> judge -> positions
    first = defaultdict(int)
    wins = defaultdict(lambda: defaultdict(list))  # (a, b) -> judge -> [1 if a above b else 0]
    send = defaultdict(lambda: defaultdict(list))
    fact_votes = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # (system, id) -> judge -> [flagged, passes]
    fact_notes = defaultdict(list)
    for r in rows:
        if r["id"] not in ids:
            continue
        rank, judge = r["ranking"], r["judge"]
        for i, s in enumerate(rank):
            pos[s][judge].append(i + 1)
        first[rank[0]] += 1
        for i, a in enumerate(rank):
            for b in rank[i + 1:]:
                wins[(a, b)][judge].append(1)
                wins[(b, a)][judge].append(0)
        for s, c in (r.get("candidates") or {}).items():
            if isinstance(c.get("send_as_is"), (int, float)):
                send[s][judge].append(float(c["send_as_is"]))
            errs = [e for e in (c.get("fact_errors") or []) if str(e).strip() and str(e).strip().lower() not in ("нет", "-", "—")]
            fact_votes[(s, r["id"])][judge][1] += 1
            if errs:
                fact_votes[(s, r["id"])][judge][0] += 1
                fact_notes[(s, r["id"])].append("%s: %s" % (judge.split("/")[-1], "; ".join(map(str, errs))))
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
        flags = {tid: fact_flag(fact_votes[(s, tid)]) for tid in ids if (s, tid) in fact_votes}
        mean_pos, mean_send = _equal_weight(pos[s]), _equal_weight(send[s])
        table[s] = {
            "mean_position": round(mean_pos, 2) if mean_pos is not None else None,
            "first_places": first[s],
            "passes": sum(len(v) for v in pos[s].values()),
            "send_as_is": round(mean_send, 2) if mean_send is not None else None,
            "texts_with_fact_errors": sorted(t for t, (major, _) in flags.items() if major),
            "texts_flagged_by_any_judge": sorted(t for t, (_, anyj) in flags.items() if anyj),
            "script_errors": {tid: e for (ss, tid), e in script.items() if ss == s and e},
            "similarity": round(sum(difflib.SequenceMatcher(None, sources[t], outputs[(s, t)]).ratio()
                                    for t in ids if (s, t) in outputs) / max(1, sum(1 for t in ids if (s, t) in outputs)), 3),
        }
    pair = {"%s>%s" % k: round(_equal_weight(v), 3) for k, v in wins.items() if _equal_weight(v) is not None}
    notes = {"%s|%s" % k: v for k, v in fact_notes.items()}
    return table, pair, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--ours", default="ours")
    ap.add_argument("--baseline", default="prompt")
    ap.add_argument("--prev", default="ours410", help="previous version of ours, if it is in the run")
    ap.add_argument("--judgments", default="judgments.jsonl")
    ap.add_argument("--judges", default="", help="only passes of these judges (comma list of model ids)")
    ap.add_argument("--out", default="summary", help="file name without extension for .md and .json")
    args = ap.parse_args()
    if args.judges and args.out == "summary":
        # A one-judge view must never overwrite the run's main summary.
        args.out = "summary-" + "-".join(j.split("/")[-1] for j in args.judges.split(","))
    run_dir = lib.EVAL_DIR / "results" / args.run
    index = {t["id"]: t for t in lib.read_json(lib.EVAL_DIR / "corpus" / "index.json")}
    rows = [json.loads(l) for l in (run_dir / args.judgments).read_text(encoding="utf-8").splitlines() if l.strip()]
    errors = [r for r in rows if not r.get("ranking")]
    rows = [r for r in rows if r.get("ranking")]
    if args.judges:
        keep = set(args.judges.split(","))
        errors = [r for r in errors if r["judge"] in keep]
        rows = [r for r in rows if r["judge"] in keep]
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
               "| Система | Среднее место | 1-е места | Готов к отправке, 1–10 | Тексты с ошибкой смысла (большинство судей) | Отметил хоть один судья | Ошибки скрипта сверки | Сходство с исходником |",
               "|---|---|---|---|---|---|---|---|"]
        for s in sorted(table, key=lambda x: table[x]["mean_position"] or 99):
            t = table[s]
            md.append("| %s | %s | %d из %d | %s | %d | %d | %d | %.2f |" % (
                s, t["mean_position"], t["first_places"], t["passes"], t["send_as_is"],
                len(t["texts_with_fact_errors"]), len(t["texts_flagged_by_any_judge"]),
                len(t["script_errors"]), t["similarity"]))
        md.append("")
        md.append("Среднее место и доли считаются у каждого судьи отдельно, затем усредняются: у каждого "
                  "судьи один голос, сколько бы проходов он ни сделал.")
        md.append("")
        if args.ours in table:
            md.append("Доля сравнений, где `%s` выше соперника:" % args.ours)
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
        errs = {s: len(v["texts_with_fact_errors"]) for s, v in ai["table"].items()}
        others = [s for s in ai["table"] if s not in (args.ours, args.prev)]
        competitors = [s for s in others if s not in (args.baseline, "old_v3")]
        best = max(competitors, key=lambda s: -ai["table"][s]["mean_position"]) if competitors else None
        careful = min(others, key=lambda s: errs[s]) if others else None
        n_err = errs[args.ours]
        # Rule set 2 (fixed on 15.10.2026 before the holdout2 texts existed): one error text
        # per 12 AI texts at most, and no more than the most careful other participant.
        limit = max(1, len(ai["ids"]) // 12)
        ok_err = n_err <= limit and (careful is None or n_err <= errs[careful])
        cmp = ", и не больше, чем у самого аккуратного из остальных (%s: %d)" % (careful, errs[careful]) if careful else ""
        checks = [("Тексты с ошибкой смысла (большинство судей): не больше %d на %d ИИ-текстов%s"
                   % (limit, len(ai["ids"]), cmp), ok_err, "%d" % n_err)]
        if args.baseline in ai["table"]:
            share = ai["pairwise"].get("%s>%s" % (args.ours, args.baseline), 0)
            checks.append(("Выше простой просьбы хотя бы в 60% сравнений", share >= 0.6, "%.0f%%" % (100 * share)))
        else:
            # A tuning run without the baseline must not look as if this threshold had failed or passed.
            checks.append(("Выше простой просьбы хотя бы в 60% сравнений", None, "просьбы в прогоне нет"))
        if best:
            share = ai["pairwise"].get("%s>%s" % (args.ours, best), 0)
            checks.append(("Не хуже лучшего конкурента (%s): не меньше 50%%" % best, share >= 0.5, "%.0f%%" % (100 * share)))
        if args.prev in ai["table"]:
            share = ai["pairwise"].get("%s>%s" % (args.ours, args.prev), 0)
            checks.append(("Не хуже прошлой версии (%s): не меньше 50%% и ошибок смысла не больше (%d)"
                           % (args.prev, errs[args.prev]), share >= 0.5 and n_err <= errs[args.prev],
                           "%.0f%%, %d" % (100 * share, n_err)))
        if tr and args.ours in tr["table"]:
            tt = tr["table"][args.ours]
            ok_traps = sum(1 for tid in tr["ids"] if tid not in tt["texts_with_fact_errors"])
            checks.append(("Ловушки: без ошибок смысла хотя бы 5 из 6", ok_traps >= 5, "%d из %d" % (ok_traps, len(tr["ids"]))))
        else:
            # A run without traps must not look as if the trap threshold had passed.
            checks.append(("Ловушки: без ошибок смысла хотя бы 5 из 6", None, "ловушек в прогоне нет"))
        md += ["## Пороги полезности", "", "| Условие | Итог | Значение |", "|---|---|---|"]
        for name, ok, val in checks:
            verdict = "не проверено" if gaps or ok is None else ("выполнено" if ok else "не выполнено")
            md.append("| %s | %s | %s |" % (name, verdict, val))
        md.append("")
        result["thresholds"] = [{"name": n, "ok": (None if gaps else ok), "value": v} for n, ok, v in checks]
    md.append("Расходы на API за все прогоны: $%.2f." % lib.ledger().data["total"])
    lib.write_text(run_dir / (args.out + ".md"), "\n".join(md) + "\n")
    lib.write_json(run_dir / (args.out + ".json"), result)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
