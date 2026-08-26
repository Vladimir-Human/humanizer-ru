#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ainl_calibration.py — корпусная калибровка мягких маркеров на AINL-Eval 2025.

Адаптация подхода из клона ilyautov/humanizer-ru (eval/ainl_calibration.py и
eval/AINL-CALIBRATION.md, автор идеи — Владимир «ilyautov»). Чужое измерение
приведено в research/calibration/README.md; этот скрипт делает наше.

Корпус. AINL-Eval 2025 (shared task конференции AINL, организаторы
iis-research-team): 35 158 русских научных аннотаций с разметкой по автору —
`human` (8769), `gpt-4-turbo` (8801), `gemma-2-27b` (8790), `llama-3.3-70b`
(8798). Это первая возможность померить ложные срабатывания наших мягких
маркеров на живом русском в масштабе.

Что считает. Для каждой из двух жанровых настроек (`neutral` и `academic`)
и каждого класса — долю ДОКУМЕНТОВ, на которых сработал каждый выбранный
детектор scan_soft_signals.py:
  * bureaucratese  (#8  канцелярит)            — маркер «канцелярит»
  * est_avoidance  (#11 избегание «есть/это»)  — маркер «является»
  * emdash_bold    (#16 тире и жирный)         — маркер «тире»
  * significance   (#2  раздувание значимости) — маркер «играет важную роль»
  * inanimate_intent(#6b неодушевлённый субъект)
Доля на «человеке» — ложные срабатывания (FP по-человеку), доля на машинах —
recall, отношение AI/чел — разделяющая сила маркера. Эффект жанрового
глушения — разница между neutral и academic в доле документов, где сработал
хотя бы один из выбранных детекторов (аналог «strict_any_ban_pct» →
«academic_any_ban_pct» у ilyautov).

Лицензионный режим. У выгрузки организаторов нет файла лицензии, поэтому в
репозиторий едут только числа (отчёт research/calibration/ainl-2025-<дата>.md).
Сам корпус качается во временную папку tempfile.gettempdir() и не коммитится.
Машинный JSON печатается в stdout (можно перенаправить), human-readable отчёт
пишется в research/calibration/.

Честный отказ. Если корпус недоступен (нет сети / 404 / пустой файл) — код
возврата 2 и текст, как скачать вручную, БЕЗ подделки чисел. См.
research/calibration/README.md, раздел «Воспроизведение».

Запуск (из корня репозитория):
    python eval/ainl_calibration.py                  # train, скачает во временную папку
    python eval/ainl_calibration.py --genre academic # по умолчанию обе (neutral, academic)
    python eval/ainl_calibration.py --csv путь.csv   # взять готовый CSV вместо скачивания
    python eval/ainl_calibration.py --limit 4000     # быстрый прогон на выборке
    python eval/ainl_calibration.py --selftest       # автономная самопроверка (без сети)
    python eval/ainl_calibration.py --help

Требуется сеть при первом запуске. В CI не гоняется: внешний источник,
~100 МБ трафика (два режима, полный train) и несколько минут работы.
Только стандартная библиотека (нет pip-зависимостей сверх stdlib).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from scan_soft_signals import GENRES, analyze  # noqa: E402

# Источники корпуса: первичный — GitHub raw (ровно как у ilyautov), вторичный —
# канонический датасет организаторов на HuggingFace. Оба ведут к train.csv.
PRIMARY_BASE = "https://raw.githubusercontent.com/iis-research-team/AINL-Eval-2025/main/data/"
HF_RESOLVE = "https://huggingface.co/datasets/iis-research-team/AINL-Eval-2025/resolve/main/"
SPLITS = {"train": "train.csv", "dev": "dev_full.csv"}
LABEL_ALIASES = {"abstract": "human"}
CACHE_STEM = "ainl_calibration_{split}.csv"

# Выбранные детекторы для калибровки (id в REGISTRY scan_soft_signals.py).
# Соответствие маркеру из отчёта ilyautov указано в docstring. Детектор
# «сработал на документе», если его id присутствует в report["findings"].
SELECTED = [
    "bureaucratese",      # канцелярит
    "est_avoidance",      # является
    "emdash_bold",        # тире
    "significance",       # играет важную роль / раздувание значимости
    "inanimate_intent",   # неодушевлённый субъект
]
GENRES_TO_RUN = ("neutral", "academic")


def _human_url_kind() -> str:
    """Возвращает каноническую справку об источнике для сообщений об ошибке."""
    return ("https://github.com/iis-research-team/AINL-Eval-2025 "
            "(файлы data/train.csv и data/dev_full.csv; тот же датасет на "
            "HuggingFace: https://huggingface.co/datasets/iis-research-team/"
            "AINL-Eval-2025)")


def _urls_for(split: str) -> list[str]:
    name = SPLITS[split]
    return [PRIMARY_BASE + name, HF_RESOLVE + name]


def _download(url: str, dest: Path) -> bool:
    """Качает url в dest с таймаутом; True — успех, False — сеть/404."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "humanizer-ru-ainl-calibration"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (фикс https)
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
        return False
    if not data:
        return False
    dest.write_bytes(data)
    return True


def _obtain_csv(split: str, limit: int | None) -> Path | None:
    """Возвращает путь к CSV корпуса, скачав во временную папку.

    None — корпус недоступен (все источники упали). Корпус НЕ кладётся в
    репозиторий: только tempfile каталог.
    """
    cache = Path(tempfile.gettempdir()) / CACHE_STEM.format(split=split)
    if cache.exists():
        return cache
    for url in _urls_for(split):
        print("[скачиваю] %s -> %s" % (url, cache), file=sys.stderr)
        if _download(url, cache):
            return cache
    return None


def _load(csv_path: Path, limit: int | None) -> list[dict]:
    csv.field_size_limit(10 ** 7)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:limit] if limit else rows


def _class_stats(rows: list[dict]):
    """Проверяет целостность разметки и возвращает классы и totals."""
    labels = [LABEL_ALIASES.get(r.get("label", ""), r.get("label", "")) for r in rows]
    all_labels = {lb for lb in labels if lb}
    if "human" not in all_labels:
        return None, None
    classes = ["human"] + sorted(all_labels - {"human"})
    totals = defaultdict(int)
    for lb in labels:
        if lb:
            totals[lb] += 1
    return classes, dict(totals)


def _run_detector_stats(rows: list[dict], classes: list[str], totals: dict):
    """Считает per-document срабатывания выбранных детекторов в обоих жанрах.

    Возвращает (doc_hits, any_fired, soft_per_doc):
      doc_hits[genre][detector_id][cls] -> число документов, где сработал
      any_fired[genre][cls]             -> число документов, где сработал
                                           хотя бы один выбранный детектор
      soft_per_doc[genre][cls]          -> список features_total по документам
    """
    doc_hits = {g: defaultdict(lambda: defaultdict(int)) for g in GENRES_TO_RUN}
    any_fired = {g: defaultdict(int) for g in GENRES_TO_RUN}
    soft_per_doc = {g: defaultdict(list) for g in GENRES_TO_RUN}
    sel = set(SELECTED)
    for i, row in enumerate(rows):
        text = (row.get("text") or "").strip()
        label = LABEL_ALIASES.get(row.get("label", ""), row.get("label", ""))
        if not text or label not in totals:
            continue
        for genre in GENRES_TO_RUN:
            try:
                report = analyze(text, genre=genre)
            except ValueError:
                continue
            fired = {f["id"] for f in report.get("findings", [])}
            for det in SELECTED:
                if det in fired:
                    doc_hits[genre][det][label] += 1
            if fired & sel:
                any_fired[genre][label] += 1
            soft_per_doc[genre][label].append(
                report.get("features_total", 0))
        if i and i % 5000 == 0:
            print("  …%d/%d" % (i, len(rows)), file=sys.stderr)
    return doc_hits, any_fired, soft_per_doc


def _detector_label(det_id: str, registry) -> str:
    for d in registry:
        if d["id"] == det_id:
            return "%s (%s)" % (d["pat"], det_id)
    return det_id


def _build_report(rows, classes, totals, registry, split, limit, args) -> dict:
    doc_hits, any_fired, soft_per_doc = _run_detector_stats(rows, classes, totals)
    present = [c for c in classes if totals.get(c)]
    ai_classes = [c for c in present if c != "human"]

    def rate(hits, marker, cls):
        t = totals.get(cls) or 0
        return 100.0 * hits[cls] / t if t else 0.0

    markers = []
    for genre in GENRES_TO_RUN:
        for det in SELECTED:
            human = rate(doc_hits[genre][det], det, "human")
            ai_means = [rate(doc_hits[genre][det], det, c) for c in ai_classes]
            ai_avg = statistics.mean(ai_means) if ai_means else 0.0
            markers.append({
                "genre": genre,
                "detector": det,
                "label": _detector_label(det, registry),
                "human_pct": round(human, 2),
                **{c: round(rate(doc_hits[genre][det], det, c), 2) for c in present},
                "ai_mean_pct": round(ai_avg, 2),
                "lift": round(ai_avg / human, 2) if human else None,
            })

    # Эффект жанрового глушения: доля документов с любым выбранным детектором.
    genre_muting = {}
    for cls in present:
        neutral = 100.0 * any_fired["neutral"][cls] / totals[cls]
        academic = 100.0 * any_fired["academic"][cls] / totals[cls]
        genre_muting[cls] = {
            "neutral_any_pct": round(neutral, 2),
            "academic_any_pct": round(academic, 2),
            "delta_pp": round(academic - neutral, 2),
        }

    soft = {
        g: {c: round(statistics.mean(soft_per_doc[g][c]), 2)
            for c in present if soft_per_doc[g][c]}
        for g in GENRES_TO_RUN
    }

    return {
        "source": "AINL-Eval-2025 (iis-research-team)",
        "split": split,
        "limit": limit,
        "documents": {c: totals[c] for c in present},
        "selected_detectors": SELECTED,
        "genres": GENRES_TO_RUN,
        "genre_muting_any_pct": genre_muting,
        "soft_features_per_doc": soft,
        "markers": markers,
    }


def _markdown(report: dict) -> str:
    import datetime
    today = datetime.date.today().isoformat()
    lines = [
        "# Калибровка мягких маркеров на AINL-Eval 2025",
        "",
        "Прогон: `python eval/ainl_calibration.py`, дата %s." % today,
        "Корпус: [AINL-Eval 2025](https://github.com/iis-research-team/"
        "AINL-Eval-2025), %s русских научных аннотаций."
        % sum(report["documents"].values()),
        "Корпус из репозитория исключён: файла лицензии у выгрузки нет, скрипт "
        "качает его во временную папку и оставляет здесь только числа.",
        "",
    ]
    docs = report["documents"]
    lines.append("Документов по классам: " + ", ".join(
        "%s=%d" % (c, n) for c, n in docs.items()) + ".")
    lines.append("")

    # Жанровое глушение
    lines.append("## Эффект жанрового глушения (academic vs neutral)")
    lines.append("")
    lines.append("Доля документов, где сработал хотя бы один выбранный детектор "
                 "(канцелярит / является / тире / значимость / неодушевлённый "
                 "субъект).")
    lines.append("")
    lines.append("| класс | neutral | academic | Δ, п.п. |")
    lines.append("|---|---|---|---|")
    for cls, v in report["genre_muting_any_pct"].items():
        lines.append("| %s | %s%% | %s%% | %s |" % (cls, v["neutral_any_pct"],
                    v["academic_any_pct"], v["delta_pp"]))
    lines.append("")

    # Мягкие признаки на документ
    lines.append("## Мягких признаков на документ (mean features_total)")
    lines.append("")
    cols = ["класс"] + list(GENRES_TO_RUN)
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for cls in report["documents"]:
        row = [cls]
        for g in GENRES_TO_RUN:
            row.append(str(report["soft_features_per_doc"].get(g, {}).get(cls, "—")))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # По-детекторные таблицы на каждый жанр
    for genre in GENRES_TO_RUN:
        lines.append("## Жанр `%s`: доля документов с попаданием" % genre)
        lines.append("")
        lines.append("| маркер | human | %s | AI/чел |" % " | ".join(
            c for c in report["documents"] if c != "human"))
        n_ai = sum(1 for c in report["documents"] if c != "human")
        lines.append("|" + "---|" * (3 + n_ai))
        for m in [x for x in report["markers"] if x["genre"] == genre]:
            row = [m["label"], "%.1f%%" % m["human_pct"]]
            for c in report["documents"]:
                if c == "human":
                    continue
                row.append("%.1f%%" % m[c])
            if m["lift"] is None:
                lift = "∞" if m["ai_mean_pct"] > 0 else "—"
            else:
                lift = "%.1f" % m["lift"]
            row.append(lift)
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.append("## Как это читать")
    lines.append("")
    lines.append("- Доля на `human` — ложные срабатывания: насколько часто "
                 "маркер бьёт по живому русскому в этом домене.")
    lines.append("- `AI/чел` много больше 1 — маркер различает машину и "
                 "человека; около 1 или меньше — маркер в этом домене не "
                 "разделяет классы, а то и бьёт по людям сильнее.")
    lines.append("- Сравнение `neutral` и `academic` — эффект жанрового "
                 "глушения: какие маркеры суть норма научного регистра.")
    lines.append("")
    lines.append("Метод, границы домена (научные аннотации) и чужое измерение "
                 "ilyautov — в [README.md](README.md).")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Калибровка мягких маркеров по внешнему корпусу AINL-Eval 2025; "
                    "корпус качается во временную папку, в репозиторий — только числа.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, help="локальный train.csv вместо скачивания")
    ap.add_argument("--limit", type=int, help="взять только первые N строк")
    ap.add_argument("--split", choices=sorted(SPLITS.keys()), default="train",
                    help="train (четыре класса) или dev (плюс невиданная модель `unknown`)")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "research" / "calibration" /
                            ("ainl-2025-%s.md" % _today()),
                    help="путь к Markdown-отчёту (по умолчанию research/calibration/"
                         "ainl-2025-<дата>.md)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.csv is not None:
        csv_path = args.csv
    else:
        csv_path = _obtain_csv(args.split, args.limit)
        if csv_path is None:
            print(
                "[отказ] корпус AINL-Eval 2025 недоступен (нет сети / 404).\n"
                "Скачайте вручную %s\n"
                "  train.csv   -> %s\n"
                "  dev_full.csv-> %s\n"
                "и запустите: python eval/ainl_calibration.py --csv путь\\train.csv\n"
                "Числа НЕ подделываются: без корпуса отчёт не строится."
                % (_human_url_kind(),
                   _urls_for("train")[0],
                   _urls_for("dev")[0]),
                file=sys.stderr)
            return 2

    rows = _load(csv_path, args.limit)
    classes, totals = _class_stats(rows)
    present = [c for c in classes if totals.get(c)] if classes else []
    if not classes or not present:
        print("[отказ] в %s нет человеческого класса или ни одного размеченного "
              "класса — файл повреждён или не тот. Скачайте заново %s"
              % (csv_path, _human_url_kind()), file=sys.stderr)
        return 2

    from scan_soft_signals import REGISTRY
    report = _build_report(rows, classes, totals, REGISTRY, args.split,
                           args.limit, args)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_markdown(report), encoding="utf-8")
    print("[ok] отчёт -> %s" % args.out, file=sys.stderr)
    return 0


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def selftest() -> int:
    """Автономная самопроверка без сети: проверяет связку с детекторами и
    формат отчёта на синтетическом корпусе."""
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    # 1. Адаптация умеет импортировать детекторы и знает выбранные id.
    from scan_soft_signals import REGISTRY
    ids = {d["id"] for d in REGISTRY}
    missing = [d for d in SELECTED if d not in ids]
    case("выбранные детекторы есть в REGISTRY", not missing)

    # 2. Детекторы действительно живы: образцы срабатывают.
    by_id = {d["id"]: d for d in REGISTRY}
    for det in SELECTED:
        sample = by_id[det]["pos"]
        rep = analyze(sample)
        fired = {f["id"] for f in rep["findings"]}
        case("%s: образец срабатывает" % det, det in fired)

    # 3. Жанровое глушение: academic гасит «является» (est_avoidance) и
    #    «играет важную роль» (significance) — как по SUPPRESS, так и по
    #    GENRE_PHRASE_EXCLUDES. Значимость требует min_hits=2, поэтому дадим
    #    две фразы вне исключения нейтрально, а в academic одна удаляется.
    est_sample = by_id["est_avoidance"]["pos"]
    rep_n = analyze(est_sample)
    rep_a = analyze(est_sample, genre="academic")
    fired_n = {f["id"] for f in rep_n["findings"]}
    fired_a = {f["id"] for f in rep_a["findings"]}
    case("neutral: является ловится", "est_avoidance" in fired_n)
    case("academic: является глушится", "est_avoidance" not in fired_a)

    # 4. Сводный отчёт на синтетическом корпусе строится.
    fake = [
        {"text": "Организация осуществляет деятельность в рамках реализации "
                 "программы в целях обеспечения качества. Результат знаменует "
                 "собой поворотный момент и играет ключевую роль.",
         "label": "human"},
        {"text": "Исследование подчёркивает важность. Договор отражает стремление. "
                 "Метод играет важную роль в сходимости.",
         "label": "gpt-4-turbo"},
    ]
    classes = ["human", "gpt-4-turbo"]
    totals = {"human": 2, "gpt-4-turbo": 2}
    rep = _build_report(fake, classes, totals, REGISTRY, "train", None, None)
    case("отчёт строится с обоими жанрами",
         rep["markers"] and {m["genre"] for m in rep["markers"]} == set(GENRES_TO_RUN))
    case("отчёт имеет documents и genre_muting",
         rep["documents"] and rep["genre_muting_any_pct"])

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
