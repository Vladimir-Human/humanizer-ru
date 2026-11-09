#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Release gate 6 of 4.2.0 (eval/README): does an edit "in my manner" with the author's
#          sample come closer to the author than the same skill's edit without it? Four public-
#          domain authors from ru.wikisource; each text is split into a sample (given to the
#          editor) and a held-out part (the target), so copying phrases from the sample earns
#          nothing. Closeness = voice_profile.py distance (character 3-grams) to the held-out part.
# SCOPE: `fetch` writes eval/corpus/voice/<slug>.txt and index.json; `run` makes 2 model notes per
#        author (MiniMax, free route) and edits them with each system, with and without the
#        sample; `score` writes eval/results/<run>/voice.md and voice.json.
# DEPENDS: evallib, run_systems (load_system, inline_system, REQUEST), fetch_human (_Paragraphs),
#          skills/humanizer-ru/scripts/voice_profile.py.
# LINKS: M-EVAL-VOICE; R-VOICE; V-M-VOICE-PROFILE.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# AUTHORS: slug, author, ru.wikisource page.
# fetch: page text (paragraphs) at its current revision, permanent link kept.
# parts: sample (first ~700 words), held-out (next ~1200), topics (paragraphs after that).
# run: notes from topics, then edits: "<system>+sample" and "<system>" for each system.
# score: distance of every edit to the held-out profile; per author, mean with and without sample.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import evallib as lib
import run_systems as rs
from fetch_human import _Paragraphs

API = "https://ru.wikisource.org/w/api.php"
UA = "humanizer-ru-eval/1.0 (https://github.com/Vladimir-Human/humanizer-ru)"
VOICE = lib.EVAL_DIR / "corpus" / "voice"
AUTHORS = [
    ("gilyarovsky", "В. А. Гиляровский", "Москва и москвичи (Гиляровский)/Сухаревка"),
    ("rozanov", "В. В. Розанов", "Уединенное (Розанов)"),
    ("chekhov", "А. П. Чехов", "Остров Сахалин (Чехов)/Глава 03"),
    ("doroshevich", "В. М. Дорошевич", "Сахалин (Дорошевич)/Столица Сахалина"),
]
NOTE_MODEL = "dsh:minimax/MiniMax-M3.1-Flash"
SAMPLE_WORDS, HELD_WORDS = 700, 1200
VOICE_REQUEST = ("Вот образец моего текста:\n\n{sample}\n\nПерепиши текст ниже в моей манере, как будто его "
                 "написал я. Факты не меняй.\n\n")

_spec = importlib.util.spec_from_file_location("voice_profile", lib.EVAL_DIR.parent / "skills/humanizer-ru/scripts/voice_profile.py")
voice_profile = importlib.util.module_from_spec(_spec)
sys.modules["voice_profile"] = voice_profile
_spec.loader.exec_module(voice_profile)


def _api(**params) -> dict:
    params.update(format="json", formatversion="2")
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch() -> int:
    VOICE.mkdir(parents=True, exist_ok=True)
    index = []
    for slug, author, title in AUTHORS:
        parsed = _api(action="parse", page=title, prop="text|revid", disablelimitreport=1)["parse"]
        p = _Paragraphs()
        p.feed(parsed["text"])
        paras = [html.unescape(t) for t in p.paras if len(t) > 60]
        text = "\n\n".join(paras)
        lib.write_text(VOICE / (slug + ".txt"), text + "\n")
        index.append({"id": slug, "author": author, "title": title, "revision": parsed["revid"],
                      "url": "https://ru.wikisource.org/w/index.php?oldid=%d" % parsed["revid"],
                      "licence": "общественное достояние", "words": len(voice_profile.WORD_RX.findall(text)),
                      "pre_reform": sum(text.count(c) for c in "ѣіѳ")})
        print("[M-EVAL-VOICE][fetch] %s words=%d pre_reform=%d" % (slug, index[-1]["words"], index[-1]["pre_reform"]))
    lib.write_json(VOICE / "index.json", index)
    return 0


def parts(text: str) -> tuple:
    """Whole paragraphs: sample up to SAMPLE_WORDS, held-out up to HELD_WORDS, the rest for topics."""
    out, cur, n, limits = [[], [], []], 0, 0, (SAMPLE_WORDS, HELD_WORDS)
    for para in text.split("\n\n"):
        w = len(voice_profile.WORD_RX.findall(para))
        if cur < 2 and n + w > limits[cur] and out[cur]:
            cur, n = cur + 1, 0
        out[cur].append(para)
        n += w
    return tuple("\n\n".join(x) for x in out)


def _note_prompt(topic: str) -> str:
    return ("Напиши короткую заметку для блога, примерно 200 слов, по этим фактам и наблюдениям. "
            "Пиши своими словами, современным языком.\n\n" + topic)


def run(run_name: str, systems: list, executor: str, workers: int) -> int:
    run_dir = lib.EVAL_DIR / "results" / run_name / "voice"
    sysdefs = {s["name"]: s for s in lib.read_json(lib.EVAL_DIR / "systems.json")}
    loaded = {}
    for name in systems:
        system, files = rs.load_system(sysdefs[name])
        loaded[name] = rs.inline_system(system, files) if executor.startswith(lib.DSH_PREFIX) else system
    jobs = []
    for slug, _, _ in AUTHORS:
        sample, _, rest = parts(lib.read_text(VOICE / (slug + ".txt")))
        topics = [p for p in rest.split("\n\n") if len(p) > 300][:2]
        for k, topic in enumerate(topics):
            note_path = run_dir / "notes" / ("%s-%d.txt" % (slug, k))
            if not note_path.exists():
                msg, _ = lib.chat(NOTE_MODEL, [{"role": "user", "content": _note_prompt(topic[:1500])}], max_tokens=4000, tag="voice")
                lib.write_text(note_path, (msg.get("content") or "").strip() + "\n")
            note = lib.read_text(note_path)
            for name in systems:
                for with_sample in (True, False):
                    label = name + ("+sample" if with_sample else "")
                    path = run_dir / label / ("%s-%d.txt" % (slug, k))
                    if not path.exists():
                        req = VOICE_REQUEST.format(sample=sample) if with_sample else rs.REQUEST
                        jobs.append((path, loaded[name], req + note))

    def one(job):
        path, system, user = job
        msg, _ = lib.chat(executor, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                          max_tokens=6000, tag="voice")
        text = (msg.get("content") or "").strip()
        if not text:
            raise RuntimeError("empty answer")
        lib.write_text(path, text + "\n")

    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, j): j[0] for j in jobs}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                failed += 1
                print("[M-EVAL-VOICE][run] failed %s: %s" % (futures[fut], str(exc)[:200]))
    lib.write_json(run_dir / "config.json", {"executor": executor, "systems": systems, "note_model": NOTE_MODEL})
    print("[M-EVAL-VOICE][run] jobs=%d failed=%d" % (len(jobs), failed))
    return 1 if failed else 0


def _body(text: str) -> str:
    """The edited text without the notes after the last line '---'."""
    lines = text.rstrip().split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "---":
            return "\n".join(lines[:i]).strip()
    return text.strip()


def score(run_name: str) -> int:
    run_dir = lib.EVAL_DIR / "results" / run_name / "voice"
    labels = sorted(d.name for d in run_dir.iterdir() if d.is_dir() and d.name != "notes")
    res = {}
    for slug, author, _ in AUTHORS:
        _, held, _ = parts(lib.read_text(VOICE / (slug + ".txt")))
        prof = voice_profile.build(held)
        row = {"note": []}
        for f in sorted((run_dir / "notes").glob(slug + "-*.txt")):
            row["note"].append(voice_profile.distance(prof, lib.read_text(f))["distance"])
            for label in labels:
                p = run_dir / label / f.name
                if p.exists():
                    row.setdefault(label, []).append(voice_profile.distance(prof, _body(lib.read_text(p)))["distance"])
        res[slug] = {k: round(sum(v) / len(v), 4) for k, v in row.items() if v}
        res[slug]["author"] = author
    systems = sorted({l.replace("+sample", "") for l in labels})
    verdict = {s: sum(1 for slug in res if s + "+sample" in res[slug] and s in res[slug]
                      and res[slug][s + "+sample"] < res[slug][s]) for s in systems}
    md = ["# Голос автора: %s" % run_name, "",
          "Расстояние по символьным триграммам до отложенной части текста автора (0 — та же манера). "
          "Образец (первые ~%d слов) получает только правка «+sample»; отложенная часть (следующие ~%d слов) "
          "редактору не показывается." % (SAMPLE_WORDS, HELD_WORDS), "",
          "| Автор | Заметка модели | " + " | ".join(labels) + " |", "|---" * (len(labels) + 2) + "|"]
    for slug, r in res.items():
        md.append("| %s | %.3f | " % (r["author"], r["note"]) + " | ".join("%.3f" % r[l] if l in r else "—" for l in labels) + " |")
    md += [""] + ["- `%s`: правка с образцом ближе к автору у %d из %d авторов (порог 6: хотя бы у 3)." % (s, verdict[s], len(res))
                  for s in systems]
    lib.write_text(run_dir / "voice.md", "\n".join(md) + "\n")
    lib.write_json(run_dir / "voice.json", {"authors": res, "closer_with_sample": verdict})
    print("\n".join(md))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    r = sub.add_parser("run")
    r.add_argument("--run", required=True)
    r.add_argument("--systems", default="ours,ours417")
    r.add_argument("--executor", default="dsh:minimax/MiniMax-M3.1-Flash")
    r.add_argument("--workers", type=int, default=4)
    s = sub.add_parser("score")
    s.add_argument("--run", required=True)
    args = ap.parse_args()
    if args.cmd == "fetch":
        return fetch()
    if args.cmd == "run":
        return run(args.run, args.systems.split(","), args.executor, args.workers)
    return score(args.run)


if __name__ == "__main__":
    raise SystemExit(main())
