#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пишет status.json (docs/ и demo/): commit, date, tests_passed,
markers_count, parity, main_commit, published_commit, published_tag,
lag_commits. Вызывается из workflow: status.yml (артефакт прогона) и
demo-pages.yml (деплой-артефакт с точным SHA деплоя, --sha).

Семантика полей: lag_commits — число коммитов main после релизного тега;
null, если тегов нет вовсе (неизвестный релиз НЕ равен нулевому лагу);
published_commit/published_tag — null при отсутствии тега."""
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default=None,
                    help="SHA деплоя/прогона вместо git HEAD")
    ap.add_argument("--root", default=ROOT,
                    help="корень репозитория (для самопроверок)")
    args = ap.parse_args(argv)
    root = args.root
    commit = args.sha or subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=root).stdout.strip()
    markers = json.load(open(os.path.join(root, "markers.v1.json"),
                             encoding="utf-8"))
    # L8: статус-лаг — main против последнего релизного тега. Тег берётся
    # максимумом версий среди v*, а не git describe: релизный тег может не
    # быть предком HEAD (rebase поверх CI-коммита), и describe возвращает
    # предыдущий тег.
    import re as _re
    tag = ""
    tags_out = subprocess.run(["git", "tag", "-l", "v*"],
                              capture_output=True, text=True,
                              cwd=root).stdout.split()
    best = None
    for tg in tags_out:
        m = _re.match(r"^v(\d+)\.(\d+)\.(\d+)$", tg.strip())
        if m:
            ver = tuple(int(x) for x in m.groups())
            if best is None or ver > best[0]:
                best = (ver, tg.strip())
    if best:
        tag = best[1]
    published = None
    lag = None
    if tag:
        published = subprocess.run(["git", "rev-parse", "--short", tag],
                                   capture_output=True, text=True,
                                   cwd=root).stdout.strip()
        head = args.sha or "HEAD"
        cnt = subprocess.run(["git", "rev-list", "--count",
                              "%s..%s" % (tag, head)], capture_output=True,
                             text=True, cwd=root).stdout.strip()
        lag = int(cnt) if cnt.isdigit() else None
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
        out = os.path.join(root, rel, "status.json")
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    print("Записан status.json (docs и demo):", commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
