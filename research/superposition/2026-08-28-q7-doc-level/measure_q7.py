#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_q7.py — замерный прогон Q7 (документ-уровневый слой), фаза 3.

Предрегистрация: preregistration.md. Fail-closed. Только stdlib.

Замеры:
  P1  аудит quantitative-heuristics.md (4 оси, ручные процедуры,
      отсутствие корпусной проверки — по заявлению в шапке);
  P2  существование /audit (слэш-команда) и наличие/отсутствие в нём
      документ-уровневых метрик;
  P3  скриптовый расчёт четырёх осей на 24 ИИ серии 1 vs 26 human:
      (1) разброс длины предложений (std);
      (2) плотность длинных тире на 1000 знаков;
      (3) доля однотипных зачинов абзацев (топ-зачин / все абзацы);
      (4) доля списков (строки-маркеры / все строки);
      AUC каждой оси (Mann-Whitney) на разделении классов.

Запуск из корня:
    python3 research/superposition/2026-08-28-q7-doc-level/measure_q7.py
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

SENT_SPLIT = re.compile(r"(?<=[.!?\u2026])\s+")
WORD = re.compile(r"[А-Яа-яЁёA-Za-z\d-]+")


def die(msg):
    print("ОШИБКА ВХОДА: %s" % msg, file=sys.stderr)
    sys.exit(2)


def axis_values(text):
    """Четыре документ-оси из quantitative-heuristics.md, скриптово."""
    sents = [len(WORD.findall(s)) for s in SENT_SPLIT.split(text) if s.strip()]
    # ось 1: разброс длины (std; 0 для пустых)
    if len(sents) >= 2:
        mean = sum(sents) / len(sents)
        std = (sum((x - mean) ** 2 for x in sents) / len(sents)) ** 0.5
    else:
        std = 0.0
    chars = max(len(text), 1)
    # ось 2: плотность длинных тире на 1000 знаков
    dashes = text.count("\u2014") * 1000.0 / chars
    # ось 3: однотипные зачины (доля топ-зачина среди непустых абзацев)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if paras:
        starts = {}
        for p in paras:
            key = p[:12]
            starts[key] = starts.get(key, 0) + 1
        top = max(starts.values())
        op_frac = top / float(len(paras))
    else:
        op_frac = 0.0
    # ось 4: доля списков (строки-маркеры / все непустые строки)
    lines = [l for l in text.splitlines() if l.strip()]
    bullets = sum(1 for l in lines if re.match(r"\s*[-*•\d]+[.)]?\s", l))
    list_frac = bullets / float(len(lines)) if lines else 0.0
    return {"rhythm_std": round(std, 2), "emdash_per_1k": round(dashes, 2),
            "opener_top_frac": round(op_frac, 3), "list_frac": round(list_frac, 3)}


def auc(pos, neg):
    ranked = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum_pos = 0.0
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            if ranked[k][1] == 1:
                rank_sum_pos += avg
        i = j
    n_pos, n_neg = len(pos), len(neg)
    if not n_pos or not n_neg:
        return None
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return round(u / (n_pos * n_neg), 4)


def main():
    # P1: аудит справочника
    qh_path = os.path.join(ROOT, "references", "quantitative-heuristics.md")
    with open(qh_path, encoding="utf-8") as fh:
        qh = fh.read()
    axes = [l.strip() for l in qh.splitlines() if l.startswith("## Ось")]
    has_manual = "Как посчитать вручную" in qh
    no_corpus_check = ("не проходил корпусной проверки" in qh.replace("\n", " ")
                       or "не проходил корпусной" in " ".join(qh.split()))

    # P2: /audit существует?
    audit_hits = []
    for pat in ("**/*audit*",):
        for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
            if ".git" in p or "__pycache__" in p:
                continue
            audit_hits.append(os.path.relpath(p, ROOT))
    # связь /audit с документ-уровнем
    audit_doc_level = False
    for p in audit_hits:
        if p.endswith((".md", ".yml", ".yaml")):
            try:
                with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
                    if "quantitative" in fh.read().lower():
                        audit_doc_level = True
            except OSError:
                pass

    # P3: оси на корпусе
    ai = sorted(glob.glob(os.path.join(ROOT, "research", "raw", "**", "*.txt"),
                          recursive=True))
    human = sorted(glob.glob(os.path.join(ROOT, "research", "validation",
                                          "human", "*.txt")))
    if not ai or not human:
        die("корпус не найден")
    vals = {"ai": [], "human": []}
    for kind, paths in (("ai", ai), ("human", human)):
        for p in paths:
            with open(p, encoding="utf-8") as fh:
                vals[kind].append(axis_values(fh.read()))
    axes_names = ("rhythm_std", "emdash_per_1k", "opener_top_frac", "list_frac")
    aucs = {}
    for ax in axes_names:
        pos = [v[ax] for v in vals["ai"]]
        neg = [v[ax] for v in vals["human"]]
        aucs[ax] = auc(pos, neg)

    out = {
        "P1": {"axes_count": len(axes), "axes": axes,
               "has_manual_procedures": has_manual,
               "no_corpus_check_claim": no_corpus_check},
        "P2": {"audit_paths": sorted(audit_hits)[:12],
               "audit_count": len(audit_hits),
               "audit_references_doc_level": audit_doc_level},
        "P3": {"ai_files": len(ai), "human_files": len(human),
               "auc": aucs,
               "max_auc": max(v for v in aucs.values() if v is not None),
               "aucs_above_coin": sum(1 for v in aucs.values()
                                      if v is not None and v > 0.5)},
    }
    out_path = os.path.join(HERE, "evidence", "stats.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))
    print("P1: осей=%d, ручные процедуры=%s, без корпусной проверки=%s"
          % (len(axes), has_manual, no_corpus_check))
    print("P2: /audit артефактов=%d, ссылается на документ-уровень=%s"
          % (len(audit_hits), audit_doc_level))
    print("P3: AUC осей: %s" % json.dumps(aucs))
    print("P3: max AUC=%s, осей > 0.5: %d"
          % (out["P3"]["max_auc"], out["P3"]["aucs_above_coin"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
