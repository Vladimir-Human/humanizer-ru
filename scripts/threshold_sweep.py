#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""threshold_sweep.py — свип порогов мягкого слоя по корпусу.

Дерево решений SKILL.md поручает мягкому слою калибровку объёма правки:
0–2 признака — не править; 3–5 признаков из двух и более категорий —
выборочная правка; 6 и более — переписывание с сохранением фактов.
Независимое измерение показало, что на всех 24 реальных ИИ-текстах
research/raw/**/*.txt ни один файл не набирает больше двух признаков,
поэтому действие дерева решений не наступает ни разу.

Скрипт проверяет этот факт и строит для каждого порога T (минимальное
число признаков) и K (минимальное число категорий) таблицу:
TP — ИИ-файлы с сигналом `features_total >= T and categories_total >= K`,
FP — человеческие файлы с тем же сигналом, precision и recall.
Boundary-файлы из eval/manifest.v1.json приводятся отдельно.

Жанр: в режиме `per-file` (по умолчанию) используется жанровое дерево
SKILL.md — художественная классика сканируется как fiction (исключает
правило трёх и плотность длинных тире), Конституция — как legal,
энциклопедические/лексикографические тексты — как academic, новости и
IT-нотация — как neutral. В режиме `neutral` все файлы сканируются как
neutral, чтобы показать, откуда берутся «единичные литературные тире».

Сканирование выполняется той же командой, что и в эксплуатации, —
`python3 scripts/scan_soft_signals.py --json --genre <жанр> <файл>`;
это надёжнее импорта функций: не зависит от внутренних договорённостей
модуля и использует ровно тот код, который описан в README.

Коды возврата: 0 — свип построен; 1 — провал самопроверки; 2 — ошибка
входа или не хватает данных. Только стандартная библиотека.

Запуск из корня репозитория:
    python3 scripts/threshold_sweep.py
    python3 scripts/threshold_sweep.py --mode neutral
    python3 scripts/threshold_sweep.py --json-out /tmp/threshold_sweep.json
    python3 scripts/threshold_sweep.py --selftest
"""
import argparse
import glob
import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCAN = os.path.join(HERE, "scan_soft_signals.py")
MANIFEST = os.path.join(ROOT, "eval", "manifest.v1.json")

AI_GLOB = "research/raw/**/*.txt"
HUMAN_DIR = "research/validation/human"
BOUNDARY_DIR = "research/validation/boundary"

# Для человеческого корпуса вне манифеста (12–26) применяются те же
# жанровые решения, что в research/validation/README.md: классика —
# художественная проза, нормативный акт — legal, энциклопедический и
# лексикографический тексты — academic, современная новость и IT-нотация —
# neutral.
HUMAN_GENRE_OVERRIDES = {
    "08-constitution.txt": "legal",
    "09-wikipedia-modern.txt": "academic",
    "10-wikinews.txt": "neutral",
    "11-it-notation.txt": "neutral",
    "26-dal-predvaritelnoe-obyasnenie.txt": "academic",
}
HUMAN_GENRE_DEFAULT = "fiction"


def human_genre_for(relpath):
    """Жанр scan_soft_signals для человеческого файла."""
    base = os.path.basename(relpath)
    return HUMAN_GENRE_OVERRIDES.get(base, HUMAN_GENRE_DEFAULT)


def scan_file(path, genre):
    """Запуск scan_soft_signals.py --json и разбор отчёта."""
    proc = subprocess.run(
        [sys.executable, SCAN, "--json", "--genre", genre, path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if proc.returncode != 0:
        raise RuntimeError("scan_soft_signals.py упал на %s: %s"
                           % (path, proc.stderr.strip()[:200]))
    payload = json.loads(proc.stdout)
    report = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(report, dict):
        raise RuntimeError("scan_soft_signals.py вернул неожиданный JSON: %s"
                           % path)
    findings = report.get("findings", [])
    return {
        "path": path,
        "genre": genre,
        "features_total": int(report.get("features_total", 0)),
        "categories_total": int(report.get("categories_total", 0)),
        "categories": report.get("categories", {}),
        "recommendation": report.get("recommendation", ""),
        "findings": [
            {
                "id": f.get("id"),
                "category": f.get("category"),
                "pattern": f.get("pattern"),
                "criticality": f.get("criticality"),
                "count": int(f.get("count", 0)),
            }
            for f in findings
        ],
        "raw_report": report,
    }


def load_boundary_paths():
    """Boundary-файлы из манифеста: ровно те, что использует лидерборд."""
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("не удалось прочитать %s: %s" % (MANIFEST, exc), file=sys.stderr)
        return None
    entries = [c for c in manifest.get("corpus", []) if c.get("kind") == "boundary"]
    return [c["path"] for c in entries]


def scan_corpus(mode):
    """Прогон всех трёх групп корпуса. Возвращает словарь или None."""
    ai_files = sorted(glob.glob(os.path.join(ROOT, AI_GLOB), recursive=True))
    human_files = sorted(glob.glob(os.path.join(ROOT, HUMAN_DIR, "*.txt")))
    boundary_files = load_boundary_paths()
    if boundary_files is None:
        return None
    if not ai_files or not human_files or not boundary_files:
        print("корпус не найден: ИИ-файлов %d, человеческих файлов %d, "
              "boundary-файлов %d" % (len(ai_files), len(human_files), len(boundary_files)),
              file=sys.stderr)
        return None
    groups = {}
    for kind, files in (
        ("ai", ai_files),
        ("human", human_files),
        ("boundary", boundary_files),
    ):
        rows = []
        for path in files:
            genre = "neutral"
            if mode == "per-file" and kind == "human":
                genre = human_genre_for(path)
            row = scan_file(path, genre)
            row["kind"] = kind
            rows.append(row)
        groups[kind] = rows
    return groups


def sweep(groups, max_t=8, max_k=4):
    """Считает TP, FP, precision, recall для каждой пары T × K."""
    ai = groups["ai"]
    humans = groups["human"]
    boundary = groups["boundary"]
    rows = []
    for t in range(1, max_t + 1):
        for k in range(1, max_k + 1):
            tp = sum(1 for r in ai
                     if r["features_total"] >= t and r["categories_total"] >= k)
            fp = sum(1 for r in humans
                     if r["features_total"] >= t and r["categories_total"] >= k)
            bd = sum(1 for r in boundary
                     if r["features_total"] >= t and r["categories_total"] >= k)
            rows.append({
                "t": t,
                "k": k,
                "tp": tp,
                "fp": fp,
                "boundary_signals": bd,
                "precision": None if tp + fp == 0 else tp / float(tp + fp),
                "recall": tp / float(len(ai)),
            })
    return rows


def _action_notes():
    """Возвращает справку о текущем дереве решений."""
    return (
        "Текущее дерево SKILL.md: действие наступает при `features_total >= 3` "
        "и `categories_total >= 2` (3–5 — выборочная правка, 6+ — "
        "переписывание); при `categories_total == 1` и `features_total >= 3` "
        "предлагается только форматная правка одной категории. Вердикт об "
        "авторстве мягкие признаки не дают никогда."
    )


def render_markdown(mode, groups, rows):
    ai = groups["ai"]
    humans = groups["human"]
    boundary = groups["boundary"]
    max_ai_features = max(r["features_total"] for r in ai)
    max_human_features = max(r["features_total"] for r in humans)
    out = []
    out.append("## Свип порогов мягкого слоя (режим `%s`)" % mode)
    out.append("")
    out.append("Корпус: %d ИИ-текста, %d человеческих текстов, "
               "%d boundary-контролей. Сканер: `scripts/scan_soft_signals.py`."
               % (len(ai), len(humans), len(boundary)))
    out.append("")
    out.append("Максимум признаков на одном файле: ИИ — %d, "
               "человек — %d, boundary — %d."
               % (max_ai_features, max_human_features,
                  max(r["features_total"] for r in boundary)))
    out.append("")
    out.append(_action_notes())
    out.append("")
    out.append("| T | K | TP (AI-файлы) | FP (human-файлы) | Precision | Recall | Boundary |")
    out.append("|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        precision = "—" if row["precision"] is None else "%.1f%%" % (row["precision"] * 100.0)
        out.append("| %d | %d | %d | %d | %s | %.1f%% | %d |"
                   % (row["t"], row["k"], row["tp"], row["fp"],
                      precision, row["recall"] * 100.0, row["boundary_signals"]))
    # Лучший достижимый порог с FP = 0.
    candidates = [r for r in rows if r["fp"] == 0 and r["tp"] > 0 and r["k"] == 2]
    out.append("")
    if candidates:
        best = max(candidates, key=lambda r: (r["recall"], r["t"]))
        out.append("Лучший порог с FP=0 и K=2: T=%d, TP=%d/%d, recall=%.1f%%, "
                   "precision=%s."
                   % (best["t"], best["tp"], len(ai),
                      best["recall"] * 100.0,
                      "100.0%" if best["precision"] is None else "%.1f%%" % (best["precision"] * 100.0)))
    else:
        out.append("Порогов с ненулевым recall и нулевым FP при K=2 нет.")
    # AI-файлы, которые зажигаются только при пороге 2.
    out.append("")
    out.append("AI-файлы с сигналом при T=2, K=2 (порог на один шаг ниже "
               "текущего):")
    out.append("")
    hits = sorted(
        [r for r in ai if r["features_total"] >= 2 and r["categories_total"] >= 2],
        key=lambda r: r["path"],
    )
    if not hits:
        out.append("- нет")
    for r in hits:
        cats = ", ".join(sorted(r["categories"]))
        rel = os.path.relpath(r["path"], ROOT).replace("\\", "/")
        out.append("- `%s` — признаков: %d, категорий: %d (%s)"
                   % (rel, r["features_total"], r["categories_total"], cats))
    out.append("")
    return "\n".join(out)


def _rel(path):
    """Путь в отчёте — относительно корня репозитория, POSIX-разделитель:
    сырые JSON попадают в git, локальные абсолютные пути туда не нужны."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def make_report(mode, groups, rows, argv):
    return {
        "script": "scripts/threshold_sweep.py",
        "mode": mode,
        "argv": argv,
        "scanner": "scripts/scan_soft_signals.py",
        "action_tree": {
            "current_action_requires_features": 3,
            "current_action_requires_categories": 2,
            "note": _action_notes(),
        },
        "corpus_counts": {
            "ai": len(groups["ai"]),
            "human": len(groups["human"]),
            "boundary": len(groups["boundary"]),
        },
        "max_features_per_file": {
            "ai": max(r["features_total"] for r in groups["ai"]),
            "human": max(r["features_total"] for r in groups["human"]),
            "boundary": max(r["features_total"] for r in groups["boundary"]),
        },
        "files": {
            "ai": [
                {
                    "path": _rel(r["path"]),
                    "genre": r["genre"],
                    "features_total": r["features_total"],
                    "categories_total": r["categories_total"],
                    "categories": r["categories"],
                    "findings": r["findings"],
                }
                for r in groups["ai"]
            ],
            "human": [
                {
                    "path": _rel(r["path"]),
                    "genre": r["genre"],
                    "features_total": r["features_total"],
                    "categories_total": r["categories_total"],
                    "categories": r["categories"],
                    "findings": r["findings"],
                }
                for r in groups["human"]
            ],
            "boundary": [
                {
                    "path": _rel(r["path"]),
                    "genre": r["genre"],
                    "features_total": r["features_total"],
                    "categories_total": r["categories_total"],
                    "categories": r["categories"],
                    "findings": r["findings"],
                }
                for r in groups["boundary"]
            ],
        },
        "sweep": rows,
    }


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    case("human_genre_for: конституция → legal",
         human_genre_for("research/validation/human/08-constitution.txt") == "legal")
    case("human_genre_for: википедия → academic",
         human_genre_for("research/validation/human/09-wikipedia-modern.txt") == "academic")
    case("human_genre_for: классика → fiction",
         human_genre_for("research/validation/human/01-turgenev-mumu.txt") == "fiction")

    groups = {
        "ai": [
            {"features_total": 2, "categories_total": 2},
            {"features_total": 1, "categories_total": 1},
            {"features_total": 0, "categories_total": 0},
        ],
        "human": [
            {"features_total": 1, "categories_total": 1},
            {"features_total": 0, "categories_total": 0},
        ],
        "boundary": [
            {"features_total": 0, "categories_total": 0},
        ],
    }
    rows = sweep(groups, max_t=3, max_k=2)
    by_key = {(r["t"], r["k"]): r for r in rows}
    case("свип: T=2,K=2 даёт TP=1, FP=0, recall=1/3",
         by_key[(2, 2)]["tp"] == 1 and by_key[(2, 2)]["fp"] == 0
         and abs(by_key[(2, 2)]["recall"] - 1.0 / 3.0) < 1e-12)
    case("свип: T=3,K=2 даёт TP=0",
         by_key[(3, 2)]["tp"] == 0)
    case("свип: T=1,K=1 даёт TP=2, FP=1",
         by_key[(1, 1)]["tp"] == 2 and by_key[(1, 1)]["fp"] == 1
         and abs(by_key[(1, 1)]["precision"] - 2.0 / 3.0) < 1e-12)
    case("свип: boundary считается отдельно",
         by_key[(1, 1)]["boundary_signals"] == 0)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Свип порогов мягкого слоя по корпусу.")
    ap.add_argument("--mode", choices=("per-file", "neutral"), default="per-file",
                    help="per-file — жанровые исключения SKILL.md; neutral — "
                         "все файлы как neutral (по умолчанию per-file)")
    ap.add_argument("--json-out", default=None, metavar="PATH",
                    help="записать машиночитаемый отчёт в JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    groups = scan_corpus(args.mode)
    if groups is None:
        return 2
    rows = sweep(groups)
    print(render_markdown(args.mode, groups, rows))
    if args.json_out:
        report = make_report(args.mode, groups, rows, argv)
        try:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            print("не удалось записать %s: %s" % (args.json_out, exc),
                  file=sys.stderr)
            return 2
        print("\nJSON записан: %s" % args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())