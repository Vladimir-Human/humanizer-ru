# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
#!/usr/bin/env python3
"""filemarks.py — единый осмотр и снятие AI-меток поставщиков из файлов.

Осмотр:  filemarks.py --inspect файл [--json]
Снятие:  filemarks.py --clean файл -o выход [--json]
Форматы: текст (Layer A по маркерам A.7/invisible_layout из check_markers),
PNG/JPEG (C2PA/EXIF/XMP), SVG/PDF/DOCX/ODT/HTML/MD (метаданные контейнеров).

Коды: 0 — чисто (или снято), 1 — найдены метки, 2 — ошибка входа.
PDF — best-effort: без exiftool снимается только XMP-пакет. Снятие
пиксельного SynthID не выполняется (опциональный внешний скоринг — только
оценка, см. score_synthid.py). Только стандартная библиотека.
"""
import argparse
import json
import os
import sys
import tempfile
import zlib
import zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from common_fm import MAX_INPUT_BYTES, cleaned_path, emit_json, safe_write_bytes  # noqa: E402
from container_meta import clean_container, inspect_container  # noqa: E402
from image_meta import clean_image, detect_format as detect_image, inspect_image  # noqa: E402

TEXT_EXTS = {".txt", ".text", ".md", ".markdown", ".mdx", ".html", ".htm",
             ".css", ".js", ".py", ".rs", ".go", ".json", ".yaml", ".yml", ".toml", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
CONTAINER_EXTS = {".svg", ".pdf", ".docx", ".odt", ".html", ".htm", ".md", ".markdown", ".mdx"}

try:
    from check_markers import CASES as _MARKER_CASES
except Exception:
    _MARKER_CASES = {}
_LAYER_A_RX = None


def _layer_a_rx():
    """Склейка A.7 + invisible_layout: ровно то, что снимает текстовый слой."""
    global _LAYER_A_RX
    if _LAYER_A_RX is None:
        import re
        parts = []
        for name in ("zero_width", "invisible_layout"):
            if name in _MARKER_CASES:
                parts.append("(?:" + _MARKER_CASES[name][0] + ")")
        _LAYER_A_RX = re.compile("|".join(parts)) if parts else None
    return _LAYER_A_RX


def clean_text_layer(text):
    rx = _layer_a_rx()
    if rx is None:
        return text, 0
    cleaned, n = rx.subn("", text)
    return cleaned, n


def classify(path):
    if path.suffix.lower() in IMAGE_EXTS:
        return "image"
    if path.suffix.lower() in CONTAINER_EXTS:
        return "container"
    if path.suffix.lower() in TEXT_EXTS:
        return "text"
    data = path.read_bytes()[:16]
    if detect_image(data if len(data) >= 8 else path.read_bytes()) in ("png", "jpeg"):
        return "image"
    from container_meta import detect_container_format
    if detect_container_format(path, path.read_bytes()[:4096] if path.stat().st_size else b"") != "unknown":
        return "container"
    return "text"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--inspect", action="store_true", dest="inspect")
    p.add_argument("--clean", action="store_true", dest="clean")
    p.add_argument("-o", "--out", type=Path, default=None, dest="out")
    p.add_argument("--json", action="store_true", dest="json_out")
    p.add_argument("--selftest", action="store_true", dest="selftest")
    args = p.parse_args()

    if args.selftest:
        return _selftest()

    if not (args.inspect ^ args.clean):
        print("нужен ровно один режим: --inspect или --clean", file=sys.stderr)
        return 2
    if not args.path or not args.path.is_file():
        print("не файл: %s" % args.path, file=sys.stderr)
        return 2
    if args.path.stat().st_size > MAX_INPUT_BYTES:
        print("отказ: файл больше %d байт" % MAX_INPUT_BYTES, file=sys.stderr)
        return 2
    if args.clean and args.out is None:
        args.out = cleaned_path(args.path)

    kind = classify(args.path)
    if kind == "text":
        text = args.path.read_text(encoding="utf-8", errors="surrogateescape")
        if args.inspect:
            cleaned, n = clean_text_layer(text)
            rep = {"kind": "text", "path": str(args.path), "layer_a_hits": n,
                   "sample": text[:200]}
        else:
            cleaned, n = clean_text_layer(text)
            with open(args.out, "w", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write(cleaned)
            rep = {"kind": "text", "input": str(args.path), "output": str(args.out),
                   "removed": n}
    elif kind == "image":
        if args.inspect:
            rep = {"kind": "image", **inspect_image(args.path)}
        else:
            rep = {"kind": "image", **clean_image(args.path, args.out)}
    else:
        if args.inspect:
            rep = {"kind": "container", **inspect_container(args.path)}
        else:
            rep = {"kind": "container", **clean_container(args.path, args.out)}

    if args.json_out:
        emit_json(rep)
    else:
        if args.inspect:
            print("Тип: %s" % rep.get("kind"))
            print("Путь: %s" % rep.get("path"))
            if rep.get("kind") == "text":
                print("Совпадений Layer A: %d" % rep.get("layer_a_hits", 0))
            else:
                print("C2PA: %s" % rep.get("has_c2pa"))
                print("AI-метаданные: %s" % rep.get("has_ai_metadata"))
                for f in rep.get("findings", []):
                    print("  - %s" % f)
        else:
            print("Очистка: %s -> %s" % (rep.get("input"), rep.get("output")))
            for a in rep.get("actions", []):
                print("  - %s" % a)

    dirty = False
    if args.inspect:
        dirty = rep.get("layer_a_hits", 0) > 0 or rep.get("has_c2pa") or rep.get("has_ai_metadata")
    return 1 if dirty else 0


def _selftest():
    import struct
    tmp = Path(tempfile.mkdtemp())
    checks = []

    def case(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # 1) PNG с C2PA-чанком и tEXt с OpenAI
    def mk_png(chunks):
        out = b"\x89PNG\r\n\x1a\n"

        def chunk(ctype, payload):
            crc = zlib.crc32(ctype)
            crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
            return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)
        for ctype, payload in chunks:
            out += chunk(ctype, payload)
        out += chunk(b"IEND", b"")
        return out

    png = mk_png([(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
                  (b"caBX", b"c2pa manifest data"),
                  (b"tEXt", b"Generated by OpenAI"),
                  (b"IDAT", zlib.compress(b"\x00"))])
    png_path = tmp / "x.png"
    png_path.write_bytes(png)
    rep = inspect_image(png_path)
    case("PNG: C2PA-чанк найден", rep["has_c2pa"], str(rep["findings"][:2]))
    out_png = tmp / "x.cleaned.png"
    rep2 = clean_image(png_path, out_png)
    case("PNG: снятие убирает C2PA и текстовые чанки",
         not rep2["still_has_c2pa"] and not rep2["still_has_ai_metadata"], str(rep2["actions"]))

    # 2) JPEG с APP11 и APP1 c2pa
    def mk_jpeg():
        out = bytearray(b"\xff\xd8")

        def seg(marker, payload):
            out.extend(b"\xff" + bytes([marker]))
            out.extend(struct.pack(">H", len(payload) + 2))
            out.extend(payload)
        seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
        seg(0xEB, b"jumbf c2pa")
        seg(0xE1, b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x00\x00\x00\x00")
        out.extend(b"\xff\xda")
        return bytes(out)
    jpg_path = tmp / "x.jpg"
    jpg_path.write_bytes(mk_jpeg())
    rep = inspect_image(jpg_path)
    case("JPEG: APP11 найден", rep["has_c2pa"], str(rep["findings"][:2]))
    out_jpg = tmp / "x.cleaned.jpg"
    rep2 = clean_image(jpg_path, out_jpg)
    case("JPEG: APP11/APP1 сняты", not rep2["still_has_c2pa"], str(rep2["actions"]))

    # 3) SVG с metadata и xmpmeta
    svg = ('<svg xmlns="http://www.w3.org/2000/svg"><metadata>XMP c2pa</metadata>'
           '<x:xmpmeta xmlns:x="adobe:ns:meta/">contentcredentials</x:xmpmeta><circle/></svg>')
    svg_path = tmp / "x.svg"
    svg_path.write_bytes(svg.encode())
    rep = inspect_container(svg_path)
    case("SVG: metadata найден", rep["has_ai_metadata"], str(rep["findings"][:2]))
    out_svg = tmp / "x.cleaned.svg"
    rep2 = clean_container(svg_path, out_svg)
    case("SVG: metadata снят", not rep2["still_has_ai_metadata"], str(rep2["actions"]))

    # 4) Markdown frontmatter с AI-ключами
    md = "---\ntitle: ок\nmodel: claude-4\ngenerator: x\n---\n\nТекст.\n"
    md_path = tmp / "x.md"
    md_path.write_bytes(md.encode())
    rep = inspect_container(md_path)
    case("MD: AI-frontmatter найден", rep["has_ai_metadata"], str(rep["findings"][:2]))
    out_md = tmp / "x.cleaned.md"
    rep2 = clean_container(md_path, out_md)
    case("MD: AI-ключи сняты", "model" not in out_md.read_text(encoding="utf-8"),
         str(rep2["actions"]))

    # 5) DOCX с customXml и docProps
    buf = __import__("io").BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "<w:document/>")
        zf.writestr("customXml/item1.xml", "<c2pa/>")
        zf.writestr("docProps/core.xml", "<dc:creator>Claude</dc:creator>")
    docx_path = tmp / "x.docx"
    docx_path.write_bytes(buf.getvalue())
    rep = inspect_container(docx_path)
    case("DOCX: customXml найден", rep["has_ai_metadata"], str(rep["findings"][:2]))
    out_docx = tmp / "x.cleaned.docx"
    rep2 = clean_container(docx_path, out_docx)
    with zipfile.ZipFile(out_docx) as zf:
        names = set(zf.namelist())
    case("DOCX: customXml снят", not any(n.startswith("customXml/") for n in names),
         str(rep2["actions"]))

    # 6) Текст: слой A
    txt_path = tmp / "x.txt"
    txt_path.write_text("сло\u200bво и мягкий\u00adперенос\n", encoding="utf-8")
    import re as _re
    if _layer_a_rx() is not None:
        cleaned, n = clean_text_layer(txt_path.read_text(encoding="utf-8"))
        case("TXT: слой A снят", n == 2 and "\u200b" not in cleaned and "\u00ad" not in cleaned,
             "n=%d" % n)
    else:
        case("TXT: слой A снят", False, "check_markers не импортирован")

    fails = [n for n, ok, _ in checks if not ok]
    for n, ok, detail in checks:
        print(("PASS: " if ok else "FAIL: ") + n + ((" | " + detail) if detail else ""))
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
