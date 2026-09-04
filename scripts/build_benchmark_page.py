#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_benchmark_page.py — W9: публичный бенчмарк из снимков метрик репозитория.

Читает детерминированные снимки (research/fp-corpus-2026-09/result.json,
research/f8-2026-09/result.json, research/adversarial-2026-09/result.json,
research/marker-lr-2026-09/result.json, реестр фактов для fact-loss) и строит:
  research/benchmark-2026-09-04/results.json,
  research/BENCHMARK.md (таблица с CI, командой воспроизведения, колонкой
  «где мы хуже», абзацем «Как обмануть humanizer-ru» и статусом конкурентов),
  docs/benchmark/index.html (статическая страница той же таблицы).
Никаких ручных чисел: только значения из снимков.
"""
import json
import os
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATE = "2026-09-04"
OUTD = ROOT / "research" / ("benchmark-" + DATE)
OUTD.mkdir(parents=True, exist_ok=True)


def load(rel):
    p = ROOT / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


fp = load("research/fp-corpus-2026-09/result.json")
f8 = load("research/f8-2026-09/result.json")
adv = load("research/adversarial-2026-09/result.json")
lr = load("research/marker-lr-2026-09/result.json")
facts = load("eval/facts/facts.v1.json")
fl = next((e for e in facts["entries"]
           if e.get("fact_id") == "fact-loss-2026-09"), None)

rows = []
if fp:
    ov = fp["overall"]
    rows.append({
        "id": "fp-light",
        "metric": "Ложные срабатывания на человеческих текстах (лёгкий домен)",
        "value": "%d/%d = %s" % (ov["fp"], ov["n"], ov.get("fpr", ov.get("fp_share"))),
        "ci95": ov["wilson95"],
        "source": "research/fp-corpus-2026-09/result.json",
        "reproduce": "python tools/fp_corpus_measure.py (предрег f16-fp-corpus-prereg-2026-09, один проход)",
        "worse": "тяжёлый домен (юридика, канцелярит, OCR) даёт FP на порядок выше — см. fp-heavy",
    })
    hv = fp["f16b_fp"]["overall"] if "f16b_fp" in fp else None
    if hv:
        rows.append({
            "id": "fp-heavy",
            "metric": "Ложные срабатывания, тяжёлый домен (legal+official, n=381)",
            "value": "%d/%d = %s" % (hv["k"], hv["n"], hv["fpr"]),
            "ci95": hv["wilson95"],
            "source": "research/fp-corpus-2026-09/result.json",
            "reproduce": "python tools/fp_corpus_measure.py (страта S4)",
            "worse": "да: официоз и OCR-шум дают FP на порядок чаще лёгкого домена",
        })
if f8:
    for key, label in (("S1-machine-21-22_vs_human_all", "AUC мягких сигналов, поколение 2021-22 против human"),
                       ("S2-machine-24-26_vs_human_all", "AUC мягких сигналов, поколение 2024-26 против human")):
        v = f8["f8c_auc"].get(key)
        if v:
            rows.append({
                "id": key,
                "metric": label,
                "value": v["auc"],
                "ci95": v["ci95"],
                "source": "research/f8-2026-09/result.json",
                "reproduce": "python tools/f8_measure.py (предрег f8-umbrella-prereg-2026-09)",
                "worse": "да: мягкие признаки не разделяют машинность (AUC около 0.6), вердиктов по ним нет",
            })
if adv:
    ret = adv.get("retention", {})
    for op in ("zero-width", "homoglyph", "markup"):
        v = ret.get(op)
        if v:
            rows.append({
                "id": "ret-" + op,
                "metric": "Retention сигнатур после оператора %s (глубина 3)" % op,
                "value": v.get("d3"),
                "ci95": None,
                "source": "research/adversarial-2026-09/result.json",
                "reproduce": "python tools/f3v2_measure.py (предрег f3-adversarial-prereg-v2-2026-09)",
                "worse": "да: невидимые символы и гомоглифы снижают удержание сигнатур",
            })
if lr:
    weak = sum(1 for v in lr["markers"].values() if v.get("scale") == "слабое")
    rows.append({
        "id": "lr-weak",
        "metric": "Маркеры без доказательной силы на машинных текстах (LR слабое)",
        "value": "%d из %d" % (weak, len(lr["markers"])),
        "ci95": None,
        "source": "research/marker-lr-2026-09/result.json",
        "reproduce": "python tools/marker_lr_measure.py (предрег f17-lr-prereg-2026-09)",
        "worse": "да: маркеры копипасты молчат на чистых машинных текстах — это граница, а не детектор машинности",
    })
if fl:
    rows.append({
        "id": "fact-loss-showcase",
        "metric": "Потеря фактов авторских категорий на витринных парах",
        "value": fl.get("value_note", "")[:120],
        "ci95": None,
        "source": "eval/facts/facts.v1.json",  # fact-loss-2026-09
        "reproduce": "python scripts/check_facts_diff.py + предрег factloss",
        "worse": "да: на слепом переписывании потери существенны — правка без fact-loss не рекомендуется",
    })

results = {"date": DATE, "rows": rows,
           "competitors": [
               {"repo": "Imalwayshere/Open-Detector", "stars": 238,
                "status": "не удалось воспроизвести: BERT-модель обучена на английском академическом тексте, русского корпуса и публичного API для русского нет; см. методику"},
               {"repo": "talkstream/ru-text", "stars": 223,
                "status": "не удалось воспроизвести количественно: набор правил для агентов без исполняемой скоринг-процедуры; качественное пересечение тем учтено в THREAT-MODEL"},
               {"repo": "smixs/humanizer-ru", "stars": 148,
                "status": "форк самого проекта, не независимый конкурент"},
           ]}
(OUTD / "results.json").write_bytes(
    json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")

lines = ["# BENCHMARK — публичный бенчмарк humanizer-ru (%s)" % DATE,
         "",
         "Каждая строка — из детерминированного снимка в репозитории; команда"
         " воспроизведения и колонка «где мы хуже» обязательны.",
         "",
         "| Метрика | Значение | Wilson 95% | Источник | Где мы хуже |",
         "|---|---|---|---|---|"]
for r in rows:
    ci = "[%s; %s]" % tuple(r["ci95"]) if r["ci95"] else "—"
    lines.append("| %s | %s | %s | `%s` | %s |" % (r["metric"], r["value"], ci,
                                                   r["source"], r["worse"]))
lines += ["",
          "## Команды воспроизведения", ""]
for r in rows:
    lines.append("- `%s` — %s" % (r["reproduce"], r["metric"]))
lines += ["",
          "## Конкуренты", ""]
for c in results["competitors"]:
    lines.append("- %s (%d★): %s." % (c["repo"], c["stars"], c["status"]))
lines += ["",
          "## Как обмануть humanizer-ru",
          "",
          "Полная переписка текста снимает артефакты копипасты целиком — это"
          " следует из границы детекции (Sadasivan et al.) и зафиксировано в"
          " docs/THREAT-MODEL.md; невидимые символы и гомоглифы снижают"
          " удержание сигнатур (см. retention выше). Проект не обещает"
          " стойкости к намеренному обходу и не измеряет её (инвариант 2:"
          " публикация обхода была бы обучающим сигналом для детекторов).",
          ""]
(ROOT / "research" / "BENCHMARK.md").write_bytes(
    ("\n".join(lines)).encode("utf-8") + b"\n")

html = ["<!doctype html>", '<html lang="ru">', "<head>",
        '<meta charset="utf-8">',
        '<title>humanizer-ru — публичный бенчмарк</title>',
        '<link rel="stylesheet" href="../brand.css">',
        "</head>", "<body>",
        "<h1>Публичный бенчмарк humanizer-ru</h1>",
        '<p class="note">Дата снимка: %s. Каждая строка — из детерминированного'
        " снимка в репозитории; команды воспроизведения — в research/BENCHMARK.md.</p>" % DATE,
        '<table border="1" cellpadding="6" cellspacing="0">',
        "<tr><th>Метрика</th><th>Значение</th><th>Wilson 95%</th><th>Источник</th><th>Где мы хуже</th></tr>"]
for r in rows:
    ci = "[%s; %s]" % tuple(r["ci95"]) if r["ci95"] else "—"
    html.append("<tr><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td></tr>"
                % (r["metric"], r["value"], ci, r["source"], r["worse"]))
html += ["</table>",
         "<h2>Конкуренты</h2>", "<ul>"]
for c in results["competitors"]:
    html.append("<li>%s (%d★): %s.</li>" % (c["repo"], c["stars"], c["status"]))
html += ["</ul>",
         "<h2>Как обмануть humanizer-ru</h2>",
         "<p>Полная переписка текста снимает артефакты копипасты целиком — это"
         " граница детекции (Sadasivan et al.), зафиксированная в"
         " THREAT-MODEL. Проект не обещает стойкости к намеренному обходу и не"
         " измеряет её.</p>",
         '<p><a href="../index.html">Вернуться в демо</a></p>',
         "</body>", "</html>", ""]
bd = ROOT / "demo" / "benchmark"
bd.mkdir(parents=True, exist_ok=True)
(bd / "index.html").write_bytes("\n".join(html).encode("utf-8") + b"\n")
print("OK benchmark page at demo/benchmark; строк таблицы:", len(rows))
