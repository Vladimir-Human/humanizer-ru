#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""marker_lr_measure.py — F17: один проход калибровки маркеров в отношения
правдоподобия по замороженному предрегу f17-lr-prereg-2026-09.md (sha256
9610CC8240701380F4E22708306D2F40916016D15BBC3125482F17D849CF335D).

p1 — доля машинных текстов CoAT binary validation (label==1) с находкой
маркера (новый проход); p0 — из снимка F16 (research/fp-corpus-2026-09/
extras.json + registry-40); LR_lower = p1 / Wilson-верх p0 при p0=0.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "scripts"))
import check_markers as cm  # noqa: E402

OUT = Path(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))) / \
    "measurement" / "marker-lr-2026-09"


def wilson_upper(k, n, z=1.959963984540054):
    if n == 0:
        return 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return min(1.0, c + h)


def wilson_ci(k, n, z=1.959963984540054):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 6), round(min(1.0, c + h), 6)]


def machine_texts():
    import pyarrow.parquet as pq
    tmp = os.path.join(tempfile.gettempdir(), "coat-binary-validation.parquet")
    table = pq.read_table(tmp, columns=["text", "label"])
    return [r["text"] for r in table.to_pylist() if r["label"] == 1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    texts = machine_texts()
    n1 = len(texts)
    names = [n for n in cm.CASES if cm.CLASS_OF.get(n) in ("A", "B")]
    compiled = {n: re.compile(cm.CASES[n][0]) for n in names}
    hits = {n: 0 for n in names}
    for t in texts:
        seen = set()
        for line in t.splitlines():
            for _s, _e, name in cm._line_matches(line, compiled):
                seen.add(name)
        for n in seen:
            hits[n] += 1
    ex = json.loads((ROOT / "research" / "fp-corpus-2026-09" / "extras.json")
                    .read_text(encoding="utf-8"))
    n0 = ex["lengths"]["n"] + 40
    fp0 = dict(ex["fp_by_marker"])
    rows = {}
    for n in names:
        k1 = hits[n]
        p1 = k1 / n1 if n1 else 0.0
        k0 = fp0.get(n, 0)
        p0 = k0 / n0
        p0u = wilson_upper(k0, n0)
        lr_lower = round(p1 / p0u, 4) if p0u > 0 else None
        scale = ("сильное" if (lr_lower or 0) > 20 else
                 "умеренное" if (lr_lower or 0) > 6 else
                 "ограниченное" if (lr_lower or 0) > 2 else "слабое")
        rows[n] = {"class": cm.CLASS_OF.get(n), "k1": k1, "n1": n1,
                   "p1": round(p1, 6), "p1_ci": wilson_ci(k1, n1),
                   "k0": k0, "n0": n0, "p0": round(p0, 6),
                   "lr_lower": lr_lower, "scale": scale}
    res = {"prereg_sha256": "9610CC8240701380F4E22708306D2F40916016D15BBC3125482F17D849CF335D",
           "n1": n1, "n0": n0, "markers": rows}
    (OUT / "result.json").write_bytes(
        json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    strong = [n for n, r in rows.items() if r["scale"] == "сильное"]
    moderate = [n for n, r in rows.items() if r["scale"] == "умеренное"]
    print("n1:", n1, "| сильных:", len(strong), "| умеренных:", len(moderate))
    print("сильные:", strong[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
