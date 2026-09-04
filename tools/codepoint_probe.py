#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codepoint_probe.py — F7': автопроба невидимых и служебных кодпоинтов в
корпусе текста (кандидаты в новые маркеры отпечатков моделей).

Классы (stdlib, без зависимостей):
  zero_width        200B 200C 200D 2060 FEFF
  bidi_controls     202A-202E 2066-2069
  pua               E000-F8FF
  tags              E0000-E007F
  variation_select  FE00-FE0F E0100-E01EF
  invisible_layout  00AD 2061-2064
  control           00-08 0B 0C 0E-1F

Запуск:
  python3 tools/codepoint_probe.py файл_или_каталог [...] [--json]
  python3 tools/codepoint_probe.py --selftest
"""
import argparse
import json
import os
import sys

CLASSES = {
    "zero_width": set("\u200b\u200c\u200d\u2060\ufeff"),
    "bidi_controls": (set(chr(c) for c in range(0x202A, 0x202F))
                      | set(chr(c) for c in range(0x2066, 0x206A))),
    "pua": set(chr(c) for c in range(0xE000, 0xF8FF)),
    "tags": set(chr(c) for c in range(0xE0000, 0xE0080)),
    "variation_select": (set(chr(c) for c in range(0xFE00, 0xFE10))
                         | set(chr(c) for c in range(0xE0100, 0xE01F0))),
    "invisible_layout": (set("\u00ad")
                         | set(chr(c) for c in range(0x2061, 0x2065))),
    "control": (set(chr(c) for c in range(0x00, 0x09))
                | {"\u000b", "\u000c"}
                | set(chr(c) for c in range(0x0E, 0x20))),
}


def classify(ch):
    for name, table in CLASSES.items():
        if ch in table:
            return name
    return None


def probe_text(text):
    counts = {name: 0 for name in CLASSES}
    for ch in text:
        name = classify(ch)
        if name:
            counts[name] += 1
    return {k: v for k, v in counts.items() if v}


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for base, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
                for f in sorted(files):
                    if f.endswith((".md", ".txt", ".json", ".jsonl")):
                        yield os.path.join(base, f)
        elif os.path.isfile(p):
            yield p


def probe_paths(paths):
    per_file = []
    totals = {name: 0 for name in CLASSES}
    n = 0
    for path in iter_files(paths):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        n += 1
        counts = probe_text(text)
        for k, v in counts.items():
            totals[k] += v
        if counts:
            per_file.append({"file": path, "counts": counts})
    per_file.sort(key=lambda r: -sum(r["counts"].values()))
    return {"scanned_files": n,
            "totals": {k: v for k, v in totals.items() if v},
            "top_files": per_file[:20]}


def selftest():
    fails = 0

    def case(name, ok, detail=""):
        nonlocal fails
        print(("PASS: " if ok else "FAIL: ") + name
              + ((" | " + detail) if not ok and detail else ""))
        fails += 0 if ok else 1

    dirty = ("обычный текст\u200b с невидимым, \ue001 pua, \U000e0041 tag, "
             "\u202e bidi, \ufe0f vs, \u00ad soft, \u0007 bell")
    counts = probe_text(dirty)
    case("все классы найдены в синтетике",
         set(counts) == {"zero_width", "pua", "tags", "bidi_controls",
                         "variation_select", "invisible_layout", "control"},
         str(sorted(counts)))
    clean = probe_text("Чистый русский текст без служебных символов. 12.5")
    case("чистый текст даёт ноль находок (негатив)", clean == {}, str(clean))
    fixtures = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tests", "fixtures")
    rep = probe_paths([fixtures])
    case("probe_paths возвращает отчёт", "scanned_files" in rep
         and rep["scanned_files"] > 0)
    print("САМОПРОВЕРКА codepoint-probe: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.paths:
        ap.error("нужны файлы или каталоги")
    rep = probe_paths(args.paths)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("Файлов: %d" % rep["scanned_files"])
        for name, count in sorted(rep["totals"].items()):
            print("  %s: %d" % (name, count))
        for row in rep["top_files"][:10]:
            print("  %s: %s" % (row["file"], row["counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
