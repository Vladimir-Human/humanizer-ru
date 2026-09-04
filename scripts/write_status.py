#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пишет docs/status.json: commit, date, tests_passed, markers_count, parity.
Вызывается только из workflow status.yml после зелёных тестов и паритета,
поэтому файл обновляется исключительно успешным прогоном main."""
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True,
                            cwd=ROOT).stdout.strip()
    markers = json.load(open(os.path.join(ROOT, "markers.v1.json"),
                             encoding="utf-8"))
    data = {
        "commit": commit,
        "date": datetime.date.today().isoformat(),
        "tests_passed": True,
        "markers_count": markers.get("count"),
        "parity": "ok",
    }
    for rel in ("docs", "demo"):
        out = os.path.join(ROOT, rel, "status.json")
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    print("Записан status.json (docs и demo):", commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
