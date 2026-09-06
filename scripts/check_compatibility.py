#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_compatibility.py — compatibility-тест против предыдущей опубликованной версии.

Правило плана v2: каждый релиз сверяется с предыдущей ОПУБЛИКОВАННОЙ
версией. Аддитивные поля разрешены; изменение кодов возврата, формы
конверта и результатов детекции на одинаковых входах — несовместимость.

Механика:
  1. Предыдущая версия определяется с PyPI: максимальная строго меньше
     версии дерева (src/humanizer_ru/__init__.py).
  2. Она ставится во временное чистое venv (pip; сеть).
  3. Фиксированная матрица входов (русский текст с артефактами, чистый
     русский, английский, пустой, Markdown, нечитаемый файл) прогоняется
     через все четыре команды в двух окружениях: OLD (установленный пакет)
     и NEW (пакет дерева, PYTHONPATH=src).
  4. Сравнение: rc равен; поля, присутствующие в OLD-ответе, равны в NEW;
     NEW может добавлять поля (аддитивность), но не менять и не удалять.

Запуск:
    python3 scripts/check_compatibility.py             # проверка
    python3 scripts/check_compatibility.py --selftest  # негативные кейсы

Коды: 0 — совместимо; 1 — несовместимость; 2 — отказ среды (нет сети,
venv или PyPI). Только стандартная библиотека (pip — из venv).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYPI_JSON = "https://pypi.org/pypi/humanizer-ru/json"
# Явный список нормализуемых нестабильных полей: тексты причин ошибок
# зависят от путей окружения (сравниваются наличие и тип, не текст).
# Пути файлов нормализует проба (к именам файлов). Иного нормализующего
# списка нет: значения и типы всех остальных полей сравниваются как есть.
NORM_TEXT_KEYS = ("error", "env_error")

PROBE = '''# -*- coding: utf-8 -*-
import contextlib, io, json, os, tempfile
from humanizer_ru.cli import scan_main, markers_main, polish_main, detect_main

T = tempfile.mkdtemp(prefix="compat-probe-")

# Явный список нормализуемых нестабильных значений: тексты причин ошибок
# зависят от путей окружения, пути файлов — от временного каталога пробы.
# Ничего остального проба не нормализует: сравниваются все файлы и все
# вложенные поля конвертов, рекурсивно, с различением типов JSON.
NORM_TEXT_KEYS = ("error", "env_error")

def norm(value, key=None):
    if isinstance(value, dict):
        return {k: norm(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [norm(v) for v in value]
    if isinstance(value, str):
        if key in NORM_TEXT_KEYS:
            return "<текст причины нормализован>"
        if key == "file":
            return os.path.basename(value)
        return value
    return value

def w(name, text):
    p = os.path.join(T, name)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return p

ru = w("ru.txt", "\\u0421\\u043e\\u0433\\u043b\\u0430\\u0441\\u043d\\u043e \\u043e\\u0442\\u0447\\u0451\\u0442\\u0443 :contentReference[oaicite:12]{index=12}, \\u0437\\u0430\\u044f\\u0432\\u043e\\u043a \\u0441\\u0442\\u0430\\u043b\\u043e \\u0431\\u043e\\u043b\\u044c\\u0448\\u0435 \\u043d\\u0430 12% \\u2014 \\u0438\\u0441\\u0442\\u043e\\u0447\\u043d\\u0438\\u043a: https://example.com/r?utm_source=chatgpt.com\\n\\u0414\\u0430\\u043d\\u043d\\u044b\\u0435 \\u043f\\u043e\\u0434\\u0442\\u0432\\u0435\\u0440\\u0436\\u0434\\u0435\\u043d\\u044b \\u0430\\u0441\\u0441\\u0438\\u0441\\u0442\\u0435\\u043d\\u0442\\u043e\\u043c\\u200b.\\n")
clean = w("clean.txt", "\\u041e\\u0431\\u044b\\u0447\\u043d\\u044b\\u0439 \\u0440\\u0443\\u0441\\u0441\\u043a\\u0438\\u0439 \\u0442\\u0435\\u043a\\u0441\\u0442 \\u0431\\u0435\\u0437 \\u0434\\u0435\\u0444\\u0435\\u043a\\u0442\\u043e\\u0432. \\u0412\\u0442\\u043e\\u0440\\u043e\\u0439 \\u0430\\u0431\\u0437\\u0430\\u0446.\\n")
en = w("en.txt", "Plain English text without any Russian words.\\n")
empty = w("empty.txt", "")
md = w("md.txt", "# \\u0417\\u0430\\u0433\\u043e\\u043b\\u043e\\u0432\\u043e\\u043a\\n\\n**\\u0416\\u0438\\u0440\\u043d\\u044b\\u0439** \\u0438 \\u00ab\\u0451\\u043b\\u043e\\u0447\\u043a\\u0438\\u00bb \\u2014 \\u0442\\u0438\\u0440\\u0435\\u2026\\n")
missing = os.path.join(T, "no-such-file.txt")

out = []

def run(label, fn, argv):
    buf = io.StringIO()
    ebuf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
        try:
            rc = fn(argv)
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    rec = {"label": label, "rc": rc}
    try:
        payload = json.loads(buf.getvalue())
    except Exception:
        payload = None
    rec["payload"] = norm(payload)
    out.append(rec)

for p in (ru, clean, en, empty, md, missing):
    name = os.path.basename(p)
    run("markers:" + name, markers_main, ["--scan", "--json", p])
    run("scan:" + name, scan_main, ["--json", p])
    run("polish:" + name, polish_main, ["--json", p])
    run("detect:" + name, detect_main, ["--json", p])

print(json.dumps(out, ensure_ascii=False, sort_keys=True))
'''


def tree_version() -> str:
    with open(os.path.join(ROOT, "src", "humanizer_ru", "__init__.py"),
              encoding="utf-8") as fh:
        m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', fh.read())
    if not m:
        raise ValueError("__version__ не найден")
    return m.group(1)


def prev_published(current: str):
    """Максимальная опубликованная версия строго меньше current."""
    req = urllib.request.Request(
        PYPI_JSON, headers={"User-Agent": "humanizer-ru-check-compatibility"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    cur = tuple(int(x) for x in current.split("."))
    best = None
    for rel in doc.get("releases", {}):
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", rel)
        if not m or not doc["releases"][rel]:
            continue
        ver = tuple(int(g) for g in m.groups())
        if ver < cur and (best is None or ver > best):
            best = ver
    return ".".join(str(x) for x in best) if best else None


def _tname(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _compat_problems(old, new, path, key=None) -> list:
    """Рекурсивное сравнение с типами JSON: 1 и True — разные типы,
    удалённое поле OLD — несовместимость, добавленное поле NEW — нет.

    Списки: каждый элемент OLD обязан иметь типизированную пару в NEW
    (добавления допустимы, удаления и подмены элементов — нет).
    """
    if key in NORM_TEXT_KEYS and isinstance(old, str):
        if isinstance(new, str):
            return []
        return ["%s: поле %s: OLD текст причины, NEW тип %s"
                % (path, key, _tname(new))]
    t_old, t_new = _tname(old), _tname(new)
    if t_old != t_new:
        return ["%s: поле %s: тип OLD=%s NEW=%s (в JSON-контракте это "
                "разные типы)" % (path, key or "-", t_old, t_new)]
    if t_old == "dict":
        problems = []
        for k in old:
            if k not in new:
                problems.append("%s: поле %s удалено в новой версии"
                                % (path, k))
            else:
                problems.extend(_compat_problems(old[k], new[k], path, k))
        return problems
    if t_old == "list":
        problems = []
        pool = list(new)
        for i, item in enumerate(old):
            hit = None
            best = None
            for j, cand in enumerate(pool):
                sub = _compat_problems(item, cand, path, key)
                if not sub:
                    hit = j
                    break
                if best is None or len(sub) < len(best[1]):
                    best = (j, sub)
            if hit is None:
                detail = ""
                if best is not None:
                    detail = "; ближайшее расхождение: %s" % best[1][0]
                    pool.pop(best[0])
                problems.append("%s: элемент %d списка %s отсутствует "
                                "или изменён в новой версии%s"
                                % (path, i, key or "-", detail))
            else:
                pool.pop(hit)
        return problems
    if old != new:
        return ["%s: поле %s: OLD=%r NEW=%r" % (path, key or "-", old, new)]
    return []


def compare(old_recs, new_recs) -> list:
    """Несовместимости: записи OLD обязаны совпасть в NEW по типам и
    значениям всех полей (включая вложенные конверты всех файлов);
    NEW может добавлять поля. Возвращает список человекочитаемых
    нарушений. Нормализуются только явно нестабильные значения
    (NORM_TEXT_KEYS в пробе: тексты причин ошибок; пути файлов
    приводятся к именам).
    """
    problems = []
    old_by = {r["label"]: r for r in old_recs}
    new_by = {r["label"]: r for r in new_recs}
    for label, old in sorted(old_by.items()):
        new = new_by.get(label)
        if new is None:
            problems.append("%s: проба исчезла в новой версии" % label)
            continue
        problems.extend(_compat_problems(old, new, label))
    for label in sorted(new_by):
        if label not in old_by:
            problems.append("%s: новая проба без пары (матрица разъехалась)"
                            % label)
    return problems


def _venv_python(venvdir: str) -> str:
    if os.name == "nt":
        return os.path.join(venvdir, "Scripts", "python.exe")
    return os.path.join(venvdir, "bin", "python")


def run_check() -> int:
    try:
        current = tree_version()
    except (OSError, ValueError) as exc:
        print("ОТКАЗ: версия дерева не читается: %r" % exc, file=sys.stderr)
        return 2
    try:
        prev = prev_published(current)
    except (OSError, ValueError, KeyError) as exc:
        print("ОТКАЗ: PyPI недоступен: %r" % exc, file=sys.stderr)
        return 2
    if prev is None:
        print("ОТКАЗ: нет опубликованной версии старше %s" % current,
              file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="compat-venv-")
    probe_path = os.path.join(tmp, "probe.py")
    with open(probe_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PROBE)
    try:
        venv = os.path.join(tmp, "venv")
        proc = subprocess.run([sys.executable, "-m", "venv", venv],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            print("ОТКАЗ: venv не создан: %s" % proc.stderr[-200:],
                  file=sys.stderr)
            return 2
        vpy = _venv_python(venv)
        proc = subprocess.run(
            [vpy, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "humanizer-ru==" + prev],
            capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            print("ОТКАЗ: установка humanizer-ru==%s не удалась (сеть?): %s"
                  % (prev, proc.stderr[-200:]), file=sys.stderr)
            return 2
        proc_old = subprocess.run([vpy, "-X", "utf8", probe_path],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=300)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep \
            + env.get("PYTHONPATH", "")
        proc_new = subprocess.run([sys.executable, "-X", "utf8", probe_path],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=300, env=env, cwd=ROOT)
        for name, proc in (("OLD", proc_old), ("NEW", proc_new)):
            if proc.returncode != 0:
                print("ОТКАЗ: пробный прогон %s упал: %s"
                      % (name, proc.stderr[-300:]), file=sys.stderr)
                return 2
        try:
            old_recs = json.loads(proc_old.stdout.strip().splitlines()[-1])
            new_recs = json.loads(proc_new.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            print("ОТКАЗ: вывод проб не JSON: %r" % exc, file=sys.stderr)
            return 2
        problems = compare(old_recs, new_recs)
        for p in problems:
            print("[FAIL] " + p)
        if problems:
            print("СОВМЕСТИМОСТЬ: %s -> %s — нарушений %d"
                  % (prev, current, len(problems)))
            return 1
        print("СОВМЕСТИМОСТЬ: %s -> %s — %d проб, аддитивность соблюдена "
              "(rc, конверты и детекция совпадают; новые поля разрешены)"
              % (prev, current, len(new_recs)))
        return 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("ОТКАЗ: среда: %r" % exc, file=sys.stderr)
        return 2
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    old = [{"label": "scan:a", "rc": 0, "features_total": 3},
           {"label": "markers:a", "rc": 1, "count": 2,
            "markers": ["utm_chatgpt", "zero_width"]}]
    case("идентичные прогоны совместимы", compare(old, [dict(r) for r in old]) == [])
    new_added = [{"label": "scan:a", "rc": 0, "features_total": 3,
                  "status": "out-of-scope"},
                 {"label": "markers:a", "rc": 1, "count": 2,
                  "markers": ["utm_chatgpt", "zero_width"]}]
    case("новое поле — аддитивно, совместимо", compare(old, new_added) == [])
    rc_changed = [{"label": "scan:a", "rc": 2, "features_total": 3},
                  {"label": "markers:a", "rc": 1, "count": 2,
                   "markers": ["utm_chatgpt", "zero_width"]}]
    case("смена rc ловится (негатив)",
         any("rc" in p for p in compare(old, rc_changed)))
    val_changed = [{"label": "scan:a", "rc": 0, "features_total": 4},
                   {"label": "markers:a", "rc": 1, "count": 2,
                    "markers": ["utm_chatgpt", "zero_width"]}]
    case("изменение значения поля ловится (негатив)",
         any("features_total" in p for p in compare(old, val_changed)))
    dropped = [{"label": "scan:a", "rc": 0, "features_total": 3}]
    case("исчезновение пробы ловится (негатив)",
         any("исчезла" in p for p in compare(old, dropped)))
    err_text = [{"label": "scan:a", "rc": 0, "features_total": 3},
                {"label": "markers:a", "rc": 1, "count": 2,
                 "markers": ["utm_chatgpt", "zero_width"],
                 "error": "путь /tmp/old-xxxx"}]
    err_new = [{"label": "scan:a", "rc": 0, "features_total": 3},
               {"label": "markers:a", "rc": 1, "count": 2,
                "markers": ["utm_chatgpt", "zero_width"],
                "error": "путь /tmp/new-yyyy"}]
    case("текст error зависит от среды и не считается несовместимостью",
         compare(err_text, err_new) == [])
    err_gone = [{"label": "scan:a", "rc": 0, "features_total": 3},
                {"label": "markers:a", "rc": 1, "count": 2,
                 "markers": ["utm_chatgpt", "zero_width"]}]
    case("пропажа поля error ловится (негатив)",
         any("error" in p for p in compare(err_text, err_gone)))
    typed_old = [{"label": "scan:a", "rc": 0,
                  "payload": {"tool": "humanizer-scan", "schema": 1,
                              "files": [{"file": "a.txt", "count": 2,
                                         "invariants": []}]}}]
    typed_bool = [{"label": "scan:a", "rc": 0,
                   "payload": {"tool": "humanizer-scan", "schema": True,
                               "files": [{"file": "a.txt", "count": 2,
                                          "invariants": []}]}}]
    case("schema 1 против True — разные типы JSON (негатив)",
         any("тип" in p for p in compare(typed_old, typed_bool)))
    typed_rc_bool = [{"label": "scan:a", "rc": False,
                      "payload": typed_old[0]["payload"]}]
    case("rc 0 против False — разные типы JSON (негатив)",
         any("тип" in p for p in compare(typed_old, typed_rc_bool)))
    typed_dropped = [{"label": "scan:a", "rc": 0,
                      "payload": {"tool": "humanizer-scan", "schema": 1,
                                  "files": [{"file": "a.txt",
                                             "count": 2}]}}]
    case("удалённое вложенное поле invariants ловится (негатив)",
         any("invariants" in p for p in compare(typed_old, typed_dropped)))
    typed_added = [{"label": "scan:a", "rc": 0,
                    "payload": {"tool": "humanizer-scan", "schema": 1,
                                "files": [{"file": "a.txt", "count": 2,
                                           "invariants": [],
                                           "date_like": True}]}}]
    case("добавленное вложенное поле аддитивно",
         compare(typed_old, typed_added) == [])
    print("САМОПРОВЕРКА check_compatibility: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Совместимость с предыдущей опубликованной версией "
                    "(аддитивность без смены rc и детекции).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
