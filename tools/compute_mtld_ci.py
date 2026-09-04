#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compute_mtld_ci.py — MTLD (lexical diversity, stdlib) по 500 human-текстам
CoAT validation + бутстрэп ДИ среднего; пишет measurement/f8-2026-09/mtld.json."""
import json
import os
import random
import re
import sys
import tempfile
from pathlib import Path

OUT = Path(r"C:\Users\vovap\Projects\humanizer-superposition\run-20260831") / \
    "measurement" / "f8-2026-09"


def mtld(text, threshold=0.72):
    toks = re.findall(r"[a-zа-яё]+", text.lower())
    if len(toks) < 10:
        return None
    vals = []
    for seq in (toks, toks[::-1]):
        factors = 0.0
        n = 0
        uniq = {}
        for i, t in enumerate(seq, 1):
            uniq[t] = uniq.get(t, 0) + 1
            n = i
            ttr = len(uniq) / n
            if ttr < threshold:
                factors += (1 - ttr) / (1 - threshold)
                uniq = {}
                n = 0
        if n:
            factors += 1
        vals.append(len(seq) / factors if factors else 0.0)
    return sum(vals) / 2.0


def main():
    import pyarrow.parquet as pq
    tmp = os.path.join(tempfile.gettempdir(), "coat-binary-validation.parquet")
    table = pq.read_table(tmp, columns=["text", "label"])
    texts = [r["text"] for r in table.to_pylist() if r["label"] == 0][:500]
    vals = [v for v in (mtld(t) for t in texts) if v is not None]
    mean = sum(vals) / len(vals)
    rng = random.Random(20260904)
    means = []
    for _ in range(1000):
        s = rng.choices(vals, k=len(vals))
        means.append(sum(s) / len(s))
    means.sort()
    ci = [round(means[50], 4), round(means[950], 4)]
    res = {"n": len(vals), "mean": round(mean, 4), "ci95": ci}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mtld.json").write_bytes(
        json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    print("mtld:", res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
