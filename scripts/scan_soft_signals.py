#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_soft_signals.py — измеримый счётчик мягких признаков машинного текста.

Regex-маркеры (check_markers.py) ловят артефакты копирования из интерфейсов,
но русскоязычные модели таких артефактов почти не оставляют: парный прогон
2026-07-26 показал ноль срабатываний на выводах GigaChat и Алисы. Мягкий слой
(паттерны #1–#25 из references/) до сих пор считался только глазами. Этот
скрипт делает его счётным: находит кандидатов по четырём категориям и считает
их по правилам дерева решений SKILL.md.

Что скрипт НЕ делает — вердикт об авторстве. Он печатает кандидатов с цитатами
и рекомендацию объёма правки по порогам дерева решений. Главное правило
(SKILL.md) и границы ложных срабатываний (references/false-positives.md)
остаются за человеком или агентом.

Правила счёта — из дерева решений SKILL.md:
- каждый паттерн считается один раз на текст; число вхождений влияет на объём
  правки, не на вердикт;
- все признаки из одной категории — стилистическая особенность, вердикт об
  авторстве не выносится;
- пороги объёма правки: 0–2 признака — не править; 3–5 из двух и более
  категорий — выборочная правка; 6 и более — переписывание с сохранением фактов.

Жанр (--genre) выключает признаки, которые для жанра являются нормой, по
references/false-positives.md: художественная проза — правило трёх и плотность
тире; академический текст — «является», каскад оговорок, связки, отрицательные
параллелизмы; юридический — мягкие признаки не считаются вовсе (правится
только класс A, см. дерево решений).

Пороги внутри детекторов подобраны консервативно и записаны в REGISTRY явно:
это ориентиры уровня O (наблюдение), как в quantitative-heuristics.md, а не
корпусные константы.

Запуск:
    python3 scripts/scan_soft_signals.py файл1.txt [файл2.md ...]
    python3 scripts/scan_soft_signals.py файл.md --genre fiction
    python3 scripts/scan_soft_signals.py файл.md --json
    python3 scripts/scan_soft_signals.py --selftest

Флаги:
    --genre {neutral,fiction,legal,academic,marketing,chat}  жанр текста
    --plain-text   текст предназначен для среды без Markdown: следы разметки
                   (#20) считаются признаком, а не оформлением
    --json         машиночитаемый отчёт вместо текстового
    --fail-at N    код возврата 1, если признаков не меньше N (для сценариев CI)

Коды возврата: 0 — прогон выполнен (наличие находок не ошибка), 1 — провал
самопроверки или порога --fail-at, 2 — ошибка входа. Только стандартная
библиотека.
"""
import argparse
import json
import os
import re
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

CONTENT, LANGUAGE, STRUCTURE, COMMUNICATION = (
    "содержательная", "языковая", "структурная", "коммуникативная")

GENRES = ("neutral", "fiction", "legal", "academic", "marketing", "chat")

# Жанровые исключения — по дереву решений SKILL.md и false-positives.md.
# Точечные исключения отдельных фраз внутри детектора: false-positives.md
# §4 («погрузиться» в академическом тексте) и §11 («играет важную роль» —
# затёртое, но допустимое академическое клише).
GENRE_PHRASE_EXCLUDES = {
    "academic": {
        "ai_lexicon": ["погрузиться"],
        "significance": ["играет важную роль"],
    },
}
SUPPRESS = {
    "neutral": set(),
    "fiction": {"rule_of_three", "emdash_bold"},
    "legal": None,  # особый случай: мягкие признаки не считаются вовсе
    "academic": {"est_avoidance", "mitigation_cascade", "link_fillers",
                 "neg_parallel"},
    "marketing": set(),
    "chat": {"quotes_style", "sentence_rhythm"},
}


def _norm(text):
    """Нормализация для поиска фраз: нижний регистр, е вместо ё."""
    return text.lower().replace("\u0451", "\u0435")


def _phrase_rx(phrases):
    """Компилирует список фраз в одно выражение по нормализованному тексту.

    Фраза с завершающей «*» — основа слова (допускает окончание).
    Границы: слева и справа не должно быть буквы, чтобы «в целом» не ловился
    внутри «в целомудрии».
    """
    parts = []
    for p in phrases:
        p = _norm(p)
        stem = p.endswith("*")
        body = re.escape(p[:-1] if stem else p).replace(r"\ ", r"\s+")
        tail = r"[а-яa-z]*" if stem else ""
        parts.append(body + tail)
    return re.compile(r"(?<![а-яa-z])(?:%s)(?![а-яa-z])" % "|".join(parts))


_SENT_SPLIT_RX = re.compile(r"(?<=[.!?\u2026])\s+")
_WORD_RX = re.compile(r"[а-яА-ЯёЁa-zA-Z\d-]+")
_LIST_LINE_RX = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
_FENCED_RX = re.compile(r"(?ms)^[ \t]*(?:```|~~~).*?(?:^[ \t]*(?:```|~~~)[ \t]*$|\Z)")
_TABLE_ROW_RX = re.compile(r"(?m)^[ \t]*\|.*$")
_HEADING_RX = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_EMOJI_RX = "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2705\u2728\u274C\u2757\u2B50]"


def _fenced_lines(text):
    """Номера строк внутри блоков кода ``` — их детекторы разметки
    не считают: bash-комментарий «# раздел» не заголовок."""
    inside = set()
    fence = False
    for n, l in enumerate(text.splitlines(), 1):
        if l.lstrip().startswith("```"):
            fence = not fence
            inside.add(n)
            continue
        if fence:
            inside.add(n)
    return inside


def _prose(text):
    """Текст без блоков кода и строк таблиц — для количественных осей."""
    return _TABLE_ROW_RX.sub("", _FENCED_RX.sub("", text))


def _sentences(text):
    out = []
    for line in _prose(text).splitlines():
        line = line.strip()
        if not line or _LIST_LINE_RX.match(line) or line.startswith("#"):
            continue
        for s in _SENT_SPLIT_RX.split(line):
            s = s.strip()
            if len(_WORD_RX.findall(s)) >= 2:
                out.append(s)
    return out


def _find_phrases(lines, rx):
    hits = []
    for lineno, line in enumerate(lines, 1):
        for m in rx.finditer(_norm(line)):
            hits.append((lineno, line.strip()[:90]))
    return hits


def _make_phrase_finder(phrases):
    rx = _phrase_rx(phrases)

    def finder(text, lines):
        return _find_phrases(lines, rx)

    finder.prose_mask = True
    return finder


# --------------------------------------------------------------- сложные детекторы

_SOFTENERS = _phrase_rx(["возможно", "вероятно", "по-видимому", "как правило",
                         "в некоторых случаях", "в зависимости от", "обычно",
                         "в большинстве", "скорее всего",
                         "при определенных условиях"])


def _mitigation(text, lines):
    hits = []
    for lineno, line in enumerate(lines, 1):
        for s in _SENT_SPLIT_RX.split(line):
            if len(_SOFTENERS.findall(_norm(s))) >= 3:
                hits.append((lineno, s.strip()[:90]))
    return hits


_NEG_PAR_RX = re.compile(
    r"не\s+только[^.!?\n]{1,120}?,?\s*но\s+и|"
    r"(?:это\s+)?не\s+просто[^.!?\n]{1,80}?,\s*а\s|"
    r"больше,?\s+чем\s+просто|не\s+столько[^.!?\n]{1,80}?,\s*сколько")


def _neg_parallel(text, lines):
    return _find_phrases(lines, _NEG_PAR_RX)


_ITEM = r"[а-яa-z\d\u0451-]+(?:\s+[а-яa-z\d\u0451-]+){0,2}"
_TRIPLE_RX = re.compile(r"(?<![а-яa-z\d\u0451,-])%s,\s+%s\s+и\s+%s" % (_ITEM, _ITEM, _ITEM))


def _rule_of_three(text, lines):
    hits = []
    for lineno, line in enumerate(lines, 1):
        norm = _norm(line)
        for m in _TRIPLE_RX.finditer(norm):
            # Четвёрки и длиннее не считаем: совпадение может начинаться
            # с пробела после запятой («a, b, c и d» ловится с «b»),
            # поэтому запятую ищем за пробелами перед совпадением.
            j = m.start() - 1
            while j >= 0 and norm[j] in " \t":
                j -= 1
            if j >= 0 and norm[j] == ",":
                continue
            # Четвёрки вида «X, Y и Z, W» считаются: риторическая тройка
            # в них присутствует, а запятая после третьего члена может
            # начинать придаточное («…и тестирование, что подтверждено») —
            # выключать совпадение по запятой означало бы терять тройки.
            # Чисто числовые перечисления (годы, номера) — не риторика:
            # если каждый элемент тройки несёт цифру, это перечисление
            # чисел с обвязкой («вышли в 2019, 2020 и 2021 годах»),
            # а не риторическое правило трёх.
            parts = [p for p in re.split(r",\s+|\s+и\s+", m.group(0)) if p]
            if parts and all(re.search(r"\d", p) for p in parts):
                continue
            hits.append((lineno, line.strip()[:90]))
    return hits


_mitigation.prose_mask = True
_neg_parallel.prose_mask = True


_UNAVAILABLE = _phrase_rx(["не раскрывается", "не раскрываются",
                           "не публикуется", "не публикуются",
                           "не является общедоступной", "данные недоступны"])
_SPECULATION = _phrase_rx(["однако, вероятно", "скорее всего",
                           "можно предположить", "по-видимому", "по всей видимости"])


def _unavailable_speculation(text, lines):
    hits = []
    for lineno, line in enumerate(lines, 1):
        for s in _SENT_SPLIT_RX.split(line):
            n = _norm(s)
            if _UNAVAILABLE.search(n) and _SPECULATION.search(n):
                hits.append((lineno, s.strip()[:90]))
    return hits


_STRAIGHT_Q_RX = re.compile(r'"[^"\n]{2,}"')


def _quotes_style(text, lines):
    hits = []
    for lineno, line in enumerate(lines, 1):
        if not re.search(r"[а-яА-ЯёЁ]", line):
            continue
        for m in _STRAIGHT_Q_RX.finditer(line):
            hits.append((lineno, line.strip()[:90]))
    return hits


_EMOJI_ITEM_RX = re.compile(r"^\s*(?:[-*\u2022]\s*)?%s+\s*(?:\*\*|[А-ЯЁA-Z])" % _EMOJI_RX)


def _emoji_lists(text, lines):
    blocked = _fenced_lines(text)
    return [(n, l.strip()[:90]) for n, l in enumerate(lines, 1)
            if n not in blocked and _EMOJI_ITEM_RX.match(l)]


_BOLD_RX = re.compile(r"\*\*[^*\n]+\*\*")
_DASH = "\u2014"


def _dash_and_bold(text, lines):
    """Паттерн #16: плотность длинных тире (ось 2) либо перегруз жирным."""
    prose = _prose(text)
    hits = []
    dashes = prose.count(_DASH)
    if len(prose) >= 500 and dashes >= 4 and dashes * 1000.0 / len(prose) > 6.0:
        for n, l in enumerate(lines, 1):
            if l.count(_DASH) >= 2:
                hits.append((n, l.strip()[:90]))
        if not hits:
            hits.append((1, "плотность длинных тире выше 6 на 1000 знаков"))
    bold = _BOLD_RX.findall(prose)
    if len(bold) >= 8:
        hits.append((1, "жирным выделено %d фрагментов" % len(bold)))
    return hits


def _tiny_tables(text, lines):
    blocked = _fenced_lines(text)
    hits = []
    i = 0
    while i < len(lines) - 1:
        if i + 1 in blocked:
            i += 1
            continue
        if lines[i].lstrip().startswith("|") and re.match(
                r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            rows = 0
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows += 1
                j += 1
            if 1 <= rows <= 3:
                hits.append((i + 1, lines[i].strip()[:90]))
            i = j
        else:
            i += 1
    return hits


def _heading_levels(lines):
    out = []
    for n, l in enumerate(lines, 1):
        m = _HEADING_RX.match(l)
        if m:
            out.append((n, len(m.group(1)), m.group(2)))
    return out


def _heading_hierarchy(text, lines):
    blocked = _fenced_lines(text)
    heads = [h for h in _heading_levels(lines) if h[0] not in blocked]
    hits = []
    h1 = [h for h in heads if h[1] == 1]
    if len(h1) > 1:
        hits.append((h1[1][0], "второй заголовок H1: %s" % h1[1][2][:70]))
    for (n1, lv1, _t1), (n2, lv2, t2) in zip(heads, heads[1:]):
        if lv2 - lv1 >= 2:
            hits.append((n2, "прыжок H%d -> H%d: %s" % (lv1, lv2, t2[:60])))
    return hits


_CAP_WORD_RX = re.compile(r"^[А-ЯЁ][а-яё]+$")


def _title_case(text, lines):
    blocked = _fenced_lines(text)
    hits = []
    for n, lv, title in _heading_levels(lines):
        if n in blocked:
            continue
        words = title.split()
        caps = sum(1 for w in words[1:] if _CAP_WORD_RX.match(w))
        if caps >= 2:
            hits.append((n, title[:90]))
    return hits


def _markdown_traces(text, lines):
    hits = []
    for n, l in enumerate(lines, 1):
        if _HEADING_RX.match(l) or _BOLD_RX.search(l) or \
                re.search(r"\[[^\]\n]+\]\([^)\s]+\)", l):
            hits.append((n, l.strip()[:90]))
    return hits


def _sentence_rhythm(text, lines):
    sents = _sentences(text)
    if len(sents) < 10:
        return []
    counts = [len(_WORD_RX.findall(s)) for s in sents]
    mid = sum(1 for c in counts if 15 <= c <= 25)
    if min(counts) >= 10 and mid / float(len(counts)) >= 0.7:
        return [(1, "из %d предложений %d лежат в 15-25 словах, коротких нет"
                 % (len(counts), mid))]
    return []


def _list_share(text, lines):
    nonempty = [l for l in lines if l.strip()]
    if not nonempty:
        return []
    listed = [l for l in nonempty if _LIST_LINE_RX.match(l)]
    if len(listed) >= 6 and len(listed) / float(len(nonempty)) > 0.4:
        return [(1, "%d из %d непустых строк — пункты списков"
                 % (len(listed), len(nonempty)))]
    return []


_OPENERS = _phrase_rx(["кроме того", "более того", "важно отметить",
                       "стоит отметить", "следует отметить", "таким образом",
                       "однако", "в целом", "вместе с тем", "при этом", "также"])


def _paragraph_openers(text, lines):
    paras = [p.strip() for p in re.split(r"\n\s*\n", _prose(text)) if p.strip()]
    opened = []
    for p in paras:
        first = " ".join(p.split()[:3])
        opened.append(bool(_OPENERS.match(_norm(first))))
    best = run = 0
    for flag in opened:
        run = run + 1 if flag else 0
        best = max(best, run)
    if best >= 3 or sum(opened) >= 4:
        frags = [(1, "однотипные зачины у %d абзацев (подряд: %d)"
                  % (sum(opened), best))]
        return frags
    return []


def _cutoff(text, lines):
    stripped = text.rstrip()
    if not stripped:
        return []
    last = stripped.splitlines()[-1].strip()
    if len(_WORD_RX.findall(last)) < 4 or last.startswith(("#", "|", "-", "*")):
        return []
    if stripped[-1] not in ".!?\u2026\u00bb\u201d\")»;:":
        return [(len(lines), "текст обрывается: …%s" % last[-70:])]
    return []


# --------------------------------------------------------------- реестр детекторов

# Поля: id, категория, паттерн (ссылка на references/), критичность,
# min_hits (сколько вхождений нужно, чтобы признак был засчитан), finder,
# pos/neg — встроенные образцы самопроверки. Обнулённый детектор ловится
# самопроверкой: каждый pos обязан сработать (урок count_style_markers 3.7.3).
_AI_LEXICON_PHRASES = [
    "безусловно", "крайне важно", "более того", "следует отметить",
    "стоит подчеркнуть", "важно подчеркнуть", "синерги*",
    "многогранн*", "всеобъемлющ*", "в контексте", "погрузиться",
    "раскрыть потенциал", "по сути", "комплексный подход"]

_SIGNIFICANCE_PHRASES = [
    "является свидетельством", "знаменует собой",
    "подчеркивает важность", "играет ключевую роль",
    "играет важную роль", "играет решающую роль",
    "закладывает фундамент", "неизгладимый след",
    "в постоянно меняющемся ландшафте", "поворотный момент",
    "непреходящее значение", "оставил глубокий след", "стал вехой",
    "отражает более широкие тенденции"]


REGISTRY = [
    dict(id="significance", cat=CONTENT, pat="#2 раздувание значимости",
         crit="средняя", min_hits=2, phrases=_SIGNIFICANCE_PHRASES,
         finder=_make_phrase_finder(_SIGNIFICANCE_PHRASES),
         pos="Открытие завода знаменует собой поворотный момент и играет ключевую роль.",
         neg="Завод открылся в 1989 году и начал выпускать насосы."),
    dict(id="media_mentions", cat=CONTENT, pat="#3 акцент на медийности",
         crit="средняя", min_hits=1,
         finder=_make_phrase_finder([
             "широко освещался в СМИ", "получил признание экспертов",
             "упоминался в ведущих изданиях",
             "активно присутствует в социальных сетях",
             "независимые источники подтверждают"]),
         pos="Проект широко освещался в СМИ и получил признание экспертов.",
         neg="О проекте написали два местных издания: подробности в архиве."),
    dict(id="promo", cat=CONTENT, pat="#5 рекламный язык",
         crit="средняя", min_hits=2,
         finder=_make_phrase_finder([
             "уникальн*", "инновационн*", "революционн*",
             "не имеющий аналогов", "жемчужина", "идеальное место",
             "богатая палитра", "гармоничное сочетание", "живописн*",
             "аутентичн*", "обязательный к посещению"]),
         pos="Уникальный город — настоящая жемчужина в живописном месте.",
         neg="Город известен рынком по субботам и церковью."),
    dict(id="vague_experts", cat=CONTENT, pat="#6 размытые атрибуции",
         crit="высокая", min_hits=1,
         finder=_make_phrase_finder([
             "эксперты считают", "по мнению специалистов",
             "исследователи отмечают", "критики указывают",
             "наблюдатели полагают", "ряд аналитиков",
             "многие источники подтверждают"]),
         pos="Эксперты считают, что река важна. Исследователи отмечают её характер.",
         neg="По данным исследования 2019 года, в реке обитают эндемики."),
    dict(id="challenges", cat=CONTENT, pat="#7 вызовы и перспективы",
         crit="низкая", min_hits=1,
         finder=_make_phrase_finder([
             "сталкивается с рядом вызовов", "несмотря на эти трудности",
             "продолжает процветать", "будущее выглядит многообещающим",
             "перспективы развития остаются"]),
         pos="Несмотря на эти трудности, город продолжает процветать.",
         neg="После открытия IT-парков пробки усилились."),
    dict(id="bureaucratese", cat=CONTENT, pat="#8 канцелярит",
         crit="средняя", min_hits=3,
         finder=_make_phrase_finder([
             "осуществля*", "производить оплату", "вышеуказанн*",
             "нижеследующ*", "в целях обеспечения", "посредством",
             "на основании имеющ*", "в рамках реализации"]),
         pos=("Организация осуществляет деятельность в рамках реализации "
              "программы в целях обеспечения качества."),
         neg="Мы консультируем клиентов, опираясь на свой опыт."),
    dict(id="academic_cliche", cat=CONTENT, pat="#9a академические клише",
         crit="средняя", min_hits=1,
         finder=_make_phrase_finder([
             "актуальность темы обусловлена", "целью данной работы является",
             "в данной работе рассматривается",
             "по результатам исследования можно сделать вывод",
             "на основании вышеизложенного",
             "поставленные задачи были успешно решены"]),
         pos="Актуальность темы обусловлена возрастающей ролью технологий.",
         neg="В работе разбирается, как удалёнка изменила занятость."),
    dict(id="ai_lexicon", cat=LANGUAGE, pat="#10 машинная лексика",
         crit="высокая", min_hits=4, phrases=_AI_LEXICON_PHRASES,
         finder=_make_phrase_finder(_AI_LEXICON_PHRASES),
         pos=("Безусловно, крайне важно раскрыть потенциал синергии. Более "
              "того, в контексте комплексного подхода это по сути главное."),
         neg="Важно, чтобы все элементы работали вместе."),
    dict(id="est_avoidance", cat=LANGUAGE, pat="#11 избегание «есть/это»",
         crit="средняя", min_hits=3,
         finder=_make_phrase_finder([
             "является", "представляет собой", "выступает в качестве",
             "функционирует как"]),
         pos=("Галерея является пространством. Зал представляет собой сцену. "
              "Фойе выступает в качестве буфета."),
         neg="Галерея — это выставочное пространство."),
    dict(id="neg_parallel", cat=LANGUAGE, pat="#12 отрицательные параллелизмы",
         crit="средняя", min_hits=2, finder=_neg_parallel,
         pos=("Это не просто инструмент, а революция. Он не только ускоряет "
              "работу, но и делает её прозрачнее."),
         neg="Инструмент ускоряет работу и делает её прозрачнее."),
    dict(id="rule_of_three", cat=LANGUAGE, pat="#13 правило трёх",
         crit="высокая", min_hits=3, finder=_rule_of_three,
         pos=("Будут доклады, дискуссии и нетворкинг. Ждём инновации, "
              "вдохновение и инсайты. Обещают еду, музыку и призы."),
         neg="Будут доклады и дискуссии. Между сессиями можно пообщаться."),
    dict(id="mitigation_cascade", cat=LANGUAGE, pat="#15b каскад смягчений",
         crit="средняя", min_hits=1, finder=_mitigation,
         pos=("Возможно, в некоторых случаях, в зависимости от подхода, это "
              "может оказаться полезным."),
         neg="Возможно, стратегия сработает: в исследовании конверсия выросла."),
    dict(id="link_fillers", cat=LANGUAGE, pat="#15c связки-затычки",
         crit="средняя", min_hits=2,
         finder=_make_phrase_finder([
             "однако стоит отметить", "при этом важно понимать",
             "тем не менее, нельзя забывать", "кроме того, следует подчеркнуть",
             "в заключение хочется отметить", "подводя итог, можно сказать",
             "резюмируя вышесказанное", "таким образом, мы видим"]),
         pos=("Однако стоит отметить, что есть пределы. В заключение хочется "
              "отметить, что выбор за вами."),
         neg="У подхода есть ограничения. Выбор зависит от контекста."),
    dict(id="anglicism_shift", cat=LANGUAGE, pat="#15e сдвиг через английское поле",
         crit="средняя", min_hits=1,
         finder=_make_phrase_finder([
             "адресовать проблему", "адресовать вопрос", "доставить ценность",
             "основание науки", "делает разницу"]),
         pos="Команда планирует адресовать проблему в следующем спринте.",
         neg="Команда решит проблему в следующем спринте."),
    dict(id="paragraph_openers", cat=LANGUAGE, pat="ось 3: зачины абзацев",
         crit="низкая", min_hits=1, finder=_paragraph_openers,
         pos=("Кроме того, продукт быстрый.\n\nБолее того, он дешёвый.\n\n"
              "Таким образом, он выгодный.\n\nОднако есть нюанс."),
         neg="Продукт быстрый.\n\nЦена ниже рынка.\n\nЕсть один нюанс."),
    dict(id="emdash_bold", cat=STRUCTURE, pat="#16 тире и жирный (ось 2)",
         crit="высокая", min_hits=1, finder=_dash_and_bold,
         pos=("Решение — ключ к успеху — оно меняет всё — сразу. " * 12),
         neg=("Решение упрощает работу. Команда довольна результатом. " * 12)),
    dict(id="emoji_lists", cat=STRUCTURE, pat="#17 эмодзи-списки",
         crit="высокая", min_hits=2, finder=_emoji_lists,
         pos="\U0001F680 **Скорость:** быстро.\n\U0001F4A1 **Идея:** новый подход.",
         neg="- Скорость: быстро.\n- Идея: новый подход."),
    dict(id="quotes_style", cat=STRUCTURE, pat="#18 кавычки-лапки",
         crit="средняя", min_hits=3, finder=_quotes_style,
         pos=('Проект "Восход" запустил "умный" сервис "по-новому".'),
         neg="Проект «Восход» запустил «умный» сервис."),
    dict(id="tiny_tables", cat=STRUCTURE, pat="#19 избыточные таблицы",
         crit="высокая", min_hits=1, finder=_tiny_tables,
         pos="| Параметр | Значение |\n|---|---|\n| Цвет | Синий |\n| Размер | Большой |",
         neg=("| Модель | Цена | Вес | Год | Тип |\n|---|---|---|---|---|\n" +
              "\n".join("| m%d | %d | %d | %d | t |" % (i, i, i, i)
                        for i in range(1, 7)))),
    dict(id="markdown_traces", cat=STRUCTURE, pat="#20 следы Markdown",
         crit="высокая", min_hits=2, finder=_markdown_traces,
         pos="# Заголовок\nТекст со **звёздочками** и [ссылкой](https://example.org).",
         neg="Обычное письмо без разметки. Спасибо за встречу."),
    dict(id="heading_hierarchy", cat=STRUCTURE, pat="#21 иерархия заголовков",
         crit="высокая", min_hits=1, finder=_heading_hierarchy,
         pos="# Главный\n\n### Сразу третий уровень\n",
         neg="# Главный\n\n## Второй уровень\n\n### Третий\n"),
    dict(id="title_case", cat=STRUCTURE, pat="#21a Каждое Слово С Прописной",
         crit="высокая", min_hits=1, finder=_title_case,
         pos="## Ранняя Жизнь и Образование\n",
         neg="## История МГУ имени Ломоносова\n"),
    dict(id="sentence_rhythm", cat=STRUCTURE, pat="ось 1: ровный ритм",
         crit="низкая", min_hits=1, finder=_sentence_rhythm,
         pos=" ".join(
             "Команда планирует расширить производство и выйти на новые рынки "
             "уже в следующем отчётном квартале этого года." for _ in range(12)),
         neg=("Мы выросли. " * 3 +
              "Потом наступил длинный и тяжёлый год, который научил нас "
              "считать деньги, беречь людей и не верить прогнозам. Коротко. " * 4)),
    dict(id="list_share", cat=STRUCTURE, pat="ось 4: доля списков",
         crit="низкая", min_hits=1, finder=_list_share,
         pos="Вступление.\n" + "\n".join("- пункт %d" % i for i in range(1, 8)),
         neg="Абзац один.\nАбзац два.\nАбзац три.\n- единственный пункт"),
    dict(id="chat_remnants", cat=COMMUNICATION, pat="#22 остатки реплик",
         crit="высокая", min_hits=1,
         finder=_make_phrase_finder([
             "надеюсь, это поможет", "дайте знать", "конечно!", "разумеется!",
             "с удовольствием!", "буду рад помочь", "хотите, чтобы я",
             "[вставьте", "[укажите", "[добавьте ссылку", "[требуется источник"]),
         pos="Вот обзор. Надеюсь, это поможет! Дайте знать, если что.",
         neg="Обзор занимает две страницы и охватывает 2019–2024 годы."),
    dict(id="knowledge_disclaimers", cat=COMMUNICATION, pat="#23 оговорки о знаниях",
         crit="средняя", min_hits=1,
         finder=_make_phrase_finder([
             "на момент моего обучения",
             "по состоянию на момент обновления",
             "хотя конкретные детали ограничены",
             "на основе доступной информации",
             "в предоставленных результатах поиска"]),
         pos="Хотя конкретные детали ограничены, компания создана в 1990-х.",
         neg="Согласно регистрационным документам, компания основана в 1994 году."),
    dict(id="unavailable_speculation", cat=COMMUNICATION,
         pat="#23a недоступность со спекуляцией", crit="средняя", min_hits=1,
         finder=_unavailable_speculation,
         pos=("Выручка не раскрывается, однако, вероятно, она составляет "
              "сотни миллионов."),
         neg="Компания не публикует финансовую отчётность."),
    dict(id="flattery", cat=COMMUNICATION, pat="#24 льстивый тон",
         crit="средняя", min_hits=1,
         finder=_make_phrase_finder([
             "отличный вопрос", "прекрасное замечание", "вы абсолютно правы",
             "замечательно, что вы", "это очень глубокая мысль"]),
         pos="Отличный вопрос! Вы абсолютно правы, тема сложная.",
         neg="Экономические факторы здесь действительно релевантны."),
    dict(id="positive_conclusions", cat=COMMUNICATION, pat="#25 общие позитивные выводы",
         crit="средняя", min_hits=1,
         finder=_make_phrase_finder([
             "будущее выглядит светлым", "впереди захватывающие времена",
             "это только начало", "возможности безграничны",
             "шаг в правильном направлении", "путь к совершенству"]),
         pos="Будущее выглядит светлым, и это только начало.",
         neg="Компания планирует открыть два филиала в следующем году."),
    dict(id="mid_cutoff", cat=COMMUNICATION, pat="#25a обрыв на полуслове",
         crit="средняя", min_hits=1, finder=_cutoff,
         pos="Итоги квартала обнадёживают. Кроме того, компания планирует расширить",
         neg="Итоги квартала обнадёживают. Компания планирует расширение."),
]

_IDS = [d["id"] for d in REGISTRY]
assert len(_IDS) == len(set(_IDS)), "дубль id в REGISTRY"


# --------------------------------------------------------------- прогон

def analyze(text, genre="neutral", plain_text=False):
    """Возвращает отчёт-словарь по одному тексту."""
    if genre not in GENRES:
        raise ValueError("неизвестный жанр: %s" % genre)
    lines = text.splitlines() or [""]
    report = {"genre": genre, "findings": [], "categories": {},
              "features_total": 0, "categories_total": 0,
              "recommendation": "", "note": ""}
    if genre == "legal":
        report["note"] = ("юридический жанр: мягкие признаки не считаются; "
                          "проверяются только маркеры разметки — "
                          "check_markers.py --scan")
        report["recommendation"] = ("правка по мягким признакам не применяется; "
                                    "канцелярит здесь норма жанра")
        return report
    suppressed = SUPPRESS[genre]
    genre_excl = GENRE_PHRASE_EXCLUDES.get(genre, {})
    masked_lines = None
    triggered_patterns = {}
    for det in REGISTRY:
        if det["id"] in suppressed:
            continue
        if det["id"] == "markdown_traces" and not plain_text:
            continue
        finder = det["finder"]
        excl = genre_excl.get(det["id"])
        if excl and "phrases" in det:
            finder = _make_phrase_finder([p for p in det["phrases"]
                                           if p not in excl])
        if getattr(finder, "prose_mask", False):
            # Фразовые детекторы не читают блоки кода: JSON с «в контексте»
            # внутри fenced-блока — цитата, а не стиль автора.
            if masked_lines is None:
                fenced = _fenced_lines(text)
                masked_lines = ["" if n in fenced else l
                                for n, l in enumerate(lines, 1)]
            hits = finder(text, masked_lines)
        else:
            hits = finder(text, lines)
        if len(hits) >= det["min_hits"]:
            report["findings"].append({
                "id": det["id"], "category": det["cat"], "pattern": det["pat"],
                "criticality": det["crit"], "count": len(hits),
                "samples": [{"line": n, "fragment": f} for n, f in hits[:3]]})
            triggered_patterns.setdefault(det["pat"], det["cat"])
    cats = {}
    for pat, cat in triggered_patterns.items():
        cats.setdefault(cat, []).append(pat)
    report["categories"] = {c: sorted(v) for c, v in cats.items()}
    report["features_total"] = len(triggered_patterns)
    report["categories_total"] = len(cats)
    report["recommendation"] = _recommend(len(triggered_patterns), len(cats))
    return report


def _recommend(features, categories):
    """Пороги дерева решений SKILL.md. Вердикт об авторстве не выносится."""
    if features == 0:
        return "мягких признаков-кандидатов не найдено; правка не требуется"
    if categories == 1:
        if features >= 3:
            return ("все признаки из одной категории — стилистическая "
                    "особенность: можно предложить форматную правку этой "
                    "категории, авторство не определялось")
        return "признаков мало и все из одной категории; не править"
    if features <= 2:
        return "0-2 признака: текст вероятно человеческий, не править"
    if features <= 5:
        return ("3-5 признаков из двух и более категорий: выборочная правка "
                "мест с высокой критичностью по rewrite-guide.md")
    return ("6 и более признаков из двух и более категорий: можно предложить "
            "переписывание с сохранением фактов по rewrite-guide.md")


MAIN_RULE_NOTE = ("Вердикт об авторстве этим счётчиком не выносится: см. "
                  "Главное правило в SKILL.md и references/false-positives.md.")


def render(path, report):
    out = ["== %s (жанр: %s)" % (path, report["genre"])]
    if report["note"]:
        out.append("   " + report["note"])
    for f in report["findings"]:
        out.append(" [%s | %s | критичность: %s] вхождений: %d"
                   % (f["category"], f["pattern"], f["criticality"], f["count"]))
        for s in f["samples"]:
            out.append("   строка %d: %s" % (s["line"], s["fragment"]))
    cats = ", ".join("%s: %d" % (c, len(v))
                     for c, v in sorted(report["categories"].items())) or "нет"
    out.append(" Признаков: %d; категории: %s"
               % (report["features_total"], cats))
    out.append(" Рекомендация: %s" % report["recommendation"])
    out.append(" " + MAIN_RULE_NOTE)
    return "\n".join(out)


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    def fires(det, text):
        return len(det["finder"](text, text.splitlines() or [""])) >= det["min_hits"]

    # 1. Каждый детектор жив: pos срабатывает, neg молчит.
    for det in REGISTRY:
        case("%s: прямой образец" % det["id"], fires(det, det["pos"]))
        case("%s: отрицательный образец" % det["id"], not fires(det, det["neg"]))

    # 2. Харнесс умеет падать: детектор с мёртвой лексикой не проходит pos.
    dead = dict(REGISTRY[0])
    dead["finder"] = _make_phrase_finder(["\u00a7\u00a7\u043d\u0435\u0442-\u0442\u0430\u043a\u043e\u0439-\u0444\u0440\u0430\u0437\u044b\u00a7\u00a7"])
    case("харнесс ловит обнулённый детектор", not fires(dead, dead["pos"]))

    # 3. Признак считается один раз на текст.
    rep = analyze("Эксперты считают одно. Эксперты считают другое. "
                  "Эксперты считают третье.")
    case("паттерн считается один раз", rep["features_total"] == 1
         and rep["findings"] and rep["findings"][0]["count"] == 3)

    # 4. Пороги дерева решений.
    case("одна категория, 3+ признака -> форматная правка без вердикта",
         "авторство не определялось" in _recommend(3, 1))
    case("0-2 признака -> не править", "не править" in _recommend(2, 2))
    case("3-5 из >=2 категорий -> выборочная правка",
         "выборочная" in _recommend(4, 2))
    case("6+ из >=2 категорий -> переписывание",
         "переписывание" in _recommend(7, 3))
    ai_like = ("Отличный вопрос! Безусловно, крайне важно раскрыть потенциал "
               "синергии. Более того, по сути это не просто инструмент, а "
               "новый подход. Он не только быстрый, но и удобный.\n\n"
               "Однако стоит отметить, что эксперты считают проект уникальным "
               "и инновационным. В заключение хочется отметить: будущее "
               "выглядит светлым. Надеюсь, это поможет!")
    rep = analyze(ai_like)
    case("синтетический ИИ-текст: признаков >= 6 и категорий >= 2",
         rep["features_total"] >= 6 and rep["categories_total"] >= 2)
    case("синтетический ИИ-текст: рекомендация — переписывание",
         "переписывание" in rep["recommendation"])
    human = ("Утром мы пошли на рынок. Купили хлеба и молока. Дождь так и "
             "не начался, зато к обеду распогодилось.")
    rep = analyze(human)
    case("короткий человеческий текст: ноль признаков",
         rep["features_total"] == 0)

    # 5. Жанровые исключения.
    triples = REGISTRY[[d["id"] for d in REGISTRY].index("rule_of_three")]["pos"]
    case("нейтральный жанр: тройки считаются",
         any(f["id"] == "rule_of_three"
             for f in analyze(triples)["findings"]))
    case("художественный жанр: тройки не считаются",
         not any(f["id"] == "rule_of_three"
                 for f in analyze(triples, genre="fiction")["findings"]))
    academ = REGISTRY[[d["id"] for d in REGISTRY].index("est_avoidance")]["pos"]
    case("академический жанр: «является» не считается",
         not any(f["id"] == "est_avoidance"
                 for f in analyze(academ, genre="academic")["findings"]))
    legal = analyze("Стороны осуществляют деятельность на основании договора.",
                    genre="legal")
    case("юридический жанр: мягкие признаки не считаются",
         legal["features_total"] == 0 and "класс" not in legal["note"]
         and "check_markers" in legal["note"])

    # 6. Следы Markdown считаются только с --plain-text.
    md = REGISTRY[[d["id"] for d in REGISTRY].index("markdown_traces")]["pos"]
    case("без --plain-text следы Markdown не считаются",
         not any(f["id"] == "markdown_traces" for f in analyze(md)["findings"]))
    case("с --plain-text следы Markdown считаются",
         any(f["id"] == "markdown_traces"
             for f in analyze(md, plain_text=True)["findings"]))

    # 7. JSON-отчёт сериализуется и содержит те же поля.
    dumped = json.loads(json.dumps(analyze(ai_like), ensure_ascii=False))
    case("json-отчёт сериализуется без потерь",
         dumped["features_total"] == rep0_total(ai_like))

    # 7c. Академические клише по false-positives §4/§11 не считаются
    # в жанре academic: «играет важную роль», «погрузиться».
    acad = ("Следует отметить, что более того, в контексте задачи стоит "
            "погрузиться в детали доказательства.")
    case("нейтральный жанр видит машинную лексику",
         any(d["id"] == "ai_lexicon" for d in analyze(acad)["findings"]))
    case("academic: «погрузиться» исключён из лексики",
         all(d["id"] != "ai_lexicon" for d in analyze(acad, genre="academic")["findings"]))
    sig2 = "Метод играет важную роль в сходимости. Результат знаменует собой новый этап."
    case("academic: «играет важную роль» не доводит значимость до порога",
         any(d["id"] == "significance" for d in analyze(sig2)["findings"])
         and all(d["id"] != "significance"
                 for d in analyze(sig2, genre="academic")["findings"]))

    # 7b. Правило трёх: четвёрки и числовые перечисления не считаются
    # (урок rev3: «a, b, c и d» ловилось с «b», годы считались риторикой).
    quad = "На конференции будут доклады, дискуссии, мастер-классы " \
           "и нетворкинг. И доклады, дискуссии, мастер-классы и воркшопы. " \
           "Снова доклады, дискуссии, мастер-классы и воркшопы."
    case("четвёрки не считаются правилом трёх",
         "rule_of_three" not in analyze(quad)["categories"].get("языковая", [])
         and all(d["id"] != "rule_of_three" for d in analyze(quad)["findings"]))
    years = "в 2019, 2020 и 2021 годах. В 2019, 2020 и 2021 годах. " \
            "За 2019, 2020 и 2021 годы."
    case("перечисления годов не считаются правилом трёх",
         all(d["id"] != "rule_of_three" for d in analyze(years)["findings"]))
    fenced = ("```bash\n# главный раздел\n### подобласть без второго уровня\n"
              "```\nОбычный текст без заголовков.")
    case("заголовки внутри блоков кода не дают #21",
         all(d["id"] not in ("heading_hierarchy", "title_case")
             for d in analyze(fenced)["findings"]))

    # 7a. Жанровые исключения ссылаются на существующие детекторы
    # (урок rev3: «emdash_density» жил в SUPPRESS, а в REGISTRY был
    # «emdash_bold» — художка получала тире-признак вопреки скиллу).
    for genre, suppressed in SUPPRESS.items():
        if suppressed is None:
            continue
        for det_id in suppressed:
            case("SUPPRESS[%s] знает детектор %s" % (genre, det_id),
                 det_id in _IDS)
    fic = analyze("Утро было такое — свежее, прозрачное, тонкое. Город ещё "
                  "спал — только редкие шаги отдавались эхом.", genre="fiction")
    case("художка: тире-детектор подавлен",
         "emdash_bold" not in fic["categories"].get("структурная", [])
         and all(d["id"] != "emdash_bold" for d in fic["findings"]))

    # 8. Порог --max-cats: гейт человеческого корпуса. Две категории —
    # уже повод для вердикта по дереву решений, одна — стилистическая
    # особенность; 0 отключает порог.
    sig_pos = next(d["pos"] for d in REGISTRY if d["cat"] == "содержательная")
    lex_pos = next(d["pos"] for d in REGISTRY if d["cat"] == "языковая")
    chat_pos = next(d["pos"] for d in REGISTRY if d["cat"] == "коммуникативная")
    two_text = sig_pos + " " + lex_pos
    case("образец для max-cats даёт две категории",
         analyze(two_text)["categories_total"] == 2)
    case("образец для max-cats даёт одну категорию",
         analyze(chat_pos)["categories_total"] == 1)
    with tempfile.TemporaryDirectory() as td:
        p_two = os.path.join(td, "two.txt")
        p_one = os.path.join(td, "one.txt")
        with open(p_two, "w", encoding="utf-8") as fh:
            fh.write(two_text)
        with open(p_one, "w", encoding="utf-8") as fh:
            fh.write(chat_pos)
        case("--max-cats 1: две категории валят проверку",
             main([p_two, "--max-cats", "1"]) == 1)
        case("--max-cats 1: одна категория проходит",
             main([p_one, "--max-cats", "1"]) == 0)
        case("--max-cats 0: порог выключен",
             main([p_two, "--max-cats", "0"]) == 0)

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def rep0_total(text):
    return analyze(text)["features_total"]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Счётчик мягких признаков; вердикта об авторстве не выносит.")
    ap.add_argument("files", nargs="*", help="файлы для проверки")
    ap.add_argument("--genre", default="neutral", choices=GENRES)
    ap.add_argument("--plain-text", action="store_true",
                    help="текст не предназначен для Markdown-среды")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--fail-at", type=int, default=0, metavar="N",
                    help="код 1, если признаков не меньше N (0 — выключено)")
    ap.add_argument("--max-cats", type=int, default=0, metavar="N",
                    help="код 1, если категорий мягких признаков больше N "
                         "(0 — выключено; по дереву решений одна категория — "
                         "стилистическая особенность, не машинный след)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.files:
        ap.print_usage()
        print("нет входных файлов", file=sys.stderr)
        return 2
    worst = 0
    worst_cats = 0
    payload = []
    for path in args.files:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
            return 2
        report = analyze(text, genre=args.genre, plain_text=args.plain_text)
        worst = max(worst, report["features_total"])
        worst_cats = max(worst_cats, report["categories_total"])
        if args.as_json:
            payload.append(dict(report, file=path))
        else:
            print(render(path, report))
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.fail_at and worst >= args.fail_at:
        return 1
    if args.max_cats and worst_cats > args.max_cats:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
