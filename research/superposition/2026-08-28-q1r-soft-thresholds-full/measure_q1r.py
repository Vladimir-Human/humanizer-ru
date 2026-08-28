#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_q1r.py — гонка порогов мягкого слоя на РАСШИРЕННОМ гейте (Q1-зачёт).

Доволение Q1 по уроку decision.md: блокирующий гейт всех будущих гонок —
полный набор FP-контролей репозитория (26 human + 12 adversarial +
2 boundary), оба режима сканера (per-file по жанровым решениям
threshold_sweep и neutral). Гонка порогов T×K перезапускается на
расширенном гейте;FP берётся из живого скана, а не из памяти.

Прогнозы и правило — preregistration.md этого каталога.

Запуск из корня:
    python3 research/superposition/2026-08-28-q1r-soft-thresholds-full/measure_q1r.py
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import threshold_sweep as tw  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

RUN_DIR = HERE
ADVERSARIAL_MANIFEST = os.path.join(ROOT, "research", "validation",
                                    "adversarial", "manifest.v1.json")


def die(msg):
    print("ОШИБКА ВХОДА: %s" % msg, file=sys.stderr)
    sys.exit(2)


def scan_file(path, genre):
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
         "--json", "--genre", genre, path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    if proc.returncode != 0:
        die("scan_soft_signals упал на %s: %s" % (path, proc.stderr[:200]))
    payload = json.loads(proc.stdout)
    report = payload[0] if isinstance(payload, list) and payload else payload
    return int(report.get("features_total", 0)), int(report.get("categories_total", 0))


def main():
    ai = sorted(glob.glob(os.path.join(ROOT, "research", "raw", "**", "*.txt"),
                          recursive=True))
    human = sorted(glob.glob(os.path.join(ROOT, "research", "validation",
                                          "human", "*.txt")))
    with open(ADVERSARIAL_MANIFEST, encoding="utf-8") as fh:
        adv = json.load(fh)
    adv_files = [(os.path.join(ROOT, c["path"]), c.get("genre", "neutral"))
                 for c in adv.get("corpus", [])]
    manifest = json.load(open(os.path.join(ROOT, "eval", "manifest.v1.json"),
                              encoding="utf-8"))
    boundary = [(os.path.join(ROOT, c["path"]), "neutral")
                for c in manifest.get("corpus", []) if c.get("kind") == "boundary"]
    if not (ai and human and adv_files and boundary):
        die("корпус неполон: ai=%d human=%d adv=%d boundary=%d"
            % (len(ai), len(human), len(adv_files), len(boundary)))

    rows = {"ai": [], "human": [], "adversarial": [], "boundary": []}

    def scan_group(paths_genre, kind):
        for path, genre in paths_genre:
            feats, cats = scan_file(path, genre)
            rows[kind].append({"file": os.path.relpath(path, ROOT),
                               "features": feats, "categories": cats})

    # ИИ: neutral (как в гонке Q1).
    scan_group([(p, "neutral") for p in ai], "ai")
    # human: per-file жанровые решения sweep + отдельный прогон neutral.
    scan_group([(p, tw.human_genre_for(p)) for p in human], "human")
    # adversarial: жанры манифеста (per-file) + neutral-прогон.
    scan_group(adv_files, "adversarial")
    # boundary: neutral.
    scan_group(boundary, "boundary")

    # neutral-дубли human и adversarial (второй режим гейта).
    human_neutral = []
    for p in human:
        f, c = scan_file(p, "neutral")
        human_neutral.append({"file": os.path.relpath(p, ROOT),
                              "features": f, "categories": c})
    adv_neutral = []
    for p, _g in adv_files:
        f, c = scan_file(p, "neutral")
        adv_neutral.append({"file": os.path.relpath(p, ROOT),
                            "features": f, "categories": c})

    def race(t, k):
        tp = sum(1 for r in rows["ai"] if r["features"] >= t and r["categories"] >= k)
        fp_pf = sum(1 for r in rows["human"] if r["features"] >= t and r["categories"] >= k)
        fp_nt = sum(1 for r in human_neutral if r["features"] >= t and r["categories"] >= k)
        fp_adv = sum(1 for r in rows["adversarial"] if r["features"] >= t and r["categories"] >= k)
        fp_advn = sum(1 for r in adv_neutral if r["features"] >= t and r["categories"] >= k)
        bd = sum(1 for r in rows["boundary"] if r["features"] >= t and r["categories"] >= k)
        return {"tp": tp, "recall": round(tp / float(len(rows["ai"])), 4),
                "fp_human_perfile": fp_pf, "fp_human_neutral": fp_nt,
                "fp_adversarial_perfile": fp_adv, "fp_adversarial_neutral": fp_advn,
                "boundary_signals": bd,
                "gate_pass": (fp_pf == 0 and fp_nt == 0 and fp_adv == 0
                              and fp_advn == 0 and bd == 0)}

    grid = {}
    for t in range(1, 9):
        for k in range(1, 5):
            grid["T%d_K%d" % (t, k)] = race(t, k)

    stats = {
        "script": os.path.relpath(os.path.abspath(__file__), ROOT),
        "corpus": {"ai": len(rows["ai"]), "human": len(rows["human"]),
                   "adversarial": len(rows["adversarial"]),
                   "boundary": len(rows["boundary"])},
        "max_features": {k: max(r["features"] for r in v)
                         for k, v in rows.items()},
        "grid": grid,
        "passing_with_recall": [name for name, r in grid.items()
                                if r["gate_pass"] and r["tp"] > 0],
        "best_passing_recall": max([r["recall"] for r in grid.values()
                                    if r["gate_pass"] and r["tp"] > 0], default=0.0),
    }
    out_path = os.path.join(RUN_DIR, "evidence", "stats.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))
    print("корпус: %s" % json.dumps(stats["corpus"]))
    print("максимум признаков: %s" % json.dumps(stats["max_features"]))
    print("конфигурации, проходящие гейт с recall>0: %s"
          % (stats["passing_with_recall"] or "НЕТ"))
    for name in ("T1_K1", "T1_K2", "T2_K1", "T2_K2", "T3_K1", "T3_K2"):
        r = grid[name]
        print("  %s: tp=%d fp_h=%d/%d fp_adv=%d/%d bd=%d pass=%s"
              % (name, r["tp"], r["fp_human_perfile"], r["fp_human_neutral"],
                 r["fp_adversarial_perfile"], r["fp_adversarial_neutral"],
                 r["boundary_signals"], r["gate_pass"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
