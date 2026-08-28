#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_q2.py — замерный прогон Q2 (lint-only как продуктовая линия), фаза 3.

Предрегистрация: preregistration.md (тот же каталог). Скрипт заморожен хешем
в evidence/corpus-freeze.sha256 ДО прогона. Fail-closed: нет данных — падает.
Только стандартная библиотека.

Замеры (нумерация прогнозов — из предрегистрации):
  P1  lint-нейтральность: 26 human + 12 adversarial (манифест + файлы)
      + 2 boundary — чистка text-пути filemarks меняет 0 байт;
  P2  lint-нейтральность пробы Q3: 9 файлов (истинных артефактов нет после
      фикса гарда) — 0 изменённых байт;
  P3  сегментная перепись M×S на 33 ИИ-файлах: M = маркеры классов A/B
      (check_markers --scan), S = мягкое действие текущего дерева (T=3/K=2);
  P4  полнота снятия: чистка M+-файлов серии 1 + повторный скан — 0 маркеров;
  P5  сегмент S+ по текущему дереву (ожидание: пуст).

Запуск из корня репозитория:
    python3 research/superposition/2026-08-28-q2-lint-only/measure_q2.py
Код возврата: 0 — замер выполнен; 2 — ошибка входа.
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "filemarks"))

import threshold_sweep as tw  # noqa: E402
import check_markers as cm  # noqa: E402
from text_layer import clean_text_layer, clean_markup  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

RUN_DIR = HERE
EVIDENCE = os.path.join(RUN_DIR, "evidence")
PROBE_DIR = os.path.join(ROOT, "research", "superposition",
                         "2026-08-28-q3-holdout", "evidence", "probe")
ADVERSARIAL_MANIFEST = os.path.join(ROOT, "research", "validation",
                                    "adversarial", "manifest.v1.json")


def die(msg):
    print("ОШИБКА ВХОДА: %s" % msg, file=sys.stderr)
    sys.exit(2)


def lint_text(text):
    """Тот же путь, что filemarks.py --clean для текста (Layer A + MARKUP):
    clean_text_layer, затем clean_markup от результата (строки 184-185
    filemarks.py). Возвращает (cleaned, всего_снятий)."""
    cleaned, n = clean_text_layer(text)
    cleaned, m = clean_markup(cleaned)
    return cleaned, n + m


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def neutrality(paths):
    """Чистка по списку файлов: изменённые байты/файлы."""
    changed_files = []
    total_bytes = 0
    for path in paths:
        text = _read(path)
        cleaned, removed = lint_text(text)
        if cleaned != text:
            diff = sum(1 for a, b in zip(text, cleaned) if a != b)
            diff += abs(len(text) - len(cleaned))
            changed_files.append({
                "file": os.path.relpath(path, ROOT).replace("\\", "/"),
                "removed_marks": removed,
                "char_delta": diff,
            })
            total_bytes += diff
    return {"files_total": len(paths), "files_changed": len(changed_files),
            "changed": changed_files}


def marker_files(paths):
    """Скан маркеров по файлам через CASES (как check_adversarial._marker_hits:
    построчно, с пропуском внутри-backticks). Возвращает {relpath: [hits]}."""
    compiled = {name: rx for name, rx in cm.compiled_cases().items()} \
        if hasattr(cm, "compiled_cases") else \
        {name: __import__("re").compile(cm.CASES[name][0]) for name in cm.CASES}
    result = {}
    for path in paths:
        text = _read(path)
        hits = []
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in compiled.items():
                for m in rx.finditer(line):
                    if cm._inside_backticks(line, m.start(), m.end()):
                        continue
                    hits.append((lineno, name))
        if hits:
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            result[rel] = hits
    return result


def soft_signal(path):
    """Мягкие признаки одного файла (жанр neutral, как в гонке Q1)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
         "--json", "--genre", "neutral", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    if proc.returncode != 0:
        die("scan_soft_signals упал на %s" % path)
    payload = json.loads(proc.stdout)
    report = payload[0] if isinstance(payload, list) and payload else payload
    return int(report.get("features_total", 0)), int(report.get("categories_total", 0))


def main():
    # --- корпусы
    human = sorted(glob.glob(os.path.join(ROOT, tw.HUMAN_DIR, "*.txt")))
    ai_series1 = sorted(glob.glob(os.path.join(ROOT, "research", "raw",
                                                "**", "*.txt"), recursive=True))
    probe = sorted(glob.glob(os.path.join(PROBE_DIR, "*.txt")))
    if not os.path.isdir(PROBE_DIR):
        die("нет каталога пробы Q3")
    with open(ADVERSARIAL_MANIFEST, encoding="utf-8") as fh:
        adv_manifest = json.load(fh)
    adv_files = [os.path.join(ROOT, c["path"])
                 for c in adv_manifest.get("corpus", [])]
    for f in adv_files:
        if not os.path.isfile(f):
            die("нет adversarial-файла %s" % f)
    manifest = json.load(open(os.path.join(ROOT, "eval", "manifest.v1.json"),
                              encoding="utf-8"))
    boundary = [os.path.join(ROOT, c["path"]) for c in manifest.get("corpus", [])
                if c.get("kind") == "boundary"]
    if not (human and ai_series1 and probe and boundary):
        die("корпус неполон: human=%d ai=%d probe=%d boundary=%d"
            % (len(human), len(ai_series1), len(probe), len(boundary)))

    stats = {"script": os.path.relpath(os.path.abspath(__file__), ROOT)}

    # --- P1: нейтральность на контролях (26 + 12 + 2)
    controls = human + adv_files + boundary
    stats["neutrality_controls"] = neutrality(controls)

    # --- P2: нейтральность пробы (9)
    stats["neutrality_probe"] = neutrality(probe)

    # --- P3: сегментная перепись на 33 ИИ-файлах
    ai_all = ai_series1 + probe
    m_hits = marker_files(ai_all)
    m_files = set(m_hits.keys())
    census = []
    for path in ai_all:
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        feats, cats = soft_signal(path)
        m = rel in m_files
        s = feats >= 3 and cats >= 2  # текущее дерево T=3/K=2
        census.append({"file": rel, "markers": bool(m),
                       "features": feats, "categories": cats, "soft_action": bool(s)})
    seg = {
        "markers_only": sum(1 for c in census if c["markers"] and not c["soft_action"]),
        "soft_only": sum(1 for c in census if not c["markers"] and c["soft_action"]),
        "both": sum(1 for c in census if c["markers"] and c["soft_action"]),
        "neither": sum(1 for c in census if not c["markers"] and not c["soft_action"]),
    }
    stats["census"] = {"files": census, "segments": seg,
                       "total": len(census), "marker_files": len(m_files),
                       "marker_hits": sum(len(v) for v in m_hits.values()),
                       "marker_detail": {k: [h[1] for h in v]
                                         for k, v in m_hits.items()}}

    # --- P4: полнота снятия на M+-файлах серии 1
    m_series1 = [p for p in ai_series1
                 if os.path.relpath(p, ROOT).replace("\\", "/") in m_files]
    removal = []
    for path in m_series1:
        text = _read(path)
        cleaned, _removed = lint_text(text)
        tmp = path + ".linted.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(cleaned)
        recheck = marker_files([tmp])
        os.remove(tmp)
        residual = sum(len(v) for v in recheck.values())
        removal.append({
            "file": os.path.relpath(path, ROOT).replace("\\", "/"),
            "residual_markers": residual,
        })
    stats["removal_completeness"] = {
        "files": removal,
        "all_clean": all(r["residual_markers"] == 0 for r in removal)}

    out_path = os.path.join(EVIDENCE, "stats.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))

    print("P1 нейтральность контролов: %d/%d файлов изменено"
          % (stats["neutrality_controls"]["files_changed"],
             stats["neutrality_controls"]["files_total"]))
    print("P2 нейтральность пробы: %d/%d файлов изменено"
          % (stats["neutrality_probe"]["files_changed"],
             stats["neutrality_probe"]["files_total"]))
    print("P3 сегменты: только маркеры=%d, только мягкий=%d, оба=%d, ничего=%d (из %d)"
          % (seg["markers_only"], seg["soft_only"], seg["both"],
             seg["neither"], len(census)))
    print("P4 полнота снятия: все чисты=%s (%d файлов)"
          % (stats["removal_completeness"]["all_clean"], len(removal)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
