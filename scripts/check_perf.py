#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_perf.py — перф-гейт выражений маркеров (docs/REVIEW.md, класс B).

Требование REVIEW.md: выражение не дольше 0.5 с на входе в 30 000 символов.
До этого гейта требование существовало только на словах: ни один валидатор
скорость не мерил, и катастрофический откат мог попасть в CASES незамеченным.

Каждое выражение из check_markers.CASES прогоняется полным finditer по
четырём синтетическим корпусам по 30 000 символов:
  проза      - связный русский текст без маркеров;
  near-miss  - плотные почти-совпадения (самый тяжёлый случай для откатов);
  url        - высокая плотность ссылок и параметров запроса;
  long-line  - одна строка без пробелов (нет точек разрыва для движка).

Плюс короткая ловушка откатов: строка из слов с пробелами, не совпадающая с
выражением до самого конца. Вложенная квантификация вида (?:\w+|\s+)+$ растёт
на ней экспоненциально (замер: 0.0001 с на 6 токенах, 0.0054 с на 12), поэтому
опасное выражение видно на коротком входе за доли секунды. На полных 30 000
символов такое выражение просто не завершилось бы, и гейт с одним лишь большим
корпусом невозможно было бы прогнать до конца.

Берётся лучшее из трёх измерений: цель — поймать катастрофическое поведение
выражения, а не шум загруженной машины.

Запуск:
    python3 scripts/check_perf.py [--budget 0.5] [--verbose]
    python3 scripts/check_perf.py --selftest
Коды возврата: 0 — все выражения в бюджете, 1 — превышение, 2 — ошибка входа.
Только стандартная библиотека.
"""
import os
import re
import sys
import time

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

try:
    from check_markers import CASES
except Exception:  # noqa: BLE001 — запуск не из каталога scripts/
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from check_markers import CASES

CORPUS_SIZE = 30000
DEFAULT_BUDGET = 0.5
REPEATS = 3


def _grow(chunk, size=CORPUS_SIZE):
    """Повторяет образец до нужной длины и обрезает точно по размеру."""
    return (chunk * (size // len(chunk) + 1))[:size]


def make_corpora(size=CORPUS_SIZE):
    """Четыре синтетических корпуса по size символов."""
    prose = _grow(
        u"Утром пошёл дождь, и мы решили остаться дома. "
        u"Кофе закончился, пришлось идти в магазин на углу. "
        u"Продавщица сказала, что привоз будет только к вечеру. ", size)
    near_miss = _grow(
        u"turn0searchX citeturn0 oaicite: contentReferenc "
        u"attached_file grok_render_citation_car <thin> "
        u"utm_source=copilot utm_medium=chat 2025-13-XX Excel+1С ", size)
    # Домены зарезервированы RFC 2606: корпус нужен для плотности ссылок и
    # параметров запроса, а не для воспроизведения примет конкретных моделей.
    urls = _grow(
        u"https://example.org/page?utm_source=news&utm_medium=mail&id=42 "
        u"https://example.net/files/report.pdf?ref=1&token=abcdef "
        u"https://example.com/search?q=test&page=7&sort=date ", size)
    long_line = _grow(u"аaбbвcгdдeеfжgзhиiйjкkлlмmнnоoпpрqсrтsуtфuхvцwчxшyщzъ", size)
    # Ловушка откатов. Намеренно короткая: у выражения с вложенной
    # квантификацией время растёт экспоненциально от числа токенов, поэтому
    # опасное поведение видно уже на 22 токенах, а на 30 000 символов прогон
    # не завершился бы вовсе. Хвост «!» не даёт выражению совпасть до конца
    # строки — именно это запускает полный перебор разбиений.
    backtrack = (u"сл " * 22) + u"!"
    return [
        ("проза", prose),
        ("near-miss", near_miss),
        ("url", urls),
        ("long-line", long_line),
        ("ловушка-откатов", backtrack),
    ]


def measure(pattern, text, repeats=REPEATS):
    """Лучшее из repeats время полного finditer по тексту."""
    rx = re.compile(pattern)
    best = None
    for _ in range(repeats):
        start = time.perf_counter()
        for _m in rx.finditer(text):
            pass
        elapsed = time.perf_counter() - start
        if best is None or elapsed < best:
            best = elapsed
    return best


def run(budget=DEFAULT_BUDGET, cases=None, verbose=False, corpora=None):
    cases = CASES if cases is None else cases
    corpora = make_corpora() if corpora is None else corpora
    if not cases:
        print("[СБОЙ] не удалось получить ни одного выражения из check_markers.CASES")
        return 2
    over, worst = [], []
    for name in sorted(cases):
        pattern = cases[name][0] if isinstance(cases[name], (tuple, list)) else cases[name]
        case_worst, case_corpus = 0.0, ""
        for corpus_name, text in corpora:
            elapsed = measure(pattern, text)
            if elapsed > case_worst:
                case_worst, case_corpus = elapsed, corpus_name
            if elapsed > budget:
                over.append((name, corpus_name, elapsed))
        worst.append((case_worst, name, case_corpus))
        if verbose:
            print("  %-22s %.4f с (%s)" % (name, case_worst, case_corpus))

    worst.sort(reverse=True)
    if over:
        for name, corpus_name, elapsed in over:
            print("[FAIL] %s: %.3f с на корпусе «%s» — бюджет %.3f с"
                  % (name, elapsed, corpus_name, budget))
        print("ПЕРФ-ГЕЙТ: превышение бюджета у %d выражений." % len({o[0] for o in over}))
        return 1
    top = worst[0]
    print("ПЕРФ-ГЕЙТ: %d выражений, вход %d символов, бюджет %.3f с. "
          "Самое медленное: %s — %.4f с (%s). ОК."
          % (len(cases), CORPUS_SIZE, budget, top[1], top[0], top[2]))
    return 0


def selftest():
    checks = []
    corpora = make_corpora()

    big = [c for c in corpora if c[0] != "ловушка-откатов"]
    sizes_ok = all(len(text) == CORPUS_SIZE for _, text in big)
    checks.append(("четыре корпуса по %d символов плюс ловушка откатов" % CORPUS_SIZE,
                   sizes_ok and len(big) == 4 and len(corpora) == 5))

    rc = run(budget=DEFAULT_BUDGET, corpora=corpora)
    checks.append(("эталонный набор укладывается в бюджет", rc == 0))

    # Нулевой бюджет обязан валить гейт: доказательство, что проверка умеет
    # падать, а не только печатать «ОК».
    rc = run(budget=0.0, cases={"zero_width": CASES["zero_width"]}, corpora=corpora)
    checks.append(("budget=0.0 валит гейт", rc == 1))

    # Катастрофический откат: (a+)+$ на входе без совпадения. На таком выражении
    # движок перебирает экспоненциальное число разбиений.
    bomb = {"катастрофический": (r"(a+)+$",)}
    bomb_text = [("бомба", "a" * 24 + "b")]
    start = time.perf_counter()
    rc = run(budget=0.05, cases=bomb, corpora=bomb_text)
    spent = time.perf_counter() - start
    checks.append(("катастрофический откат (a+)+$ пойман", rc == 1 and spent > 0.05))

    # Тот же вход не должен валить нормальное выражение.
    rc = run(budget=0.05, cases={"safe": (r"a+b",)}, corpora=bomb_text)
    checks.append(("безопасное выражение на том же входе проходит", rc == 0))

    # Реалистичный случай: вложенная квантификация с \s — типичная ошибка при
    # правке выражения. Ловится именно на корпусе «ловушка-откатов»: на прозе и
    # на строке без пробелов это выражение выглядит быстрым.
    risky = {"вложенная_квантификация": (r"(?:[a-zA-Zа-яА-Я0-9]+|\s+)+$",)}
    trap = [c for c in corpora if c[0] == "ловушка-откатов"]
    safe_corpora = [c for c in corpora if c[0] == "long-line"]
    rc_trap = run(budget=0.05, cases=risky, corpora=trap)
    rc_safe = run(budget=0.05, cases=risky, corpora=safe_corpora)
    checks.append(("вложенная квантификация ловится ловушкой откатов", rc_trap == 1))
    checks.append(("та же квантификация на строке без пробелов выглядит быстрой",
                   rc_safe == 0))

    # Пустой набор выражений — отказ инструмента (код 2), а не тихий успех.
    rc = run(budget=DEFAULT_BUDGET, cases={}, corpora=corpora)
    checks.append(("пустой набор выражений -> код 2", rc == 2))

    fails = [n for n, p in checks if not p]
    for n, p in checks:
        print(("PASS: " if p else "FAIL: ") + n)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    budget = DEFAULT_BUDGET
    if "--budget" in argv:
        k = argv.index("--budget")
        try:
            budget = float(argv[k + 1])
        except (IndexError, ValueError):
            print("после --budget нужно число секунд")
            return 2
    return run(budget=budget, verbose="--verbose" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
