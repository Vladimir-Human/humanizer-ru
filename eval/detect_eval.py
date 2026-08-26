#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detect_eval.py — харнес измерения детектируемости «до/после».

Харнес поверх eval/detectors/: прогоняет существующие парные прогоны
eval/runs/<run>/ (source/ = «до», with/ = «после») локальными детекторами AI-текста
и строит отчёт об относительной дельте детектируемости. Детектор — ВСЕГДА
относительная метрика до/после, никогда вердикт (см. eval/README.md).

Что делает:
  1. Читает eval/runs/<run>/manifest.json (run_sha256 НЕ трогается и не меняется —
     детекторный прогон это отдельный артефакт поверх замороженного run).
  2. Для каждой пары из source/ (до) и with/ (после) — score каждым доступным
     детектором.
  3. Агрегаты: средний скор raw (до), средний скор humanized (после), средняя
     дельта, доля пар «после ниже до».
  4. ОБЯЗАТЕЛЬНАЯ секция FP-аудит: скор детектора на 11 human-текстах манифеста
     eval/manifest.v1.json (манифест читается отдельно по этому пути); score >= 0.5
     на human = ложное обвинение; блок «FP-аудит: K/11 ложных обвинений».
  5. Гейты зачёта (AUDIT H4): изменение длины на каждой паре — пары, где after
     длиннее before более чем на 20%, помечаются, но НЕ исключаются (new_facts уже
     проверен blind_eval).
  6. Вывод: JSON-отчёт {detector: {model, version}, pairs, aggregates, fp_audit} +
     человекочитаемая сводка. Модель и её версия (из /api/tags) — ОБЯЗАТЕЛЬНО.
  7. Ноль доступных детекторов -> exit 2 с сообщением «нет доступных детекторов:
     отчёт не создан» (fail-closed, НЕ пустой отчёт).
  8. --selftest: без аргументов проверяет детерминированную логику агрегации
     (фабричные scores) и формат FP-блока; умеет падать; НЕ требует Ollama.

CLI:
  python eval/detect_eval.py <run_dir> [--detectors llm[,ppl]] [--perplexity]
                                [--json out.json]
  python eval/detect_eval.py --selftest

Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from detectors import collect

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = "eval/manifest.v1.json"
LENGTH_OVER_THRESHOLD = 1.20   # after длиннее before более чем на 20%
HUMAN_REGRESSION_DELTA = 0.1   # человеческие пары: рост скора > +0.1 — warning
FP_THRESHOLD = 0.5             # score >= 0.5 на human = ложное обвинение


# ------------------------------------------------------------------ модели данных

def read_text(path: str) -> str:
    """Читает текст файла как UTF-8 (errors=replace — не роняет на испорченном)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def load_run_manifest(run_dir: str) -> dict:
    """Читает manifest.json прогона (read-only). Ошибка — RuntimeError.

    run_sha256 не трогаем: детекторный прогон отдельный артефакт поверх
    замороженного run, никакой записи в файл здесь нет."""
    path = os.path.join(run_dir, "manifest.json")
    if not os.path.isfile(path):
        raise FileNotFoundError("нет manifest.json прогона: %s" % path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("manifest.json прогона — не объект: %s" % path)
    return data


def list_pairs(run_dir: str, manifest: dict) -> list[dict]:
    """Список пар [{id, kind}] из манифеста; fallback — сверка имён source/with.

    Приоритет — поле pairs манифеста run'а (там есть kind для гейтов H5). Если
    его нет, берём общие имена файлов из source/ и with/ c kind=None."""
    raw = manifest.get("pairs")
    if isinstance(raw, list):
        out = []
        for p in raw:
            if not isinstance(p, dict) or not str(p.get("id", "")).strip():
                continue
            out.append({"id": str(p["id"]), "kind": p.get("kind")})
        if out:
            return out
    src = os.path.join(run_dir, "source")
    wth = os.path.join(run_dir, "with")
    common = []
    if os.path.isdir(src) and os.path.isdir(wth):
        for name in sorted(os.listdir(src)):
            if name.endswith(".txt") and os.path.isfile(os.path.join(wth, name)):
                common.append({"id": name[:-4], "kind": None})
    return common


def load_human_texts(manifest_path: str = DEFAULT_MANIFEST) -> list[dict]:
    """Читает human-тексты манифеста: [{path, text}]. Пусто при отсутствии файла.

    Манифест детекторного прогона читается ОТДЕЛЬНО от run-manifest — FP-аудит
    всегда на одном и том же нейтральном человеческом корпусе (11 текстов)."""
    if not os.path.isfile(manifest_path):
        return []
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    out = []
    if not isinstance(data, dict):
        return out
    for entry in data.get("corpus", []):
        if not isinstance(entry, dict) or entry.get("kind") != "human":
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel.strip():
            continue
        path = os.path.normpath(os.path.join(ROOT, rel))
        if not os.path.isfile(path):
            continue
        out.append({"path": rel, "text": read_text(path)})
    return out


# ------------------------------------------------------------------ чистая логика

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def eval_pair_block(run_dir, pair, first_text, second_text):
    """Собирает per-pair запись с длинами и length-флагом (без скора)."""
    len_before = len(first_text)
    len_after = len(second_text)
    flag = None
    if len_before > 0 and len_after > len_before * LENGTH_OVER_THRESHOLD:
        flag = "after_longer_20pct"
    return {
        "id": pair["id"],
        "kind": pair.get("kind"),
        "len_before": len_before,
        "len_after": len_after,
        "length_flag": flag,
    }


def _mean(values):
    values = [v for v in values if v is not None]
    return (sum(values) / len(values)) if values else None


def aggregate(pairs_with_scores):
    """Чистые агрегаты из списка пар {id, kind, before, after, delta, length_flag}.

    Детерминированная функция агрегации — то же самое, что зовёт прогон;
    selftest проверяет её фабричными scores без сети."""
    complete = [p for p in pairs_with_scores
                if p.get("before") is not None and p.get("after") is not None]
    n_pairs = len(pairs_with_scores)
    mean_before = _mean([p.get("before") for p in pairs_with_scores])
    mean_after = _mean([p.get("after") for p in pairs_with_scores])
    mean_delta = _mean([p.get("delta") for p in pairs_with_scores])
    frac_after_lower = None
    if complete:
        frac_after_lower = sum(1 for p in complete if p["after"] < p["before"]) / len(complete)

    # Гейты зачёта H5 (текстовые поля отчёта, не exit-коды).
    warnings = []
    npair_regression = 0
    for p in pairs_with_scores:
        kind = p.get("kind")
        if kind == "ai" and p.get("delta") is not None and p["delta"] > 1e-9:
            p["regression"] = True
            npair_regression += 1
    if npair_regression:
        warnings.append("регрессия на %d AI-паре(ах): после правки скор вырос "
                        "(дельта > 0), направление не то" % npair_regression)

    human = [p.get("delta") for p in pairs_with_scores
             if p.get("kind") == "human" and p.get("delta") is not None]
    human_mean_delta = _mean(human)
    if human_mean_delta is not None and human_mean_delta > HUMAN_REGRESSION_DELTA:
        warnings.append("внимание: на human-парах скор после правки систематически "
                        "растёт (средняя дельта %.3f > +0.1) — правка делает живое "
                        "«машиннее»" % human_mean_delta)

    # Учёт длины: только пометка, не исключение.
    length_flags = [p["id"] for p in pairs_with_scores if p.get("length_flag")]

    return {
        "n_pairs": n_pairs,
        "n_scored_both": len(complete),
        "mean_before": mean_before,
        "mean_after": mean_after,
        "mean_delta": mean_delta,
        "frac_after_lower": frac_after_lower,
        "human_pairs_mean_delta": human_mean_delta,
        "length_flags": length_flags,
        "warnings": warnings,
    }


def fp_audit(detector, human_texts):
    """FP-аудит детектора на human-текстах манифеста.

    Возвращает {"n", "false_accusations", "false_rate", "details"} — блок отчёта.
    score >= FP_THRESHOLD (0.5) на человеческом тексте = ложное обвинение."""
    details = []
    false_count = 0
    for item in human_texts:
        sc = detector.score(item["text"])
        if sc is None:
            # Недоступность на позиции не обвинение, но и не молчаливая норма:
            # помечаем в details, чтобы блок был честным.
            details.append({"file": item["path"], "score": None})
            continue
        sc = clamp01(sc)
        is_fp = sc >= FP_THRESHOLD
        if is_fp:
            false_count += 1
        details.append({"file": item["path"], "score": round(sc, 4),
                        "false_accusation": is_fp})
    n = len(human_texts)
    return {
        "n": n,
        "false_accusations": false_count,
        "false_rate": (false_count / n) if n else None,
        "threshold": FP_THRESHOLD,
        "details": details,
    }


def fp_audit_line(audit: dict) -> str:
    """Человекочитаемая строка блока FP-аудита."""
    return "FP-аудит: %d/%d ложных обвинений (порог скор >= %.2f)" % (
        audit["false_accusations"], audit["n"], FP_THRESHOLD)


# ------------------------------------------------------------------ прогон

def run_detect(run_dir: str, detectors, human_texts,
               manifest_path: str = DEFAULT_MANIFEST) -> dict:
    """Полный детекторный прогон одного run всеми detectors.

    Возвращает структуру отчёта верхнего уровня. detectors — список Detector,
    каждый обрабатывается независимо на одних и тех же парах."""
    manifest = load_run_manifest(run_dir)
    pairs = list_pairs(run_dir, manifest)
    src_dir = os.path.join(run_dir, "source")
    wth_dir = os.path.join(run_dir, "with")

    by_det = {}
    for det in detectors:
        pair_records = []
        for p in pairs:
            sid = p["id"]
            src = os.path.join(src_dir, sid + ".txt")
            wth = os.path.join(wth_dir, sid + ".txt")
            if not (os.path.isfile(src) and os.path.isfile(wth)):
                continue
            first = read_text(src)
            second = read_text(wth)
            rec = eval_pair_block(run_dir, p, first, second)
            before = det.score(first) if det.available() else None
            after = det.score(second) if det.available() else None
            rec["before"] = before
            rec["after"] = after
            rec["delta"] = (after - before) if (before is not None and after is not None) else None
            pair_records.append(rec)

        audit = fp_audit(det, human_texts)
        flat = {
            "detector": det.describe(),
            "pairs": pair_records,
            "aggregates": aggregate(pair_records),
            "fp_audit": audit,
        }
        by_det[det.name] = flat

    # Один детектор — плоский отчёт по схеме задачи; несколько — словарь results.
    base = {"run": os.path.basename(run_dir.rstrip("/\\")),
            "created": _today(), "manifest": manifest_path}
    if len(by_det) == 1:
        det = next(iter(by_det.values()))
        report = dict(base)
        report.update(det)
        return report
    base["results"] = by_det
    return base


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def format_summary(report: dict) -> str:
    """Человекочитаемая сводка из отчёта (лист, один или несколько детекторов)."""
    lines = []
    title = "Детектор-харнес «до/после» — run %s" % report.get("run", "?")
    lines.append(title)
    lines.append("-" * len(title))
    entries = report["results"].values() if "results" in report else [report]
    for flat in entries:
        det = flat["detector"]
        model = det.get("model") or "n/a"
        version = det.get("version") or "n/a"
        lines.append("Детектор: %s (модель %s, версия %s)" % (det.get("name"), model, version))
        agg = flat["aggregates"]
        lines.append("  скор «до»:    %s" % _fmt(agg.get("mean_before")))
        lines.append("  скор «после»: %s" % _fmt(agg.get("mean_after")))
        lines.append("  средняя дельта:      %s" % _fmt(agg.get("mean_delta")))
        lines.append("  доля пар «после ниже до»: %s" % _fmt(agg.get("frac_after_lower")))
        audit = flat["fp_audit"]
        lines.append("  " + fp_audit_line(audit))
        for p in flat["pairs"]:
            marks = []
            if p.get("length_flag"):
                marks.append("length+20%%")
            if p.get("regression"):
                marks.append("регрессия")
            m = (" [%s]" % (", ".join(marks))) if marks else ""
            lines.append("    %-24s %s -> %s%s" % (
                (p.get("kind") or "?") + ":" + p["id"],
                _fmt(p.get("before")), _fmt(p.get("after")), m))
        for w in agg.get("warnings", []):
            lines.append("  WARNING: %s" % w)
        lines.append("")
    return "\n".join(lines).rstrip()


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    return "%.3f" % value


# ------------------------------------------------------------------ main/CLI

# Канонические имена детекторов (d.name) и их CLI-шорткаты.
_DETECTOR_ALIASES = {"llm": "ollama_llm", "ppl": "ollama_ppl",
                     "ttr": "ttr_lexdiv"}


def parse_detector_names(raw: str | None, perplexity: bool) -> set[str]:
    """Множество КАНОНИЧЕСКИХ имён разрешённых детекторов.

    CLI-шорткаты llm/ppl/ttr переводятся в d.name (ollama_llm/ollama_ppl/
    ttr_lexdiv); полные имена принимаются как есть. --perplexity добавляет ppl."""
    allowed = set()
    if raw:
        for part in raw.split(","):
            part = part.strip().lower()
            if not part:
                continue
            allowed.add(_DETECTOR_ALIASES.get(part, part))
    if not allowed:
        allowed.add("ollama_llm")  # дефолт — LLM-рубрика
    if perplexity:
        allowed.add("ollama_ppl")
    return allowed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Измерение детектируемости «до/после» на парных прогонах.")
    ap.add_argument("run_dir", nargs="?", help="eval/runs/<run> — каталог прогона")
    ap.add_argument("--detectors", default="llm",
                    help="имя детекторов через запятую: llm[,ppl][,ttr]"
                         " (по умолчанию llm; ttr — stdlib-прокси ttr_lexdiv)")
    ap.add_argument("--perplexity", action="store_true",
                    help="включить приближённую перплексию (ollama_ppl)")
    ap.add_argument("--json", help="путь для записи JSON-отчёта")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST,
                    help="манифест FP-аудита (по умолчанию eval/manifest.v1.json)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.run_dir:
        print("укажите eval/runs/<run> (или --selftest)", file=sys.stderr)
        return 2

    # Изолируем импорты детекторов без сети до того, как считать available.
    allowed = parse_detector_names(args.detectors, args.perplexity)
    detectors = [d for d in collect(include_ppl=True) if d.name in allowed]
    if not detectors:
        print("нет доступных детекторов: отчёт не создан", file=sys.stderr)
        return 2

    human_texts = load_human_texts(args.manifest)
    if not human_texts:
        print("FP-аудит невозможен: в %s нет human-текстов" % args.manifest,
              file=sys.stderr)
        return 2

    try:
        report = run_detect(args.run_dir, detectors, human_texts, args.manifest)
    except (OSError, ValueError) as exc:
        print("ОТКАЗ: %s" % exc, file=sys.stderr)
        return 2

    print(format_summary(report))
    if args.json:
        out = os.path.abspath(args.json)
        if os.path.dirname(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("JSON-отчёт: %s" % out)
    return 0


# ------------------------------------------------------------------ selftest

class _FakeDetector:
    """Фейковый детектор с детерминированными scores — для selftest без Ollama.

    score(text) возвращает фиксированное/формульное значение; available()=True.
    Используется только в selftest (детерминированная логика агрегации и формат FP)."""
    def __init__(self, score_map=None, factory=None, name="fake"):
        self.name = name
        self._map = score_map or {}
        self._factory = factory or (lambda text: 0.5)
    def available(self):
        return True
    def score(self, text):
        key = _key_of(text)
        if key in self._map:
            return self._map[key]
        return self._factory(text)
    def model_name(self):
        return self.name + "-model"
    def model_version(self):
        return "fake-v1"
    def describe(self):
        return {"name": self.name, "model": self.model_name(), "version": self.model_version()}


_FEED_KEY = "__feedkey__"


def _key_of(text):
    # Для фейка: если текст начинается со служебного тега, это ключ; иначе срез.
    if text.startswith(_FEED_KEY):
        return text[len(_FEED_KEY):].strip()
    return text[:32]


def _make_human_texts(names):
    return [{"path": n, "text": _FEED_KEY + " " + n} for n in names]


def _make_run(tmp, pairs):
    """Создаёт временный run-каталог с source/with и manifest.json."""
    run_dir = os.path.join(tmp, "run")
    os.makedirs(os.path.join(run_dir, "source"))
    os.makedirs(os.path.join(run_dir, "with"))
    manifest_pairs = []
    for p in pairs:
        sid = p["id"]
        bb = _FEED_KEY + " " + sid + " before"
        aa = _FEED_KEY + " " + sid + " after"
        with open(os.path.join(run_dir, "source", sid + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(bb)
        with open(os.path.join(run_dir, "with", sid + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(aa)
        manifest_pairs.append({"id": sid, "kind": p["kind"]})
    with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"run": "selftest", "pairs": manifest_pairs}, fh, ensure_ascii=False)
    return run_dir


def selftest() -> int:
    import shutil
    import tempfile

    # Проверяемые данные: длины фейковых текстов подбираем так, чтобы один
    # «after» был на >20% длиннее «before» (флаг длины), остальные — нет.
    longer_pair = _FEED_KEY + " ai1 before"
    # after-текст сделаем длинным: добавляем 40 пробелов, чтобы len_after > 1.2*len_before.
    long_after = _FEED_KEY + " ai1 after" + " " * 80

    def run_agg():
        pairs_with_scores = [
            {"id": "ai1", "kind": "ai", "before": 0.9, "after": 0.4, "delta": -0.5,
             "length_flag": "after_longer_20pct"},
            {"id": "ai2", "kind": "ai", "before": 0.8, "after": 0.8, "delta": 0.0,
             "length_flag": None},
            {"id": "human1", "kind": "human", "before": 0.2, "after": 0.15, "delta": -0.05,
             "length_flag": None},
        ]
        return aggregate(pairs_with_scores)

    agg = run_agg()

    results = []
    # CLI-шорткаты -> канонические имена детекторов (b. детектор найден).
    ok = parse_detector_names("llm", False) == {"ollama_llm"}
    results.append(("CLI: 'llm' разрешает ollama_llm", ok))
    ok = parse_detector_names("llm,ppl", True) == {"ollama_llm", "ollama_ppl"}
    results.append(("CLI: 'llm,ppl' + --perplexity разрешает оба", ok))
    ok = parse_detector_names(None, False) == {"ollama_llm"}
    results.append(("CLI: дефолт = ollama_llm", ok))
    # Числовые проверки агрегации: средние по ВСЕМ полным парам.
    # mean_before = (0.9+0.8+0.2)/3, mean_after = (0.4+0.8+0.15)/3,
    # mean_delta = (-0.5+0.0-0.05)/3, frac_after_lower = 2/3 (ai1, human1).
    ok = (abs(agg["mean_before"] - (0.9 + 0.8 + 0.2) / 3) < 1e-9
          and abs(agg["mean_after"] - (0.4 + 0.8 + 0.15) / 3) < 1e-9
          and abs(agg["mean_delta"] - (-0.5 + 0.0 - 0.05) / 3) < 1e-9)
    results.append(("агрегация: средние скора/дельты посчитаны верно", ok))
    ok = abs(agg["frac_after_lower"] - 2 / 3) < 1e-9  # ai1 и human1 ниже
    results.append(("агрегация: доля пар «после ниже до»", ok))
    ok = agg["length_flags"] == ["ai1"]
    results.append(("агрегация: флаг длины 20% собран", ok))
    ok = any("регрессия" in w for w in agg["warnings"])
    results.append(("агрегация: нет регрессии (все дельты <= 0)", not ok))
    # Отдельно проверяем, что детектор умеет ЛОВИТЬ регрессию (умеет падать):
    bad_agg = aggregate([
        {"id": "aiX", "kind": "ai", "before": 0.4, "after": 0.7, "delta": 0.3,
         "length_flag": None},
    ])
    ok = bad_agg["warnings"] and any("регрессия" in w for w in bad_agg["warnings"])
    results.append(("гейт: регрессия на AI-паре ловится", ok))

    # Human-пара: систематический рост скора -> warning.
    hun_agg = aggregate([
        {"id": "h", "kind": "human", "before": 0.1, "after": 0.3, "delta": 0.2,
         "length_flag": None},
    ])
    ok = any("human" in w for w in hun_agg["warnings"])
    results.append(("гейт: рост скора на human-парах -> warning", ok))

    # FP-аудит: детерминированный формат блока.
    audit = fp_audit(_FakeDetector(score_map={"h1.txt": 0.1, "h2.txt": 0.9, "h3.txt": 0.3}),
                     _make_human_texts(["h1.txt", "h2.txt", "h3.txt"]))
    ok = (audit["false_accusations"] == 1 and audit["n"] == 3
          and audit["false_rate"] == 1 / 3)
    results.append(("FP-аудит: ровно h2.txt — ложное обвинение", ok))
    line = fp_audit_line(audit)
    ok = line == "FP-аудит: 1/3 ложных обвинений (порог скор >= 0.50)"
    results.append(("FP-аудит: формат строки блока", ok))

    # None от детектора (недоступность позиции) не роняет агрегаты и не обвинение.
    audit_none = fp_audit(_FakeDetector(factory=lambda t: None),
                          _make_human_texts(["h1.txt"]))
    ok = (audit_none["false_accusations"] == 0 and audit_none["details"][0]["score"] is None)
    results.append(("FP-аудит: score=None не считается ложным обвинением", ok))

    # Полный путь прогона на временном run без сети (фейковый детектор).
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _make_run(tmp, [
            {"id": "ai1", "kind": "ai"},
            {"id": "ai2", "kind": "ai"},
            {"id": "human1", "kind": "human"},
        ])
        # after-текст ai1 делаем длинным поверх: длиннее before на >20%.
        src = os.path.join(run_dir, "source", "ai1.txt")
        wth = os.path.join(run_dir, "with", "ai1.txt")
        before_txt = read_text(src)
        after_txt = read_text(wth)
        with open(wth, "w", encoding="utf-8") as fh:
            fh.write(after_txt + " " * 100)
        fake = _FakeDetector(score_map={
            "ai1 before": 0.9, "ai1 after": 0.4,
            "ai2 before": 0.8, "ai2 after": 0.7,
            "human1 before": 0.2, "human1 after": 0.15,
        })
        human_texts = _make_human_texts(["h1.txt", "h2.txt", "h3.txt"])
        rep = run_detect(run_dir, [fake], human_texts, "tmp-manifest.json")
        ok = (rep["detector"]["model"] == "fake-model"
              and len(rep["pairs"]) == 3
              and rep["aggregates"]["frac_after_lower"] == 1.0
              and "ai1" in rep["aggregates"]["length_flags"])
        results.append(("прогон: полный отчёт без сети (фейк), плоская схема", ok))
        # Пары без обоих скоров не дают средних значений.
        rep_none = run_detect(run_dir, [_FakeDetector(factory=lambda t: None)],
                              human_texts, "tmp-manifest.json")
        ok = (rep_none["aggregates"]["mean_before"] is None
              and rep_none["aggregates"]["frac_after_lower"] is None)
        results.append(("прогон: all-None не роняет отчёт (mean=n/a)", ok))

    # Отчёт нескольких детекторов -> словарь results.
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _make_run(tmp, [{"id": "p1", "kind": "ai"}])
        rep_multi = run_detect(run_dir, [
            _FakeDetector(score_map={"p1 before": 0.9, "p1 after": 0.5}, name="fake_a"),
            _FakeDetector(score_map={"p1 before": 0.9, "p1 after": 0.5}, name="fake_b"),
        ], _make_human_texts(["h.txt"]), "tmp-manifest.json")
        ok = ("results" in rep_multi and len(rep_multi["results"]) == 2
              and set(rep_multi["results"]) == {"fake_a", "fake_b"})
        results.append(("прогон: несколько детекторов -> results{name: flat}", ok))

    passed = sum(1 for _n, ok in results if ok)
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
