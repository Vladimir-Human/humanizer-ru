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
    """Чистит файл текстовым путём. Возвращает (status, info)."""
    from text_layer import clean_text_layer, clean_markup  # noqa: E402
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        text = fh.read()
    cleaned, n = clean_text_layer(text)
    cleaned, m = clean_markup(cleaned)
    if cleaned == text:
        return ("CLEAN", (0, 0))
    if n + m == 0:
        # Текст изменился без снятия маркеров (не должно происходить) —
        # считаем непочищаемым, чтобы вызывающий код решил.
        return ("UNFIXED", (n, m))
    with open(path, "w", encoding="utf-8", errors="surrogateescape",
              newline="") as fh:
        fh.write(cleaned)
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


if __name__ == "__main__":
    sys.exit(main())
