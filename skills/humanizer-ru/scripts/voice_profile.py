#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Describe how an author writes from a sample of their text, and tell how far another
#          text is from that manner, so an edit "in my voice" can be checked instead of guessed.
#          Character 3-grams carry most of the signal (they hold word endings, function words and
#          punctuation habits); readable features say what to change.
# SCOPE: deterministic, stdlib only; reads the files given; `build` prints a profile (JSON),
#        `distance` compares texts with a profile or with a sample file.
# DEPENDS: Python 3.8+ standard library.
# LINKS: M-VOICE-PROFILE; R-VOICE; V-M-VOICE-PROFILE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# features: text -> readable features (sentence length, punctuation and ё rates, first person,
#           function words) and the relative frequencies of character 3-grams.
# build: sample text -> profile dict (features, 3-grams, size warning under 300 words).
# distance: profile + text -> cosine distance of 3-grams (0 same manner, 1 nothing shared) and
#           the readable differences that matter most.
# main: CLI `voice_profile.py build sample.txt` and `voice_profile.py distance sample.txt|profile.json text.txt ...`.
# END_MODULE_MAP
"""Профиль манеры автора по образцу и расстояние до него.

    python voice_profile.py build образец.txt > профиль.json
    python voice_profile.py distance образец.txt черновик.txt правка.txt
    python voice_profile.py distance профиль.json правка.txt --json

Расстояние — косинусное по символьным триграммам: 0 — та же манера, 1 — ничего общего.
Образец нужен от 300 слов, лучше 500 и больше. Код выхода: 0 — готово, 2 — файл не читается.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

WORD_RX = re.compile("[0-9A-Za-zА-Яа-яЁё]+(?:-[0-9A-Za-zА-Яа-яЁё]+)*")
SENT_SPLIT_RX = re.compile("[.!?…]+(?=\\s|$)|\\n\\s*\\n")
PUNCT = {"dash": "—–", "colon": ":", "semicolon": ";", "ellipsis": "…", "exclamation": "!",
         "question": "?", "parenthesis": "(", "comma": ",", "quote": "«\"„“"}
PUNCT_NAMES = {"dash": "тире", "colon": "двоеточия", "semicolon": "точки с запятой", "ellipsis": "многоточия",
               "exclamation": "восклицательные знаки", "question": "вопросы", "parenthesis": "скобки",
               "comma": "запятые", "quote": "кавычки"}
FUNCTION_WORDS = ("и а но да или же ли бы не ни что чтобы как так вот это то там тут здесь уже ещё еще "
                  "только даже вообще ведь вроде будто потом тогда если когда пока раз хоть хотя "
                  "в на с к по о об от до из за для при без под над про через у я мы ты вы он она они "
                  "мой наш свой его её их все всё весь очень просто").split()
MIN_WORDS = 300


def _ngrams(text: str) -> Counter:
    t = re.sub("\\s+", " ", text.lower())
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


# START_CONTRACT: features
# PURPOSE: Readable features and 3-gram frequencies of one text.
# INPUTS: text.
# OUTPUTS: {"words", "sentence_mean", "sentence_sd", "short_share", "punct": {name: per 1000 chars},
#           "yo_share", "first_person", "function": {word: per 1000 words}, "trigrams": {gram: share}}.
# RULES: sentences end at . ! ? … or a blank line; short = up to 6 words; yo_share = ё / (е + ё);
#        first_person = я/мы forms per 1000 words.
# END_CONTRACT: features
def features(text: str) -> dict:
    words = [w.lower() for w in WORD_RX.findall(text)]
    n_words = max(1, len(words))
    chars = max(1, len(text))
    sents = [len(WORD_RX.findall(s)) for s in SENT_SPLIT_RX.split(text)]
    sents = [n for n in sents if n] or [0]
    mean = sum(sents) / len(sents)
    sd = math.sqrt(sum((n - mean) ** 2 for n in sents) / len(sents))
    lower = text.lower()
    e, yo = lower.count("е"), lower.count("ё")
    wc = Counter(words)
    first = sum(wc[w] for w in ("я", "меня", "мне", "мной", "мы", "нас", "нам", "нами", "мой", "моя", "моё", "мое", "мои", "наш", "наша", "наше", "наши"))
    grams = _ngrams(text)
    total = max(1, sum(grams.values()))
    return {
        "words": len(words),
        "sentence_mean": round(mean, 2),
        "sentence_sd": round(sd, 2),
        "short_share": round(sum(1 for n in sents if n <= 6) / len(sents), 3),
        "punct": {k: round(1000.0 * sum(text.count(c) for c in v) / chars, 2) for k, v in PUNCT.items()},
        "yo_share": round(yo / (e + yo), 3) if e + yo else 0.0,
        "first_person": round(1000.0 * first / n_words, 2),
        "function": {w: round(1000.0 * wc[w] / n_words, 2) for w in FUNCTION_WORDS if wc[w]},
        "trigrams": {g: c / total for g, c in grams.items()},
    }


def build(text: str) -> dict:
    prof = features(text)
    prof["warning"] = ("Образец короткий (%d слов): профиль неустойчив, нужно хотя бы %d." % (prof["words"], MIN_WORDS)
                       if prof["words"] < MIN_WORDS else "")
    return prof


def _cosine_distance(a: dict, b: dict) -> float:
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return round(1.0 - dot / (na * nb), 4) if na and nb else 1.0


# START_CONTRACT: distance
# PURPOSE: How far a text is from the author's manner, and what differs most.
# INPUTS: profile (from build), text.
# OUTPUTS: {"distance": cosine distance of 3-grams, "differences": [Russian lines, largest first]}.
# RULES: a feature is reported when it differs by half or more of the profile value (and by an
#        absolute floor that ignores noise of short texts); at most 5 lines.
# END_CONTRACT: distance
def distance(profile: dict, text: str) -> dict:
    f = features(text)
    diffs = []

    def note(weight, line):
        diffs.append((weight, line))

    pm, tm = profile["sentence_mean"], f["sentence_mean"]
    if pm and abs(tm - pm) >= max(3.0, 0.3 * pm):
        note(abs(tm - pm) / pm, "фразы %s: в среднем %.0f слов, у автора %.0f" % ("длиннее" if tm > pm else "короче", tm, pm))
    for k, pv in profile["punct"].items():
        tv = f["punct"][k]
        if abs(tv - pv) >= max(1.0, 0.5 * pv):
            note(abs(tv - pv) / max(pv, 1.0), "%s: %.1f на 1000 знаков, у автора %.1f" % (PUNCT_NAMES[k], tv, pv))
    if abs(f["yo_share"] - profile["yo_share"]) >= 0.3:
        note(1.0, "буква «ё»: %.0f%% случаев, у автора %.0f%%" % (100 * f["yo_share"], 100 * profile["yo_share"]))
    if abs(f["first_person"] - profile["first_person"]) >= max(8.0, 0.5 * profile["first_person"]):
        note(abs(f["first_person"] - profile["first_person"]) / max(profile["first_person"], 8.0),
             "«я/мы»: %.0f на 1000 слов, у автора %.0f" % (f["first_person"], profile["first_person"]))
    diffs.sort(key=lambda d: -d[0])
    return {"distance": _cosine_distance(profile["trigrams"], f["trigrams"]), "words": f["words"],
            "differences": [line for _, line in diffs[:5]]}


def _read(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Профиль манеры автора и расстояние до него")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("sample")
    d = sub.add_parser("distance")
    d.add_argument("profile", help="профиль .json или сам образец .txt")
    d.add_argument("texts", nargs="+")
    d.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "build":
            print(json.dumps(build(_read(args.sample)), ensure_ascii=False))
            return 0
        raw = _read(args.profile)
        profile = json.loads(raw) if args.profile.endswith(".json") else build(raw)
        results = {t: distance(profile, _read(t)) for t in args.texts}
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print("[M-VOICE-PROFILE] не читается: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0
    if profile.get("warning"):
        print(profile["warning"])
    for name, res in results.items():
        print("%s: расстояние %.3f (0 — манера автора, 1 — ничего общего)" % (name, res["distance"]))
        for line in res["differences"]:
            print("  - " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
