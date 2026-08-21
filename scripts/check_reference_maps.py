#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Карты разбитых справочников: единственность разделов и живость ссылок.

Справочники `chatbot-artifacts` и `test-fixtures` разбиты на индекс и части.
Этот валидатор держит два свойства конструкции:

1. Каждый заголовок раздела (ID вроде `A.1`–`A.12`, `Раздел II`, `C`, `D`,
   нумерация образцов 1–15/11a) встречается в семействе ровно один раз:
   на ID ссылаются другие файлы проекта, дубль или пропажа ломает ссылку.
2. Каждый файл, названный в индексе в обратных кавычках, существует
   в каталоге справочников или в корне репозитория.

Запуск из корня репозитория:
    python3 scripts/check_reference_maps.py            # оба семейства
    python3 scripts/check_reference_maps.py --selftest

Коды: 0 — карты целы; 1 — есть дубль, пропажа или битая ссылка;
2 — ошибка запуска (файл семейства исчез, не читается). Только стандартная
библиотека.
"""
import fnmatch
import glob
import io
import os
import re
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FAMILIES = (
    {
        "name": "chatbot-artifacts",
        "glob": os.path.join("references", "chatbot-artifacts*.md"),
        "index": os.path.join("references", "chatbot-artifacts.md"),
        "headings": ["### A.%d." % i for i in range(1, 13)]
                    + ["## Раздел II", "## C.", "## D."],
    },
    {
        "name": "test-fixtures",
        "glob": os.path.join("references", "test-fixtures*.md"),
        "index": os.path.join("references", "test-fixtures.md"),
        "headings": ["## Образцы для регулярных выражений",
                     "## Полные пары",
                     "## Эмпирическая проверка регулярных выражений",
                     "## Принцип использования"]
                    + ["### %d." % i for i in range(1, 16)]
                    + ["### 11a."],
    },
)


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def headings_once(files, headings):
    """Список ошибок: заголовок должен встретиться ровно один раз."""
    counts = dict.fromkeys(headings, 0)
    for path in files:
        for line in read(path).splitlines():
            for head in headings:
                if line.startswith(head):
                    counts[head] += 1
    errors = []
    for head in headings:
        if counts[head] == 0:
            errors.append("заголовок %r не найден" % head)
        elif counts[head] > 1:
            errors.append("заголовок %r встречается %d раза"
                          % (head, counts[head]))
    return errors


def index_refs(index_path, root, ref_dir):
    """Список ошибок: каждый `.md` из индекса должен существовать.

    Ссылкой считается одиночное имя файла в обратных кавычках. Команды вида
    `python3 scripts/check_markers.py --scan файл.md` не совпадают: внутри
    кавычек у них пробелы, а шаблон требует кавычку сразу перед именем.
    """
    errors = []
    refs = re.findall(r"`([\w./-]+\.md)`", read(index_path))
    for ref in sorted(set(refs)):
        candidates = (os.path.join(ref_dir, ref), os.path.join(root, ref))
        if not any(os.path.exists(p) for p in candidates):
            errors.append("индекс ссылается на отсутствующий %s" % ref)
    return errors


def check_family(family, root):
    """Возвращает (ошибки, файлы) для одного семейства."""
    files = sorted(glob.glob(os.path.join(root, family["glob"])))
    index = os.path.join(root, family["index"])
    if not files or index not in [os.path.normpath(p) for p in files]:
        return ["нет индекса %s" % family["index"]], files
    errors = headings_once(files, family["headings"])
    errors += index_refs(index, root, os.path.dirname(index))
    return errors, files


def selftest():
    cases = []
    with tempfile.TemporaryDirectory(prefix="ref-maps-selftest-") as td:
        refs = os.path.join(td, "references")
        os.mkdir(refs)
        index = os.path.join(refs, "mini.md")
        part_a = os.path.join(refs, "mini-a.md")
        part_b = os.path.join(refs, "mini-b.md")

        with io.open(index, "w", encoding="utf-8") as fh:
            fh.write("# Мини\n\n| Раздел | Где |\n|---|---|\n"
                     "| первый | `mini-a.md` |\n| второй | `mini-b.md` |\n")
        with io.open(part_a, "w", encoding="utf-8") as fh:
            fh.write("### 1. Первый\n\n### 2. Второй\n")
        with io.open(part_b, "w", encoding="utf-8") as fh:
            fh.write("### 3. Третий\n")

        heads = ["### 1.", "### 2.", "### 3."]
        cases.append(("чистое семейство без ошибок",
                      headings_once([part_a, part_b], heads) == []))
        cases.append(("ссылки чистого индекса живут",
                      index_refs(index, td, refs) == []))

        with io.open(part_b, "a", encoding="utf-8") as fh:
            fh.write("\n### 1. Дубль\n")
        errs = headings_once([part_a, part_b], heads)
        cases.append(("дубль заголовка виден", len(errs) == 1
                      and "1." in errs[0]))

        with io.open(part_b, "w", encoding="utf-8") as fh:
            fh.write("### 3. Третий\n\nИндекс: `mini.md`.\n")
        with io.open(index, "a", encoding="utf-8") as fh:
            fh.write("См. `нет-такого.md`.\n")
        errs = index_refs(index, td, refs)
        cases.append(("битая ссылка индекса видна",
                      any("нет-такого.md" in e for e in errs)))

        # Свойство 3: чужой .md в references/ без упоминания виден.
        stray_path = os.path.join(refs, "stray-note.md")
        with io.open(stray_path, "w", encoding="utf-8") as fh:
            fh.write("Заметка без упоминаний.\n")
        errs = stray_references(td)
        cases.append(("чужой файл в references/ виден",
                      any("stray-note.md" in e for e in errs)))
        with io.open(part_a, "a", encoding="utf-8") as fh:
            fh.write("\nСм. `stray-note.md`.\n")
        errs = stray_references(td)
        cases.append(("упомянутый чужой файл не в претензии",
                      all("stray-note.md" not in e for e in errs)))

    ok = 0
    for name, passed in cases:
        print(("  [OK]   " if passed else "  [FAIL] ") + name)
        ok += 1 if passed else 0
    print("Самопроверка: %d/%d" % (ok, len(cases)))
    return 0 if ok == len(cases) else 1


def stray_references(root):
    """Чужие файлы в references/: вне семейств обязаны быть упомянутыми.

    Каталог references/ целиком уходит в релизный архив; подброшенный
    файл любого расширения в любом подкаталоге, который нигде не назван,
    уехал бы туда незамеченным (урок rev4/rev5: мусорные файлы проходили
    зелёным через верхний уровень, вложенный каталог и не-.md).
    Упоминанием считается имя в обратных кавычках или в цели
    markdown-ссылки; простое вхождение подстрокой в текст не считается.
    """
    texts = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                with io.open(path, encoding="utf-8") as fh:
                    texts[path] = fh.read()
            except (OSError, UnicodeDecodeError):
                pass
    fam_patterns = [os.path.basename(fam["glob"]) for fam in FAMILIES]
    errors = []
    refs_dir = os.path.join(root, "references")
    if not os.path.isdir(refs_dir):
        return errors
    for dirpath, dirnames, filenames in os.walk(refs_dir):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if dirpath == refs_dir and name.endswith(".md") and any(
                    fnmatch.fnmatch(name, pat) for pat in fam_patterns):
                continue
            esc = re.escape(name)
            mention_rx = re.compile(
                r"`%s`|\]\((?:references/|\./)?%s\)" % (esc, esc))
            if any(mention_rx.search(t) for p, t in texts.items()
                   if p != path):
                continue
            errors.append("лишний файл %s не упомянут ни в одном документе"
                          % rel)
    return errors


def main(argv):
    if "--selftest" in argv:
        return selftest()
    total_errors = 0
    broken = False
    for family in FAMILIES:
        try:
            errors, files = check_family(family, ROOT)
        except (OSError, UnicodeDecodeError) as exc:
            print("ошибка инструмента: %s: %r" % (family["name"], exc),
                  file=sys.stderr)
            broken = True
            continue
        if errors:
            total_errors += len(errors)
            for e in errors:
                print("ПРОВАЛ %s: %s" % (family["name"], e))
        else:
            print("OK %s: %d файлов, заголовки и ссылки целы"
                  % (family["name"], len(files)))
    stray = stray_references(ROOT)
    for e in stray:
        print("ПРОВАЛ справочники: %s" % e)
    total_errors += len(stray)
    if broken:
        return 2
    if total_errors:
        print("Итог: ошибок карт %d" % total_errors)
        return 1
    print("Итог: карты справочников целы")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
