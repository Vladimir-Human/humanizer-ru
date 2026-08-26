#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_ollama.py — минимальный stdlib-клиент локальной Ollama для детекторов.

Порт приёмов из ilyautov/humanizer-ru (eval/llm_backend.py), MIT. Атрибуция:
структура вызовов /api/tags, /api/chat, /api/generate и робастный парсинг JSON
перенесены из проекта https://github.com/ilyautov/humanizer-ru (© ilyautov,
MIT License) и адаптированы под чистую стандартную библиотеку: вместо requests
используется urllib.request (никаких внешних зависимостей — детектор-харнес
живёт без установки пакетов, в том числе в CI).

Контракт Ollama (проверен вживую):
  GET  /api/tags            — список моделей (проверка живости демона).
  POST /api/chat            — {"message": {"content": "..."}, ...} (чат-модель).
  POST /api/generate        — {"response": str, "logprobs": [...]} (teacher-forcing).

Все функции fail-closed: при недоступности демона, таймауте, не-JSON или битом
поле возвращают None/False и наружу исключений НЕ пробрасывают. Потребитель
(детектор) на этом основании тоже деградирует в available()=False / score()=None.

Env:
  OLLAMA_HOST — база API без хвостового слэша (по умолчанию http://127.0.0.1:11434).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.error

# Таймауты: tags — быстрый ping живости; chat/generate — Ollama серийная.
TAGS_TIMEOUT_S = 5
GEN_TIMEOUT_S = 120

# Вырезание reasoning-тегов вида  thinking... response (qwen3 и подобные),
# если модель вернёт их вопреки options.think:false.
_THINK_RE = re.compile(r" thinking.*? response", re.DOTALL | re.IGNORECASE)


def host() -> str:
    """База Ollama API без хвостового слэша.

    Пустая строка env трактуется как «не задано»: иначе OLLAMA_HOST="" дала бы
    относительный URL "/api/tags" и молча отключила бы все детекторы."""
    raw = os.environ.get("OLLAMA_HOST", "").strip()
    return (raw or "http://127.0.0.1:11434").rstrip("/")


def _call(method: str, path: str, payload: dict | None = None,
          timeout: int = GEN_TIMEOUT_S) -> str | None:
    """Низкоуровневый HTTP-вызов. Возвращает сырое тело ответа либо None.

    Ошибки сети/JSON/HTTP не пробрасываются: None — сигнал недоступности.
    """
    url = host() + path
    req = urllib.request.Request(url, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(payload).encode("utf-8")
    else:
        data = None
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _json(text: str | None) -> dict | None:
    """Разобрать тело как JSON-объект; None при неудаче."""
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------ API

def available() -> bool:
    """True, если демон Ollama отвечает на /api/tags за короткий таймаут."""
    return _call("GET", "/api/tags", timeout=TAGS_TIMEOUT_S) is not None


def list_models() -> list[dict]:
    """Список моделей из /api/tags: [{name, model, digest}]. Пусто при сбое."""
    raw = _call("GET", "/api/tags", timeout=TAGS_TIMEOUT_S)
    data = _json(raw)
    if not data:
        return []
    out = []
    for m in data.get("models", []):
        if not isinstance(m, dict):
            continue
        out.append({
            "name": m.get("name", ""),
            "model": m.get("model", ""),
            "digest": m.get("digest", ""),
        })
    return out


def model_version(model_name: str) -> str | None:
    """Версия модели = короткий слепок digest из /api/tags, если он найден.

    Имя в /api/tags может нести суффикс тега (qwen3.8-27b-unc:latest), поэтому
    сопоставление терпимо к ":TAG". Модель может быть не загружена/не в списке —
    тогда версия неизвестна (None), но детектор всё равно работоспособен. None
    не роняет отчёт: detect_eval пишет версию как «n/a», когда её нет."""
    if not model_name:
        return None
    wanted = model_name.split(":", 1)[0].lower()
    for m in list_models():
        tag = (m["name"] or "").split(":", 1)[0].lower()
        if tag == wanted and m["digest"]:
            return m["digest"][:12]
    return None


def strip_think(text: str) -> str:
    """Убирает reasoning-теги и схлопывает пробелы по краям."""
    return _THINK_RE.sub("", text).strip()


def extract_json(raw: str | None) -> dict | None:
    """Достаёт первый JSON-объект из ответа модели; None при неудаче.

    Снимает ```json-ограду, вырезает think-теги, затем ищет первую
    сбалансированную {...}. Робастно к мусору до/после JSON."""
    if not raw:
        return None
    raw = strip_think(raw).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(raw)):
            ch = raw[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = raw[start:i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
        start = raw.find("{", start + 1)
    return None


def chat(model: str, prompt: str, *, timeout: int = GEN_TIMEOUT_S) -> str | None:
    """Один чат-ответ (content) модели; None при недоступности/сбое.

    options.think:false явно отключает reasoning-режим — модели qwen-семейства
    не должны оборачивать ответ в  thinking... response."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"think": False},
    }
    raw = _call("POST", "/api/chat", payload, timeout=timeout)
    data = _json(raw)
    if not data:
        return None
    msg = data.get("message")
    if not isinstance(msg, dict):
        return None
    content = msg.get("content")
    return content if isinstance(content, str) else None


def generate_raw(model: str, prompt: str, *,
                 num_predict: int = 1, top_logprobs: int = 20,
                 timeout: int = GEN_TIMEOUT_S) -> dict | None:
    """Сырой ответ /api/generate с logprobs для сгенерированных токенов.

    Используется perplexity-детектором (teacher-forcing): нужны поля response,
    logprobs. None при ошибке. top_logprobs поддерживается не всеми моделями —
    вызывающий обрабатывает отсутствие logprobs как неизвестность (floor)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.0},
        "logprobs": True,
        "top_logprobs": top_logprobs,
    }
    raw = _call("POST", "/api/generate", payload, timeout=timeout)
    return _json(raw)
