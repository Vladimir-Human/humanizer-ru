#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ollama_ppl.py — ПРИБЛИЖЁННЫЙ perplexity-детектор через teacher-forcing.

Порт ilyautov/humanizer-ru (eval/detectors/ollama_ppl.py), MIT. Атрибуция:
метод teacher-forcing, семпл ≤40 позиций, top_logprobs=20, floor -15, константы
NLL_CENTER=6.0 / NLL_SCALE=2.5 перенесены из проекта
https://github.com/ilyautov/humanizer-ru (© ilyautov, MIT License).
Адаптация: чистый stdlib (razdel заменён на приближённую word-токенизацию
регулярками), вызов через _ollama (urllib, без requests/llm_backend).

Идея: AI-текст обычно предсказуемее человеческого, поэтому у языковой модели
на нём ниже перплексия. Оцениваем перплексию teacher-forcing'ом: по выбранным
позициям шлём префикс, просим 1 токен с top_logprobs=K, ищем фактический
следующий токен среди кандидатов (нет в топе -> floor -15, «модель удивлена»),
усредняем -(logprob) -> mean NLL -> sigmoid в лог-домене.

ЧУЖАЯ КАЛИБРОВКА, ПРИБЛИЖЕНИЕ ПО СЕМПЛУ, НЕ ЧЕСТНАЯ ПЕРПЛЕКСИЯ:
  - семплируем максимум ~40 позиций (Ollama серийная, дорого);
  - word-токенизация != сабворды модели, top-K усечён (ranking но не scores);
  - центры NLL_CENTER/NLL_SCALE эмпирические, взяты из ilyautov как есть;
  - поэтому НЕ входит в дефолтный --detectors, только через флаг --perplexity,
    и в LEADERBOARD/вердикты не идёт (перплексия — не судейская ось).

Env: OLLAMA_HOST, OLLAMA_PPL_MODEL (по умолчанию qwen3.8-27b-unc).
"""
from __future__ import annotations

import math
import os
import re

from .base import Detector
from . import _ollama

# Параметры семпла и нормализации (константы ilyautov как есть).
MAX_POSITIONS = 40        # максимум позиций-вызовов на текст
TOP_LOGPROBS = 20         # сколько кандидатов запрашиваем
FLOOR_LOGPROB = -15.0     # штраф, если фактический токен не попал в top-K
MIN_TOKENS = 6            # короче — оценивать нечего

# Нормализация в «AI-вероятность» через mean NLL (= log perplexity), а не через
# сырую perplexity: exp() на приближённых NLL легко улетает в миллионы и
# схлопывает сигмоиду. Работаем в лог-домене — численно устойчиво.
# ai = sigmoid((NLL_CENTER - mean_nll) / NLL_SCALE): ниже NLL (предсказуемее,
# «AI-нее») => выше вероятность. ЧУЖАЯ КАЛИБРОВКА: центры ilyautov, приближение.
NLL_CENTER = 6.0
NLL_SCALE = 2.5

# Word-токенизация: целые слова и значащая пунктуация. Это ПРИБЛИЖЕНИЕ razdel:
# разбиение не совпадает с сабвордами модели (как и razdel у ilyautov), но не
# требует внешней зависимости — детектор-харнес остаётся чистым stdlib.
_WORD_RX = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def ppl_model() -> str:
    """Перплексия-модель = чат-модель по умолчанию (class >=27b) из env."""
    return os.environ.get("OLLAMA_PPL_MODEL",
                          os.environ.get("HUMANIZER_DETECT_MODEL", "qwen3.8-27b-unc"))


def _tokens(text: str) -> list[str]:
    return _WORD_RX.findall(text)


def _sample_indices(n: int) -> list[int]:
    """Индексы позиций (1..n-1) для оценки: равномерный семпл не более MAX."""
    positions = list(range(1, n))  # позиция 0 не имеет префикса
    if len(positions) <= MAX_POSITIONS:
        return positions
    step = len(positions) / MAX_POSITIONS
    return [positions[int(i * step)] for i in range(MAX_POSITIONS)]


def _match_logprob(target: str, cands: list) -> float | None:
    """Ищет фактический токен среди top_logprobs; логпроб лучшего матча либо None.

    Токенизатор модели (BPE-сабворды) не совпадает с word-токенами, поэтому
    матчим мягко: точное совпадение, либо кандидат — непустой префикс целевого
    слова (типичный первый сабворд), без учёта регистра и ведущего пробела."""
    tgt = target.strip().lower()
    best = None
    for c in cands:
        if not isinstance(c, dict):
            continue
        ctok = str(c.get("token", "")).strip().lower()
        if not ctok:
            continue
        if ctok == tgt or tgt.startswith(ctok) or ctok.startswith(tgt):
            lp = c.get("logprob")
            try:
                lp = float(lp)
            except (TypeError, ValueError):
                continue
            if best is None or lp > best:
                best = lp
    return best


class OllamaPPLDetector(Detector):
    name = "ollama_ppl"

    def available(self) -> bool:
        """Демон Ollama отвечает на /api/tags (перплексия включена по флагу)."""
        return _ollama.available()

    def model_name(self) -> str | None:
        return ppl_model()

    def model_version(self) -> str | None:
        return _ollama.model_version(ppl_model())

    def _mean_nll(self, text: str) -> float | None:
        """Средний negative log-likelihood по семплу (= log perplexity).

        «Сырьё» и для perplexity(), и для score(). None при недоступности,
        слишком коротком тексте или полном отсутствии данных по позициям.
        """
        if not self.available():
            return None
        toks = _tokens(text)
        if len(toks) < MIN_TOKENS:
            return None
        model = ppl_model()
        nlls: list[float] = []
        for idx in _sample_indices(len(toks)):
            prefix = " ".join(toks[:idx])
            target = toks[idx]
            resp = _ollama.generate_raw(model, prefix, num_predict=1,
                                        top_logprobs=TOP_LOGPROBS)
            logprob = FLOOR_LOGPROB
            if resp:
                lps = resp.get("logprobs")
                if isinstance(lps, list) and lps:
                    cands = lps[0].get("top_logprobs")
                    if isinstance(cands, list):
                        found = _match_logprob(target, cands)
                        if found is not None:
                            logprob = found
            nlls.append(-logprob)
        if not nlls:
            return None
        return sum(nlls) / len(nlls)

    def perplexity(self, text: str) -> float | None:
        """Приближённая perplexity = exp(mean NLL). None при недоступности."""
        mean_nll = self._mean_nll(text)
        if mean_nll is None:
            return None
        return math.exp(min(mean_nll, 50.0))

    def score(self, text: str) -> float | None:
        """Нормализованная «AI-вероятность» 0..1 (ниже perplexity => выше).

        Лог-доменная сигмоида устойчива к раздутым exp. НЕ честная перплексия:
        центры NLL_CENTER/NLL_SCALE — чужая калибровка (ilyautov), приближение
        по семплу и word-токенам."""
        mean_nll = self._mean_nll(text)
        if mean_nll is None:
            return None
        z = (NLL_CENTER - mean_nll) / NLL_SCALE
        z = max(-50.0, min(50.0, z))  # защита от переполнения exp
        ai = 1.0 / (1.0 + math.exp(-z))
        return max(0.0, min(1.0, ai))
