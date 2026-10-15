#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Shared helpers for the blind comparison: chat API client (fal OpenRouter router),
#          spend ledger with a hard budget cap, JSON/IO helpers.
# SCOPE: eval/ scripts only; never imported by the skill.
# DEPENDS: Python 3.9+ stdlib; env FAL_KEY (never printed or written).
# LINKS: M-EVAL-LIB; DF-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# chat: one chat completion with retries; returns (message, usage) and books the cost.
# Ledger: reads/writes eval/.cache/spend.json, refuses calls past the cap.
# read_json / write_json / read_text / write_text: UTF-8 file helpers.
# END_MODULE_MAP
from __future__ import annotations

import json
import os
import sys
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


class BudgetExceeded(RuntimeError):
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


# START_CONTRACT: chat
# PURPOSE: One OpenAI-compatible chat completion through fal's OpenRouter router.
# INPUTS: model id, messages, optional tools, max_tokens, temperature, reasoning effort, tag.
# OUTPUTS: (assistant message dict, usage dict with cost).
# SIDE_EFFECTS: network call; books usage.cost in the ledger under tag.
# END_CONTRACT: chat
def chat(model: str, messages: list, *, tools=None, max_tokens: int = 4000,
         temperature=None, effort=None, tag: str = "misc", retries: int = 4):
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
