#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_q3.py — замерный прогон Q3 (дизайн скрытого holdout), фаза 3.

Предрегистрация: preregistration.md (тот же каталог). Скрипт заморожен хешем
в evidence/corpus-freeze.sha256 ДО прогона. Fail-closed: нет данных — падает.
Только стандартная библиотека.

Замеры (нумерация прогнозов — из предрегистрации):
  P1  мощность: точный бином — power(12, p), N_required(p=0.7, 80%, a=0.05
      односторонний), точные CI для 9/9, 14/14, 19/19 (H-C3);
  P2  скан пробы 3 новых семейств (9 файлов): максимум features_total,
      срабатывания маркеров классов A/B (H2);
  P3  регистровый аудит: доля художественной классики XIX века в
      человеческом корпусе (H1);
  P4  аудит «реестр ↔ корпус»: семейства-источники маркеров без корпусной
      поддержки в research/raw (H1/H2).

Запуск из корня репозитория:
    python3 research/superposition/2026-08-28-q3-holdout/measure_q3.py
Код возврата: 0 — замер выполнен; 2 — ошибка входа.
"""
import glob
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import threshold_sweep as tw  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

RUN_DIR = HERE
PROBE_DIR = os.path.join(RUN_DIR, "evidence", "probe")
MARKERS_SOURCES = os.path.join(ROOT, "research", "fixtures", "marker-sources.json")
SCAN = os.path.join(ROOT, "scripts", "scan_soft_signals.py")
CHECK_MARKERS = os.path.join(ROOT, "scripts", "check_markers.py")

Z95 = 1.959963984540054


def die(msg):
    print("ОШИБКА ВХОДА: %s" % msg, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- P1: мощность

def binom_tail(n, k, p):
    """P(X >= k) для X ~ Bin(n, p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i)
               for i in range(k, n + 1))


def kstar(n, alpha=0.05):
    """Минимальное k со значимостью <= alpha (односторонний, H0: p=0.5).

    Tail P(X>=k | 0.5) монотонно убывает по k: минимальное k с tail <= alpha
    — это порог значимости, а не максимум (k=n всегда даёт наименьший tail).
    """
    for k in range(1, n + 1):
        if binom_tail(n, k, 0.5) <= alpha:
            return k
    return n + 1  # недостижимо


def power_measure():
    """P1: точные биномиальные величины для модели знакового теста."""
    rows = {}
    ks12 = kstar(12)
    for p in (0.6, 0.7, 0.8, 0.85, 0.87, 0.9):
        rows["p=%.2f" % p] = round(binom_tail(12, ks12, p), 4)
    # N_required для p=0.7 при 80% мощности, односторонний alpha=0.05.
    n_req = None
    for n in range(5, 400):
        k = kstar(n)
        if k <= n and binom_tail(n, k, 0.7) >= 0.80:
            n_req = n
            break
    ci = {}
    for n in (9, 14, 19):
        ci["%d/%d" % (n, n)] = {
            "clopper_pearson_lb_2sided": round(0.025 ** (1.0 / n), 4),
            "wilson_lb_2sided": round(n / (n + Z95 ** 2), 4),
        }
    pvalues = {"9/9": 2 * 0.5 ** 9, "14/14": 2 * 0.5 ** 14, "19/19": 2 * 0.5 ** 19}
    return {
        "kstar_for_n12": ks12,
        "alpha_at_kstar_n12": round(binom_tail(12, ks12, 0.5), 5),
        "power_n12": rows,
        "n_required_p07_power80": n_req,
        "ci_lower_bounds": ci,
        "published_pvalues_reproduced": {k: round(v, 7) for k, v in pvalues.items()},
    }


# ---------------------------------------------------------------- P2: скан пробы

def scan_probe():
    """P2: мягкие сигналы + маркеры классов A/B на файлах пробы."""
    files = sorted(glob.glob(os.path.join(PROBE_DIR, "*.txt")))
    if len(files) != 9:
        die("проба неполна: файлов %d (нужно 9)" % len(files))
    rows = []
    for path in files:
        rel = os.path.relpath(path, ROOT)
        proc = subprocess.run(
            [sys.executable, SCAN, "--json", "--genre", "neutral", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
        if proc.returncode != 0:
            die("scan_soft_signals упал на %s: %s" % (rel, proc.stderr[:200]))
        payload = json.loads(proc.stdout)
        report = payload[0] if isinstance(payload, list) and payload else payload
        rows.append({
            "file": os.path.relpath(path, RUN_DIR).replace("\\", "/"),
            "features_total": int(report.get("features_total", 0)),
            "categories_total": int(report.get("categories_total", 0)),
            "findings": [
                {"id": f.get("id"), "category": f.get("category"),
                 "criticality": f.get("criticality"), "count": f.get("count")}
                for f in report.get("findings", [])],
        })
    # Маркеры классов A/B: один общий прогон по всем файлам пробы.
    proc = subprocess.run(
        [sys.executable, CHECK_MARKERS, "--scan"] + files,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    return {
        "files": rows,
        "max_features": max(r["features_total"] for r in rows),
        "max_categories": max(r["categories_total"] for r in rows),
        "markers_scan_exit": proc.returncode,
        "markers_scan_output_tail": proc.stdout.strip().splitlines()[-5:],
    }


# ------------------------------------------------- P3: регистровый аудит корпуса

def register_audit():
    """P3: доля художественной классики в человеческом корпусе.

    Механика — жанровые решения threshold_sweep.py: файлы вне
    HUMAN_GENRE_OVERRIDES сканируются как fiction (художественная классика
    XIX века); оверрайды — Конституция (legal), Википедия/Даль (academic),
    Викиновости/IT-notation (neutral).
    """
    human = sorted(glob.glob(os.path.join(ROOT, tw.HUMAN_DIR, "*.txt")))
    if not human:
        die("человеческий корпус не найден")
    classic = [p for p in human
               if os.path.basename(p) not in tw.HUMAN_GENRE_OVERRIDES]
    nonfiction = [os.path.basename(p) for p in human
                  if os.path.basename(p) in tw.HUMAN_GENRE_OVERRIDES]
    return {
        "total": len(human),
        "classic_prose": len(classic),
        "classic_share": round(len(classic) / float(len(human)), 4),
        "nonfiction_files": sorted(nonfiction),
    }


# ------------------------------------------------ P4: аудит «реестр ↔ корпус»

_PLATFORM_RX = [
    ("OpenAI", ("openai", "chatgpt", "codex")),
    ("Perplexity", ("perplexity",)),
    ("Vertex AI", ("vertex",)),
    ("Gemini", ("gemini",)),
    ("Grok/xAI", ("grok", "xai")),
    ("Copilot/Bing", ("copilot", "bing")),
    ("DeepSeek", ("deepseek",)),
    ("GigaChat", ("gigachat",)),
    ("YandexGPT/Alisa", ("yandex", "alisa", "алиса")),
    ("Le Chat/Mistral", ("mistral", "le chat")),
]

_RAW_DIR_TO_FAMILY = {
    "gigachat": "GigaChat", "alisa": "YandexGPT/Alisa", "le-chat": "Le Chat/Mistral",
    "deepseek": "DeepSeek", "grok": "Grok/xAI", "gemini": "Gemini",
    "copilot": "Copilot/Bing",
}


def registry_audit():
    """P4: семейства-источники маркеров без корпусной поддержки."""
    if not os.path.isfile(MARKERS_SOURCES):
        die("нет %s" % os.path.relpath(MARKERS_SOURCES, ROOT))
    with open(MARKERS_SOURCES, encoding="utf-8") as fh:
        records = json.load(fh)
    families = {}
    for rec in records:
        platform = str(rec.get("platform", "")).lower()
        family = None
        for name, keys in _PLATFORM_RX:
            if any(k in platform for k in keys):
                family = name
                break
        if family is None:
            family = "прочие/неатрибутированные"
        families.setdefault(family, set()).add(rec.get("case"))
    raw_dirs = set()
    raw_root = os.path.join(ROOT, "research", "raw")
    for name in os.listdir(raw_root):
        if os.path.isdir(os.path.join(raw_root, name)):
            raw_dirs.add(_RAW_DIR_TO_FAMILY.get(name, name))
    unsupported = sorted(set(families) - raw_dirs)
    return {
        "marker_families": {k: sorted(v) for k, v in sorted(families.items())},
        "corpus_families": sorted(raw_dirs),
        "families_without_corpus": unsupported,
        "families_without_corpus_count": len(unsupported),
    }


def main():
    stats = {
        "script": os.path.relpath(os.path.abspath(__file__), ROOT),
        "power": power_measure(),
        "register_audit": register_audit(),
        "registry_audit": registry_audit(),
        "probe_scan": scan_probe(),
    }
    out_path = os.path.join(RUN_DIR, "evidence", "stats.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))
    p = stats["power"]
    print("P1 мощность: k*(12)=%d (alpha=%.4f); power(12,0.7)=%.4f; "
          "N_req(0.7,80%%)=%s"
          % (p["kstar_for_n12"], p["alpha_at_kstar_n12"],
             p["power_n12"]["p=0.70"], p["n_required_p07_power80"]))
    print("P1 CI: %s" % json.dumps(p["ci_lower_bounds"], ensure_ascii=False))
    r = stats["register_audit"]
    print("P3 регистр: классика %d/%d (%.1f%%)"
          % (r["classic_prose"], r["total"], 100 * r["classic_share"]))
    g = stats["registry_audit"]
    print("P4 реестр-корпус: без корпусной поддержки %d семей: %s"
          % (g["families_without_corpus_count"],
             ", ".join(g["families_without_corpus"])))
    s = stats["probe_scan"]
    print("P2 проба: max features %d, max categories %d, markers exit %d"
          % (s["max_features"], s["max_categories"], s["markers_scan_exit"]))
    for row in s["files"]:
        fired = ", ".join("%s(%s)" % (f["id"], f["criticality"])
                          for f in row["findings"]) or "чисто"
        print("  %s: features=%d [%s]" % (row["file"], row["features_total"], fired))
    print("  маркеры (последние строки): %s"
          % " | ".join(s["markers_scan_output_tail"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
