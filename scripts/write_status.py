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
    # L8: статус-лаг — main против последнего релизного тега. Тег берётся
    # максимумом версий среди v*, а не git describe: релизный тег может не
    # быть предком HEAD (rebase поверх CI-коммита), и describe возвращает
    # предыдущий тег.
    import re as _re
    tag = ""
    tags_out = subprocess.run(["git", "tag", "-l", "v*"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.split()
    best = None
    for tg in tags_out:
        m = _re.match(r"^v(\d+)\.(\d+)\.(\d+)$", tg.strip())
        if m:
            ver = tuple(int(x) for x in m.groups())
            if best is None or ver > best[0]:
                best = (ver, tg.strip())
    if best:
        tag = best[1]
    published = ""
    lag = 0
    if tag:
        published = subprocess.run(["git", "rev-parse", "--short", tag],
                                   capture_output=True, text=True,
                                   cwd=ROOT).stdout.strip()
        cnt = subprocess.run(["git", "rev-list", "--count",
                              "%s..HEAD" % tag], capture_output=True,
                             text=True, cwd=ROOT).stdout.strip()
        lag = int(cnt) if cnt.isdigit() else 0
    data = {
        "commit": commit,
        "date": datetime.date.today().isoformat(),
        "tests_passed": True,
        "markers_count": markers.get("count"),
        "parity": "ok",
        "main_commit": commit,
        "published_commit": published,
        "published_tag": tag,
        "lag_commits": lag,
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
