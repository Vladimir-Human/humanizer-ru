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


def _parse_answer(response):
    """Первый JSON-объект с tool/mode из текста ответа сессии."""
    for line in (response or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if isinstance(doc, dict) and "tool" in doc:
                return doc
    return None


def _key_vs_contract(key, problems, where):
    """Ключ проверяется по контракту: инструменты и режимы реальны."""
    try:
        with open(os.path.join(ROOT, "contract.v1.json"),
                  encoding="utf-8") as fh:
            contract = json.load(fh)
    except (OSError, ValueError) as exc:
        problems.append("%s: контракт не читается: %r" % (where, exc))
        return
    tools = {t.get("command"): t for t in contract.get("tools", [])}
    for tid in sorted(key):
        want = key[tid] or {}
        tool = tools.get(want.get("tool"))
        if tool is None:
            problems.append("%s: ключ %s — инструмент %r отсутствует в "
                            "контракте" % (where, tid, want.get("tool")))
            continue
        modes = " ".join(tool.get("modes", []))
        for flag in want.get("required_flags", []):
            if flag not in modes:
                problems.append("%s: ключ %s — требуемый флаг %r "
                                "отсутствует в modes контракта (%s)"
                                % (where, tid, flag, modes[:60]))


def _regrade(sessions, key):
    """Независимая оценка ответов: [bool] по порядку сессий."""
    out = []
    for s in sessions:
        want = key.get(str(s.get("task_id")))
        ans = _parse_answer(s.get("response"))
        if want is None or ans is None:
            out.append(False)
            continue
        tool_ok = ans.get("tool") == want.get("tool")
        flags_ok = all(f in (ans.get("mode") or "")
                       for f in want.get("required_flags", []))
        out.append(bool(tool_ok and flags_ok))
    return out


def _verify_choice_section(sec, tasks_path, where, problems,
                           spec=None, expect_sessions=6,
                           isolation_required=False):
    """Общая проверка секции выбора операции (o4/o5): состав сессий,
    уникальность task_id, независимый перегрейдинг из текстов ответов
    (graded.ok НЕ является источником истины), ключ против контракта.

    isolation_required=True (протокол O5): файл задач НЕ может содержать
    answer_key — ключ обязан быть недоступен испытуемому. Для O4 файл
    исторически содержит ключ — это дефект прежнего протокола, раскрыт
    эрратой; исторические протоколы задним числом не отвергаются."""
    try:
        if spec is None:
            with open(tasks_path, encoding="utf-8") as fh:
                spec = json.load(fh)
    except (OSError, ValueError) as exc:
        problems.append("%s: файл задач не читается: %r" % (where, exc))
        return
    if isolation_required and "answer_key" in spec:
        problems.append("%s: файл задач содержит answer_key — ключ "
                        "доступен испытуемому" % where)
    key = sec.get("answer_key") or spec.get("answer_key") or {}
    if not key:
        problems.append("%s: ключ ответов отсутствует" % where)
        return
    _key_vs_contract(key, problems, where)
    tasks_ids = {str(t.get("task_id")) for t in spec.get("tasks", [])}
    sessions = sec.get("sessions") or []
    if len(sessions) != expect_sessions:
        problems.append("%s: сессий %s != %d (замороженный протокол)"
                        % (where, len(sessions), expect_sessions))
    seen = set()
    for s in sessions:
        for field in ("task_id", "prompt", "response", "model", "provider"):
            if not s.get(field):
                problems.append("%s: сессия без поля %s — запись неполна"
                                % (where, field))
        tid = str(s.get("task_id"))
        if tid in seen:
            problems.append("%s: task_id %s встречается дважды — "
                            "уникальность нарушена" % (where, tid))
        seen.add(tid)
    if seen != tasks_ids:
        problems.append("%s: состав задач сессий %r != замороженный %r"
                        % (where, sorted(seen), sorted(tasks_ids)))
    regraded = _regrade(sessions, key)
    recorded_ok = [bool(g.get("ok")) for g in (sec.get("graded") or [])]
    if recorded_ok and len(recorded_ok) != len(regraded):
        problems.append("%s: записей graded %s != сессий %s"
                        % (where, len(recorded_ok), len(regraded)))
    for i, (rec, fresh) in enumerate(zip(recorded_ok, regraded)):
        if rec != fresh:
            problems.append("%s: вердикт сессии %d (task %s) не "
                            "пересчитывается из response: graded=%s, "
                            "независимая оценка=%s — подмена ответов или "
                            "оценки" % (where, i + 1,
                                        sessions[i].get("task_id"),
                                        rec, fresh))
    correct = sum(1 for x in regraded if x)
    if sec.get("correct") != correct:
        problems.append("%s: correct %s != независимый пересчёт из "
                        "response %s" % (where, sec.get("correct"), correct))


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
            _verify_choice_section(o4, os.path.join(TB, "o4-tasks.json"),
                                   "o4", problems)
        else:
            problems.append("o4: неизвестный статус %r" % o4.get("status"))
    # O5 (нейтральный пересмотр выбора операции): необязательная секция,
    # но если заявлена — проверяется полностью, включая изоляцию ключа
    # (файл задач НЕ содержит ключ) и хеш ключа из предрегистрации.
    o5 = results.get("o5")
    if isinstance(o5, dict) and o5.get("status") == "ok":
        o5_problems = []
        _verify_choice_section(o5, os.path.join(TB, "o5-tasks.json"),
                               "o5", o5_problems,
                               spec=o5.get("tasks_spec"),
                               isolation_required=True)
        problems.extend(o5_problems)
        key_hash = o5.get("key_sha256")
        if not key_hash:
            problems.append("o5: нет key_sha256 — связь ключа с "
                            "предрегистрацией не проверить")
        else:
            try:
                with open(os.path.join(TB, "o5-prereg.md"),
                          encoding="utf-8") as fh:
                    o5_prereg = fh.read()
                if key_hash not in o5_prereg:
                    problems.append("o5: хеш ключа %s не заморожен в "
                                    "предрегистрации — ключ изменён после "
                                    "заморозки" % key_hash[:12])
            except OSError:
                problems.append("o5: предрегистрация o5-prereg.md не "
                                "читается")
        for base_name in ("noop", "keyword"):
            base = (o5.get("baselines") or {}).get(base_name)
            if not base:
                problems.append("o5: базовый уровень %s отсутствует "
                                "(no-op и прозрачный baseline обязательны)"
                                % base_name)
                continue
            answers = base.get("answers") or []
            key = o5.get("answer_key") or {}
            fresh = sum(1 for a in answers
                        if key.get(str(a.get("task_id")), {}).get("tool")
                        == a.get("tool"))
            if base.get("correct") != fresh:
                problems.append("o5: baseline %s correct %s != пересчёт %s"
                                % (base_name, base.get("correct"), fresh))
    elif isinstance(o5, dict) and o5.get("status") == "BLOCKED":
        if not o5.get("reason"):
            problems.append("o5 BLOCKED без причины")
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
    o5_loss = results.get("o5")
    if isinstance(o5_loss, dict):
        if o5_loss.get("status") == "BLOCKED":
            want_losses.append({"op": "o5",
                                "reason": "BLOCKED: "
                                + o5_loss.get("reason", "")})
        elif o5_loss.get("status") == "ok" and not o5_loss.get("pass"):
            want_losses.append({"op": "o5",
                                "reason": "нейтральный выбор: правильных "
                                          "%d из %d (порог 5/6)"
                                % (o5_loss.get("correct"),
                                   len(o5_loss.get("sessions") or []))})
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
    with open(os.path.join(TB, "o4-tasks.json"), encoding="utf-8") as fh:
        o4_spec = json.load(fh)
    o4_key = o4_spec["answer_key"]

    def o4_session(i):
        want = o4_key[str(i)]
        resp = json.dumps({"task_id": i, "tool": want["tool"],
                           "mode": " ".join(want["required_flags"])},
                          ensure_ascii=False)
        return {"task_id": i, "prompt": "p%d" % i, "response": resp,
                "model": "test-model", "provider": "test-provider",
                "temperature": 0}

    o4_ok = {"status": "ok",
             "sessions": [o4_session(i) for i in range(1, 7)],
             "graded": [{"task_id": str(i), "ok": True}
                        for i in range(1, 7)],
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

    # O4/O5: независимый перегрейдинг и изоляция ключа.
    bad = copy.deepcopy(results)
    ans = json.loads(bad["o4"]["sessions"][0]["response"])
    ans["tool"] = "humanizer-scan"
    bad["o4"]["sessions"][0]["response"] = json.dumps(ans,
                                                      ensure_ascii=False)
    case("мутант: подмена O4-ответа при сохранённом graded ловится "
         "пересчётом из response",
         any("не пересчитывается" in p or "correct" in p
             for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    bad["o4"]["sessions"][1]["task_id"] = bad["o4"]["sessions"][0]["task_id"]
    case("мутант: дубликат task_id O4 ловится",
         any("дважды" in p for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    bad["o4"]["answer_key"] = {str(i): dict(o4_key[str(i)])
                               for i in range(1, 7)}
    bad["o4"]["answer_key"]["3"]["required_flags"] = ["--no-such-flag"]
    case("мутант: флаг ключа вне modes контракта ловится",
         any("отсутствует в modes" in p for p in verify(bad, live=False)))

    bad = copy.deepcopy(results)
    bad["o5"] = {"status": "ok", "key_sha256": "a" * 64,
                 "tasks_spec": {"tasks": [], "answer_key": {"1": {}}},
                 "sessions": [], "correct": 0, "baselines": {}}
    errs5 = verify(bad, live=False)
    case("мутант: O5 — ключ в файле задач и отсутствие baselines ловятся",
         any("answer_key" in p for p in errs5)
         and any("базовый уровень" in p for p in errs5))

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
