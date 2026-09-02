#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_self_attack.py — запрет самоатаки (Гудхарт): типографическая
полировка не оптимизирует признак детектора связок.

Инвариант: `conj_density(polish(x)) == conj_density(x)` на текстах, где
полировка не удаляет невидимые разделители слов (нулевая ширина, мягкий
перенос): полировка не трогает буквы и цифры, а признак считается по
словам. Если полировка когда-нибудь начнёт менять слова ради признака —
это оптимизация против собственного детектора, и гейт обязан упасть.

Ограничение (задокументировано, не дефект): извлечение слов в признаке
идёт по границам `\b`, а подчёркивание — словесный символ. Полировка,
снимая артефакты (невидимые разделители слов, `__`-пары вплотную к
буквам), меняет границы слов, и знаменатель признака может смениться;
такие файлы гейт помечает и пропускает (это снятие артефакта, а не
оптимизация). Равно и мета-шапка, обнажаемая снятием хэша: это логика
самого измерительного конвейера (мета-шапка не учитывается). На текстах
без таких артефактов инвариант обязан выполняться строго.

Режимы:
    python3 scripts/check_self_attack.py              # по фикстурам полировки
    python3 scripts/check_self_attack.py КАТАЛОГ      # по своему каталогу
    python3 scripts/check_self_attack.py --selftest   # самопроверка

Коды: 0 — инвариант цел; 1 — нарушение; 2 — ошибка входа.
Только стандартная библиотека.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join("tests", "fixtures", "polish")

# Артефакты, снятие которых меняет границы слов (\b-токенизацию): невидимые
# разделители слов и подчёркивания вплотную к буквам.
_MERGE_CHARS = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
_UNDERSCORE_EDGE = re.compile(
    r"_[\u0410-\u042f\u0430-\u044f\u0401\u0451a-zA-Z]"
    r"|[\u0410-\u042f\u0430-\u044f\u0401\u0451a-zA-Z]_")


def _load(name: str):
    path = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location("_sa_" + name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mod_polish():
    return _load("polish.py")


def _mod_conj():
    return _load("detect_conj.py")


def check_text(polish_mod, conj_mod, text: str) -> str | None:
    """Возвращает описание нарушения или None, если инвариант цел."""
    cleaned = polish_mod.polish(text)
    if conj_mod.conj_density(cleaned) != conj_mod.conj_density(text):
        return ("conj_density меняется полировкой: до=%.4f после=%.4f"
                % (conj_mod.conj_density(text), conj_mod.conj_density(cleaned)))
    return None


def check_tree(polish_mod, conj_mod, root: str) -> int:
    bad = 0
    checked = 0
    skipped = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith((".md", ".txt")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc))
                bad += 1
                continue
            if any(ch in text for ch in _MERGE_CHARS) \
                    or _UNDERSCORE_EDGE.search(text):
                print("ПРОПУСК %s: артефакты, меняющие границы слов "
                      "(снятие артефакта, не оптимизация)"
                      % os.path.relpath(path, ROOT))
                skipped += 1
                continue
            problem = check_text(polish_mod, conj_mod, text)
            if problem:
                print("НАРУШЕНИЕ %s: %s" % (os.path.relpath(path, ROOT), problem))
                bad += 1
            else:
                checked += 1
    if bad:
        print("САМОАТАКА: нарушений %d (проверено %d, пропущено по ограничению %d)"
              % (bad, checked, skipped))
        return 1
    print("САМОАТАКА: полировка не трогает признак на %d файлах "
          "(пропущено по ограничению %d)" % (checked, skipped))
    return 0


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    polish_mod = _mod_polish()
    conj_mod = _mod_conj()

    text = ("# Заголовок\n\n"
            "Если хотите, нажмите кнопку — и получите «результат»…\n"
            "**Важно:** это не меняет смысла.\n")
    case("на обычном тексте инвариант цел",
         check_text(polish_mod, conj_mod, text) is None)

    # Негатив: подмена полировки функцией, удаляющей связку, ловится.
    class _Fake:
        @staticmethod
        def polish(t):
            return t.replace("Если", "")  # удаление слова-связки
    case("удаление слова-связки ловится",
         check_text(_Fake, conj_mod, text) is not None)

    class _FakeAdd:
        @staticmethod
        def polish(t):
            return t + " однако однако"  # вставка связок
    case("вставка связок ловится",
         check_text(_FakeAdd, conj_mod, text) is not None)

    # Текст без связок: полировка ничего не меняет в признаке.
    plain = "Просто текст без единой связки тут.\n"
    case("на тексте без связок инвариант цел",
         check_text(polish_mod, conj_mod, plain) is None)

    # Дерево: чистый файл проверяется, файл с артефактами границ слов
    # помечается и пропускается (итог зелёный).
    import tempfile
    with tempfile.TemporaryDirectory(prefix="selfattack-selftest-") as td:
        with open(os.path.join(td, "clean.md"), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write("Если что нажмите кнопку.\n")
        with open(os.path.join(td, "artifact.txt"), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write("Слово__слитное и обычное.\n")
        case("чистый файл плюс файл с артефактом границ: зелёный исход",
             check_tree(polish_mod, conj_mod, td) == 0)
        with open(os.path.join(td, "clean.md"), "w", encoding="utf-8",
                  newline="") as fh:
            # ломающая «полировка»: удаляет связку
            fh.write("Если что нажмите кнопку.\n")

        class _Breaker:
            @staticmethod
            def polish(t):
                return t.replace("Если", "")
        case("дерево ловит ломающую полировку",
             check_tree(_Breaker, conj_mod, td) == 1)

    print("САМОПРОВЕРКА check_self_attack: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return selftest()
    target = args[0] if args else os.path.join(ROOT, FIXTURES)
    if not os.path.exists(target):
        print("нет пути: %s" % target, file=sys.stderr)
        return 2
    polish_mod = _mod_polish()
    conj_mod = _mod_conj()
    return check_tree(polish_mod, conj_mod, target)


if __name__ == "__main__":
    sys.exit(main())
