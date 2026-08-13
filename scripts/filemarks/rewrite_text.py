# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
#!/usr/bin/env python3
"""rewrite_text.py — слой B против статистических меток: хук перезаписи.

Слой B снимает статистические (token-sampling) метки только перезаписью —
верификатора таких меток публично не существует, поэтому отчёт обязан
говорить «best-effort», а не «снято». Модель для перезаписи выбирается из
другого семейства, чем подозреваемый источник (гигиена моделей).

Backend по умолчанию — print-prompt: печатает промпт, модель не зовёт.
Промпты на русском; {TEXT} подставляется вызовом.
"""
import argparse
import sys
from pathlib import Path

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
sys.path.insert(0, HERE)
from common_fm import MAX_STDIN_BYTES, eprint

PROMPTS = {
    "paraphrase": (
        "Перепиши следующий текст так, чтобы на уровне слов он звучал заметно "
        "иначе. Меняй порядок частей, связки и переходы; варьируй границы и длину "
        "предложений; заменяй и знаменательные, и служебные слова там, где смысл "
        "позволяет. Сохрани все факты, числа, имена и технические идентификаторы. "
        "Ничего не добавляй и не убирай по смыслу. Выдай только переписанный текст.\n\n---\n{TEXT}"
    ),
    "humanize": (
        "Перепиши следующий текст так, как написал бы его человек с нуля. Варьируй "
        "ритм и длину предложений, заменяй шаблонные переходы и заполнители живой "
        "естественной речью, используй простую и разнообразную лексику. Сохрани все "
        "факты, числа, имена и технические идентификаторы. Ничего не добавляй и не "
        "убирай по смыслу. Выдай только переписанный текст.\n\n---\n{TEXT}"
    ),
    "code": (
        "Перепиши естественно-языковые части этого кода — комментарии, docstring и "
        "строковые литералы — другими словами. Переименуй локальные переменные, "
        "параметры функций и приватные помощники в эквивалентные по смыслу имена. "
        "Сохрани поведение программы, публичные имена API и все значения, влияющие "
        "на вывод. Выдай только переписанный код.\n\n---\n{TEXT}"
    ),
    "backtranslate_out": (
        "Переведи следующий текст на {LANG}. Выдай только перевод.\n\n---\n{TEXT}"
    ),
    "backtranslate_back": (
        "Переведи следующий текст на {ORIGINAL_LANG}. Сохрани смысл; используй "
        "естественные формулировки. Выдай только перевод.\n\n---\n{TEXT}"
    ),
    "structural_outline": (
        "Выпиши маркированный план всех утверждений и структуры текста (без полных "
        "предложений). Выдай только план.\n\n---\n{TEXT}"
    ),
    "structural_write": (
        "Напиши полный документ по этому плану естественной разнообразной прозой. "
        "Избегай шаблонных переходов. Не пропускай ни одного пункта плана. Выдай "
        "только документ.\n\n---\n{TEXT}"
    ),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--strength", choices=sorted(PROMPTS), default="paraphrase")
    p.add_argument("--backend", choices=("print-prompt",), default="print-prompt")
    p.add_argument("--lang", default="en")
    p.add_argument("--original-lang", default="ru")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        ok = all("{TEXT}" in v for v in PROMPTS.values()) and len(PROMPTS) == 7
        print("САМОПРОВЕРКА: 1/1 PASS" if ok else "САМОПРОВЕРКА: 0/1 PASS")
        return 0 if ok else 1
    text = ""
    if args.path and args.path.is_file():
        text = args.path.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read(MAX_STDIN_BYTES + 1)
        if len(text) > MAX_STDIN_BYTES:
            eprint("отказ: stdin больше %d байт" % MAX_STDIN_BYTES)
            return 2
    out = PROMPTS[args.strength].replace("{TEXT}", text)
    out = out.replace("{LANG}", args.lang).replace("{ORIGINAL_LANG}", args.original_lang)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
