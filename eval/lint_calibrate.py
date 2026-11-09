#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Measure the style linter on texts of known origin: how often each rule and metric fires
#          on human texts and on model texts, and which level the linter gives them. The human rate
#          is the published false-alarm rate (R-LINT-STYLE); limits in rules.json are set from the
#          tuning part only, the controls are reported apart.
# SCOPE: no API calls; reads eval/corpus (human, pairs, texts, index.json); writes
#        eval/results/style-lint/calibration.md and .json.
# DEPENDS: skills/humanizer-ru/scripts/lint_style.py; build_corpus.human_wikinews.
# LINKS: M-EVAL-LINT-CALIBRATE; R-LINT-STYLE; V-M-LINT-STYLE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# groups: tuning human (150 Wikinews outside the controls), controls (set human + traps),
#         model texts (generated eval sources by set, and the matched pairs when present).
# measure: per group the share of texts hit by each rule, metric quantiles, level shares.
# main: CLI; prints and writes the tables.
# END_MODULE_MAP
from __future__ import annotations

import importlib.util
import statistics
import sys
from collections import Counter

import evallib as lib
from build_corpus import human_wikinews

REPO = lib.EVAL_DIR.parent
_spec = importlib.util.spec_from_file_location("lint_style", REPO / "skills/humanizer-ru/scripts/lint_style.py")
lint_style = importlib.util.module_from_spec(_spec)
sys.modules["lint_style"] = lint_style
_spec.loader.exec_module(lint_style)
CORPUS = lib.EVAL_DIR / "corpus"
OUT = lib.EVAL_DIR / "results" / "style-lint"


def groups() -> dict:
    wiki = lib.read_json(CORPUS / "human" / "index.json")
    controls = {r["id"] for r in human_wikinews(wiki)}
    index = lib.read_json(CORPUS / "index.json")
    text = lambda tid: lib.read_text(CORPUS / "texts" / (tid + ".txt"))
    g = {
        "Люди: Викиновости до 2022, настройка (150)": [lib.read_text(CORPUS / "human" / (r["id"] + ".txt"))
                                                      for r in wiki if r["id"] not in controls],
        "Люди: контроль (набор human и ловушки)": [text(r["id"]) for r in index if r["kind"] in ("human", "trap")],
        "Модели: исходники прошлых наборов (dev–holdout3)": [text(r["id"]) for r in index
                                                             if r["kind"] == "generated" and r["set"] != "holdout4"],
        "Модели: holdout4": [text(r["id"]) for r in index if r["set"] == "holdout4"],
        "Чат-боты: сохранённые ответы r01–r06": [text(r["id"]) for r in index if r["kind"] == "real"],
    }
    pairs = CORPUS / "pairs" / "index.json"
    if pairs.exists():
        g["Модели: новости по тем же заголовкам (пары)"] = [lib.read_text(CORPUS / "pairs" / (i + ".txt"))
                                                           for i in sorted(lib.read_json(pairs))]
    return g


def _q(vals, q):
    vals = sorted(v for v in vals if v is not None)
    return round(vals[min(len(vals) - 1, int(q * (len(vals) - 1) + 0.5))], 2) if vals else None


def measure(texts: list, rules: dict) -> dict:
    reps = [lint_style.lint(t, rules) for t in texts]
    n = len(reps)
    rule_hits = Counter(h["id"] for r in reps for h in r["hits"])
    metric_over = Counter(k for r in reps for k, m in r["metrics"].items() if m["over"])
    return {
        "texts": n,
        "rules": {p["id"]: round(rule_hits[p["id"]] / n, 3) for p in rules["phrases"]},
        "metrics_over": {k: round(metric_over[k] / n, 3) for k in rules["metrics"]},
        "metric_median": {k: _q([r["metrics"][k]["value"] for r in reps], 0.5) for k in rules["metrics"]},
        "metric_p90": {k: _q([r["metrics"][k]["value"] for r in reps], 0.9) for k in rules["metrics"]},
        "levels": {lv: round(sum(1 for r in reps if r["level"] == lv) / n, 3) for lv in ("нет", "мало", "есть", "много")},
        "score_median": round(statistics.median(r["score"] for r in reps), 2),
    }


def main() -> int:
    rules = lint_style.load_rules()
    res = {name: measure(texts, rules) for name, texts in groups().items() if texts}
    names = list(res)
    short = ["Г%d" % (i + 1) for i in range(len(names))]
    md = ["# Линтер стиля на текстах известного происхождения", "",
          "Доля текстов, где сработало правило или метрика вышла за предел. Пределы в rules.json "
          "подбирались только по группе Г1; контроль (Г2) в настройке не участвовал.", ""]
    md += ["- %s: %s, текстов %d" % (s, n, res[n]["texts"]) for s, n in zip(short, names)] + [""]
    md += ["| Уровень | " + " | ".join(short) + " |", "|---" * (len(short) + 1) + "|"]
    for lv in ("нет", "мало", "есть", "много"):
        md.append("| %s | " % lv + " | ".join("%.0f%%" % (100 * res[n]["levels"][lv]) for n in names) + " |")
    md.append("| медиана балла | " + " | ".join("%.1f" % res[n]["score_median"] for n in names) + " |")
    md += ["", "| Правило | " + " | ".join(short) + " |", "|---" * (len(short) + 1) + "|"]
    for p in rules["phrases"]:
        md.append("| %s (#%d) | " % (p["id"], p["sign"]) + " | ".join("%.0f%%" % (100 * res[n]["rules"][p["id"]]) for n in names) + " |")
    md += ["", "| Метрика: за пределом (медиана; 90-й процентиль) | " + " | ".join(short) + " |", "|---" * (len(short) + 1) + "|"]
    for k, cfg in rules["metrics"].items():
        md.append("| %s, предел %s | " % (k, cfg.get("max", cfg.get("min"))) + " | ".join(
            "%.0f%% (%s; %s)" % (100 * res[n]["metrics_over"][k], res[n]["metric_median"][k], res[n]["metric_p90"][k]) for n in names) + " |")
    OUT.mkdir(parents=True, exist_ok=True)
    lib.write_text(OUT / "calibration.md", "\n".join(md) + "\n")
    lib.write_json(OUT / "calibration.json", res)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
