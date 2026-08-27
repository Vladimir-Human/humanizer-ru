#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_outward.py — черновик исходящего текста (issue, PR, внешний сервис) сухим остатком.

Файлы в репозитории берегут 57 гейтов, а публичный комментарий выходит
беспилотным. Этот валидатор переносит ту же дисциплину на исходящие тексты:
он не делает выводы за автора, а подсвечивает ровно те классы дефектов,
которые уже кусали проект: нечитаемые управляющие последовательности,
утечки локальных путей и внутренних ролей и — предупреждением —
универсальные утверждения об отсутствующем («не существует в репозитории»,
«история переписана», «раньше было только»), которые обязаны быть подкреплены
проверяющей командой: «не вижу» и «нет» — разные утверждения.

Запуск из корня репозитория:
    python3 scripts/check_outward.py путь/к/черновику.md [ещё_файл...]
    python3 scripts/check_outward.py --selftest

Коды возврата: 0 — чисто (WARN не мешает); 1 — есть FAIL; 2 — отказ
(нет входных файлов, файл не читается). Только стандартная библиотека.
"""
import argparse
import io
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Mojibake-токены берём из check_docs — единый источник, что считать cp1251-
# осадком; свой список здесь расплылся бы в дрейф.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from check_docs import MOJIBAKE_TOKENS as _MOJIBAKE_CORE
except Exception as _exc:  # импорт stdlib-файла из того же каталога не обязан шутить
    print("ВНИМАНИЕ: не импортированы токены из check_docs (%s), слой cp1251-осадка выключен"
          % _exc, file=sys.stderr)
    _MOJIBAKE_CORE = ()
_MOJIBAKE = _MOJIBAKE_CORE + ("â€", "\ufffd")

# Внутренние роли и процессы — наружу нельзя ни в файлах, ни в комментариях.
# Окончания русские, поэтому основа + хвост, а не голое слово.
BANNED_RX = [
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/]", re.I), "локальный путь оператора"),
    (re.compile(r"\bоркестратор[а-яё]*\b", re.I), "внутренняя роль прогонов"),
    (re.compile(r"\bэкзекьютор[а-яё]*\b", re.I), "внутренняя роль прогонов"),
    (re.compile(r"\bвеер[а-яё]*\b", re.I), "внутренний жаргон прогонов"),
    (re.compile(r"\bрешени[а-яё]* владельца", re.I), "внутренняя атрибуция решений"),
]

# Универсальные утверждения об отсутствии/прошлом: законны, только если рядом
# есть команда, упавшая бы на ложном. Здесь — известные публичные грабли.
CLAIM_RX = [
    re.compile(r"(?:не существует|does not exist|no longer exists)[^.]{0,80}"
               r"(?:репозитор|repos)", re.I),
    re.compile(r"история переписана|history was rewritten|was rewritten", re.I),
    re.compile(r"\bbefore that it was\b|раньше было только", re.I),
    re.compile(r"ни одного (?:коммита|файла|запуска) нет", re.I),
]

def check_bytes(raw):
    """По байтам возвращает (fails, warns)."""
    fails, warns = [], []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ["текст не декодируется как UTF-8: %s" % exc], []
    if text.startswith("\ufeff"):
        fails.append("BOM в начале — получатель увидит мусорный первый символ")
    if "\x1b" in text:
        fails.append("ESC-последовательность в тексте (mojibake от shell-экранирования)")
    for ch in _MOJIBAKE:
        if ch in text:
            fails.append("похоже на mojibake-последовательность %r" % ch)
            break
    for rx, why in BANNED_RX:
        m = rx.search(text)
        if m:
            line = text[:m.start()].count("\n") + 1
            fails.append("стр. %d: %s — «%s» наружу нельзя" % (line, why, m.group(0)[:40]))
    for rx in CLAIM_RX:
        for m in rx.finditer(text):
            line = text[:m.start()].count("\n") + 1
            warns.append("стр. %d: «%s» — подкрепи командой, которая упала бы, "
                         "если это ложь" % (line, m.group(0)[:60]))
    return fails, warns


def check_files(paths):
    fails_total = warns_total = 0
    for p in paths:
        try:
            raw = io.open(p, "rb").read()
        except OSError as exc:
            print("ОТКАЗ: не читается %s: %s" % (p, exc))
            return 2
        fails, warns = check_bytes(raw)
        for f in fails:
            print("[FAIL] %s: %s" % (p, f))
        for w in warns:
            print("[WARN] %s: %s" % (p, w))
        fails_total += len(fails)
        warns_total += len(warns)
    print("ИТОГ: %d файл(ов), FAIL: %d, WARN: %d." % (len(paths), fails_total, warns_total))
    return 1 if fails_total else 0


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, data, want_fail, want_warn=None):
        nonlocal passed, failed
        raw = data if isinstance(data, bytes) else data.encode("utf-8")
        fails, warns = check_bytes(raw)
        ok = bool(fails) == want_fail
        if want_warn is not None:
            ok = ok and bool(warns) == want_warn
        print(("PASS: " if ok else "FAIL: ") + name)
        if ok:
            passed += 1
        else:
            failed += 1

    case("чистый черновик -> без сигналов",
         "The manifest now ships name, description and license (6951f5a). "
         "Please re-scan against the v3.15.0 tag.",
         want_fail=False, want_warn=False)
    case("ESC из here-string -> FAIL", "Updated both \x1bn and zh lines",
         want_fail=True)
    case("локальный путь -> FAIL", "проверка в C:\\Users\\test\\repo\\file.md",
         want_fail=True)
    case("внутренняя роль -> FAIL", "по решению веера оркестратора исправлено",
         want_fail=True)
    case("внутренняя атрибуция -> FAIL", "убрано по решению владельца",
         want_fail=True)
    case("BOM -> FAIL", "\ufeff# заголовок", want_fail=True)
    case("не-UTF-8 байты -> FAIL", b"\xff\xfe\x00\x01", want_fail=True, want_warn=False)
    case("cp1251-моjibake -> FAIL", "РџСЂРёРІРµС‚ текст", want_fail=True)
    case("«no longer exists in this repository» -> WARN без FAIL",
         "the pinned commit no longer exists in this repository", want_fail=False,
         want_warn=True)
    case("«история переписана» -> WARN", "история переписана при переносе тега",
         want_fail=False, want_warn=True)
    case("«before that it was» -> WARN", "before that it was name+version only",
         want_fail=False, want_warn=True)
    case("безобидное «не найден» не шипит",
         "Если файл не найден в корне, проверьте каталог загрузки.",
         want_fail=False, want_warn=False)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка черновика исходящего публичного текста.")
    ap.add_argument("files", nargs="*", help="файлы-черновики (UTF-8)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.files:
        print("ОТКАЗ: не указан ни один черновик", file=sys.stderr)
        return 2
    return check_files(args.files)


if __name__ == "__main__":
    sys.exit(main())
