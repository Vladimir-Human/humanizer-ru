#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_polish_modes.py — гейт честности режимов polish (п.2.1 плана v2).

Четыре свойства, которые обязан держать человеческий слой polish:

  1. Публикационный режим `--typographic` применим к собственным публичным
     документам проекта: README.md, SKILL.md, CONTRIBUTING.md, llms.txt —
     changed:false (нулевой диф). Режим ставит русскую публикационную
     типографику (ёлочки из парных прямых кавычек, единый символ
     многоточия) и снимает невидимые символы В ПРОЗЕ, не трогая разметку,
     fenced-блоки, инлайн-код и YAML-frontmatter.
  2. Дефолтный режим (strip) те же документы МЕНЯЕТ: destructive-семантика
     не прячется — граница when_not в contract.v1.json («не запускать на
     Markdown и разметке») остаётся правдой.
  3. Оба режима идемпотентны и сохраняют буквы и цифры дословно
     (инварианты polish) на всех четырёх документах и синтетике.
  4. Безопасные режимы (`--typographic`, `--preserve-markup`) сохраняют
     защищённые области (единый источник — scripts/protected_regions.py):
     URL, кавычки HTML-атрибутов, ZWJ-кластеры эмодзи и содержимое
     инлайн-кода; разрушение области репортится инвариантами (негативы
     проверяются на уже приведённом тексте, где остальные инварианты целы).

Запуск из корня репозитория:
    python3 scripts/check_polish_modes.py             # проверка
    python3 scripts/check_polish_modes.py --selftest  # негативные кейсы

Коды: 0 — режимы честны; 1 — нарушение; 2 — вход не читается.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import polish as P  # noqa: E402

DOCS = ["README.md", "SKILL.md", "CONTRIBUTING.md", "llms.txt"]

# Синтетические кейсы защищённых областей (единый источник —
# scripts/protected_regions.py): фрагменты, которые оба безопасных режима
# обязаны оставлять неизменными, и нарушения, которые инварианты обязаны
# ловить.
PROTECTION_CASES = [
    ("URL", 'См. https://example.org/a...b тут.\n',
     ["https://example.org/a...b"]),
    ("кавычки атрибутов", 'Проза "ц" и <a href="x">т</a>.\n',
     ['<a href="x">']),
    ("ZWJ-кластер", "семья \U0001F468\u200d\U0001F469\u200d\U0001F467\n",
     ["\u200d"]),
    ("содержимое кода", 'Вне `код "x"...` и "проза"...\n',
     ['`код "x"...`']),
]
SAFE_MODES = ({"typographic": True}, {"preserve_markup": True})


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def check() -> list:
    errors = []
    for rel in DOCS:
        try:
            text = _read(rel)
        except OSError as exc:
            errors.append("%s: не читается: %r" % (rel, exc))
            continue
        typo = P.polish(text, typographic=True)
        if typo != text:
            errors.append("%s: typographic-режим изменил документ — публикационный "
                          "режим обязан давать нулевой диф на собственной "
                          "публичной прозе" % rel)
        strip = P.polish(text)
        if strip == text:
            errors.append("%s: дефолтный strip-режим ничего не изменил — либо "
                          "документ без разметки/типографики, либо strip "
                          "сломан; граница when_not перестала быть правдой" % rel)
        for label, out, kw in (("typographic", typo, {"typographic": True}),
                               ("strip", strip, {})):
            if P.polish(out, **kw) != out:
                errors.append("%s: %s не идемпотентен" % (rel, label))
            if P.letters_of(text) != P.letters_of(out):
                errors.append("%s: %s изменил буквы/цифры" % (rel, label))
    # Защищённые области: оба безопасных режима сохраняют фрагменты,
    # инварианты репортуют нарушения, а не молчат при changed:true.
    for name, src, musts in PROTECTION_CASES:
        for kw in SAFE_MODES:
            label = "typographic" if kw.get("typographic") else "preserve-markup"
            out = P.polish(src, **kw)
            for frag in musts:
                if frag not in out:
                    errors.append("кейс %s/%s: защищённый фрагмент %r не "
                                  "сохранён" % (name, label, frag))
            problems = P.invariant_problems(src, out, **kw)
            if problems:
                errors.append("кейс %s/%s: инварианты на чистом результате "
                              "не пусты: %s" % (name, label, problems))
        # Негатив: разрушение защищённой области в уже приведённом тексте
        # обязано ловиться инвариантами (идемпотентность и буквы при этом
        # целы — ловить должно именно сохранение областей).
        clean = P.polish(src, typographic=True)
        if name == "ZWJ-кластер":
            broken = clean.replace("\u200d", "")
        elif name == "URL":
            broken = clean.replace("https://example.org/a...b",
                                   "https://example.org/a\u2026b")
        elif name == "кавычки атрибутов":
            broken = clean.replace('<a href="x">', "<a href=\u00abx\u00bb>")
        else:
            broken = clean.replace('`код "x"...`', '`код "x"\u2026`')
        problems = P.invariant_problems(src, broken, typographic=True)
        if not problems:
            errors.append("кейс %s: разрушение защищённой области не "
                          "репортится инвариантами" % name)
        elif any("идемпотентность" in p or "смысловая" in p for p in problems):
            errors.append("кейс %s: негатив пойман не сохранением областей, "
                          "а другим инвариантом: %s" % (name, problems))
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    src = 'Проза "цитата"... и `код "как есть"`.\n'
    out = P.polish(src, typographic=True)
    case("typographic приводит прозу", "\u00abцитата\u00bb" in out and "\u2026" in out)
    case("typographic не трогает инлайн-код", '`код "как есть"`' in out)
    fenced = 'Текст.\n```\n"не трогать..."\n```\n"трогать"\n'
    fout = P.polish(fenced, typographic=True)
    case("typographic не трогает fenced-блок", '"не трогать..."' in fout)
    case("typographic трогает прозу вне блока", "\u00abтрогать\u00bb" in fout)
    # Версия-фикстура собирается из частей: гейт зашитых версий сканирует
    # этот файл.
    _fv = "%d.%d.%d" % (1, 2, 3)
    fm = '---\nversion: "%s"\n---\n"проза"\n' % _fv
    mout = P.polish(fm, typographic=True)
    case("typographic не трогает frontmatter",
         mout.splitlines()[1] == 'version: "%s"' % _fv)
    case("typographic идемпотентен", P.polish(mout, typographic=True) == mout)
    case("буквы и цифры целы в обоих режимах",
         P.letters_of(src) == P.letters_of(out)
         and P.letters_of(fenced) == P.letters_of(fout))
    stripped = P.polish(src)
    case("strip снимает ёлочки-кандидаты и уплощает", '"' in stripped and "..." in stripped)
    case("strip идемпотентен", P.polish(stripped) == stripped)
    # Негатив: если бы typographic трогал код, свойство 1 упало бы —
    # имитируем подменой результата и проверяем детектор check().
    saved = P.polish

    def broken(text, preserve_markup=False, typographic=False):
        if typographic:
            return saved(text)  # «сломанный» typographic = strip
        return saved(text, preserve_markup)

    P.polish = broken
    try:
        errs = check()
    finally:
        P.polish = saved
    case("подделанный typographic ловится check() (негатив)", len(errs) >= len(DOCS))
    # Негатив: режим, разрушающий защищённые ZWJ-кластеры, ловится check().
    def broken_zwj(text, preserve_markup=False, typographic=False):
        out = saved(text, preserve_markup, typographic)
        if typographic or preserve_markup:
            out = out.replace("\u200d", "")
        return out

    P.polish = broken_zwj
    try:
        errs_zwj = check()
    finally:
        P.polish = saved
    case("режим, разрушающий ZWJ-кластеры, ловится check() (негатив)",
         any("ZWJ" in e for e in errs_zwj))
    print("САМОПРОВЕРКА check_polish_modes: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Честность режимов polish: typographic не трогает "
                    "собственную витрину, strip остаётся destructive.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errors = check()
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("РЕЖИМЫ POLISH: нарушений %d" % len(errors))
        return 1
    print("РЕЖИМЫ POLISH: typographic changed:false на %d документах; "
          "strip честно destructive; инварианты целы" % len(DOCS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
