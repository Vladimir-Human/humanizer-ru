#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_nfc_table.py — таблица не-стартеров NFC для demo/engine.js.

Канон данных — demo/nfc_nonstarters.json (диапазоны кодовых точек с
каноническим комбинируемым классом > 0 плюс хангыль-джамо V/T
U+1160..U+11FF: ccc = 0, но komponуются с L/LV — граница NFC перед ними
небезопасна, Unicode TR#15). JSON создан из stdlib unicodedata и несет
версию unidata_version; проверка engine.js детерминирована и НЕ зависит
от версии unicodedata исполняющей среды (сверка идёт с данным репо,
а не с пересчётом по runtime).

Режимы:
    python3 demo/generate_nfc_table.py            # перезаписать блок engine.js из JSON
    python3 demo/generate_nfc_table.py --check    # сверка блока с JSON (дрейф — код 1)
    python3 demo/generate_nfc_table.py --refresh  # перегенерировать JSON из unicodedata
                                                  # исполняющей среды (явное действие
                                                  # сопровождения; фиксирует версию)
    python3 demo/generate_nfc_table.py --selftest # структурные проверки с негативами

Известная граница: таблица соответствует версии unicodedata из JSON;
комбинируемые знаки, назначенные в более новых версиях Unicode, до
--refresh считаются стартерами. При более новом runtime unicodedata
--check печатает явное напоминание (на код возврата не влияет: сверка
целостности engine.js <-> JSON полна и детерминирована).
"""
import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine.js")
DATA = os.path.join(HERE, "nfc_nonstarters.json")

BEGIN = "  // BEGIN GENERATED nfc-nonstarters (demo/generate_nfc_table.py)"
END = "  // END GENERATED nfc-nonstarters"

BLOCK_RX = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END), re.S)


def load_data(path=DATA):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def compute_ranges():
    """Диапазоны не-стартеров из unicodedata исполняющей среды."""
    ranges = []
    start = prev = None
    for cp in range(0x110000):
        nonstarter = (unicodedata.combining(chr(cp)) > 0
                      or 0x1160 <= cp <= 0x11FF)
        if nonstarter:
            if start is None:
                start = cp
            prev = cp
        elif start is not None:
            ranges.append([start, prev])
            start = prev = None
    if start is not None:
        ranges.append([start, prev])
    return ranges


def structural_errors(doc):
    """Структурная валидность канона (не зависит от версии unicodedata)."""
    errors = []
    if not isinstance(doc.get("unidata_version"), str):
        errors.append("нет unidata_version")
    ranges = doc.get("ranges")
    if not isinstance(ranges, list) or not ranges:
        errors.append("ranges не непустой список")
        return errors
    prev_end = -1
    for r in ranges:
        if (not isinstance(r, list) or len(r) != 2
                or not all(isinstance(x, int) for x in r)):
            errors.append("диапазон не пара целых: %r" % (r,))
            break
        lo, hi = r
        if lo > hi or lo < 0 or hi > 0x10FFFF:
            errors.append("диапазон вне пространства точек: %r" % (r,))
            break
        if lo <= prev_end:
            errors.append("диапазоны не упорядочены/перекрываются: %r" % (r,))
            break
        prev_end = hi
    if not any(lo <= 0x1160 and hi >= 0x11FF for lo, hi in ranges):
        errors.append("хангыль-джамо V/T (U+1160..U+11FF) не покрыты")
    return errors


def build_block(doc):
    body = ",".join("[%d,%d]" % tuple(r) for r in doc["ranges"])
    return (
        BEGIN + "\n"
        "  // Автогенерация из demo/nfc_nonstarters.json (unicodedata %s) —\n"
        "  // не править вручную; обновление: python3 demo/generate_nfc_table.py.\n"
        "  // Не-стартеры — канонические комбинируемые классы > 0 и\n"
        "  // хангыль-джамо V/T: после них префикс NFC не фиксируется\n"
        "  // (Unicode TR#15, граница нормализации — стартер, ccc = 0).\n"
        "  var NFC_NONSTARTERS = [%s];\n"
        "  function _isNfcStarter(cp) {\n"
        "    var lo = 0, hi = NFC_NONSTARTERS.length - 1;\n"
        "    while (lo <= hi) {\n"
        "      var mid = (lo + hi) >> 1;\n"
        "      var r = NFC_NONSTARTERS[mid];\n"
        "      if (cp < r[0]) { hi = mid - 1; }\n"
        "      else if (cp > r[1]) { lo = mid + 1; }\n"
        "      else { return false; }\n"
        "    }\n"
        "    return true;\n"
        "  }\n"
        "%s" % (doc["unidata_version"], body, END)
    )


def render(root_engine=None, root_data=None):
    """(fresh_text, errors): engine.js с блоком из JSON-канона."""
    engine_path = root_engine or ENGINE
    data_path = root_data or DATA
    try:
        doc = load_data(data_path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, ["nfc_nonstarters.json не читается: %r" % exc]
    errs = structural_errors(doc)
    if errs:
        return None, ["nfc_nonstarters.json структурно невалиден: %s"
                      % "; ".join(errs)]
    try:
        with open(engine_path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError as exc:
        return None, ["engine.js не читается: %r" % exc]
    block = build_block(doc)
    if not BLOCK_RX.search(src):
        return None, ["в engine.js нет блока между маркерами\n  %s\n  %s"
                      % (BEGIN, END)]
    return BLOCK_RX.sub(lambda _m: block, src, count=1), []


def check(root=None):
    """Сверка блока engine.js с JSON-каноном; список ошибок."""
    here = root or HERE
    fresh, errs = render(os.path.join(here, "engine.js"),
                         os.path.join(here, "nfc_nonstarters.json"))
    if errs:
        return errs
    with open(os.path.join(here, "engine.js"), encoding="utf-8") as fh:
        src = fh.read()
    if fresh != src:
        return ["таблица не-стартеров NFC в engine.js расходится с "
                "nfc_nonstarters.json — перегенерировать: python3 "
                "demo/generate_nfc_table.py"]
    return []


def selftest():
    fails = 0

    def case(name, ok):
        nonlocal fails
        print(("PASS: " if ok else "FAIL: ") + name)
        if not ok:
            fails += 1

    doc = load_data()
    case("канон структурно валиден", structural_errors(doc) == [])
    bad = json.loads(json.dumps(doc))
    bad["ranges"] = [[100, 90]] + bad["ranges"][1:]
    case("неупорядоченный диапазон ловится", structural_errors(bad) != [])
    bad2 = json.loads(json.dumps(doc))
    bad2["ranges"] = [r for r in bad2["ranges"]
                      if not (r[0] <= 0x1160 and r[1] >= 0x11FF)]
    case("пропущенные джамо V/T ловятся", structural_errors(bad2) != [])
    case("боевой --check зелёный", check() == [])
    with tempfile.TemporaryDirectory(prefix="nfc-table-selftest-") as td:
        import shutil
        shutil.copyfile(ENGINE, os.path.join(td, "engine.js"))
        shutil.copyfile(DATA, os.path.join(td, "nfc_nonstarters.json"))
        with open(os.path.join(td, "engine.js"), encoding="utf-8") as fh:
            eng = fh.read()
        broken = eng.replace("NFC_NONSTARTERS = [[768,846],",
                             "NFC_NONSTARTERS = [[768,847],", 1)
        if broken == eng:
            print("FAIL: не найдена точка подмены блока")
            fails += 1
        else:
            with open(os.path.join(td, "engine.js"), "w",
                      encoding="utf-8", newline="\n") as fh:
                fh.write(broken)
            case("порча блока в engine.js ловится", check(td) != [])
        with open(os.path.join(td, "nfc_nonstarters.json"), "w",
                  encoding="utf-8", newline="\n") as fh:
            json.dump({"unidata_version": doc["unidata_version"],
                       "ranges": [[0x1160, 0x11FF]]}, fh)
        case("подменённый канон ловится (структура/состав)",
             check(td) != [])
    print("САМОПРОВЕРКА generate_nfc_table: %s"
          % ("OK" if fails == 0 else "ПРОВАЛОВ %d" % fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="сверить блок engine.js с JSON-каноном, не писать")
    ap.add_argument("--refresh", action="store_true",
                    help="перегенерировать JSON из unicodedata среды "
                         "(явное действие сопровождения)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.refresh:
        doc = {"unidata_version": unicodedata.unidata_version,
               "note": load_data().get("note", ""),
               "ranges": compute_ranges()}
        with open(DATA, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("JSON-канон перегенерирован (unicodedata %s, %d диапазонов)"
              % (doc["unidata_version"], len(doc["ranges"])))
    if args.check:
        errs = check()
        if errs:
            for e in errs:
                print("FAIL: " + e)
            return 1
        doc = load_data()
        note = ""
        if unicodedata.unidata_version != doc["unidata_version"]:
            note = ("; напоминание: unicodedata среды %s новее канона %s — "
                    "обновление таблицы --refresh"
                    % (unicodedata.unidata_version, doc["unidata_version"]))
        print("NFC-таблица: соответствует nfc_nonstarters.json (unicodedata "
              "%s, %d диапазонов)%s"
              % (doc["unidata_version"], len(doc["ranges"]), note))
        return 0
    fresh, errs = render()
    if errs:
        for e in errs:
            print("FAIL: " + e)
        return 1
    with open(ENGINE, encoding="utf-8") as fh:
        src = fh.read()
    if fresh == src:
        print("NFC-таблица: без изменений")
        return 0
    with open(ENGINE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print("NFC-таблица: блок engine.js перезаписан из JSON-канона")
    return 0


if __name__ == "__main__":
    sys.exit(main())
