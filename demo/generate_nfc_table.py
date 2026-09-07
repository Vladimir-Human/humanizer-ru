#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_nfc_table.py — генерация таблицы не-стартеров NFC для demo/engine.js.

Канонический источник — stdlib unicodedata (канонические комбинируемые
классы). Таблица: диапазоны кодовых точек, после которых префикс NFC не
фиксируется (ccc > 0), плюс хангыль-джамо V/T (U+1160..U+11FF: ccc = 0,
но komponуются с L/LV — граница NFC перед ними небезопасна, Unicode TR#15).

Блок в engine.js между маркерами BEGIN/END GENERATED перезаписывается
целиком; --check сверяет встроенный блок с регенерацией (дрейф — код 1).
Версия unicodedata фиксируется в заголовке блока: смена версии Python с
другим Unicode — явная перегенерация, а не тихий дрейф.

Запуск:  python3 demo/generate_nfc_table.py            # перезаписать блок
         python3 demo/generate_nfc_table.py --check    # только сверка
"""
import argparse
import os
import re
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine.js")

BEGIN = "  // BEGIN GENERATED nfc-nonstarters (demo/generate_nfc_table.py)"
END = "  // END GENERATED nfc-nonstarters"

BLOCK_RX = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END), re.S)


def compute_ranges():
    """Диапазоны не-стартеров: [(lo, hi), ...] по всему пространству точек."""
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
            ranges.append((start, prev))
            start = prev = None
    if start is not None:
        ranges.append((start, prev))
    return ranges


def build_block():
    ranges = compute_ranges()
    body = ",".join("[%d,%d]" % r for r in ranges)
    return (
        BEGIN + "\n"
        "  // Автогенерация: unicodedata %s (stdlib Python). Не-стартеры —\n"
        "  // канонические комбинируемые классы > 0 и хангыль-джамо V/T:\n"
        "  // после них префикс NFC не фиксируется (Unicode TR#15, граница\n"
        "  // нормализации — стартер, ccc = 0, кроме джамо V/T).\n"
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
        "%s" % (unicodedata.unidata_version, body, END)
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="сверить встроенный блок с регенерацией, не писать")
    args = ap.parse_args(argv)
    with open(ENGINE, encoding="utf-8") as fh:
        src = fh.read()
    block = build_block()
    if not BLOCK_RX.search(src):
        print("FAIL: в demo/engine.js нет блока между маркерами\n  %s\n  %s"
              % (BEGIN, END))
        return 1
    fresh = BLOCK_RX.sub(lambda _m: block, src, count=1)
    if args.check:
        if fresh != src:
            print("FAIL: таблица не-стартеров NFC в engine.js расходится с "
                  "unicodedata %s — перегенерируйте: python3 "
                  "demo/generate_nfc_table.py" % unicodedata.unidata_version)
            return 1
        print("NFC-таблица: соответствует unicodedata %s (%d диапазонов)"
              % (unicodedata.unidata_version, len(compute_ranges())))
        return 0
    if fresh == src:
        print("NFC-таблица: без изменений (unicodedata %s)"
              % unicodedata.unidata_version)
        return 0
    with open(ENGINE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print("NFC-таблица: блок перезаписан (unicodedata %s, %d диапазонов)"
          % (unicodedata.unidata_version, len(compute_ranges())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
