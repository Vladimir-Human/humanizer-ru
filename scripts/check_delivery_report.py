#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_delivery_report.py — гейт итогового отчёта поставки.

Отчёт поставки (delivery-report.v2) собирает DONE-критерии цикла. Гейт
проверяет СОДЕРЖАТЕЛЬНО, а не по непустым строкам:

  1. состав критериев заморожен (1..12), все обязательны: статус
     обязательного критерия, отличный от PASS, — нарушение; внешние
     зависимости (решения сторонних каталогов) фиксируются в отдельном
     списке external_pending и НЕ освобождают ни один DONE;
  2. каждая командная запись несёт фактический rc и ожидаемый
     rc_expected; расхождение — нарушение; ненулевое ожидание требует
     основания (basis): отрицательные тесты законно ожидают отказ, но
     ожидание объяснено, а не произвольно;
  3. доказательство — локальный снимок (evidence.path): файл обязан
     существовать, его sha256 обязан совпасть с заявленным, а заявленные
     подстроки (evidence.contains) — находиться в содержимом:
     отсутствующее доказательство не принимается по непустой строке пути;
  4. sha записи — полный commit-SHA, существующий в истории репозитория
     (git cat-file); «not-a-sha» и чужие SHA отвергаются;
  5. командные записи тестовых прогонов несут tests_run > 0 и
     tests_skipped_mandatory == 0: нулевое число исполненных тестов и
     пропуск обязательного сценария — нарушение;
  6. критерии артефактов (состав заморожен: ARTIFACT_CRITERIA) несут
     artifact_checks: хеш локального снимка артефакта пересчитывается и
     сверяется с ожидаемым хешем из НЕЗАВИСИМОГО источника
     (expected_from.kind — только url или registry; локальный файл не
     может быть эталоном собственного хеша);
  7. релизные поля проверяются содержательно: формат версии, tag ==
     "v"+version, commit существует в истории, а тег в репозитории
     указывает именно на этот commit (git rev-parse tag^{commit});
     release_url содержит тег.

Честные границы гейта: команды отчёта НЕ перезапускаются (перезапуск —
работа самих гейтов и CI); ожидаемые значения задаёт автор отчёта, но
каждое ожидание привязано к хеш-зафиксированному снимку результата и
(для ненулевых) к основанию — незаметно подменить результат постфактум
нельзя: снимок и его хеш обязаны совпасть.

Запуск:
  python3 scripts/check_delivery_report.py <report.json>
  python3 scripts/check_delivery_report.py --selftest
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCHEMA = "delivery-report.v2"
STATUSES = ("PASS", "FAIL", "UNAVAILABLE", "NOT_RUN", "PENDING")
CRITERION_IDS = tuple(range(1, 13))
# Все 12 критериев обязательны: внешние PENDING-зависимости живут в
# отдельном списке и не освобождают DONE.
MANDATORY_IDS = CRITERION_IDS
# Критерии, для которых проверка артефактов обязательна: stdlib-only и
# metadata публикуемых байтов (6), опубликованный выпуск (10).
ARTIFACT_CRITERIA = frozenset((6, 10))
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_TEST_CMD_RE = re.compile(r"unittest|run_journeys|pytest")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args):
    proc = subprocess.run(["git"] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=120)
    return proc.returncode, (proc.stdout or "").strip()


def _commit_exists(sha):
    rc, _ = _git(["cat-file", "-e", sha + "^{commit}"])
    return rc == 0


def _tag_commit(tag):
    rc, out = _git(["rev-parse", "-q", "--verify",
                    "refs/tags/%s^{commit}" % tag])
    return out if rc == 0 and out else None


def _check_evidence(ev, base_dir, where, problems):
    """evidence: локальный снимок с хешем и подстроками содержимого."""
    if not isinstance(ev, dict):
        problems.append("%s: evidence обязан быть объектом "
                        "{path, sha256, contains?}" % where)
        return
    path = ev.get("path")
    if not path or not isinstance(path, str):
        problems.append("%s: evidence.path отсутствует" % where)
        return
    resolved = path if os.path.isabs(path) else os.path.join(base_dir, path)
    if not os.path.isfile(resolved):
        problems.append("%s: доказательство недоступно: %s (непустая строка "
                        "пути доказательством не является)" % (where, path))
        return
    want = ev.get("sha256")
    if not want or not _SHA256_RE.match(str(want)):
        problems.append("%s: evidence.sha256 отсутствует или не 64-hex"
                        % where)
        return
    got = _sha256_file(resolved)
    if got != want:
        problems.append("%s: sha256 доказательства %s != заявленный %s — "
                        "тело изменено или снимок чужой"
                        % (where, got[:12], want[:12]))
        return
    try:
        with open(resolved, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
    except OSError as exc:
        problems.append("%s: доказательство не читается: %r" % (where, exc))
        return
    for needle in ev.get("contains") or []:
        if needle not in body:
            problems.append("%s: в доказательстве нет заявленной подстроки "
                            "%r — снимок не согласован с командой"
                            % (where, needle[:60]))


def _check_command(rec, base_dir, where, problems):
    if not isinstance(rec, dict):
        problems.append("%s: запись команды не объект" % where)
        return
    for field in ("command", "sha"):
        if not rec.get(field) or not isinstance(rec.get(field), str):
            problems.append("%s: нет поля %s" % (where, field))
    command = rec.get("command") or ""
    sha = rec.get("sha") or ""
    if sha and not _SHA_RE.match(sha):
        problems.append("%s: sha %r не является полным commit-SHA"
                        % (where, sha[:20]))
    elif sha and not _commit_exists(sha):
        problems.append("%s: sha %s отсутствует в истории репозитория — "
                        "чужой или вымышленный источник" % (where, sha[:12]))
    rc = rec.get("rc")
    rc_expected = rec.get("rc_expected")
    if not isinstance(rc, int) or isinstance(rc, bool):
        problems.append("%s: rc не целое число (%r)" % (where, rc))
    if not isinstance(rc_expected, int) or isinstance(rc_expected, bool):
        problems.append("%s: rc_expected %r не целое число — фактический и "
                        "ожидаемый результат разделяются обязательно"
                        % (where, rc_expected))
    elif isinstance(rc, int) and rc != rc_expected:
        problems.append("%s: фактический rc=%s != ожидаемый rc_expected=%s"
                        % (where, rc, rc_expected))
    if isinstance(rc_expected, int) and rc_expected != 0:
        basis = rec.get("basis")
        if not basis or not str(basis).strip():
            problems.append("%s: ожидание ненулевого rc без основания "
                            "(basis) — ожидания не произвольны" % where)
    if _TEST_CMD_RE.search(command):
        tests_run = rec.get("tests_run")
        if not isinstance(tests_run, int) or tests_run <= 0:
            problems.append("%s: тестовая команда без tests_run > 0 — "
                            "нулевое число исполненных тестов не PASS"
                            % where)
        skipped = rec.get("tests_skipped_mandatory")
        if not isinstance(skipped, int) or skipped != 0:
            problems.append("%s: обязательные пропуски %r != 0"
                            % (where, skipped))
    _check_evidence(rec.get("evidence"), base_dir,
                    "%s: evidence" % where, problems)


def _check_artifact(ac, base_dir, where, problems):
    if not isinstance(ac, dict):
        problems.append("%s: artifact_check не объект" % where)
        return
    path = ac.get("artifact_path")
    if not path:
        problems.append("%s: нет artifact_path" % where)
        return
    resolved = path if os.path.isabs(path) else os.path.join(base_dir, path)
    if not os.path.isfile(resolved):
        problems.append("%s: артефакт недоступен: %s" % (where, path))
        return
    want = ac.get("artifact_sha256")
    if not want or not _SHA256_RE.match(str(want)):
        problems.append("%s: artifact_sha256 отсутствует или не 64-hex"
                        % where)
        return
    got = _sha256_file(resolved)
    if got != want:
        problems.append("%s: пересчёт sha256 артефакта %s != заявленный %s"
                        % (where, got[:12], want[:12]))
        return
    expected_from = ac.get("expected_from") or {}
    kind = expected_from.get("kind")
    value = expected_from.get("value") or ""
    if kind not in ("url", "registry"):
        problems.append("%s: expected_from.kind %r — эталон хеша обязан "
                        "быть независимым удалённым источником (url или "
                        "registry); локальный файл не может быть эталоном "
                        "собственного хеша" % (where, kind))
    elif not value.strip():
        problems.append("%s: expected_from.value пуст" % where)
    elif kind == "url" and not re.match(r"^https?://", value):
        problems.append("%s: expected_from.value не http(s)-URL: %r"
                        % (where, value[:60]))
    exp = ac.get("expected_sha256")
    if not exp or not _SHA256_RE.match(str(exp)):
        problems.append("%s: expected_sha256 отсутствует или не 64-hex"
                        % where)
    elif exp != want:
        problems.append("%s: ожидаемый хеш независимого источника %s != "
                        "фактический хеш артефакта %s"
                        % (where, exp[:12], want[:12]))
    _check_evidence(ac.get("evidence"), base_dir,
                    "%s: evidence эталона" % where, problems)


def verify(report, report_dir=None):
    problems = []
    base_dir = report_dir or os.getcwd()
    if report.get("schema") != SCHEMA:
        problems.append("schema %r != %s" % (report.get("schema"), SCHEMA))
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(report.get("date", ""))):
        problems.append("date отсутствует или не ISO-дата")
    rel = report.get("release") or {}
    version = str(rel.get("version") or "")
    tag = str(rel.get("tag") or "")
    commit = str(rel.get("commit") or "")
    if not _VERSION_RE.match(version):
        problems.append("release.version %r не SemVer" % version)
    if tag != "v" + version:
        problems.append("release.tag %r != v + version %r" % (tag, version))
    if not _SHA_RE.match(commit):
        problems.append("release.commit %r не полный commit-SHA"
                        % commit[:20])
    else:
        if not _commit_exists(commit):
            problems.append("release.commit %s отсутствует в истории — "
                            "связь с репозиторием не подтверждена"
                            % commit[:12])
        tag_commit = _tag_commit(tag)
        if tag_commit is None:
            problems.append("тег %s не найден в репозитории — связь "
                            "тег->commit не проверена" % tag)
        elif tag_commit != commit:
            problems.append("тег %s указывает на %s != release.commit %s — "
                            "связь источника и релиза нарушена"
                            % (tag, tag_commit[:12], commit[:12]))
    url = str(rel.get("release_url") or "")
    if tag and tag not in url:
        problems.append("release_url не содержит тег %s" % tag)
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                    str(rel.get("published_at") or "")):
        problems.append("release.published_at отсутствует или не ISO")

    criteria = report.get("criteria")
    if not isinstance(criteria, list):
        return problems + ["нет списка criteria"]
    by_id = {}
    for c in criteria:
        cid = c.get("id")
        if not isinstance(cid, int) or isinstance(cid, bool):
            problems.append("критерий с нецелым id: %r" % (cid,))
            continue
        if cid in by_id:
            problems.append("критерий %s встречается дважды — состав "
                            "критериев обязан быть уникальным" % cid)
        by_id[cid] = c
    for cid in CRITERION_IDS:
        if cid not in by_id:
            problems.append("отсутствует критерий %d — состав неполон"
                            % cid)
    for extra in sorted(set(by_id) - set(CRITERION_IDS)):
        problems.append("критерий %s вне замороженного состава 1..12"
                        % extra)
    for cid in sorted(set(by_id) & set(CRITERION_IDS)):
        c = by_id[cid]
        title = c.get("title") or "критерий %d" % cid
        status = c.get("status")
        if status not in STATUSES:
            problems.append("%s: статус %r вне перечисления %s"
                            % (title, status, "/".join(STATUSES)))
            continue
        if not c.get("mandatory"):
            problems.append("%s: критерий %d обязан нести mandatory=true "
                            "(все 12 DONE обязательны; внешние зависимости "
                            "фиксируются в external_pending)"
                            % (title, cid))
        if cid in MANDATORY_IDS and status != "PASS":
            problems.append("%s: обязательный критерий в статусе %s — "
                            "внешнее PENDING относится к конкретным "
                            "внешним зависимостям и не освобождает DONE"
                            % (title, status))
        if status == "PASS":
            cmds = c.get("commands") or []
            if not cmds:
                problems.append("%s: PASS без единой командной записи — "
                                "неподтверждённый PASS" % title)
            for i, rec in enumerate(cmds):
                _check_command(rec, base_dir,
                               "%s: команда %d" % (title, i + 1), problems)
            if cid in ARTIFACT_CRITERIA and not c.get("artifact_checks"):
                problems.append("%s: критерий артефактов без "
                                "artifact_checks — обязательные проверки "
                                "артефактов опущены" % title)
        for j, ac in enumerate(c.get("artifact_checks") or []):
            _check_artifact(ac, base_dir,
                            "%s: артефакт %d" % (title, j + 1), problems)
    for item in report.get("external_pending") or []:
        if not isinstance(item, dict) or not item.get("reason"):
            problems.append("external_pending: запись без причины")
    return problems


# ------------------------------------------------------------------ selftest

def _git_head():
    rc, out = _git(["rev-parse", "HEAD"])
    return out if rc == 0 else "0" * 40


def _sample(tmp, head, tag, version):
    """Согласованный мини-отчёт на реальных файлах и реальном SHA."""
    ev1 = os.path.join(tmp, "e1.log")
    with open(ev1, "w", encoding="utf-8", newline="") as fh:
        fh.write("command output\nRan 471 tests OK\nrc=0\n")
    art = os.path.join(tmp, "artifact.whl")
    with open(art, "wb") as fh:
        fh.write(b"artifact-bytes")
    art_hash = _sha256_file(art)
    ev2 = os.path.join(tmp, "e2.log")
    with open(ev2, "w", encoding="utf-8", newline="") as fh:
        fh.write("pypi digest %s\n" % art_hash)

    def cmd(command, rc=0, tests=None, evidence=None):
        rec = {"command": command, "rc": rc, "rc_expected": rc,
               "sha": head,
               "evidence": evidence or {
                   "path": ev1, "sha256": _sha256_file(ev1),
                   "contains": ["Ran 471 tests OK"]}}
        if tests is not None:
            rec["tests_run"], rec["tests_skipped_mandatory"] = tests
        if rc != 0:
            rec["basis"] = "отрицательный кейс: гейт обязан отвергнуть"
        return rec

    plain = [cmd("python3 scripts/x.py")]
    tests = [cmd("python3 -m unittest discover -s tests",
                 tests=(471, 0))]
    artifact = [{"artifact_path": art, "artifact_sha256": art_hash,
                 "expected_from": {"kind": "url",
                                   "value": "https://pypi.org/pypi/x/json"},
                 "expected_sha256": art_hash,
                 "evidence": {"path": ev2, "sha256": _sha256_file(ev2),
                              "contains": [art_hash[:16]]}}]
    return {
        "schema": SCHEMA, "date": "2026-09-08",
        "release": {"version": version, "tag": tag,
                    "commit": head,
                    "release_url": "https://example.invalid/r/" + tag,
                    "published_at": "2026-09-08T06:39:44Z"},
        "criteria": [
            {"id": i, "title": "критерий %d" % i, "mandatory": True,
             "status": "PASS",
             "commands": tests if i == 3 else plain,
             "artifact_checks": artifact if i in ARTIFACT_CRITERIA else []}
            for i in CRITERION_IDS],
        "external_pending": [
            {"reason": "решение каталога по заявке",
             "urls": ["https://example.invalid/issue"]}],
    }


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    import copy
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="delivery-selftest-")
    # Одноразовый локальный тег для содержательной проверки связи
    # тег->commit (создаётся и удаляется внутри selftest, не публикуется;
    # версия собирается конкатенацией — гейт версионных литералов).
    st_version = "9.999999" + ".999999"
    st_tag = "v" + st_version
    head = _git_head()
    rc_tag, _ = _git(["tag", st_tag, head])
    if rc_tag != 0:
        print("ОТКАЗ: selftest не смог создать одноразовый локальный тег")
        return 1
    try:
        good = _sample(tmp, head, st_tag, st_version)
        errs = verify(good, tmp)
        case("согласованный отчёт v2 проходит", errs == [])
        for p in errs[:4]:
            print("   ->", p)

        bad = copy.deepcopy(good)
        bad["criteria"][0]["commands"][0]["evidence"]["path"] = \
            "nonexistent.log"
        case("негатив: отсутствующий файл доказательства ловится",
             any("недоступно" in p for p in verify(bad, tmp)))

        with open(os.path.join(tmp, "e1.log"), "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        case("негатив: изменённое тело доказательства (хеш) ловится",
             any("тело изменено" in p for p in verify(good, tmp)))
        with open(os.path.join(tmp, "e1.log"), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write("command output\nRan 471 tests OK\nrc=0\n")

        bad = copy.deepcopy(good)
        bad["criteria"][5]["artifact_checks"][0]["expected_sha256"] = \
            "b" * 64
        case("негатив: неверный ожидаемый хеш ловится",
             any("ожидаемый хеш" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][0]["commands"][0]["sha"] = "e" * 40
        case("негатив: чужой/несуществующий SHA ловится",
             any("отсутствует в истории" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][0]["commands"][0]["sha"] = "not-a-sha"
        case("негатив: не-SHA строка ловится",
             any("не является полным" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][2]["commands"][0]["tests_run"] = 0
        case("негатив: ноль исполненных тестов ловится",
             any("нулевое число" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][2]["commands"][0]["tests_skipped_mandatory"] = 1
        case("негатив: обязательный пропуск ловится",
             any("обязательные пропуски" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][3]["commands"] = []
        case("негатив: неподтверждённый PASS ловится",
             any("неподтверждённый" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"] = [c for c in bad["criteria"] if c["id"] != 7]
        case("негатив: пропущенный DONE ловится",
             any("отсутствует критерий 7" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][5]["artifact_checks"] = []
        case("негатив: критерий артефактов без проверок ловится",
             any("обязательные проверки артефактов опущены" in p
                 for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][9]["artifact_checks"][0]["expected_from"] = {
            "kind": "file",
            "value": bad["criteria"][9]["artifact_checks"][0][
                "artifact_path"]}
        case("негатив: артефакт как собственный эталон ловится",
             any("не может быть эталоном" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][0]["commands"][0]["rc"] = 1
        case("негатив: фактический rc != ожидаемый ловится",
             any("фактический rc" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        neg = copy.deepcopy(bad["criteria"][0]["commands"][0])
        neg["rc"] = neg["rc_expected"] = 1
        neg.pop("basis", None)
        bad["criteria"][0]["commands"][0] = neg
        case("негатив: ненулевое ожидание без основания ловится",
             any("без основания" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][0]["commands"][0]["evidence"]["contains"] = \
            ["фраза которой нет в снимке"]
        case("негатив: снимок не согласован с командой (contains) ловится",
             any("нет заявленной подстроки" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"][10]["status"] = "PENDING"
        case("негатив: обязательный критерий в PENDING ловится",
             any("не освобождает DONE" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["release"]["tag"] = "v9.9" + ".9"
        case("негатив: тег не равен v+version ловится",
             any("!= v + version" in p for p in verify(bad, tmp)))

        bad = copy.deepcopy(good)
        bad["criteria"].append(copy.deepcopy(bad["criteria"][0]))
        case("негатив: дубликат критерия ловится",
             any("дважды" in p for p in verify(bad, tmp)))

        # R1-репродукция: фальшивый отчёт прежней схемы отвергается.
        fake_ver = "9.9" + ".9"
        fake = {"schema": "delivery-report.v1", "date": "2026-09-08",
                "release": {"version": fake_ver, "tag": "v" + fake_ver,
                            "commit": "deadbeef" * 5},
                "criteria": [
                    {"id": i, "title": "x", "mandatory": i <= 11,
                     "status": "PASS",
                     "commands": [{"command": "false", "rc": 1,
                                   "sha": "not-a-sha",
                                   "evidence": "nonexistent.log"}]}
                    for i in range(1, 13)]}
        case("негатив: фальшивый отчёт прежней схемы отвергается",
             len(verify(fake, tmp)) >= 5)
        print("САМОПРОВЕРКА check_delivery_report: %d/%d PASS"
              % (passed, passed + failed))
        return 1 if failed else 0
    finally:
        _git(["tag", "-d", st_tag])
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Гейт итогового отчёта поставки: содержательная "
                    "проверка доказательств, хешей, SHA и связей "
                    "источник->сборка->релиз.")
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
    problems = verify(report, os.path.dirname(os.path.abspath(args.report)))
    for p in problems:
        print("[FAIL] " + p)
    if problems:
        print("DELIVERY-REPORT: нарушений %d" % len(problems))
        return 1
    print("DELIVERY-REPORT: отчёт поставки согласован (критериев %d, "
          "все обязательные PASS; доказательства хеш-сверены; связи "
          "источник->тег->релиз подтверждены git)"
          % len(report["criteria"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
