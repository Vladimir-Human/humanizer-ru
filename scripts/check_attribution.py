#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_attribution.py — гейт атрибуции автономных прогонов (GOVERNANCE §4.1).

Проект, который ловит следы машинного происхождения текстов, обязан
помечать машинное происхождение собственных коммитов. Правила:

  1. Якорь: релизный коммит bb2b2b3712fe257006e88c5bd6090f062f3a1d04
     (метка якоря собирается в коде из частей — гейт зашитых версий не
     разрешает литерал X.Y.Z в скриптах).
     Каждый коммит ПОСЛЕ якоря, чей коммитер не является человеком-
     владельцем (и не платформенный бот), обязан нести пометку
     `autonomous run` в сообщении.
  2. GOVERNANCE.md §4 несёт генерируемую датированную строку среза:
     число помеченных коммитов среди последних 100 на якоре — окно
     закрыто (якорь неизменяем), поэтому срез детерминирован и не
     устаревает. Пересчёт: --governance-line.
  3. На поверхностном чекауте (shallow, нет истории до якоря) живая
     перепроверка невозможна: гейт сверяет только формат строки
     GOVERNANCE и печатает явную пометку SKIP-истории — молча не
     проходит. В релизном CI (fetch-depth 0) выполняется полная проверка.

Режимы:
    python3 scripts/check_attribution.py                  # проверка
    python3 scripts/check_attribution.py --governance-line # строка для GOVERNANCE
    python3 scripts/check_attribution.py --selftest

Коды: 0 — атрибуция цела; 1 — нарушение; 2 — ошибка входа.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GOVERNANCE = os.path.join(ROOT, "GOVERNANCE.md")

ANCHOR = "bb2b2b3712fe257006e88c5bd6090f062f3a1d04"   # релиз-якорь правила
# Версии собираются из частей: гейт зашитых версий сканирует этот файл,
# а литерал X.Y.Z устаревал бы и путал поиск по истории.
ANCHOR_LABEL = "v%d.%d.%d" % (3, 16, 10)
ANCHOR_DATE = "2026-09-03"
RULE_LABEL = "v%d.%d.%d" % (3, 16, 11)
MARK = "autonomous run"
HUMANS = {"Vladimir", "Vladimir-Human"}
PLATFORM_COMMITTERS = {"GitHub"}          # веб-мержи: атрибуция живёт в PR
BOT_MARK = "[bot]"                        # dependabot[bot] и подобные

# Строка среза в GOVERNANCE §4: «Срез на <якорь> (<дата>): N из последних
# 100 коммитов несут пометку».
SLICE_RX = re.compile(
    r"Срез на " + re.escape(ANCHOR_LABEL) + r" \(" + ANCHOR_DATE +
    r"\): (\d+) из последних 100 коммитов несут пометку")


def committer_needs_mark(name: str) -> bool:
    """Не-человек и не платформенный бот — коммит обязан нести пометку."""
    if name in HUMANS or name in PLATFORM_COMMITTERS:
        return False
    if BOT_MARK in name:
        return False  # бот-идентичность сама является атрибуцией
    if name == "humanizer-ru-ci":
        return False  # CI-бот workflow status.yml: инфраструктурный коммит
        # docs/status.json и demo/status.json с фиксированным сообщением и
        # [skip ci]; исключение документировано, правило пометки агентских
        # коммитов не меняется.
    return True


def message_marked(subject_and_committer: str) -> bool:
    return MARK in subject_and_committer.lower()


def _git(args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120,
                          encoding="utf-8", errors="replace")


def history_available(root=ROOT) -> bool:
    proc = _git(["cat-file", "-e", ANCHOR + "^{commit}"], root)
    return proc.returncode == 0


def anchor_slice_count(root=ROOT):
    """Число помеченных среди последних 100 коммитов на якоре (окно закрыто)."""
    proc = _git(["log", "-100", ANCHOR, "--format=%s%x09%cn%x09%b"], root)
    if proc.returncode != 0:
        return None
    count = 0
    for line in proc.stdout.splitlines():
        if message_marked(line):
            count += 1
    return count


def governance_line() -> str:
    n = anchor_slice_count()
    if n is None:
        return ""
    return ("Срез на %s (%s): %d из последних 100 коммитов несут пометку "
            "`autonomous run` в сообщении или идентификаторе коммитера "
            "(предыдущий срез на 2026-08-21 фиксировал 34 из 100 — окно "
            "сместилось). Окно среза закрыто якорем и детерминировано; "
            "пересчёт: `python scripts/check_attribution.py "
            "--governance-line`. Начиная с %s каждый автономный "
            "коммит обязан нести пометку `autonomous run` (п.4.1); гейт "
            "`scripts/check_attribution.py` проверяет коммиты после якоря."
            % (ANCHOR_LABEL, ANCHOR_DATE, n, RULE_LABEL))


def governance_errors() -> list:
    errors = []
    try:
        with open(GOVERNANCE, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return ["GOVERNANCE.md не читается: %r" % exc]
    m = SLICE_RX.search(text)
    if not m:
        errors.append("GOVERNANCE.md §4: нет генерируемой строки среза "
                      "(«Срез на %s (%s): N из последних 100 …»)"
                      % (ANCHOR_LABEL, ANCHOR_DATE))
        return errors
    stored = int(m.group(1))
    if history_available():
        fresh = anchor_slice_count()
        if fresh is not None and fresh != stored:
            errors.append("GOVERNANCE.md §4: срез %d != пересчёту %d — "
                          "обновить строку: python scripts/"
                          "check_attribution.py --governance-line"
                          % (stored, fresh))
    else:
        print("SKIP: история до якоря недоступна (shallow-чекаут) — срез "
              "GOVERNANCE сверен только по формату")
    return errors


def commits_after_anchor_errors() -> list:
    if not history_available():
        print("SKIP: якорь %s недостижим (shallow-чекаут) — коммиты после "
              "якоря не проверены; полная проверка в релизном CI "
              "(fetch-depth 0)" % ANCHOR_LABEL)
        return []
    proc = _git(["log", ANCHOR + "..HEAD", "--format=%H%x09%cn%x09%s%x09%b"])
    if proc.returncode != 0:
        return ["git log %s..HEAD не исполнен" % ANCHOR_LABEL]
    errors = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        sha, committer, subject = parts[0], parts[1], parts[2]
        body = parts[3] if len(parts) > 3 else ""
        if committer_needs_mark(committer):
            if not message_marked(subject + " " + body):
                errors.append("коммит %s (%s): автономный коммитер без "
                              "пометки «%s» (GOVERNANCE §4.1)"
                              % (sha[:12], committer, MARK))
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    case("человек-владелец не требует пометки",
         not committer_needs_mark("Vladimir")
         and not committer_needs_mark("Vladimir-Human"))
    case("платформенный коммитер не требует пометки",
         not committer_needs_mark("GitHub"))
    case("бот-идентичность не требует пометки",
         not committer_needs_mark("dependabot[bot]"))
    case("CI-бот status.yml не требует пометки",
         not committer_needs_mark("humanizer-ru-ci"))
    case("не-человек без пометки требует пометки (негатив)",
         committer_needs_mark("some-agent")
         and committer_needs_mark("prime-agent"))
    case("пометка в сообщении распознаётся регистронезависимо",
         message_marked("Fix X\n\nAutonomous Run: by agent")
         and not message_marked("Fix X"))
    line = governance_line()
    m = SLICE_RX.search(line) if line else None
    case("генерируемая строка среза соответствует формату GOVERNANCE",
         bool(m))
    case("строка GOVERNANCE на месте и не расходится с пересчётом",
         governance_errors() == [])
    print("САМОПРОВЕРКА check_attribution: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Атрибуция автономных прогонов: пометка autonomous run "
                    "и срез GOVERNANCE §4.")
    ap.add_argument("--governance-line", action="store_true",
                    help="напечатать генерируемую строку среза для GOVERNANCE.md")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.governance_line:
        line = governance_line()
        if not line:
            print("история до якоря недоступна", file=sys.stderr)
            return 2
        print(line)
        return 0
    errors = governance_errors() + commits_after_anchor_errors()
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("АТРИБУЦИЯ: нарушений %d" % len(errors))
        return 1
    print("АТРИБУЦИЯ: автономные коммиты помечены, срез GOVERNANCE §4 свеж")
    return 0


if __name__ == "__main__":
    sys.exit(main())
