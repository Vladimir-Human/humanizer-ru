#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detect_conj.py — детектор частоты связок (conj_density).

Признак: доля слов-связок из списка 12 среди всех слов текста (×100).
Направление: высокое значение характернее для машинного текста. Признак
разделяет человеческий и машинный текст в домене «чистая проза,
инструкции» (по измерениям прогона, числа которых живут в реестре фактов
и здесь не цитируются); в эссе порог не пройден, на веб-тексте с
артефактами неприменим. Границы обязательны в каждом выводе.

Извлечение слова в слово повторяет измерительный конвейер прогона
(content_of: снятие мета-шапки и URL; слова — только буквы).

Вывод не выносит вердикта об авторстве: значение, направление и статус
домена. Статусы домена:
  works           — instructions: признаку можно доверять в заявленных
                    границах;
  not-validated   — essay/prose: ниже порога валидации, вердикт не даётся;
  not-applicable  — web: артефакты разметки и URL вне домена признака.

Режимы:
    python3 scripts/detect_conj.py ФАЙЛ...            # человекочитаемо
    python3 scripts/detect_conj.py --json ФАЙЛ...     # машиночитаемый отчёт
    python3 scripts/detect_conj.py --genre G ФАЙЛ...  # жанр явно
    python3 scripts/detect_conj.py --gate КАТАЛОГ     # смоук-гейт на фикстурах
    python3 scripts/detect_conj.py --selftest         # самопроверка с негативами

Жанры: instructions, essay, prose, web, auto (по умолчанию).
Коды: 0 — успех; 2 — вход не читается. Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

CONJ = ["и", "но", "а", "однако", "хотя", "зато", "потому", "чтобы",
        "когда", "если", "что", "который"]

# Мета-шапка захвата (Вопрос/Режим/…) и URL вырезаются ДО подсчёта — ровно
# как в измерительном конвейере прогона.
META = re.compile(r"^(Режим|Вопрос|Дата|Клиент|Ответ|Модель|Запрос)\b[^\n]*:?\s*$", re.M)
URL = re.compile(
    r"(?:https?://\S+|www\.\S+|\b[\w-]+(?:\.(?:ru|com|org|io|ai|net|yandex"
    r"|wikipedia|progorod62|makfa|prochepetsk))+(?:/\S*)?)", re.I)
WORD = re.compile(r"\b[\u0410-\u042f\u0430-\u044f\u0401\u0451a-zA-Z]{1,}\b")
MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
HTML_TAG = re.compile(r"<[a-zA-Z][^>]*>")
STEP = re.compile(r"(?m)^\s*\d+[.)]\s+\S")

GENRES = ("instructions", "essay", "prose", "web")
DOMAIN_STATUS = {
    "instructions": "works",
    "essay": "not-validated",
    "prose": "not-validated",
    "web": "not-applicable",
}


def content_of(text: str) -> str:
    """Снятие мета-шапки и URL — порт из измерительного конвейера."""
    parts = re.split(r"\n\s*\n", text, maxsplit=1)
    if len(parts) == 2:
        head, rest = parts
        head_lines = [l for l in head.strip().split("\n") if l.strip()]
        if head_lines and all(META.match(l.strip()) or l.strip().endswith(":")
                              for l in head_lines[:6]):
            text = rest
    return URL.sub(" ", text)


def words_of(text: str) -> list[str]:
    return WORD.findall(text)


def conj_density(text: str) -> float:
    """Доля слов-связок среди всех слов (×100) на содержимом текста."""
    lw = [w.lower() for w in words_of(content_of(text))]
    n = len(lw) or 1
    return sum(1 for w in lw if w in CONJ) / n * 100


def classify_genre(text: str, declared: str = "auto") -> str:
    """Жанр домена. Консервативно: без явного объявления «инструкции» не
    заявляются — авто-эвристика отличает только веб (разметка/ссылки)."""
    if declared in GENRES:
        return declared
    if URL.search(text) or MD_LINK.search(text) or HTML_TAG.search(text):
        return "web"
    return "prose"


def detect(text: str, declared: str = "auto") -> dict:
    genre = classify_genre(text, declared)
    density = conj_density(text)
    return {
        "conj_density": round(density, 4),
        "words_total": len(words_of(content_of(text))),
        "genre": genre,
        "status": DOMAIN_STATUS[genre],
        "direction": "выше — характернее для машинного текста",
        "note": ("значения сравниваются только в пределах заявленного "
                 "домена; вердикт об авторстве не выносится"),
    }


# ------------------------------------------------------------------ selftest

def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    # Арифметика признака: 2 связки (если, что) из 5 слов = 40.0.
    text = "Если что пойдет не так"
    case("плотность связок считается", abs(conj_density(text) - 40.0) < 1e-9)
    case("регистр не важен", abs(conj_density("ЕСЛИ ЧТО ПОЙДЕТ НЕ ТАК") - 40.0) < 1e-9)

    # Мета-шапка не учитывается.
    wrapped = "Вопрос: как?\n\nЕсли что пойдет не так"
    case("мета-шапка снята до подсчёта",
         abs(conj_density(wrapped) - 40.0) < 1e-9)

    # URL не учитывается (список TLD — латиница, как в измерительном
    # конвейере; кириллические домены остаются в тексте).
    with_url = "Если что см. primer.ru и вот"
    d_url = conj_density(with_url)
    d_no_url = conj_density("Если что см. и вот")
    case("URL вырезан до подсчёта", abs(d_url - d_no_url) < 1e-9)

    # Пустой вход не падает.
    case("пустой вход — ноль без падения", conj_density("") == 0.0)

    # Маршрутизация доменов.
    case("жанр по умолчанию — проза", classify_genre("Просто текст.") == "prose")
    case("веб по ссылке", classify_genre("Текст [тут](http://a.ru/b)") == "web")
    case("веб по URL", classify_genre("Заходи на primer.ru сегодня") == "web")
    case("явные инструкции", classify_genre("1. Нажми.", "instructions") == "instructions")
    case("статусы доменов",
         detect("Просто текст.", "instructions")["status"] == "works"
         and detect("Просто текст.", "essay")["status"] == "not-validated"
         and detect("Ссылка [x](http://a.ru)")["status"] == "not-applicable")

    # Негатив: детектор не имеет права называться вердиктом.
    res = detect("Если что пойдет не так", "instructions")
    case("в выводе нет вердикта об авторстве",
         "автор" not in res["note"] or "не выносится" in res["note"])

    print("САМОПРОВЕРКА detect_conj: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


# --------------------------------------------------------------------- gate

def gate(paths: list[str]) -> int:
    """Смоук-гейт: на каждом файле детектор возвращает полный валидный
    ответ (отказов нет — градуированный ответ на любом входе)."""
    bad = 0
    checked = 0
    for path in paths:
        if os.path.isdir(path):
            for dirpath, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.endswith((".md", ".txt")):
                        bad += _gate_file(os.path.join(dirpath, name))
                        checked += 1
        else:
            bad += _gate_file(path)
            checked += 1
    if bad:
        print("ДЕТЕКТОР СВЯЗОК: сбоев %d (файлов проверено %d)" % (bad, checked))
        return 1
    print("ДЕТЕКТОР СВЯЗОК: градуированный ответ на %d файлах, отказов 0"
          % checked)
    return 0


def _gate_file(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc))
        return 1
    res = detect(text)
    problems = []
    if not isinstance(res.get("conj_density"), (int, float)) or res["conj_density"] < 0:
        problems.append("плотность вне диапазона")
    if res.get("status") not in ("works", "not-validated", "not-applicable"):
        problems.append("статус домена вне словаря")
    if not res.get("direction"):
        problems.append("нет направления")
    for p in problems:
        print("СБОЙ %s: %s" % (path, p))
    return 1 if problems else 0


# ---------------------------------------------------------------------- CLI

def _cyrillic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "\u0400" <= c <= "\u04ff")
    return cyr / len(letters)


def scope_note(text: str) -> str:
    """Пометка «вне области»: пустой и не-русский вход — вне домена скилла.

    Градуированный ответ остаётся непустым (контракт): плотность связок
    считается механически, но область детектора — русская проза и
    инструкции, а не произвольный текст.
    """
    if not text.strip():
        return "вне области: пустой вход"
    if _cyrillic_share(text) < 0.1:
        return "вне области: текст не на русском (область детектора — русская проза и инструкции)"
    return ""


SHORT_RU = "Проверяемая гигиена вставки из чата для русского текста"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Детектор частоты связок с границами домена. Вердикта об "
                    "авторстве не выносит никогда.",
        epilog="Репозиторий: https://github.com/Vladimir-Human/humanizer-ru\n"
               "Вход для агентов: llms.txt; машинный контракт: contract.v1.json",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*",
                    help="файлы для обработки; «-» читает stdin (UTF-8)")
    ap.add_argument("--genre", default="auto",
                    help="жанр домена: instructions|essay|prose|web|auto "
                         "(единый словарь CLI: значения счётчика признаков "
                         "уходят в автоклассификацию)")
    ap.add_argument("--json", action="store_true",
                    help="машиночитаемый отчёт")
    ap.add_argument("--gate", metavar="ПУТЬ",
                    help="режим смоук-гейта по файлам/каталогу")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка с негативными кейсами")
    ap.description = SHORT_RU + "\n\n" + (ap.description or "")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.gate:
        return gate([args.gate])
    if not args.files:
        print("нет файлов; справка: --help, самопроверка: --selftest",
              file=sys.stderr)
        return 2

    rc = 0
    report = []
    errors = []
    for path in args.files:
        try:
            if path == "-":
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
                text = sys.stdin.read()
            else:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc), file=sys.stderr)
            errors.append({"file": "<stdin>" if path == "-" else path,
                           "error": repr(exc)})
            rc = 2
            continue
        res = detect(text, args.genre)
        res = {"file": "<stdin>" if path == "-" else path, **res}
        note = scope_note(text)
        if note:
            res["status"] = "out-of-scope"
            res["scope_note"] = note
        if args.json:
            report.append(res)
        else:
            print("%s: conj_density=%.4f, слов=%d, жанр=%s, статус=%s"
                  % (path, res["conj_density"], res["words_total"],
                     res["genre"], res["status"]))
            print("  направление: %s" % res["direction"])
            print("  примечание: %s" % res["note"])
            if note:
                print("  %s" % note)
    if args.json:
        envelope = {"tool": "humanizer-detect", "schema": 1,
                    "files": report + errors}
        if rc == 2:
            envelope["error"] = "вход не читается (код 2)"
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
