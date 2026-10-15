#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Blind ranking of all system outputs for each text by judge models from other labs
#          than the executor. Candidates are shuffled per (text, judge, round) and labelled A, B, ...
#          The judge also lists fact errors, AI traces and language errors per candidate.
# SCOPE: reads eval/results/<run>/outputs; appends eval/results/<run>/judgments.jsonl; resumable.
# DEPENDS: evallib (chat, ledger).
# LINKS: M-EVAL-JUDGE; DF-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# PROMPT: judge instructions (Russian), answer format JSON.
# build: shuffled candidate block and the label->system key.
# parse: tolerant JSON extraction from the judge answer.
# main: CLI --run --judges (model=N for N passes) --rounds --texts.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import json
import random
import re
import string
from concurrent.futures import ThreadPoolExecutor

import evallib as lib

PROMPT = """Пользователь попросил «очеловечить» текст: сделать его живым и естественным, как написал бы грамотный человек для той же цели, и сохранить смысл и все факты. Ниже исходный текст и {n} вариантов правки от разных редакторов. Порядок вариантов случайный.

Оцени каждый вариант по трём вопросам.
1. Факты и смысл. Сравни с исходником. Ошибка: потеряно или изменено число, дата, срок, время, сумма, имя, название, адрес, ссылка, условие, ограничение, отрицание или оговорка («около», «до», «только»); перепутано, кто что сделал или получил; добавлено утверждение, которого нет в исходнике (пример, цифра, обещание, совет, вывод). Не считай ошибкой удаление пустых фраз, повторов, эмодзи, хэштегов, обращений, служебных реплик чат-бота («Конечно! Вот…», «Если хотите, могу…») советов чат-бота самому пользователю, которые не входят в текст для отправки («Совет: перед отправкой добавьте…»), а также удаление мусора вставки из чата: хвостов utm_source в ссылках, меток contentReference, невидимых символов.
2. Живость. Читается ли вариант как текст, написанный живым грамотным человеком для этого жанра? Остались ли штампы нейросети: канцелярит, пустые подводки, «не просто X, а Y», раздутые эпитеты, тройки по шаблону, концовки-лозунги, жирный и эмодзи по шаблону, неестественная бодрость? Не появилась ли новая неестественность: панибратство, рубленые фразы, выдуманные эмоции?
3. Русский язык: грамматика, пунктуация (тире и кавычки по правилам русского языка), стиль.

Если исходник уже хороший человеческий текст, закон или официальный документ, лучший вариант тот, что бережно оставил его почти без изменений.

Затем отранжируй все варианты от лучшего к худшему по главному вопросу: какой из них ты бы отправил или опубликовал с наименьшей доработкой. Вариант с серьёзной ошибкой в фактах не может стоять выше варианта без таких ошибок.

Пиши коротко: в каждом списке не больше трёх пунктов по нескольку слов. Ответ — только JSON такого вида:
{{"candidates": {{"A": {{"fact_errors": ["..."], "ai_traces": ["..."], "language_errors": ["..."], "send_as_is": 7}}}}, "ranking": ["A", "B"], "comment": "одна фраза"}}
где send_as_is — от 1 до 10: насколько вариант готов к отправке без правок.

<исходник>
{source}
</исходник>

{candidates}"""


def build(tid: str, outputs: dict, judge: str, rnd: int):
    names = sorted(outputs)
    rng = random.Random("%s|%s|%d" % (tid, judge, rnd))
    rng.shuffle(names)
    labels = string.ascii_uppercase[:len(names)]
    key = dict(zip(labels, names))
    block = "\n\n".join('<вариант id="%s">\n%s\n</вариант>' % (lab, outputs[name].strip()) for lab, name in key.items())
    return block, key


def parse(text: str):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    raw = m.group()
    for attempt in (raw, re.sub(r",\s*([}\]])", r"\1", raw)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    # One vote per judge in report.py; "model=N" gives that judge N passes in different orders.
    ap.add_argument("--judges", default="google/gemini-4-argon=2,moonshotai/kimi-k3,meta/muse-spark-1.3")
    ap.add_argument("--rounds", type=int, default=1, help="passes for judges without =N")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--texts", default="")
    ap.add_argument("--systems", default="", help="only these systems (default: all with outputs)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="judgments.jsonl")
    args = ap.parse_args()

    run_dir = lib.EVAL_DIR / "results" / args.run
    out_dir = run_dir / "outputs"
    systems = sorted(p.name for p in out_dir.iterdir() if p.is_dir())
    if args.systems:
        systems = [s for s in systems if s in args.systems.split(",")]
    ids = sorted({p.stem for s in systems for p in (out_dir / s).glob("*.txt")})
    if args.texts:
        ids = [i for i in ids if i in args.texts.split(",")]
    log = run_dir / args.out
    done = set()
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("ranking"):
                # The candidate set is part of the identity: a pass with other systems is not reused.
                done.add((row["id"], row["judge"], row["round"], tuple(sorted(row["key"].values()))))

    jobs = []
    for tid in ids:
        outputs = {s: lib.read_text(out_dir / s / (tid + ".txt")) for s in systems if (out_dir / s / (tid + ".txt")).exists()}
        if len(outputs) < len(systems):
            print("skip %s: outputs missing for %s" % (tid, sorted(set(systems) - set(outputs))))
            continue
        source = lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (tid + ".txt"))
        for spec in args.judges.split(","):
            judge, _, n = spec.partition("=")
            for rnd in range(int(n) if n else args.rounds):
                if (tid, judge, rnd, tuple(sorted(outputs))) not in done:
                    jobs.append((tid, judge, rnd, source, outputs))

    def work(job):
        tid, judge, rnd, source, outputs = job
        block, key = build(tid, outputs, judge, rnd)
        prompt = PROMPT.format(n=len(key), source=source.strip(), candidates=block)
        row = {"id": tid, "judge": judge, "round": rnd, "key": key}
        try:
            msg, usage = lib.chat(judge, [{"role": "user", "content": prompt}], max_tokens=12000,
                                  effort=args.effort, tag="judge")
            data = parse(msg.get("content"))
            row["cost"] = usage.get("cost")
            if not data or "ranking" not in data:
                row["error"] = "unparsed: " + (msg.get("content") or "")[:300]
                return row
            ranking = [lab for lab in data["ranking"] if lab in key]
            if sorted(ranking) != sorted(key):
                row["error"] = "bad ranking %s" % data["ranking"]
                return row
            row["ranking"] = [key[lab] for lab in ranking]
            row["candidates"] = {key[lab]: v for lab, v in (data.get("candidates") or {}).items() if lab in key}
            row["comment"] = data.get("comment", "")
        except lib.BudgetExceeded:
            raise
        except Exception as exc:
            row["error"] = repr(exc)[:300]
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(work, jobs):
            with open(log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(row["id"], row["judge"].split("/")[-1], row["round"],
                  " > ".join(row.get("ranking", [])) or "ERROR " + row.get("error", ""), "$%.4f" % float(row.get("cost") or 0))
    print("spend so far $%.4f" % lib.ledger().data["total"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
