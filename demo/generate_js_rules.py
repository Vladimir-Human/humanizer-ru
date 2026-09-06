#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор JS-правил из markers.v1.json для статического браузерного демо.

Python re переносится в JavaScript RegExp детерминированно, с явной
Unicode-семантикой (решения зафиксированы 2026-09-06 и сверяются гейтом
scripts/check_demo_parity.py на общих векторах):

  - инлайновый флаг (?m) переносится во флаги конструктора;
  - Python-escape Uhhhhhhhh переводится в JS-escape u{hhhhhh} (нужен флаг u);
  - \\d -> \\p{Nd}, \\D -> [^\\p{Nd}]: Python \\d — десятичные цифры Unicode,
    JS \\d — только ASCII; \\p{Nd} с флагом u повторяет Python;
  - \\w -> [\\p{L}\\p{N}\\p{M}_], \\W — отрицание того же класса: Python \\w —
    буквенно-цифровые Unicode плюс подчёркивание (включая комбинируемые
    диакритики); JS \\w — только ASCII;
  - \\s / \\S -> явный класс пробельных Python (\\t \\n \\v \\f \\r
    \\u001c-\\u001f пробел \\u0085 \\u00a0 \\u1680 \\u2000-\\u200a \\u2028
    \\u2029 \\u202f \\u205f \\u3000): наборы \\s в средах различаются
    (JS включает \\ufeff, Python — \\u001c-\\u001f и \\u0085); явный класс
    одинаков в обеих;
  - \\b и \\B в исходных паттернах ЗАПРЕЩЕНЫ (генератор отказывает):
    семантика границы слова различается (Python — Unicode, JS — ASCII),
    источник обязан нести явные lookaround-классы, одинаковые в обеих
    средах;
  - флаг u добавляется, когда в результате есть \\p{...}, \\u{...} или
    символы вне BMP;
  - поле url_marker из реестра переносится в правило: engine.js применяет
    маскирование URL только к правилам без этого флага (граница детектора).

Генератор не исполняет regex сам; корректность JS-строк браузер и Node
проверяют при загрузке демо. Вход — markers.v1.json.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(HERE, "markers.v1.json")
OUT = os.path.join(HERE, "markers.js")
BS = chr(92)
NL = chr(10)

# Явный класс пробельных Python re (\\s) для переноса в JS: одинаков в
# обеих средах, в отличие от «родных» \\s.
_PY_SPACE_CLASS = (BS + "t" + BS + "n" + BS + "v" + BS + "f" + BS + "r"
                   + BS + "u001c-" + BS + "u001f" + BS + "u0020"
                   + BS + "u0085" + BS + "u00a0" + BS + "u1680"
                   + BS + "u2000-" + BS + "u200a" + BS + "u2028"
                   + BS + "u2029" + BS + "u202f" + BS + "u205f"
                   + BS + "u3000")
_WORD_CLASS = BS + "p{L}" + BS + "p{N}" + BS + "p{M}_"

# Классы переноса: ключ — двухсимвольный escape Python, значение — замена
# для JS (строки уже содержат нужные экранированные последовательности).
_CLASS_MAP = {
    "d": BS + "p{Nd}",
    "D": "[^" + BS + "p{Nd}]",
    "w": "[" + _WORD_CLASS + "]",
    "W": "[^" + _WORD_CLASS + "]",
    "s": "[" + _PY_SPACE_CLASS + "]",
    "S": "[^" + _PY_SPACE_CLASS + "]",
}


def _is_hex(text):
    return len(text) > 0 and all(c in "0123456789abcdefABCDEF" for c in text)


def py_to_js(pattern):
    source = pattern
    flags = "g"
    if source.startswith("(?m)"):
        source = source[4:]
        flags += "m"
    # \b/\B непереносимы (ASCII в JS навсегда): источник обязан нести
    # явные lookaround-классы. Отказ генератора — защита от тихого
    # расхождения семантики между CLI и демо.
    i = 0
    n = len(source)
    while i < n:
        if source[i] == BS:
            if i + 1 < n and source[i + 1] == BS:
                i += 2
                continue
            if i + 1 < n and source[i + 1] in "bB":
                raise ValueError(
                    "паттерн содержит %s%s: граница слова в JS — ASCII и "
                    "расходится с Python; замените на явные lookaround-"
                    "классы (?<![A-Za-z0-9_]) / (?![A-Za-z0-9_])"
                    % (BS, source[i + 1]))
            i += 2
            continue
        i += 1
    out = []
    i = 0
    n = len(source)
    while i < n:
        if source[i] != BS or i + 1 >= n:
            out.append(source[i])
            i += 1
            continue
        nxt = source[i + 1]
        if nxt == BS:
            out.append(BS + BS)
            i += 2
            continue
        if nxt == "U" and i + 9 < n and _is_hex(source[i + 2:i + 10]):
            code = int(source[i + 2:i + 10], 16)
            out.append(BS + "u{" + format(code, "x") + "}")
            i += 10
            continue
        if nxt in _CLASS_MAP:
            out.append(_CLASS_MAP[nxt])
            i += 2
            continue
        if nxt == '"' or nxt == "'":
            # Под флагом u экранирование кавычек недопустимо (identity
            # escapes ограничены); голая кавычка законна и в классе.
            out.append(nxt)
            i += 2
            continue
        out.append(source[i])
        out.append(nxt)
        i += 2
    source = "".join(out)
    if ((BS + "u{") in source or (BS + "p{") in source
            or any(ord(c) > 0xFFFF for c in source)):
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
            "url_marker": bool(m.get("url_marker", False)),
            "explain": m.get("explain_ru"),
        })
    # Дата сборки выводится из содержания реестра (максимальная дата
    # accessed в записях источников), а не из текущего дня: регенерация
    # детерминирована, гейт синхронности не ломается на следующий день и
    # работает во временной копии без git. Резерв — дата файла реестра.
    accessed = [m["source"]["accessed"] for m in doc["markers"]
                if m.get("source") and m["source"].get("accessed")]
    if accessed:
        build_date = max(accessed)
    else:
        import datetime
        build_date = datetime.date.fromtimestamp(
            os.path.getmtime(IN)).isoformat()
    data = {"schema_version": doc["schema_version"], "count": doc["count"],
            "meta": {"rules_version": doc["schema_version"],
                     "markers_count": doc["count"],
                     "build_date": build_date},
            "rules": rules}
    return ("/* Автогенерация из markers.v1.json скриптом generate_js_rules.py. */\n"
            "const HUMANIZER_MARKERS = " +
            json.dumps(data, ensure_ascii=False, indent=2) + ";" + NL + 'window.HUMANIZER_MARKERS = HUMANIZER_MARKERS;' + NL)


def build_sw(js_text, index_text=""):
    import hashlib
    digest = hashlib.sha256(
        (js_text + index_text).encode("utf-8")).hexdigest()[:12]
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
    index_text = ""
    index_path = os.path.join(HERE, "index.html")
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8") as fh:
            index_text = fh.read()
    with open(os.path.join(HERE, "sw.js"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(build_sw(out, index_text))
    print("Записан %s: правил %d" % (OUT, doc["count"]))


if __name__ == "__main__":
    sys.exit(main())
