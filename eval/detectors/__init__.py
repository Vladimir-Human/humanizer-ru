#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пакет детекторов AI-текста для харнеса «до/после» .

Реэкспорт контракта Detector и реестра collect() (см. base.py). Все детекторы
опциональны и деградируют до available()=False / score()=None, если нет живого
демона Ollama/модели. Приближённая перплексия (ollama_ppl) намеренно НЕ входит
в дефолтный набор — включается только через include_ppl=True (флаг
--perplexity в detect_eval).

Порт архитектуры из ilyautov/humanizer-ru (eval/detectors/), MIT; атрибуция —
в docstring каждого файла.
"""
from __future__ import annotations

from .base import Detector, collect

__all__ = ["Detector", "collect"]
