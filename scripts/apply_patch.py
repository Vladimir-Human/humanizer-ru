#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_patch.py — пакетное применение exact-match правок к файлам.

Вход — UTF-8 JSON-массив операций:

    [{"path": "README.md", "old": "старый текст", "new": "новый текст"}, ...]

Каждая операция заменяет фрагмент `old` на `new` в файле `path`. Совпадение
строгое, посимвольное: без regex и «умного» выравнивания — фрагмент обязан
быть передан ровно как в файле. Необязательное поле `count` — ожидаемое
число вхождений `old` (считается как str.count, без пересечений); по
умолчанию 1, то есть фрагмент обязан встречаться ровно один раз — защита
от неоднозначной замены. Заменяются все `count` вхождений.

Семантика пакета — «всё или ничего»: сначала все операции проверяются и
применяются в памяти, файлы перезаписываются только при полном успехе.
Операции одного файла выполняются по порядку, каждая видит результат
предыдущих. При несовпадении печатается diff-подсказка: unified diff
ожидаемого фрагмента с ближайшим похожим участком файла.

Переносы строк: файл читается с нормализацией CRLF/CR -> LF, old/new
сопоставляются с LF-текстом, и файл всегда записывается с LF (инвариант
репозитория №2). Запись атомарная: временный файл в том же каталоге и
os.replace поверх оригинала.

Запуск:  python3 scripts/apply_patch.py patch.json
         python3 scripts/apply_patch.py --selftest
Код возврата: 0 — все операции применены; 1 — несовпадение (хотя бы один
old не найден или count не сошёлся; ни один файл не изменён); 2 — отказ
инструмента (patch.json не найден, битый JSON, неверная структура записи,
целевой файл не существует или не читается как UTF-8).
Только стандартная библиотека.
"""
import argparse
import difflib
import json
import os
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять инструмент на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


class ToolRefusal(Exception):
    """Отказ инструмента: работа не может быть выполнена, код 2."""


def load_ops(patch_path):
    """Читает patch.json и валидирует структуру. Возвращает список операций."""
    try:
        # utf-8-sig: BOM у patch.json терпим, агенты на Windows часто его пишут.
        with open(patch_path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ToolRefusal("файл патча не найден: %s" % patch_path)
    except UnicodeDecodeError as exc:
        raise ToolRefusal("%s не читается как UTF-8: %s" % (patch_path, exc))
    except json.JSONDecodeError as exc:
        raise ToolRefusal("%s не разбирается как JSON: %s" % (patch_path, exc))
    except OSError as exc:
        raise ToolRefusal("не удалось прочитать %s: %s" % (patch_path, exc))
    if not isinstance(data, list):
        raise ToolRefusal("корень patch.json обязан быть массивом операций, "
                          "получено: %s" % type(data).__name__)
    if not data:
        raise ToolRefusal("patch.json пуст: нечего применять")
    ops = []
    for i, item in enumerate(data):
        where = "операция #%d" % (i + 1)
        if not isinstance(item, dict):
            raise ToolRefusal("%s: запись обязана быть объектом "
                              "{path, old, new[, count]}" % where)
        for key in ("path", "old", "new"):
            if key not in item:
                raise ToolRefusal("%s: нет обязательного поля %r" % (where, key))
            if not isinstance(item[key], str):
                raise ToolRefusal("%s: поле %r обязано быть строкой" % (where, key))
        if item["old"] == "":
            raise ToolRefusal("%s: поле 'old' пустое — пустой фрагмент "
                              "заменять нельзя" % where)
        count = item.get("count", 1)
        # bool — наследник int, поэтому проверяется отдельно: true вместо
        # числа не должно молча превращаться в 1.
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ToolRefusal("%s: count обязан быть целым числом >= 1, "
                              "получено: %r" % (where, count))
        ops.append({"path": item["path"], "old": item["old"],
                    "new": item["new"], "count": count})
    return ops


def read_target(path):
    """Читает целевой файл строго как UTF-8, нормализуя переносы к LF.

    Возвращает (text, had_crlf). Строгость важна: errors="replace" здесь
    превратил бы битый файл в мусор и перезаписал бы его. BOM, если есть,
    остаётся частью содержимого и сохраняется при записи.
    """
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            raw = fh.read()
    except FileNotFoundError:
        raise ToolRefusal("целевой файл не найден: %s" % path)
    except UnicodeDecodeError as exc:
        raise ToolRefusal("%s не читается как UTF-8: %s" % (path, exc))
    except OSError as exc:
        raise ToolRefusal("не удалось прочитать целевой файл %s: %s" % (path, exc))
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    return text, text != raw


def write_atomic(path, content):
    """Атомарная запись: временный файл в том же каталоге + os.replace.

    Переносы уже нормализованы к LF; newline="" отключает трансляцию.
    """
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".apply-patch-",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        # mkstemp создаёт файл с правами 0600: возвращаем режим оригинала.
        try:
            os.chmod(tmp, os.stat(path).st_mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise ToolRefusal("не удалось записать %s: %s" % (path, exc))


def _diff_hint(text, old):
    """Unified diff ожидаемого фрагмента с ближайшим похожим участком файла.

    Возвращает список строк для печати либо None, если похожего места нет.
    Якорь поиска — первая непустая строка old.
    """
    old_lines = old.split("\n")
    anchor = ""
    for line in old_lines:
        if line.strip():
            anchor = line.strip()
            break
    if not anchor:
        return None
    lines = text.split("\n")
    best_ratio, best_idx = 0.0, -1
    for i, line in enumerate(lines):
        ratio = difflib.SequenceMatcher(None, anchor, line.strip()).ratio()
        if ratio > best_ratio:
            best_ratio, best_idx = ratio, i
    if best_idx < 0 or best_ratio < 0.4:
        return None
    window = lines[best_idx:best_idx + len(old_lines)]
    diff = list(difflib.unified_diff(
        old_lines, window,
        fromfile="old (ожидалось)",
        tofile="файл (строка %d)" % (best_idx + 1),
        lineterm="", n=2))
    # Подсказка не должна заливать консоль: строки и хвост diff-а режем.
    out = [(d if len(d) <= 200 else d[:200] + "…") for d in diff[:40]]
    if len(diff) > 40:
        out.append("… (diff усечён)")
    return out


def run(patch_path):
    try:
        ops = load_ops(patch_path)
        # Группировка по файлу в порядке появления: dict сохраняет порядок
        # вставки, а операции одного файла идут друг за другом.
        by_path = {}
        for op in ops:
            by_path.setdefault(op["path"], []).append(op)
        texts = {}
        for path in by_path:
            texts[path] = read_target(path)
    except ToolRefusal as exc:
        print("[СБОЙ] %s" % exc)
        return 2

    # Фаза проверки: всё в памяти, на диск ничего не пишется.
    failures = []
    new_texts = {}
    for path, file_ops in by_path.items():
        current = texts[path][0]
        for op in file_ops:
            found = current.count(op["old"])
            if found == 0:
                # Подсказку строим по текущему состоянию: предыдущие
                # операции этого файла могли уже сдвинуть содержимое.
                failures.append((path, "фрагмент old не найден",
                                 _diff_hint(current, op["old"])))
                break  # остальные операции этого файла уже бессмысленны
            if found != op["count"]:
                failures.append((path,
                                 "фрагмент old встречается %d раз, ожидалось %d"
                                 % (found, op["count"]), None))
                break
            current = current.replace(op["old"], op["new"])
        else:
            new_texts[path] = current

    if failures:
        for path, msg, hint in failures:
            print("[FAIL] %s: %s" % (path, msg))
            for line in hint or ():
                print("    " + line)
        print("PATCH: правки НЕ применены: несовпадения в %d файлах; "
              "ни один файл не изменён." % len({p for p, _m, _h in failures}))
        return 1

    # Фаза записи: все операции совпали, можно перезаписывать.
    written = 0
    for path, current in new_texts.items():
        text, had_crlf = texts[path]
        if current == text and not had_crlf:
            continue  # no-op: ни содержимое, ни переносы не меняются
        try:
            write_atomic(path, current)
        except ToolRefusal as exc:
            print("[СБОЙ] %s" % exc)
            return 2
        written += 1
        note = " (переносы строк нормализованы к LF)" if had_crlf else ""
        print("[OK] %s%s" % (path, note))
    print("PATCH: применено операций: %d, записано файлов: %d. ОК."
          % (len(ops), written))
    return 0


# --------------------------------------------------------------- selftest

def selftest():
    cases = []
    with tempfile.TemporaryDirectory(prefix="apply-patch-test-") as tmp:

        def _write(name, content):
            p = os.path.join(tmp, name)
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            return p

        def _read(p):
            with open(p, encoding="utf-8", newline="") as fh:
                return fh.read()

        def _patch(entries):
            p = os.path.join(tmp, "patch.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, ensure_ascii=False)
            return p

        # Позитив: одиночная замена.
        target = _write("цель.txt", "первая строка\nвторая строка\n")
        rc = run(_patch([{"path": target, "old": "вторая строка",
                          "new": "вторая глава"}]))
        cases.append(("одиночная замена -> код 0", rc == 0))
        cases.append(("содержимое заменено",
                      _read(target) == "первая строка\nвторая глава\n"))

        # Позитив: count > 1 заменяет все вхождения.
        multi = _write("много.txt", "раз раз раз\n")
        rc = run(_patch([{"path": multi, "old": "раз", "new": "два",
                          "count": 3}]))
        cases.append(("count=3 заменяет все вхождения -> код 0",
                      rc == 0 and _read(multi) == "два два два\n"))

        # Позитив: операции одного файла идут цепочкой.
        seq = _write("цепочка.txt", "шаг один\n")
        rc = run(_patch([
            {"path": seq, "old": "один", "new": "два"},
            {"path": seq, "old": "шаг два", "new": "шаг три"},
        ]))
        cases.append(("операции одного файла применяются по цепочке -> код 0",
                      rc == 0 and _read(seq) == "шаг три\n"))

        # Негатив: old не совпал.
        rc = run(_patch([{"path": target, "old": "нет такого фрагмента",
                          "new": "x"}]))
        cases.append(("несовпавший old -> код 1", rc == 1))
        cases.append(("файл не изменён при несовпадении",
                      _read(target) == "первая строка\nвторая глава\n"))

        # Негатив: неоднозначность без count.
        amb = _write("двусмысленно.txt", "повтор и повтор\n")
        rc = run(_patch([{"path": amb, "old": "повтор", "new": "раз"}]))
        cases.append(("old встречается дважды, count не задан -> код 1", rc == 1))
        cases.append(("файл не изменён при неоднозначности",
                      _read(amb) == "повтор и повтор\n"))

        # Негатив: count не сошёлся (в multi теперь три «два», ждём пять).
        rc = run(_patch([{"path": multi, "old": "два", "new": "раз",
                          "count": 5}]))
        cases.append(("count не сошёлся -> код 1", rc == 1))

        # Негатив: пакет «всё или ничего» — совпавший файл не записывается,
        # если другой не совпал.
        first = _write("первый.txt", "один\n")
        second = _write("второй.txt", "два\n")
        rc = run(_patch([
            {"path": first, "old": "один", "new": "три"},
            {"path": second, "old": "отсутствует", "new": "четыре"},
        ]))
        cases.append(("пакет с несовпадением -> код 1", rc == 1))
        cases.append(("атомарность пакета: совпавший файл не записан",
                      _read(first) == "один\n"))

        # Негатив: целевой файл не найден.
        rc = run(_patch([{"path": os.path.join(tmp, "нет-такого.txt"),
                          "old": "а", "new": "б"}]))
        cases.append(("целевой файл не найден -> код 2", rc == 2))

        # Негатив: patch.json не найден.
        rc = run(os.path.join(tmp, "нет-patch.json"))
        cases.append(("patch.json не найден -> код 2", rc == 2))

        # Негатив: битый JSON.
        broken = _write("битый.json", '[{"path": "x", ')
        rc = run(broken)
        cases.append(("битый JSON -> код 2", rc == 2))

        # Негатив: структурные ошибки записи.
        rc = run(_patch({"path": target, "old": "а", "new": "б"}))
        cases.append(("корень не массив -> код 2", rc == 2))
        rc = run(_patch([]))
        cases.append(("пустой массив -> код 2", rc == 2))
        rc = run(_patch([{"path": target, "new": "б"}]))
        cases.append(("нет поля old -> код 2", rc == 2))
        rc = run(_patch([{"path": target, "old": "", "new": "б"}]))
        cases.append(("пустой old -> код 2", rc == 2))
        rc = run(_patch([{"path": target, "old": "а", "new": "б", "count": 0}]))
        cases.append(("count=0 -> код 2", rc == 2))
        rc = run(_patch([{"path": target, "old": "а", "new": "б",
                          "count": True}]))
        cases.append(("count=true вместо числа -> код 2", rc == 2))

        # CRLF: old пишется с LF, файл перезаписывается с LF.
        crlf = os.path.join(tmp, "виндовый.txt")
        with open(crlf, "wb") as fh:
            fh.write("альфа\r\nбета\r\n".encode("utf-8"))
        rc = run(_patch([{"path": crlf, "old": "альфа\nбета",
                          "new": "альфа\nгамма"}]))
        cases.append(("old с LF совпал в CRLF-файле -> код 0", rc == 0))
        cases.append(("переносы нормализованы к LF",
                      _read(crlf) == "альфа\nгамма\n"))

        # no-op (old == new) — не ошибка.
        noop = _write("пустышка.txt", "как было\n")
        rc = run(_patch([{"path": noop, "old": "как было", "new": "как было"}]))
        cases.append(("old == new: no-op -> код 0",
                      rc == 0 and _read(noop) == "как было\n"))

        # Подсказка: ближайшее похожее место находится, чужой текст — нет.
        cases.append(("diff-подсказка находит похожее место",
                      bool(_diff_hint("первая строка\nвторая строка\n",
                                      "вторая строKa"))))
        cases.append(("diff-подсказка молчит без похожих строк",
                      _diff_hint("альфа\nбета\n", "qxz wv ut") is None))

        # CLI без аргументов — отказ, а не traceback.
        cases.append(("запуск без аргументов -> код 2", main([]) == 2))

    fails = [n for n, p in cases if not p]
    for n, p in cases:
        print(("PASS: " if p else "FAIL: ") + n)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(cases) - len(fails), len(cases)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Пакетное применение exact-match правок из patch.json.")
    ap.add_argument("patch", nargs="?", help="путь к patch.json (UTF-8)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.patch:
        print("[СБОЙ] нужен путь к patch.json: "
              "python3 scripts/apply_patch.py patch.json")
        return 2
    return run(args.patch)


if __name__ == "__main__":
    sys.exit(main())
