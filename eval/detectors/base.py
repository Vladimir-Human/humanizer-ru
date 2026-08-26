#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base.py — базовый контракт детектора AI-текста и реестр доступных.

Порт архитектуры из ilyautov/humanizer-ru (eval/detectors/base.py), MIT.
Атрибуция: контракт «Detector», идея реестра и graceful-деградации перенесены
из проекта https://github.com/ilyautov/humanizer-ru (© ilyautov, MIT License).
Адаптация: методы available()/score() (не свойства) и collect() в этом файле.

Детектор — адаптер над внешним сервисом или локальной моделью (Ollama). Все
они опциональны: если нет сети/модели/ключа, детектор сообщает available()=False
и score()=None — наружу исключения не пробрасываются, метрики не страдают.

Контракт:
    available() -> bool              доступен ли детектор сейчас;
    score(text)  -> float | None     вероятность AI-генерации 0..1; None при
                                     недоступности или сбое (fail-closed).

Идемпотентность score(): повторный вызов на том же тексте может дать иной
числовой результат (LLM-детектор не детерминирован), поэтому отчёт считает
агрегаты по фактическим значениям, а не по детерминированной модели.

Graceful-деградация: collect() возвращает только доступные детекторы; ноль
доступных — НЕ ошибка, а пустой список с явным сообщением (см. detect_eval):
detect_eval в этом случае отказывается кодом 2 и не создаёт пустой отчёт.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Detector(ABC):
    """Абстрактный детектор AI-текста: вероятность машинной генерации 0..1."""

    #: короткое имя для отчёта (например "ollama_llm")
    name: str = "detector"

    @abstractmethod
    def available(self) -> bool:
        """True, если детектор реально может работать сейчас.

        Сюда входят все проверки внешних ресурсов: жив ли демон Ollama, есть ли
        модель/ключ/пакет. Ложь = снаружи вызванный score() обязан вернуть None."""

    @abstractmethod
    def score(self, text: str) -> float | None:
        """Вероятность AI-генерации 0..1. None, если недоступен или упал.

        Любой сбой (недоступность, таймаут, битый JSON, нечисловой ответ)
        возвращает None, а не бросает исключение и не подставляет фиктивный скор."""

    # --- отчётность (не входит в базовый контракт, но нужна detect_eval) ---

    def model_name(self) -> str | None:
        """Имя модели для отчёта; None, если детектор модель не раскрывает."""
        return None

    def model_version(self) -> str | None:
        """Версия модели (слепок digest из /api/tags); None, если не известна."""
        return None

    def describe(self) -> dict:
        """Информация для секции detector отчёта: {name, model, version}."""
        return {"name": self.name,
                "model": self.model_name(),
                "version": self.model_version()}

    def __repr__(self) -> str:  # pragma: no cover — косметика
        state = "доступен" if self.available() else "недоступен"
        return "<Detector %s: %s>" % (self.name, state)


def _known() -> list[Detector]:
    """Все известные детекторы в рабочем порядке (импорт ленив, чтобы пакет
    detectors импортировался без сети и без требований на конкретные модели)."""
    from .ollama_llm import OllamaLLMDetector
    from .ollama_ppl import OllamaPPLDetector
    from .ttr_lexdiv import TTRLexDivDetector
    # ttr_lexdiv — stdlib, доступен всегда (второй прокси H6); в дефолт
    # detect_eval не входит — вызывается явно (--detectors ttr).
    return [OllamaLLMDetector(), OllamaPPLDetector(), TTRLexDivDetector()]


def collect(include_ppl: bool = False) -> list[Detector]:
    """Реестр: только реально доступные детекторы (graceful-деградация).

    По умолчанию включает LLM-детектор (демон Ollama жив). Приближённая
    перплексия (ollama_ppl) — дорогая и грубая, поэтому включается только явно
    через include_ppl=True (флаг --perplexity в detect_eval), как и в исходнике.

    Ноль доступных — пустой список, а не ошибка: detect_eval сам решает, как
    поступить (fail-closed кодом 2 без пустого отчёта)."""
    return [d for d in _known() if d.available() and (include_ppl or d.name != "ollama_ppl")]
