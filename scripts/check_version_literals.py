#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_version_literals.py — semver-литералы в scripts/ и tests/.

Зашитая версия вида X.Y.Z в валидаторе или тесте устаревает с каждым
выпуском и при этом читается как факт. Каноничная версия живёт в одном
месте — src/humanizer_ru/__init__.py.

Исключения (полномочные места литерала):
 1. src/humanizer_ru/__init__.py — каноничная __version__;
 2. scripts/check_docs.py — гейт согласованности версии, его паттерны
    и фикстуры самопроверки по необходимости цитируют версии;
 3. документация *.md (не сканируется).

CLI:
    python3 scripts/check_version_literals.py            # проверка репозитория
    python3 scripts/check_version_literals.py --selftest # PASS/FAIL

Коды: 0 — нарушений нет; 1 — есть литералы вне положенных мест;
2 — ошибка запуска. Только стандартная библиотека.
"""
import argparse
import os
import re
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VERSION_RE = re.compile(r"\d+\.\d+\.\d+")

# Файлы, где литерал версии законен (относительно корня, с /).
# Гейт сверы версий, собственные selftest-фикстуры, гейты с историческими
# комментариями об уроках прошлых версий и тестовыми версиями манифестов.
ALLOWED_FILES = frozenset((
    "scripts/check_docs.py",
    "scripts/check_version_literals.py",
    "scripts/check_release.py",
    "scripts/check_outward.py",
    "scripts/check_fixture_sources.py",
    "scripts/check_corpus.py",
    "scripts/check_examples.py",
    "scripts/scan_soft_signals.py",
))


def scan_file(path, rel):
    """Возвращает список (строка, литерал) для одного файла."""
    findings = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return findings
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in VERSION_RE.finditer(line):
            findings.append((lineno, m.group(0), line.strip()[:80]))
    return findings


def run():
    errors = []
    for sub in ("scripts", "tests"):
        base = os.path.join(ROOT, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                fp = os.path.join(dirpath, name)
                rel = os.path.relpath(fp, ROOT).replace(os.sep, "/")
                if rel in ALLOWED_FILES:
                    continue
                for lineno, literal, context in scan_file(fp, rel):
                    errors.append(
                        "%s:%d: литерал версии «%s» — %s"
                        % (rel, lineno, literal, context))
    if errors:
        for e in errors:
            print("[FAIL] " + e)
        print("VERSION-LITERALS: %d зашитых версий вне положенных мест."
              % len(errors))
        return 1
    print("VERSION-LITERALS: зашитых версий в scripts/tests нет.")
    return 0


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    with tempfile.TemporaryDirectory(prefix="version-literals-") as tmp:
        # Мини-репозиторий
        os.makedirs(os.path.join(tmp, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "tests"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "src", "humanizer_ru"), exist_ok=True)

        # Каноничная версия — разрешена
        io_path = os.path.join(tmp, "src", "humanizer_ru", "__init__.py")
        # __init__.py не сканируется (не в scripts/ или tests/) — просто создаём
        with open(io_path, "w") as fh:
            fh.write('__version__ = "3.15.1"\n')

        # Разрешённый файл — гейт версий
        allowed = os.path.join(tmp, "scripts", "check_docs.py")
        with open(allowed, "w") as fh:
            fh.write('# паттерн для версий 3.15.1 в CHANGELOG\n')

        # Запрещённый: версия в тесте
        bad_test = os.path.join(tmp, "tests", "test_bad.py")
        with open(bad_test, "w") as fh:
            fh.write("def test():\n    assert version == '9.9.9'\n")

        # Запрещённый: версия в комментарии скрипта
        bad_script = os.path.join(tmp, "scripts", "check_bad.py")
        with open(bad_script, "w") as fh:
            fh.write("# проверено в версии 2.3.4\n")

        # Чистый файл
        clean = os.path.join(tmp, "scripts", "check_clean.py")
        with open(clean, "w") as fh:
            fh.write("# чистый скрипт без версий\n")

        # Сканируем как run() но с tmp как ROOT
        global ROOT
        old_root = ROOT
        ROOT = tmp
        try:
            errors = []
            for sub in ("scripts", "tests"):
                base = os.path.join(tmp, sub)
                if not os.path.isdir(base):
                    continue
                for dirpath, _dirs, files in os.walk(base):
                    for name in sorted(files):
                        if not name.endswith(".py"):
                            continue
                        fp = os.path.join(dirpath, name)
                        rel = os.path.relpath(fp, tmp).replace(os.sep, "/")
                        if rel in ALLOWED_FILES:
                            continue
                        for lineno, literal, ctx in scan_file(fp, rel):
                            errors.append((rel, lineno, literal))

            case("разрешённый check_docs.py не flagged",
                 not any("check_docs" in e[0] for e in errors))
            case("9.9.9 в тесте поймана",
                 any("9.9.9" in e[2] and "test_bad" in e[0] for e in errors))
            case("2.3.4 в комментарии поймана",
                 any("2.3.4" in e[2] and "check_bad" in e[0] for e in errors))
            case("чистый файл не flagged",
                 not any("check_clean" in e[0] for e in errors))
            case("ровно две ошибки",
                 len(errors) == 2)
        finally:
            ROOT = old_root

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Гейт зашитых версий.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    return run()


if __name__ == "__main__":
    sys.exit(main())
