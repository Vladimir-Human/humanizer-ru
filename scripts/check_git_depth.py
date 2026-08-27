#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_git_depth.py — shallow-клон ловится до того, как станет причиной лжи.

Shallow clone молчит о половине истории: «commit не существует» на глубине
18 коммитов — это не факт, а артефакт клона. Гейт fail-closed: репозиторий
shallow — ошибка, полный — OK.

CLI:
    python3 scripts/check_git_depth.py
    python3 scripts/check_git_depth.py --selftest

Коды: 0 — полный клон; 1 — shallow (требуется git fetch --unshallow);
2 — не git-репозиторий или отказ git. Только стандартная библиотека.
"""
import argparse
import os
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _git(*args):
    """Выполнить git-команду, вернуть stdout или None."""
    r = subprocess.run(
        ["git"] + list(args), cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def run():
    # is-shallow-repository: "true" или "false"
    shallow = _git("rev-parse", "--is-shallow-repository")
    if shallow is None:
        print("GIT-DEPTH: не git-репозиторий или git недоступен.", file=sys.stderr)
        return 2

    if shallow == "true":
        print("[FAIL] Репозиторий shallow: git-утверждения об истории недостоверны.")
        print("       Исправление: git fetch --unshallow")
        return 1

    count = _git("rev-list", "--count", "HEAD")
    print("GIT-DEPTH: полный клон, %s коммитов." % (count or "?"))
    return 0


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    with tempfile.TemporaryDirectory(prefix="git-depth-") as tmp:
        # Полный клон: обычный git init + commit
        full = os.path.join(tmp, "full")
        os.makedirs(full)
        subprocess.run(["git", "init", "-q"], cwd=full, capture_output=True)
        with open(os.path.join(full, "f.txt"), "w") as fh:
            fh.write("x\n")
        subprocess.run(["git", "add", "."], cwd=full, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init",
             "--author", "t <t@t>", "--date", "2026-01-01"],
            cwd=full, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

        r = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=full, capture_output=True, text=True)
        case("обычный init → не shallow", r.stdout.strip() == "false")

        # Shallow: git clone --depth 1
        shallow = os.path.join(tmp, "shallow")
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", "file://" + full, shallow],
            capture_output=True)
        r2 = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=shallow, capture_output=True, text=True)
        case("clone --depth 1 → shallow", r2.stdout.strip() == "true")

        # .git/shallow существует
        case(".git/shallow существует в shallow-клоне",
             os.path.isfile(os.path.join(shallow, ".git", "shallow")))
        case(".git/shallow не существует в полном",
             not os.path.isfile(os.path.join(full, ".git", "shallow")))

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Гейт shallow-клона.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    return run()


if __name__ == "__main__":
    sys.exit(main())
