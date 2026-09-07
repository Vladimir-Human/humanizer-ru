#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_task_benchmark.py — прогоны задачного бенчмарка O1–O3 (+ слияние O4).

Предрегистрация заморожена: research/task-benchmark/prereg.md (её sha256
пишется в протокол; сверка — scripts/check_task_benchmark.py --verify).
O4 (выбор операции агентом, живой API) исполняется отдельно по
замороженному протоколу research/task-benchmark/o4-tasks.json и
сливается сюда через --merge-o4; при недоступности живого API
записывается BLOCKED с причиной, сессии не фабрикуются.

Запуск:
  python3 eval/run_task_benchmark.py
      -> research/task-benchmark/results-<дата>.json
  python3 eval/run_task_benchmark.py --merge-o4 <o4-sessions.json> \
      <results.json>   (перезаписывает протокол с секцией o4)
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
TB = os.path.join(ROOT, "research", "task-benchmark")
PREREG = os.path.join(TB, "prereg.md")
O4_TASKS = os.path.join(TB, "o4-tasks.json")
PY = sys.executable


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _run_eval(candidate=None):
    cmd = [PY, "-X", "utf8", os.path.join(ROOT, "eval", "run_eval.py")]
    if candidate:
        cmd += ["--candidate", candidate]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          cwd=ROOT, timeout=900)
    # rc=1 у run_eval — легитимный результат («найдены проблемы»: у
    # компаратора это его человеческие FP), данные — JSON в stdout.
    # Отказ исполнения — rc>=2 или непарсящийся stdout.
    if proc.returncode >= 2:
        raise RuntimeError("run_eval rc=%d: %s"
                           % (proc.returncode, (proc.stderr or "")[-300:]))
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise RuntimeError("run_eval rc=%d: stdout не JSON: %s"
                           % (proc.returncode, (proc.stdout or "")[-200:]))


_AXES = ("files", "files_missing", "hash_mismatches", "human_hits",
         "ai_hits", "ai_unexpected", "boundary_expected_ok",
         "boundary_unexpected")


def run_o1():
    """Детекция на корпусе манифеста; компаратор — приколотый smixs."""
    ref = _run_eval()
    smixs = _run_eval(os.path.join(ROOT, "eval", "candidates",
                                   "smixs_runner.py"))
    axes = {}
    for name, doc in (("reference", ref), ("smixs-91f70df", smixs)):
        axes[name] = {k: doc.get(k) for k in _AXES}
    fails = []
    r = axes["reference"]
    if r["files_missing"]:
        fails.append("O1: %s файл(ов) манифеста отсутствует"
                     % r["files_missing"])
    if r["hash_mismatches"]:
        fails.append("O1: %s hash-расхождени(е/й) корпуса"
                     % r["hash_mismatches"])
    if r["human_hits"]:
        fails.append("O1: ложные обвинения на человеческих документах: %s"
                     % r["human_hits"])
    if r["boundary_unexpected"]:
        fails.append("O1: boundary-контроли: неожиданное поведение %s"
                     % r["boundary_unexpected"])
    if r["ai_unexpected"]:
        fails.append("O1: AI-документы: расхождение с заявленными "
                     "ожиданиями манифеста %s" % r["ai_unexpected"])
    return {"axes": axes,
            "details_reference": ref.get("details"),
            "details_smixs": smixs.get("details"),
            "comparability": ("сопоставимы только human-FP и boundary "
                              "(предрегистрация O1); счётчики правил "
                              "несопоставимы"),
            "fails": fails, "pass": not fails}


def run_o2_v2():
    """O2 по предрегистрации v2: документированный путь продукта.

    Факты — через edit_report.facts_part (marker-aware: payload маркеров
    не факт автора); защищённые области — guard-список контракта
    (fenced/frontmatter/инлайн-код построчно); снятие utm/referrer
    внутри URL — документированное поведение, не нарушение.
    """
    from humanizer_ru import text_layer, edit_report, protected_regions
    records = []
    fails = []

    def guard_texts(t):
        spans = []
        lines = t.split("\n")
        fi = protected_regions.fenced_line_indices(lines)
        fr = protected_regions.frontmatter_line_indices(lines)
        for i, ln in enumerate(lines):
            if i in fi or i in fr:
                spans.append(ln)
            else:
                for s, e in protected_regions.code_spans(ln):
                    spans.append(ln[s:e])
        return spans

    docs = _o2_docs()
    for name, before in docs:
        cleaned, counters = text_layer.clean_supported(before)
        again, counters2 = text_layer.clean_supported(cleaned)
        facts = edit_report.facts_part(before, cleaned)
        guards_ok = guard_texts(before) == guard_texts(cleaned)
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with tempfile.TemporaryDirectory(prefix="o2v2-") as td:
            p = os.path.join(td, name if name.endswith((".txt", ".md"))
                             else name + ".txt")
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(before)
            with contextlib.redirect_stdout(buf):
                rc = text_layer.clean_main([p, "--json"])
        try:
            env_ok = bool(json.loads(buf.getvalue()).get("files"))
        except ValueError:
            env_ok = False
        rec = {"doc": name, "removed": counters,
               "fixed_point": again == cleaned and
               counters2 == {"invisible": 0, "markup": 0},
               "facts_lost": facts["lost"],
               "facts_changed": facts["changed"],
               "facts_added": facts["added"],
               "guards_intact": guards_ok,
               "cli_rc": rc, "cli_envelope_ok": env_ok,
               "changed": cleaned != before}
        records.append(rec)
        if not rec["fixed_point"]:
            fails.append("O2 %s: очистка не достигла неподвижной точки "
                         "(поддерживаемые артефакты остались)" % name)
        if facts["lost"] or facts["changed"]:
            fails.append("O2 %s: документированный путь сверки фактов "
                         "показал потерю/изменение (lost=%s changed=%s)"
                         % (name, facts["lost"], facts["changed"]))
        if not guards_ok:
            fails.append("O2 %s: guard-области контракта (fenced/"
                         "frontmatter/инлайн-код) изменены" % name)
        if rc not in (0, 1) or not env_ok:
            fails.append("O2 %s: CLI humanizer-clean rc=%s, конверт %s — "
                         "не соответствует контракту"
                         % (name, rc, "ok" if env_ok else "не прочитан"))
    return {"records": records, "comparator": None,
            "comparator_note": ("компаратор отсутствует: smixs — линтер "
                                "без очистки; отсутствие публикуется как "
                                "отсутствие, не как победа"),
            "fails": fails, "pass": not fails}


def _o2_docs():
    fixdir = os.path.join(ROOT, "tests", "fixtures")
    docs = []
    for name in sorted(os.listdir(fixdir)):
        if name.endswith(".txt"):
            with open(os.path.join(fixdir, name), encoding="utf-8") as fh:
                docs.append((name, fh.read()))
    synth = ("---\ntitle: Отчёт\n---\n\n# Заголовок\n\n"
             "Текст с utm_source=chatgpt.com и меткой.\u200b\n\n"
             "```python\nx = 'utm_source=chatgpt.com'\n```\n\n"
             "Обычный текст и `код utm_source=chatgpt.com` в строке.\n")
    docs.append(("synthetic-protected.md", synth))
    return docs


def run_o2():
    """Контролируемая очистка (критерии v1): фикспойнт, сырой facts_diff,
    все защищённые спаны. Замер v1 сохранён для истории."""
    from humanizer_ru import text_layer, facts_diff, protected_regions
    records = []
    fails = []
    docs = _o2_docs()

    for name, before in docs:
        cleaned, counters = text_layer.clean_supported(before)
        again, counters2 = text_layer.clean_supported(cleaned)
        d = facts_diff.diff(before, cleaned)
        prot_ok = (protected_regions.protected_texts(before)
                   == protected_regions.protected_texts(cleaned))
        rec = {"doc": name, "removed": counters,
               "fixed_point": again == cleaned and
               counters2 == {"invisible": 0, "markup": 0},
               "facts_lost": len(d["lost"]),
               "facts_changed": len(d["changed"]),
               "facts_added": len(d["added"]),
               "protected_intact": prot_ok,
               "changed": cleaned != before}
        records.append(rec)
        if not rec["fixed_point"]:
            fails.append("O2 %s: очистка не достигла неподвижной точки "
                         "(поддерживаемые артефакты остались)" % name)
        if rec["facts_lost"] or rec["facts_changed"]:
            fails.append("O2 %s: очистка потеряла/изменила факты "
                         "(lost=%s changed=%s)"
                         % (name, rec["facts_lost"], rec["facts_changed"]))
        if not prot_ok:
            fails.append("O2 %s: защищённые области изменены" % name)
    return {"records": records, "comparator": None,
            "comparator_note": ("компаратор отсутствует: smixs — линтер "
                                "без очистки; отсутствие публикуется как "
                                "отсутствие, не как победа"),
            "fails": fails, "pass": not fails}


# Замороженные пары O3 (предрегистрация): (id, до, после, ожидание).
O3_PAIRS = [
    ("identical", "Встреча состоялась. Цена 100 рублей.",
     "Встреча состоялась. Цена 100 рублей.",
     {"lost": 0, "added": 0, "changed": 0}),
    ("loss", "Бюджет 500 тыс. ₽ до 15 марта 2026 года.",
     "Бюджет уточняется.", {"lost_min": 1}),
    ("addition", "Встреча состоялась.",
     "Встреча состоялась. Цена 100 рублей.", {"added_min": 1}),
    ("inversion", "Иван Петров не подтвердил данные.",
     "Иван Петров подтвердил данные.", {"changed_min": 1}),
    ("permutation-boundary", "Иван получил 100 рублей, Мария 200.",
     "Мария получила 100 рублей, Иван 200.",
     {"lost": 0, "added": 0, "changed": 0}),
    ("mixed-scale", "Цена 5 миллионов рублей.",
     "Цена пять миллионов рублей.", {"lost": 0, "added": 0, "changed": 0}),
    ("fraction-scale", "Выручка 2.5 миллиона.", "Выручка 2500000.",
     {"lost": 0, "added": 0, "changed": 0}),
    ("range-boundary", "Диапазон 5-10 миллионов заявок.",
     "Диапазон 5-10 миллионов заявок.",
     {"lost": 0, "added": 0, "changed": 0,
      "numbers_values": sorted(["5", "10", "1000000"])}),
]


def _verdict_ok(expect, d, numbers=None):
    for key, want in expect.items():
        if key == "lost_min":
            if len(d["lost"]) < want:
                return False
        elif key == "added_min":
            if len(d["added"]) < want:
                return False
        elif key == "changed_min":
            if len(d["changed"]) < want:
                return False
        elif key == "numbers_values":
            if numbers != want:
                return False
        elif key in ("lost", "added", "changed"):
            if len(d[key]) != want:
                return False
    return True


def run_o3():
    from humanizer_ru import facts_diff
    records = []
    fails = []
    for pid, before, after, expect in O3_PAIRS:
        d = facts_diff.diff(before, after)
        numbers = None
        if "numbers_values" in expect:
            numbers = sorted(n["value"] for n in
                             facts_diff.extract(before)["numbers"])
        ok = _verdict_ok(expect, d, numbers)
        records.append({"pair_id": pid, "before": before, "after": after,
                        "expect": expect,
                        "got": {"lost": len(d["lost"]),
                                "added": len(d["added"]),
                                "changed": len(d["changed"]),
                                "numbers_values": numbers},
                        "ok": ok})
        if not ok:
            fails.append("O3 %s: вердикт %r != ожидание %r"
                         % (pid, records[-1]["got"], expect))
    # Строгий режим --no-additions: rc=1 на добавлении, rc=0 без него.
    import contextlib
    import io as _io
    with tempfile.TemporaryDirectory(prefix="o3-") as td:
        b = os.path.join(td, "b.txt")
        a = os.path.join(td, "a.txt")
        with open(b, "w", encoding="utf-8", newline="") as fh:
            fh.write("Встреча состоялась.\n")
        with open(a, "w", encoding="utf-8", newline="") as fh:
            fh.write("Встреча состоялась. Цена 100 рублей.\n")
        with contextlib.redirect_stdout(_io.StringIO()):
            strict = facts_diff.main(["diff", b, a, "--json",
                                      "--no-additions"])
            loose = facts_diff.main(["diff", b, a, "--json"])
        ok_strict = strict == 1 and loose == 0
        records.append({"pair_id": "strict-mode-rc",
                        "expect": {"strict_rc": 1, "loose_rc": 0},
                        "got": {"strict_rc": strict, "loose_rc": loose},
                        "ok": ok_strict})
        if not ok_strict:
            fails.append("O3 strict-mode-rc: --no-additions rc=%s "
                         "(ожидался 1), дефолт rc=%s (ожидался 0)"
                         % (strict, loose))
    return {"records": records,
            "comparator": None,
            "comparator_note": ("компаратор отсутствует: детерминированная "
                                "сверка фактов на стандартной библиотеке — "
                                "публичные аналоги не измерены (статус "
                                "«не измерено», не «нет»)"),
            "fails": fails, "pass": not fails}


def grade_o4(sessions):
    """Оценка O4-сессий против замороженного ключа."""
    with open(O4_TASKS, encoding="utf-8") as fh:
        spec = json.load(fh)
    key = spec["answer_key"]
    graded = []
    correct = 0
    for s in sessions:
        tid = str(s.get("task_id"))
        want = key.get(tid)
        verdict = s.get("verdict") or {}
        tool_ok = verdict.get("tool") == want["tool"]
        flags_ok = all(f in (verdict.get("mode") or "")
                       for f in want["required_flags"])
        ok = tool_ok and flags_ok
        correct += 1 if ok else 0
        graded.append({"task_id": tid, "tool": verdict.get("tool"),
                       "mode": verdict.get("mode"), "ok": ok})
    return {"sessions": sessions, "graded": graded,
            "correct": correct, "total": len(sessions),
            "pass": correct >= 5 and len(sessions) == 6}


def merge_o4(sessions_path, results_path):
    with open(sessions_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    with open(results_path, encoding="utf-8") as fh:
        results = json.load(fh)
    if isinstance(payload, dict) and payload.get("blocked"):
        results["o4"] = {"status": "BLOCKED",
                         "reason": payload["blocked"]}
    else:
        results["o4"] = grade_o4(payload)
        results["o4"]["status"] = "ok"
    _rebuild_losses(results)
    with open(results_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("O4 слит в %s" % results_path)


def _rebuild_losses(results):
    losses = []
    for op in ("o1", "o2", "o3"):
        for f in results[op]["fails"]:
            losses.append({"op": op, "reason": f})
    o4 = results.get("o4")
    if o4 and o4.get("status") == "BLOCKED":
        losses.append({"op": "o4", "reason": "BLOCKED: " + o4["reason"]})
    elif o4 and o4.get("status") == "ok" and not o4["pass"]:
        losses.append({"op": "o4",
                       "reason": "правильных выборов %d из %d (порог 5/6)"
                       % (o4["correct"], o4["total"])})
    results["losses"] = losses
    results["summary"] = {
        "o1_pass": results["o1"]["pass"],
        "o2_pass": results["o2"]["pass"],
        "o3_pass": results["o3"]["pass"],
        "o4_status": (o4 or {}).get("status", "not-run"),
        "o4_pass": (o4 or {}).get("pass"),
        "losses": len(losses)}


def selftest():
    """Негативы логики оценки (grade_o4, _verdict_ok) без сети и прогона."""
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    with open(O4_TASKS, encoding="utf-8") as fh:
        spec = json.load(fh)
    key = spec["answer_key"]

    def session(tid, tool, mode):
        return {"task_id": tid, "verdict": {"tool": tool, "mode": mode}}

    good = [session(int(t), key[t]["tool"],
                    " ".join(key[t]["required_flags"]))
            for t in sorted(key)]
    g = grade_o4(good)
    case("ключевые ответы: 6/6, PASS", g["correct"] == 6 and g["pass"])

    bad = list(good)
    bad[2] = session(3, "humanizer-facts", "")  # без --no-additions
    bad[3] = session(4, "humanizer-polish", "")  # без --preserve-markup
    g2 = grade_o4(bad)
    case("потеря обязательных флагов снижает счёт (4/6, не PASS)",
         g2["correct"] == 4 and not g2["pass"])

    wrong_tool = list(good)
    wrong_tool[0] = session(1, "humanizer-scan", "")
    g3 = grade_o4(wrong_tool)
    case("неверный инструмент не засчитывается", g3["correct"] == 5)

    d_empty = {"lost": [], "added": [], "changed": []}
    case("_verdict_ok: точные нули на пустом diff",
         _verdict_ok({"lost": 0, "added": 0, "changed": 0}, d_empty))
    d_lost = {"lost": [1], "added": [], "changed": []}
    case("_verdict_ok: потеря при ожидании нуля — отказ (негатив)",
         not _verdict_ok({"lost": 0}, d_lost))
    case("_verdict_ok: lost_min выполняется",
         _verdict_ok({"lost_min": 1}, d_lost))
    case("_verdict_ok: список значений чисел сверяется",
         _verdict_ok({"numbers_values": ["1", "2"]}, d_empty,
                     numbers=["1", "2"])
         and not _verdict_ok({"numbers_values": ["1"]}, d_empty,
                             numbers=["1", "2"]))
    print("САМОПРОВЕРКА run_task_benchmark: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        return selftest()
    if argv and argv[0] == "--merge-o4":
        merge_o4(argv[1], argv[2])
        return 0
    v2 = bool(argv and argv[0] == "--v2")
    prereg_rel = ("research/task-benchmark/prereg-v2.md" if v2
                  else "research/task-benchmark/prereg.md")
    prereg_path = os.path.join(ROOT, *prereg_rel.split("/"))
    results = {
        "schema": "task-benchmark.v1",
        "date": datetime.datetime.now(datetime.timezone.utc)
                .strftime("%Y-%m-%d"),
        "prereg": prereg_rel,
        "prereg_version": 2 if v2 else 1,
        "prereg_sha256": sha256_file(prereg_path),
    }
    results["o1"] = run_o1()
    results["o2"] = run_o2_v2() if v2 else run_o2()
    results["o3"] = run_o3()
    results["o4"] = None
    _rebuild_losses(results)
    out = os.path.join(
        TB, ("results-v2-" if v2 else "results-")
        + datetime.datetime.now(datetime.timezone.utc)
          .strftime("%Y-%m-%d") + ".json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("ПРОТОКОЛ: %s" % out)
    print("ИТОГ: O1 %s, O2 %s, O3 %s, O4 %s; потерь %d"
          % ("PASS" if results["o1"]["pass"] else "FAIL",
             "PASS" if results["o2"]["pass"] else "FAIL",
             "PASS" if results["o3"]["pass"] else "FAIL",
             results["summary"]["o4_status"], len(results["losses"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
