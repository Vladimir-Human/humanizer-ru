#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_all.py — весь релизный чек-лист одной командой.

До этого скрипта релизный чек-лист состоял из восьми команд, которые
запускались по памяти; пропуск любой из них CI ловил только после пуша. Здесь
тот же набор гейтов собран в один прогон с итоговой таблицей.

Скрипт честно различает три исхода:
- PASS — гейт прошёл;
- FAIL — гейт упал (итоговый код возврата 1);
- SKIP — гейта нет в этой поставке. Архив скилла не содержит research/,
  tests/ и eval/ (см. check_release.py), поэтому в нём корпусные гейты
  пропускаются с пояснением, а не имитируют успех.

Запуск из корня репозитория:
    python3 scripts/check_all.py            # полный прогон
    python3 scripts/check_all.py --quick    # без перф-гейта, полного eval
                                            # и сборки архива
    python3 scripts/check_all.py --selftest

Код возврата: 0 — ни одного FAIL, 1 — есть FAIL или провал самопроверки,
2 — ошибка запуска. Только стандартная библиотека.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable or "python3"


def _gates(quick, tmpdir):
    """Список гейтов: (метка, argv, обязательные пути, допустимые коды)."""
    d = os.path.basename(ROOT) or "humanizer-ru"
    zip_path = os.path.join(tmpdir, "humanizer-ru.zip")
    gates = [
        ("spec: самопроверка", [PY, "scripts/check_spec.py", "--selftest"], [], {0}),
        ("spec: SKILL.md строгий", [PY, "scripts/check_spec.py", "SKILL.md",
                                    "--strict", "--expect-dir", d], [], {0}),
        ("budget: самопроверка", [PY, "scripts/check_budget.py", "--selftest"], [], {0}),
        ("budget: лимиты SKILL.md", [PY, "scripts/check_budget.py", "SKILL.md",
                                     "--expect-dir", d], [], {0}),
        ("docs: самопроверка", [PY, "scripts/check_docs.py", "--selftest"], [], {0}),
        ("docs: согласованность", [PY, "scripts/check_docs.py"], [], {0}),
        ("markers: три уровня образцов", [PY, "scripts/check_markers.py"], [], {0}),
        ("markers: паритет md-py", [PY, "scripts/check_markers.py", "--parity"],
         ["references/chatbot-artifacts.md",
          "references/chatbot-artifacts-links.md",
          "references/chatbot-artifacts-markup.md",
          "references/chatbot-artifacts-legacy.md"], {0}),
        ("style: самопроверка", [PY, "scripts/count_style_markers.py", "--selftest"], [], {0}),
        ("style: самопроверка порога", [PY, "scripts/check_own_style.py", "--selftest"], [], {0}),
        ("style: порог на собственные файлы", [PY, "scripts/check_own_style.py"], [], {0}),
        ("soft-signals: самопроверка", [PY, "scripts/scan_soft_signals.py", "--selftest"], [], {0}),
        ("examples: самопроверка", [PY, "scripts/check_examples.py", "--selftest"], [], {0}),
        ("examples: честность До/После", [PY, "scripts/check_examples.py"], [], {0}),
        ("readme-parity: самопроверка", [PY, "scripts/check_readme_parity.py", "--selftest"], [], {0}),
        ("readme-parity: витрина", [PY, "scripts/check_readme_parity.py"],
         ["README.md", "README.en.md"], {0}),
        ("maps: самопроверка", [PY, "scripts/check_reference_maps.py", "--selftest"], [], {0}),
        ("maps: карты справочников", [PY, "scripts/check_reference_maps.py"], [], {0}),
        ("registry: самопроверка", [PY, "scripts/check_fixture_sources.py", "--selftest"], [], {0}),
        ("registry: реестр доказательств", [PY, "scripts/check_fixture_sources.py",
                                            "research/fixtures/marker-sources.json"],
         ["research/fixtures/marker-sources.json"], {0}),
        ("corpus: регрессия корпусов", [PY, "scripts/check_corpus.py"],
         ["research/validation/human"], {0}),
        ("corpus: мягкие сигналы человеческих текстов",
         [PY, "scripts/scan_soft_signals.py", "--max-cats", "1"] + [
             os.path.join("research", "validation", "human", name)
             for name in sorted(os.listdir(os.path.join(ROOT, "research",
                                                        "validation", "human")))
             if name.endswith(".txt")],
         ["research/validation/human"], {0}),
        ("perf: самопроверка", [PY, "scripts/check_perf.py", "--selftest"], [], {0}),
    ]
    if not quick:
        gates.append(("perf: 38 выражений на 30k", [PY, "scripts/check_perf.py"], [], {0}))
    gates += [
        ("eval: самопроверка гарнесса", [PY, "eval/run_eval.py", "--selftest"],
         ["eval/run_eval.py"], {0}),
    ]
    if not quick:
        gates.append(("eval: manifest.v1.json", [PY, "eval/run_eval.py"],
                      ["eval/run_eval.py", "eval/manifest.v1.json",
                       "research/validation/human"], {0}))
    gates += [
        ("blind-eval: самопроверка", [PY, "eval/blind_eval.py", "--selftest"],
         ["eval/blind_eval.py"], {0}),
        # Без парных прогонов гарнесс обязан отказать кодом 2 (fail-closed);
        # при собранных данных законен и код 0 — оба исхода не ошибка.
        ("blind-eval: отказ без данных", [PY, "eval/blind_eval.py"],
         ["eval/blind_eval.py"], {0, 2}),
        ("compile: scripts", [PY, "-m", "compileall", "-q", "scripts"], [], {0}),
        ("release: самопроверка", [PY, "scripts/check_release.py", "--selftest"], [], {0}),
    ]
    if not quick:
        gates += [
            ("release: сборка архива", [PY, "scripts/check_release.py",
                                        "--root", ".", "--build", zip_path], [], {0}),
            ("release: верификация архива", [PY, "scripts/check_release.py",
                                             "--verify", zip_path], [], {0}),
        ]
    return gates


def run_gates(gates, root):
    """Выполняет гейты; возвращает (строки отчёта, число FAIL, число SKIP)."""
    rows, fails, skips = [], 0, 0
    for label, argv, needs, ok_codes in gates:
        script = argv[1] if len(argv) > 1 and argv[1].endswith(".py") else None
        missing = [p for p in needs if not os.path.exists(os.path.join(root, p))]
        if script and not os.path.exists(os.path.join(root, script)):
            missing.insert(0, script)
        if missing:
            skips += 1
            rows.append(("SKIP", label, "нет в этой поставке: %s" % ", ".join(missing), 0.0))
            continue
        started = time.time()
        try:
            proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            rows.append(("FAIL", label, "не запустился: %s" % exc, 0.0))
            fails += 1
            continue
        took = time.time() - started
        if proc.returncode in ok_codes:
            rows.append(("PASS", label, "", took))
        else:
            fails += 1
            tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
            detail = "; ".join(tail[-3:]) if tail else "код %d" % proc.returncode
            rows.append(("FAIL", label, "код %d: %s" % (proc.returncode, detail[:220]), took))
    return rows, fails, skips


def render(rows, fails, skips):
    width = max(len(label) for _s, label, _d, _t in rows)
    out = []
    for status, label, detail, took in rows:
        line = "%-4s %-*s %5.1fс" % (status, width, label, took)
        if detail:
            line += "  — " + detail
        out.append(line)
    out.append("ИТОГ: %d гейтов, FAIL: %d, SKIP: %d." % (len(rows), fails, skips))
    return "\n".join(out)


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    ok_gate = ("зелёный гейт", [PY, "-c", "print('ok')"], [], {0})
    bad_gate = ("красный гейт", [PY, "-c", "import sys; sys.exit(3)"], [], {0})
    code2_gate = ("контролируемый отказ", [PY, "-c", "import sys; sys.exit(2)"], [], {0, 2})
    missing_gate = ("гейт без файла", [PY, "scripts/нет_такого_скрипта.py"], [], {0})

    rows, fails, skips = run_gates([ok_gate], ROOT)
    case("зелёный гейт даёт PASS и ноль FAIL", fails == 0 and rows[0][0] == "PASS")

    rows, fails, skips = run_gates([ok_gate, bad_gate], ROOT)
    case("красный гейт даёт FAIL (раннер умеет падать)",
         fails == 1 and rows[1][0] == "FAIL")

    rows, fails, skips = run_gates([code2_gate], ROOT)
    case("допустимый код 2 не считается провалом", fails == 0 and rows[0][0] == "PASS")

    rows, fails, skips = run_gates([missing_gate], ROOT)
    case("отсутствующий скрипт даёт SKIP, а не ложный PASS/FAIL",
         skips == 1 and rows[0][0] == "SKIP" and fails == 0)

    with tempfile.TemporaryDirectory() as td:
        quick = {g[0] for g in _gates(True, td)}
        full = {g[0] for g in _gates(False, td)}
    case("--quick строго уже полного набора", quick < full)

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Все гейты проекта одной командой.")
    ap.add_argument("--quick", action="store_true",
                    help="без перф-гейта, полного eval и сборки архива")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not os.path.isfile(os.path.join(ROOT, "SKILL.md")):
        print("SKILL.md не найден рядом со scripts/ — запуск не из корня скилла",
              file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="humanizer-check-all-") as td:
        rows, fails, skips = run_gates(_gates(args.quick, td), ROOT)
    print(render(rows, fails, skips))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
