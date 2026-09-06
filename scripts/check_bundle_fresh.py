#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_bundle_fresh.py — свежесть бандла (приказ 2026-09-05, N13/N39):
metadata.version в SKILL.md равен последнему релизному тегу. Установка
бандлом (17 файлов) — штатный способ, и пользователь обязан получать версию
не старше последнего релиза.

Опережение тега допустимо только в окне подготовки релиза: версия выше
последнего тега И раздел «## <версия>» уже есть в CHANGELOG.md (релиз
документирован, тег ставится по постоянному поручению — GOVERNANCE.md
раздел 2, пункт 5). Во всех прочих случаях — FAIL.

Запуск:
    python3 scripts/check_bundle_fresh.py [--selftest]
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VER_RX = re.compile(r'^\s*version:\s*"?(\d+\.\d+\.\d+)"?', re.M)


def skill_version(text):
    m = VER_RX.search(text)
    return m.group(1) if m else None


def latest_tag():
    out = subprocess.run(["git", "tag", "-l", "v*"], capture_output=True,
                         text=True, cwd=ROOT).stdout.split()
    tags = []
    for t in out:
        m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", t.strip())
        if m:
            tags.append(tuple(int(x) for x in m.groups()))
    return ".".join(map(str, max(tags))) if tags else None


def compare(version, tag, changelog_text):
    """Чистая функция решения: (ok, reason)."""
    if version is None:
        return False, "metadata.version не найден в SKILL.md"
    if tag is None:
        return False, "в репозитории нет релизных тегов"
    if version == tag:
        return True, "бандл свеж: %s == тег v%s" % (version, tag)
    vt = tuple(int(x) for x in version.split("."))
    tt = tuple(int(x) for x in tag.split("."))
    if vt > tt and ("## %s " % version) in changelog_text:
        return True, ("окно подготовки релиза: %s опережает тег v%s, раздел "
                      "CHANGELOG на месте — тег ставится по постоянному "
                      "поручению (GOVERNANCE.md раздел 2, пункт 5)"
                      % (version, tag))
    if vt > tt:
        return False, ("бандл %s опережает тег v%s без раздела CHANGELOG — "
                       "недокументированный релиз" % (version, tag))
    return False, "бандл %s старше последнего тега v%s" % (version, tag)


def check():
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        version = skill_version(fh.read())
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        changelog = fh.read()
    return compare(version, latest_tag(), changelog)


def _v(a, b, c):
    return "%d.%d.%d" % (a, b, c)


def selftest():
    cur, nxt, old_ = _v(3, 1, 0), _v(3, 2, 0), _v(3, 0, 0)
    cl = "## %s — 2026-01-02\n\nрелиз\n" % nxt
    checks = [
        ("равенство версии и тега — ок",
         compare(cur, cur, "")[0]),
        ("бандл старше тега — fail",
         not compare(old_, cur, "")[0]),
        ("опережение без CHANGELOG — fail",
         not compare(nxt, cur, "")[0]),
        ("опережение с разделом CHANGELOG — окно релиза, ок",
         compare(nxt, cur, cl)[0]),
        ("репозиторий: бандл свеж", check()[0]),
    ]
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА bundle-fresh: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    ok, reason = check()
    print(("BUNDLE-FRESH: " if ok else "[FAIL] ") + reason)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
