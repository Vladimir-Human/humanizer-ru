#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F5a: round-trip DOCX на 20 фикстурах + гейт фактопотерь.

Каждая фикстура несёт известные факты (число, дата, имя, доля) в видимом
тексте document.xml и свой набор частей (комментарии, сноски, колонтитулы,
скрытый текст, полевые команды, гиперссылки, таблицы, customXml, медиа,
AI-метаданные). После clean_container проверяется:
  1. cleaned — валидный zip;
  2. document.xml парсится XML-парсером;
  3. все четыре факта присутствуют в видимом тексте cleaned-документа;
  4. текстовые части (footnotes/comments/headers/footers) не удалены;
  5. inspect на cleaned больше не находит AI-метаданных (контракт filemarks).
"""
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILEMARKS = os.path.join(ROOT, "scripts", "filemarks")
for p in (os.path.join(ROOT, "scripts"), FILEMARKS):
    if p not in sys.path:
        sys.path.insert(0, p)

import container_meta  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FACTS = ["12.5", "2026-01-15", "Иванов", "42"]


def _doc_xml(extra_runs=""):
    body = ("Согласно отчёту значение 12.5 от 2026-01-15, ответственный "
            "Иванов, доля 42 случая на 1000.")
    return ('<?xml version="1.0"?><w:document xmlns:w="%s"><w:body>'
            "<w:p><w:r><w:t>%s</w:t></w:r>%s</w:p>"
            "</w:body></w:document>" % (W, body, extra_runs))


def _make_docx(parts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        for name, data in parts.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _comment_part(text="Заметка на полях"):
    return ('<?xml version="1.0"?><w:comments xmlns:w="%s">'
            "<w:comment><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:comment>"
            "</w:comments>" % (W, text))


def _footnote_part():
    return ('<?xml version="1.0"?><w:footnotes xmlns:w="%s">'
            "<w:footnote><w:p><w:r><w:t>Сноска с пояснением</w:t></w:r></w:p>"
            "</w:footnote></w:footnotes>" % W)


def _header_part():
    return ('<?xml version="1.0"?><w:hdr xmlns:w="%s">'
            "<w:p><w:r><w:t>Колонтитул</w:t></w:r></w:p></w:hdr>" % W)


def _vanish_run():
    return ('<w:p><w:r><w:rPr><w:vanish/></w:rPr>'
            "<w:t>Скрытый текст черновика</w:t></w:r></w:p>")


def _instr_run():
    return ('<w:p><w:r><w:instrText> PAGE </w:instrText></w:r></w:p>')


def _table_part():
    return ('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Ячейка таблицы</w:t>'
            "</w:r></w:p></w:tc></w:tr></w:tbl>")


def _rels_hyperlink(target="https://example.com/r?utm_source=chatgpt.com"):
    return ('<?xml version="1.0"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            'Target="%s" TargetMode="External"/></Relationships>' % target)


def _core_xml(creator="Claude"):
    return ('<?xml version="1.0"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:creator>%s</dc:creator></cp:coreProperties>" % creator)


def _png():
    import struct
    import zlib
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


BASE = {
    "word/document.xml": _doc_xml(),
    "_rels/.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
}

FIXTURES = [
    ("plain", {}),
    ("comments", {"word/comments.xml": _comment_part()}),
    ("footnotes", {"word/footnotes.xml": _footnote_part()}),
    ("header", {"word/header1.xml": _header_part()}),
    ("footer", {"word/footer1.xml": _header_part()}),
    ("vanish", {"word/document.xml": _doc_xml(_vanish_run())}),
    ("instrText", {"word/document.xml": _doc_xml(_instr_run())}),
    ("hyperlink-rels", {"word/_rels/document.xml.rels": _rels_hyperlink()}),
    ("table", {"word/document.xml": _doc_xml(_table_part())}),
    ("customXml", {"customXml/item1.xml": "<root/>"}),
    ("ai-creator", {"docProps/core.xml": _core_xml("Claude")}),
    ("ai-app", {"docProps/app.xml": "<?xml version=\"1.0\"?><Properties><Application>ChatGPT</Application></Properties>"}),
    ("all-text-parts", {"word/comments.xml": _comment_part(),
                        "word/footnotes.xml": _footnote_part(),
                        "word/header1.xml": _header_part(),
                        "word/footer1.xml": _header_part()}),
    ("all-plus-ai", {"word/comments.xml": _comment_part(),
                     "word/footnotes.xml": _footnote_part(),
                     "docProps/core.xml": _core_xml("Copilot")}),
    ("media-png", {"word/media/image1.png": _png()}),
    ("two-headers", {"word/header1.xml": _header_part(),
                     "word/header2.xml": _header_part()}),
    ("endnotes", {"word/endnotes.xml": _footnote_part()}),
    ("customXml-x2", {"customXml/item1.xml": "<root/>",
                      "customXml/item2.xml": "<root/>"}),
    ("sandbox-rels", {"word/_rels/document.xml.rels":
                      _rels_hyperlink("sandbox:/mnt/data/report.xlsx")}),
    ("vanish-instr-comments", {"word/document.xml":
                               _doc_xml(_vanish_run() + _instr_run()),
                               "word/comments.xml": _comment_part()}),
]


class DocxFactlossTests(unittest.TestCase):
    def _run_fixture(self, name, extra):
        parts = dict(BASE)
        parts.update(extra)
        data = _make_docx(parts)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / ("%s.docx" % name)
            dst = Path(td) / ("%s.cleaned.docx" % name)
            src.write_bytes(data)
            container_meta.clean_container(src, dst)
            self.assertTrue(dst.is_file(), "cleaned не создан")
            with zipfile.ZipFile(dst) as zf:
                names = set(zf.namelist())
                doc = zf.read("word/document.xml").decode("utf-8")
                ET.fromstring(doc)  # валидный XML
                for fact in FACTS:
                    self.assertIn(fact, doc,
                                  "факт %s потерян в %s" % (fact, name))
                for text_part in ("word/comments.xml", "word/footnotes.xml",
                                  "word/header1.xml", "word/footer1.xml",
                                  "word/endnotes.xml"):
                    if text_part in parts:
                        self.assertIn(text_part, names,
                                      "текстовая часть %s удалена в %s"
                                      % (text_part, name))
            rep = container_meta.inspect_container(dst)
            self.assertFalse(rep["has_ai_metadata"],
                             "AI-метаданные остались в %s" % name)

    def test_fixtures(self):
        self.assertEqual(len(FIXTURES), 20, "ожидалось 20 фикстур")
        for name, extra in FIXTURES:
            with self.subTest(fixture=name):
                self._run_fixture(name, extra)


if __name__ == "__main__":
    unittest.main()
