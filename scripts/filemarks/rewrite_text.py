#!/usr/bin/env python3
# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
"""rewrite_text.py — слой B против статистических меток: хук перезаписи.

Слой B снимает статистические (token-sampling) метки только перезаписью —
верификатора таких меток публично не существует, поэтому отчёт обязан
говорить «best-effort», а не «снято». Модель для перезаписи выбирается из
другого семейства, чем подозреваемый источник (гигиена моделей).

Backend по умолчанию — print-prompt: печатает промпт, модель не зовёт.
Промпты на русском; {TEXT} подставляется вызовом.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common_fm import MAX_INPUT_BYTES, MAX_STDIN_BYTES, eprint

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
    # B2: контрастное вычитание — бьёт в сигнал
    # перплексии, не портя факты.
    "contrastive": (
        "Перепиши контрастным вычитанием. В каждом предложении найди самое "
        "предсказуемое, шаблонное слово и замени его менее вероятным, "
        "естественным для живого автора словом — тем, которое выбрал бы этот "
        "автор, а не генератор. Делай 1–2 замены на предложение; не заменяй "
        "синонимом того же регистра (синоним-замена не лечение — штамп, "
        "заменённый родственным штампом, остаётся штампом). Сохрани все факты, "
        "числа, имена и технические идентификаторы дословно — числа менять "
        "категорически нельзя. Ничего не добавляй и не убирай по смыслу. "
        "Выдай только переписанный текст.\n\n---\n{TEXT}"
    ),
    # B3: зелёные абзацы (mixed content) — чистые абзацы не трогать,
    # переписывать только абзацы с признаками машинного текста.
    "mixed": (
        "Переписывай только те абзацы, в которых есть признаки машинного "
        "текста (шаблонные переходы, ровный ритм, канцелярит); чисто "
        "написанные абзацы оставь дословно, без изменений. В каждом "
        "переписанном абзаце сделай 1–2 контрастные замены (замени самое "
        "предсказуемое слово менее вероятным, естественным для автора). "
        "На чистый абзац допустимо максимум 1–2 контрастные замены — не "
        "больше. Сохрани все факты, числа, имена и технические "
        "идентификаторы дословно — числа менять категорически нельзя. "
        "Ничего не добавляй и не убирай по смыслу. Выдай только "
        "переписанный текст.\n\n---\n{TEXT}"
    ),
}


# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


# Итеративная цепочка Слоя B: петля перезаписи
# до порога прокси (check_rewrite_delta), не более 3 проходов. Порядок
# стойкости: парафраз < humanize < обратный перевод < план->документ.
_CHAINS = {
    "backtranslate": ["backtranslate_out", "backtranslate_back"],
    "structural": ["structural_outline", "structural_write"],
}
_CHAIN_MAX_PASSES = 3


def _chain(name):
    """Возвращает читаемую последовательность промптов для --chain <name>.

    Печатает порядок применения, шаги из существующих PROMPTS и лимит в 3
    прохода (петля «повторять до порога прокси, не более 3»). Пустой текст
    не нужен: промпты печатаются без подстановки {TEXT}.
    """
    steps = _CHAINS[name]
    lines = ["Цепочка «%s» (итеративная перезапись Слоя B):" % name]
    for i, step in enumerate(steps, 1):
        prompt = PROMPTS[step].split("\n\n---\n")[0]
        lines.append("%d) %s — %s" % (i, step, prompt))
    lines.append("Порядок применения: %s" % " -> ".join(steps))
    lines.append("Лимит: не более %d проходов (повторять перезапись до "
                 "низкого остаточного риска по check_rewrite_delta.py, "
                 "максимум %d раз)." % (_CHAIN_MAX_PASSES, _CHAIN_MAX_PASSES))
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--strength", choices=sorted(PROMPTS), default="paraphrase")
    p.add_argument("--backend", choices=("print-prompt", "exec"), default="print-prompt",
                   help="print-prompt — печатает промпт (по умолчанию); exec — "
                        "исполняет внешнюю команду HUMANIZER_REWRITE_CMD с "
                        "плейсхолдером {INPUT} (путь к файлу с промптом), "
                        "ответ читается из stdout; жёсткий таймаут "
                        "HUMANIZER_REWRITE_TIMEOUT_S (по умолчанию 300)")
    p.add_argument("--chain", choices=sorted(_CHAINS), default=None,
                   help="итеративная цепочка Слоя B: печатает последовательность "
                        "промптов с порядком применения и лимитом 3 проходов")
    p.add_argument("--lang", default="en")
    p.add_argument("--original-lang", default="ru")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        ok = (all("{TEXT}" in v for v in PROMPTS.values())
              and len(PROMPTS) >= 9
              and all(set(_CHAINS[c]) <= set(PROMPTS) for c in _CHAINS)
              and "contrastive" in PROMPTS and "mixed" in PROMPTS)
        print("САМОПРОВЕРКА: %s" % ("1/1 PASS" if ok else "0/1 PASS"))
        return 0 if ok else 1
    if args.chain:
        print(_chain(args.chain))
        return 0
    text = ""
    if args.path and not args.path.is_file():
        eprint("файл не существует: %s" % args.path)
        return 2
    if args.path and args.path.is_file():
        if args.path.stat().st_size > MAX_INPUT_BYTES:
            eprint("отказ: файл больше %d байт" % MAX_INPUT_BYTES)
            return 2
        try:
            text = args.path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            eprint("файл не читается как UTF-8: %s" % exc)
            return 2
    elif not sys.stdin.isatty():
        raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
        if len(raw) > MAX_STDIN_BYTES:
            eprint("отказ: stdin больше %d байт" % MAX_STDIN_BYTES)
            return 2
        text = raw.decode("utf-8", errors="replace")
    out = PROMPTS[args.strength]
    out = out.replace("{LANG}", args.lang).replace("{ORIGINAL_LANG}", args.original_lang)
    out = out.replace("{TEXT}", text)
    if args.backend == "exec":
        return _exec_backend(out)
    print(out)
    return 0


def _exec_backend(prompt):
    """Opt-in вывод: запустить внешнюю переписывающую команду. Команда берётся из окружения HUMANIZER_REWRITE_CMD и
    обязана содержать плейсхолдер {INPUT} — он заменяется путём к временному
    файлу с промптом; ответ команды читается из stdout. Жёсткий таймаут из
    HUMANIZER_REWRITE_TIMEOUT_S (по умолчанию 300 с): зависшая команда
    убивается, висеть этот хук не умеет по построению. Только stdlib,
    дефолт остаётся print-prompt. Коды: 0 — ответ напечатан; 3 — команда
    не настроена, упала или истекла по таймауту."""
    cmd = os.environ.get("HUMANIZER_REWRITE_CMD", "").strip()
    if not cmd:
        eprint("exec-backend не настроен: задайте HUMANIZER_REWRITE_CMD с "
               "{INPUT}, или используйте print-prompt")
        return 3
    if "{INPUT}" not in cmd:
        eprint("HUMANIZER_REWRITE_CMD обязан содержать плейсхолдер {INPUT}")
        return 3
    try:
        timeout = int(os.environ.get("HUMANIZER_REWRITE_TIMEOUT_S", "300"))
    except ValueError:
        timeout = 300
    timeout = max(10, min(timeout, 600))
    fd, tmp = tempfile.mkstemp(prefix="hr-rewrite-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(prompt)
        # shell=True осознанно: шаблон команды задаёт сам оператор
        # (как core.editor в git); привилегий она не повышает.
        proc = subprocess.run(
            cmd.replace("{INPUT}", tmp), shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        eprint("exec-backend истёк по таймауту (%d с)" % timeout)
        return 3
    except OSError as exc:
        eprint("exec-backend не запустился: %s" % exc)
        return 3
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if proc.returncode != 0:
        eprint("exec-backend вернул код %d: %s"
               % (proc.returncode, proc.stderr.strip()[:200]))
        return 3
    out = proc.stdout.strip()
    if not out:
        eprint("exec-backend вернул пустой ответ")
        return 3
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())