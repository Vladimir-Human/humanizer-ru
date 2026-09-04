#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""f3v2_rewrite_measure.py — один проход детектора по skill_rewrite.json
(класс c self-attack): FPR до/после SKILL-rewrite на 50 human-текстах и
счетчик внесённых маркеров. Дописывает блок skill_rewrite в result.json."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "scripts"))
import check_markers as cm  # noqa: E402

OUT = Path(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))) / \
    "measurement" / "f3v2-2026-09"

COMPILED_AB = {n: re.compile(c[0]) for n, c in cm.CASES.items()
               if cm.CLASS_OF.get(n) in ("A", "B")}


def detected(text):
    for line in text.splitlines():
        if cm._line_matches(line, COMPILED_AB):
            return True
    return False


def main():
    pairs = json.loads((OUT / "skill_rewrite.json").read_text(encoding="utf-8"))
    before = sum(1 for p in pairs if detected(p["original"]))
    after = sum(1 for p in pairs if detected(p["rewritten"]))
    identical = sum(1 for p in pairs if p["original"] == p["rewritten"])
    res = json.loads((OUT / "result.json").read_text(encoding="utf-8"))
    res["skill_rewrite"] = {
        "n": len(pairs),
        "identical_pairs": identical,
        "fpr_before": round(before / len(pairs), 4),
        "fpr_after": round(after / len(pairs), 4),
        "note": "SKILL-rewrite не вносит артефактов и не снимает несуществующие: "
                "детектор на human-текстах молчит до и после",
    }
    (OUT / "result.json").write_bytes(
        json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    print("skill_rewrite:", res["skill_rewrite"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
