#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_folder.py — батч-скан папки с текстами: отчёт MD или CSV.

Преподавательский и редакторский сценарий: проверить стопку файлов одной
командой и получить таблицу находок. Только стандартная библиотека.

    python3 scripts/scan_folder.py КАТАЛОГ [--format md|csv] [--out файл]

Каждый файл .md/.txt сканируется двумя слоями: regex-маркеры вставки
(scripts/check_markers.py) и мягкие сигналы (scripts/scan_soft_signals.py).
Отчёт начинается строкой: находки — не вердикт об авторстве.

Состояния проверки (аудит N44, 2026-09-06): файл получает статус по слоям:
ok — слой отработал; error — дочерний процесс отказал (код входа вне 0/1),
истёк по таймауту или вернул нечитаемый/некорректный вывод. Строка отчёта
несёт статус и текст ошибки проверки; ошибочные показатели НЕ подаются как
достоверный ноль: при статусе error счётчики слоя в таблице не печатаются
(прочерк). Коды выхода: 0 — все файлы проверены; 1 — хотя бы один файл не
проверен полностью (отчёт всё равно построен и помечен); 2 — отказ входа
(каталог не найден). Таймаут дочернего процесса — 120 с (слой успевает на
любых разумных текстах; зависший ребёнок не висит вечно).
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILD_TIMEOUT_S = 120
DISCLAIMER = ("Находки — следы вставки и статистические приметы, а не вердикт "
              "об авторстве. Каждый флаг требует человеческого решения.")


def iter_texts(folder):
    for base, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if f.endswith((".md", ".txt")):
                yield os.path.join(base, f)


def _run(argv, timeout=CHILD_TIMEOUT_S):
    """Обёртка subprocess с таймаутом; возвращает (proc, error)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=ROOT,
                              timeout=timeout)
        return proc, None
    except subprocess.TimeoutExpired:
        return None, "таймаут дочернего процесса (%d с)" % timeout
    except OSError as exc:
        return None, "дочерний процесс не запустился: %s" % exc


def scan_markers(path, argv=None, timeout=CHILD_TIMEOUT_S):
    """(hits, status, error): status ok|error; error — причина отказа."""
    argv = argv or [sys.executable, "-X", "utf8",
                    os.path.join(ROOT, "scripts", "check_markers.py"),
                    "--scan", path]
    proc, err = _run(argv, timeout)
    if err:
        return [], "error", err
    if proc.returncode not in (0, 1):
        return [], "error", "код дочернего процесса %d" % proc.returncode
    hits = []
    for ln in proc.stdout.splitlines():
        if " [" in ln and "]" in ln:
            hits.append(ln.strip())
    return hits, "ok", None


def scan_soft(path, argv=None, timeout=CHILD_TIMEOUT_S):
    """(count, status, error): некорректный вывод ребёнка — ошибка, не ноль."""
    argv = argv or [sys.executable, "-X", "utf8",
                    os.path.join(ROOT, "scripts", "scan_soft_signals.py"),
                    path, "--json"]
    proc, err = _run(argv, timeout)
    if err:
        return None, "error", err
    if proc.returncode not in (0, 1):
        return None, "error", "код дочернего процесса %d" % proc.returncode
    try:
        doc = json.loads(proc.stdout)
        if not isinstance(doc, dict):
            raise ValueError("конверт не объект")
        files = doc.get("files") or []
        if not isinstance(files, list):
            raise ValueError("files не список")
        return int(files[0].get("features_total", 0)), "ok", None
    except (ValueError, AttributeError, TypeError):
        return None, "error", "вывод дочернего процесса некорректен"


def collect_rows(folder, markers_fn=scan_markers, soft_fn=scan_soft):
    rows = []
    for path in iter_texts(folder):
        hits, mst, merr = markers_fn(path)
        soft, sst, serr = soft_fn(path)
        errors = [e for e in (merr, serr) if e]
        if not errors:
            status = "ok"
        elif mst == "ok" or sst == "ok":
            status = "partial"
        else:
            status = "error"
        rows.append({
            "file": os.path.relpath(path, folder),
            "markers": len(hits) if mst == "ok" else None,
            "marker_lines": "; ".join(hits[:5]) if mst == "ok" else "",
            "soft_signals": soft if sst == "ok" else None,
            "status": status,
            "check_errors": "; ".join(errors),
        })
    return rows


def _md_cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")


def render(rows, fmt):
    buf = io.StringIO()
    checked = sum(1 for r in rows if r["status"] == "ok")
    bad = sum(1 for r in rows if r["status"] != "ok")
    if fmt == "csv":
        w = csv.writer(buf)
        w.writerow(["# " + DISCLAIMER])
        w.writerow(["# проверено: %d, с ошибками проверки: %d"
                    % (checked, bad)])
        w.writerow(["file", "markers", "soft_signals", "status",
                    "check_errors", "marker_lines"])
        for r in rows:
            w.writerow([r["file"],
                        "" if r["markers"] is None else r["markers"],
                        "" if r["soft_signals"] is None else r["soft_signals"],
                        r["status"], r["check_errors"], r["marker_lines"]])
    else:
        buf.write("# Отчёт батч-скана\n\n")
        buf.write("> " + DISCLAIMER + "\n\n")
        buf.write("> Проверено полностью: %d; с ошибками проверки: %d. "
                  "Прочерк в счётчиках — файл НЕ проверен слоем.\n\n"
                  % (checked, bad))
        buf.write("| Файл | Маркеры вставки | Мягкие сигналы | Статус | "
                  "Ошибка проверки | Примеры |\n")
        buf.write("|---|---|---|---|---|---|\n")
        for r in rows:
            buf.write("| %s | %s | %s | %s | %s | %s |\n"
                      % (_md_cell(r["file"]),
                         "—" if r["markers"] is None else r["markers"],
                         "—" if r["soft_signals"] is None else r["soft_signals"],
                         r["status"], _md_cell(r["check_errors"]) or "—",
                         _md_cell(r["marker_lines"])[:120]))
    return buf.getvalue()


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        good = os.path.join(td, "good.txt")
        with open(good, "w", encoding="utf-8") as fh:
            fh.write("обычный текст без артефактов\n")
        missing = [sys.executable, "-X", "utf8",
                   os.path.join(td, "no-such-child.py"), good]
        hits, st, err = scan_markers(good, argv=missing)
        case("отсутствующий дочерний скрипт -> error", st == "error" and err)
        rc2 = [sys.executable, "-c", "import sys; sys.exit(2)"]
        hits, st, err = scan_markers(good, argv=rc2)
        case("код входа 2 -> error", st == "error" and "код" in err)
        crash = [sys.executable, "-c", "import sys; sys.exit(3)"]
        cnt, st, err = scan_soft(good, argv=crash)
        case("аварийный код входа -> error", st == "error" and cnt is None)
        badjson = [sys.executable, "-c", "print('not json')"]
        cnt, st, err = scan_soft(good, argv=badjson)
        case("невалидный JSON -> error, не ноль",
             st == "error" and cnt is None)
        slow = [sys.executable, "-c", "import time; time.sleep(6)"]
        cnt, st, err = scan_soft(good, argv=slow, timeout=1)
        case("таймаут дочернего процесса -> error",
             st == "error" and "таймаут" in err)

        def ok_markers(path, argv=None, timeout=CHILD_TIMEOUT_S):
            return ["1 [utm_openai] пример"], "ok", None

        def ok_soft(path, argv=None, timeout=CHILD_TIMEOUT_S):
            return 2, "ok", None

        def bad_soft(path, argv=None, timeout=CHILD_TIMEOUT_S):
            return None, "error", "сбой слоя мягких сигналов"

        rows = collect_rows(td, markers_fn=ok_markers, soft_fn=ok_soft)
        case("полностью проверенная папка -> статус ok",
             rows and rows[0]["status"] == "ok")
        rows = collect_rows(td, markers_fn=ok_markers, soft_fn=bad_soft)
        case("частично проверенный файл -> partial, счётчик слоя прочерк",
             rows[0]["status"] == "partial" and rows[0]["soft_signals"] is None
             and rows[0]["check_errors"])
        md = render(rows, "md")
        case("отчёт частично проверенной папки помечен, а не «успех»",
             "с ошибками проверки: 1" in md and "|" in md)
        csvout = render(rows, "csv")
        case("csv несёт статус и ошибку проверки",
             "partial" in csvout and "сбой слоя мягких сигналов" in csvout)
        case("имя с вертикальной чертой экранируется в md",
             "\\|" in render([{"file": "a|b.txt", "markers": 1,
                               "soft_signals": 1, "status": "ok",
                               "check_errors": "", "marker_lines": "x|y"}],
                             "md"))
    print("САМОПРОВЕРКА scan_folder: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main():
    ap = argparse.ArgumentParser(
        description="Батч-скан папки: следы вставки и мягкие сигналы.")
    ap.add_argument("folder", nargs="?", default=None)
    ap.add_argument("--format", choices=("md", "csv"), default="md")
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка с отрицательными случаями")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.folder:
        print("Каталог не указан")
        return 2
    if not os.path.isdir(args.folder):
        print("Каталог не найден: %s" % args.folder)
        return 2
    rows = collect_rows(args.folder)
    out = render(rows, args.format)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
        print("Отчёт записан: %s (файлов: %d, с ошибками проверки: %d)"
              % (args.out, len(rows),
                 sum(1 for r in rows if r["status"] != "ok")))
    else:
        print(out)
    return 1 if any(r["status"] != "ok" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
