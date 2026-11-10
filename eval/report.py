#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Turn judgments and fact checks into the comparison table and the pass/fail verdict
#          against the usefulness thresholds of the remake.
# SCOPE: reads eval/results/<run>/{outputs,judgments.jsonl}; writes summary.md and summary.json
#        (--out renames them; --judges keeps only the passes of the named judges;
#        --rank-judges takes places from some judges and fact votes from all).
# DEPENDS: evallib; skills/humanizer-ru/scripts/check_facts.py (imported by path).
# LINKS: M-EVAL-REPORT; DF-EVAL; V-M-EVAL; R-EVAL-RANK-JUDGES; R-EVAL-NOISE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# load: judgments with a valid ranking, corpus index, outputs.
# aggregate: per-system positions, first places, pairwise wins, send_as_is, fact flags.
# share_interval: 95% paired bootstrap interval over texts for a share "a above b" (R-EVAL-NOISE).
# fact_flag: one vote per judge, the error counts on a majority of judges.
# agreed_record, sign_test, critical_wins: wins only when every pass agrees; exact sign test.
# release_gates: gates 2 and 3 of the 4.2.0 rules (README); a run without judges (human set) works.
# thresholds: usefulness criteria for "ours" (rule set 2, see README), reported only since 4.2.0.
# render: Markdown summary.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import math
import random
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


# START_CONTRACT: aggregate
# PURPOSE: Per-system table for one group of texts.
# INPUTS: judgment rows with a ranking, text ids, outputs {(system, id): text}, sources, and
#         rank_judges: judges whose rankings and scores count (None = all). Every judge's
#         fact_errors still vote on meaning errors (R-EVAL-RANK-JUDGES).
# OUTPUTS: (table per system, pairwise shares "a>b", fact notes).
# END_CONTRACT: aggregate
def aggregate(rows, ids, outputs, sources, rank_judges=None):
    # Systems come from the rankings and, for a run without judges (set human), from the outputs.
    systems = sorted({s for r in rows for s in r["ranking"]} | {s for (s, t) in outputs if t in ids})
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
        ranks = rank_judges is None or judge in rank_judges
        if ranks:
            for i, s in enumerate(rank):
                pos[s][judge].append(i + 1)
            first[rank[0]] += 1
            for i, a in enumerate(rank):
                for b in rank[i + 1:]:
                    wins[(a, b)][judge].append(1)
                    wins[(b, a)][judge].append(0)
        for s, c in (r.get("candidates") or {}).items():
            if ranks and isinstance(c.get("send_as_is"), (int, float)):
                send[s][judge].append(float(c["send_as_is"]))
            errs = [e for e in (c.get("fact_errors") or []) if str(e).strip() and str(e).strip().lower() not in ("нет", "-", "—")]
            fact_votes[(s, r["id"])][judge][1] += 1
            if errs:
                fact_votes[(s, r["id"])][judge][0] += 1
                fact_notes[(s, r["id"])].append("%s: %s" % (judge.split("/")[-1], "; ".join(map(str, errs))))
    script = {}
    for s in systems:
        for tid in sorted(ids):
            out = outputs.get((s, tid))
            if out is None:
                continue
            res = check_facts.compare(sources[tid], lib.split_notes(out, sources[tid])[0])  # R-NOTES-NOT-TEXT
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


# START_CONTRACT: share_interval
# PURPOSE: How far the share "a above b" can move by chance: a paired bootstrap over texts.
# INPUTS: judgment rows with a ranking, text ids, systems a and b, rank_judges (None = all),
#         rounds, seed (fixed, so the same judgments always give the same interval).
# OUTPUTS: (low, high) of the 95% percentile interval, or None with fewer than 2 texts.
# RULE: the text is the unit of chance (passes and judges of one text are not independent), so
#       texts are drawn with replacement and the share is computed exactly as in aggregate: the
#       mean over judges of each judge's mean over its passes. An interval that holds 0.5 means
#       the run cannot tell a and b apart; the pass/fail thresholds themselves stay as fixed.
# END_CONTRACT: share_interval
def share_interval(rows, ids, a, b, rank_judges=None, rounds=2000, seed=0):
    by = defaultdict(lambda: defaultdict(list))  # judge -> text -> [1 if a above b else 0]
    for r in rows:
        rank = r.get("ranking") or []
        if r["id"] not in ids or a not in rank or b not in rank:
            continue
        if rank_judges is not None and r["judge"] not in rank_judges:
            continue
        by[r["judge"]][r["id"]].append(1 if rank.index(a) < rank.index(b) else 0)
    texts = sorted({t for d in by.values() for t in d})
    if len(texts) < 2:
        return None

    def share(sample):
        means = []
        for d in by.values():
            v = [x for t in sample for x in d.get(t, ())]
            if v:
                means.append(sum(v) / len(v))
        return sum(means) / len(means) if means else None

    rng = random.Random(seed)
    vals = sorted(s for s in (share([rng.choice(texts) for _ in texts]) for _ in range(rounds)) if s is not None)
    return vals[int(0.025 * (len(vals) - 1))], vals[int(round(0.975 * (len(vals) - 1)))]


# START_CONTRACT: agreed_record
# PURPOSE: Wins, losses and ties of a over b where a win needs every pass to agree (4.2.0 rule).
# INPUTS: judgment rows with a ranking, text ids, systems a and b, rank_judges (None = all).
# OUTPUTS: {"wins", "losses", "ties", "texts"}; a text without a pass that ranks both is skipped.
# RULE: per text, every counted pass (all rounds of all rank judges) must put a above b for a win,
#       b above a for a loss; any disagreement is a tie. Order effects of one shuffle cancel out.
# END_CONTRACT: agreed_record
def agreed_record(rows, ids, a, b, rank_judges=None):
    votes = defaultdict(list)  # text -> [True if a above b]
    for r in rows:
        rank = r.get("ranking") or []
        if r["id"] not in ids or a not in rank or b not in rank:
            continue
        if rank_judges is not None and r["judge"] not in rank_judges:
            continue
        votes[r["id"]].append(rank.index(a) < rank.index(b))
    rec = {"wins": 0, "losses": 0, "ties": 0, "texts": len(votes)}
    for v in votes.values():
        rec["wins" if all(v) else "losses" if not any(v) else "ties"] += 1
    return rec


def sign_test(wins: int, losses: int) -> float:
    """One-sided exact sign test: P(at least `wins` of wins+losses at a fair coin). Ties are dropped."""
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n


def critical_wins(n: int, alpha: float = 0.05):
    """Fewest wins out of n decisive texts that the one-sided sign test calls real (None if none can)."""
    for k in range(n + 1):
        if sign_test(k, n - k) <= alpha:
            return k
    return None


def _agreed_line(rec) -> str:
    n = rec["wins"] + rec["losses"]
    need = critical_wins(n)
    return "согласных побед %d, поражений %d, ничьих %d; знаковый тест p = %.3f (на %d решённых текстах перевес виден от %s побед)" % (
        rec["wins"], rec["losses"], rec["ties"], sign_test(rec["wins"], rec["losses"]), n,
        need if need is not None else "—")


def _with_interval(share, ci):
    """"46%" → "46% (95%: 33–58%, не отличить от 50%)"."""
    if ci is None:
        return "%.0f%%" % (100 * share)
    lo, hi = ci
    verdict = "не отличить от 50%" if lo <= 0.5 <= hi else ("выше 50%" if lo > 0.5 else "ниже 50%")
    return "%.0f%% (95%%: %.0f–%.0f%%, %s)" % (100 * share, 100 * lo, 100 * hi, verdict)


# START_CONTRACT: release_gates
# PURPOSE: Gates 2 and 3 of the 4.2.0 rules (eval/README) for one run, against the previous version.
# INPUTS: result with groups from main, judgment rows, outputs, sources, ours, prev, rank_judges.
# OUTPUTS: [(name, ok, value)]; empty when prev is not in the run.
# RULE: gate 2 (AI texts): agreed wins of ours over prev >= agreed losses, and texts with a meaning
#       error not more than prev's. Gate 3 (human texts plus traps): mean similarity to the source
#       >= prev's minus 0.02, and texts with check_facts errors not more than prev's.
# END_CONTRACT: release_gates
def release_gates(result, rows, outputs, sources, ours, prev, rank_judges=None) -> list:
    gates = []
    ai = result["groups"].get("ai")
    if ai and ours in ai["table"] and prev in ai["table"] and rows:
        rec = agreed_record(rows, set(ai["ids"]), ours, prev, rank_judges)
        e_ours, e_prev = len(ai["table"][ours]["texts_with_fact_errors"]), len(ai["table"][prev]["texts_with_fact_errors"])
        gates.append(("2. ИИ-тексты: согласных побед над %s не меньше поражений, ошибок смысла не больше" % prev,
                      rec["wins"] >= rec["losses"] and e_ours <= e_prev,
                      "%d:%d (ничьих %d); ошибок %d против %d" % (rec["wins"], rec["losses"], rec["ties"], e_ours, e_prev)))
    ids = set(result["groups"].get("human", {}).get("ids", [])) | set(result["groups"].get("trap", {}).get("ids", []))
    if ids:
        table, _, _ = aggregate([], ids, outputs, sources)
        if ours in table and prev in table:
            s_ours, s_prev = table[ours]["similarity"], table[prev]["similarity"]
            f_ours, f_prev = len(table[ours]["script_errors"]), len(table[prev]["script_errors"])
            gates.append(("3. Человеческие тексты: сходство не ниже, чем у %s, минус 0,02; ошибок сверки не больше" % prev,
                          s_ours >= s_prev - 0.02 and f_ours <= f_prev,
                          "сходство %.3f против %.3f; ошибок сверки %d против %d (текстов %d)" % (s_ours, s_prev, f_ours, f_prev, len(ids))))
    return gates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--ours", default="ours")
    ap.add_argument("--baseline", default="prompt")
    ap.add_argument("--prev", default="ours410", help="previous version of ours, if it is in the run")
    ap.add_argument("--judgments", default="judgments.jsonl")
    ap.add_argument("--judges", default="", help="only passes of these judges (comma list of model ids)")
    ap.add_argument("--rank-judges", default="", help="places and shares from these judges only; all judges vote on facts")
    ap.add_argument("--out", default="summary", help="file name without extension for .md and .json")
    args = ap.parse_args()
    rank_judges = set(args.rank_judges.split(",")) if args.rank_judges else None
    if args.judges and args.out == "summary":
        # A one-judge view must never overwrite the run's main summary.
        args.out = "summary-" + "-".join(j.split("/")[-1] for j in args.judges.split(","))
    run_dir = lib.EVAL_DIR / "results" / args.run
    index = {t["id"]: t for t in lib.read_json(lib.EVAL_DIR / "corpus" / "index.json")}
    # A run of the human set has no judges: similarity and the fact script are its measures.
    jpath = run_dir / args.judgments
    rows = [json.loads(l) for l in jpath.read_text(encoding="utf-8").splitlines() if l.strip()] if jpath.exists() else []
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
    all_ids = sorted({r["id"] for r in rows} if rows else {t for (_, t) in outputs if t in index})
    for tid in all_ids:
        sources[tid] = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (tid + ".txt"))
    groups = {
        "ai": [t for t in all_ids if index[t]["kind"] in ("generated", "real")],
        "trap": [t for t in all_ids if index[t]["kind"] == "trap"],
        "human": [t for t in all_ids if index[t]["kind"] == "human"],
    }
    # Coverage: every text of the run must have the same number of valid judge passes,
    # otherwise the thresholds are reported as unverified instead of passed.
    cfg = lib.read_json(run_dir / "config.json") if (run_dir / "config.json").exists() else {}
    # Probes are hand-written checks of a candidate's new rules and are never judged (README, final4).
    expected = [t for t in (cfg.get("texts") or all_ids) if index.get(t, {}).get("kind") != "probe"]
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
        if rank_judges:
            md.append("Места, доли и «готов к отправке» — только по судьям %s; ошибки смысла — по всем судьям."
                      % ", ".join(sorted(rank_judges)))
        md.append("")
    for gname, ids in groups.items():
        if not ids:
            continue
        table, pair, notes = aggregate(rows, set(ids), outputs, sources, rank_judges)
        result["groups"][gname] = {"ids": ids, "table": table, "pairwise": pair, "fact_notes": notes}
        title = {"ai": "ИИ-тексты", "trap": "Ловушки (человеческие тексты и закон)",
                 "human": "Человеческие тексты (Викиновости до 2022 и тексты v3)"}[gname]
        md += ["## %s: %d текстов" % (title, len(ids)), "",
               "| Система | Среднее место | 1-е места | Готов к отправке, 1–10 | Тексты с ошибкой смысла (большинство судей) | Отметил хоть один судья | Ошибки скрипта сверки | Сходство с исходником |",
               "|---|---|---|---|---|---|---|---|"]
        for s in sorted(table, key=lambda x: table[x]["mean_position"] or 99):
            t = table[s]
            md.append("| %s | %s | %d из %d | %s | %d | %d | %d | %.2f |" % (
                s, "—" if t["mean_position"] is None else t["mean_position"], t["first_places"], t["passes"],
                "—" if t["send_as_is"] is None else t["send_as_is"],
                len(t["texts_with_fact_errors"]), len(t["texts_flagged_by_any_judge"]),
                len(t["script_errors"]), t["similarity"]))
        md.append("")
        md.append("Среднее место и доли считаются у каждого судьи отдельно, затем усредняются: у каждого "
                  "судьи один голос, сколько бы проходов он ни сделал.")
        md.append("")
        if args.ours in table:
            md.append("Доля сравнений, где `%s` выше соперника:" % args.ours)
            md.append("")
            cis, agreed = {}, {}
            for s in sorted(table):
                if s != args.ours and ("%s>%s" % (args.ours, s)) in pair:
                    cis[s] = share_interval(rows, set(ids), args.ours, s, rank_judges)
                    agreed[s] = agreed_record(rows, set(ids), args.ours, s, rank_judges)
                    md.append("- %s: %s; %s" % (s, _with_interval(pair["%s>%s" % (args.ours, s)], cis[s]),
                                                _agreed_line(agreed[s])))
            result["groups"][gname]["pairwise_ci"] = {"%s>%s" % (args.ours, s): (list(ci) if ci else None)
                                                      for s, ci in cis.items()}
            result["groups"][gname]["agreed"] = {"%s>%s" % (args.ours, s): dict(rec, p=round(sign_test(rec["wins"], rec["losses"]), 4))
                                                 for s, rec in agreed.items()}
            md.append("")
            md.append("В скобках 95%% интервал: тексты выбраны заново с повторами %d раз (бутстрэп по текстам). "
                      "Если интервал включает 50%%, этот прогон не различает двух участников. Согласная победа — "
                      "все проходы судей мест ставят `%s` выше; разногласие — ничья." % (2000, args.ours))
            md.append("")
        missing = {s: sorted(t for t in ids if (s, t) not in outputs) for s in table}
        missing = {s: v for s, v in missing.items() if v}
        if missing:
            md.append("**Нет правки:** %s. Такие тексты не входят в места и доли этой системы." % "; ".join(
                "%s — %s" % (s, ", ".join(v)) for s, v in sorted(missing.items())))
            md.append("")
            result["groups"][gname]["missing_outputs"] = missing
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
        def shown(other):
            # The verdict below is the fixed threshold; the interval only says how sure the run is.
            share = ai["pairwise"].get("%s>%s" % (args.ours, other), 0)
            return share, _with_interval(share, share_interval(rows, set(ai["ids"]), args.ours, other, rank_judges))

        if args.baseline in ai["table"]:
            share, text = shown(args.baseline)
            checks.append(("Выше простой просьбы хотя бы в 60% сравнений", share >= 0.6, text))
        else:
            # A tuning run without the baseline must not look as if this threshold had failed or passed.
            checks.append(("Выше простой просьбы хотя бы в 60% сравнений", None, "просьбы в прогоне нет"))
        if best:
            share, text = shown(best)
            checks.append(("Не хуже лучшего конкурента (%s): не меньше 50%%" % best, share >= 0.5, text))
        if args.prev in ai["table"]:
            share, text = shown(args.prev)
            checks.append(("Не хуже прошлой версии (%s): не меньше 50%% и ошибок смысла не больше (%d)"
                           % (args.prev, errs[args.prev]), share >= 0.5 and n_err <= errs[args.prev],
                           "%s, %d" % (text, n_err)))
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
    gates = release_gates(result, rows, outputs, sources, args.ours, args.prev, rank_judges)
    if gates:
        md += ["## Пороги выпуска 4.2.0 (README, правила от 09.11.2026)", "", "| Порог | Итог | Значение |", "|---|---|---|"]
        for name, ok, val in gates:
            md.append("| %s | %s | %s |" % (name, "не проверено" if gaps else ("выполнено" if ok else "не выполнено"), val))
        md.append("")
        result["release_gates"] = [{"name": n, "ok": (None if gaps else ok), "value": v} for n, ok, v in gates]
    md.append("Расходы на API за все прогоны: $%.2f." % lib.ledger().data["total"])
    lib.write_text(run_dir / (args.out + ".md"), "\n".join(md) + "\n")
    lib.write_json(run_dir / (args.out + ".json"), result)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
