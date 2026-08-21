#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_confidence.py — доверительные интервалы Уилсона для публичных долей.

Числа проекта не должны выглядеть точнее, чем они есть. «0 ложных
срабатываний на 11 человеческих текстах» — это не ноль в популяции, а
наблюдение 0/11. Скрипт пересчитывает такие доли из сырых JSON в
95% доверительные интервалы Уилсона (Wilson score interval) и печатает
markdown-таблицу.

Источники:
  - eval/results/*.json — поля summary: false_edits_with / false_edits_without
    с знаменателем pairs_human_control (ложные правки на человеческих парах);
  - research/leaderboard/*.json — human_hits / ai_hits / boundary_expected_ok
    (совпадения детекторов на нейтральном корпусе).

Флаг --check сверяет числа в LEADERBOARD.md с пересчётом из
research/leaderboard/*.json и eval/manifest.v1.json.

Коды возврата: 0 — таблицы построены и/или сверка сошлась; 1 — сверка
нашла расхождение строк лидерборда; 2 — ошибка входа или не хватает данных.
Только стандартная библиотека.

Запуск из корня репозитория:
    python3 scripts/check_confidence.py
    python3 scripts/check_confidence.py --check
    python3 scripts/check_confidence.py --selftest
"""
import argparse
import glob
import json
import math
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
Z = 1.959963984540054

EVAL_RESULTS_DIR = "eval/results"
LEADERBOARD_DIR = "research/leaderboard"
LEADERBOARD_MD = "LEADERBOARD.md"
MANIFEST = "eval/manifest.v1.json"


def wilson(k, n, z=Z):
    """95% доверительный интервал Уилсона для доли k/n.

    Возвращает (low, high) в долях единицы. При n=0 возвращает (0.0, 0.0):
    по нулю наблюдений оценивать долю нельзя.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = k / float(n)
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    margin = z / denom * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def _fmt_pct(low, high, n=None):
    def num(value):
        value = value * 100.0
        if value < 0.05:
            return "0%"
        return "%.1f%%" % value
    body = "[%s; %s]" % (num(low), num(high))
    return body if n is None else "%s (n=%d)" % (body, n)


def _load_eval_summaries():
    files = sorted(glob.glob(os.path.join(ROOT, EVAL_RESULTS_DIR, "*.json")))
    if not files:
        return None, None
    total = {"false_edits_with": 0, "false_edits_without": 0}
    denom = {"false_edits_with": 0, "false_edits_without": 0}
    runs = 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print("не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
            return None, None
        summary = data.get("summary")
        if not isinstance(summary, dict):
            continue
        n = summary.get("pairs_human_control")
        if n is None or n <= 0:
            continue
        for key in total:
            value = summary.get(key)
            if value is None:
                continue
            total[key] += int(value)
            denom[key] += int(n)
        runs += 1
    if runs == 0:
        return None, None
    return total, denom


def _load_leaderboard_records():
    files = sorted(glob.glob(os.path.join(ROOT, LEADERBOARD_DIR, "*.json")))
    records = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print("не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
            continue
        stem = os.path.basename(path).split("-")[0]
        human_hits = data.get("human_hits")
        ai_hits = data.get("ai_hits")
        boundary_ok = data.get("boundary_expected_ok")
        if human_hits is None or boundary_ok is None:
            continue
        records[stem] = {
            "file": path,
            "candidate": data.get("candidate", stem),
            "human_hits": int(human_hits),
            "ai_hits": None if ai_hits is None else int(ai_hits),
            "boundary_expected_ok": int(boundary_ok),
        }
    return records


def _boundary_total():
    try:
        with open(os.path.join(ROOT, MANIFEST), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("не удалось прочитать %s: %s" % (MANIFEST, exc), file=sys.stderr)
        return 0
    return sum(1 for c in manifest.get("corpus", []) if c.get("kind") == "boundary")


def _render_eval_table(total, denom):
    out = [
        "### Парные прогоны: ложные правки на человеческих контрольных парах",
        "",
        "| Заявление | k | n | Доля | Wilson 95% CI |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "false_edits_with": "false_edits_with — правки ветки со скиллом",
        "false_edits_without": "false_edits_without — правки ветки «LLM без скилла»",
    }
    for key in sorted(total):
        k = total[key]
        n = denom[key]
        low, high = wilson(k, n)
        out.append("| %s | %d | %d | %.1f%% | %s |"
                   % (labels[key], k, n, 100.0 * k / max(n, 1), _fmt_pct(low, high)))
    return "\n".join(out)


def _render_tables():
    parts = [
        "## Доверительные интервалы Wilson 95%",
        "",
        "Метод: Wilson score interval (z=%.4f)." % Z,
        "Пересчёт выполняется только по сырым JSON; ручных чисел нет.",
        "",
    ]
    total, denom = _load_eval_summaries()
    if total is None:
        parts.append("Парные прогоны: `false_edits_*` не найдены в "
                     "`eval/results/*.json` (нужны данные blind_eval).")
        parts.append("")
    else:
        parts.append(_render_eval_table(total, denom))
        parts.append("")

    records = _load_leaderboard_records()
    boundary_total = _boundary_total()
    if records:
        parts.append("### Лидерборд: человеческие тексты (11 файлов)")
        parts.append("")
        parts.append("| Кандидат | k | n | Доля | Wilson 95% CI |")
        parts.append("|---|---:|---:|---:|---:|")
        for stem in sorted(records):
            rec = records[stem]
            low, high = wilson(rec["human_hits"], 11)
            parts.append("| %s | %d | 11 | %.1f%% | %s |"
                         % (rec["candidate"], rec["human_hits"],
                            100.0 * rec["human_hits"] / 11.0, _fmt_pct(low, high)))
        parts.append("")
        parts.append("### Лидерборд: AI-выводы (12 файлов)")
        parts.append("")
        parts.append("| Кандидат | Значение | Wilson 95% CI |")
        parts.append("|---|---:|---:|")
        for stem in sorted(records):
            rec = records[stem]
            if rec["ai_hits"] is None:
                continue
            # smixs считает сумму всех правил, поэтому ai_hits у него > числа
            # файлов; долю и доверительный интервал по ней считать нельзя.
            if rec["ai_hits"] <= 12:
                low, high = wilson(rec["ai_hits"], 12)
                parts.append("| %s | %d / 12 | %s |"
                             % (rec["candidate"], rec["ai_hits"],
                                _fmt_pct(low, high)))
            else:
                parts.append("| %s | %d (сумма правил, не доля файлов) | — |"
                             % (rec["candidate"], rec["ai_hits"]))
        parts.append("")
        parts.append("### Лидерборд: boundary-контроли")
        parts.append("")
        parts.append("| Кандидат | k | n | Wilson 95% CI |")
        parts.append("|---|---:|---:|---:|")
        for stem in sorted(records):
            rec = records[stem]
            if boundary_total > 0:
                low, high = wilson(rec["boundary_expected_ok"], boundary_total)
                parts.append("| %s | %d | %d | %s |"
                             % (rec["candidate"], rec["boundary_expected_ok"],
                                boundary_total, _fmt_pct(low, high)))
        parts.append("")
    else:
        parts.append("Лидерборд: `research/leaderboard/*.json` не найдены.")
    return "\n".join(parts)


def _clean_cell(cell):
    return cell.strip().replace("**", "").replace("`", "").strip()


def _parse_int(cell):
    m = re.search(r"(\d+)", _clean_cell(cell))
    return int(m.group(1)) if m else None


def _parse_boundary(cell):
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", _clean_cell(cell))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _parse_leaderboard_rows(text):
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) not in (4, 5):
            continue
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        first = cells[0].lower()
        if "humanizer-ru" not in first and "smixs" not in first:
            continue
        rows.append(cells)
    return rows


def _check_leaderboard():
    path = os.path.join(ROOT, LEADERBOARD_MD)
    if not os.path.exists(path):
        print("нет %s" % path, file=sys.stderr)
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, ValueError) as exc:
        print("не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
        return None
    records = _load_leaderboard_records()
    if not records:
        print("нет research/leaderboard/*.json", file=sys.stderr)
        return None
    boundary_total = _boundary_total()
    if boundary_total <= 0:
        print("в %s нет boundary-файлов" % MANIFEST, file=sys.stderr)
        return None
    rows = _parse_leaderboard_rows(text)
    if not rows:
        print("в %s не найдена таблица лидерборда" % path, file=sys.stderr)
        return None
    mismatches = []
    for cells in rows:
        first = cells[0].lower()
        stem = "smixs" if "smixs" in first else "reference"
        rec = records.get(stem)
        if rec is None:
            mismatches.append("%s: нет JSON для %s" % (cells[0], stem))
            continue
        human_cell = cells[1]
        ci_cell = None if len(cells) == 4 else cells[2]
        ai_cell = cells[2] if len(cells) == 4 else cells[3]
        boundary_cell = cells[3] if len(cells) == 4 else cells[4]
        if _parse_int(human_cell) != rec["human_hits"]:
            mismatches.append("человеческие тексты: LEADERBOARD=%s, JSON=%d"
                              % (human_cell, rec["human_hits"]))
        if rec["ai_hits"] is not None and _parse_int(ai_cell) != rec["ai_hits"]:
            mismatches.append("AI-выводы: LEADERBOARD=%s, JSON=%d"
                              % (ai_cell, rec["ai_hits"]))
        if ci_cell is not None:
            expected_ci = _fmt_pct(*wilson(rec["human_hits"], 11))
            if ci_cell != expected_ci:
                mismatches.append("человеческие тексты CI: LEADERBOARD=%s, Wilson=%s"
                                  % (ci_cell, expected_ci))
        cell_ok, cell_total = _parse_boundary(boundary_cell)
        if cell_ok is None or cell_total != boundary_total or cell_ok != rec["boundary_expected_ok"]:
            mismatches.append("boundary: LEADERBOARD=%s, JSON=%d/%d"
                              % (boundary_cell, rec["boundary_expected_ok"], boundary_total))
    return mismatches


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    def inside(value, low, high):
        return low <= value <= high

    low, high = wilson(0, 11)
    case("wilson(0,11) нижняя граница 0", abs(low - 0.0) < 1e-12)
    case("wilson(0,11) верхняя граница ≈ 25.9%", inside(high, 0.2588, 0.2590))
    low, high = wilson(6, 11)
    case("wilson(6,11) ≈ [28.0%; 78.7%]",
         inside(low, 0.2800, 0.2801) and inside(high, 0.7872, 0.7873))
    case("wilson(n=0) не падает", wilson(0, 0) == (0.0, 0.0))
    rows = _parse_leaderboard_rows(
        "| Кандидат | Человеческие | AI | Boundary |\n"
        "|---|---|---|---|\n"
        "| [humanizer-ru](https://...) (reference, regex-слой классов A/B) | **0** | 1 | 2/2 |\n"
        "| [smixs/humanizer-ru](https://...) (линтер, коммит 91f70df) | 6 | 67 | 1/2 |\n")
    case("парсер лидерборда находит обе строки (4 колонки)", len(rows) == 2)
    rows5 = _parse_leaderboard_rows(
        "| Кандидат | Человеческие | CI | AI | Boundary |\n"
        "|---|---|---|---|---|\n"
        "| [humanizer-ru](https://...) (reference, regex-слой классов A/B) | **0** | [0%; 25.9%] | 1 | 2/2 |\n")
    case("парсер лидерборда понимает 5 колонок", len(rows5) == 1)
    case("парсер чистит **0**", _parse_int("**0**") == 0)
    case("парсер читает boundary 2/2", _parse_boundary("2/2") == (2, 2))
    low, high = wilson(0, 11)
    case("формат CI 0/11 = [0%; 25.9%]", _fmt_pct(low, high) == "[0%; 25.9%]")
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Доверительные интервалы Уилсона для публичных долей.")
    ap.add_argument("--check", action="store_true",
                    help="сверить числа LEADERBOARD.md с сырыми JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.check:
        mismatches = _check_leaderboard()
        if mismatches is None:
            return 2
        if mismatches:
            for m in mismatches:
                print("[FAIL] " + m)
            print("ЛИДЕРБОРД: расхождений с пересчётом — %d." % len(mismatches))
            return 1
        print("ЛИДЕРБОРД: все числа соответствуют сырым JSON.")
        return 0
    output = _render_tables()
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())