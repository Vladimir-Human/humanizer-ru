#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_evidence.py — F18: метаданные docx как свидетельства класса hard
в режиме «контекст, не вердикт» (стык с F10/F5a).

Читает .docx (zipfile, stdlib): docProps/core.xml (creator, dates, revision),
docProps/app.xml (Application, AppVersion, TotalTime), число w:rsid в
document.xml. Никаких выводов об авторстве: только контекст правки.

Запуск:
  python3 tools/docx_evidence.py файл.docx [--json]
  python3 tools/docx_evidence.py --selftest
"""
import argparse
import io
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NOTE = ("контекст, не вердикт: метаданные свидетельствуют о истории правки, "
        "но не доказывают авторство и не заменяют детекторный слой")


def extract(path):
    out = {"evidence_class": "hard-context", "note": NOTE,
           "core": {}, "app": {}, "rsid_count": None}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "docProps/core.xml" in names:
            root = ET.fromstring(z.read("docProps/core.xml"))
            for el in root:
                tag = el.tag.split("}")[-1]
                if tag in ("creator", "lastModifiedBy", "revision",
                           "created", "modified"):
                    out["core"][tag] = (el.text or "")[:120]
        if "docProps/app.xml" in names:
            root = ET.fromstring(z.read("docProps/app.xml"))
            for el in root:
                tag = el.tag.split("}")[-1]
                if tag in ("Application", "AppVersion", "TotalTime",
                           "Company"):
                    out["app"][tag] = (el.text or "")[:120]
        if "word/document.xml" in names:
            data = z.read("word/document.xml").decode("utf-8", "replace")
            out["rsid_count"] = len(set(re.findall(r"w:rsid[A-Za-z]*=\"([0-9A-Fa-f]+)\"", data)))
    return out


def _synthetic_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docProps/core.xml",
                   '<?xml version="1.0"?><cp:coreProperties '
                   'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                   'xmlns:dcterms="http://purl.org/dc/terms/">'
                   '<dc:creator>Test Author</dc:creator>'
                   '<cp:lastModifiedBy>Second Editor</cp:lastModifiedBy>'
                   '<cp:revision>3</cp:revision></cp:coreProperties>')
        z.writestr("docProps/app.xml",
                   '<?xml version="1.0"?><Properties '
                   'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                   '<Application>Microsoft Office Word</Application>'
                   '<AppVersion>16.0</AppVersion><TotalTime>12</TotalTime></Properties>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0"?><w:document '
                   'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p w:rsidR="00A1B2C3" w:rsidRPr="00D4E5F6">'
                   '<w:r><w:t>текст</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def selftest():
    import tempfile
    checks = []
    fd, path = tempfile.mkstemp(suffix=".docx")
    with os.fdopen(fd, "wb") as fh:
        fh.write(_synthetic_docx())
    try:
        ev = extract(path)
        checks.append(("creator извлечён", ev["core"].get("creator") == "Test Author"))
        checks.append(("revision извлечён", ev["core"].get("revision") == "3"))
        checks.append(("Application извлечён",
                       ev["app"].get("Application", "").startswith("Microsoft")))
        checks.append(("rsid посчитаны", (ev["rsid_count"] or 0) >= 2))
        checks.append(("пометка «контекст, не вердикт» на месте",
                       "не вердикт" in ev["note"]))
    finally:
        os.unlink(path)
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА docx-evidence: %d FAIL" % fails)
    return 1 if fails else 0


import os  # noqa: E402  (используется в selftest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.path:
        ap.print_help()
        return 2
    import json
    ev = extract(args.path)
    if args.json:
        print(json.dumps(ev, ensure_ascii=False, indent=2))
    else:
        for k, v in ev.items():
            print("%s: %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
