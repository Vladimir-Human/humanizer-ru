#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_q5.py — побайтовый аудит кодпоинт-слоя Q5 (водяной знак Claude).

Предрегистрация: preregistration.md (тот же каталог). Fail-closed.
Только стандартная библиотека.

Замеры:
  audit  — аудит образцов Claude (evidence/samples/*.txt) + фоновый контроль
           (24 серии 1 + 9 пробы Q3 + 26 human + 2 boundary) + скан A.7
           (check_markers --scan) + слой A (text_layer);
  --rewritten FILE — повторный аудит файла перезаписи (после агентной
           перезаписи): невидимые codepoints + сравнение с исходником.

Запуск из корня:
    python3 research/superposition/2026-08-28-q5-claude-mark/measure_q5.py
    python3 research/superposition/2026-08-28-q5-claude-mark/measure_q5.py --rewritten файл
"""
import glob
import json
import os
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "filemarks"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

RUN_DIR = HERE
SAMPLES_DIR = os.path.join(RUN_DIR, "evidence", "samples")
PROBE_DIR = os.path.join(ROOT, "research", "superposition",
                         "2026-08-28-q3-holdout", "evidence", "probe")

# Полный спектр невидимых/форматных codepoints (вне легитимной типографики).
# NBSP U+00A0 и узкий NBSP U+202F — норма русской типографики: учитываются
# отдельно (легитимный слой), наборные пробелы U+2000-U+200A — легитимны
# в оцифрованных классиках: учитываются отдельно.
INVISIBLE_RANGES = [
    ("U+00AD", lambda c: c == 0x00AD),
    ("U+061C", lambda c: c == 0x061C),
    ("U+1680", lambda c: c == 0x1680),
    ("U+180B-180E", lambda c: 0x180B <= c <= 0x180E),
    ("U+200B-200F (ZWNJ..RLM)", lambda c: 0x200B <= c <= 0x200F),
    ("U+202A-202E (bidi)", lambda c: 0x202A <= c <= 0x202E),
    ("U+205F", lambda c: c == 0x205F),
    ("U+2060-2069", lambda c: 0x2060 <= c <= 0x2069),
    ("U+206A-206F", lambda c: 0x206A <= c <= 0x206F),
    ("U+3000", lambda c: c == 0x3000),
    ("U+034F", lambda c: c == 0x034F),
    ("U+FE00-FE0F (VS вне эмодзи-гарда)", lambda c: 0xFE00 <= c <= 0xFE0F),
    ("U+FEFF (BOM/ZWNBSP)", lambda c: c == 0xFEFF),
    ("U+FFF9-FFFB", lambda c: 0xFFF9 <= c <= 0xFFFB),
    ("U+E000-F8FF (PUA)", lambda c: 0xE000 <= c <= 0xF8FF),
    ("U+E0000-E007F (Tags)", lambda c: 0xE0000 <= c <= 0xE007F),
]
# Селекторы VS16 после эмодзи-баз — легальны: применяем тот же гард,
# что и маркер invisible_layout (упрощённо: сосед из набора эмодзи-баз).
EMOJI_AROUND = (0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x1F1E6, 0x1F1FF), \
    (0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x203C, 0x2049), (0x2122, 0x2139), \
    (0x2194, 0x2199), (0x21A9, 0x21AA), (0x231A, 0x231B), (0x2328, 0x2328), \
    (0x23CF, 0x23CF), (0x23E9, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25FE), \
    (0x2934, 0x2935), (0x2B00, 0x2BFF), (0x3030, 0x3030), (0x303D, 0x303D), \
    (0x3297, 0x3299), (0x20E3, 0x20E3)
# легитимный слой (норма типографики, не кандидат в знак):
LEGIT = ("U+00A0 (NBSP)", lambda c: c == 0x00A0), \
        ("U+202F (узкий NBSP)", lambda c: c == 0x202F), \
        ("U+2000-200A (наборные)", lambda c: 0x2000 <= c <= 0x200A)


def in_emoji(text, i):
    """Селектор в позиции i легален, если сосед — эмодзи-база."""
    for rng in EMOJI_AROUND:
        if i > 0 and rng[0] <= ord(text[i - 1]) <= rng[1]:
            return True
        if i + 1 < len(text) and rng[0] <= ord(text[i + 1]) <= rng[1]:
            return True
    return False


def audit_text(text):
    """Возвращает (invisible:[(cp, pos, name)], legit:[(cp, name)])."""
    invisible, legit = [], []
    for i, ch in enumerate(text):
        cp = ord(ch)
        for name, pred in INVISIBLE_RANGES:
            if pred(cp):
                if 0xFE00 <= cp <= 0xFE0F and in_emoji(text, i):
                    break  # легальный селектор эмодзи
                invisible.append((cp, i, name))
                break
        else:
            for name, pred in LEGIT:
                if pred(cp):
                    legit.append((cp, name))
                    break
    return invisible, legit


def audit_files(paths, base):
    rows = {}
    for path in paths:
        with open(path, encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
        invisible, legit = audit_text(text)
        rel = os.path.relpath(path, base).replace("\\", "/")
        rows[rel] = {
            "invisible": [{"cp": "U+%04X" % cp, "pos": pos, "class": name}
                          for cp, pos, name in invisible],
            "invisible_count": len(invisible),
            "legit": dict(Counter(name for _cp, name in legit)),
        }
    return rows


def main():
    rewritten = None
    for i, a in enumerate(sys.argv):
        if a == "--rewritten" and i + 1 < len(sys.argv):
            rewritten = sys.argv[i + 1]
    if rewritten:
        with open(rewritten, encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
        invisible, legit = audit_text(text)
        out = {
            "file": os.path.relpath(rewritten, ROOT).replace("\\", "/"),
            "invisible": [{"cp": "U+%04X" % cp, "pos": pos, "class": name}
                          for cp, pos, name in invisible],
            "invisible_count": len(invisible),
            "legit": dict(Counter(name for _cp, name in legit)),
            "chars": len(text),
        }
        out_path = os.path.join(RUN_DIR, "evidence", "rewritten-audit.json")
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("записан %s" % os.path.relpath(out_path, ROOT))
        print("перезапись: невидимых %d, легитимных %s"
              % (out["invisible_count"], out["legit"]))
        return 0

    samples = sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.txt")))
    if len(samples) != 3:
        print("ОШИБКА ВХОДА: образцов %d (нужно 3)" % len(samples),
              file=sys.stderr)
        return 2
    series1 = sorted(glob.glob(os.path.join(ROOT, "research", "raw",
                                             "**", "*.txt"), recursive=True))
    probe = sorted(glob.glob(os.path.join(PROBE_DIR, "*.txt")))
    human = sorted(glob.glob(os.path.join(ROOT, "research", "validation",
                                          "human", "*.txt")))
    manifest = json.load(open(os.path.join(ROOT, "eval", "manifest.v1.json"),
                              encoding="utf-8"))
    boundary = [os.path.join(ROOT, c["path"]) for c in manifest.get("corpus", [])
                if c.get("kind") == "boundary"]

    result = {
        "samples": audit_files(samples, ROOT),
        "background": {
            "series1": audit_files(series1, ROOT),
            "probe_q3": audit_files(probe, ROOT),
            "human": audit_files(human, ROOT),
            "boundary": audit_files(boundary, ROOT),
        },
    }

    # Фоновая сводка невидимых (какие codepoints встречаются у НЕ-Claude).
    bg_codes = Counter()
    for group in result["background"].values():
        for row in group.values():
            for inv in row["invisible"]:
                bg_codes[inv["cp"]] += 1
    result["background_invisible_summary"] = dict(bg_codes)

    # Сводка образцов: повторяемость.
    sample_codes = Counter()
    for row in result["samples"].values():
        for inv in row["invisible"]:
            sample_codes[inv["cp"]] += 1
    result["sample_invisible_summary"] = dict(sample_codes)

    # Скан A.7 (check_markers --scan) на образцах.
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "check_markers.py"),
         "--scan"] + samples,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    result["marker_scan"] = {
        "exit": proc.returncode,
        "tail": proc.stdout.strip().splitlines()[-3:],
    }

    # Слой A: что детерминированно снимается.
    from text_layer import clean_text_layer, clean_markup  # noqa: E402
    layerA = {}
    for path in samples:
        with open(path, encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
        cleaned, n = clean_text_layer(text)
        cleaned, m = clean_markup(cleaned)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        layerA[rel] = {"layer_a_removed": n, "markup_removed": m,
                       "changed": cleaned != text}
    result["layer_a"] = layerA

    out_path = os.path.join(RUN_DIR, "evidence", "audit.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("записан %s" % os.path.relpath(out_path, ROOT))
    print("образцы Claude — невидимые: %s"
          % json.dumps(result["sample_invisible_summary"], ensure_ascii=False))
    print("фон (33 ИИ + 26 human + 2 boundary) — невидимые: %s"
          % json.dumps(result["background_invisible_summary"],
                       ensure_ascii=False))
    print("скан маркеров: exit=%d, %s"
          % (result["marker_scan"]["exit"],
             " | ".join(result["marker_scan"]["tail"])))
    print("слой A: %s" % json.dumps(layerA, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
