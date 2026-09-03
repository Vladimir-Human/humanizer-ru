#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factloss_measure.py — корпусная метрика потерь фактов (F1), один проход.

Читает пары с диска сам (предрег research/factloss-prereg-2026-09.md,
заморожен в RUNLOG W-93): S1 doc-pairs, S2 blind-rewrite-with, S3 di-cells.
Считает долю пар с lost/changed и с added по авторским категориям гейта
check_examples + Wilson 95% CI; печатает JSON в stdout и пишет копию в
measurement/factloss-2026-09.json (run-каталог). Тексты пар не публикует.

Запуск (один раз):
  python tools/factloss_measure.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                            # репозиторий
RUN = os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))  # run-каталог
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from humanizer_ru import facts_diff  # noqa: E402
import check_examples as ce  # noqa: E402


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def lost_added(before, after):
    fd = facts_diff.diff(ce._loss_text(before), ce._loss_text(after))
    lost = [i for i in fd["lost"] + fd["changed"]
            if i["category"] in ce.AUTHOR_FACT_CATS and not (
                i["category"] == "modals"
                and i.get("value") not in ce.NORMATIVE_MODALS)
            and not (i["category"] == "names"
                     and i["value"].casefold() in ce._loss_text(after).casefold())]
    added = [i for i in fd["added"]
             if i["category"] in ce.AUTHOR_FACT_CATS and not (
                 i["category"] == "modals"
                 and i.get("value") not in ce.NORMATIVE_MODALS)]
    return lost, added, fd


def measure(pairs, name):
    n = len(pairs)
    k_loss = k_add = 0
    cats_loss, cats_add = {}, {}
    exempt = 0
    for item in pairs:
        if item.get("exempt"):
            exempt += 1
        lost, added, _fd = lost_added(item["before"], item["after"])
        if lost:
            k_loss += 1
            for i in lost:
                cats_loss[i["category"]] = cats_loss.get(i["category"], 0) + 1
        if added:
            k_add += 1
            for i in added:
                cats_add[i["category"]] = cats_add.get(i["category"], 0) + 1
    return {
        "set": name, "n": n, "exempt_pairs": exempt,
        "lost_share": round(k_loss / n, 4) if n else None,
        "lost_ci95": wilson(k_loss, n),
        "added_share": round(k_add / n, 4) if n else None,
        "added_ci95": wilson(k_add, n),
        "lost_by_category": cats_loss, "added_by_category": cats_add,
    }


def s1_pairs():
    out = []
    for rel in ce.TARGETS:
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for m in ce.PAIR_RX.finditer(text):
            label = (m.group("label") or "").strip().lower().strip("() ").strip()
            out.append({
                "before": m.group("before").strip(),
                "after": m.group("after").strip(),
                "exempt": label in ce.AUTHOR_LABELS
                or label in ce.LOSS_EXEMPT_LABELS,
            })
    return out


def s2_pairs():
    out = []
    runs = os.path.join(ROOT, "eval", "runs")
    for d in sorted(os.listdir(runs)):
        base = os.path.join(runs, d)
        src = os.path.join(base, "source")
        wit = os.path.join(base, "with")
        if not (os.path.isdir(src) and os.path.isdir(wit)):
            continue
        for f in sorted(os.listdir(wit)):
            if not f.endswith(".txt"):
                continue
            a = os.path.join(src, f)
            b = os.path.join(wit, f)
            if not os.path.isfile(a):
                continue
            with open(a, encoding="utf-8") as fh:
                before = fh.read()
            with open(b, encoding="utf-8") as fh:
                after = fh.read()
            out.append({"before": before, "after": after, "exempt": False,
                        "run": d, "id": f})
    return out


def s3_pairs():
    base = os.path.join(RUN, "measurement", "di-control-2026-09")
    with open(os.path.join(base, "cell-texts.json"), encoding="utf-8") as fh:
        texts = json.load(fh)
    with open(os.path.join(ROOT, "research", "di-control-2026-09",
                           "cells.json"), encoding="utf-8") as fh:
        cells = json.load(fh)
    out = []
    for c in cells:
        kind_m, id_m = c["ref"][0]
        kind_h, id_h = c["ref"][1]
        assert kind_m == "machine" and kind_h == "human"
        out.append({"before": texts["machine"][id_m],
                    "after": texts["human"][id_h],
                    "exempt": False, "id": c["cell"]})
    return out


def main():
    res = {
        "prereg": "research/factloss-prereg-2026-09.md",
        "prereg_sha256": "C8E969F6A5CC998EBE720D411619F12F86D5A7A4E1FC7B9002F13A2D0C89512D",
        "sets": [
            measure(s1_pairs(), "S1 doc-pairs"),
            measure(s2_pairs(), "S2 blind-rewrite-with"),
            measure(s3_pairs(), "S3 di-cells"),
        ],
    }
    s1 = res["sets"][0]
    core = [p for p in s1_pairs() if not p["exempt"]]
    res["S1_core_without_exempt"] = measure(core, "S1 core (без меток)")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    outdir = os.path.join(RUN, "measurement", "factloss-2026-09")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
