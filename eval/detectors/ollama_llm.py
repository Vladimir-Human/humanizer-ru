#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ollama_llm.py — детектор AI-текста на локальной Ollama (LLM-рубрика).

Порт приёмов из ilyautov/humanizer-ru (eval/detectors/ollama_llm.py), MIT.
Атрибуция: рубрика признаков машинной генерации и логика нормализации
вероятности (0..1, допуск 0..100) перенесены из проекта
https://github.com/ilyautov/humanizer-ru (© ilyautov, MIT License).
Адаптация: чистый stdlib через _ollama (urllib, без requests), вызов /api/chat
с options.think:false, модель из HUMANIZER_DETECT_MODEL, ≥27b обязательна
(4b доказано слепа — см. аудит 2026-08-25).

Идея: локальная LLM оценивает вероятность 0..1, что русский текст
машинно-сгенерирован, по чётким признакам нейросетевого стиля. Без облачных
ключей и сети наружу — нужен только живой демон Ollama.

Доступность = _ollama.available(). Любая ошибка вызова -> score() = None
(fail-closed): crashed детектор не выдаёт молчаливый фиктивный скор.

Env:
  OLLAMA_HOST            — база API (по умолчанию http://127.0.0.1:11434).
  HUMANIZER_DETECT_MODEL — чат-модель (по умолчанию qwen3.8-27b-unc).

Модель ≥27b обязательна: маленькие (напр. 4b) на человеческом корпусе
безразборчиво ставят ~0.85 всем текстам и слепы (задокументировано у ilyautov,
воспроизведено в аудит 2026-08-25). Детектор работает и с другими, но
отчёт честно несёт имя и версию модели.
"""
from __future__ import annotations

import os

from .base import Detector
from . import _ollama

# Рубрика признаков AI-текста на русском. Просим строго число + причину в JSON.
_PROMPT = """\
Ты — эксперт по выявлению машинно-сгенерированного русского текста.
Оцени вероятность от 0.0 до 1.0, что приведённый ниже текст написан нейросетью
(а не живым человеком).

Признаки, повышающие вероятность AI (0.0 = явно человек, 1.0 = явно нейросеть):
- высокая предсказуемость, низкая «перплексия» (текст течёт слишком гладко);
- ровный ритм: предложения примерно одной длины, нет всплесков (низкая burstiness);
- канцелярит и отглагольные существительные («осуществление», «реализация»);
- кальки и штампы («является», «в современном мире», «стоит отметить»);
- длинные тире вместо естественной пунктуации;
- равномерная плотность мысли, отсутствие живых интонаций и шероховатостей;
- параллелизмы «не просто X, а Y», раздувание, ложные диапазоны «от X до Y».

Текст:
---
{text}
---

Верни JSON ровно такой структуры:
{{"ai_probability": <число 0.0..1.0>, "reason": "<кратко по-русски>"}}"""


def detect_model() -> str:
    """Чат-модель из env; дефолт — qwen3.8-27b-unc (класс ≥27b, не слепа)."""
    return os.environ.get("HUMANIZER_DETECT_MODEL", "qwen3.8-27b-unc")


class OllamaLLMDetector(Detector):
    name = "ollama_llm"

    def available(self) -> bool:
        """Демон Ollama отвечает на /api/tags за короткий таймаут."""
        return _ollama.available()

    def model_name(self) -> str | None:
        return detect_model()

    def model_version(self) -> str | None:
        return _ollama.model_version(detect_model())

    def score(self, text: str) -> float | None:
        """Вероятность AI-генерации 0..1 по LLM-рубрике; None при сбое."""
        if not self.available():
            return None
        raw = _ollama.chat(detect_model(), _PROMPT.format(text=text))
        parsed = _ollama.extract_json(raw)
        if not parsed:
            return None
        val = parsed.get("ai_probability")
        if val is None:
            # Иногда модель кладёт число под другим ключом — пробуем мягко.
            for alt in ("ai_prob", "probability", "score", "ai"):
                if alt in parsed:
                    val = parsed[alt]
                    break
        try:
            prob = float(val)
        except (TypeError, ValueError):
            return None
        if prob > 1.0:
            # Модель могла вернуть 0..100 вместо 0..1 — нормализуем.
            prob = prob / 100.0
        return max(0.0, min(1.0, prob))
