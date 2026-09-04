#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adversarial_measure.py — F3: один проход recall-матрицы по замороженному
предрегу f3-adversarial-prereg-2026-09.md (sha256
7C1EF06C628E5E128697B95217ED134BAE4571A3E2F1F01D79235DEA74D2EEC8).

recall(оператор, глубина) по 40 маркерам + таблица «что снимает --remove».
Сид 20260904. Результат: measurement/adversarial-2026-09/result.json.
"""
import json
import os
import random
from pathlib import Path
import re
import sys

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_markers as cm  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts", "filemarks"))
import text_layer as tl  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(ROOT))),
                   "measurement", "adversarial-2026-09")

HOMO = {"a": "а", "e": "е", "o": "о", "c": "с", "x": "х", "y": "у",
        "h": "һ", "A": "А", "E": "Е", "O": "О", "C": "С", "X": "Х",
        "Y": "У", "H": "Н"}
ZW = ["​", "‌"]
PUNCT = {":": "：", "(": "（", ")": "）", "[": "［", "]": "］",
         "{": "｛", "}": "｝"}
TRANS = {"c": "к", "o": "о", "n": "н", "t": "т", "e": "е", "r": "р",
         "f": "ф", "u": "и", "s": "с", "a": "а", "g": "г", "l": "л",
         "m": "м", "p": "п", "d": "д", "h": "х", "b": "б", "y": "у",
         "w": "в", "v": "в", "i": "и", "k": "к", "q": "к", "z": "з",
         "x": "кс"}
OCR = {"о": "о", "е": "е", "с": "с", "а": "а", "т": "т", "m": "m",
       "l": "l", "i": "i"}  # таблица-заглушка: замены ниже детерминированы сидом


def op_homoglyph(s, rng):
    return "".join(HOMO.get(ch, ch) if rng.random() < 0.5 else ch for ch in s)


def op_zerowidth(s, rng):
    out = []
    for ch in s:
        out.append(ch)
        if ch.isalnum() and rng.random() < 0.3:
            out.append(rng.choice(ZW))
    return "".join(out)


def op_punct(s, rng):
    return "".join(PUNCT.get(ch, ch) for ch in s)


def op_linebreak(s, rng):
    if len(s) < 6:
        return s
    i = len(s) // 2
    return s[:i] + "\n" + s[i:]


def op_nfc_nfkc(s, rng):
    import unicodedata
    return unicodedata.normalize("NFKC" if rng.random() < 0.5 else "NFC", s)


def op_translit(s, rng):
    return "".join(TRANS.get(ch, ch) for ch in s)


def op_word_smart(s, rng):
    s = s.replace("(c)", "©")
    return s.replace('"', "“")


def op_html(s, rng):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def op_telegram_pdf(s, rng):
    s = s.replace("  ", " ")
    chars = list(s)
    for i, ch in enumerate(chars):
        if ch in OCR and rng.random() < 0.1:
            chars[i] = rng.choice(["о", "e", "c", "a", "т"])
    return "".join(chars)


OPS = {
    "homoglyph": op_homoglyph,
    "zero-width": op_zerowidth,
    "punctuation": op_punct,
    "linebreak": op_linebreak,
    "nfc-nfkc": op_nfc_nfkc,
    "translit": op_translit,
    "word-smart": op_word_smart,
    "html-convert": op_html,
    "telegram-pdf": op_telegram_pdf,
}


def detected(sample, name):
    rx = re.compile(cm.CASES[name][0])
    for line in sample.splitlines():
        if cm._line_matches(line, {name: rx}):
            return True
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    src = json.loads((ROOT / "research" / "fixtures" / "marker-sources.json")
                     .read_text(encoding="utf-8"))
    samples = {}
    for rec in src:
        name = rec.get("case") or rec.get("name")
        if not name:
            continue
        sample = rec.get("verbatim_sample")
        if not sample:
            ff = rec.get("fixture_file")
            if ff:
                fp = (ROOT / "research" / "fixtures" / ff).resolve()
                if fp.is_file():
                    sample = fp.read_text(encoding="utf-8", errors="replace")
        if sample:
            samples[name] = sample
    names = sorted(samples)
    res = {"prereg_sha256": "7C1EF06C628E5E128697B95217ED134BAE4571A3E2F1F01D79235DEA74D2EEC8",
           "n_markers": len(names), "matrix": {}, "remove_table": {}}
    for opname, fn in OPS.items():
        row = {}
        rem = []
        for depth in (1, 2, 3):
            hit = 0
            for name in names:
                rng = random.Random(20260904 + hash((opname, depth, name)) % 1000)
                s = samples[name]
                for _ in range(depth):
                    s = fn(s, rng)
                if detected(s, name):
                    hit += 1
                if depth == 1:
                    try:
                        changed = tl.remove_invisible(s) != s
                    except TypeError:
                        changed = False
                    rem.append(changed)
            row["d%d" % depth] = round(hit / len(names), 4)
        res["matrix"][opname] = row
        res["remove_table"][opname] = round(sum(rem) / len(rem), 4) if rem else None
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
