#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор JS-правил из markers.v1.json для статического браузерного демо.

Python re переносится в JavaScript RegExp:
  - инлайновый флаг (?m) переносится во флаги конструктора;
  - Python-escape Uhhhhhhhh переводится в JS-escape u{hhhhhh} (нужен флаг u);
  - остальные escape (d, s, w, b, uXXXX, xHH) в JS RegExp работают как есть.
Генератор не исполняет regex сам; корректность JS-строк браузер и Node
проверяют при загрузке демо. Вход — markers.v1.json.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(HERE, "markers.v1.json")
OUT = os.path.join(HERE, "markers.js")
BS = chr(92)


def _is_hex(text):
    return len(text) > 0 and all(c in "0123456789abcdefABCDEF" for c in text)


def py_to_js(pattern):
    source = pattern
    flags = "g"
    if source.startswith("(?m)"):
        source = source[4:]
        flags += "m"
    out = []
    i = 0
    n = len(source)
    while i < n:
        if (source[i] == BS and i + 9 < n and source[i + 1] == "U"
                and _is_hex(source[i + 2:i + 10])):
            code = int(source[i + 2:i + 10], 16)
            out.append(BS + "u{" + format(code, "x") + "}")
            i += 10
            continue
        out.append(source[i])
        i += 1
    source = "".join(out)
    if (BS + "u{") in source or any(ord(c) > 0xFFFF for c in source):
        flags += "u"
    return source, flags


def build_js(doc):
    rules = []
    for m in doc["markers"]:
        source, flags = py_to_js(m["pattern"])
        rules.append({
            "id": m["id"],
            "class": m["class"],
            "description": m["description"],
            "source": source,
            "flags": flags,
        })
    data = {"schema_version": doc["schema_version"], "count": doc["count"], "rules": rules}
    return ("/* Автогенерация из markers.v1.json скриптом generate_js_rules.py. */\n"
            "const HUMANIZER_MARKERS = " +
            json.dumps(data, ensure_ascii=False, indent=2) + ";\n")


def main():
    with open(IN, encoding="utf-8") as fh:
        doc = json.load(fh)
    out = build_js(doc)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    print("Записан %s: правил %d" % (OUT, doc["count"]))


if __name__ == "__main__":
    sys.exit(main())
