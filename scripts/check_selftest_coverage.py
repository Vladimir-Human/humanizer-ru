#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_selftest_coverage.py — каждый скрипт-гейт из check_all.py поддерживает
--selftest (приказ 2026-09-05, L6; инвариант 5 AGENTS.md). Selftest с негативом."""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_RX = re.compile(r"\"((?:scripts|tools|eval)/[A-Za-z0-9_./-]+\.py)\"")


def gate_scripts(check_all_text):
    return sorted(set(SCRIPT_RX.findall(check_all_text)))


def missing_selftest(scripts, root=ROOT):
    out = []
    for rel in scripts:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            out.append((rel, "файл отсутствует"))
            continue
        try:
            body = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            out.append((rel, "не читается: %s" % exc))
            continue
        if "--selftest" not in body:
            out.append((rel, "нет --selftest"))
    return out


def check():
    with open(os.path.join(ROOT, "scripts", "check_all.py"),
              encoding="utf-8") as fh:
        scripts = gate_scripts(fh.read())
    return scripts, missing_selftest(scripts)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "scripts"))
        good = os.path.join(td, "scripts", "good.py")
        bad = os.path.join(td, "scripts", "bad.py")
        with open(good, "w", encoding="utf-8") as fh:
            fh.write("# --selftest supported\n")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("# no selftest here\n")
        neg_ok = missing_selftest(["scripts/bad.py"], root=td) != []
        pos_ok = missing_selftest(["scripts/good.py"], root=td) == []
    checks = [
        ("негатив: скрипт без --selftest ловится", neg_ok),
        ("позитив: скрипт с --selftest проходит", pos_ok),
        ("репозиторий: покрытие полное", check()[1] == []),
        ("негатив: пустой список не ломает функцию",
         missing_selftest([]) == []),
    ]
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА selftest-coverage: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    scripts, missing = check()
    for rel, why in missing:
        print("[FAIL] %s: %s" % (rel, why))
    if missing:
        print("SELFTEST-COVERAGE: %d скриптов check_all без --selftest"
              % len(missing))
        return 1
    print("SELFTEST-COVERAGE: все %d скриптов check_all поддерживают "
          "--selftest" % len(scripts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
