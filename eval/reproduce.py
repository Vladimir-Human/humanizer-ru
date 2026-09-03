#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reproduce.py — воспроизведение оси «дельта детектируемости» из открытых данных.

Протокол REPRODUCE: каждое опубликованное число оси проверяется пересчётом из
артефакта репозитория одной командой. Скрипт читает детекторный отчёт
(eval/detect-results/*.json), пересчитывает агрегаты и статистики и сверяет их
с записанными в отчёте значениями: расхождение — код 1 (число больше не
воспроизводится из данных). Новых измерений нет: это верификатор уже
опубликованных замеров, а не их источник.

Что считает и проверяет:
  1. Внутренняя согласованность отчёта: delta == after - before на каждой паре
     (допуск 1e-9); агрегаты mean_before / mean_after / mean_delta /
     frac_after_lower совпадают с пересчётом; fp_audit согласован со своими
     details (false_accusation == score >= threshold, счётчики сходятся).
  2. Статистики дельты: непараметрический бутстрап среднего по парам
     (B=100000, seed 20260831 — константы протокола, задокументированы здесь),
     percentile CI 95%; t-интервал 95% (таблица квантилей t, df<=120);
     двусторонний знак-тест (нули исключаются из n).
  3. Wilson 95% CI доли ложных обвинений FP-аудита.

Ось — ОТНОСИТЕЛЬНАЯ метрика до/после одного детектора и одной даты
(см. eval/README.md, «Принципы»): абсолютные проценты и обещания обхода
детекции скриптом не поддерживаются и не формулируются.

CLI:
  python3 eval/reproduce.py                              # флагманский отчёт llm_rubric
  python3 eval/reproduce.py eval/detect-results/<файл>.json
  python3 eval/reproduce.py --report eval/detect-results/<файл>.json  # документированная форма
  python3 eval/reproduce.py --all-reports                # сверить каждый отчёт eval/detect-results/
  python3 eval/reproduce.py <отчёт> --json out.json      # статистики в JSON
  python3 eval/reproduce.py --selftest                   # негативные кейсы, без данных

Коды возврата: 0 — отчёт воспроизводится; 1 — расхождение числа с данными;
2 — ошибка ввода (нет файла, битый JSON, нет пар). Только стандартная
библиотека; байтовая детерминированность бутстрапа обеспечена фиксированным
seed (random.Random, Mersenne Twister — платформенно-независим).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT_IMPORT = __file__  # noqa: F841 — маркер позиции файла для читателя
DEFAULT_REPORT = "eval/detect-results/2026-08-25-detect-axis-12-glm53.json"

# Константы протокола: менять = менять протокол (фиксируется в CHANGELOG).
BOOTSTRAP_B = 100_000
BOOTSTRAP_SEED = 20260831
TOL = 1e-9          # пары: delta обязана равняться after-before точно
AGG_TOL = 1e-4      # агрегаты публикуются с округлением до 4 знаков

# t-квантили 97.5%: df -> t. Для df > 120 — нормальное приближение 1.959964.
_T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021, 60: 2.000,
    120: 1.980,
}
_T_INF = 1.959964


class ReportError(Exception):
    """Структура отчёта не соответствует контракту (код 2)."""


class MismatchError(Exception):
    """Число в отчёте не воспроизводится из данных (код 1)."""


# ------------------------------------------------------------------ статистики

def bootstrap_ci(values: list[float], b: int = BOOTSTRAP_B,
                 seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """Percentile-бутстрап 95% CI среднего; детерминирован фиксированным seed."""
    if not values:
        raise ReportError("бутстрап пустого списка")
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(b):
        acc = 0.0
        for _ in range(n):
            acc += values[rng.randrange(n)]
        means.append(acc / n)
    means.sort()
    lo = means[int(0.025 * b)]
    hi = means[min(b - 1, int(0.975 * b))]
    return lo, hi


def t_interval(values: list[float]) -> tuple[float, float]:
    """t-интервал 95% для среднего (несмещённая SD)."""
    n = len(values)
    if n < 2:
        raise ReportError("t-интервал требует n>=2")
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    sd = math.sqrt(var)
    df = n - 1
    if df in _T975:
        t = _T975[df]
    elif df > 120:
        t = _T_INF
    else:
        keys = [k for k in _T975 if k <= df]
        t = _T975[max(keys)] if keys else _T_INF
    half = t * sd / math.sqrt(n)
    return mean - half, mean + half


def sign_test_two_sided(deltas: list[float]) -> tuple[int, int, float]:
    """Двусторонний знак-тест; нули исключаются. Возврат (neg, n, p)."""
    nz = [d for d in deltas if d != 0.0]
    n = len(nz)
    if n == 0:
        return 0, 0, 1.0
    neg = sum(1 for d in nz if d < 0)
    k = min(neg, n - neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return neg, n, min(1.0, 2.0 * tail)


def wilson_ci(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson 95% CI доли k/n."""
    if n <= 0:
        raise ReportError("Wilson при n=0")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


# ------------------------------------------------------------------ парсер отчёта

def load_report(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as e:
        raise ReportError(f"отчёт не читается: {e}") from e
    except json.JSONDecodeError as e:
        raise ReportError(f"отчёт не является JSON: {e}") from e
    if not isinstance(data, dict):
        raise ReportError("отчёт — не JSON-объект")
    return data


def extract_pairs(data: dict) -> tuple[list[dict], int]:
    """Валидные пары + число guard-пропусков.

    Guard-пара — любое из полей before/after/delta равно None:
    задокументированный отказ счёта для пар, где любая сторона короче
    20 токенов (note агрегатов отчёта, LEADERBOARD). Это часть данных,
    а не ошибка входа: пара исключается из статистик с явным счётчиком.
    Значение поля не число и не None (строка, bool) — порча отчёта,
    ReportError.
    """
    pairs = data.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ReportError("в отчёте нет непустого массива pairs")
    out = []
    skipped = 0
    for i, p in enumerate(pairs):
        if not isinstance(p, dict):
            raise ReportError(f"пара #{i} — не объект")
        vals = [p.get(key) for key in ("before", "after", "delta")]
        if any(v is None for v in vals):
            skipped += 1
            continue
        for key, v in zip(("before", "after", "delta"), vals):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ReportError(f"пара #{i}: поле {key} не число")
        out.append(p)
    if not out:
        raise ReportError("в отчёте нет ни одной валидной пары (все — guard)")
    return out, skipped


def validate_and_compute(data: dict) -> dict:
    """Сверка отчёта с пересчётом + все статистики. Расхождение — MismatchError."""
    pairs, guard_skipped = extract_pairs(data)
    deltas = []
    for i, p in enumerate(pairs):
        d = float(p["after"]) - float(p["before"])
        if abs(d - float(p["delta"])) > TOL:
            raise MismatchError(
                f"пара #{i} ({p.get('id', '?')}): delta={p['delta']} "
                f"!= after-before={d:.6f}")
        deltas.append(d)

    n = len(deltas)
    mean_before = sum(float(p["before"]) for p in pairs) / n
    mean_after = sum(float(p["after"]) for p in pairs) / n
    mean_delta = sum(deltas) / n
    frac_lower = sum(1 for d in deltas if d < 0) / n

    agg = data.get("aggregates") or {}
    mismatches = []
    if "mean_before" in agg and abs(agg["mean_before"] - mean_before) > AGG_TOL:
        mismatches.append(f"mean_before: {agg['mean_before']} != {mean_before:.6f}")
    if "mean_after" in agg and abs(agg["mean_after"] - mean_after) > AGG_TOL:
        mismatches.append(f"mean_after: {agg['mean_after']} != {mean_after:.6f}")
    if "mean_delta" in agg and abs(agg["mean_delta"] - mean_delta) > AGG_TOL:
        mismatches.append(f"mean_delta: {agg['mean_delta']} != {mean_delta:.6f}")
    if "frac_after_lower" in agg and abs(agg["frac_after_lower"] - frac_lower) > AGG_TOL:
        mismatches.append(
            f"frac_after_lower: {agg['frac_after_lower']} != {frac_lower:.6f}")
    if mismatches:
        raise MismatchError("агрегаты не сходятся: " + "; ".join(mismatches))

    fp = data.get("fp_audit")
    fp_stats = None
    if isinstance(fp, dict):
        details = fp.get("details")
        if not isinstance(details, list):
            raise ReportError("fp_audit.details отсутствует или не список")
        thr = fp.get("threshold", 0.5)
        acc = 0
        guard_fp = 0
        bad = []
        for j, rec in enumerate(details):
            s = rec.get("score")
            if s is None:
                # guard: текст короче порога прокси — скор не вычислен.
                # Такая запись не может быть ложным обвинением (обвинение
                # требует скора); флаг false_accusation=true при score=null
                # — рассогласование данных.
                if rec.get("false_accusation"):
                    bad.append(j)
                guard_fp += 1
                continue
            if not isinstance(s, (int, float)) or isinstance(s, bool):
                raise ReportError(f"fp_audit.details[{j}].score не число")
            expected = s >= thr
            if bool(rec.get("false_accusation")) != expected:
                bad.append(j)
            acc += int(expected)
        if bad:
            raise MismatchError(
                f"fp_audit: флаги false_accusation не согласованы со скорами "
                f"при пороге {thr} (индексы {bad})")
        if "n" in fp and int(fp["n"]) != len(details):
            raise MismatchError(
                f"fp_audit.n={fp['n']} != числу details ({len(details)})")
        if "false_accusations" in fp and int(fp["false_accusations"]) != acc:
            raise MismatchError(
                f"fp_audit.false_accusations={fp['false_accusations']} != {acc}")
        lo, hi = wilson_ci(acc, len(details))
        fp_stats = {"n": len(details), "false_accusations": acc,
                    "guard_skipped": guard_fp,
                    "threshold": thr,
                    "wilson95": [round(lo, 4), round(hi, 4)]}

    ci = bootstrap_ci(deltas)
    ti = t_interval(deltas)
    neg, n_nz, p_sign = sign_test_two_sided(deltas)
    return {
        "n_pairs": n,
        "guard_skipped": guard_skipped,
        "mean_before": round(mean_before, 4),
        "mean_after": round(mean_after, 4),
        "mean_delta": round(mean_delta, 4),
        "frac_after_lower": round(frac_lower, 4),
        "bootstrap": {"B": BOOTSTRAP_B, "seed": BOOTSTRAP_SEED,
                      "ci95_percentile": [round(ci[0], 4), round(ci[1], 4)]},
        "t_interval_95": [round(ti[0], 4), round(ti[1], 4)],
        "sign_test": {"negative_deltas": neg, "n_nonzero": n_nz,
                      "two_sided_p": round(p_sign, 6)},
        "fp_audit": fp_stats,
        "detector": data.get("detector"),
        "run": data.get("run"),
        "created": data.get("created"),
    }


def print_summary(st: dict, path: str) -> None:
    det = st.get("detector") or {}
    print(f"отчёт: {path}")
    if det:
        print(f"детектор: {det.get('name')} | модель: {det.get('model')} | "
              f"дата: {st.get('created')}")
    print(f"n пар: {st['n_pairs']}")
    if st.get("guard_skipped"):
        print(f"пар пропущено (guard, короче 20 токенов): {st['guard_skipped']}")
    print(f"средний скор до:    {st['mean_before']}")
    print(f"средний скор после: {st['mean_after']}")
    print(f"дельта (после − до): {st['mean_delta']}")
    print(f"пар «после ниже до»: {st['frac_after_lower']:.1%}")
    b = st["bootstrap"]
    print(f"бутстрап 95% CI дельты: [{b['ci95_percentile'][0]}; "
          f"{b['ci95_percentile'][1]}]  (B={b['B']}, seed={b['seed']})")
    print(f"t-интервал 95%: [{st['t_interval_95'][0]}; {st['t_interval_95'][1]}]")
    s = st["sign_test"]
    print(f"знак-тест: {s['negative_deltas']}/{s['n_nonzero']} отрицательны, "
          f"p={s['two_sided_p']}")
    if st["fp_audit"]:
        f = st["fp_audit"]
        w = f["wilson95"]
        print(f"FP-аудит: {f['false_accusations']}/{f['n']} при пороге "
              f"{f['threshold']}; Wilson 95% [{w[0]}; {w[1]}]")
        if f.get("guard_skipped"):
            print(f"  (из них guard-записей без скора: {f['guard_skipped']} — "
                  f"обвинением быть не могут)")
    print("воспроизводится из данных: да")


def all_reports(directory: str) -> int:
    """Сверка каждого отчёта каталога: rc=0, когда ВСЕ числа воспроизводимы.

    Гейт «витринная строка воспроизводится» не должен зависеть от того,
    какой именно отчёт выбран по умолчанию: проверяются все файлы
    eval/detect-results/*.json. Код 1 — хотя бы одно расхождение числа с
    данными; код 2 — хотя бы один отчёт не читается (входная ошибка).
    """
    paths = sorted(glob.glob(os.path.join(directory, "*.json")))
    if not paths:
        print(f"в каталоге нет отчётов: {directory}", file=sys.stderr)
        return 2
    mismatch = False
    input_error = False
    for path in paths:
        try:
            data = load_report(path)
            st = validate_and_compute(data)
        except ReportError as e:
            print(f"ОШИБКА ВХОДА {path}: {e}", file=sys.stderr)
            input_error = True
            continue
        except MismatchError as e:
            print(f"РАСХОЖДЕНИЕ {path}: {e}", file=sys.stderr)
            mismatch = True
            continue
        g = st.get("guard_skipped") or 0
        tail = f", guard-пропусков {g}" if g else ""
        print(f"OK {path}: n={st['n_pairs']}{tail}, дельта {st['mean_delta']}")
    ok = not (mismatch or input_error)
    print(f"воспроизводимость всех отчётов {directory}: {'да' if ok else 'НЕТ'}")
    if input_error:
        return 2
    return 1 if mismatch else 0


# ------------------------------------------------------------------ selftest

def _fixture() -> dict:
    # Константы фикстуры намеренно не совпадают с токенами реестра фактов
    # (гейт недрейфа сверяет числа витрины с реестром).
    befores = [0.9, 0.8, 0.7, 0.6, 0.85, 0.75, 0.95, 0.651, 0.55, 0.8]
    afters = [0.4, 0.3, 0.5, 0.2, 0.45, 0.35, 0.6, 0.25, 0.15, 0.5]
    pairs = []
    for i, (b, a) in enumerate(zip(befores, afters), 1):
        pairs.append({"id": f"x-{i:02d}", "kind": "ai", "before": b,
                      "after": a, "delta": round(a - b, 10)})
    mb = sum(befores) / len(befores)
    ma = sum(afters) / len(afters)
    deltas = [a - b for a, b in zip(afters, befores)]
    md = sum(deltas) / len(deltas)
    return {
        "run": "fixture", "created": "selftest",
        "detector": {"name": "fixture", "model": "none", "version": "selftest"},
        "pairs": pairs,
        "aggregates": {"mean_before": round(mb, 10), "mean_after": round(ma, 10),
                       "mean_delta": round(md, 10),
                       "frac_after_lower": sum(1 for d in deltas if d < 0) / 10},
        "fp_audit": {"n": 3, "false_accusations": 1, "threshold": 0.5,
                     "details": [{"file": "h1", "score": 0.1,
                                  "false_accusation": False},
                                 {"file": "h2", "score": 0.5,
                                  "false_accusation": True},
                                 {"file": "h3", "score": 0.3,
                                  "false_accusation": False}]},
    }


def _deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


def selftest() -> int:
    """Негативные кейсы: самопроверка обязана уметь падать."""
    failures = []

    # 1. Корректный фиксстур: все статистики считаются, сверка зелёная.
    st = validate_and_compute(_fixture())
    if st["n_pairs"] != 10 or abs(st["mean_delta"] - (-0.3851)) > 1e-9:
        failures.append("fixture: базовые агрегаты неверны")
    if st["frac_after_lower"] != 1.0:
        failures.append("fixture: frac_after_lower != 1.0")
    if st["fp_audit"]["false_accusations"] != 1:
        failures.append("fixture: score==threshold должен быть обвинением")

    # 2. Детерминизм бутстрапа: два прогона дают бит-в-бит одинаковый CI.
    d1 = bootstrap_ci([0.5, -0.2, 0.1, -0.3])
    d2 = bootstrap_ci([0.5, -0.2, 0.1, -0.3])
    if d1 != d2:
        failures.append("бутстрап недетерминирован при фиксированном seed")

    # 3. Подделанная delta в одной паре — MismatchError.
    f = _deep_copy(_fixture())
    f["pairs"][3]["delta"] = f["pairs"][3]["delta"] + 0.05
    try:
        validate_and_compute(f)
        failures.append("подделанная delta не поймана")
    except MismatchError:
        pass

    # 4. Подделанный агрегат — MismatchError.
    f = _deep_copy(_fixture())
    f["aggregates"]["mean_delta"] = -0.1
    try:
        validate_and_compute(f)
        failures.append("подделанный mean_delta не пойман")
    except MismatchError:
        pass

    # 5. fp_audit: флаг не согласован со скором — MismatchError.
    f = _deep_copy(_fixture())
    f["fp_audit"]["details"][2]["false_accusation"] = True
    try:
        validate_and_compute(f)
        failures.append("несогласованный fp-флаг не пойман")
    except MismatchError:
        pass

    # 6. Отсутствие pairs — ReportError.
    f = _deep_copy(_fixture())
    del f["pairs"]
    try:
        validate_and_compute(f)
        failures.append("отсутствие pairs не поймано")
    except ReportError:
        pass

    # 7. Wilson на граничном случае 0/11.
    lo, hi = wilson_ci(0, 11)
    if not (0.0 <= lo < hi <= 0.30):
        failures.append(f"Wilson(0/11) вне ожидаемого диапазона: {lo}, {hi}")

    # 8. Знак-тест: известное значение 11/12 отрицательных -> p=0.006348.
    neg, n_nz, p = sign_test_two_sided(
        [-0.3] * 11 + [0.05])
    if neg != 11 or n_nz != 12 or abs(p - 0.006348) > 1e-5:
        failures.append(f"знак-тест 11/12: получено {neg}/{n_nz}, p={p}")

    # 9. t-интервал симметричен вокруг среднего.
    vals = [0.1, 0.2, 0.3, 0.4]
    lo, hi = t_interval(vals)
    mid = sum(vals) / 4
    if abs((lo + hi) / 2 - mid) > 1e-12 or not (lo < mid < hi):
        failures.append("t-интервал несимметричен")

    # 10. Guard-пара (before/after/delta = None все три) пропускается со
    # счётом; статистики считаются по валидным парам.
    f = _deep_copy(_fixture())
    f["pairs"][2] = {"id": "x-03", "kind": "ai",
                     "before": None, "after": None, "delta": None}
    f["aggregates"] = {}
    st = validate_and_compute(f)
    if st["n_pairs"] != 9 or st["guard_skipped"] != 1:
        failures.append("guard-пара не пропущена или счётчик неверен")

    # 11. Частичный null (сторона короче 20 токенов) — тот же guard;
    # нечисловое значение поля (строка) — порча отчёта, ReportError.
    f = _deep_copy(_fixture())
    f["pairs"][1]["after"] = None
    f["pairs"][1]["delta"] = None
    f["aggregates"] = {}
    st = validate_and_compute(f)
    if st["n_pairs"] != 9 or st["guard_skipped"] != 1:
        failures.append("частичный null не учтён как guard")
    f = _deep_copy(_fixture())
    f["pairs"][1]["after"] = "0.3"
    try:
        validate_and_compute(f)
        failures.append("нечисловое поле пары не поймано")
    except ReportError:
        pass

    # 12. --all-reports: чистый каталог — 0, подложенное расхождение — 1
    # (негатив гейта «воспроизводимость всех отчётов»).
    import tempfile as _tf
    with _tf.TemporaryDirectory(prefix="repro-all-") as td:
        with open(os.path.join(td, "good.json"), "w", encoding="utf-8") as fh:
            json.dump(_fixture(), fh)
        if all_reports(td) != 0:
            failures.append("all_reports на чистом каталоге не дал 0")
        bad = _deep_copy(_fixture())
        bad["aggregates"]["mean_delta"] = -0.01
        with open(os.path.join(td, "bad.json"), "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        if all_reports(td) == 0:
            failures.append("all_reports не поймал подложенное расхождение")

    # 13. fp_audit: запись score=None — guard (не обвинение); Wilson по полному n.
    f = _deep_copy(_fixture())
    f["fp_audit"]["details"][1] = {"file": "h2", "score": None}
    f["fp_audit"]["false_accusations"] = 0
    st = validate_and_compute(f)
    fa = st["fp_audit"]
    if fa["false_accusations"] != 0 or fa["guard_skipped"] != 1 or fa["n"] != 3:
        failures.append("fp-guard не учтён (скор None должен быть пропуском)")

    if failures:
        print("SELFTEST FAIL:")
        for msg in failures:
            print(f"  - {msg}")
        return 1
    print("SELFTEST OK: 13/13")
    return 0


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Воспроизведение оси «дельта детектируемости» из отчёта "
                    "eval/detect-results/ (пересчёт + сверка чисел).")
    ap.add_argument("report", nargs="?", default=None,
                    help=f"путь к отчёту JSON (по умолчанию {DEFAULT_REPORT})")
    ap.add_argument("--report", dest="report_flag", metavar="ПУТЬ", default=None,
                    help="то же, что позиционный аргумент; документированная "
                         "форма команды (LEADERBOARD.md, реестр фактов)")
    ap.add_argument("--all-reports", metavar="DIR", nargs="?",
                    const="eval/detect-results", default=None,
                    help="сверить каждый *.json в DIR (по умолчанию "
                         "eval/detect-results); код 1 при расхождении любого")
    ap.add_argument("--json", metavar="OUT",
                    help="записать статистики в OUT (JSON, UTF-8)")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка без данных (негативные кейсы)")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.all_reports is not None:
        return all_reports(args.all_reports)
    report = args.report_flag or args.report or DEFAULT_REPORT

    try:
        data = load_report(report)
        st = validate_and_compute(data)
    except ReportError as e:
        print(f"ОШИБКА ВХОДА (код 2): {e}", file=sys.stderr)
        return 2
    except MismatchError as e:
        print(f"РАСХОЖДЕНИЕ (код 1): {e}", file=sys.stderr)
        return 1

    print_summary(st, report)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"статистики записаны: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
