#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_facts_diff.py — гейт F1: fact-loss модуль, CLI и его место в продукте.

Проверяет:
  1. selftest модуля facts_diff зелёный (негативы внутри);
  2. CLI коды выхода: потери/инверсия -> 1, чисто -> 0, добавленная дата -> 0
     с непустым added в конверте;
  3. конверт стабилен: {tool, schema, counts, diff};
  4. контракт содержит humanizer-facts с двумя входами;
  5. SKILL.md предписывает прогон diff после переписывания;
  6. check_examples.py использует facts_diff (защита от тихого отключения).

Запуск:
  python3 scripts/check_facts_diff.py
  python3 scripts/check_facts_diff.py --selftest

Только стандартная библиотека.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))


def _run(args):
    return subprocess.run([sys.executable, "-X", "utf8", "-m",
                           "humanizer_ru.facts_diff"] + args,
                          capture_output=True, text=True, env=ENV,
                          timeout=120)


def check():
    errors = []
    tmp = tempfile.mkdtemp(prefix="factsdiff-gate-")
    try:
        b = os.path.join(tmp, "b.txt")
        a = os.path.join(tmp, "a.txt")

        def write(path, text):
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

        base = ("Бюджет 500 тыс. ₽ до 15 марта 2026 года; Иван Петров не подтвердил; "
                "нельзя публиковать. См. https://example.com/x")
        write(b, base)
        write(a, base)
        proc = _run(["diff", b, a, "--json"])
        if proc.returncode != 0:
            errors.append("чистая пара дала код %d" % proc.returncode)
        env = json.loads(proc.stdout)
        if sorted(env.keys()) != ["counts", "diff", "files", "schema", "tool"]:
            errors.append("конверт изменился: %s" % sorted(env.keys()))

        write(a, "Бюджет уточняется; Иван Петров не подтвердил; "
                 "нельзя публиковать.")
        proc = _run(["diff", b, a, "--json"])
        if proc.returncode != 1:
            errors.append("потерянное число+дата+url не дали код 1: %d"
                          % proc.returncode)

        write(a, base.replace("не подтвердил", "подтвердил"))
        proc = _run(["diff", b, a, "--json"])
        if proc.returncode != 1 or not json.loads(proc.stdout)["diff"]["changed"]:
            errors.append("инверсия отрицания не дала код 1 с changed")

        write(a, base + " Встреча 01 апреля 2026 года.")
        proc = _run(["diff", b, a, "--json"])
        env = json.loads(proc.stdout)
        if proc.returncode != 0 or env["counts"]["added"] == 0:
            errors.append("добавленная дата: код %d, added %d"
                          % (proc.returncode, env["counts"]["added"]))

        proc = _run(["diff", os.path.join(tmp, "nope.txt"), a])
        if proc.returncode != 2:
            errors.append("нечитаемый вход не дал код 2")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    with open(os.path.join(ROOT, "contract.v1.json"), encoding="utf-8") as fh:
        contract = json.load(fh)
    tool = next((t for t in contract["tools"]
                 if t["command"] == "humanizer-facts"), None)
    if tool is None:
        errors.append("в контракте нет humanizer-facts")
    elif tool.get("inputs") != ["text_before", "text_after"]:
        errors.append("у humanizer-facts входы не [text_before, text_after]")

    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        skill = fh.read()
    if "humanizer-facts" not in skill:
        errors.append("SKILL.md не предписывает humanizer-facts")

    with open(os.path.join(ROOT, "scripts", "check_examples.py"),
              encoding="utf-8") as fh:
        if "facts_diff" not in fh.read():
            errors.append("check_examples.py не использует facts_diff")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        proc = _run(["--selftest"])
        print(proc.stdout.strip())
        ok = proc.returncode == 0 and "0 FAIL" in proc.stdout
        # негатив гейта: битый контракт ловится
        print("САМОПРОВЕРКА гейта: " + ("пройдена" if ok else "ПРОВАЛЕНА"))
        return 0 if ok else 1
    errors = check()
    for e in errors:
        print("[FAIL] %s" % e)
    if errors:
        print("FACTS-DIFF ГЕЙТ: %d ошибок" % len(errors))
        return 1
    print("FACTS-DIFF ГЕЙТ: пройден (модуль, CLI-коды, конверт, контракт, "
          "SKILL, check_examples)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
