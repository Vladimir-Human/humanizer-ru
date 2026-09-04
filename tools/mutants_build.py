#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mutants_build.py — П2: детерминированный архив мутантов для предрега v2 F3.

Множества: H = первые 500 human-текстов CoAT binary validation (FPR-кривая);
M1 = первые 150 machine-текстов CoAT binary validation (поколение 2021-22);
M2 = первые 150 machine-текстов eval/runs (поколения 2024-26, сортировка по
пути); E = 38 текстов с внедрёнными маркерами (verbatim_sample из реестра в
фикс-шаблоне) для retention-метрики.
Операторы класса (b) детерминированные с числовой параметризацией глубины;
класс (a) регенерация берётся из готовых пар eval/runs blind-rewrite (0
вызовов); класс (c) self-attack исполняется в прогоне (--remove и
SKILL-rewrite). Архив: mutants.jsonl + tar.gz с фиксированными mtime.
"""
import hashlib
import io
import json
import os
import random
import re
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "scripts"))
import check_markers as cm  # noqa: E402

OUT = Path(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))) / \
    "measurement" / "f3v2-mutants"

SYN = [("большой", "крупный"), ("быстро", "скоро"), ("дом", "жилище"),
       ("говорит", "сказал"), ("очень", "весьма"), ("работа", "труд"),
       ("смотреть", "глядеть"), ("идти", "шагать"), ("хороший", "добрый"),
       ("плохой", "скверный"), ("night", "вечер"), ("город", "град"),
       ("река", "поток"), ("лес", "бор"), ("поле", "нива"),
       ("друг", "товарищ"), ("враг", "недруг"), ("путь", "дорога"),
       ("слово", "речь"), ("время", "пора")]
HOMO = {"a": "а", "e": "е", "o": "о", "c": "с", "x": "х", "y": "у"}
TRANS = {"c": "к", "o": "о", "n": "н", "t": "т", "e": "е", "r": "р",
         "f": "ф", "u": "и", "s": "с", "a": "а", "g": "г", "l": "л"}


def op_typo(text, rate, rng):
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch.isalpha() and rng.random() < rate:
            kind = rng.random()
            if kind < 0.4:
                chars[i] = rng.choice("абвгдежзиклмнопрстуфхцчшщэюя")
            elif kind < 0.7 and i + 1 < len(chars):
                chars[i], chars[i + 1] = chars[i + 1], chars[i]
            else:
                chars[i] = ""
    return "".join(chars)


def op_syn(text, count, rng):
    for a, b in rng.sample(SYN, min(count, len(SYN))):
        text = text.replace(a, b, 1)
    return text


def op_ws(text, rounds, rng):
    for _ in range(rounds):
        text = re.sub(r" {2,}", " ", text) if rng.random() < 0.5 \
            else text.replace(" ", "  ", 3)
        text = text.replace("\n\n", "\n") if rng.random() < 0.5 else text
    return text


def op_markup(text, rounds, rng):
    for _ in range(rounds):
        pick = rng.random()
        if pick < 0.34:
            text = "**" + text[:20] + "**" + text[20:]
        elif pick < 0.67:
            text = "## " + text
        else:
            text = text.replace(".", " .", 2)
    return text


def op_homoglyph(text, rounds, rng):
    for _ in range(rounds):
        text = "".join(HOMO.get(c, c) if rng.random() < 0.3 else c for c in text)
    return text


def op_translit(text, rounds, rng):
    for _ in range(rounds):
        text = "".join(TRANS.get(c, c) for c in text)
    return text


def op_zw(text, rounds, rng):
    for _ in range(rounds):
        i = rng.randrange(max(1, len(text)))
        text = text[:i] + "​" + text[i:]
    return text


def op_punct(text, rounds, rng):
    for _ in range(rounds):
        text = text.replace(":", "：").replace("(", "（")
    return text


def op_html(text, rounds, rng):
    for _ in range(rounds):
        text = text.replace("&", "&amp;").replace("<", "&lt;")
    return text


def op_linebreak(text, rounds, rng):
    for _ in range(rounds):
        i = rng.randrange(max(1, len(text)))
        text = text[:i] + "\n" + text[i:]
    return text


OPS = {
    "typo": (op_typo, [0.01, 0.03, 0.05]),
    "synonym-swap": (op_syn, [2, 5, 10]),
    "whitespace": (op_ws, [1, 2, 3]),
    "markup": (op_markup, [1, 2, 3]),
    "homoglyph": (op_homoglyph, [1, 2, 3]),
    "translit": (op_translit, [1, 2, 3]),
    "zero-width": (op_zw, [1, 2, 3]),
    "punctuation": (op_punct, [1, 2, 3]),
    "html-escape": (op_html, [1, 2, 3]),
    "linebreak": (op_linebreak, [1, 2, 3]),
}


def _seed(*key):
    import hashlib
    return int(hashlib.md5(repr(key).encode("utf-8")).hexdigest(), 16) % (2 ** 31)


def coat_split(label):
    import pyarrow.parquet as pq
    tmp = os.path.join(tempfile.gettempdir(), "coat-binary-validation.parquet")
    table = pq.read_table(tmp, columns=["text", "label"])
    return [r["text"] for r in table.to_pylist() if r["label"] == label]


def eval_runs_machine():
    out = []
    base = ROOT / "eval" / "runs"
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*.txt")):
        if "packet" in p.parts:
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(t) > 40:
            out.append(t)
        if len(out) >= 150:
            break
    return out


def embedded():
    src = json.loads((ROOT / "research" / "fixtures" / "marker-sources.json")
                     .read_text(encoding="utf-8"))
    out = []
    for rec in src:
        sample = rec.get("verbatim_sample")
        if sample:
            out.append(("embed-" + str(rec.get("case")),
                        "Живой текст носителя без артефактов. " + sample +
                        " Продолжение обычного предложения.\n"))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    H = coat_split(0)[:500]
    M1 = coat_split(1)[:150]
    M2 = eval_runs_machine()[:150]
    E = embedded()
    rows = []
    for setname, texts in (("H", H), ("M1", M1), ("M2", M2)):
        for i, text in enumerate(texts):
            rows.append({"set": setname, "idx": i, "op": "none",
                         "param": None, "depth": 0, "text": text})
            for opname, (fn, params) in OPS.items():
                for depth, param in enumerate(params, start=1):
                    rng = random.Random(_seed(setname, i, opname, depth))
                    rows.append({"set": setname, "idx": i, "op": opname,
                                 "param": param, "depth": depth,
                                 "text": fn(text, param, rng)})
    for name, text in E:
        rows.append({"set": "E", "idx": name, "op": "none", "param": None,
                     "depth": 0, "text": text})
        for opname, (fn, params) in OPS.items():
            for depth, param in enumerate(params, start=1):
                rng = random.Random(_seed("E", name, opname, depth))
                rows.append({"set": "E", "idx": name, "op": opname,
                             "param": param, "depth": depth,
                             "text": fn(text, param, rng)})
    jsonl = OUT / "mutants.jsonl"
    with open(jsonl, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tar = OUT / "mutants.tar.gz"
    with tarfile.open(tar, "w:gz", format=tarfile.GNU_FORMAT) as tf:
        info = tarfile.TarInfo("mutants.jsonl")
        data = jsonl.read_bytes()
        info.size = len(data)
        info.mtime = 1756944000
        tf.addfile(info, io.BytesIO(data))
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    (OUT / "archive-sha256.txt").write_text(sha + "\n", encoding="utf-8")
    print("строк мутантов:", len(rows), "| H", len(H), "M1", len(M1),
          "M2", len(M2), "E", len(E))
    print("archive sha256:", sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
