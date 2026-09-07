#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_task_benchmark.py — гейт протокола задачного бенчмарка.

Проверяет протокол результатов (research/task-benchmark/results-*.json)
против замороженной предрегистрации (prereg.md):

  1. sha256 предрегистрации совпадает (критерии не правились постфактум);
  2. все объявленные операции присутствуют (o1, o2, o3; o4 — исполнен или
     BLOCKED с причиной; «не исполнен» в публикуемом протоколе = отказ);
  3. потери не скрыты: секция losses в точности соответствует fails
     операций и статусу o4 (пересчитывается независимо);
  4. числа O3 пересчитываются ЖИВЬЁМ из записанных пар (подмена вердикта
     ловится); записи O2 пересчитываются живой очисткой тех же документов;
  5. сводка summary соответствует секциям.

Ось O1 хранит сырые детали run_eval (reference и приколотый smixs);
пересчёт O1 из сырых JSON — командой из предрегистрации (eval/run_eval.py),
протокол сохраняет оба массива details для независимой перепроверки.

Запуск:
  python3 scripts/check_task_benchmark.py --verify <results.json>
  python3 scripts/check_task_benchmark.py --selftest
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
TB = os.path.join(ROOT, "research", "task-benchmark")
PREREG = os.path.join(TB, "prereg.md")
RUNNER = os.path.join(ROOT, "eval", "run_task_benchmark.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_task_benchmark",
                                                  RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def verify(results, live=True):
    """Список нарушений протокола (пустой — протокол пригоден)."""
    runner = _load_runner()
    problems = []
    version = results.get("prereg_version", 1)
    prereg_rel = results.get("prereg", "research/task-benchmark/prereg.md")
    prereg_path = os.path.join(ROOT, *prereg_rel.split("/"))
    if not os.path.isfile(prereg_path):
        problems.append("предрегистрация %s отсутствует" % prereg_rel)
        prereg_path = PREREG
    want_hash = _sha256(prereg_path)
    if results.get("prereg_sha256") != want_hash:
        problems.append("sha256 предрегистрации %r != фактический %r: "
                        "критерии изменены после заморозки или протокол "
                        "чужой" % (results.get("prereg_sha256"), want_hash))
    for op in ("o1", "o2", "o3"):
        if not isinstance(results.get(op), dict):
            problems.append("нет секции %s — прогон неполон" % op)
    if "o1" in results and isinstance(results["o1"], dict):
        o1 = results["o1"]
        if o1.get("pass") != (not o1.get("fails")):
            problems.append("o1: флаг pass не соответствует fails")
        axes = o1.get("axes") or {}
        if set(axes) != {"reference", "smixs-91f70df"}:
            problems.append("o1: нет осей reference И приколотого "
                            "компаратора (протокол без компаратора)")
        for name, ax in axes.items():
            if ax.get("files") and o1.get("details_%s"
                                          % ("reference"
                                             if name == "reference"
                                             else "smixs")) is None:
                problems.append("o1 %s: нет сырых details для независимого "
                                "пересчёта" % name)
    if "o2" in results and isinstance(results["o2"], dict):
        o2 = results["o2"]
        if o2.get("pass") != (not o2.get("fails")):
            problems.append("o2: флаг pass не соответствует fails")
        if not o2.get("records"):
            problems.append("o2: нет записей прогона")
        if o2.get("comparator_note") is None:
            problems.append("o2: отсутствие компаратора не опубликовано")
        if live:
            fresh = runner.run_o2_v2() if version == 2 else runner.run_o2()
            keys = ["doc", "changed", "facts_lost", "facts_changed"]
            if version == 2:
                keys += ["guards_intact", "cli_rc"]
            got = {tuple(r.get(k) for k in keys)
                   for r in o2["records"]}
            want = {tuple(r.get(k) for k in keys)
                    for r in fresh["records"]}
            if got != want:
                problems.append("o2: записи не воспроизводятся живой "
                                "очисткой (числа протокола подменены или "
                                "продукт изменился)")
    if "o3" in results and isinstance(results["o3"], dict):
        o3 = results["o3"]
        if o3.get("pass") != (not o3.get("fails")):
            problems.append("o3: флаг pass не соответствует fails")
        if not o3.get("records"):
            problems.append("o3: нет записей прогона")
        if live:
            from humanizer_ru import facts_diff
            for rec in o3["records"]:
                if "before" not in rec:
                    continue
                d = facts_diff.diff(rec["before"], rec["after"])
                got = {"lost": len(d["lost"]), "added": len(d["added"]),
                       "changed": len(d["changed"])}
                r = rec.get("got") or {}
                if any(r.get(k) != v for k, v in got.items()):
                    problems.append("o3 %s: вердикт протокола %r != живой "
                                    "пересчёт %r" % (rec.get("pair_id"),
                                                     r, got))
    o4 = results.get("o4")
    if o4 is None:
        problems.append("o4 не исполнен: публикуемый протокол обязан нести "
                        "o4 (ok или BLOCKED с причиной); сессии не "
                        "фабрикуются, но и пропуск не публикуется как успех")
    elif isinstance(o4, dict):
        if o4.get("status") == "BLOCKED":
            if not o4.get("reason"):
                problems.append("o4 BLOCKED без причины")
        elif o4.get("status") == "ok":
            if len(o4.get("sessions") or []) != 6:
                problems.append("o4: сессий %s != 6 (замороженный протокол)"
                                % len(o4.get("sessions") or []))
            for s in o4.get("sessions") or []:
                for field in ("task_id", "prompt", "response", "model",
                              "provider"):
                    if not s.get(field):
                        problems.append("o4: сессия без поля %s — запись "
                                        "неполна" % field)
            graded = o4.get("graded") or []
            correct = sum(1 for g in graded if g.get("ok"))
            if o4.get("correct") != correct:
                problems.append("o4: correct %s != пересчёт по graded %s"
                                % (o4.get("correct"), correct))
        else:
            problems.append("o4: неизвестный статус %r" % o4.get("status"))
    # Потери: независимый пересчёт.
    want_losses = []
    for op in ("o1", "o2", "o3"):
        sec = results.get(op)
        if isinstance(sec, dict):
            for f in sec.get("fails") or []:
                want_losses.append({"op": op, "reason": f})
    if isinstance(o4, dict):
        if o4.get("status") == "BLOCKED":
            want_losses.append({"op": "o4",
                                "reason": "BLOCKED: " + o4.get("reason", "")})
        elif o4.get("status") == "ok" and not o4.get("pass"):
            want_losses.append({"op": "o4",
                                "reason": "правильных выборов %d из %d "
                                          "(порог 5/6)"
                                % (o4.get("correct"), o4.get("total"))})
    got_losses = results.get("losses")
    if got_losses is None:
        problems.append("нет секции losses — потери не публикуются")
    elif sorted(json.dumps(x, ensure_ascii=False, sort_keys=True)
                for x in got_losses) != \
            sorted(json.dumps(x, ensure_ascii=False, sort_keys=True)
                   for x in want_losses):
        problems.append("losses не соответствует fails операций: скрытая "
                        "потеря или лишняя запись")
    summary = results.get("summary") or {}
    if summary.get("losses") != len(want_losses):
        problems.append("summary.losses %s != пересчёт %s"
                        % (summary.get("losses"), len(want_losses)))
    return problems


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    runner = _load_runner()
    # Живой мини-протокол: O1 из сохранённого сырого JSON лидерборда
    # (структура осей), O2/O3 — живой прогон (быстро, детерминированно).
    with open(os.path.join(ROOT, "research", "leaderboard",
                           "reference-2026-08-12.json"),
              encoding="utf-8") as fh:
        ref_old = json.load(fh)
    axes_doc = {k: ref_old.get(k) for k in runner._AXES}
    o2 = runner.run_o2()
    o3 = runner.run_o3()
    o4_ok = {"status": "ok", "sessions": [
        {"task_id": i, "prompt": "p%d" % i, "response": "r%d" % i,
         "model": "test-model", "provider": "test-provider",
         "temperature": 0} for i in range(1, 7)],
        "graded": [{"task_id": str(i), "ok": True} for i in range(1, 7)],
        "correct": 6, "total": 6, "pass": True}
    results = {
        "schema": "task-benchmark.v1", "date": "2026-09-08",
        "prereg_sha256": _sha256(PREREG),
        "o1": {"axes": {"reference": axes_doc, "smixs-91f70df": axes_doc},
               "details_reference": [{}] * axes_doc["files"],
               "details_smixs": [{}] * axes_doc["files"],
               "fails": [], "pass": True},
        "o2": o2, "o3": o3, "o4": o4_ok,
    }
    runner._rebuild_losses(results)
    case("живой согласованный протокол проходит", verify(results) == [])

    import copy
    bad = copy.deepcopy(results)
    bad["prereg_sha256"] = "0" * 64
    case("мутант: чужой хеш предрегистрации ловится",
         any("предрегистрации" in p for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    del bad["o2"]
    case("мутант: отсутствующий прогон O2 ловится",
         any("o2" in p for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    bad["o1"]["fails"] = ["O1: ложное обвинение"]
    bad["o1"]["pass"] = False
    # losses НЕ пересобраны — скрытая потеря
    case("мутант: скрытая потеря ловится",
         any("losses" in p for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    for rec in bad["o3"]["records"]:
        if rec.get("pair_id") == "loss" and "got" in rec:
            rec["got"]["lost"] = 0
    case("мутант: подменённый вердикт O3 ловится живым пересчётом",
         any("o3 loss" in p for p in verify(bad)))

    bad = copy.deepcopy(results)
    bad["o4"] = None
    case("мутант: O4 не исполнен — протокол не публикуется",
         any("o4" in p for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    bad["o4"] = {"status": "BLOCKED", "reason": "живой API недоступен"}
    runner._rebuild_losses(bad)
    errs = verify(bad, live=False)
    case("BLOCKED с причиной — потеря опубликована, протокол валиден",
         errs == [] and any(l["op"] == "o4" for l in bad["losses"]))

    # v2: документированный путь O2 + хеш prereg-v2.
    results_v2 = copy.deepcopy(results)
    results_v2["o2"] = runner.run_o2_v2()
    results_v2["prereg"] = "research/task-benchmark/prereg-v2.md"
    results_v2["prereg_version"] = 2
    results_v2["prereg_sha256"] = _sha256(os.path.join(TB, "prereg-v2.md"))
    runner._rebuild_losses(results_v2)
    case("протокол v2 (документированный путь O2) проходит",
         verify(results_v2) == [])
    bad = copy.deepcopy(results_v2)
    for rec in bad["o2"]["records"]:
        rec["guards_intact"] = not rec["guards_intact"]
    case("мутант: подмена guards_intact v2 ловится живым пересчётом",
         any("o2" in p for p in verify(bad)))
    bad = copy.deepcopy(results_v2)
    bad["prereg_sha256"] = results["prereg_sha256"]
    case("мутант: хеш v1 в протоколе v2 ловится",
         any("предрегистрации" in p for p in verify(bad, live=False)))

    print("САМОПРОВЕРКА check_task_benchmark: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Гейт протокола задачного бенчмарка (предрегистрация, "
                    "полнота, потери, живой пересчёт).")
    ap.add_argument("--verify", metavar="RESULTS",
                    help="проверить протокол результатов")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.verify:
        ap.print_help()
        return 2
    with open(args.verify, encoding="utf-8") as fh:
        results = json.load(fh)
    problems = verify(results)
    for p in problems:
        print("[FAIL] " + p)
    if problems:
        print("TASK-BENCHMARK: нарушений %d" % len(problems))
        return 1
    print("TASK-BENCHMARK: протокол соответствует замороженной "
          "предрегистрации; потери опубликованы (%d)"
          % len(results.get("losses") or []))
    return 0


if __name__ == "__main__":
    sys.exit(main())
