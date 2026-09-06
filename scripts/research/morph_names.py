#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""morph_names.py — ИССЛЕДОВАТЕЛЬСКИЙ инструмент (вне поставляемого
продукта): сравнение имён двух текстов по леммам при наличии pymorphy3
в окружении исследователя.

Продуктовый контур humanizer_ru.facts_diff сравнивает имена
регистр-независимо и не зависит от окружения (решение 2026-09-07);
лемматизация осталась здесь как опциональное исследовательское
сравнение. Без pymorphy3 инструмент честно печатает UNAVAILABLE и
возвращает код 3 (не 0 и не 1: отсутствие зависимости — не результат
сравнения).

Запуск:
    python3 scripts/research/morph_names.py <до> <после>
    python3 scripts/research/morph_names.py --selftest
"""
import json
import sys

SCHEMA = 1
TOOL = "humanizer-research-morph-names"

try:  # окружение исследователя, не продукт
    from pymorphy3 import MorphAnalyzer as _Morph
    _MORPH = _Morph()
except Exception:  # noqa: BLE001
    _MORPH = None


def _lemma(word):
    if _MORPH is None:
        return None
    try:
        return _MORPH.parse(word)[0].normal_form
    except Exception:  # noqa: BLE001
        return word.casefold()


def _capword_names(text):
    import re
    rx = re.compile(r"(?:[А-ЯЁ][а-яё]+|[A-Z][a-z]+)")
    out = []
    for m in rx.finditer(text):
        out.append(m.group())
    return out


def compare(before, after):
    """(леммы_до, леммы_после); None, если морфология недоступна."""
    if _MORPH is None:
        return None
    return ([_lemma(w) for w in _capword_names(before)],
            [_lemma(w) for w in _capword_names(after)])


def selftest():
    fails = 0
    if _MORPH is None:
        print("UNAVAILABLE: pymorphy3 отсутствует в окружении")
        return 3
    a, b = compare("Иван Петров подтвердил", "Иван Петров подтвердил")
    ok = a == b and a and all(a)
    print("%s: идентичные тексты дают равные леммы" % ("PASS" if ok else "FAIL"))
    fails += 0 if ok else 1
    a, b = compare("Мария Соколова писала", "Мария Соколова писала")
    ok = a == ["мария", "соколова"]
    print("%s: лемма фамилии вычислена (%s)" % ("PASS" if ok else "FAIL", a))
    fails += 0 if ok else 1
    print("САМОПРОВЕРКА morph_names: %d FAIL" % fails)
    return 1 if fails else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        return selftest()
    if len(argv) != 2:
        print("usage: morph_names.py <до> <после> | --selftest",
              file=sys.stderr)
        return 2
    if _MORPH is None:
        print(json.dumps({"tool": TOOL, "schema": SCHEMA,
                          "status": "UNAVAILABLE",
                          "reason": "pymorphy3 отсутствует в окружении "
                                    "исследователя"},
                         ensure_ascii=False))
        return 3
    with open(argv[0], encoding="utf-8") as fh:
        before = fh.read()
    with open(argv[1], encoding="utf-8") as fh:
        after = fh.read()
    lemmas_before, lemmas_after = compare(before, after)
    lost = [w for w in lemmas_before if w not in lemmas_after]
    added = [w for w in lemmas_after if w not in lemmas_before]
    print(json.dumps({"tool": TOOL, "schema": SCHEMA,
                      "lost": lost, "added": added},
                     ensure_ascii=False, indent=2))
    return 0 if not lost else 1


if __name__ == "__main__":
    sys.exit(main())
