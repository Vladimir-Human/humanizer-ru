# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
"""Текстовый слой A: снятие невидимых символов по маркерам проекта.

Использует ровно те же выражения, что и детектор (check_markers):
A.7 zero_width + invisible_layout. Снятие — детерминированное и
проверяемое повторным прогоном детектора.
"""
import re

_MARKER_CASES = {}
try:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from check_markers import CASES as _MARKER_CASES
except Exception:
    pass

_RX = None
_BUILT = False


def layer_a_rx():
    global _RX, _BUILT
    if not _BUILT:
        _BUILT = True
        parts = []
        for name in ("zero_width", "invisible_layout"):
            if name in _MARKER_CASES:
                parts.append("(?:" + _MARKER_CASES[name][0] + ")")
        _RX = re.compile("|".join(parts)) if parts else None
    return _RX


DETECTOR_OK = _MARKER_CASES != {}


def clean_text_layer(text):
    rx = layer_a_rx()
    if rx is None:
        return text, 0
    cleaned, n = rx.subn("", text)
    return cleaned, n
