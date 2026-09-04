#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""f8_corpus_build.py — П3/ЭТАП3: единый корпус зонтика F8 до заморозки
предрега. Страты: S1 machine 2021-22 (CoAT validation label=1), S2 machine
2024-26 (eval/runs), S3 human light (CoAT validation label=0 + registry-40),
S4 human heavy (законы РФ PD через GitHub code search, канцелярит PD там же,
OCR Wikisource ru CC BY-SA), S5 sensitivity artifact-bearing (GitHub code
search по сигнатурам маркеров, blob SHA immutable).

Eligibility: длина >= 40, доля кириллицы >= 0.5 (S5: >= 0.3), дедуп по
sha256 текста. Фрагменты не публикуются: наружу только агрегаты и хеши.
Выход: measurement/f8-2026-09/corpus.jsonl + corpus.tar.gz + sha256.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = Path(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))) / \
    "measurement" / "f8-2026-09"

CYR = re.compile("[а-яё]")


def cyr_share(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if CYR.match(c)) / len(letters)


def eligible(text, min_cyr=0.5):
    return len(text) >= 40 and cyr_share(text) >= min_cyr


def gh_json(args):
    cmd = ["gh", "api"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def gh_code_search(query, per_page=30, pages=3):
    out = []
    for page in range(1, pages + 1):
        d = gh_json(["--method", "GET", "search/code",
                     "-f", "q=" + query, "-f", "per_page=%d" % per_page,
                     "-f", "page=%d" % page])
        if not d or not d.get("items"):
            break
        for it in d["items"]:
            out.append(it)
    return out


def fetch_raw(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


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
    return out


def registry40():
    out = []
    for sub in ("human", "adversarial", "boundary"):
        d = ROOT / "research" / "validation" / sub
        if not d.is_dir():
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".txt"):
                out.append((d / fn).read_text(encoding="utf-8"))
    return out


def wikisource_ocr(n=200):
    out = []
    base = ("https://ru.wikisource.org/w/api.php?action=query&format=json"
            "&list=categorymembers&cmtitle=%s&cmlimit=50&cmtype=page")
    d = None
    for catname in ("Категория:Вычитанные страницы",
                    "Категория:Страницы с распознанным текстом",
                    "Категория:OCR"):
        cat = urllib.parse.quote(catname)
        try:
            with urllib.request.urlopen(base % cat, timeout=60) as r:
                d = json.load(r)
            if d.get("query", {}).get("categorymembers"):
                break
        except Exception:
            d = None
    if not d:
        return out
    titles = [m["title"] for m in
              d.get("query", {}).get("categorymembers", [])][:40]
    for t in titles:
        if len(out) >= n:
            break
        u = ("https://ru.wikisource.org/w/api.php?action=parse&format=json"
             "&prop=wikitext&page=" + urllib.parse.quote(t))
        try:
            with urllib.request.urlopen(u, timeout=60) as r:
                dd = json.load(r)
            txt = dd.get("parse", {}).get("wikitext", {}).get("*", "")
        except Exception:
            continue
        if eligible(txt):
            out.append(txt)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set()
    rows = []

    def add(stratum, text, meta=None):
        if not text:
            return
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h in seen:
            return
        seen.add(h)
        rows.append({"stratum": stratum, "sha256": h, "text": text,
                     "meta": meta or {}})

    for t in coat_split(1):
        if eligible(t):
            add("S1-machine-21-22", t)
    for t in eval_runs_machine():
        if eligible(t):
            add("S2-machine-24-26", t)
    for t in coat_split(0):
        if eligible(t):
            add("S3-human-light", t)
    for t in registry40():
        add("S3-human-light", t)

    # S4 heavy: законы РФ и канцелярит (официальные документы, PD), OCR WS
    for query, strat in (("ФЕДЕРАЛЬНЫЙ ЗАКОН extension:md", "S4-heavy-legal"),
                         ("постановляет приказываю extension:md",
                          "S4-heavy-official"),
                         ("МУНИЦИПАЛЬНОЕ ОБРАЗОВАНИЕ постановление "
                          "extension:md", "S4-heavy-official"),
                         ("приказ утвердить приложение extension:txt",
                          "S4-heavy-official")):
        for it in gh_code_search(query, pages=8):
            raw = ("https://raw.githubusercontent.com/%s/%s/%s" % (
                it["repository"]["full_name"],
                urllib.parse.quote(it.get("ref", "master")),
                urllib.parse.quote(it["path"])))
            txt = fetch_raw(raw)
            if txt and eligible(txt):
                add(strat, txt, {"repo": it["repository"]["full_name"],
                                 "path": it["path"],
                                 "sha": it.get("sha", "")})
    for t in wikisource_ocr(200):
        add("S4-heavy-ocr", t, {"source": "ru.wikisource.org",
                                "license": "CC BY-SA"})
    # MT + человеческая редактура: msgstr из .po (переводные проекты)
    for it in gh_code_search("Project-Id-Version extension:po", pages=8):
        txt = fetch_raw("https://raw.githubusercontent.com/%s/%s/%s" % (
            it["repository"]["full_name"],
            urllib.parse.quote(it.get("ref", "master")),
            urllib.parse.quote(it["path"])))
        if not txt:
            continue
        if eligible(txt):
            add("S4-heavy-mt-human", txt,
                {"repo": it["repository"]["full_name"],
                 "path": it["path"], "sha": it.get("sha", ""),
                 "license": "по лицензии репозитория; фрагменты локально"})

    # S5 sensitivity: blob'ы с сигнатурами маркеров (immutable SHA)
    for sig in (":contentReference", "cite_turn", "oaicite",
                "utm_source=chatgpt", "grok.com/?referrer",
                "attributableIndex"):
        for it in gh_code_search('"%s"' % sig, pages=8):
            txt = fetch_raw("https://raw.githubusercontent.com/%s/%s/%s" % (
                it["repository"]["full_name"],
                urllib.parse.quote(it.get("ref", "master")),
                urllib.parse.quote(it["path"])))
            if txt and len(txt) >= 40:
                add("S5-artifact-bearing", txt,
                    {"repo": it["repository"]["full_name"],
                     "path": it["path"], "sha": it.get("sha", ""),
                     "sig": sig})

    jsonl = OUT / "corpus.jsonl"
    with open(jsonl, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tar = OUT / "corpus.tar.gz"
    with tarfile.open(tar, "w:gz", format=tarfile.GNU_FORMAT) as tf:
        info = tarfile.TarInfo("corpus.jsonl")
        data = jsonl.read_bytes()
        info.size = len(data)
        info.mtime = 1756944000
        tf.addfile(info, io.BytesIO(data))
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    (OUT / "corpus-sha256.txt").write_text(sha + "\n", encoding="utf-8")
    import collections
    cnt = collections.Counter(r["stratum"] for r in rows)
    print("строк:", len(rows), dict(cnt))
    print("corpus sha256:", sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
