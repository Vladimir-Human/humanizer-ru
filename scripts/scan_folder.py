#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_folder.py — батч-скан папки с текстами: отчёт MD или CSV.

Преподавательский и редакторский сценарий: проверить стопку файлов одной
командой и получить таблицу находок. Только стандартная библиотека.

    python3 scripts/scan_folder.py КАТАЛОГ [--format md|csv] [--out файл]

Каждый файл .md/.txtсканируется двумя слоями: regex-маркеры вставки
(scripts/check_markers.py) и мягкие сигналы (scripts/scan_soft_signals.py).
Отчёт начинается строкой: находки — не вердикт об авторстве.
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCLAIMER = ("Находки — следы вставки и статистические приметы, а не вердикт "
              "об авторстве. Каждый флаг требует человеческого решения.")


def iter_texts(folder):
    for base, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if f.endswith((".md", ".txt")):
                yield os.path.join(base, f)


def scan_markers(path):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "scripts", "check_markers.py"), "--scan", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT)
    hits = []
    for ln in proc.stdout.splitlines():
        if " [" in ln and "]" in ln:
            hits.append(ln.strip())
    return hits


def scan_soft(path):
    proc = subprocess.run(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "scripts", "scan_soft_signals.py"), path, "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT)
    try:
        doc = json.loads(proc.stdout)
        files = doc.get("files") or []
        if files:
            return int(files[0].get("features_total", 0))
        return 0
    except (ValueError, AttributeError, TypeError):
        return 0


def main():
    ap = argparse.ArgumentParser(
        description="Батч-скан папки: следы вставки и мягкие сигналы.")
    ap.add_argument("folder")
    ap.add_argument("--format", choices=("md", "csv"), default="md")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not os.path.isdir(args.folder):
        print("Каталог не найден: %s" % args.folder)
        return 2
    rows = []
    for path in iter_texts(args.folder):
        hits = scan_markers(path)
        soft = scan_soft(path)
        rows.append({
            "file": os.path.relpath(path, args.folder),
            "markers": len(hits),
            "marker_lines": "; ".join(hits[:5]),
            "soft_signals": soft,
        })
    buf = io.StringIO()
    if args.format == "csv":
        w = csv.writer(buf)
        w.writerow(["# " + DISCLAIMER])
        w.writerow(["file", "markers", "soft_signals", "marker_lines"])
        for r in rows:
            w.writerow([r["file"], r["markers"], r["soft_signals"],
                        r["marker_lines"]])
    else:
        buf.write("# Отчёт батч-скана\n\n")
        buf.write("> " + DISCLAIMER + "\n\n")
        buf.write("| Файл | Маркеры вставки | Мягкие сигналы | Примеры |\n")
        buf.write("|---|---|---|---|\n")
        for r in rows:
            buf.write("| %s | %d | %d | %s |\n"
                      % (r["file"], r["markers"], r["soft_signals"],
                         r["marker_lines"][:120]))
    out = buf.getvalue()
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
        print("Отчёт записан: %s (файлов: %d)" % (args.out, len(rows)))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
