#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""polish.py — типографическая нормализация русского текста (главный режим).

Единственный путь проекта с доказанными числами: типографическая чистка
снимает верхний слой «машинности» так, что детерминированные линтеры
перестают обвинять текст (интервенция на панелях двух чужих линтеров).
Числа интервенции живут в реестре фактов прогона и здесь не цитируются.

Трансформация T (и только она): тире→дефис, ёлочки→прямые кавычки,
многоточие, невидимые символы и NBSP, снятие **/__ и хэшей заголовков,
переносы строк к LF. Лексика и списки нетронуты.

ЧЕСТНАЯ ГРАНИЦА: T снимает машинный слой типографики и для этого
выравнивает русскую типографику и Markdown в плоский текст — не
запускайте polish на Markdown и разметке без --preserve-markup: он снимет
##, **, ёлочки, тире и многоточие. Постановку ёлочек и тире по русской
норме делает агентный слой (SKILL.md), а не этот инструмент;
--preserve-markup оставляет разметку и русскую типографику, снимая
только невидимые символы, NBSP и нормализуя переносы строк.

Третий режим — --typographic (публикационный): приводит текст к русской
публикационной типографике БЕЗ снятия заголовков и выделения: парные
прямые кавычки -> ёлочки, «...» -> единый символ многоточия, невидимые
символы и NBSP снимаются, переносы строк к LF. Режимы --preserve-markup и
--typographic опираются на единый источник защищённых областей
(scripts/protected_regions.py, копия в пакете): содержимое fenced-блоков
(``` и ~~~), YAML-frontmatter, инлайн-код (серии бэктиков фиксированной
длины), URL, HTML-теги с кавычками атрибутов и ZWJ-кластеры составных
эмодзи не трогаются; ZWJ вне эмодзи-контекста снимается как артефакт.
Если общий источник правил недоступен, оба режима отказывают с явной
ошибкой вместо небезопасного преобразования. Тире режим не ставит: выбор
тире — решение агентного слоя. Режим идемпотентен и применим к
собственным публичным документам проекта (гейт
scripts/check_polish_modes.py требует changed:false на README.md,
SKILL.md, CONTRIBUTING.md, llms.txt).

Инварианты (проверяются гейтом и самопроверкой):
  1. Идемпотентность: polish(polish(x)) == polish(x).
  2. Ноль смысловых правок: последовательность букв и цифр до и после
     совпадает дословно — трансформация не удаляет, не добавляет и не
     переставляет ни одной буквы (слова и числа содержимого целы;
     нулевые символы внутри слова лишь склеивают разорванное слово).
  3. Сохранение защищённых областей (--preserve-markup и --typographic):
     каждая защищённая область входа обязана присутствовать в результате
     неизменной; нарушение репортится в списке invariants (URL, кавычки
     атрибутов, ZWJ-кластер, содержимое кода) и даёт код 1.

Доля отказов 0: polish не отказывает ни на каком входе; текст без
типографических дефектов возвращается неизменным (пустой диф — норма).
Пустой и не-русский вход помечаются «вне области» (scope_note): механика
типографики отрабатывает, но область скилла — русский текст.

Режимы:
    python3 scripts/polish.py ФАЙЛ...           # результат в stdout («-» = stdin)
    python3 scripts/polish.py --preserve-markup ФАЙЛ...  # без снятия разметки
    python3 scripts/polish.py --typographic ФАЙЛ...  # публикационная типографика
    python3 scripts/polish.py --diff ФАЙЛ...    # унифицированный диф
    python3 scripts/polish.py --in-place ФАЙЛ...# запись на место (+ .bak)
    python3 scripts/polish.py --dry-run --in-place ФАЙЛ...  # что изменится
    python3 scripts/polish.py --json ФАЙЛ...    # машиночитаемый отчёт
    python3 scripts/polish.py --gate КАТАЛОГ    # инварианты по *.md/*.txt
    python3 scripts/polish.py --selftest        # самопроверка с негативами

Коды: 0 — успех/инварианты целы; 1 — нарушение инварианта или диф-гейт;
2 — вход не читается либо запись --in-place не удалась (с --json конверт
ошибки печатается в stdout).
Репозиторий: https://github.com/Vladimir-Human/humanizer-ru
Вход для агентов: llms.txt; машинный контракт: contract.v1.json.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

# Единый источник правил защищённых областей: пакетный контекст
# (humanizer_ru.polish) берёт соседний модуль, скриптовый — из своего
# каталога. Копии scripts/polish.py и src/humanizer_ru/polish.py побайтно
# равны (гейт check_pkg_sync.py), как и копии protected_regions.py.
try:
    from . import protected_regions as PR
except ImportError:
    try:
        import os as _os_pr
        import sys as _sys_pr
        _sys_pr.path.insert(
            0, _os_pr.path.dirname(_os_pr.path.abspath(__file__)))
        import protected_regions as PR
    except Exception:  # pragma: no cover — поставка неполна
        PR = None


def _require_pr():
    """Режимы сохранения обязаны защищать области или честно отказать."""
    if PR is None:
        raise RuntimeError(
            "protected_regions недоступен: режимы --preserve-markup и "
            "--typographic отказывают вместо небезопасного преобразования")

# Невидимые символы: пробельные -> обычный пробел, нулевой ширины -> удалить.
_INVIS = {
    "\u00a0": " ",   # неразрывный пробел
    "\u2009": " ",   # узкий пробел
    "\u202f": " ",   # узкий неразрывный пробел
    "\u200b": "",    # нулевая ширина, пробел
    "\u200c": "",    # разъединитель нулевой ширины
    "\u200d": "",    # соединитель нулевой ширины
    "\u2060": "",    # межсловный соединитель
    "\ufeff": "",    # BOM / неразрывный пробел нулевой ширины
    "\u00ad": "",    # мягкий перенос
}
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)
_HEADING = re.compile(r"(?m)^(?:#{1,6}[ \t]+)+")
_WORD = re.compile(r"[0-9A-Za-z\u0410-\u042f\u0430-\u044f\u0401\u0451]+")
_LETTERS = re.compile(r"[0-9A-Za-z\u0410-\u042f\u0430-\u044f\u0401\u0451]")
_FIXPOINT_ROUNDS = 20
# Публикационный режим: парные прямые кавычки в пределах одной строки.
_PAIR_QUOTES = re.compile(r'"([^"\n]*)"')
# Русские подписи видов защищённых областей для списка invariants.
_PROTECTION_LABELS = {
    "code": "содержимого кода",
    "fenced": "fenced-блока",
    "frontmatter": "frontmatter",
    "url": "URL",
    "html": "HTML-тега (кавычек атрибутов)",
    "zwj": "ZWJ-кластера",
}


def words_of(text: str) -> list[str]:
    """Последовательность слов (буквы/цифры) — для отчётов и дифов."""
    return _WORD.findall(text)


def letters_of(text: str) -> str:
    """Последовательность букв и цифр — канва инварианта №2."""
    return "".join(_LETTERS.findall(text))


def _polish_once(text: str, preserve_markup: bool = False) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    if preserve_markup:
        # Режим сохранения разметки: невидимые символы/NBSP снимаются
        # только в прозе вне защищённых областей (единый источник —
        # protected_regions); ёлочки, тире, многоточия, ** и ## остаются.
        return _preserve_regions_once(t)
    for ch, repl in _INVIS.items():
        t = t.replace(ch, repl)
    t = t.replace("\u2014", "-").replace("\u2013", "-")  # тире: длинное/короткое
    t = t.replace("\u00ab", '"').replace("\u00bb", '"')  # ёлочки -> прямые
    t = t.replace("\u2026", "...")                        # многоточие
    t = _BOLD.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _HEADING.sub("", t)
    return t


def _preserve_regions_once(t: str) -> str:
    """Один проход режима сохранения: LF уже нормализованы вызывающим."""
    _require_pr()
    lines = t.split("\n")
    fenced = PR.fenced_line_indices(lines)
    front = PR.frontmatter_line_indices(lines)
    out = []
    for i, line in enumerate(lines):
        if i in fenced or i in front:
            out.append(line)
            continue
        pieces = []
        last = 0
        for s, e in PR.protected_line_spans(line):
            pieces.append(PR.remove_invisibles(line[last:s], _INVIS))
            pieces.append(line[s:e])
            last = e
        pieces.append(PR.remove_invisibles(line[last:], _INVIS))
        out.append("".join(pieces))
    return "\n".join(out)


def polish(text: str, preserve_markup: bool = False,
           typographic: bool = False) -> str:
    """Трансформация T до неподвижной точки.

    Итерация до фикспойнта обязательна: снятие маркера может обнажить
    следующий (жирный под заголовком, вложенные пары) — однократная замена
    на таких входах неидемпотентна. Фикспойнт гарантирует инвариант №1 по
    построению; буквы и цифры ни одна замена не трогает (инвариант №2).
    preserve_markup=True — снять только машинный слой (невидимые символы,
    NBSP, переносы строк), сохранив разметку и русскую типографику.
    typographic=True — публикационный режим: русская типографика
    (ёлочки из парных прямых кавычек, единый символ многоточия) БЕЗ снятия
    разметки; fenced-блоки и инлайн-бэктики не трогаются; при сочетании
    флагов typographic имеет приоритет.
    """
    t = text
    for _ in range(_FIXPOINT_ROUNDS):
        if typographic:
            nxt = _typographic_once(t)
        else:
            nxt = _polish_once(t, preserve_markup)
        if nxt == t:
            return t
        t = nxt
    return t


def _typo_prose(seg: str) -> str:
    """Типографская правка одного прозаического сегмента (вне защит)."""
    seg = PR.remove_invisibles(seg, _INVIS)
    seg = _PAIR_QUOTES.sub("\u00ab\\1\u00bb", seg)
    seg = seg.replace("...", "\u2026")
    return seg


def _typographic_once(text: str) -> str:
    """Один проход публикационного режима (без снятия разметки).

    Трансформации применяются ТОЛЬКО к прозе вне защищённых областей
    (единый источник — protected_regions): fenced-блоки (``` и ~~~),
    YAML-frontmatter, инлайн-код (серии бэктиков фиксированной длины),
    URL, HTML-теги с кавычками атрибутов и ZWJ-кластеры эмодзи не
    трогаются. Невидимые символы и NBSP в прозе снимаются, переносы строк
    нормализуются везде.
    """
    _require_pr()
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = t.split("\n")
    fenced = PR.fenced_line_indices(lines)
    front = PR.frontmatter_line_indices(lines)
    out = []
    for i, line in enumerate(lines):
        if i in fenced or i in front:
            out.append(line)
            continue
        if ("`" not in line and '"' not in line and "..." not in line
                and not any(ch in line for ch in _INVIS)):
            out.append(line)
            continue
        pieces = []
        last = 0
        for s, e in PR.protected_line_spans(line):
            pieces.append(_typo_prose(line[last:s]))
            pieces.append(line[s:e])
            last = e
        pieces.append(_typo_prose(line[last:]))
        out.append("".join(pieces))
    return "\n".join(out)


def _cyrillic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "\u0400" <= c <= "\u04ff")
    return cyr / len(letters)


def scope_note(text: str) -> str:
    """Пометка «вне области»: пустой и не-русский вход — вне домена скилла.

    Градуированный ответ остаётся непустым (контракт): механика типографики
    отрабатывает на любом входе, но честный статус входа агент обязан видеть.
    """
    if not text.strip():
        return "вне области: пустой вход"
    if _cyrillic_share(text) < 0.1:
        return "вне области: текст не на русском (область скилла — русский текст)"
    return ""


def invariant_problems(original: str, cleaned: str,
                       preserve_markup: bool = False,
                       typographic: bool = False) -> list[str]:
    """Проверка пары (до, после): список нарушений инвариантов.

    В режимах --preserve-markup и --typographic дополнительно сверяется
    сохранение защищённых областей: каждая область входа (содержимое кода,
    fenced-блок, frontmatter, URL, HTML-тег, ZWJ-кластер) обязана
    присутствовать в результате неизменной. Список нарушений попадает в
    --json (поле invariants) и даёт код возврата 1: «почти сохранил»
    недопустимо.
    """
    problems = []
    if polish(cleaned, preserve_markup, typographic) != cleaned:
        problems.append("идемпотентность: повторный проход меняет текст")
    if letters_of(original) != letters_of(cleaned):
        problems.append("смысловая правка: буквы/цифры изменены")
    if preserve_markup or typographic:
        _require_pr()
        seen = set()
        for kind, frag in PR.protected_regions(original):
            if frag in cleaned or (kind, frag) in seen:
                continue
            seen.add((kind, frag))
            problems.append(
                "сохранение %s: защищённая область изменена или удалена: %r"
                % (_PROTECTION_LABELS.get(kind, kind), frag[:60]))
    return problems


# ------------------------------------------------------------------ selftest

def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    src = ("# Заголовок раздела\n\n"
           "**Жирная мысль** о длинном — тире и «ёлочках»…\n"
           "Второй абзац с неразрывным\u00a0пробелом и нулевым\u200bсловом.\n")
    out = polish(src)
    case("тире заменено на дефис", "\u2014" not in out and "-" in out)
    case("ёлочки заменены на прямые", "\u00ab" not in out and '"' in out)
    case("многоточие заменено", "\u2026" not in out and "..." in out)
    case("жирный снят", "**" not in out and "Жирная мысль" in out)
    case("хэш заголовка снят", not out.startswith("#") and "Заголовок" in out)
    case("NBSP заменён на пробел", "\u00a0" not in out)
    case("нулевой ширины удалён", "\u200b" not in out and "нулевымсловом" in out)
    case("идемпотентность на образце", polish(out) == out)
    case("буквы и цифры сохранены дословно", letters_of(src) == letters_of(out))
    case("инварианты без нарушений", invariant_problems(src, out) == [])

    # Коварные вложения: снятие маркера обнажает следующий маркер.
    nested = "## **# Заголовок**\n"
    nout = polish(nested)
    case("идемпотентность при вложении (жирный под заголовком)",
         polish(nout) == nout)
    case("буквы целы при вложении", letters_of(nested) == letters_of(nout))
    nested2 = "**__двойное__**"
    case("идемпотентность при вложенных парах", polish(polish(nested2)) == polish(nested2))

    # Концы строк: CRLF и одиночный CR приводятся к LF.
    crlf = "Строка один — с тире.\r\nСтрока два…\rТретья.\n"
    cout = polish(crlf)
    case("переносы строк к LF", "\r" not in cout)
    case("буквы целы при нормализации концов", letters_of(crlf) == letters_of(cout))
    case("идемпотентность после нормализации концов", polish(cout) == cout)

    # Негативы: гейт обязан уметь падать.
    case("ловит смысловую правку (вставка слова)",
         "смысловая правка" in " ".join(invariant_problems(src, out + " Лишнее")))
    case("ловит смысловую правку (удаление слова)",
         "смысловая правка" in " ".join(invariant_problems(src, "Заголовок")))
    broken = out.replace("-", "\u2014")  # обратная замена ломает идемпотентность
    case("ловит нарушение идемпотентности",
         "идемпотентность" in " ".join(invariant_problems(broken, broken)))

    # Текст без дефектов возвращается неизменным (пустой диф — норма, не отказ).
    clean = "Обычный текст без дефектов. Второй абзац.\n"
    case("чистый текст неизменен (доля отказов 0)", polish(clean) == clean)

    # --preserve-markup: разметка и русская типографика сохраняются,
    # машинный слой (невидимые символы) снимается.
    pm = polish("## Заголовок — «цитата» **жирный**\u200b\n", preserve_markup=True)
    case("preserve-markup сохраняет ## заголовка", pm.startswith("## "))
    case("preserve-markup сохраняет ёлочки и тире",
         "\u00ab" in pm and "\u2014" in pm)
    case("preserve-markup сохраняет **жирный**", "**" in pm)
    case("preserve-markup снимает нулевой ширины", "\u200b" not in pm)
    case("preserve-markup идемпотентен", polish(pm, True) == pm)

    # Защищённые области (единый источник protected_regions): URL,
    # HTML-атрибуты, ZWJ-кластеры, инлайн-код — в обоих безопасных режимах.
    url_src = "Троеточие... и https://example.org/a...b в прозе.\n"
    uout = polish(url_src, typographic=True)
    case("typographic: URL не трогается (многоточие внутри остаётся)",
         "https://example.org/a...b" in uout)
    case("typographic: проза вне URL приводится",
         "Троеточие\u2026" in uout)
    html_src = 'Проза "цитата" и <a href="x">ссылка</a>.\n'
    hout = polish(html_src, typographic=True)
    case("typographic: кавычки атрибута сохранены", '<a href="x">' in hout)
    case("typographic: кавычки прозы приведены", "\u00abцитата\u00bb" in hout)
    family = "семья \U0001F468\u200d\U0001F469\u200d\U0001F467 в подписи\n"
    case("typographic: ZWJ-кластер семьи сохранён",
         polish(family, typographic=True) == family)
    case("preserve-markup: ZWJ-кластер семьи сохранён",
         polish(family, preserve_markup=True) == family)
    flag = "флаг \U0001F3F3\uFE0F\u200d\U0001F308 в чате\n"
    case("preserve-markup: радужный флаг сохранён",
         polish(flag, preserve_markup=True) == flag)
    psrc = "проза\u200b и `код\u200b внутри` и NBSP\u00a0тут\n"
    pout = polish(psrc, preserve_markup=True)
    case("preserve-markup: невидимые в прозе сняты",
         "проза и" in pout and "NBSP тут" in pout)
    case("preserve-markup: содержимое инлайн-кода не тронуто",
         "`код\u200b внутри`" in pout)
    fsrc2 = "проза\u200b\n```\nкод\u200b внутри\n```\n"
    fout2 = polish(fsrc2, preserve_markup=True)
    case("preserve-markup: fenced-блок не тронут",
         "код\u200b внутри" in fout2 and "проза и" not in fout2)
    case("preserve-markup: проза вне блока снята", "проза\n" in fout2)

    # Инвариант №3: нарушения сохранения репортятся, а не молчат.
    src3 = 'См. https://e.org/a...b и "проза"...\n'
    good3 = polish(src3, typographic=True)
    case("typographic: инварианты чистого результата пусты",
         invariant_problems(src3, good3, typographic=True) == [])
    doctored_url = good3.replace("https://e.org/a...b", "https://e.org/a\u2026b")
    case("инварианты ловят изменённый URL",
         any("URL" in p for p in
             invariant_problems(src3, doctored_url, typographic=True)))
    fam_broken = family.replace("\u200d", "")
    case("инварианты ловят разрушенный ZWJ-кластер",
         any("ZWJ" in p for p in
             invariant_problems(family, fam_broken, typographic=True)))
    code_broken = pout.replace("`код\u200b внутри`", "`код внутри`")
    case("инварианты ловят изменённое содержимое кода",
         any("кода" in p for p in
             invariant_problems(psrc, code_broken, preserve_markup=True)))
    attr_broken = hout.replace('<a href="x">', "<a href=\u00abx\u00bb>")
    case("инварианты ловят изменённые кавычки атрибута",
         any("атрибут" in p for p in
             invariant_problems(html_src, attr_broken, typographic=True)))

    # --typographic: публикационная типографика без снятия разметки;
    # fenced-блоки и инлайн-бэктики не трогает.
    tsrc = 'Проза "цитата" и троеточие... вне кода.\n'
    tout = polish(tsrc, typographic=True)
    case("typographic: прямые кавычки -> ёлочки",
         "\u00ab" in tout and '"' not in tout)
    case("typographic: ... -> единый символ", "\u2026" in tout and "..." not in tout)
    case("typographic: идемпотентен", polish(tout, typographic=True) == tout)
    case("typographic: буквы и цифры дословно", letters_of(tsrc) == letters_of(tout))
    case("typographic: инварианты без нарушений",
         invariant_problems(tsrc, tout, typographic=True) == [])
    fsrc = 'Проза "цель".\n```python\nx = "code..."\n```\nЕщё "проза"...\n'
    fout = polish(fsrc, typographic=True)
    case("typographic: fenced-код не тронут", 'x = "code..."' in fout)
    case("typographic: проза вне забора приведена", fout.count("\u00ab") == 2)
    bsrc = 'Вне `"кода"` и "проза".\n'
    bout = polish(bsrc, typographic=True)
    case("typographic: инлайн-бэктики не тронуты", '`"кода"`' in bout)
    case("typographic: кавычки вне бэктиков приведены", "\u00abпроза\u00bb" in bout)
    case("typographic: уже приведённый текст неизменен",
         polish("Обычный «текст» с тире — и многоточием…\n",
                typographic=True) == "Обычный «текст» с тире — и многоточием…\n")
    case("typographic: невидимые внутри бэктиков не трогает",
         "`a\u200bb`" in polish("x `a\u200bb` \"y\"...\n", typographic=True))
    case("typographic: невидимые в прозе снимает",
         "\u200b" not in polish("Слово\u200b и \"цитата\".\n", typographic=True))
    fm = polish('---\nname: "x"\n---\nПроза "y"...\n', typographic=True)
    case("typographic: YAML-frontmatter не трогает",
         fm.splitlines()[1] == 'name: "x"' and "\u00aby\u00bb" in fm)

    # Пометка «вне области»: пустой и не-русский вход (градуированный ответ
    # остаётся непустым, но статус входа честный).
    case("пустой вход — вне области", scope_note("") != "" and scope_note("  \n") != "")
    case("английский текст — вне области",
         scope_note("Plain English text without any Russian.") != "")
    case("русский текст — в области", scope_note("Обычный русский текст.") == "")

    print("САМОПРОВЕРКА polish: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


# --------------------------------------------------------------------- gate

def gate(paths: list[str]) -> int:
    """Инварианты по файлам (*.md, *.txt). Падает при нарушении."""
    bad = 0
    checked = 0
    for path in paths:
        if os.path.isdir(path):
            for dirpath, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.endswith((".md", ".txt")):
                        bad += _gate_file(os.path.join(dirpath, name))
                        checked += 1
        else:
            bad += _gate_file(path)
            checked += 1
    if bad:
        print("ПОЛИРОВКА: нарушений инвариантов %d (файлов проверено %d)"
              % (bad, checked))
        return 1
    print("ПОЛИРОВКА: инварианты целы на %d файлах" % checked)
    return 0


def _gate_file(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc))
        return 1
    cleaned = polish(text)
    problems = invariant_problems(text, cleaned)
    for p in problems:
        print("НАРУШЕНИЕ %s: %s" % (path, p))
    return 1 if problems else 0


# ---------------------------------------------------------------------- CLI

def _diff_text(before: str, after: str, label: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=label + " (до)", tofile=label + " (после)")
    return "".join(lines)


SHORT_RU = "Проверяемая гигиена вставки из чата для русского текста"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Типографическая нормализация русского текста. "
                    "Не запускать на Markdown и разметке: снимает ##, **, "
                    "ёлочки, тире, многоточие; режим сохранения разметки — "
                    "--preserve-markup.",
        epilog="Репозиторий: https://github.com/Vladimir-Human/humanizer-ru\n"
               "Вход для агентов: llms.txt; машинный контракт: contract.v1.json",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*",
                    help="файлы для обработки; «-» читает stdin (UTF-8)")
    ap.add_argument("--diff", action="store_true",
                    help="показать унифицированный диф до/после")
    ap.add_argument("--in-place", action="store_true",
                    help="записать результат на место (с копией .bak)")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать изменения, не писать")
    ap.add_argument("--preserve-markup", action="store_true",
                    help="снимать только невидимые символы/NBSP и "
                         "нормализовать переносы строк; Markdown и русская "
                         "типографика (ёлочки, тире) сохраняются; "
                         "защищённые области (инлайн-код, fenced-блоки, "
                         "frontmatter, URL, HTML-теги, ZWJ-кластеры эмодзи) "
                         "не трогаются")
    ap.add_argument("--remove", action="store_true",
                    help="явный алиас дефолтного режима: снятие "
                         "машинного слоя (невидимые, разметка); "
                         "поведение идентично вызову без флагов")
    ap.add_argument("--typographic", action="store_true",
                    help="публикационный режим: парные прямые кавычки -> "
                         "ёлочки, «...» -> единый символ многоточия, "
                         "невидимые символы снимаются только в прозе; "
                         "защищённые области (разметка, fenced-блоки, "
                         "инлайн-код, frontmatter, URL, HTML-теги, "
                         "ZWJ-кластеры эмодзи) не трогаются; приоритет над "
                         "--preserve-markup")
    ap.add_argument("--json", action="store_true",
                    help="машиночитаемый отчёт (схема 1)")
    ap.add_argument("--gate", metavar="ПУТЬ",
                    help="режим гейта: проверить инварианты по файлам/каталогу")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка с негативными кейсами")
    ap.description = SHORT_RU + "\n\n" + (ap.description or "")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.gate:
        return gate([args.gate])
    if not args.files:
        print("нет файлов; справка: --help, самопроверка: --selftest",
              file=sys.stderr)
        return 2

    report = []
    errors = []
    rc = 0
    for path in args.files:
        if path == "-" and args.in_place:
            msg = "--in-place неприменим к stdin"
            print("НЕ ЧИТАЕТСЯ -: " + msg, file=sys.stderr)
            errors.append({"file": "<stdin>", "error": msg})
            rc = 2
            continue
        try:
            if path == "-":
                if hasattr(sys.stdin, "reconfigure"):
                    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
                before = sys.stdin.read()
            else:
                with open(path, encoding="utf-8") as fh:
                    before = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print("НЕ ЧИТАЕТСЯ %s: %r" % (path, exc), file=sys.stderr)
            errors.append({"file": path, "error": repr(exc)})
            rc = 2
            continue
        after = polish(before, args.preserve_markup, args.typographic)
        problems = invariant_problems(before, after, args.preserve_markup,
                                      args.typographic)
        if problems:
            rc = 1
        changed = after != before
        note = scope_note(before)
        entry = {
            "file": "<stdin>" if path == "-" else path,
            "changed": changed,
            "chars_before": len(before),
            "chars_after": len(after),
            "preserve_markup": bool(args.preserve_markup),
            "typographic": bool(args.typographic),
            "invariants": problems,
        }
        if note:
            entry["status"] = "out-of-scope"
            entry["scope_note"] = note
            print("%s: %s" % (path, note), file=sys.stderr)
        if args.json:
            report.append(entry)
        elif args.diff:
            sys.stdout.write(_diff_text(before, after, path))
        elif args.in_place:
            if args.dry_run:
                print(("ИЗМЕНИТСЯ " if changed else "БЕЗ ИЗМЕНЕНИЙ ") + path)
            elif problems:
                # Нарушен инвариант — результат не записывается: файл
                # остаётся целым, нарушение видно в stderr и коде возврата.
                print("НЕ ЗАПИСАНО %s: нарушение инвариантов: %s"
                      % (path, "; ".join(problems)), file=sys.stderr)
            else:
                if changed:
                    # Безопасная запись: сначала копия .bak, затем атомарная
                    # подмена (tmp + os.replace). Ошибка записи не оставляет
                    # частичный «успешный» результат: исходный файл цел,
                    # временный убирается, состояние уходит в errors с кодом 2.
                    tmp = path + ".tmp-polish"
                    try:
                        with open(path + ".bak", "w", encoding="utf-8",
                                  newline="") as fh:
                            fh.write(before)
                        with open(tmp, "w", encoding="utf-8",
                                  newline="") as fh:
                            fh.write(after)
                        os.replace(tmp, path)
                    except OSError as exc:
                        try:
                            os.unlink(tmp)
                        except OSError:
                            pass
                        print("НЕ ЗАПИСАНО %s: %r (исходный файл не изменён)"
                              % (path, exc), file=sys.stderr)
                        errors.append({"file": path, "error": repr(exc)})
                        rc = 2
                        continue
                print(("ЗАПИСАНО " if changed else "БЕЗ ИЗМЕНЕНИЙ ") + path)
        else:
            # Завершающий перевод строки обязателен: следующий промпт
            # консоли не должен прилипать к тексту.
            sys.stdout.write(after if not after or after.endswith("\n")
                             else after + "\n")
    if args.json:
        envelope = {"tool": "humanizer-polish", "schema": 1,
                    "files": report + errors}
        if rc == 2:
            envelope["error"] = "вход не читается (код 2)"
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
