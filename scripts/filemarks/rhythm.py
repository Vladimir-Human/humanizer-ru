#!/usr/bin/env python3
# CV-метр ритма текста — порт идеи burstiness из ilyautov/humanizer-ru
# (humanizer_metrics/burstiness.py). Адаптация: упрощённая разбивка на
# предложения и слова (нет razdel — только stdlib), русский вывод, конвенции
# humanizer-ru, selftest.
"""rhythm.py — CV-метр ритма текста (дисперсия длин предложений).

Слой B (перезапись) обязан двигать ритм к большей дисперсии, а не менять
среднюю длину: вторая производная surprisal (DivEye, 2509.18880) и зазор
перплексии (2509.24930) живут на дисперсии. Скрипт считает длины предложений
в словах, их среднее, стандартное отклонение и коэффициент вариации
(CV = std/mean) — то, что ilyautov называют burstiness.

Пороги 0,35/0,45 НЕКаЛиброваны: ориентиры уровня O из чужой калибровки,
не гейты. Человеческий контроль ilyautov (CV 0,129–0,572) перекрывается с
AI (0,147–0,328), поэтому жёсткий порог запрещён.
Скрипт сообщает CV фактом и печатает ориентиры, а не вердикт об авторстве.

Разбивка на предложения — упрощённая: по [.!?…] (приём из
scan_soft_signals._SENT_SPLIT_RX); слова — regex [а-яА-ЯёЁa-zA-Z0-9-]+
(приём из scan_soft_signals._WORD_RX).

Запуск:
    python3 scripts/filemarks/rhythm.py файл.txt
    python3 scripts/filemarks/rhythm.py файл.txt --json
    python3 scripts/filemarks/rhythm.py --selftest

Коды возврата: 0 — прогон выполнен, 1 — провал самопроверки, 2 — ошибка входа.
Только стандартная библиотека.
"""
import argparse
import json
import re
import statistics
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Приёмы из scan_soft_signals.py: предложения — по разделителям [.!?…],
# слова — регулярка со словарными знаками и дефисом.
_SENT_SPLIT_RX = re.compile(r"(?<=[.!?\u2026])\s+")
_WORD_RX = re.compile(r"[а-яА-ЯёЁa-zA-Z\d-]+")

# Пороги НЕ калиброваны: ориентиры уровня O из чужой
# калибровки (ilyautov), не гейты. CV < 0.35 — «ровный»; ориентир живого
# регистра >= 0.45. Не использовать как вердикт об авторстве.
CV_FLAT = 0.35
CV_LIVE_TARGET = 0.45


def _word_count(sentence):
    """Число слов в предложении по модели _WORD_RX."""
    return len(_WORD_RX.findall(sentence))


def rhythm(text):
    """Считает длины предложений и возвращает агрегаты ритма.

    Возвращает dict: sentences, mean, std, cv. Для пустого входа — нули.
    """
    lengths = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for s in _SENT_SPLIT_RX.split(line):
            s = s.strip()
            if not s:
                continue
            n = _word_count(s)
            if n > 0:
                lengths.append(n)
    n = len(lengths)
    mean = statistics.mean(lengths) if lengths else 0.0
    std = statistics.pstdev(lengths) if n > 1 else 0.0
    cv = (std / mean) if mean else 0.0
    return {"sentences": n, "mean": mean, "std": std, "cv": cv}


def _fmt(v):
    return ("%.2f" % v).rstrip("0").rstrip(".") if v else "0"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=str, nargs="?")
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        return selftest()
    if not args.path:
        print("укажите путь к текстовому файлу", file=sys.stderr)
        return 2
    try:
        with open(args.path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("не читается: %s: %s" % (args.path, exc), file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print("не UTF-8: %s: %s" % (args.path, exc), file=sys.stderr)
        return 2
    r = rhythm(text)
    r = dict(r, mean=round(r["mean"], 3), std=round(r["std"], 3),
             cv=round(r["cv"], 3))
    if args.json:
        json.dump(r, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        if r["sentences"] == 0:
            zone = "нет предложений"
        elif r["cv"] < CV_FLAT:
            zone = "ровный: <%.2f" % CV_FLAT
        else:
            zone = "ориентир живого регистра: >=%.2f" % CV_LIVE_TARGET
        print("CV ритма: %s (предложений: %d, средняя: %s слов, std: %s; %s)"
              % (_fmt(r["cv"]), r["sentences"], _fmt(r["mean"]),
                 _fmt(r["std"]), zone))
    return 0


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    flat = ("Ровный текст состоит из предложений одинаковой длины. "
            "Здесь каждое предложение имеет примерно три слова. "
            "Мы пишем размеренно и ровно. Так мы заполняем строки. "
            "Каждое из таких предложений короткое. " * 5)
    varied = ("Мы выросли. " * 3 +
              "Потом наступил длинный и тяжёлый год, который научил нас "
              "считать деньги, беречь людей и не верить прогнозам. "
              "Коротко. " * 4)
    f = rhythm(flat)
    v = rhythm(varied)
    case("ровный текст даёт низкий CV (< 0.35)", 0 < f["cv"] < 0.35)
    case("чередование длин даёт высокий CV (> 0.45)", v["cv"] > 0.45)
    case("высокий CV выше низкого", v["cv"] > f["cv"])
    e = rhythm("")
    case("пустой ввод — нули без падения",
         e == {"sentences": 0, "mean": 0.0, "std": 0.0, "cv": 0.0})
    one = rhythm("Одно единственное предложение из многих слов.")
    case("одно предложение — std и CV нулевые",
         one["sentences"] == 1 and one["std"] == 0.0 and one["cv"] == 0.0)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
