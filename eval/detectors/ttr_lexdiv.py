#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ttr_lexdiv.py — лексическое разнообразие (TTR) как stdlib-прокси (H6).

Второй разнотипный прокси оси «дельта детектируемости до/после»
(аудит 2026-08-25): чистая стандартная библиотека, без модели,
без сети, без собственного регэксп-слоя маркеров. Владелец запретил
локальную модель (Ollama) — прокси обязан работать без неё.

Идея: живой текст лексически разнообразнее машинного (у моделей
переспективные клише и повторяющаяся лексика). TTR = типы/токены;
скор ИИ-подобности убывает с ростом TTR.

Калибровка (нейтральный корпус eval/manifest.v1.json, 2026-08-25):
  AI (11 валидных из 12):     TTR 0.682–0.852, среднее 0.758;
  human (8 валидных из 11):   TTR 0.753–0.958, среднее 0.889;
  якоря LO=0.60, HI=0.86 подобраны по корпусу: FP human = 0/11
  (максимум на человеческом тексте — it-notation 0.411 < порога 0.5).
Направление (27 AI-пар четырёх прогонов): TTR растёт после перезаписи
скиллом в 15/17 пар («после» менее ИИ-подобен); на 14/14 человеческих
пар не ухудшается. Отрицательные альтернативы (compression-ratio zlib,
rep3/rep4, CV длины предложений, CV длины слов) отбракованы измерением —
см. research/calibration/proxy-selection-2026-08-25.md.

Границы честности (уровень O, как у всех порогов чужой калибровки):
  - это НЕ классификатор авторства и не вердикт; прокси — относительная
    метрика до/после в рамках одной даты;
  - якоря калиброваны на одном корпусе (12 AI + 11 human) — при смене
    домена возможен дрейф, пороги не гейт;
  - guard: тексты короче MIN_TOKENS=20 токенов не оцениваются (None);
    в корпусе это 3 human, 1 AI и оба boundary (короткие фрагменты).

Контракт — как у всех детекторов пакета (см. base.py): score() → 0..1
или None (fail-closed), исключений наружу нет.
"""
from __future__ import annotations

import re

from .base import Detector

_WORD = re.compile(r"[а-яА-ЯёЁa-zA-Z\d-]+")

#: Якоря калибровки на eval/manifest.v1.json (2026-08-25), уровень O.
TTR_LO = 0.60
TTR_HI = 0.86
#: Тексты короче не оцениваются: TTR на 5–19 токенах не устойчив.
MIN_TOKENS = 20


class TTRLexDivDetector(Detector):
    """TTR-прокси: скор ИИ-подобности = (HI - ttr) / (HI - LO), зажатый в 0..1."""

    name = "ttr_lexdiv"

    def available(self) -> bool:
        """Чистый stdlib — детерминированно доступен всегда."""
        return True

    def model_name(self) -> str | None:
        return "stdlib-ttr-v1"

    def model_version(self) -> str | None:
        return "calibrated-2026-08-25"

    def score(self, text: str) -> float | None:
        """0..1 (меньше TTR — выше скор) или None при guard/сбое."""
        try:
            tokens = _WORD.findall(text.lower())
            if len(tokens) < MIN_TOKENS:
                return None
            ttr = len(set(tokens)) / len(tokens)
            value = (TTR_HI - ttr) / (TTR_HI - TTR_LO)
            return max(0.0, min(1.0, value))
        except Exception:  # noqa: BLE001 — контракт: сбой = None, не исключение
            return None