#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт синхронности бандла dsh/ с корнем репозитория.

Бандл `dsh/` — детерминированный вендор для DeepSeek Harness: каталог
`dsh/skills/humanizer-ru/` обязан побайтово повторять корневые `SKILL.md`
и `references/*.md`. Верификация синхронности здесь, а не в понимании
читателя: рассинхронизированный вендор — это битые ссылки или устаревшие
маркеры у тех, кто установил скилл из бандла.

Правила:
1. Каждый файл `dsh/skills/humanizer-ru/SKILL.md` и
   `dsh/skills/humanizer-ru/references/*.md` побайтово равен своему
   корневому источнику.
2. Лишних файлов в вендоре нет: только SKILL.md и references/*.md
   (вендор обязан оставаться «без кода» — scripts/ в бандл не входит).
3. Имя каталога скилла — ровно `humanizer-ru` (валидаторы корня вызываются
   с --expect-dir humanizer-ru, и это же имя видит dsh).

Запуск из корня репозитория:
    python3 scripts/check_bundle_sync.py            # проверка
    python3 scripts/check_bundle_sync.py --selftest # самопроверка

Коды: 0 — вендор синхронен; 1 — есть расхождение; 2 — ошибка запуска.
Только стандартная библиотека.
"""
import os
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BUNDLE_ROOT = os.path.join("dsh", "skills", "humanizer-ru")
def read(path):
    """Содержимое файла с нормализованными переносами строк.

    Сравнивать сырые байты нельзя: `.gitattributes` предписывает `eol=lf`, но
    в рабочем дереве Windows источник и вендорная копия легко расходятся по
    CRLF/LF, оставаясь при этом идентичными в индексе. Такое расхождение —
    свойство чекаута, а не рассинхронизация вендора, и валидатор не должен
    падать на нём: иначе гейт даёт ложный провал у любого контрибьютора,
    который правит файлы редактором с переносами Windows.
    """
    with open(path, "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def list_vendor_files(root):
    vendor = os.path.join(root, BUNDLE_ROOT)
    out = []
    for dirpath, dirnames, filenames in os.walk(vendor):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            out.append(os.path.relpath(os.path.join(dirpath, name), vendor))
    return out


def check(root):
    errors = []
    vendor = os.path.join(root, BUNDLE_ROOT)
    if not os.path.isdir(vendor):
        return ["нет каталога бандла %s" % BUNDLE_ROOT]
    files = list_vendor_files(root)
    expected = ["SKILL.md"] + sorted(
        os.path.join("references", name)
        for name in os.listdir(os.path.join(root, "references"))
        if name.endswith(".md"))
    # knowledge/ — опциональный слой пользовательских правил: если каталог
    # есть в корне, вендор обязан повторять его .md-файлы побайтово
    # (механизм corrections smixs/ilyautov).
    knowledge_dir = os.path.join(root, "knowledge")
    if os.path.isdir(knowledge_dir):
        expected += sorted(
            os.path.join("knowledge", name)
            for name in os.listdir(knowledge_dir)
            if name.endswith(".md"))
    # 2. Лишние файлы.
    for rel in files:
        if rel not in expected:
            errors.append("лишний файл вендора: %s" % rel)
    for rel in expected:
        if rel not in files:
            errors.append("в вендоре нет файла: %s" % rel)
            continue
        # 1. Побайтовое равенство.
        try:
            left = read(os.path.join(vendor, rel))
            right = read(os.path.join(root, rel))
        except OSError as exc:
            errors.append("не читается %s: %r" % (rel, exc))
            continue
        if left != right:
            errors.append("вендор рассинхронизирован: %s" % rel)
    return errors


def selftest():
    cases = []
    with tempfile.TemporaryDirectory(prefix="bundle-sync-selftest-") as td:
        os.makedirs(os.path.join(td, "references"))
        os.makedirs(os.path.join(td, "dsh", "skills", "humanizer-ru", "references"))
        root_skill = os.path.join(td, "SKILL.md")
        root_ref = os.path.join(td, "references", "note.md")
        with open(root_skill, "w", encoding="utf-8") as fh:
            fh.write("# Карта\n")
        with open(root_ref, "w", encoding="utf-8") as fh:
            fh.write("Справочник\n")
        with open(os.path.join(td, "dsh", "skills", "humanizer-ru", "SKILL.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("# Карта\n")
        with open(os.path.join(td, "dsh", "skills", "humanizer-ru",
                               "references", "note.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("Справочник\n")
        cases.append(("синхронный вендор без ошибок", check(td) == []))

        # knowledge/: опциональный каталог — синхронен или отсутствует.
        os.makedirs(os.path.join(td, "knowledge"))
        with open(os.path.join(td, "knowledge", "corrections.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("Журнал\n")
        errs = check(td)
        cases.append(("knowledge в корне без вендора виден",
                      any("в вендоре нет файла" in e
                          and "knowledge" in e for e in errs)))
        os.makedirs(os.path.join(td, "dsh", "skills", "humanizer-ru",
                                 "knowledge"))
        with open(os.path.join(td, "dsh", "skills", "humanizer-ru",
                               "knowledge", "corrections.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("Журнал\n")
        cases.append(("knowledge синхронен", check(td) == []))
        with open(os.path.join(td, "knowledge", "corrections.md"), "a",
                  encoding="utf-8") as fh:
            fh.write("запись\n")
        cases.append(("дрейф knowledge виден",
                      any("knowledge" in e for e in check(td))))

        with open(os.path.join(td, "SKILL.md"), "a", encoding="utf-8") as fh:
            fh.write("дрейф\n")
        cases.append(("дрейф SKILL.md виден",
                      any("SKILL.md" in e for e in check(td))))

        with open(os.path.join(td, "SKILL.md"), "r", encoding="utf-8") as fh:
            base = fh.read()
        with open(os.path.join(td, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write(base.replace("дрейф\n", ""))
        os.makedirs(os.path.join(td, "dsh", "skills", "humanizer-ru", "scripts"))
        with open(os.path.join(td, "dsh", "skills", "humanizer-ru",
                               "scripts", ".keep"), "w") as fh:
            fh.write("")
        errs = check(td)
        cases.append(("лишний файл (scripts) виден",
                      any("лишний файл" in e for e in errs)))

    ok = 0
    for name, passed in cases:
        print(("  [OK]   " if passed else "  [FAIL] ") + name)
        ok += 1 if passed else 0
    print("Самопроверка: %d/%d" % (ok, len(cases)))
    return 0 if ok == len(cases) else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    errors = check(ROOT)
    for e in errors:
        print("ПРОВАЛ бандл: %s" % e)
    if errors:
        print("Итог: расхождений бандла %d" % len(errors))
        return 1
    vn = len(list_vendor_files(ROOT))
    print("OK бандл: вендор синхронен, файлов %d" % vn)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
