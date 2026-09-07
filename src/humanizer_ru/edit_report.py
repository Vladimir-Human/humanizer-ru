#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humanizer-report (F2): машиночитаемый отчёт правки без LLM-судей.

Считает по паре «до/после»: токены keep/add/delete (difflib, stdlib),
адаптированные компоненты SARI (без золотого эталона: отчёт описательный),
типизацию дельты по классам правок (невидимые, разметка, пунктуация,
пробелы, регистр, лексика) и сверку фактов через facts_diff (потерянные и
изменённые факты авторских категорий). Вердиктов об авторстве нет.

CLI:
  humanizer-report до.md после.md [--json]
Коды: 0 — отчёт построен; 2 — ошибка входа.
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata

_INVISIBLE_RX = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]")
_MARKUP_RX = re.compile(r"^[#>*_`~\-\[\](){}|]+$|^</?[a-zA-Z][^>]*>$|^&[a-z]+;$|^&#\d+;$")
_PUNCT_RX = re.compile(r"^[\W_]+$", re.UNICODE)


def _tokens(text):
    return text.split()


def _classify(tok_before, tok_after):
    """Класс правки для заменённого токена (или класса удаления/вставки)."""
    t = tok_after if tok_after is not None else tok_before
    if _INVISIBLE_RX.search(t or ""):
        return "invisible"
    if _MARKUP_RX.match(t or ""):
        return "markup"
    if _PUNCT_RX.match(t or ""):
        return "punctuation"
    if tok_before and tok_after and tok_before.lower() == tok_after.lower():
        return "casing"
    return "lexical"


def compute(before, after):
    bt, at = _tokens(before), _tokens(after)
    sm = difflib.SequenceMatcher(a=bt, b=at, autojunk=False)
    keep = add = delete = 0
    types = {"invisible": 0, "markup": 0, "punctuation": 0,
             "whitespace": 0, "casing": 0, "lexical": 0}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            keep += i2 - i1
        elif tag == "delete":
            delete += i2 - i1
            for tok in bt[i1:i2]:
                types[_classify(tok, None)] += 1
        elif tag == "insert":
            add += j2 - j1
            for tok in at[j1:j2]:
                types[_classify(None, tok)] += 1
        else:
            delete += i2 - i1
            add += j2 - j1
            for tok in bt[i1:i2]:
                types[_classify(tok, None)] += 1
            for tok in at[j1:j2]:
                types[_classify(None, tok)] += 1
    # пробельные правки: разница числа строк и двойных пробелов
    ws = abs(before.count("\n") - after.count("\n")) + \
        abs(before.count("  ") - after.count("  "))
    types["whitespace"] += ws
    sari = {
        "keep": round(keep / len(bt), 4) if bt else 1.0,
        "add": round(add / len(at), 4) if at else 0.0,
        "delete": round(delete / len(bt), 4) if bt else 0.0,
    }
    return {"tokens": {"keep": keep, "add": add, "delete": delete},
            "sari_adapted": sari, "edit_types": types}


def _strip_markers(text):
    """Payload маркеров копипасты не является фактом автора (check_examples
    делает то же через _loss_text): снимаем сигнатуры до сверки фактов."""
    cm = None
    try:
        # Пакетный контекст (в том числе установленная поставка: sdist/wheel
        # не несут каталог scripts/, скриптовый путь там не работает).
        from humanizer_ru import check_markers as _cm_pkg
        cm = _cm_pkg
    except Exception:
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        for base in (os.path.dirname(os.path.dirname(here)),
                     os.path.dirname(here)):
            sp = os.path.join(base, "scripts")
            if os.path.isdir(sp) and sp not in sys.path:
                sys.path.insert(0, sp)
        try:
            import check_markers as _cm_scripts
            cm = _cm_scripts
        except Exception:
            cm = None
    if cm is None:
        return text
    for case in cm.CASES.values():
        text = re.sub(case[0], " ", text)
    return text


METRIC_NAMES = ["tokens.keep", "tokens.add", "tokens.delete",
                "sari_adapted.keep", "sari_adapted.add",
                "sari_adapted.delete", "edit_types", "facts.lost",
                "facts.changed", "mtld"]


def mtld(text, threshold=0.72):
    """MTLD (lexical diversity): среднее факторов TTR ниже порога по
    прямой и обратной последовательностям токенов; stdlib-реализация,
    вариант частичного фактора документирован в METRICS.md."""
    toks = re.findall(r"[a-zа-яё]+", text.lower())
    if len(toks) < 10:
        return None
    vals = []
    for seq in (toks, toks[::-1]):
        factors = 0.0
        n = 0
        uniq = {}
        for i, tk in enumerate(seq, 1):
            uniq[tk] = uniq.get(tk, 0) + 1
            n = i
            ttr = len(uniq) / n
            if ttr < threshold:
                factors += (1 - ttr) / (1 - threshold)
                uniq = {}
                n = 0
        if n:
            factors += 1
        vals.append(len(seq) / factors if factors else 0.0)
    return round(sum(vals) / 2.0, 4)


def facts_part(before, after):
    try:
        from humanizer_ru import facts_diff as fd
    except Exception:
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        import facts_diff as fd
    env = fd.diff(_strip_markers(before), _strip_markers(after))
    lost = len(env.get("lost", []) or [])
    changed = len(env.get("changed", []) or [])
    return {"lost": lost, "changed": changed,
            "unchanged": lost == 0 and changed == 0}


def _scope_note(text):
    """Статус «вне области» — единый определитель (polish.scope_note)."""
    try:
        from humanizer_ru.polish import scope_note
    except Exception:
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        from polish import scope_note
    return scope_note(text)


def report(before_path, after_path):
    # Строгий UTF-8: повреждённый вход — ошибка (код 2) по контракту,
    # а не молчаливая замена байтов на U+FFFD внутри сверки фактов.
    with open(before_path, encoding="utf-8") as fh:
        before = fh.read()
    with open(after_path, encoding="utf-8") as fh:
        after = fh.read()
    body = compute(before, after)
    body["facts"] = facts_part(before, after)
    mb, ma = mtld(before), mtld(after)
    body["mtld"] = {"before": mb, "after": ma}
    entry = {"before": before_path, "after": after_path, **body}
    # Градуированный ответ (контракт, graduated_response.out_of_scope):
    # пустой и не-русский вход получают честный статус; поля аддитивны —
    # tokens/sari_adapted/edit_types/facts/mtld сохраняют прежнюю семантику.
    notes = []
    for side_label, side_text in (("до", before), ("после", after)):
        note = _scope_note(side_text)
        if note:
            notes.append("%s: %s" % (side_label, note))
    if notes:
        entry["status"] = "out-of-scope"
        entry["scope_note"] = "; ".join(notes)
    return {"tool": "humanizer-report", "schema": 1, "files": [entry]}


SHORT_RU = "Проверяемая гигиена вставки из чата для русского текста"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="humanizer-report")
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--json", action="store_true")
    ap.description = SHORT_RU + "\n\n" + (ap.description or "")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if code == 0:
            return 0
        raw = list(sys.argv[1:] if argv is None else argv)
        if "--json" in raw:
            # error_rule контракта: с --json отказ разбора аргументов тоже
            # даёт конверт в stdout (usage остаётся в stderr).
            print(json.dumps({"tool": "humanizer-report", "schema": 1,
                              "files": [],
                              "error": "аргументы не распознаны (код 2)"},
                             ensure_ascii=False, indent=2))
        return code
    try:
        env = report(args.before, args.after)
    except (OSError, UnicodeDecodeError) as exc:
        # Коды из docstring: 2 — ошибка входа (нет файла, не UTF-8).
        print("не удалось прочитать вход: %s" % exc, file=sys.stderr)
        if args.json:
            print(json.dumps({"tool": "humanizer-report", "schema": 1,
                              "files": [{"before": args.before,
                                         "after": args.after,
                                         "error": str(exc)}],
                              "error": "вход не читается (код 2)"},
                             ensure_ascii=False, indent=2))
        return 2
    if args.json:
        print(json.dumps(env, ensure_ascii=False, indent=2))
    else:
        f = env["files"][0]
        print("Токены: keep %(keep)d, add %(add)d, delete %(delete)d"
              % f["tokens"])
        print("SARI-адаптация: keep %(keep)s, add %(add)s, delete %(delete)s"
              % f["sari_adapted"])
        print("Классы правок: " + ", ".join(
            "%s=%d" % (k, v) for k, v in f["edit_types"].items() if v))
        print("Факты: потеряно %d, изменено %d, без потерь: %s"
              % (f["facts"]["lost"], f["facts"]["changed"],
                 "да" if f["facts"]["unchanged"] else "НЕТ"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
