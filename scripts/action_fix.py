#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""action_fix.py — автофикс текстовых маркеров класса A для CI-экшена.

Вынесен из action/action.yml (точечный выпуск): Python-код в heredoc внутри YAML
literal-блока ломал парсинг экшена; отдельный скрипт читаем, тестируем
и не требует встраивания кода в YAML.

Чистка идёт текстовым путём filemarks (text_layer: Layer A + MARKUP) —
прямой вызов, а не filemarks --clean: CLI маршрутизирует .md (дефолтный
глоб экшена) в контейнерный путь (метаданные frontmatter), который не
снимает текстовые маркеры. Файлы без маркеров не перезаписываются
(решение принимает вызывающий код, сравнивая скан до и после).

Запуск:
    python3 scripts/action_fix.py файл [файл ...]

Выходы: по каждому файлу строка вида
    CHANGED  путь  (layer_a=N, markup=M)
    UNFIXED  путь  (маркер вне текстового пути)
    CLEAN    путь
Код возврата: 0 всегда (успех неприменимости — решение гейта принимает
повторный скан check_markers.py). Только стандартная библиотека.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "filemarks"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")


def fix_file(path):
    """Чистит файл текстовым путём. Возвращает (status, info).

    Статусы: CHANGED (сняты маркеры текстового пути), CLEAN (маркеров
    класса A не было или вход чист), UNFIXED (есть маркеры класса A,
    которые текстовый путь не снимает — sandbox_link, grok_card_tag;
    они перечисляются повторным сканом вызывающего кода).

    Граница записи: путь обязан оставаться внутри рабочего каталога
    (GITHUB_WORKSPACE либо текущего каталога). Абсолютный путь или путь
    с выходом через «..» за его пределы — отказ (UNFIXED), не запись:
    экшен получает значение `files` из входа workflow, и без этой
    проверки значение могло бы перезаписать файл за пределами репо
    (аудит 2026-08-30).
    """
    from text_layer import clean_text_layer, clean_markup  # noqa: E402
    from common_fm import safe_write_text  # noqa: E402
    import check_markers as cm  # noqa: E402

    workspace = os.path.realpath(os.environ.get("GITHUB_WORKSPACE")
                                 or os.getcwd())
    real = os.path.realpath(path)
    if not (real == workspace or real.startswith(workspace + os.sep)):
        return ("UNFIXED", (0, 0))

    with open(real, encoding="utf-8", errors="surrogateescape") as fh:
        text = fh.read()
    # Маркеры класса A вне текстового пути: фиксируем до чистки,
    # чтобы UNFIXED честно называл такой файл.
    has_class_a = False
    compiled = {name: __import__("re").compile(case[0])
                for name, case in cm.CASES.items()}
    for line in text.splitlines():
        if cm._line_matches(line, compiled):
            has_class_a = True
            break
    cleaned, n = clean_text_layer(text)
    cleaned, m = clean_markup(cleaned)
    if cleaned == text:
        return ("UNFIXED" if has_class_a else "CLEAN", (0, 0))
    if n + m == 0:
        return ("UNFIXED", (n, m))
    # Запись через safe_write_text (common_fm): атомарность и защита от
    # симлинков — как у filemarks, не голым open().
    safe_write_text(real, cleaned)
    return ("CHANGED", (n, m))


def main():
    if len(sys.argv) < 2:
        print("usage: action_fix.py файл [файл ...]", file=sys.stderr)
        return 2
    changed = 0
    unfixed = []
    for path in sys.argv[1:]:
        try:
            status, (n, m) = fix_file(path)
        except OSError as exc:
            print("UNFIXED  %s  (%s)" % (path, exc))
            unfixed.append(path)
            continue
        if status == "CHANGED":
            changed += 1
            print("CHANGED  %s  (layer_a=%d, markup=%d)" % (path, n, m))
        elif status == "UNFIXED":
            unfixed.append(path)
            print("UNFIXED  %s  (маркер вне текстового пути)" % path)
        else:
            print("CLEAN    %s" % path)
    print("почищено: %d; непочищаемые: %d" % (changed, len(unfixed)))
    return 0


def _selftest():
    """PASS/FAIL: CHANGED/CLEAN/UNFIXED и граница записи (workspace)."""
    import shutil
    import tempfile
    fails = 0
    old_ws = os.environ.get("GITHUB_WORKSPACE")
    d = tempfile.mkdtemp()
    os.environ["GITHUB_WORKSPACE"] = d
    try:
        inside = os.path.join(d, "in.md")
        with open(inside, "w", encoding="utf-8") as fh:
            fh.write("Текст [span_1](start_span)маркер[span_1](end_span).\n")
        st, _ = fix_file(inside)
        if st != "CHANGED":
            print("ПРОВАЛ selftest: внутренний путь не CHANGED (%s)" % st)
            fails += 1
        clean = os.path.join(d, "clean.md")
        with open(clean, "w", encoding="utf-8") as fh:
            fh.write("Чистый текст.\n")
        st2, _ = fix_file(clean)
        if st2 != "CLEAN":
            print("ПРОВАЛ selftest: чистый не CLEAN (%s)" % st2)
            fails += 1
        outside = os.path.join(tempfile.gettempdir(),
                               "action-fix-outside-selftest.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("Текст [span_1](start_span)маркер[span_1](end_span).\n")
        before = open(outside, encoding="utf-8").read()
        st3, _ = fix_file(outside)
        after = open(outside, encoding="utf-8").read()
        if st3 != "UNFIXED" or before != after:
            print("ПРОВАЛ selftest: внешний путь не отказан (%s)" % st3)
            fails += 1
        os.unlink(outside)
        sandbox = os.path.join(d, "sb.md")
        with open(sandbox, "w", encoding="utf-8") as fh:
            fh.write("Файл [документ](sandbox:/mnt/data/doc.pdf).\n")
        st4, _ = fix_file(sandbox)
        if st4 != "UNFIXED":
            print("ПРОВАЛ selftest: sandbox_link не UNFIXED (%s)" % st4)
            fails += 1
    finally:
        if old_ws is None:
            os.environ.pop("GITHUB_WORKSPACE", None)
        else:
            os.environ["GITHUB_WORKSPACE"] = old_ws
        shutil.rmtree(d, ignore_errors=True)
    if fails:
        print("САМОПРОВЕРКА: провалов %d" % fails)
        return 1
    print("САМОПРОВЕРКА: 4/4 PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
