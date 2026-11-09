#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Shared helpers for the blind comparison: chat API client (fal OpenRouter router, or
#          an owner-approved free route through the local DSH bridge for "dsh:" models),
#          spend ledger with a hard budget cap, JSON/IO helpers.
# SCOPE: eval/ scripts only; never imported by the skill.
# DEPENDS: Python 3.9+ stdlib; env FAL_KEY (never printed or written); for "dsh:" models node and
#          ~/.claude/skills/dsh-bridge/dsh-task.mjs.
# LINKS: M-EVAL-LIB; DF-EVAL; R-EVAL-DSH.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# chat: one chat completion with retries; returns (message, usage) and books the cost.
# dsh_task_text / dsh_answer: messages -> one bridge task; bridge JSON -> (message, usage).
# Ledger: reads/writes eval/.cache/spend.json, refuses calls past the cap.
# read_json / write_json / read_text / write_text: UTF-8 file helpers.
# split_notes: answer -> (edited text, notes after the last '---'); fact checks use the text.
# END_MODULE_MAP
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVAL_DIR / ".cache"
LEDGER = CACHE_DIR / "spend.json"
URL = "https://fal.run/openrouter/router/openai/v1/chat/completions"
BUDGET_USD = float(os.environ.get("EVAL_BUDGET_USD", "15"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, data) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# START_CONTRACT: split_notes
# PURPOSE: The edited text of an answer without the notes to the author (R-NOTES-NOT-TEXT).
# INPUTS: answer; source (the text that was edited, "" when unknown).
# OUTPUTS: (text, notes); notes follow the last line that is exactly "---".
# RULES: the tail after the answer's last "---" is notes when it talks about the edit, not the
#        topic: at most NOTE_MAX_CHARS, an editing word or a question mark outside quotes, and
#        under half of its word stems (outside «quotes») found in the source. Counting "---" lines
#        does not decide it: sources carry their own sections and chat wrappers, and an edit may
#        drop, keep or add separators. Calibrated 09.11.2026 on all 320 saved eval answers with a
#        "---" (1841 answers): 19 notes cut, 301 text sections kept, no disagreement with a
#        reading by eye; the old count-and-similarity rule cut a text's closing paragraph and
#        kept notes that open with prose (cross-review F1-F3).
#        Fact checks compare source with text: «Три вопроса» in the notes is not an added fact.
# END_CONTRACT: split_notes
NOTE_MAX_CHARS = 1200
NOTE_QUOTE_RX = re.compile(r"«[^»\n]*»|\"[^\"\n]*\"|“[^”\n]*”")
NOTE_EDIT_RX = re.compile(
    r"(?i)\?|\b(?:убра|убир|замен|сократ|переп|правк|правил|исправ|оставил|оставлен|остал|не трога|"
    r"вопрос|сверк|уточн|знак|обёрт|оберт|заметк|провер|добав|удал|заглушк|плейсхолдер|текст|"
    r"абзац|заголов|сня[лв]|штамп|канцел|изменен|изменил)")
NOTE_WORD_RX = re.compile(r"[A-Za-zА-Яа-яЁё]{4,}")


def _stems(text: str) -> set:
    return {w.lower().replace("ё", "е")[:5] for w in NOTE_WORD_RX.findall(text)}


def split_notes(answer: str, source: str = "") -> tuple:
    lines = answer.rstrip().split("\n")
    rules = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if not rules:
        return answer.strip(), ""
    text, notes = "\n".join(lines[:rules[-1]]).strip(), "\n".join(lines[rules[-1] + 1:]).strip()
    if notes and len(notes) <= NOTE_MAX_CHARS:
        bare = NOTE_QUOTE_RX.sub(" ", notes)
        if NOTE_EDIT_RX.search(bare):
            stems = _stems(bare)
            if not stems or len(stems & _stems(source)) / len(stems) < 0.5:
                return text, notes
    return answer.strip(), ""


class BudgetExceeded(RuntimeError):
    pass


# A plan quota does not come back in minutes (MiniMax Token Plan answers 429 «已达到 Token Plan 用量上限»).
# The first such answer closes the route for this process: no retries, and every later call fails
# at once without reaching the provider. 2026-11-09: a run kept retrying 24 calls 3 times each after
# the MiniMax quota had ended. A per-minute rate limit («token rate limit» on Sol) is not a quota.
QUOTA_RX = re.compile(r"Token Plan|用量上限|insufficient_quota|exceeded your current quota|usage limit|plan quota", re.I)
EXHAUSTED: set = set()


class QuotaExhausted(BudgetExceeded):
    pass


# START_CONTRACT: Ledger
# PURPOSE: Keep the running total of API spend across all eval scripts and stop at the cap.
# INPUTS: cost in USD from the API usage block.
# OUTPUTS: total so far; raises BudgetExceeded before a call when total >= cap.
# SIDE_EFFECTS: writes eval/.cache/spend.json.
# END_CONTRACT: Ledger
class Ledger:
    """One process, many threads: a lock serialises read-modify-write; the file is replaced
    atomically so a reader never sees half a JSON. Scripts that spend run one at a time."""

    def __init__(self, cap: float = BUDGET_USD):
        self.cap = cap
        self.lock = threading.Lock()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.data = read_json(LEDGER) if LEDGER.exists() else {"total": 0.0, "by_tag": {}}

    def check(self) -> None:
        with self.lock:
            total = self.data["total"]
        if total >= self.cap:
            raise BudgetExceeded("budget cap $%.2f reached (spent $%.4f)" % (self.cap, total))

    def add(self, tag: str, cost: float) -> None:
        with self.lock:
            if LEDGER.exists():
                self.data = read_json(LEDGER)
            self.data["total"] = round(self.data["total"] + cost, 6)
            self.data["by_tag"][tag] = round(self.data["by_tag"].get(tag, 0.0) + cost, 6)
            tmp = LEDGER.with_suffix(".tmp")
            write_json(tmp, self.data)
            os.replace(tmp, LEDGER)


_LEDGER = None


def ledger() -> Ledger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = Ledger()
    return _LEDGER


# START_BLOCK_DSH
# Routes the owner approved as free on 2026-10-21 ("Sol and MiniMax are free now"). The bridge
# still prices them at list rates: that number is kept in usage["listed_cost"], the ledger books 0.
# Any other bridge route could be paid, so it is refused before anything runs.
DSH_PREFIX = "dsh:"
DSH_TASK = Path.home() / ".claude" / "skills" / "dsh-bridge" / "dsh-task.mjs"
DSH_FREE = frozenset({"agentrouter-astra/gpt-6.1-sol", "minimax/MiniMax-M3.1-Flash"})
# The DSH agent is a coding agent with file tools; the eval needs a plain reply.
DSH_RULES = ("Answer in your reply only: do not create, read or change files and do not run commands. "
             "Everything you need is below.")


def dsh_task_text(messages: list) -> str:
    """System instructions first, then the user's messages, under the bridge rules."""
    def text(content):
        return content if isinstance(content, str) else "".join(c.get("text", "") for c in content)
    roles = {m["role"] for m in messages}
    if roles - {"system", "user"}:
        raise ValueError("the dsh route takes system and user messages only")
    parts = [DSH_RULES] + [text(m["content"]) for m in messages if m["role"] == "system"]
    parts += [text(m["content"]) for m in messages if m["role"] == "user"]
    return "\n\n".join(parts)


def dsh_answer(report: dict):
    """Bridge --json report -> (message, usage). A failed run or an empty answer raises."""
    if not report.get("ok"):
        why = report.get("errors") or report.get("stderrTail") or [report.get("error") or report.get("endReason")]
        raise RuntimeError("dsh run failed: %s %s" % (report.get("failKind"), "; ".join(map(str, why))[:300]))
    text = report.get("answer") or ""
    if report.get("answerTruncated") and report.get("answerPath"):
        text = read_text(report["answerPath"])
    if not text.strip():
        raise RuntimeError("dsh run gave an empty answer: %s" % report.get("dir"))
    tokens = report.get("tokens") or {}
    usage = {"cost": 0.0, "listed_cost": report.get("cost"), "prompt_tokens": tokens.get("in"),
             "completion_tokens": tokens.get("out"), "seconds": report.get("seconds"), "dsh_run": report.get("dir")}
    return {"content": text}, usage


def _dsh_chat(model: str, messages: list, effort, tag: str, retries: int = 3):
    ref = model[len(DSH_PREFIX):]
    if ref not in DSH_FREE:
        raise SystemExit("%s is not an approved free DSH route (%s)" % (ref, ", ".join(sorted(DSH_FREE))))
    if ref in EXHAUSTED:
        raise QuotaExhausted("%s: the plan quota ended earlier in this run; nothing sent" % ref)
    work = CACHE_DIR / "dsh"
    (work / "cwd").mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", dir=work, delete=False) as fh:
        fh.write(dsh_task_text(messages))
    # --no-fallback: when the free route fails the bridge must not switch to a paid fal model.
    # --bare (R-BARE-EXECUTOR): no installed skills and no AGENTS.md / CLAUDE.md in the agent's context.
    # Without it the agent loaded the installed humanizer-ru by itself: 61 of 63 runs of the plain
    # request on 2026-11-05 were the skill, not the plain request.
    cmd = ["node", str(DSH_TASK), "--model", ref, "--cwd", str(work / "cwd"), "--confirm", "--no-fallback", "--bare",
           "--max-cost", "1", "--max-chars", "100000", "--json", "--task-file", fh.name]
    if effort:
        cmd += ["--effort", effort]
    last = None
    try:
        for attempt in range(retries):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2400)
                try:
                    report = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    raise RuntimeError("dsh bridge rc=%s: %s" % (proc.returncode, (proc.stderr or proc.stdout)[-300:]))
                msg, usage = dsh_answer(report)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                # The free routes restart now and then ("Server is restarting; please retry shortly").
                last = exc
                if QUOTA_RX.search(str(exc)):
                    EXHAUSTED.add(ref)
                    print("[M-EVAL-LIB][BLOCK_DSH] %s %s: plan quota ended, route closed for this run" % (tag, ref))
                    raise QuotaExhausted("%s: plan quota ended: %s" % (ref, str(exc)[:200])) from exc
                print("[M-EVAL-LIB][BLOCK_DSH] %s %s attempt %d failed: %s" % (tag, ref, attempt + 1, str(exc)[:200]))
                time.sleep(30 * (attempt + 1))
                continue
            print("[M-EVAL-LIB][BLOCK_DSH] %s %s %ss listed $%.4f booked $0" % (tag, ref, usage["seconds"], float(usage["listed_cost"] or 0)))
            return msg, usage
    finally:
        os.unlink(fh.name)
    raise RuntimeError("dsh route %s failed %d times: %s" % (ref, retries, last))
# END_BLOCK_DSH


# START_CONTRACT: chat
# PURPOSE: One OpenAI-compatible chat completion through fal's OpenRouter router, or through the
#          DSH bridge for "dsh:<route>" models (approved free routes only, no tools).
# INPUTS: model id, messages, optional tools, max_tokens, temperature, reasoning effort, tag.
# OUTPUTS: (assistant message dict, usage dict with cost).
# SIDE_EFFECTS: network call; books usage.cost in the ledger under tag (0 for the free routes).
# END_CONTRACT: chat
def chat(model: str, messages: list, *, tools=None, max_tokens: int = 4000,
         temperature=None, effort=None, tag: str = "misc", retries: int = 4):
    if model.startswith(DSH_PREFIX):
        if tools:
            raise ValueError("the dsh route has no tool calls")
        return _dsh_chat(model, messages, effort, tag)
    key = os.environ.get("FAL_KEY")
    if not key:
        raise SystemExit("FAL_KEY is not set")
    ledger().check()
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature
    if effort:
        body["reasoning"] = {"effort": effort}
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(URL, data=data, headers={
            "Authorization": "Key " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                out = json.load(resp)
            if "choices" not in out:
                raise RuntimeError("no choices: %s" % json.dumps(out)[:300])
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = "HTTP %s %s" % (e.code, detail)
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # network, timeout, malformed reply
            last = repr(e)[:300]
        else:
            # Booking happens outside the retry block: a local ledger error must not
            # repeat a request that was already paid for.
            usage = out.get("usage") or {}
            ledger().add(tag, float(usage.get("cost") or 0.0))
            return out["choices"][0]["message"], usage
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("chat failed for %s: %s" % (model, last))
