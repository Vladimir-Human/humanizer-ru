#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""f3v2_measure.py — П2/П3: детерминированная часть прохода по замороженному
предрегу f3-adversarial-prereg-v2-2026-09.md (sha256
17CC780F6BFC758DDADACB5A94FD7D8F3B09E126ACB49EC8C3D843E27BB08191).

Self-attack --remove первой строкой, FPR-кривая на H, recall на M1/M2,
retention на E, McNemar по парам операторов, бутстрэп ДИ разностей глубин.
SKILL-rewrite (класс c, 50 вызовов) исполняется отдельным шагом кампейна.
"""
import json
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "filemarks"))
import check_markers as cm  # noqa: E402
import text_layer as tl  # noqa: E402

OUT = Path(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))) / \
    "measurement" / "f3v2-2026-09"

COMPILED_AB = {n: re.compile(c[0]) for n, c in cm.CASES.items()
               if cm.CLASS_OF.get(n) in ("A", "B")}


def detected(text, name=None):
    rx = {name: re.compile(cm.CASES[name][0])} if name else COMPILED_AB
    for line in text.splitlines():
        if cm._line_matches(line, rx):
            return True
    return False


def remove_safe(text):
    t = tl.remove_invisible(text)
    if isinstance(t, tuple):
        t = t[0]
    try:
        t2 = tl.clean_markup(t)
        if isinstance(t2, tuple):
            t2 = t2[0]
        t = t2
    except Exception:
        pass
    return t


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(ln) for ln in
            (OUT.parent / "f3v2-mutants" / "mutants.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    base = {(r["set"], str(r["idx"])): r["text"] for r in rows
            if r["op"] == "none"}
    res = {"prereg_sha256":
           "17CC780F6BFC758DDADACB5A94FD7D8F3B09E126ACB49EC8C3D843E27BB08191",
           "self_attack_remove": {}, "fpr_curve": {}, "recall": {},
           "retention": {}, "mcnemar": {}, "bootstrap": {}}

    # 1) self-attack --remove (первая строка отчёта)
    e_base = [t for (s, _i), t in base.items() if s == "E"]
    before = sum(1 for t in e_base if detected(t))
    after = sum(1 for t in e_base if detected(remove_safe(t)))
    h_base = [t for (s, _i), t in base.items() if s == "H"]
    fpr_before = sum(1 for t in h_base if detected(t)) / len(h_base)
    fpr_after = sum(1 for t in h_base if detected(remove_safe(t))) / len(h_base)
    res["self_attack_remove"] = {
        "E_recall_before": round(before / len(e_base), 4),
        "E_recall_after_remove": round(after / len(e_base), 4),
        "ratio": round((after / len(e_base)) / max(before / len(e_base), 1e-9), 4),
        "H_fpr_before": round(fpr_before, 4),
        "H_fpr_after_remove": round(fpr_after, 4),
    }

    # 2) FPR-кривая на H и recall на M1/M2, retention на E
    ops = sorted({r["op"] for r in rows if r["op"] != "none"})
    for op in ops:
        curve = {}
        rec = {}
        ret = {}
        for depth in (1, 2, 3):
            sub = [r for r in rows if r["op"] == op and r["depth"] == depth]
            h = [r for r in sub if r["set"] == "H"]
            m = [r for r in sub if r["set"] in ("M1", "M2")]
            e = [r for r in sub if r["set"] == "E"]
            curve["d%d" % depth] = round(
                sum(1 for r in h if detected(r["text"])) / len(h), 4)
            rec["d%d" % depth] = round(
                sum(1 for r in m if detected(r["text"])) / len(m), 4)
            ok = 0
            for r in e:
                case = str(r["idx"]).replace("embed-", "", 1)
                if detected(r["text"], case):
                    ok += 1
            ret["d%d" % depth] = round(ok / len(e), 4)
        res["fpr_curve"][op] = curve
        res["recall"][op] = rec
        res["retention"][op] = ret

    # 3) McNemar по парам операторов (depth 1, H)
    def mcnemar(op_a, op_b):
        a = {str(r["idx"]): detected(r["text"]) for r in rows
             if r["op"] == op_a and r["depth"] == 1 and r["set"] == "H"}
        b = {str(r["idx"]): detected(r["text"]) for r in rows
             if r["op"] == op_b and r["depth"] == 1 and r["set"] == "H"}
        disc = [(a[k], b[k]) for k in a if a[k] != b[k]]
        n01 = sum(1 for x, y in disc if not x and y)
        n10 = sum(1 for x, y in disc if x and not y)
        stat = (abs(n01 - n10) - 1) ** 2 / max(n01 + n10, 1)
        return {"n01": n01, "n10": n10, "chi2_cc": round(stat, 4)}
    res["mcnemar"]["typo_vs_synonym-swap"] = mcnemar("typo", "synonym-swap")
    res["mcnemar"]["homoglyph_vs_translit"] = mcnemar("homoglyph", "translit")

    # 4) бутстрэп ДИ recall d1-d3 на E
    for op in ops:
        e1 = [r for r in rows if r["op"] == op and r["depth"] == 1
              and r["set"] == "E"]
        e3 = [r for r in rows if r["op"] == op and r["depth"] == 3
              and r["set"] == "E"]
        v1 = [1 if detected(r["text"], str(r["idx"]).replace("embed-", "", 1))
              else 0 for r in e1]
        v3 = [1 if detected(r["text"], str(r["idx"]).replace("embed-", "", 1))
              else 0 for r in e3]
        rng = random.Random(20260904)
        diffs = []
        for _ in range(1000):
            s1 = rng.choices(v1, k=len(v1))
            s3 = rng.choices(v3, k=len(v3))
            diffs.append(sum(s1) / len(s1) - sum(s3) / len(s3))
        diffs.sort()
        res["bootstrap"][op] = [round(diffs[50], 4), round(diffs[950], 4)]

    (OUT / "result.json").write_bytes(
        json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    print("self_attack_remove:", res["self_attack_remove"])
    print("retention d1 sample:", {k: v["d1"] for k, v in
                                   list(res["retention"].items())[:5]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
