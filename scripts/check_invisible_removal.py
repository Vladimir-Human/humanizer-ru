#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_invisible_removal.py — гейт классификации невидимых символов.

Проверяет (критерий v2 3.2):
  1. Фикстуры на каждый класс риска (tests/fixtures/invisibles/): действия
     remove_invisible совпадают с expected.json — safe снимается
     автоматически; ambiguous только opt-in (с предупреждениями);
     dangerous показывается и НЕ снимается никогда; теговые блоки
     эмодзи-флагов сохраняются, одиночные теги снимаются.
  2. Инвариант запрета: ни в одном режиме (включая include_ambiguous)
     dangerous-символ не попадает в removed; режима «снять всё невидимое»
     не существует (у функции ровно два параметра: text,
     include_ambiguous).
  3. Реестр: блок invisible_classes в markers.v1.json побайтово
     соответствует таблице text_layer.INVISIBLE_CLASSES (единственный
     источник — код; реестр — публикуемая копия).
  4. Документация: каждый диапазон таблицы представлен в
     references/removal-matrix.md (U+XXXX литералы).
  5. CLI-интеграция: humanizer-markers --remove --json на safe-фикстуре
     даёт тот же отчёт, что функция (через пакет из src/).
  6. Съём невидимок не порождает видимый артефакт: зазор схлопывается в
     точке съёма (после safe/opt-in/to-space нет {2,} пробелов), а
     авторская типографика вне точек съёма не трогается; законная
     кириллическая диакритика (категория Mn) сохраняется во всех режимах.

Запуск:
    python3 scripts/check_invisible_removal.py             # проверка
    python3 scripts/check_invisible_removal.py --selftest

Коды: 0 — классификация цела; 1 — нарушение; 2 — вход не читается.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "invisibles")
MARKERS_JSON = os.path.join(ROOT, "markers.v1.json")
MATRIX_MD = os.path.join(ROOT, "references", "removal-matrix.md")

sys.path.insert(0, os.path.join(HERE, "filemarks"))
import text_layer  # noqa: E402


def _registry_block():
    """Блок invisible_classes так, как его строит export_markers."""
    return [
        {"range": ["U+%04X" % lo, "U+%04X" % hi], "class": cls,
         "name": name, "risk": risk, "action": action}
        for (lo, hi), cls, name, risk, action in text_layer.INVISIBLE_CLASSES
    ]


def _codes(records):
    return [r["codepoint"] for r in records]


def check_fixtures() -> list:
    errors = []
    with open(os.path.join(FIXTURES, "expected.json"), encoding="utf-8") as fh:
        expected = json.load(fh)
    for name, exp in sorted(expected.items()):
        path = os.path.join(FIXTURES, name)
        if not os.path.isfile(path):
            errors.append("%s: фикстура отсутствует" % name)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for mode, key in (("default", False), ("opt-in", True)):
            cleaned, report = text_layer.remove_invisible(
                text, include_ambiguous=key)
            want = exp.get("default" if not key else "opt_in", {})
            got_removed = _codes(report["removed"])
            if "removed" in want and got_removed != want["removed"]:
                errors.append("%s [%s]: removed %r != ожидаемому %r"
                              % (name, mode, got_removed, want["removed"]))
            if "reported" in want \
                    and _codes(report["reported"]) != want["reported"]:
                errors.append("%s [%s]: reported %r != ожидаемому %r"
                              % (name, mode, _codes(report["reported"]),
                                 want["reported"]))
            if "kept_flags" in want \
                    and len(report["flag_sequences_kept"]) != want["kept_flags"]:
                errors.append("%s [%s]: флагов сохранено %d != %d"
                              % (name, mode,
                                 len(report["flag_sequences_kept"]),
                                 want["kept_flags"]))
            if "changed" in want and (cleaned != text) != want["changed"]:
                errors.append("%s [%s]: changed != %r"
                              % (name, mode, want["changed"]))
            if "warnings_min" in want \
                    and len(report["warnings"]) < want["warnings_min"]:
                errors.append("%s [%s]: предупреждений %d < %d"
                              % (name, mode, len(report["warnings"]),
                                 want["warnings_min"]))
            # Инвариант запрета: dangerous никогда не снимается.
            for rec in report["removed"]:
                if rec["class"] == "dangerous":
                    errors.append("%s [%s]: dangerous %s СНЯТ — запрет "
                                  "нарушен" % (name, mode, rec["codepoint"]))
        # dangerous-символы обязаны остаться в тексте после обоих режимов.
        cleaned_opt, _ = text_layer.remove_invisible(text, True)
        for cp in ("U+2028", "U+2029", "U+FFF9"):
            if any(r["codepoint"] == cp for r in
                   text_layer.remove_invisible(text)[1]["reported"]) \
                    and chr(int(cp[2:], 16)) not in cleaned_opt:
                errors.append("%s: dangerous %s исчез из текста" % (name, cp))
    return errors


def check_registry() -> list:
    errors = []
    try:
        with open(MARKERS_JSON, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["markers.v1.json не читается: %r" % exc]
    block = doc.get("invisible_classes")
    if block != _registry_block():
        errors.append("markers.v1.json invisible_classes != таблице "
                      "text_layer (перегенерируйте export_markers.py)")
    return errors


def check_matrix_doc() -> list:
    errors = []
    try:
        with open(MATRIX_MD, encoding="utf-8") as fh:
            doc = fh.read()
    except OSError as exc:
        return ["removal-matrix.md не читается: %r" % exc]
    for (lo, hi), cls, name, _risk, action in text_layer.INVISIBLE_CLASSES:
        for cp in {lo, hi}:
            token = "U+%04X" % cp
            if token not in doc:
                errors.append("removal-matrix.md: нет %s (%s, %s)"
                              % (token, name, cls))
    return errors


def check_cli() -> list:
    """CLI-интеграция: --remove --json через пакет из src/."""
    errors = []
    path = os.path.join(FIXTURES, "safe.txt")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep \
        + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c",
         "from humanizer_ru.cli import markers_main; import sys; "
         "sys.exit(markers_main(['--remove', '--json', sys.argv[1]]))",
         path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
        encoding="utf-8", errors="replace", env=env, cwd=ROOT)
    if proc.returncode != 0:
        return ["CLI --remove: код %d, stderr: %s"
                % (proc.returncode, proc.stderr[-200:])]
    try:
        env_json = json.loads(proc.stdout)
        entry = env_json["files"][0]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        return ["CLI --remove: конверт не тот: %r" % exc]
    if entry.get("removed_safe") != 5 or entry.get("removed_ambiguous") != 0:
        errors.append("CLI --remove: счётчики не те: safe=%s ambiguous=%s"
                      % (entry.get("removed_safe"),
                         entry.get("removed_ambiguous")))
    if entry.get("mode") != "remove":
        errors.append("CLI --remove: mode != remove")
    return errors


def check_removal_gaps() -> list:
    """Съём невидимок не порождает видимый артефакт: {2,} пробелов.

    Проверяются safe-режим (нулевая ширина между пробелами), opt-in
    (ambiguous между пробелами) и to-space (NBSP между пробелами —
    тройной пробел не появляется). Законная кириллическая диакритика
    (категория Mn) сохраняется побайтно во всех режимах.
    """
    errors = []
    gap = "слово \u200b слово и ещё \u2060 одно"
    cleaned, _ = text_layer.remove_invisible(gap)
    if "  " in cleaned:
        errors.append("safe-съём породил {2,} пробелов: %r" % cleaned)
    if cleaned != "слово слово и ещё одно":
        errors.append("safe-съём: схлопывание не в точке съёма: %r" % cleaned)
    gap2 = "слово \u00a0 слово"
    cleaned2, _ = text_layer.remove_invisible(gap2, True)
    if "  " in cleaned2:
        errors.append("opt-in to-space породил {2,} пробелов: %r" % cleaned2)
    gap3 = "слово \u200e слово"
    cleaned3, _ = text_layer.remove_invisible(gap3, True)
    if "  " in cleaned3:
        errors.append("opt-in снятие породило {2,} пробелов: %r" % cleaned3)
    author = "авторский  текст без невидимок"
    if text_layer.remove_invisible(author)[0] != author:
        errors.append("двойной пробел автора тронут вне точки съёма")
    mn = "й\u0301 о\u0308"
    for mode in (False, True):
        out, _ = text_layer.remove_invisible(mn, mode)
        if out != mn:
            errors.append("Mn-диакритика изменена в режиме include_ambiguous"
                          "=%s: %r" % (mode, out))
    return errors


def check() -> list:
    errors = []
    # Запрет массового удаления по построению: у remove_invisible ровно два
    # параметра, флага «снять всё» не существует.
    sig = inspect.signature(text_layer.remove_invisible)
    if list(sig.parameters) != ["text", "include_ambiguous"]:
        errors.append("remove_invisible: сигнатура %r — появился лишний "
                      "режим (массовое удаление запрещено)"
                      % list(sig.parameters))
    for fn in (check_fixtures, check_registry, check_matrix_doc, check_cli,
               check_removal_gaps):
        try:
            errors.extend(fn())
        except OSError as exc:
            errors.append("%s: отказ входа: %r" % (fn.__name__, exc))
    return errors


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    text = "x\u200by\u2028z"
    cleaned, report = text_layer.remove_invisible(text)
    case("safe снимается", "\u200b" not in cleaned)
    case("dangerous остаётся", "\u2028" in cleaned)
    cleaned_opt, report_opt = text_layer.remove_invisible(text, True)
    case("dangerous остаётся и в opt-in", "\u2028" in cleaned_opt)
    case("dangerous в reported обоих режимов",
         any(r["codepoint"] == "U+2028" for r in report["reported"])
         and any(r["codepoint"] == "U+2028" for r in report_opt["reported"]))
    case("вне таблицы — dangerous (fail-safe)",
         text_layer.classify_codepoint(0x061C) is None
         and text_layer.remove_invisible("a\u061cb")[1]["reported"]
         and _codes(text_layer.remove_invisible("a\u061cb")[1]["reported"])
         == ["U+061C"]
         and text_layer.remove_invisible("a\u061cb")[0] == "a\u061cb")
    flag = "\U0001F3F4\U000E0067\U000E007F"
    cleaned_f, rep_f = text_layer.remove_invisible(flag)
    case("эмодзи-флаг сохраняется", cleaned_f == flag
         and len(rep_f["flag_sequences_kept"]) == 2)
    lone = "a\U000E0041b"
    cleaned_l, rep_l = text_layer.remove_invisible(lone)
    case("одиночный тег снимается", cleaned_l == "ab"
         and _codes(rep_l["removed"]) == ["U+E0041"])
    nbsp = "12\u00a0%"
    cleaned_n, _ = text_layer.remove_invisible(nbsp, True)
    case("NBSP opt-in -> обычный пробел", cleaned_n == "12 %")
    case("NBSP по умолчанию не трогается",
         text_layer.remove_invisible(nbsp)[0] == nbsp)
    gap = "слово \u200b слово"
    cleaned_gap, _ = text_layer.remove_invisible(gap)
    case("после съёма нет {2,} пробелов",
         cleaned_gap == "слово слово" and "  " not in cleaned_gap)
    cleaned_gapn, _ = text_layer.remove_invisible("слово \u00a0 слово", True)
    case("opt-in: двойного/тройного пробела нет", "  " not in cleaned_gapn)
    mn = "й\u0301 о\u0308"
    case("Mn-диакритика сохранена во всех режимах",
         text_layer.remove_invisible(mn)[0] == mn
         and text_layer.remove_invisible(mn, True)[0] == mn)
    # Негатив на глобальное схлопывание: авторский двойной пробел вне
    # точки съёма обязан оставаться — правится только зазор у снятого.
    case("авторский двойной пробел вне съёма не трогается",
         text_layer.remove_invisible("авторский  текст")[0] == "авторский  текст")
    errs = check_fixtures()
    case("реальные фикстуры проходят", errs == [])
    # Негатив: подмена expected ловится.
    exp_path = os.path.join(FIXTURES, "expected.json")
    with open(exp_path, encoding="utf-8") as fh:
        original = fh.read()
    tampered = json.loads(original)
    tampered["dangerous.txt"]["default"]["removed"] = ["U+2028"]
    with open(exp_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(tampered, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    try:
        case("подмена expected ловится (негатив)", check_fixtures() != [])
    finally:
        with open(exp_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(original)
    case("expected восстановлен", check_fixtures() == [])
    print("САМОПРОВЕРКА check_invisible_removal: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Классификация невидимых символов: safe/ambiguous/"
                    "dangerous, фикстуры, реестр, документация, CLI.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errors = check()
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("СНЯТИЕ НЕВИДИМЫХ: нарушений %d" % len(errors))
        return 1
    print("СНЯТИЕ НЕВИДИМЫХ: классификация, фикстуры, реестр, матрица и "
          "CLI согласованы; dangerous не снимается никогда")
    return 0


if __name__ == "__main__":
    sys.exit(main())
