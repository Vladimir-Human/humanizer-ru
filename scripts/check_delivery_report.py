#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_delivery_report.py — гейт итогового отчёта поставки.

Отчёт поставки (delivery-report.v1) собирает DONE-критерии цикла: каждый
критерий несёт статус (PASS/FAIL/UNAVAILABLE/NOT_RUN/PENDING), команды с
кодами возврата, SHA дерева/коммита и ссылку на свидетельство. Гейт
отвергает:

  1. отсутствующий критерий (состав 1..12 заморожен здесь);
  2. обязательный критерий (mandatory) в статусе SKIP/UNAVAILABLE/
     PENDING/NOT_RUN/FAIL — обязательный PASS не заменяется пропуском;
  3. неподтверждённый PASS: статус PASS без хотя бы одной записи
     {command, rc, sha, evidence} с непустыми полями;
  4. артефакт, сравненный сам с собой: artifact_check обязан нести
     РАЗНЫЕ источники факта и эталона (artifact_source != expected_source);
     скачанный файл не может быть эталоном собственного хеша;
  5. статус вне перечисления; rc не целое; дата/релизные поля пустые.

Запуск:
  python3 scripts/check_delivery_report.py <report.json>
  python3 scripts/check_delivery_report.py --selftest
"""
import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

SCHEMA = "delivery-report.v1"
STATUSES = ("PASS", "FAIL", "UNAVAILABLE", "NOT_RUN", "PENDING")
CRITERION_IDS = tuple(range(1, 13))
# Обязательные критерии: их PASS не заменяется пропуском. Состав —
# ядро поставки (потоки и публикация); внешне-зависимые критерии
# (сторонние каталоги) обязательными не объявляются.
MANDATORY_IDS = tuple(range(1, 12))


def verify(report):
    problems = []
    if report.get("schema") != SCHEMA:
        problems.append("schema %r != %s" % (report.get("schema"), SCHEMA))
    for field in ("date", "release"):
        if not report.get(field):
            problems.append("нет поля %s" % field)
    rel = report.get("release") or {}
    for field in ("version", "tag", "commit"):
        if not rel.get(field):
            problems.append("release: нет поля %s" % field)
    criteria = report.get("criteria")
    if not isinstance(criteria, list):
        return problems + ["нет списка criteria"]
    by_id = {}
    for c in criteria:
        cid = c.get("id")
        if cid in by_id:
            problems.append("критерий %s дважды" % cid)
        by_id[cid] = c
    for cid in CRITERION_IDS:
        if cid not in by_id:
            problems.append("отсутствует критерий %d — состав неполон"
                            % cid)
    for cid, c in sorted(by_id.items(), key=lambda kv: str(kv[0])):
        title = c.get("title") or "критерий %s" % cid
        status = c.get("status")
        if status not in STATUSES:
            problems.append("%s: статус %r вне перечисления %s"
                            % (title, status, "/".join(STATUSES)))
            continue
        mandatory = c.get("mandatory")
        if cid in MANDATORY_IDS and not mandatory:
            problems.append("%s: критерий %d обязан нести mandatory=true "
                            "(состав заморожен гейтом)" % (title, cid))
        if mandatory and status != "PASS":
            problems.append("%s: обязательный критерий в статусе %s — "
                            "обязательный PASS не заменяется пропуском"
                            % (title, status))
        if status == "PASS":
            cmds = c.get("commands") or []
            ok_cmd = False
            for rec in cmds:
                if all(str(rec.get(k, "")).strip()
                       for k in ("command", "sha", "evidence")) \
                        and isinstance(rec.get("rc"), int):
                    ok_cmd = True
                else:
                    problems.append("%s: запись команды неполна "
                                    "(command/rc/sha/evidence)" % title)
            if not ok_cmd:
                problems.append("%s: PASS без подтверждённой команды "
                                "(command+rc+sha+evidence) — неподтверждённый "
                                "PASS" % title)
        for ac in c.get("artifact_checks") or []:
            src = ac.get("artifact_source")
            exp = ac.get("expected_source")
            if not src or not exp:
                problems.append("%s: artifact_check без источника факта "
                                "или эталона" % title)
            elif src == exp:
                problems.append("%s: артефакт сравнен сам с собой "
                                "(artifact_source == expected_source %r) — "
                                "эталон обязан быть независимым"
                                % (title, src))
            if not ac.get("sha256"):
                problems.append("%s: artifact_check без sha256" % title)
    return problems


def _sample_report():
    return {
        "schema": SCHEMA,
        "date": "2026-09-08",
        "release": {"version": "example-version", "tag": "v-example",
                    "commit": "0" * 40,
                    "release_url": "https://example.invalid/r/1"},
        "criteria": [
            {"id": i, "title": "критерий %d" % i,
             "mandatory": i in MANDATORY_IDS,
             "status": "PASS" if i <= 11 else "PENDING",
             "commands": [{"command": "python3 scripts/x.py", "rc": 0,
                           "sha": "0" * 40,
                           "evidence": "journal.md#L10"}]
             if i <= 11 else [],
             "artifact_checks": (
                 [{"artifact_source": "pypi:humanizer-ru:example:sdist",
                   "expected_source":
                       "https://example.invalid/release-notes",
                   "sha256": "a" * 64}] if i == 11 else [])}
            for i in CRITERION_IDS
        ],
    }


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    import copy
    good = _sample_report()
    case("согласованный отчёт проходит", verify(good) == [])

    bad = copy.deepcopy(good)
    bad["criteria"] = [c for c in bad["criteria"] if c["id"] != 7]
    case("мутант: отсутствующий критерий ловится",
         any("отсутствует критерий 7" in p for p in verify(bad)))

    bad = copy.deepcopy(good)
    bad["criteria"][2]["status"] = "UNAVAILABLE"
    bad["criteria"][2]["commands"] = []
    case("мутант: обязательный критерий пропущен (UNAVAILABLE) ловится",
         any("обязательный" in p for p in verify(bad)))

    bad = copy.deepcopy(good)
    bad["criteria"][4]["commands"] = []
    case("мутант: неподтверждённый PASS ловится",
         any("неподтверждённый" in p for p in verify(bad)))

    bad = copy.deepcopy(good)
    bad["criteria"][4]["commands"] = [
        {"command": "x", "rc": "0", "sha": "0" * 40, "evidence": "e"}]
    case("мутант: rc строкой — запись неполна",
         any("неполна" in p for p in verify(bad)))

    bad = copy.deepcopy(good)
    bad["criteria"][10]["artifact_checks"] = [
        {"artifact_source": "dist/artifact-example.tar.gz",
         "expected_source": "dist/artifact-example.tar.gz",
         "sha256": "a" * 64}]
    case("мутант: артефакт сравнен сам с собой ловится",
         any("сам с собой" in p for p in verify(bad)))

    bad = copy.deepcopy(good)
    bad["criteria"][0]["status"] = "SKIP"
    case("мутант: статус вне перечисления (SKIP) ловится",
         any("вне перечисления" in p for p in verify(bad)))

    bad = copy.deepcopy(good)
    bad["criteria"][11]["mandatory"] = False
    case("внешне-зависимый критерий PENDING без mandatory — допустим",
         verify(bad) == [])

    print("САМОПРОВЕРКА check_delivery_report: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Гейт итогового отчёта поставки (DONE-критерии, "
                    "подтверждения, независимость эталонов).")
    ap.add_argument("report", nargs="?", help="путь к report.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.report:
        ap.print_help()
        return 2
    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    problems = verify(report)
    for p in problems:
        print("[FAIL] " + p)
    if problems:
        print("DELIVERY-REPORT: нарушений %d" % len(problems))
        return 1
    print("DELIVERY-REPORT: отчёт поставки согласован (критериев %d, "
          "обязательных PASS %d)"
          % (len(report.get("criteria") or []),
             sum(1 for c in report.get("criteria") or []
                 if c.get("mandatory") and c.get("status") == "PASS")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
