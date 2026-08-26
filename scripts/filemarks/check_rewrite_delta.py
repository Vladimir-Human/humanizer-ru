#!/usr/bin/env python3
"""check_rewrite_delta.py — прокси остаточного риска перезаписи.

Верификатора снятия статистических (token-sampling) меток публично не
существует, поэтому после перезаписи нельзя сказать «знак снят». Вместо этого
Слой B проверяет, насколько сильно изменился текст: чем больше сохранено
словесных n-грамм и чем меньше изменилась длина, тем больше остаточного
риска, что перезапись прошла поверх исходного распределения.

Метрика — СОВЕЩАТЕЛЬНАЯ, НЕ вердикт «знак снят»: высокое сходство n-грамм —
признак, что перезапись была слабой, но полное расхождение само по себе не
гарантирует необнаружимость. Пороги эвристические (низкий/средний/высокий) и
явно задокументированы ниже.

Вход — два файла (до/после). Считается:
- доля СОХРАНЁННЫХ словесных n-грамм (n=3,4,5) из текста «после», которые
  встречались и в тексте «до»: numerator = сумма сохранённых n-грамм по всем n,
  denominator = сумма всех n-грамм «после» по тем же n; share = numerator/denominator;
- отношение длин после/до в словах;
- остаточный риск: низкий (n-gram overlap < 20% ИЛИ длина изменилась > ±30%);
  средний (20–40%); высокий (> 40%). Пороги эвристические.

Запуск:
    python3 scripts/filemarks/check_rewrite_delta.py до.txt после.txt
    python3 scripts/filemarks/check_rewrite_delta.py до.txt после.txt --json
    python3 scripts/filemarks/check_rewrite_delta.py --selftest

Коды возврата: 0 — прогон выполнен, 1 — провал самопроверки, 2 — ошибка входа.
Только стандартная библиотека.
"""
import argparse
import json
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

_WORD_RX = re.compile(r"[а-яА-ЯёЁa-zA-Z\d-]+")
_N_GRAMS = (3, 4, 5)

# Эвристические пороги остаточного риска (СОВЕЩАТЕЛЬНАЯ метрика, не вердикт).
LOW_OVERLAP = 0.20
HIGH_OVERLAP = 0.40
LEN_CHANGE_PCT = 30.0  # длина изменилась сильнее этого (±) — низкий риск


def _words(text):
    return _WORD_RX.findall(text.lower())


def _ngrams(words, n):
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def _build_index(before_words, n):
    """Множество n-грамм «до» для быстрой проверки сохранности."""
    return set(_ngrams(before_words, n))


def overlap(before, after):
    """Доля словесных n-грамм (3,4,5) текста «after», сохранённых в «before».

    Суммируем сохранённые и общие n-граммы по всем n; share = сохр/общее.
    Пустой текст «after» → 0.0.
    """
    before_words = _words(before)
    after_words = _words(after)
    idx = {n: _build_index(before_words, n) for n in _N_GRAMS}
    saved = 0
    total = 0
    for n in _N_GRAMS:
        for g in _ngrams(after_words, n):
            total += 1
            if g in idx[n]:
                saved += 1
    return (saved / total) if total else 0.0


def risk_level(share, len_ratio):
    """Остаточный риск по эвристическим порогам.

    len_ratio = words_after / words_before. Если длина изменилась сильнее чем
    на LEN_CHANGE_PCT в любую сторону — считаем низким риском (текст сильно
    перестроен), независимо от доли сохранённых n-грамм.
    """
    if len_ratio < 1.0 / (1.0 + LEN_CHANGE_PCT / 100.0) \
            or len_ratio > 1.0 + LEN_CHANGE_PCT / 100.0:
        return "низкий"
    if share < LOW_OVERLAP:
        return "низкий"
    if share <= HIGH_OVERLAP:
        return "средний"
    return "высокий"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("before", type=str, nargs="?")
    p.add_argument("after", type=str, nargs="?")
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        return selftest()
    if not args.before or not args.after:
        print("укажите два файла: до и после", file=sys.stderr)
        return 2
    try:
        with open(args.before, encoding="utf-8") as fh:
            before = fh.read()
        with open(args.after, encoding="utf-8") as fh:
            after = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("не читается вход: %s" % exc, file=sys.stderr)
        return 2
    share = overlap(before, after)
    bw, aw = len(_words(before)), len(_words(after))
    ratio = (aw / bw) if bw else 0.0
    level = risk_level(share, ratio)
    payload = {"n_gram_overlap": round(share, 4),
               "words_before": bw, "words_after": aw,
               "len_ratio": round(ratio, 3),
               "risk": level,
               "note": ("совещательная метрика, НЕ вердикт «знак снят»; "
                        "верификатора статистических меток не существует")}
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print("остаточный риск: %s (совпадение n-грамм %.0f%%, "
              "длина после/до %.2f — совещательная метрика, не вердикт)"
              % (level, share * 100.0, ratio))
    return 0


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    text = ("Команда планирует расширить производство и выйти на новые рынки "
            "уже в следующем отчётном квартале этого года. "
            "Мы рассчитываем на устойчивый рост спроса и новые партнёрства.")
    identical = overlap(text, text)
    case("идентичные файлы — почти полное совпадение n-грамм",
         0.9 < identical <= 1.0)
    case("идентичные файлы — высокий риск",
         risk_level(identical, 1.0) == "высокий")
    rewritten = ("Мы сначала не верили. Потом всё изменилось. "
                 "За год мы научились считать деньги. И вот теперь — рост.")
    low = overlap(text, rewritten)
    case("полностью переписанный — низкая доля n-грамм",
         low < LOW_OVERLAP)
    case("полностью переписанный — низкий риск",
         risk_level(low, 1.0) == "низкий")
    case("пустой после — нулевой риск",
         risk_level(overlap(text, ""), 0.0) == "низкий")
    # Неверное ожидание порога — кейс «умеет падать»: если доля между
    # 20–40%, риск обязан быть средним, а не высоким.
    mid = 0.30
    case("доля 30% и длина без изменений — средний риск (не высокий)",
         risk_level(mid, 1.0) == "средний")
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
