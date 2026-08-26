#!/usr/bin/env python3
# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
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
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from common_fm import MAX_INPUT_BYTES, cleaned_path, emit_json, safe_write_text  # noqa: E402
from container_meta import clean_container, inspect_container  # noqa: E402
from image_meta import clean_image, detect_format as detect_image, inspect_image  # noqa: E402

TEXT_EXTS = {".txt", ".text", ".css", ".js", ".py", ".rs", ".go",
             ".json", ".yaml", ".yml", ".toml", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
CONTAINER_EXTS = {".svg", ".pdf", ".docx", ".pptx", ".xlsx", ".odt", ".html", ".htm", ".md", ".markdown", ".mdx"}

from text_layer import (DETECTOR_OK, clean_markup, clean_text_layer,  # noqa: E402
                        clean_tag_strip, layer_a_rx)


# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def _unsupported_binary(head):
    """I.13: известные, но неподдерживаемые бинарные форматы по magic.

    Возвращает имя формата или None. Это защита от ложно-чистого отчёта:
    прежде такой файл молча относился к «text» и сканировался как мусор.
    WebP поддерживается с ревизии I.27 и сюда не входит.
    """
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        return "tiff"
    # JPEG XL: codestream начинается FF 0A, контейнер — сигнатурой «JXL ».
    if head[:2] == b"\xff\x0a" or (len(head) >= 12 and head[:4] == b"JXL "):
        return "jxl"
    # ISO-BMFF (HEIC/AVIF): файл начинается с 4-байтового размера бокса, затем
    # "ftyp", затем major brand (HEIC/AVIF/…) на байтах 8–12.
    if head[4:8] == b"ftyp":
        brand = head[8:12].lower()
        if brand in (b"avif", b"avis", b"mif1", b"heic", b"heix", b"hevc",
                     b"heif", b"miaf"):
            return "heic/avif"
    return None


def classify(path):
    if path.suffix.lower() in IMAGE_EXTS:
        return "image"
    if path.suffix.lower() in CONTAINER_EXTS:
        return "container"
    if path.suffix.lower() in TEXT_EXTS:
        return "text"
    with open(path, "rb") as fh:
        head = fh.read(4096)
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 65536))
        tail = fh.read(65536)
    unsupported = _unsupported_binary(head)
    if unsupported:
        return "unsupported:" + unsupported
    if detect_image(head[:16] if len(head) >= 16 else head) in ("png", "jpeg", "webp"):
        return "image"
    from container_meta import detect_container_format
    if detect_container_format(path, head + tail if size else b"") != "unknown":
        return "container"
    return "text"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--inspect", action="store_true", dest="inspect")
    p.add_argument("--clean", action="store_true", dest="clean")
    p.add_argument("-o", "--out", type=Path, default=None, dest="out")
    p.add_argument("--json", action="store_true", dest="json_out")
    p.add_argument("--upstream-dir", type=Path, default=None, dest="upstream_dir",
                   help="С --inspect: внешний скоринг пиксельного SynthID "
                        "(best-effort оценка, НЕ снятие; без каталога и "
                        "зависимостей — честный блок synthid: unavailable)")
    p.add_argument("--reencode", action="store_true", dest="reencode",
                   help="С --clean для PNG: lossless-переупаковка IDAT — "
                        "байтовый хэш меняется, пиксели нет (opt-in I.31; "
                        "ломает мягкую привязку C2PA по хэшу, но НЕ гарантирует "
                        "снятие знака, в отчёте «байты изменены»)")
    p.add_argument("--selftest", action="store_true", dest="selftest")
    args = p.parse_args()

    if args.selftest:
        return _selftest()
    try:
        return _run(args)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print("ошибка обработки: %s" % exc, file=sys.stderr)
        return 2


def _score_synthid(path, upstream_dir):
    """Внешний скоринг пиксельного SynthID через score_synthid.py .

    Только оценка (best-effort, НЕ снятие, НЕ официальный детектор Google).
    Без --upstream-dir поле не вызывается; при недоступности checkout или
    зависимостей возвращается честный блок {"available": False}, а не тишина.
    """
    if upstream_dir is None:
        return {"available": False, "note": "скоринг не запрошен (нет --upstream-dir)"}
    script = os.path.join(HERE, "score_synthid.py")
    try:
        proc = subprocess.run(
            [sys.executable, script, str(path), "--upstream-dir",
             str(upstream_dir), "--json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "note": "скоринг не отработал: %s" % exc}
    if proc.returncode == 0:
        try:
            return json.loads(proc.stdout)
        except ValueError:
            return {"available": False, "note": "скоринг вернул не-JSON"}
    return {"available": False, "note": proc.stderr.strip()[:200]
            or "скоринг вернул код %d" % proc.returncode}


def _run(args):
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
    if kind.startswith("unsupported"):
        fmt = kind.split(":", 1)[1] if ":" in kind else kind
        print("неподдерживаемый бинарный формат (%s): %s" % (fmt, args.path),
              file=sys.stderr)
        return 2
    if kind == "text":
        text = args.path.read_text(encoding="utf-8", errors="surrogateescape")
        if not DETECTOR_OK:
            print("детектор check_markers недоступен: результат слоя A недействителен",
                  file=sys.stderr)
            return 2
        if args.inspect:
            cleaned, n = clean_text_layer(text)
            _c, m = clean_markup(text)
            rep = {"kind": "text", "path": str(args.path), "layer_a_hits": n,
                   "class_a_markers": m}
        else:
            # Слой A (невидимые + tag-символы) -> I.10 артефакты класса A.
            cleaned, n = clean_text_layer(text)
            cleaned, m = clean_markup(cleaned)
            # остатки после чистки: повторный прогон должен дать 0
            _rem, rem_a = clean_markup(cleaned)
            _rem2, rem_tag = clean_tag_strip(_rem)
            safe_write_text(args.out, cleaned)
            rep = {"kind": "text", "input": str(args.path), "output": str(args.out),
                   "removed": n, "class_a_removed": m,
                   "class_a_remaining": rem_a, "tag_remaining": rem_tag}
    elif kind == "image":
        if args.inspect:
            rep = {"kind": "image", **inspect_image(args.path)}
            synthid = _score_synthid(args.path, args.upstream_dir)
            if synthid is not None:
                rep["synthid"] = synthid
        else:
            rep = {"kind": "image", **clean_image(args.path, args.out,
                                                  reencode=args.reencode)}
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
            if rep.get("kind") == "text":
                print("Снято символов: %d" % rep.get("removed", 0))
                print("Снято артефактов класса A: %d" % rep.get("class_a_removed", 0))
            for a in rep.get("actions", []):
                print("  - %s" % a)

    dirty = False
    if args.inspect:
        dirty = (rep.get("layer_a_hits", 0) > 0 or rep.get("class_a_markers", 0) > 0
                 or rep.get("has_c2pa") or rep.get("has_ai_metadata"))
    else:
        # clean: код 1, если после чистки метки остались (PDF без exiftool и т.п.)
        #  недоступный детектор для контейнера уже породил ValueError -> код 2;
        # остаточные видимые/невидимые приметы учитываются отдельным флагом.
        dirty = bool(rep.get("still_has_c2pa") or rep.get("still_has_ai_metadata")
                     or rep.get("class_a_remaining") or rep.get("tag_remaining"))
    return 1 if dirty else 0


def _selftest():
    import struct
    import image_meta as _im
    tmp = Path(tempfile.mkdtemp())
    checks = []

    def _png_chunk(ctype, payload):
        crc = zlib.crc32(ctype)
        crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)

    def _mk_png_idat(plain):
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
                + _png_chunk(b"IDAT", zlib.compress(plain))
                + _png_chunk(b"IEND", b""))

    def _png_idat_plain(data):
        pos, raw = 8, bytearray()
        while pos + 8 <= len(data):
            length = struct.unpack(">I", data[pos:pos + 4])[0]
            ctype = data[pos + 4:pos + 8]
            cs, ce = pos + 8, pos + 8 + length
            if ce + 4 > len(data):
                break
            if ctype == b"IDAT":
                raw.extend(data[cs:ce])
            pos = ce + 4
        return zlib.decompress(bytes(raw))

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
    # 5-регресс: generator-атрибут снимается и при наличии metadata
    svg2 = ('<svg xmlns="http://www.w3.org/2000/svg" generator="Claude"><metadata>x</metadata></svg>')
    svg2_path = tmp / "g.svg"
    svg2_path.write_bytes(svg2.encode())
    rep2c = clean_container(svg2_path, tmp / "g.cleaned.svg")
    case("SVG: generator-атрибут снят вместе с metadata",
         not rep2c["still_has_ai_metadata"] and b"generator" not in (tmp / "g.cleaned.svg").read_bytes(),
         str(rep2c["actions"]))
    # 3-регресс: meta Generated by снимается
    html = '<html><head><meta name="generator" content="Generated by OpenAI"></head><body>x</body></html>'
    html_path = tmp / "x.html"
    html_path.write_bytes(html.encode())
    rep = inspect_container(html_path)
    case("HTML: meta Generated by найден", rep["has_ai_metadata"], str(rep["findings"][:2]))
    rep2h = clean_container(html_path, tmp / "x.cleaned.html")
    case("HTML: meta Generated by снят", not rep2h["still_has_ai_metadata"], str(rep2h["actions"]))
    # 6-регресс: русский YAML-ключ
    md_ru = "---\nзаголовок: ок\nмодель: claude-4\n---\n\nТекст.\n"
    md_ru_path = tmp / "ru.md"
    md_ru_path.write_bytes(md_ru.encode())
    rep = inspect_container(md_ru_path)
    case("MD: русский AI-ключ найден", rep["has_ai_metadata"], str(rep["findings"][:2]))
    # 4-регресс: jumb-чанк снимается
    png_j = mk_png([(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
                    (b"juMB", b"binary jumbf data"),
                    (b"IDAT", zlib.compress(b"\x00"))])
    png_j_path = tmp / "j.png"
    png_j_path.write_bytes(png_j)
    rep = inspect_image(png_j_path)
    case("PNG: juMB найден", rep["has_c2pa"], str(rep["findings"][:2]))
    rep2j = clean_image(png_j_path, tmp / "j.cleaned.png")
    case("PNG: juMB снят", not rep2j["still_has_c2pa"], str(rep2j["actions"]))
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

    # 4-регресс: DOCX Application=Gemini виден и чистится
    buf2 = __import__("io").BytesIO()
    with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "<w:document/>")
        zf.writestr("docProps/app.xml", "<Application>Gemini</Application>")
    d2 = tmp / "g.docx"
    d2.write_bytes(buf2.getvalue())
    rep = inspect_container(d2)
    case("DOCX: Application=Gemini найден", rep["has_ai_metadata"], str(rep["findings"][:2]))
    rep2d = clean_container(d2, tmp / "g.cleaned.docx")
    with zipfile.ZipFile(tmp / "g.cleaned.docx") as zf:
        app = zf.read("docProps/app.xml").decode("utf-8")
    case("DOCX: Application=Gemini вычищен", "Gemini" not in app, str(rep2d["actions"]))
    # 3-регресс: ODT manifest с C2PA-записью
    buf3 = __import__("io").BytesIO()
    with zipfile.ZipFile(buf3, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", "<content/>")
        zf.writestr("meta.xml", "<office:meta/>")
        zf.writestr("META-INF/manifest.xml",
                    '<manifest:manifest xmlns:manifest="urn:oasis"><manifest:file-entry manifest:full-path="content.xml"/><manifest:file-entry manifest:full-path="c2pa.json"/></manifest:manifest>')
    o1 = tmp / "x.odt"
    o1.write_bytes(buf3.getvalue())
    rep = inspect_container(o1)
    case("ODT: C2PA-запись manifest найдена", rep["has_c2pa"], str(rep["findings"][:2]))
    rep2o = clean_container(o1, tmp / "x.cleaned.odt")
    with zipfile.ZipFile(tmp / "x.cleaned.odt") as zf:
        man = zf.read("META-INF/manifest.xml").decode("utf-8")
    case("ODT: C2PA-запись manifest снята", "c2pa.json" not in man, str(rep2o["actions"]))

    # самоаудит-регресс: описание скилла не помечается как AI-метаданные
    md_self = ("---\ntitle: humanizer-ru\ndescription: Detects AI-generated Russian text\n"
               "compatibility: Claude.ai, Claude Code\nlicense: MIT\n---\n\nТекст.\n")
    md_self_p = tmp / "self.md"
    md_self_p.write_bytes(md_self.encode())
    rep = inspect_container(md_self_p)
    case("MD: самоописание скилла не помечается", not rep["has_ai_metadata"],
         str(rep["findings"][:3]))
    # generator со значением Claude — помечается
    md_gen = "---\ntitle: x\ngenerator: Claude\n---\n\nТекст.\n"
    md_gen_p = tmp / "gen.md"
    md_gen_p.write_bytes(md_gen.encode())
    rep = inspect_container(md_gen_p)
    case("MD: generator=Claude помечается", rep["has_ai_metadata"], str(rep["findings"][:2]))

    # 6) Текст: слой A
    txt_path = tmp / "x.txt"
    txt_path.write_text("сло\u200bво и мягкий\u00adперенос\n", encoding="utf-8")
    if layer_a_rx() is not None:
        cleaned, n = clean_text_layer(txt_path.read_text(encoding="utf-8"))
        case("TXT: слой A снят", n == 2 and "\u200b" not in cleaned and "\u00ad" not in cleaned,
             "n=%d" % n)
    else:
        case("TXT: слой A снят", False, "check_markers не импортирован")

    # 7) I.8: PUA-разделители снимаются слоем A (и длинная, и короткая форма)
    pua1 = "блок \ue200cite\ue202x\ue201 конец"
    c1, n1 = clean_text_layer(pua1)
    case("PUA: длинная форма снята слоем A", n1 == 3 and "\ue200" not in c1 and "\ue201" not in c1,
         "n=%d" % n1)
    pua2 = "конец предложения.\uea012\uea02"
    c2, n2 = clean_text_layer(pua2)
    case("PUA: короткая форма снимает обёртки, цифру сохраняет",
         n2 == 2 and "2" in c2 and "\uea01" not in c2 and "\uea02" not in c2,
         "n=%d res=%r" % (n2, c2))

    # 8) I.10: MARKUP_CASES — видимые артефакты класса A
    markup_in = "turn0search0 и :contentReference[oaicite:0]{index=0} и [cite: 8] и【1†source】."
    m_clean, m_n = clean_markup(markup_in)
    case("MARKUP: артефакты класса A сняты",
         m_n >= 4 and "turn0search0" not in m_clean and "contentReference" not in m_clean,
         "n=%d res=%r" % (m_n, m_clean))
    # I.10-б: utm вырезается как параметр URL, ссылка сохраняется
    utm_in = "см. https://example.com/?id=5&utm_source=chatgpt.com далее"
    u_clean, u_n = clean_markup(utm_in)
    case("MARKUP: utm режется как параметр, ссылка цела",
         u_n == 1 and "https://example.com/?id=5" in u_clean and "utm_source" not in u_clean,
         "n=%d res=%r" % (u_n, u_clean))
    utm_neg, u_neg = clean_markup("utm_source=openai упомянут в статье о трекинге")
    case("MARKUP: utm вне URL не трогается", u_neg == 0 and "utm_source" in utm_neg,
         "n=%d" % u_neg)
    # I.10-в: think-блок удаляется вместе с содержимым
    think_in = "Начало. <thinking>Сначала разберусь.</thinking> Ответ: 42."
    th_clean, th_n = clean_markup(think_in)
    case("MARKUP: think-блок удалён с содержимым",
         th_n == 1 and "thinking" not in th_clean and "разберусь" not in th_clean,
         "n=%d res=%r" % (th_n, th_clean))

    # 9) I.28: tag-символы снимаются, эмодзи-флаг сохраняется
    flag = "\U0001F3F4\U000E0067\U000E0062\U000E0067\U000E007F"
    solo = "x\U000E0020y\u206Az\u034Fw"
    tag_clean, tag_n = clean_tag_strip(flag)
    solo_clean, solo_n = clean_tag_strip(solo)
    case("TAG: эмодзи-флаг не тронут", tag_n == 0 and tag_clean == flag, "n=%d" % tag_n)
    case("TAG: одиночные tag/format-символы сняты",
         solo_n == 3 and solo_clean == "xyzw", "n=%d res=%r" % (solo_n, solo_clean))

    # 10) I.12: вложенный DOCX с меченым PNG — медиа очищается, текст сохраняется
    png_media = mk_png([(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
                        (b"caBX", b"c2pa manifest data"),
                        (b"IDAT", zlib.compress(b"\x00"))])
    docx_media = __import__("io").BytesIO()
    with zipfile.ZipFile(docx_media, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "<w:document><w:p>текст\u200b</w:p></w:document>")
        zf.writestr("word/media/image1.png", png_media)
    dm = tmp / "media.docx"
    dm.write_bytes(docx_media.getvalue())
    repm = clean_container(dm, tmp / "media.cleaned.docx")
    with zipfile.ZipFile(tmp / "media.cleaned.docx") as zf:
        media_after = zf.read("word/media/image1.png")
        doc_after = zf.read("word/document.xml").decode("utf-8")
    case("DOCX: вложенный PNG с C2PA очищен, текст слоя A снят",
         b"caBX" not in media_after and "\u200b" not in doc_after,
         str(repm["actions"]))
    # негатив: чистый вложенный PNG не меняет полезную нагрузку
    clean_png = mk_png([(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)),
                        (b"IDAT", zlib.compress(b"\x00"))])
    # 11) I.12: data-URI в HTML перекодируется чисто
    b64 = __import__("base64").b64encode(png_media).decode("ascii")
    html_duri = '<html><body><img src="data:image/png;base64,%s"></body></html>' % b64
    hd = tmp / "duri.html"
    hd.write_text(html_duri, encoding="utf-8")
    repd = clean_container(hd, tmp / "duri.cleaned.html")
    out_html = (tmp / "duri.cleaned.html").read_text(encoding="utf-8")
    case("HTML: data-URI PNG с C2PA перекодирован без маркера",
         "c2pa" not in out_html and "data:image/png;base64," in out_html,
         str(repd["actions"]))

    # 12) I.14: JPEG APP2/ICC сохраняется при strip_all
    def mk_jpeg_icc():
        out = bytearray(b"\xff\xd8")

        def seg(marker, payload):
            out.extend(b"\xff" + bytes([marker]))
            out.extend(struct.pack(">H", len(payload) + 2))
            out.extend(payload)
        seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
        seg(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"\x00" * 64)  # APP2 ICC
        seg(0xEB, b"jumbf c2pa")
        out.extend(b"\xff\xda")
        return bytes(out)
    icc_jpg = tmp / "icc.jpg"
    icc_jpg.write_bytes(mk_jpeg_icc())
    icc_clean, _ = _im.strip_jpeg(icc_jpg.read_bytes())
    case("JPEG: APP2/ICC сохранён при strip_all, APP11 снят",
         b"ICC_PROFILE" in icc_clean and b"jumbf" not in icc_clean,
         "len %d -> %d" % (len(icc_jpg.read_bytes()), len(icc_clean)))
    # негатив: APP2 не-ICC снимается при strip_all
    def mk_jpeg_mpf():
        out = bytearray(b"\xff\xd8")

        def seg(marker, payload):
            out.extend(b"\xff" + bytes([marker]))
            out.extend(struct.pack(">H", len(payload) + 2))
            out.extend(payload)
        seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
        seg(0xE2, b"MPF\x00" + b"\x00" * 16)
        out.extend(b"\xff\xda")
        return bytes(out)
    mpf_clean, _ = _im.strip_jpeg(mk_jpeg_mpf())
    case("JPEG: APP2 не-ICC снимается при strip_all", b"MPF" not in mpf_clean,
         "len %d" % len(mpf_clean))

    # 13) I.13/I.27: WebP теперь ПОДДЕРЖИВАЕТСЯ (детект и снятие EXIF/XMP),
    # остальные бинарные форматы отклоняются как раньше.
    webp = tmp / "x.webp"
    webp.write_bytes(b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 32)
    case("BIN: WebP теперь поддерживается (image)", classify(webp) == "image",
         classify(webp))
    webp_exif = (b"RIFF" + struct.pack("<I", 4 + (8 + 8 + 8 + 8))
                 + b"WEBP" + b"VP8X\x0a\x00\x00\x00" + b"\x00" * 10
                 + b"EXIF" + struct.pack("<I", 4) + b"AIGC"
                 + b"XMP " + struct.pack("<I", 4) + b"c2pa")
    wc, wacts = _im.strip_webp(webp_exif)
    case("WebP: EXIF/XMP сняты",
         b"AIGC" not in wc and b"c2pa" not in wc
         and any("EXIF" in a or "XMP" in a for a in wacts), str(wacts))
    # 13б) I.31: --reencode — lossless-переупаковка IDAT.
    png_re = _mk_png_idat(b"rawrow1")
    re_out, reacts = _im.reencode_png(png_re)
    re_plain = _png_idat_plain(re_out)
    case("reencode: байты изменились, IDAT-поток тот же",
         re_out != png_re and re_plain == b"rawrow1"
         and "байты изменились" in reacts[-1], str(reacts))
    gif = tmp / "x.gif"
    gif.write_bytes(b"GIF89a" + b"\x00" * 16)
    case("BIN: GIF распознан как unsupported", classify(gif).startswith("unsupported"),
         classify(gif))
    tiff = tmp / "x.tiff"
    tiff.write_bytes(b"II*\x00" + b"\x00" * 16)
    case("BIN: TIFF распознан как unsupported", classify(tiff).startswith("unsupported"),
         classify(tiff))
    heic = tmp / "x.heic"
    heic.write_bytes(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16)
    case("BIN: HEIC распознан как unsupported", classify(heic).startswith("unsupported"),
         classify(heic))
    jxl = tmp / "x.jxl"
    jxl.write_bytes(b"\xff\x0a" + b"\x00" * 16)
    case("BIN: JXL распознан как unsupported", classify(jxl).startswith("unsupported"),
         classify(jxl))
    txt_ok = tmp / "ok.txt"
    txt_ok.write_text("обычный текст\n", encoding="utf-8")
    case("BIN: обычный текст не unsupported", classify(txt_ok) == "text", classify(txt_ok))

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    fails = [n for n, ok, _ in checks if not ok]
    for n, ok, detail in checks:
        print(("PASS: " if ok else "FAIL: ") + n + ((" | " + detail) if detail else ""))
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())