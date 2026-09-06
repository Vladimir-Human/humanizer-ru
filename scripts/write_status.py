#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пишет status.json (docs/ и demo/): commit, date, tests_passed,
markers_count, parity, main_commit, published_commit, published_tag,
lag_commits. Вызывается из workflow: status.yml (артефакт прогона) и
demo-pages.yml (деплой-артефакт с точным SHA деплоя, --sha).

Утверждения статуса выводятся только из результата реального прогона:
--run-result FILE обязателен и несёт JSON {"sha", "tests_passed",
"parity"}; без результата или с непройденными проверками статус не
пишется (код 2) — заявлять непроверенное нельзя. SHA результата обязан
совпадать с SHA статуса (чужой SHA отвергается, код 2).

Семантика полей (разные сущности не подменяют друг друга):
  commit / main_commit — SHA main/деплоя, для которого собран статус;
  published_commit   — КОММИТ, на который указывает релизный тег
                       (git rev-parse <tag>^{commit}), не SHA объекта тега;
  published_tag      — имя последнего релизного тега (максимум версий v*);
  lag_commits        — число коммитов main после релизного тега;
  tests_passed/parity — из результата прогона (true/"ok" либо отказ);
  null у published_* и lag_commits, если тегов нет вовсе: неизвестный
  релиз НЕ равен нулевому лагу.

Коды: 0 — статус записан; 2 — вход/результат прогона непригодны.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(args, root):
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          cwd=root).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default=None,
                    help="SHA деплоя/прогона вместо git HEAD")
    ap.add_argument("--root", default=ROOT,
                    help="корень репозитория (для самопроверок)")
    ap.add_argument("--run-result", default=None,
                    help="JSON результата прогона {sha, tests_passed, "
                         "parity}; обязателен: статус не может утверждать "
                         "непроверенное")
    args = ap.parse_args(argv)
    root = args.root

    if not args.run_result:
        print("СТАТУС: --run-result обязателен: утверждения tests_passed/"
              "parity выводятся из результата реального прогона, а не "
              "пишутся заранее", file=sys.stderr)
        return 2
    try:
        with open(args.run_result, encoding="utf-8") as fh:
            run_result = json.load(fh)
    except (OSError, ValueError) as exc:
        print("СТАТУС: результат прогона не читается: %r" % exc,
              file=sys.stderr)
        return 2
    if not isinstance(run_result, dict):
        print("СТАТУС: результат прогона не является объектом",
              file=sys.stderr)
        return 2

    commit = args.sha or _git(["rev-parse", "--short", "HEAD"], root)
    rr_sha = str(run_result.get("sha") or "")
    if not rr_sha or not (rr_sha.startswith(commit)
                          or commit.startswith(rr_sha)):
        print("СТАТУС: чужой SHA: результат прогона %r не соответствует "
              "SHA статуса %r" % (rr_sha, commit), file=sys.stderr)
        return 2
    if run_result.get("tests_passed") is not True \
            or run_result.get("parity") != "ok":
        print("СТАТУС: прогон не зелёный (tests_passed=%r, parity=%r) — "
              "статус не публикуется" % (run_result.get("tests_passed"),
                                         run_result.get("parity")),
              file=sys.stderr)
        return 2

    markers = json.load(open(os.path.join(root, "markers.v1.json"),
                             encoding="utf-8"))
    # L8: статус-лаг — main против последнего релизного тега. Тег берётся
    # максимумом версий среди v*, а не git describe: релизный тег может не
    # быть предком HEAD (rebase поверх CI-коммита), и describe возвращает
    # предыдущий тег.
    import re as _re
    tag = ""
    tags_out = _git(["tag", "-l", "v*"], root).split()
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
    if not tag:
        tag = None
    if tag:
        # Целевой КОММИТ annotated-тега (не SHA объекта тега).
        published = _git(["rev-parse", "--short", tag + "^{commit}"], root)
        head = args.sha or "HEAD"
        cnt = _git(["rev-list", "--count", "%s..%s" % (tag, head)], root)
        lag = int(cnt) if cnt.isdigit() else None
    data = {
        "commit": commit,
        "date": datetime.date.today().isoformat(),
        "tests_passed": run_result.get("tests_passed") is True,
        "markers_count": markers.get("count"),
        "parity": str(run_result.get("parity")),
        "main_commit": commit,
        "published_commit": published,
        "published_tag": tag,
        "lag_commits": lag,
    }
    for rel in ("docs", "demo"):
        out = os.path.join(root, rel, "status.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    print("Записан status.json (docs и demo):", commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
