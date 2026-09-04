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
NL = chr(10)


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


def _validate_source(rule_id, source):
    """В исходнике правила не должно быть сырых контрольных символов:
    regex пишется экранированными последовательностями, а сырой перевод строки, нулевой байт в JS-литерале ломают и файл, и подсветку."""
    for ch in source:
        if ord(ch) < 0x20 and ch != "	":
            raise ValueError("маркер %s: сырой контрольный символ U+%04X"
                             % (rule_id, ord(ch)))





def build_js(doc):
    rules = []
    for m in doc["markers"]:
        source, flags = py_to_js(m["pattern"])
        _validate_source(m["id"], source)
        rules.append({
            "id": m["id"],
            "class": m["class"],
            "description": m["description"],
            "source": source,
            "flags": flags,
            "explain": m.get("explain_ru"),
        })
    import datetime
    data = {"schema_version": doc["schema_version"], "count": doc["count"],
            "meta": {"rules_version": doc["schema_version"],
                     "markers_count": doc["count"],
                     "build_date": datetime.date.today().isoformat()},
            "rules": rules}
    return ("/* Автогенерация из markers.v1.json скриптом generate_js_rules.py. */\n"
            "const HUMANIZER_MARKERS = " +
            json.dumps(data, ensure_ascii=False, indent=2) + ";" + NL + 'window.HUMANIZER_MARKERS = HUMANIZER_MARKERS;' + NL)


def build_sw(js_text):
    import hashlib
    digest = hashlib.sha256(js_text.encode("utf-8")).hexdigest()[:12]
    return (
        "/* Автогенерация generate_js_rules.py: кэш версионируется хэшем правил. */\n"
        "const CACHE = \"humanizer-ru-" + digest + "\";\n"
        "const STATIC = [\"./\", \"./index.html\", \"./brand.css\", \"./markers.js\",\n"
        "  \"./engine.js\", \"./sample.js\", \"./favicon.svg\", \"./manifest.json\"];\n"
        "self.addEventListener(\"install\", (e) => {\n"
        "  self.skipWaiting();\n"
        "  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)));\n"
        "});\n"
        "self.addEventListener(\"activate\", (e) => {\n"
        "  clients.claim();\n"
        "  e.waitUntil(caches.keys().then((keys) => Promise.all(\n"
        "    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));\n"
        "});\n"
        "self.addEventListener(\"fetch\", (e) => {\n"
        "  if (e.request.method !== \"GET\") return;\n"
        "  e.respondWith(caches.match(e.request).then((hit) => hit ||\n"
        "    fetch(e.request).then((res) => {\n"
        "      const copy = res.clone();\n"
        "      caches.open(CACHE).then((c) => c.put(e.request, copy));\n"
        "      return res;\n"
        "    })));\n"
        "});\n")


def main():
    with open(IN, encoding="utf-8") as fh:
        doc = json.load(fh)
    out = build_js(doc)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    with open(os.path.join(HERE, "sw.js"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(build_sw(out))
    print("Записан %s: правил %d" % (OUT, doc["count"]))


if __name__ == "__main__":
    sys.exit(main())
