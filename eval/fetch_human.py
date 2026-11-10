#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Collect human-written Russian news texts for two uses: controls that a good editor
#          leaves almost untouched (set "human"), and the human side of the frequency comparison
#          behind the style rules (lint_style, rules.json). Each text is a ru.wikinews.org article
#          as it stood on 2021-12-31 (before chat assistants), so it was written by people.
# SCOPE: network reads of the public MediaWiki API only; writes eval/corpus/human/<id>.txt and
#        eval/corpus/human/index.json (title, permanent link to the revision, date, licence).
# DEPENDS: Python 3.9+ stdlib (urllib, html.parser).
# LINKS: M-EVAL-HUMAN; R-HUMAN-CONTROLS; V-M-EVAL-HUMAN.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# api: one GET to the API with a descriptive User-Agent, JSON in, retries on network errors.
# old_revision: the last revision of a page on or before the cut date, or None.
# html_text: paragraphs of the parsed revision as plain text (no tables, references, captions).
# collect: random pages until N texts of the wanted length; skips digests and stubs.
# main: CLI --count --cut --min --max.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

API = "https://ru.wikinews.org/w/api.php"
UA = "humanizer-ru-eval/1.0 (https://github.com/Vladimir-Human/humanizer-ru)"
OUT = Path(__file__).resolve().parent / "corpus" / "human"
LICENCE = "Викиновости, CC BY 2.5"


def api(**params) -> dict:
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network hiccup: wait and retry, then give up
            if attempt == 3:
                raise
            print("[M-EVAL-HUMAN][api] retry after %s" % str(exc)[:120])
            time.sleep(2 + attempt * 3)
    return {}


def old_revision(title: str, cut: str):
    pages = api(action="query", prop="revisions", titles=title, rvprop="ids|timestamp",
                rvlimit=1, rvdir="older", rvstart=cut)["query"]["pages"]
    revs = pages[0].get("revisions") if pages else None
    return (revs[0]["revid"], revs[0]["timestamp"]) if revs else None


class _Paragraphs(HTMLParser):
    """Text of top-level <p> elements; <sup> (references) and tables are skipped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paras, self.buf, self.in_p, self.skip = [], [], False, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("sup", "table", "style", "script") or (tag == "div" and ("class", "thumbcaption") in attrs):
            self.skip += 1
        elif tag == "p" and not self.skip:
            self.in_p, self.buf = True, []

    def handle_endtag(self, tag):
        if tag in ("sup", "table", "style", "script") and self.skip:
            self.skip -= 1
        elif tag == "p" and self.in_p:
            self.in_p = False
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if text:
                self.paras.append(text)

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.buf.append(data)


def html_text(revid: int) -> str:
    parsed = api(action="parse", oldid=revid, prop="text", disablelimitreport=1)
    p = _Paragraphs()
    p.feed(parsed.get("parse", {}).get("text", ""))
    paras = [t for t in p.paras if len(t) > 40 and not t.startswith(("Источники", "Ссылки"))]
    return html.unescape("\n\n".join(paras)).strip()


# START_CONTRACT: collect
# PURPOSE: Gather `count` human news texts written before `cut`.
# INPUTS: count, cut (ISO timestamp), min_len/max_len (characters of the kept text), seen ids.
# OUTPUTS: list of index rows; texts written to OUT as wn<revid>.txt.
# RULES: a page is used only if it had a revision on or before `cut`; that revision's text is
#        taken, cut to whole paragraphs up to max_len; digests («Лента новостей») and texts shorter
#        than min_len are skipped.
# END_CONTRACT: collect
def collect(count: int, cut: str, min_len: int, max_len: int, seen: set) -> list:
    rows = []
    while len(rows) < count:
        batch = api(action="query", list="random", rnnamespace=0, rnlimit=20)["query"]["random"]
        for page in batch:
            title = page["title"]
            if title.startswith("Лента новостей") or title in seen:
                continue
            seen.add(title)
            rev = old_revision(title, cut)
            if not rev:
                continue
            text = html_text(rev[0])
            kept, size = [], 0
            for para in text.split("\n\n"):
                if size + len(para) > max_len and kept:
                    break
                kept.append(para)
                size += len(para) + 2
            body = "\n\n".join(kept)
            if len(body) < min_len:
                continue
            tid = "wn%d" % rev[0]
            (OUT / (tid + ".txt")).write_text(body + "\n", encoding="utf-8", newline="\n")
            rows.append({"id": tid, "title": title, "revision": rev[0], "date": rev[1][:10],
                         "url": "https://ru.wikinews.org/w/index.php?oldid=%d" % rev[0], "licence": LICENCE})
            print("[M-EVAL-HUMAN][collect] %d/%d %s %s" % (len(rows), count, rev[1][:10], len(body)))
            if len(rows) >= count:
                break
            time.sleep(0.2)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=170)
    ap.add_argument("--cut", default="2021-12-31T23:59:59Z")
    ap.add_argument("--min", type=int, default=500)
    ap.add_argument("--max", type=int, default=2500)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    seen = {r["title"] for r in index}
    need = args.count - len(index)
    if need > 0:
        index += collect(need, args.cut, args.min, args.max, seen)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("[M-EVAL-HUMAN] texts=%d" % len(index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
