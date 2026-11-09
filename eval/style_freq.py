#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Find word sequences that free chat models use far more often than people writing the
#          same kind of text, as candidates for the style rules (skills/humanizer-ru/scripts/
#          rules.json). Human side: ru.wikinews articles as of 2021-12-31 (fetch_human.py) that are
#          not eval controls. AI side: a news item on the same headline and lead, written by
#          MiniMax M3.1 Flash or GPT-6.1 Sol through the free DSH route. Same topic, same genre,
#          so a phrase that leans to one side leans by style, not by subject.
# SCOPE: `gen` writes eval/corpus/pairs/<id>.txt and pairs/index.json; `rank` writes
#        eval/results/style-freq/candidates.md and .json. A candidate enters rules.json only
#        after an eye check (the table is evidence, not a rule list).
# DEPENDS: evallib (chat over the free DSH route, IO); build_corpus.human_wikinews (controls).
# LINKS: M-EVAL-STYLE-FREQ; R-RULES-EVIDENCE; V-M-EVAL-STYLE-FREQ.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# pair_prompt: the request for the AI side (headline, lead, length).
# gen: generate the missing AI texts, alternating MiniMax and Sol, saving each as it is ready.
# tokens / doc_ngrams: lower-case words (ё → е), 1–3-word sequences per text (no digits).
# log_odds: log odds ratio of texts with and without a sequence, smoothed, z-scored;
#           one text repeating a phrase counts once.
# rank: candidates above support and z thresholds, both directions, Markdown and JSON.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import evallib as lib
from build_corpus import CHAT_PERSONA, human_wikinews

HUMAN = lib.EVAL_DIR / "corpus" / "human"
PAIRS = lib.EVAL_DIR / "corpus" / "pairs"
OUT = lib.EVAL_DIR / "results" / "style-freq"
MODELS = ("dsh:minimax/MiniMax-M3.1-Flash", "dsh:agentrouter-astra/gpt-6.1-sol")


def pool_rows() -> list:
    """Wikinews rows that are not eval controls, in revision order."""
    rows = lib.read_json(HUMAN / "index.json")
    controls = {r["id"] for r in human_wikinews(rows)}
    return sorted((r for r in rows if r["id"] not in controls), key=lambda r: r["revision"])


def pair_prompt(title: str, text: str) -> str:
    lead = text.split("\n\n")[0]
    return ("Напиши новость для новостного сайта, примерно %d знаков. Заголовок: «%s». "
            "Главное, что известно: %s" % (round(len(text), -2), title, lead))


def _one(row: dict, model: str) -> tuple:
    text = lib.read_text(HUMAN / (row["id"] + ".txt"))
    messages = [{"role": "system", "content": CHAT_PERSONA},
                {"role": "user", "content": pair_prompt(row["title"], text)}]
    msg, _ = lib.chat(model, messages, max_tokens=6000, tag="style-freq")
    out = (msg.get("content") or "").strip()
    if len(out) < 200:
        raise RuntimeError("short answer (%d chars)" % len(out))
    return row["id"], out + "\n"


# START_CONTRACT: gen
# PURPOSE: The AI side of every pair that is not generated yet.
# INPUTS: workers; the pool from pool_rows (row k goes to MODELS[k % 2]).
# OUTPUTS: pairs/<id>.txt per text, pairs/index.json {id: model} for the texts that exist.
# SIDE_EFFECTS: free DSH calls only (evallib refuses any other route for dsh: models).
# END_CONTRACT: gen
def gen(workers: int) -> int:
    PAIRS.mkdir(parents=True, exist_ok=True)
    rows = pool_rows()
    plan = {r["id"]: (r, MODELS[k % 2]) for k, r in enumerate(rows)}
    todo = [v for k, v in plan.items() if not (PAIRS / (k + ".txt")).exists()]
    failed = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, r, m): r["id"] for r, m in todo}
        for fut in as_completed(futures):
            try:
                tid, out = fut.result()
            except Exception as exc:
                failed.append(futures[fut])
                print("[M-EVAL-STYLE-FREQ][gen] failed %s %s" % (futures[fut], repr(exc)[:200]))
                continue
            lib.write_text(PAIRS / (tid + ".txt"), out)
            print("[M-EVAL-STYLE-FREQ][gen] %s %d chars" % (tid, len(out)))
    index = {k: m for k, (_, m) in plan.items() if (PAIRS / (k + ".txt")).exists()}
    lib.write_json(PAIRS / "index.json", index)
    print("[M-EVAL-STYLE-FREQ][gen] pairs=%d failed=%d" % (len(index), len(failed)))
    return 1 if failed else 0


WORD = re.compile(r"[а-яёa-z]+(?:-[а-яёa-z]+)*")


def tokens(text: str) -> list:
    return WORD.findall(text.lower().replace("ё", "е"))


def doc_ngrams(text: str, n_max: int = 3) -> set:
    """Every 1..n_max word sequence inside one sentence of the text."""
    seen = set()
    for sent in re.split(r"[.!?…:;\n]+", text):
        toks = tokens(sent)
        for n in range(1, n_max + 1):
            for i in range(len(toks) - n + 1):
                seen.add(" ".join(toks[i:i + n]))
    return seen


# START_CONTRACT: log_odds
# PURPOSE: How strongly each sequence leans to the AI side, beyond chance.
# INPUTS: ai_docs, human_docs: lists of sets of sequences (one set per text); a: smoothing.
# OUTPUTS: {seq: (z, ai_docs_with_it, human_docs_with_it)}; z > 0 means AI-leaning.
# RULE: per sequence a 2x2 table of texts with and without it on each side; z is the log odds
#       ratio with a added to every cell, divided by its standard error (Wald). A sequence in
#       every text of both sides gets 0, and a text repeating it counts once.
# END_CONTRACT: log_odds
def log_odds(ai_docs: list, human_docs: list, a: float = 0.5) -> dict:
    ca, ch = Counter(), Counter()
    for d in ai_docs:
        ca.update(d)
    for d in human_docs:
        ch.update(d)
    na, nh = len(ai_docs), len(human_docs)
    out = {}
    for w in set(ca) | set(ch):
        ya, yh = ca[w], ch[w]
        lor = math.log((ya + a) / (na - ya + a)) - math.log((yh + a) / (nh - yh + a))
        se = math.sqrt(1 / (ya + a) + 1 / (na - ya + a) + 1 / (yh + a) + 1 / (nh - yh + a))
        out[w] = (lor / se, ya, yh)
    return out


def rank(min_docs: int, min_z: float, top: int) -> int:
    pairs = lib.read_json(PAIRS / "index.json")
    ids = sorted(pairs)
    ai = [doc_ngrams(lib.read_text(PAIRS / (i + ".txt"))) for i in ids]
    hu = [doc_ngrams(lib.read_text(HUMAN / (i + ".txt"))) for i in ids]
    scores = log_odds(ai, hu)
    by_model = {m: [d for i, d in zip(ids, ai) if pairs[i] == m] for m in MODELS}

    def row(w, s):
        z, ya, yh = s
        per = {m.split("/")[-1]: sum(1 for d in docs if w in d) for m, docs in by_model.items()}
        return {"seq": w, "z": round(z, 2), "ai_texts": ya, "human_texts": yh, "by_model": per}

    lean_ai = sorted((row(w, s) for w, s in scores.items() if s[0] >= min_z and s[1] >= min_docs), key=lambda r: -r["z"])[:top]
    lean_hu = sorted((row(w, s) for w, s in scores.items() if s[0] <= -min_z and s[2] >= min_docs), key=lambda r: r["z"])[:top]
    OUT.mkdir(parents=True, exist_ok=True)
    lib.write_json(OUT / "candidates.json", {"pairs": len(ids), "min_docs": min_docs, "min_z": min_z,
                                             "ai_leaning": lean_ai, "human_leaning": lean_hu})
    md = ["# Частотное сравнение: %d пар «человек — модель» на одну тему" % len(ids), "",
          "Человек: статьи Викиновостей в редакции до 31.12.2021. Модель: новость по тому же заголовку и "
          "первому абзацу (MiniMax M3.1 Flash и GPT-6.1 Sol поровну). Счёт по текстам: сколько текстов "
          "содержат сочетание. z — логарифм отношения шансов (текстов с сочетанием и без него) со "
          "сглаживанием 0,5, делённый на его стандартную ошибку. Порог: z ≥ %.1f и не меньше %d текстов. Это кандидаты, правила "
          "отбираются вручную." % (min_z, min_docs), ""]
    for title, rows in (("Чаще у моделей", lean_ai), ("Чаще у людей", lean_hu)):
        md += ["## %s" % title, "", "| Сочетание | z | Тексты модели | Тексты людей | По моделям |", "|---|---|---|---|---|"]
        md += ["| %s | %.1f | %d | %d | %s |" % (r["seq"], r["z"], r["ai_texts"], r["human_texts"],
                                                 ", ".join("%s %d" % kv for kv in r["by_model"].items())) for r in rows]
        md.append("")
    lib.write_text(OUT / "candidates.md", "\n".join(md))
    print("[M-EVAL-STYLE-FREQ][rank] pairs=%d ai_leaning=%d human_leaning=%d" % (len(ids), len(lean_ai), len(lean_hu)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--workers", type=int, default=5)
    r = sub.add_parser("rank")
    r.add_argument("--min-docs", type=int, default=8)
    r.add_argument("--min-z", type=float, default=3.0)
    r.add_argument("--top", type=int, default=150)
    args = ap.parse_args()
    return gen(args.workers) if args.cmd == "gen" else rank(args.min_docs, args.min_z, args.top)


if __name__ == "__main__":
    raise SystemExit(main())
