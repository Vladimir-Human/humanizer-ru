#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_examples.py — гейт честности пар «До/После».

Проверяет главное обещание скилла: правка не дописывает факты за автора.
В варианте «После» не должно появляться проверяемых фактов (чисел, дат,
имён собственных), которых нет в «До».

Два типа пар:
  1. Правка — «**После:**». Новых фактов быть не может.
  2. Образец с данными автора — «**После (с фактами автора):**». Показывает,
     каким станет текст, когда автор подставит свою конкретику.
     Сам скилл такие факты не выдумывает, а запрашивает у автора.

Запуск:
  python3 scripts/check_examples.py
  python3 scripts/check_examples.py --selftest

Только стандартная библиотека.
"""
import argparse
import glob
import io
import os
import re
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGETS = ["SKILL.md", "README.md", "README.en.md",
           os.path.join("references", "test-fixtures-pairs.md"),
           os.path.join("references", "test-fixtures-cases.md")]

NUMWORDS = set("""
один одна одно одного одним два две двух двумя три трех тремя четыре четырех
пять пяти шесть шести семь семи восемь восьми девять девяти десять десяти
одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать
семнадцать восемнадцать девятнадцать
двадцать тридцать сорок пятьдесят шестьдесят семьдесят восемьдесят девяносто
сто ста двести триста четыреста пятьсот шестьсот семьсот восемьсот девятьсот
тысяча тысячи тысяч тысячу тысячей тысячам тысячи
миллион миллиона миллионов миллиону миллионом
миллиард миллиарда миллиардов миллиарду миллиардом
первый первая второе второй вторая третье третий третья четвертый четвертая
пятый пятая шестой шестая седьмой седьмая восьмой восьмая девятый девятая
десятый десятая первого второго третьего четвертого пятого шестого
седьмого восьмого девятого десятого первым вторым третьим четвертым
пятым первым первое второе
двое трое четверо пятеро шестеро семеро восьмеро девятеро десятеро
четырьмя пятью шестью семью восьмью девятью
двум
сотня сотни сотен дюжина дюжины полсотни
тысячами тысячах миллионами миллионах
триллион триллиона триллионов
""".split())

# Заглавные нарицательные, которые не являются проверяемым фактом.
NOT_A_FACT = set("""
Вселенной Вселенная Земля Земли Интернет Интернете
""".split())

WORD_RX = re.compile(r"[а-яё]+")
NUM_RX = re.compile(r"\d+(?:[ \u00a0\u202f]\d{3})*")
_DIGIT_SEP_RX = re.compile(r"[ \u00a0\u202f]")
CAP_RX = re.compile(r"\b([А-ЯЁ][а-яё]{2,}|[А-ЯЁ]{2,}|[A-Z][A-Za-z]+|[A-Z]{2,})\b")
SENT_END = ".!?…:—–«»\"'()[]—"


def _strip_markup(text):
    """Снимает цитатные префиксы и инлайн-разметку."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*>\s?", "", line)
        line = re.sub(r"^\s*[-*]\s+", "", line)
        lines.append(line)
    out = "\n".join(lines)
    # Markdown-ссылки: адрес с числами не факт, текст ссылки сохраняется.
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)
    # Содержимое инлайн-кода участвует в сравнении фактов: снимаются
    # только сами кавычки (урок rev4: `30%` и `Илон Маск` в обратных
    # кавычках раньше выпадали из проверки).
    out = out.replace("`", "")
    out = out.replace("**", "").replace("__", "")
    return out


def _sentence_starts(text):
    """Позиции первых слов предложений — там заглавная не значит имя."""
    starts = set()
    pending = True
    for i, ch in enumerate(text):
        if pending and (ch.isalpha() or ch.isdigit()):
            starts.add(i)
            pending = False
        elif ch in ".!?\n":
            pending = True
    return starts


def extract_facts(text):
    """Извлекает проверяемые факты: числа, числительные, имена собственные."""
    clean = _strip_markup(text)
    facts = set()
    for m in NUM_RX.finditer(clean):
        facts.add(_DIGIT_SEP_RX.sub("", m.group(0)))
    low = clean.lower().replace("ё", "е")
    seq = WORD_RX.findall(low)
    for w in seq:
        if w in NUMWORDS or w.replace("е", "ё") in NUMWORDS:
            facts.add(w)
    # Составное числительное («двадцать пять») — один факт, иначе его
    # компоненты гасятся по отдельности несвязанными числами.
    run = []
    for w in seq + [""]:
        if w in NUMWORDS:
            run.append(w)
        else:
            if len(run) >= 2 and _compound_value(run) is not None:
                facts.add(" ".join(run))
            run = []
    starts = _sentence_starts(clean)
    for m in CAP_RX.finditer(clean):
        if m.start() in starts:
            continue
        if m.group(1) in NOT_A_FACT:
            continue
        facts.add(m.group(1))
    return facts


# Число цифрой и то же число словом — один факт, а не дописка
# («2–3 дня» в «До» и «два-три дня» в «После»). Соответствие только
# по значению: подмена числа на другое число по-прежнему ловится.
DIGIT_WORD_VARIANTS = {
    "0": ("ноль",), "1": ("один", "одна", "одно", "одного", "одним"),
    "2": ("два", "две", "двух", "двумя"),
    "3": ("три", "трех", "тремя"),
    "4": ("четыре", "четырех"), "5": ("пять", "пяти"),
    "6": ("шесть", "шести"), "7": ("семь", "семи"),
    "8": ("восемь", "восьми"), "9": ("девять", "девяти"),
    "10": ("десять", "десяти"),
    "11": ("одиннадцать", "одиннадцати"), "12": ("двенадцать", "двенадцати"),
    "13": ("тринадцать", "тринадцати"), "14": ("четырнадцать", "четырнадцати"),
    "15": ("пятнадцать", "пятнадцати"), "16": ("шестнадцать", "шестнадцати"),
    "17": ("семнадцать", "семнадцати"), "18": ("восемнадцать", "восемнадцати"),
    "19": ("девятнадцать", "девятнадцати"),
    "20": ("двадцать", "двадцати"), "30": ("тридцать", "тридцати"),
    "40": ("сорок",), "50": ("пятьдесят", "пятидесяти"),
    "60": ("шестьдесят", "шестидесяти"), "70": ("семьдесят", "семидесяти"),
    "80": ("восемьдесят", "восьмидесяти"), "90": ("девяносто",),
    "100": ("сто", "ста", "сотни"),
    "1000": ("тысяча", "тысячи", "тысяч", "тысячу", "тысячей"),
    "1000000": ("миллион", "миллиона", "миллионов", "миллиону", "миллионом"),
    "1000000000": ("миллиард", "миллиарда", "миллиардов"),
    "1000000000000": ("триллион", "триллиона", "триллионов"),
    "200": ("двести", "двухсот"),
    "300": ("триста", "трехсот"),
    "400": ("четыреста", "четырехсот"),
    "500": ("пятьсот", "пятисот"),
    "600": ("шестьсот", "шестисот"),
    "700": ("семьсот", "семисот"),
    "800": ("восемьсот", "восьмисот"),
    "900": ("девятьсот", "девятисот"),
}
# «тысячах/тысячам», «миллионах» и соборные числительные — приблизительные
# количества; они сопоставляются цифре по порядку величины.
DIGIT_WORD_VARIANTS["1000"] += ("тысячам", "тысячах")
DIGIT_WORD_VARIANTS["1000000"] += ("миллионах",)
DIGIT_WORD_VARIANTS["100"] += ("сотня", "сотни", "сотен")
DIGIT_WORD_VARIANTS["12"] += ("дюжина", "дюжины")
DIGIT_WORD_VARIANTS["50"] += ("полсотни",)
for _coll, _digit in (("двое", "2"), ("трое", "3"), ("четверо", "4"),
                      ("пятеро", "5"), ("шестеро", "6"), ("семеро", "7"),
                      ("восьмеро", "8"), ("девятеро", "9"), ("десятеро", "10")):
    DIGIT_WORD_VARIANTS[_digit] += (_coll,)
# Все словоформы из карты соответствий — тоже числительные: без этого
# «двадцати», «пятисот» и т.п. не извлекались и эквивалентность молчала.
NUMWORDS |= set(w for ws in DIGIT_WORD_VARIANTS.values() for w in ws)
WORD_TO_DIGIT = {}

# Окончания, которыми словоформа может отличаться от основы: падежные
# (Иван -> Ивана/Ивану/Иваном/Иване) без образования новой сущности.
# Фамильные и топонимические суффиксы (-ов, -ев, -ск, -овка...) сюда не
# входят: «Иван -> Иванов» — другой человек, а не словоформа.
_WORDFORM_SUFFIXES = ("", "а", "я", "у", "ю", "ы", "и", "е", "ой", "ей",
                      "ом", "ем", "ым", "им", "го", "му", "ых", "им",
                      "ами", "ями")


def _same_wordform(a, b):
    """Одна ли словоформа: общая основа и допустимое окончание."""
    if a in NUMWORDS or b in NUMWORDS or a in WORD_TO_DIGIT or b in WORD_TO_DIGIT:
        return False
    if len(a) < 3 or len(b) < 3:
        return False
    if a.startswith(b):
        return a[len(b):] in _WORDFORM_SUFFIXES
    if b.startswith(a):
        return b[len(a):] in _WORDFORM_SUFFIXES
    return False
for _d, _ws in DIGIT_WORD_VARIANTS.items():
    for _w in _ws:
        WORD_TO_DIGIT.setdefault(_w, set()).add(_d)


def _compound_value(words):
    """Значения составного числительного (множество) либо None.

    «двадцать пять» -> {25}, «сто два» -> {102}. Годен только строго
    убывающий порядок разрядов: «два три» (диапазон) и «пять двадцать»
    составными не считаются; «две тысячи двадцать» тоже не склеивается
    (тысяча больше двух) — слова остаются отдельными фактами."""
    variants = []
    for w in words:
        ds = WORD_TO_DIGIT.get(w)
        if not ds:
            return None
        variants.append(sorted(int(d) for d in ds))
    totals = set()

    def walk(i, total, prev):
        if i == len(variants):
            totals.add(total)
            return
        for v in variants[i]:
            if v < prev:
                walk(i + 1, total + v, v)

    walk(0, 0, 10 ** 12)
    return totals or None


def new_facts_split(before, after):
    """Факты, появившиеся в «После» и отсутствующие в «До».

    Возвращает (hard, soft): числа и цифры — жёсткие факты (ошибка),
    имена собственные и прочие слова — мягкие (предупреждение).
    Русская морфология без внешнего анализатора различает словоформы
    лишь частично: жёсткий гейт на именах давал и пропуски дописок,
    и ложные срабатывания на падежах — предупреждения честнее."""
    b_low = _strip_markup(before).lower().replace("ё", "е")
    b_facts = extract_facts(before)
    b_words = set()
    for m in CAP_RX.finditer(_strip_markup(before)):
        b_words.add(m.group(0).lower().replace("ё", "е"))
    for w in WORD_RX.findall(b_low):
        if w in NUMWORDS:
            b_words.add(w)
    after_facts = extract_facts(after)
    comp_words = set()
    for f in after_facts:
        if " " in f:
            comp_words |= set(f.split())
    out = set()
    for f in after_facts - b_facts:
        if f.lower().replace("ё", "е") in comp_words:
            # Слово входит в составное числительное «После»; фактом
            # является составное целиком, а не его части.
            continue
        fl = f.lower().replace("ё", "е")
        # Факт уже есть в «До» как отдельное слово или отдельное число:
        # сравнение по границам, чтобы «12» не пряталось внутри «1234»,
        # а «сто» — внутри «столица».
        if fl.isdigit():
            if re.search(r"(?<!\d)%s(?!\d)" % re.escape(fl), b_low):
                continue
        else:
            if re.search(r"(?<![а-яё0-9])%s(?![а-яё0-9])" % re.escape(fl), b_low):
                continue
        # Число словом, уже присутствующее в «До» цифрой (и наоборот), —
        # тот же факт; только точное соответствие значения.
        if fl in WORD_TO_DIGIT and any(d in b_facts for d in WORD_TO_DIGIT[fl]):
            continue
        if fl.isdigit() and any(w in b_facts for w in DIGIT_WORD_VARIANTS.get(fl, ())):
            continue
        # Составное числительное, уже присутствующее в «До» цифрой:
        # «25 дней» и «двадцать пять дней» — один факт.
        if " " in fl:
            cvs = _compound_value(fl.split())
            if cvs and any(str(v) in b_facts for v in cvs):
                continue
        # Падежные словоформы того же имени — не новый факт: основа
        # совпадает префиксом (Иван -> Ивана, Петров -> Петрова).
        # К числительным префиксное правило не применяется: «пять» —
        # префикс «пятьдесят», но значение другое. Короткие совпадения
        # не считаем, чтобы не склеить разные слова.
        if fl in NUMWORDS or fl in WORD_TO_DIGIT:
            pass
        elif len(fl) >= 3 and any(
            _same_wordform(fl, bl) for bl in b_words
        ):
            continue
        out.add(f)
    def _is_numeric(f):
        # Число цифрой или числительное с известным значением (включая
        # составные) — числовой факт; подмена значения остаётся ошибкой.
        if NUM_RX.fullmatch(f) or f in WORD_TO_DIGIT:
            return True
        return bool(" " in f and _compound_value(f.split()))
    hard = sorted(f for f in out if _is_numeric(f))
    soft = sorted(f for f in out if not _is_numeric(f))
    return hard, soft


def new_facts(before, after):
    """Все новые факты (объединение) — интерфейс для blind_eval."""
    hard, soft = new_facts_split(before, after)
    return sorted(hard + soft)


PAIR_RX = re.compile(
    # «До» и «После» идут до первой пустой строки; пустая строка не
    # обрывает блок, если за ней продолжается цитата (>): так живут
    # многоабзацные примеры. Поясняющая проза без цитат в блок не входит.
    # Двоеточие метки допускается и внутри жирного, и сразу после него
    # («**До:**» и «**До**:</...>»): вариант разметки не должен тихо
    # выключать пару из проверки.
    r"\*\*(?:До|Before)(?::\*\*|\*\*\s*:)(?P<before>.*?)(?=\n\s*\n(?!>)|\Z)\n\s*\n"
    r"\*\*(?:После|After)(?P<label>[^:*]*)(?::\*\*|\*\*\s*:)(?P<after>.*?)"
    r"(?=\n\s*\n(?!>)|\n\s*\n\*\*(?:До|Before|После|After|Что)|\n\s*\n---|\n\s*\n#|\Z)",
    re.S,
)

AUTHOR_LABELS = ("с фактами автора", "author")

# Нижняя граница числа пар при полном прогоне. Гейт проверяет только те пары,
# которые нашёл PAIR_RX: если выражение перестанет совпадать (изменилась
# разметка «До/После», опечатка в шаблоне), проверка молча найдёт ноль пар и
# отчитается «пройден». Порог превращает такое обнуление в громкий отказ.
# Значение взято с запасом ниже фактического (29 пар в версии 3.7.0).
MIN_PAIRS = 10


def check_text(text, path="<text>"):
    errors, warnings, stats = [], [], {"pairs": 0, "edit": 0, "authored": 0}
    for m in PAIR_RX.finditer(text):
        stats["pairs"] += 1
        before = m.group("before").strip()
        after = m.group("after").strip()
        label = (m.group("label") or "").strip().lower()
        line = text[: m.start()].count("\n") + 1
        # Пометка понимается буквально: «author unknown» и прочие
        # случайные подписи со словом author гейт не отключают.
        # Скобки и пробелы нормализуются: в примерах метка живёт в виде
        # «После (с фактами автора):».
        authored = label.strip("() ").strip() in AUTHOR_LABELS
        added = new_facts(before, after)
        if authored:
            stats["authored"] += 1
            if not added:
                warnings.append(
                    "%s:%d: пометка «с фактами автора» излишня: новых фактов нет" % (path, line)
                )
        else:
            stats["edit"] += 1
            hard, soft = new_facts_split(before, after)
            if hard:
                errors.append(
                    "%s:%d: в «После» появились факты, которых нет в «До»: %s"
                    % (path, line, ", ".join(hard))
                )
            if soft:
                warnings.append(
                    "%s:%d: слова-кандидаты в дописанные факты (имена и т.п.; "
                    "морфология проверяется частично): %s"
                    % (path, line, ", ".join(soft))
                )
    return errors, warnings, stats


def selftest():
    ok = True
    clean = "**До:** Галерея выступает в качестве пространства.\n\n**После:** Галерея — это пространство.\n"
    dirty = "**До:** Результаты улучшаются.\n\n**После:** Результаты улучшились на 30%.\n"
    labeled = "**До:** Результаты улучшаются.\n\n**После (с фактами автора):** Результаты улучшились на 30%.\n"
    sent = "**До:** город красив.\n\n**После:** Город красив.\n"
    cases = [
        ("чистая пара проходит", clean, 0),
        ("дописанный факт ловится", dirty, 1),
        ("помеченная пара разрешена", labeled, 0),
        ("заглавная в начале предложения не факт", sent, 0),
    ]
    for name, text, expected in cases:
        errs, _, _ = check_text(text)
        got = len(errs)
        mark = "OK  " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print("[%s] %s (ошибок: %d, ожидалось: %d)" % (mark, name, got, expected))

    # Порог MIN_PAIRS: обнуление PAIR_RX должно валить полный прогон, а не
    # проходить молча. Подменяем выражение на заведомо несовпадающее и
    # вызываем main() без списка файлов — это и есть полный прогон.
    global PAIR_RX
    saved_rx, saved_argv = PAIR_RX, sys.argv
    try:
        PAIR_RX = re.compile(r"(?!x)x")
        sys.argv = ["check_examples.py"]
        rc_blind = main()
    finally:
        PAIR_RX, sys.argv = saved_rx, saved_argv
    blind_ok = rc_blind == 1
    ok = ok and blind_ok
    print("[%s] 0 пар при полном прогоне -> FAIL (код возврата: %d)"
          % ("OK  " if blind_ok else "FAIL", rc_blind))

    # Обратная сторона: единичный файл без пар — законный случай, порог молчит.
    tmp = tempfile.mkdtemp()
    lone = os.path.join(tmp, "без-пар.md")
    with io.open(lone, "w", encoding="utf-8") as fh:
        fh.write(u"# Файл без примеров\n\nПросто текст.\n")
    saved_argv = sys.argv
    try:
        sys.argv = ["check_examples.py", lone]
        rc_lone = main()
    finally:
        sys.argv = saved_argv
    lone_ok = rc_lone == 0
    ok = ok and lone_ok
    print("[%s] отдельный файл без пар не валит порог (код возврата: %d)"
          % ("OK  " if lone_ok else "FAIL", rc_lone))

    print("Самопроверка: " + ("пройдена" if ok else "ПРОВАЛЕНА"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Гейт честности пар До/После")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    files = args.files
    full_run = not files
    if not files:
        files = [os.path.join(ROOT, f) for f in TARGETS if os.path.exists(os.path.join(ROOT, f))]
        files += sorted(glob.glob(os.path.join(ROOT, "references", "*.md")))
    # TARGETS и glob по references/ пересекаются: без дедупликации пары
    # считаются дважды (урок rev3: «34 пары» вместо реальных 32).
    seen, unique = set(), []
    for f in files:
        norm = os.path.normcase(os.path.abspath(f))
        if norm not in seen:
            seen.add(norm)
            unique.append(f)
    files = unique

    all_err, all_warn = [], []
    total = {"pairs": 0, "edit": 0, "authored": 0}
    for path in files:
        # Путь мог прийти из аргументов: сбой чтения — отказ инструмента,
        # код 2, как у сестринских валидаторов, а не traceback.
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
            return 2
        rel = os.path.relpath(path, ROOT)
        errs, warns, stats = check_text(text, rel)
        all_err += errs
        all_warn += warns
        for k in total:
            total[k] += stats[k]

    if full_run and total["pairs"] < MIN_PAIRS:
        all_err.append(
            "полный прогон нашёл пар «До/После»: %d, ожидается не меньше %d — "
            "проверьте PAIR_RX и разметку примеров: гейт мог перестать видеть пары"
            % (total["pairs"], MIN_PAIRS)
        )

    for w in all_warn:
        print("[WARN] " + w)
    for e in all_err:
        print("[FAIL] " + e)
    print(
        "Пар «До/После»: %d (правка: %d, с фактами автора: %d)"
        % (total["pairs"], total["edit"], total["authored"])
    )
    if all_err:
        print("ГЕЙТ ЧЕСТНОСТИ ПРИМЕРОВ: провален (%d)" % len(all_err))
        return 1
    print("ГЕЙТ ЧЕСТНОСТИ ПРИМЕРОВ: пройден")
    return 0


if __name__ == "__main__":
    sys.exit(main())
