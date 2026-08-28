#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure.py — замерный прогон Q1 (пороги мягкого слоя), фаза 3.

Предрегистрация: preregistration.md (тот же каталог). Скрипт заморожен хешем
в evidence/corpus-freeze.sha256 ДО прогона. Fail-closed: нет данных — падает,
пустого отчёта не бывает. Только стандартная библиотека.

Замеры (нумерация прогнозов — из предрегистрации):
  P1  целостность: свежий пересканированный features_total пофайлово == perfile.json
      и neutral.json (H-S6);
  P2  max-gate критичности: TP/FP/boundary для правила «>=1 признака crit=высокая»
      в обоих режимах (H-C);
  P3  гистограмма детекторов: сколько из 33 сработали на ИИ-корпусе (H-S1);
  P4  концентрация топ-2 детекторов (H-S2);
  P5  разбивка срабатываний по категориям (H-S3);
  P6  агрегация: сумма сырых count против features_total на ИИ-корпусе (H-S4);
  P7  подпороговые потери: детекторы с 1 <= hits < min_hits на ИИ-файлах (H-S5);
  P8  преднормализация кавычек/тире/NBSP и дельта срабатываний (H-S7);
  P9  AUC разделения ИИ/человек: features_total против дисперсии длины
      предложений в словах (H-D);
  P10 гонка конфигураций: recall конкурирующих правил в обоих режимах.

Запуск из корня репозитория:
    python3 research/superposition/2026-08-28-q1-soft-thresholds/measure.py
Код возврата: 0 — замер выполнен; 2 — ошибка входа (нет корпуса/данных).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import threshold_sweep as tw  # noqa: E402
import scan_soft_signals as sss  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

RUN_DIR = HERE
SWEEP_DIR = os.path.join(ROOT, "research", "soft-threshold-sweep")


def die(msg):
    print("ОШИБКА ВХОДА: %s" % msg, file=sys.stderr)
    sys.exit(2)


def load_json(path):
    if not os.path.isfile(path):
        die("нет файла %s" % os.path.relpath(path, ROOT))
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except ValueError as exc:
            die("%s не читается: %s" % (os.path.relpath(path, ROOT), exc))


def group_files():
    ai = sorted(glob.glob(os.path.join(ROOT, tw.AI_GLOB), recursive=True))
    human = sorted(glob.glob(os.path.join(ROOT, tw.HUMAN_DIR, "*.txt")))
    boundary = tw.load_boundary_paths()
    if boundary is None:
        die("манифест корпуса не читается")
    if not ai or not human or not boundary:
        die("корпус не найден: ИИ %d, человеческих %d, boundary %d"
            % (len(ai), len(human), len(boundary)))
    return ai, human, boundary


def integrity_check(fresh_groups, prior_path):
    """P1: пофайловое features_total свежего прогона == приорный JSON.

    Пути нормализуются к относительным (scan_file возвращает абсолютные,
    приорный JSON хранит относительные).
    """
    prior = load_json(prior_path)
    mismatches = []
    for kind in ("ai", "human", "boundary"):
        prior_rows = {os.path.normpath(r["path"]).replace("\\", "/"):
                      r["features_total"]
                      for r in prior.get("files", {}).get(kind, [])}
        fresh_paths = set()
        for row in fresh_groups[kind]:
            rel = os.path.normpath(os.path.relpath(row["path"], ROOT)).replace("\\", "/")
            fresh_paths.add(rel)
            if rel not in prior_rows:
                mismatches.append({"path": rel, "reason": "нет в приорном JSON"})
                continue
            if row["features_total"] != prior_rows[rel]:
                mismatches.append({
                    "path": rel,
                    "fresh": row["features_total"],
                    "prior": prior_rows[rel],
                })
        for path in prior_rows:
            if path not in fresh_paths:
                mismatches.append({"path": path, "reason": "нет в свежем прогоне"})
    return mismatches


def criticality_gate(groups):
    """P2: правило «>=1 признака crit=высокая» — TP/FP/boundary."""
    out = {}
    for kind in ("ai", "human", "boundary"):
        out[kind] = sum(
            1 for r in groups[kind]
            if any(f.get("criticality") == "высокая" for f in r["findings"]))
    return out


def detector_histogram(ai_groups):
    """P3–P5: сработавшие детекторы, концентрация, категории."""
    fires = {}
    category_fires = {}
    for r in ai_groups["ai"]:
        for f in r["findings"]:
            fires[f["id"]] = fires.get(f["id"], 0) + 1
            category_fires[f["category"]] = category_fires.get(f["category"], 0) + 1
    total_fires = sum(fires.values())
    ranked = sorted(fires.items(), key=lambda kv: (-kv[1], kv[0]))
    top2_share = (sum(v for _k, v in ranked[:2]) / total_fires) if total_fires else 0.0
    return {
        "fired_detectors": len(fires),
        "registry_size": len(sss.REGISTRY),
        "fires_per_detector": dict(ranked),
        "top2_share": round(top2_share, 4),
        "category_fires": category_fires,
        "total_fires": total_fires,
    }


def aggregation(ai_groups):
    """P6: сумма сырых count против features_total на ИИ-корпусе."""
    sum_count = sum(f["count"] for r in ai_groups["ai"] for f in r["findings"])
    sum_features = sum(r["features_total"] for r in ai_groups["ai"])
    return {
        "sum_count": sum_count,
        "sum_features": sum_features,
        "ratio": round(sum_count / sum_features, 3) if sum_features else None,
    }


def subthreshold_losses(ai_files):
    """P7: детекторы с 1 <= hits < min_hits (минуя порог повторяемости).

    Воспроизводит путь analyze() для жанра neutral: маскировка fenced-блоков,
    markdown_traces выключен (plain_text=False), супрессии neutral пусты.
    """
    losses = []
    for path in ai_files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        lines = text.splitlines() or [""]
        fenced = sss._fenced_lines(text)
        masked = ["" if n in fenced else l for n, l in enumerate(lines, 1)]
        for det in sss.REGISTRY:
            if det["id"] == "markdown_traces":
                continue
            hits = det["finder"](text, masked)
            if 1 <= len(hits) < det["min_hits"]:
                losses.append({
                    "file": os.path.relpath(path, ROOT),
                    "detector": det["id"],
                    "hits": len(hits),
                    "min_hits": det["min_hits"],
                })
    return losses


# P8: карта преднормализации — «неканонические» формы к каноническим.
_NORM_MAP = {
    "«": '"', "»": '"',
    "—": "-", "–": "-",
    "…": "...",
    "\u00a0": " ",  # NBSP
    "ё": "е", "Ё": "Е",
}


def prenormalize(text):
    for src, dst in _NORM_MAP.items():
        text = text.replace(src, dst)
    return text


def prenorm_audit(ai_files):
    """P8: дельта срабатываний после преднормализации (жанр neutral)."""
    files_changed = 0
    feature_delta = 0
    for path in ai_files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        before = sss.analyze(text, genre="neutral")
        after = sss.analyze(prenormalize(text), genre="neutral")
        if before["features_total"] != after["features_total"]:
            files_changed += 1
            feature_delta += after["features_total"] - before["features_total"]
    return {"files_changed": files_changed, "feature_delta": feature_delta}


def _sentence_word_counts(text):
    counts = []
    for sent in sss._SENT_SPLIT_RX.split(text):
        words = sss._WORD_RX.findall(sent)
        if words:
            counts.append(len(words))
    return counts


def _variance(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / float(len(values))
    return sum((v - mean) ** 2 for v in values) / float(len(values))


def _auc(pos_scores, neg_scores):
    """AUC через Mann-Whitney U со средними рангами при связках."""
    ranked = [(s, 1) for s in pos_scores] + [(s, 0) for s in neg_scores]
    ranked.sort(key=lambda t: t[0])
    rank_sum_pos = 0.0
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0  # средний ранг связки (1-based)
        for k in range(i, j):
            if ranked[k][1] == 1:
                rank_sum_pos += avg_rank
        i = j
    n_pos, n_neg = len(pos_scores), len(neg_scores)
    if not n_pos or not n_neg:
        return None
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return round(u / (n_pos * n_neg), 4)


def auc_audit(groups):
    """P9: AUC ИИ-vs-человек по features_total и по дисперсии длины предложений."""
    feat_pos = [float(r["features_total"]) for r in groups["ai"]]
    feat_neg = [float(r["features_total"]) for r in groups["human"]]
    var_pos, var_neg = [], []
    for r in groups["ai"] + groups["human"]:
        with open(os.path.join(ROOT, r["path"]), encoding="utf-8") as fh:
            var = _variance(_sentence_word_counts(fh.read()))
        (var_pos if r["kind"] == "ai" else var_neg).append(var)
    return {
        "features_auc": _auc(feat_pos, feat_neg),
        "rhythm_variance_auc": _auc(var_pos, var_neg),
    }


def main():
    ai_files, human_files, boundary_files = group_files()

    print("сканирование per-file ...")
    perfile = tw.scan_corpus("per-file")
    print("сканирование neutral ...")
    neutral = tw.scan_corpus("neutral")
    if perfile is None or neutral is None:
        die("scan_corpus не собрал корпус")

    stats = {
        "script": os.path.relpath(os.path.abspath(__file__), ROOT),
        "corpus_counts": {
            "ai": len(perfile["ai"]), "human": len(perfile["human"]),
            "boundary": len(perfile["boundary"]),
        },
    }

    # P1: целостность против приорных JSON.
    stats["integrity"] = {
        "perfile_mismatches": integrity_check(perfile, os.path.join(SWEEP_DIR, "perfile.json")),
        "neutral_mismatches": integrity_check(neutral, os.path.join(SWEEP_DIR, "neutral.json")),
    }

    # P2: max-gate критичности в обоих режимах.
    stats["criticality_gate"] = {
        "per_file": criticality_gate(perfile),
        "neutral": criticality_gate(neutral),
    }

    # P3–P6: гистограмма и агрегация (per-file, ИИ-корпус).
    stats["detector_histogram"] = detector_histogram(perfile)
    stats["aggregation"] = aggregation(perfile)

    # P7: подпороговые потери (инструментально, жанр neutral для ИИ-файлов).
    print("инструментальный прогон подпороговых hits ...")
    stats["subthreshold_losses"] = subthreshold_losses(ai_files)

    # P8: преднормализация.
    print("аудит преднормализации ...")
    stats["prenorm"] = prenorm_audit(ai_files)

    # P9: AUC.
    print("расчёт AUC ...")
    stats["auc"] = auc_audit(perfile)

    # P10: гонка конфигураций (правило коллапса из предрегистрации).
    def race(groups):
        ai_n = len(groups["ai"])
        rows = {}
        for t, k in ((1, 1), (1, 2), (2, 1), (2, 2), (3, 2)):
            rows["T%d_K%d" % (t, k)] = {
                "tp": sum(1 for r in groups["ai"]
                          if r["features_total"] >= t and r["categories_total"] >= k),
                "fp": sum(1 for r in groups["human"]
                          if r["features_total"] >= t and r["categories_total"] >= k),
                "boundary": sum(1 for r in groups["boundary"]
                                if r["features_total"] >= t and r["categories_total"] >= k),
            }
            rows["T%d_K%d" % (t, k)]["recall"] = round(
                rows["T%d_K%d" % (t, k)]["tp"] / float(ai_n), 4)
        return rows

    stats["race"] = {"per_file": race(perfile), "neutral": race(neutral)}

    out_path = os.path.join(RUN_DIR, "evidence", "stats.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))

    # Краткое резюме в stdout (полные данные — в JSON).
    print("integrity: perfile=%d расхождений, neutral=%d расхождений"
          % (len(stats["integrity"]["perfile_mismatches"]),
             len(stats["integrity"]["neutral_mismatches"])))
    for mode in ("per_file", "neutral"):
        g = stats["criticality_gate"][mode]
        print("criticality max-gate (%s): TP=%d FP=%d boundary=%d"
              % (mode, g["ai"], g["human"], g["boundary"]))
    print("detectors fired: %d/%d, top2_share=%.2f"
          % (stats["detector_histogram"]["fired_detectors"],
             stats["detector_histogram"]["registry_size"],
             stats["detector_histogram"]["top2_share"]))
    print("aggregation ratio: %s" % stats["aggregation"]["ratio"])
    print("subthreshold losses: %d" % len(stats["subthreshold_losses"]))
    print("prenorm: files_changed=%d feature_delta=%d"
          % (stats["prenorm"]["files_changed"], stats["prenorm"]["feature_delta"]))
    print("auc features=%s rhythm=%s"
          % (stats["auc"]["features_auc"], stats["auc"]["rhythm_variance_auc"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
