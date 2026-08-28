#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_q4.py — замерный прогон Q4 (панель судей односемейная), фаза 3.

Предрегистрация: preregistration.md. Fail-closed. Только стандартная библиотека.

Замеры:
  P1  судейские семьи по eval/runs/*/manifest.json;
  P2  публикуемые оси LEADERBOARD.md (механические vs панельные);
  P3  двухсемейность панельных заявлений P3/G5/G6 (по research/agent/*).

Запуск из корня:
    python3 research/superposition/2026-08-28-q4-judge-panel/measure_q4.py
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

FAMILY_RX = [
    ("Qwen", ("qwen",)), ("GLM", ("glm",)), ("DeepSeek", ("deepseek",)),
    ("Kimi", ("kimi",)), ("Claude", ("claude",)), ("Gemini", ("gemini",)),
    ("Grok", ("grok",)), ("GigaChat", ("gigachat",)),
]


def family_of(text):
    t = str(text or "").lower()
    for name, keys in FAMILY_RX:
        if any(k in t for k in keys):
            return name
    return None


def main():
    # P1: семьи судей по прогонам
    runs = {}
    for mpath in sorted(glob.glob(os.path.join(ROOT, "eval", "runs", "*",
                                               "manifest.json"))):
        run = os.path.basename(os.path.dirname(mpath))
        with open(mpath, encoding="utf-8") as fh:
            try:
                m = json.load(fh)
            except ValueError:
                runs[run] = {"judge_family": None, "raw": "манифест не читается"}
                continue
        judge = m.get("judge", "")
        fam = family_of(judge)
        runs[run] = {
            "judge_raw": str(judge)[:160],
            "judge_family": fam,
            "generator_family": family_of(m.get("model", "")),
            "mechanical": ("механичес" in str(judge).lower()
                           or "не гонялась" in str(judge).lower()),
            "pending": "ожидается" in str(judge).lower(),
        }
    families = sorted({v["judge_family"] for v in runs.values()
                       if v.get("judge_family")})
    # P2: оси LEADERBOARD
    lb_path = os.path.join(ROOT, "LEADERBOARD.md")
    with open(lb_path, encoding="utf-8") as fh:
        lb = fh.read()
    panel_words = ("читаемост", "звучан", "предпочтен")
    lb_lines = [l for l in lb.splitlines() if l.strip()]
    panel_mentions = [l.strip()[:100] for l in lb_lines
                      if any(w in l.lower() for w in panel_words)]
    # есть ли в LEADERBOARD таблица с панельными столбцами
    has_panel_column = any("читаемост" in l.lower() for l in lb_lines
                           if l.strip().startswith("|"))
    # P3: двухсемейность P3/G5/G6
    reports = {}
    for name in ("P3-exp1-report.md", "G5-exp1-report.md",
                 "G6-exp1-report.md"):
        p = os.path.join(ROOT, "research", "agent", name)
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        fams_found = []
        for fam_name, keys in FAMILY_RX:
            if any(k in text.lower() for k in keys):
                fams_found.append(fam_name)
        reports[name] = {
            "families_mentioned": fams_found,
            "mentions_two_families": len([f for f in fams_found
                                          if f in ("Qwen", "GLM", "Claude",
                                                   "DeepSeek", "Kimi")]) >= 2,
            "snippet": next((l.strip()[:140] for l in text.splitlines()
                             if "семь" in l.lower() or "судь" in l.lower()), ""),
        }

    out = {
        "runs": runs,
        "judge_families_used": families,
        "families_count": len(families),
        "leaderboard": {
            "panel_mentions": panel_mentions,
            "has_panel_column": has_panel_column,
            "verdict": "панельные оси не публикуются"
                       if not has_panel_column else "есть панельный столбец",
        },
        "quality_reports": reports,
    }
    out_path = os.path.join(HERE, "evidence", "stats.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))
    print("P1 семьи судей в истории: %s (%d)" % (families, len(families)))
    print("P2 LEADERBOARD: %s; упоминаний панельных слов: %d"
          % (out["leaderboard"]["verdict"], len(panel_mentions)))
    for name, r in reports.items():
        print("P3 %s: семьи=%s two_families=%s" %
              (name, r["families_mentioned"], r["mentions_two_families"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
