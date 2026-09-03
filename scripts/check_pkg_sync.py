#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт синхронности PyPI-пакета с корневыми скриптами.

Пакет `src/humanizer_ru/` копирует четыре рантайм-скрипта корня:
`scripts/check_markers.py`, `scripts/scan_soft_signals.py`,
`scripts/polish.py` и `scripts/detect_conj.py`. Копии обязаны побайтово
повторять оригиналы: рассинхронизированный пакет — это wheel, который
ведёт себя иначе, чем проверенное дерево репозитория.

Правила:
1. `src/humanizer_ru/check_markers.py` равен `scripts/check_markers.py`.
2. `src/humanizer_ru/scan_soft_signals.py` равен `scripts/scan_soft_signals.py`.
3. `src/humanizer_ru/polish.py` равен `scripts/polish.py`.
4. `src/humanizer_ru/detect_conj.py` равен `scripts/detect_conj.py`.
5. В пакете нет других .py-файлов, кроме `__init__.py`, `cli.py` и четырёх копий.
6. Данные пакета синхронны с корневыми: `src/humanizer_ru/contract.v1.json`
   равен `contract.v1.json`, `src/humanizer_ru/markers.v1.json` равен
   `markers.v1.json` (копии едут в wheel/sdist — `--contract` установленного
   пакета обязан печатать тот же контракт, что и дерево репозитория).

Запуск из корня репозитория:
    python3 scripts/check_pkg_sync.py            # проверка
    python3 scripts/check_pkg_sync.py --selftest # самопроверка

Коды: 0 — пакет синхронен; 1 — есть расхождение; 2 — ошибка запуска.
Только стандартная библиотека.
"""
import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PKG = os.path.join("src", "humanizer_ru")
SYNCED = [
    ("scripts", "check_markers.py"),
    ("scripts", "scan_soft_signals.py"),
    ("scripts", "polish.py"),
    ("scripts", "detect_conj.py"),
]
ALLOWED_PY = {"__init__.py", "cli.py", "check_markers.py",
              "scan_soft_signals.py", "polish.py", "detect_conj.py"}
SYNCED_DATA = ["contract.v1.json", "markers.v1.json"]


def read(path):
    with open(path, "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def package_files(root):
    pkg = os.path.join(root, PKG)
    out = []
    for dirpath, dirnames, filenames in os.walk(pkg):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".py") or name in ("__init__.py",):
                out.append(os.path.relpath(os.path.join(dirpath, name), pkg))
    return out


def check(root):
    errors = []
    pkg = os.path.join(root, PKG)
    if not os.path.isdir(pkg):
        return ["нет каталога пакета %s" % PKG]
    # 3. Только разрешённые .py-файлы.
    files = package_files(root)
    for rel in files:
        if rel not in ALLOWED_PY:
            errors.append("лишний .py-файл пакета: %s" % rel)
    for script_name, file_name in SYNCED:
        src = os.path.join(root, script_name, file_name)
        dst = os.path.join(root, PKG, file_name)
        if file_name not in files:
            errors.append("в пакете нет файла: %s" % file_name)
            continue
        for label, path in (("корень", src), ("пакет", dst)):
            try:
                read(path)
            except OSError as exc:
                errors.append("не читается %s: %r" % (path, exc))
                continue
        try:
            if read(src) != read(dst):
                errors.append("пакет рассинхронизирован: %s" % file_name)
        except OSError:
            pass
    # 6. Данные пакета (contract.v1.json, markers.v1.json) синхронны с корнем.
    for name in SYNCED_DATA:
        src = os.path.join(root, name)
        dst = os.path.join(root, PKG, name)
        if not os.path.isfile(dst):
            errors.append("в пакете нет файла данных: %s" % name)
            continue
        try:
            if read(src) != read(dst):
                errors.append("пакет рассинхронизирован (данные): %s" % name)
        except OSError as exc:
            errors.append("не читается %s: %r" % (name, exc))
    return errors


def selftest():
    cases = []
    with tempfile.TemporaryDirectory(prefix="pkg-sync-selftest-") as td:
        os.makedirs(os.path.join(td, "scripts"))
        os.makedirs(os.path.join(td, PKG))
        root_f = os.path.join(td, "scripts", "check_markers.py")
        pkg_f = os.path.join(td, PKG, "check_markers.py")
        with open(root_f, "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        with open(pkg_f, "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        with open(os.path.join(td, PKG, "__init__.py"), "w") as fh:
            fh.write("")
        with open(os.path.join(td, PKG, "cli.py"), "w") as fh:
            fh.write("")
        with open(os.path.join(td, "scripts", "scan_soft_signals.py"), "w") as fh:
            fh.write("y = 2\n")
        with open(os.path.join(td, PKG, "scan_soft_signals.py"), "w") as fh:
            fh.write("y = 2\n")
        with open(os.path.join(td, "scripts", "polish.py"), "w") as fh:
            fh.write("z = 3\n")
        with open(os.path.join(td, PKG, "polish.py"), "w") as fh:
            fh.write("z = 3\n")
        with open(os.path.join(td, "scripts", "detect_conj.py"), "w") as fh:
            fh.write("w = 4\n")
        with open(os.path.join(td, PKG, "detect_conj.py"), "w") as fh:
            fh.write("w = 4\n")
        for data_name in SYNCED_DATA:
            with open(os.path.join(td, data_name), "w", encoding="utf-8") as fh:
                fh.write('{"data": 1}\n')
            with open(os.path.join(td, PKG, data_name), "w", encoding="utf-8") as fh:
                fh.write('{"data": 1}\n')
        cases.append(("синхронный пакет без ошибок", check(td) == []))

        with open(os.path.join(td, PKG, "contract.v1.json"), "a",
                  encoding="utf-8") as fh:
            fh.write("дрейф\n")
        cases.append(("дрейф данных пакета виден",
                      any("данные" in e and "contract" in e for e in check(td))))
        with open(os.path.join(td, PKG, "contract.v1.json"), "w",
                  encoding="utf-8") as fh:
            fh.write('{"data": 1}\n')

        with open(pkg_f, "a", encoding="utf-8") as fh:
            fh.write("дрейф\n")
        cases.append(("дрейф копии виден",
                      any("check_markers.py" in e for e in check(td))))

        with open(pkg_f, "r", encoding="utf-8") as fh:
            base = fh.read()
        with open(pkg_f, "w", encoding="utf-8") as fh:
            fh.write(base.replace("дрейф\n", ""))
        with open(os.path.join(td, PKG, "extra.py"), "w") as fh:
            fh.write("")
        cases.append(("лишний .py-файл виден",
                      any("лишний" in e for e in check(td))))

    ok = 0
    for name, passed in cases:
        print(("  [OK]   " if passed else "  [FAIL] ") + name)
        ok += 1 if passed else 0
    print("Самопроверка: %d/%d" % (ok, len(cases)))
    return 0 if ok == len(cases) else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    errors = check(ROOT)
    for e in errors:
        print("ПРОВАЛ пакет: %s" % e)
    if errors:
        print("Итог: расхождений пакета %d" % len(errors))
        return 1
    print("OK пакет: копии синхронны, файлов %d" % len(package_files(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
