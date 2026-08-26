#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт паритета «снятие ↔ детектор».

Проверяет, что слой снятия (scripts/filemarks/text_layer.py) не разошёлся
с детектором (scripts/check_markers.py): семейство «невидимых» кейсов
INVISIBLE_FAMILY обязано ровно совпадать с LAYER_A_CASES, а MARKUP_CASES
обязаны ссылаться только на существующие кейсы CASES. Мотивация: дефект
класса I.8 (детектор знает PUA-разделители, а слой снятия их не снимал)
появился именно потому, что паритета никто не проверял.

Запуск из корня репозитория:
    python3 scripts/check_removal_parity.py            # проверка
    python3 scripts/check_removal_parity.py --selftest # самопроверка

Коды: 0 — паритет соблюдён; 1 — расхождение; 2 — детектор недоступен.
Только стандартная библиотека.
"""
import importlib.util
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
FILEMARKS = os.path.join(HERE, "filemarks")
ROOT = os.path.dirname(HERE)


def _load_text_layer():
    sys.path.insert(0, FILEMARKS)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, HERE)
    spec = importlib.util.spec_from_file_location(
        "_parity_text_layer", os.path.join(FILEMARKS, "text_layer.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check():
    module = _load_text_layer()
    if not module.DETECTOR_OK:
        print("детектор check_markers недоступен: паритет не проверяется",
              file=sys.stderr)
        return 2
    errors = module.removal_parity_errors()
    for e in errors:
        print("[FAIL] %s" % e)
    if errors:
        print("Итог: расхождений снятие↔детектор: %d" % len(errors))
        return 1
    print("OK паритет снятие↔детектор: LAYER_A_CASES=%s, MARKUP_CASES=%d"
          % (",".join(sorted(module.LAYER_A_CASES)), len(module.MARKUP_CASES)))
    return 0


def selftest():
    module = _load_text_layer()
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    case("чистый паритет", module.removal_parity_errors() == [])
    saved = list(module.LAYER_A_CASES)
    saved_markup = dict(module.MARKUP_CASES)
    try:
        module.LAYER_A_CASES = ("zero_width", "invisible_layout")  # дрейф: PUA выпали
        case("дрейф LAYER_A_CASES виден",
             any("не в LAYER_A_CASES" in e or "!=" in e
                 for e in module.removal_parity_errors()))
        module.LAYER_A_CASES = tuple(saved) + ("несуществующий_кейс",)
        case("лишний кейс снятия виден",
             any("отсутствует в CASES" in e for e in module.removal_parity_errors()))
        module.LAYER_A_CASES = tuple(saved)
        module.MARKUP_CASES = {"фантомный_кейс": r"x"}
        case("MARKUP на несуществующий кейс виден",
             any("MARKUP_CASES" in e for e in module.removal_parity_errors()))
    finally:
        module.LAYER_A_CASES = tuple(saved)
        module.MARKUP_CASES = saved_markup
    print("Самопроверка: %d/%d" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    return check()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))