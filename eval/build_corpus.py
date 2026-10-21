#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Build the comparison corpus: generate fresh Russian AI texts from briefs with
#          different models, add saved real chatbot answers and human/legal "trap" texts.
# SCOPE: writes eval/corpus/texts/<id>.txt and eval/corpus/index.json; idempotent
#        (existing texts are kept unless --force).
# DEPENDS: eval/lib.py (chat, ledger); --legacy DIR with research/raw and
#          research/validation/human from tag v3.36.4 (git archive).
# LINKS: M-EVAL-CORPUS; DF-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# REAL / TRAPS: fixed lists of saved texts with origin and licence notes.
# PROBES: hand-written targeted texts kept in corpus/texts (never judged, see README final4).
# strip_header: drop "Вопрос:/Ответ ...:" preamble from saved chatbot answers.
# inject: add chat paste artifacts (utm tail, contentReference, zero-width spaces).
# generate: one text from a brief; "dsh:" models get the chat-assistant persona.
# main: generate missing texts, copy saved ones, write index.json.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import evallib as lib

CORPUS = lib.EVAL_DIR / "corpus"
TEXTS = CORPUS / "texts"

# Saved answers of real chatbots (collected 2026-07/08 for v3; origin notes from
# research/validation/README.md at tag v3.36.4).
REAL = [
    ("r01", "research/raw/alisa/01-слепая-печать.txt", "Алиса (YandexGPT), ответ 14.07.2026", "совет"),
    ("r02", "research/raw/gigachat/05-подарок-коллеге.txt", "GigaChat, ответ 14.07.2026", "совет"),
    ("r03", "research/raw/deepseek/03-v3-svinye-krylyshki.txt", "DeepSeek-V3, цитата из интервью на Хабре 29.01.2025", "рецепт"),
    ("r04", "research/raw/grok/03-grok3-gran-buduschego.txt", "grok-3, датасет vaniley/grok_answer_mail_ru", "ответ"),
    ("r05", "research/raw/copilot/02-bing-creative-neiroseti.txt", "Bing Creative, статья Click.ru на Хабре 22.03.2023", "ответ"),
    ("r06", "research/raw/gemini/01-25pro-utopia.txt", "Gemini 2.5 Pro, статья «Утопия в литературе» (Википедия, CC BY-SA)", "статья"),
]
# Human or legal texts: a good editor should leave them almost untouched.
TRAPS = [
    ("h01", "research/validation/human/07-chekhov-letter.txt", "А. П. Чехов, письмо (Викитека, общественное достояние)", "письмо"),
    ("h02", "research/validation/human/19-gilyarovsky-moskvich.txt", "В. А. Гиляровский, «Москва и москвичи» (общественное достояние)", "очерк"),
    ("h03", "research/validation/human/24-gercen-byloe-i-dumy.txt", "А. И. Герцен, «Былое и думы» (общественное достояние)", "мемуары"),
    ("h04", "research/validation/human/09-wikipedia-modern.txt", "Русская Википедия (CC BY-SA)", "энциклопедия"),
    ("h05", "research/validation/human/10-wikinews.txt", "Викиновости (CC BY 2.5)", "новость"),
    ("h06", "research/validation/human/08-constitution.txt", "Конституция РФ, ст. 2 (официальный документ)", "закон"),
]
# Targeted texts for the new rules of a candidate, written by hand before its run and never
# shown to judges: patterns.py and check_facts.py read the outputs (README, final4).
PROBES = [
    ("p01", "ответ чат-бота с хвостами вставки", "написан вручную 21.10.2026 для правил кандидата 98cf8cc"),
    ("p02", "статья с шаблонами из Википедии", "написан вручную 21.10.2026 для правил кандидата 98cf8cc"),
]
# The DSH agent is a coding agent by default; a generated text must read as a chat answer.
CHAT_PERSONA = ("You are a regular chat assistant like ChatGPT. Answer the user's request below "
                "the way you would in a chat.")


def strip_header(text: str) -> str:
    lines = text.lstrip("﻿").splitlines()
    for i, line in enumerate(lines[:12]):
        if re.match(r"^Ответ\b", line.strip()):
            return "\n".join(lines[i + 1:]).strip() + "\n"
    return "\n".join(lines).strip() + "\n"


def inject(text: str, kind: str) -> str:
    if kind == "utm":
        return re.sub(r"(https?://[^\s)\]»]+)", r"\1?utm_source=chatgpt.com", text, count=1)
    if kind == "contentref":
        # Mark the end of the 1st and 3rd sentence; whitespace and line breaks stay as they were.
        ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", text)]
        for n, pos in reversed(list(enumerate(ends[0:3:2]))):
            text = text[:pos] + " :contentReference[oaicite:%d]{index=%d}" % (n, n) + text[pos:]
        return text
    if kind == "zwsp":
        out, count = [], 0
        for token in re.split(r"( )", text):
            out.append(token)
            if token == " ":
                count += 1
                if count % 7 == 0:
                    out.append("​")
        return "".join(out)
    return text


def generate(brief: dict) -> tuple:
    # Reasoning models (GLM 5.3) can spend a small budget on thinking and return nothing.
    messages = [{"role": "user", "content": brief["prompt"]}]
    if brief["model"].startswith(lib.DSH_PREFIX):
        messages.insert(0, {"role": "system", "content": CHAT_PERSONA})
    for _ in range(2):
        msg, usage = lib.chat(brief["model"], messages, max_tokens=16000, tag="corpus")
        text = (msg.get("content") or "").strip() + "\n"
        if len(text) > 50:
            break
    else:
        raise RuntimeError("empty output from %s for %s" % (brief["model"], brief["id"]))
    if brief.get("inject"):
        text = inject(text, brief["inject"])
    return brief["id"], text, usage.get("cost", 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", required=True, help="folder with v3.36.4 research/ (git archive)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    legacy = Path(args.legacy)
    briefs = lib.read_json(CORPUS / "briefs.json")
    TEXTS.mkdir(parents=True, exist_ok=True)

    todo = [b for b in briefs if args.force or not (TEXTS / (b["id"] + ".txt")).exists()]
    failed = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        # Each text is saved as soon as it is ready: one failed brief must not lose the others.
        futures = {pool.submit(generate, b): b["id"] for b in todo}
        for fut in as_completed(futures):
            try:
                bid, text, cost = fut.result()
            except lib.BudgetExceeded:
                raise
            except Exception as exc:
                failed.append(futures[fut])
                print("failed", futures[fut], repr(exc)[:300])
                continue
            lib.write_text(TEXTS / (bid + ".txt"), text)
            print("generated", bid, len(text), "chars, $%.4f" % float(cost or 0))
    if failed:
        # index.json is written only for a complete corpus; a rerun generates just the missing texts.
        raise SystemExit("not generated: %s" % ", ".join(sorted(failed)))

    index = []
    for b in briefs:
        index.append({"id": b["id"], "set": b["set"], "kind": "generated", "genre": b["genre"],
                      "origin": b["model"], "prompt": b["prompt"], "inject": b.get("inject")})
    for kind, rows in (("real", REAL), ("trap", TRAPS)):
        for tid, rel, origin, genre in rows:
            src = legacy / rel
            text = strip_header(lib.read_text(src)) if kind == "real" else lib.read_text(src).strip() + "\n"
            lib.write_text(TEXTS / (tid + ".txt"), text)
            index.append({"id": tid, "set": "test", "kind": kind, "genre": genre, "origin": origin})
    for tid, genre, origin in PROBES:
        if (TEXTS / (tid + ".txt")).exists():
            index.append({"id": tid, "set": "probe", "kind": "probe", "genre": genre, "origin": origin})
    lib.write_json(CORPUS / "index.json", index)
    print("index:", len(index), "texts; spend so far $%.4f" % lib.ledger().data["total"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
