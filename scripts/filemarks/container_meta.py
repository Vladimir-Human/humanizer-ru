# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
"""AI-метаданные в контейнерах: SVG, PDF, DOCX, ODT, HTML, Markdown.

Порт container_meta.py из watermarks-remover: те же форматы, те же приёмы
(frontmatter-ключи, meta/json-ld, XMP, customXml, docProps, meta:generator),
русский вывод. PDF — best-effort: предпочтителен exiftool.
"""
import io
import re
import subprocess
import zipfile
from pathlib import Path

from common_fm import preexec, safe_arg, safe_write_bytes, safe_write_text, which
from image_meta import AI_META_HINTS, C2PA_MARKERS, run_optional_tools

AI_FRONTMATTER_KEYS = frozenset({"generator", "ai", "ai_generated", "ai-generated",
                                 "claude", "anthropic", "openai", "gemini", "synthid",
                                 "c2pa", "content_credentials", "contentcredentials",
                                 "provenance", "digital_source_type", "digitalsourcetype",
                                 "created_with", "createdwith", "model", "llm",
                                 "генератор", "модель", "нейросеть", "ии",
                                 "сгенерировано", "автор_ии"})
AI_META_NAME_RE = re.compile(r"generator|ai[-_ ]?generated|claude|anthropic|openai|gemini|synthid|"
                             r"c2pa|content.?credential|provenance|digital.?source|aigc|"
                             r"генератор|модель|нейросеть|сгенерировано|искуственный интеллект", re.I)

_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
_JSONLD_RE = re.compile(
    r"""<script\b[^>]*type\s*=\s*["']application/ld\+json["'][^>]*>.*?</script>""",
    re.I | re.DOTALL)
MAX_ZIP_DECOMPRESSED_BYTES = 128 * 1024 * 1024
DOCX_META_PARTS = ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml")


def detect_container_format(path, data=None):
    ext = Path(path).suffix.lower()
    if ext == ".svg":
        return "svg"
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext == ".odt":
        return "odt"
    if ext in (".html", ".htm"):
        return "html"
    if ext in (".md", ".markdown", ".mdx"):
        return "markdown"
    if data is not None:
        if data[:4] == b"%PDF":
            return "pdf"
        if data[:100].lstrip().startswith(b"<") and b"svg" in data[:500].lower():
            return "svg"
        if data[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    names = set(zf.namelist())
                    if "word/document.xml" in names:
                        return "docx"
                    if "content.xml" in names and "meta.xml" in names:
                        return "odt"
            except zipfile.BadZipFile:
                pass
    return "unknown"


def _blob_hits(blob):
    low = blob.lower()
    findings, has_c2pa, has_ai = [], False, False
    seen_c2pa = set()
    for n in C2PA_MARKERS:
        key = n.decode("ascii", errors="replace").lower()
        if key in seen_c2pa:
            continue
        if n.lower() in low:
            seen_c2pa.add(key)
            has_c2pa = True
            findings.append("marker:%s" % key)
    for n in AI_META_HINTS:
        if n.lower() in low:
            has_ai = True
            label = n.decode("ascii", errors="replace")
            if label not in {f.split(":", 1)[-1] for f in findings}:
                findings.append("ai:%s" % label)
    return has_c2pa, has_ai or has_c2pa, findings[:30]


def _top_yaml_keys(block):
    rows = []
    for i, line in enumerate(block.splitlines()):
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line[0] in (" ", "\t", "-"):
            continue
        m = re.match(r"^([\w.\-]+)\s*:", line)
        if m:
            rows.append((m.group(1), line, i))
    return rows


def inspect_markdown(text):
    findings, has_ai = [], False
    m = _FM_RE.match(text)
    if not m:
        return False, False, [], {"has_frontmatter": False}
    block = m.group(1)
    keys = []
    for key, line, _i in _top_yaml_keys(block):
        keys.append(key)
        if key.lower() in AI_FRONTMATTER_KEYS or AI_META_NAME_RE.search(key):
            has_ai = True
            findings.append("frontmatter-ключ: %s" % key)
        val = line.split(":", 1)[1] if ":" in line else ""
        if AI_META_NAME_RE.search(val):
            has_ai = True
            findings.append("frontmatter-значение у %s" % key)
    c2pa = any(("c2pa" in f.lower()) or ("contentcredential" in f.lower()) or ("content_credential" in f.lower()) for f in findings)
    return c2pa, has_ai, findings, {"has_frontmatter": True, "keys": keys}


def clean_markdown(text):
    actions = []
    m = _FM_RE.match(text)
    if not m:
        return text, ["YAML-frontmatter отсутствует"]
    block = m.group(1)
    body = text[m.end():]
    kept = []
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#") or line[0] in (" ", "\t", "-"):
            kept.append(line)
            continue
        km = re.match(r"^([\w.\-]+)\s*:", line)
        if km:
            key = km.group(1)
            if key.lower() in AI_FRONTMATTER_KEYS or AI_META_NAME_RE.search(key):
                actions.append("снят frontmatter-ключ: %s" % key)
                continue
            val = line.split(":", 1)[1] if ":" in line else ""
            if AI_META_NAME_RE.search(val):
                actions.append("снят frontmatter-ключ (значение): %s" % key)
                continue
        kept.append(line)
    if not actions:
        actions.append("AI-ключей во frontmatter не найдено")
    new_block = "\n".join(kept).strip("\n")
    if new_block:
        out = "---\n%s\n---\n%s" % (new_block, body)
    else:
        out = body.lstrip("\n")
        actions.append("пустой frontmatter снят целиком")
    return out, actions


def _meta_has_ai(tag):
    return (AI_META_NAME_RE.search(tag)
            or any(h.decode("ascii", "ignore").lower() in tag.lower()
                   for h in AI_META_HINTS[:12]))


def inspect_html(text):
    findings, has_ai, has_c2pa = [], False, False
    for tag in _META_TAG_RE.findall(text):
        if _meta_has_ai(tag):
            has_ai = True
            findings.append("meta: %s" % tag[:120])
            if re.search(r"c2pa|content.?credential", tag, re.I):
                has_c2pa = True
    for m in _JSONLD_RE.finditer(text):
        blob = m.group(0)
        if AI_META_NAME_RE.search(blob) or re.search(r"DigitalSourceType|trainedAlgorithmicMedia|SoftwareAgent", blob, re.I):
            has_ai = True
            findings.append("json-ld provenance-блок")
            if re.search(r"c2pa|contentcredential", blob, re.I):
                has_c2pa = True
    for m in re.finditer(r"""(?:^|\s)data-ai[\w-]*\s*=\s*["'][^"']*["']""", text, re.I):
        has_ai = True
        findings.append("attr: %s" % m.group(0)[:80])
    return has_c2pa, has_ai, findings, {}


def clean_html(text):
    actions = []

    def _meta_sub(m):
        tag = m.group(0)
        if _meta_has_ai(tag):
            actions.append("снят meta: %s" % tag[:80])
            return ""
        return tag

    out = _META_TAG_RE.sub(_meta_sub, text)

    def _jsonld_sub(m):
        blob = m.group(0)
        if AI_META_NAME_RE.search(blob) or re.search(r"DigitalSourceType|trainedAlgorithmicMedia|SoftwareAgent", blob, re.I):
            actions.append("снят json-ld provenance-скрипт")
            return ""
        return blob

    out = _JSONLD_RE.sub(_jsonld_sub, out)
    out2, n = re.subn(r"""(?:^|\s)data-ai[\w-]*\s*=\s*["'][^"']*["']""", " ", out, flags=re.I)
    if n:
        actions.append("сняты data-ai* атрибуты x%d" % n)
        out = out2
    if not actions:
        actions.append("AI-meta в HTML нет")
    return out, actions


def inspect_svg(data):
    findings = []
    has_c2pa, has_ai, hits = _blob_hits(data)
    findings.extend(hits)
    try:
        text = data.decode("utf-8", errors="surrogateescape")
        if re.search(r"<metadata[\s>]", text, re.I):
            findings.append("svg <metadata> присутствует")
            has_ai = True
        if re.search(r"xmpmeta|rdf:RDF|contentcredentials", text, re.I):
            has_ai = True
            findings.append("XMP/RDF-содержимое в SVG")
        if re.search(r"c2pa|jumbf", text, re.I):
            has_c2pa = True
    except Exception as exc:
        findings.append("svg: %s" % exc)
    return has_c2pa, has_ai or has_c2pa, findings, {}


def clean_svg(data):
    actions = []
    text = data.decode("utf-8", errors="surrogateescape")
    new, n = re.subn(r"<metadata\b[^>]*>.*?</metadata\s*>", "", text, flags=re.I | re.DOTALL)
    if n:
        actions.append("снят <metadata> x%d" % n)
        text = new
    new, n = re.subn(r"<x:xmpmeta\b[^>]*>.*?</x:xmpmeta\s*>", "", text, flags=re.I | re.DOTALL)
    if n:
        actions.append("снят xmpmeta x%d" % n)
        text = new

    def _cmt(m):
        body = m.group(0)
        if AI_META_NAME_RE.search(body):
            actions.append("снят SVG-комментарий с AI-маркерами")
            return ""
        return body

    text = re.sub(r"<!--.*?-->", _cmt, text, flags=re.DOTALL)
    new, n = re.subn(r"""\s(inkscape:version|sodipodi:docname|generator)\s*=\s*(?:"[^"]*"|'[^']*')""", "", text, flags=re.I)
    if n:
        actions.append("сняты generator-атрибуты x%d" % n)
        text = new
    if not actions:
        actions.append("SVG-метаданных нет")
    return text.encode("utf-8", errors="surrogateescape"), actions


def _check_zip_budget(info, budget):
    budget[0] += info.file_size
    if budget[0] > MAX_ZIP_DECOMPRESSED_BYTES:
        raise ValueError("распакованный размер zip превышает лимит (%d байт)" % MAX_ZIP_DECOMPRESSED_BYTES)


def _safe_read(zf, name, budget):
    """Чтение части zip с контролем фактического размера: заголовку zip
    верить нельзя (file_size из central directory подделывается)."""
    raw = zf.read(name)
    delta = len(raw) - zf.getinfo(name).file_size
    budget[0] += delta
    if budget[0] > MAX_ZIP_DECOMPRESSED_BYTES:
        raise ValueError("фактический распакованный размер превышает лимит")
    return raw


def inspect_docx(data):
    findings, has_c2pa, has_ai = [], False, False
    parts = []
    budget = [0]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            parts = zf.namelist()
            for info in zf.infolist():
                if not (info.filename.startswith(("docProps/", "customXml/"))):
                    continue
                _check_zip_budget(info, budget)
                raw = _safe_read(zf, info.filename, budget)
                c2, ai, hits = _blob_hits(raw)
                if info.filename.startswith("docProps/"):
                    txt = raw.decode("utf-8", errors="replace")
                    if AI_META_NAME_RE.search(txt) or re.search(
                            r"claude|openai|anthropic|gemini|chatgpt|synthid|copilot", txt, re.I):
                        ai = True
                        hits = hits + ["ai:docProps-field"]
                if c2 or ai:
                    has_c2pa = has_c2pa or c2
                    has_ai = has_ai or ai
                    findings.append("%s: %s" % (info.filename, ", ".join(hits[:6])))
            custom = [n for n in parts if n.startswith("customXml/")]
            if custom:
                findings.append("customXml-частей: %d" % len(custom))
    except (zipfile.BadZipFile, ValueError) as exc:
        return False, False, ["ошибка zip: %s" % exc], {}
    return has_c2pa, has_ai or has_c2pa, findings, {"parts": len(parts)}


def clean_docx(data):
    actions = []
    out_buf = io.BytesIO()
    budget = [0]
    try:
        return _clean_docx_zip(data, out_buf, budget, actions)
    except (zipfile.BadZipFile, ValueError) as exc:
        raise ValueError("ошибка обработки DOCX: %s" % exc)


def _clean_docx_zip(data, out_buf, budget, actions):
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            name = info.filename
            _check_zip_budget(info, budget)
            raw = _safe_read(zin, name, budget)
            if name.startswith("customXml/"):
                actions.append("снята часть %s" % name)
                continue
            if name in DOCX_META_PARTS or name.startswith("docProps/"):
                text = raw.decode("utf-8", errors="replace")
                new = text
                for pat, label in ((r"(<dc:creator[^>]*>)(.*?)(</dc:creator>)", "dc:creator"),
                                   (r"(<cp:lastModifiedBy[^>]*>)(.*?)(</cp:lastModifiedBy>)", "cp:lastModifiedBy"),
                                   (r"(<Application[^>]*>)(.*?)(</Application>)", "Application"),
                                   (r"(<AppVersion[^>]*>)(.*?)(</AppVersion>)", "AppVersion")):

                    def _sub(m, _label=label):
                        inner = m.group(2)
                        if AI_META_NAME_RE.search(inner) or AI_META_NAME_RE.search(_label):
                            actions.append("вычищено %s: %s" % (name, _label))
                            return m.group(1) + m.group(3)
                        if _label in ("Application", "AppVersion") and re.search(
                                r"claude|openai|anthropic|gemini|chatgpt|synthid|copilot", inner, re.I):
                            actions.append("вычищено %s: %s" % (name, _label))
                            return m.group(1) + m.group(3)
                        return m.group(0)

                    new = re.sub(pat, _sub, new, flags=re.I | re.DOTALL)
                if name.endswith("custom.xml") and (_blob_hits(raw)[1] or AI_META_NAME_RE.search(text)):
                    actions.append("снята часть %s" % name)
                    continue
                raw = new.encode("utf-8")
            if name == "[Content_Types].xml":
                text = raw.decode("utf-8", errors="replace")
                new, n = re.subn(r"""<Override\b[^>]*PartName="/customXml/[^"]*"[^>]*/>""", "", text)
                if n:
                    actions.append("сняты Content_Types customXml-override x%d" % n)
                    raw = new.encode("utf-8")
            zout.writestr(info, raw)
    if not actions:
        actions.append("DOCX-метаданных нет")
    return out_buf.getvalue(), actions


def inspect_odt(data):
    findings, has_c2pa, has_ai = [], False, False
    budget = [0]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.filename not in ("meta.xml", "META-INF/manifest.xml"):
                    continue
                _check_zip_budget(info, budget)
                raw = _safe_read(zf, info.filename, budget)
                c2, ai, hits = _blob_hits(raw)
                if c2 or ai:
                    has_c2pa = has_c2pa or c2
                    has_ai = has_ai or ai
                    findings.append("%s: %s" % (info.filename, ", ".join(hits[:6])))
            if "meta.xml" in zf.namelist():
                meta = _safe_read(zf, "meta.xml", budget).decode("utf-8", errors="replace")
                if re.search(r"generator|claude|openai|anthropic|gemini", meta, re.I):
                    has_ai = True
                    findings.append("meta.xml: generator-подобные поля")
    except (zipfile.BadZipFile, ValueError) as exc:
        return False, False, ["ошибка zip: %s" % exc], {}
    return has_c2pa, has_ai or has_c2pa, findings, {}


def clean_odt(data):
    actions = []
    out_buf = io.BytesIO()
    budget = [0]
    try:
        return _clean_odt_zip(data, out_buf, budget, actions)
    except (zipfile.BadZipFile, ValueError) as exc:
        raise ValueError("ошибка обработки ODT: %s" % exc)


def _clean_odt_zip(data, out_buf, budget, actions):
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            name = info.filename
            _check_zip_budget(info, budget)
            raw = _safe_read(zin, name, budget)
            if name == "META-INF/manifest.xml":
                text = raw.decode("utf-8", errors="replace")
                new, n = re.subn(
                    r"""<manifest:file-entry[^>]*full-path="[^"]*(?:c2pa|contentcredential)[^"]*"[^>]*/>""",
                    "", text, flags=re.I)
                if n:
                    actions.append("сняты C2PA-записи manifest.xml x%d" % n)
                    raw = new.encode("utf-8")
            elif name == "meta.xml":
                text = raw.decode("utf-8", errors="replace")
                new, n = re.subn(r"<meta:generator\b[^>]*>.*?</meta:generator\s*>", "", text, flags=re.I | re.DOTALL)
                if n:
                    actions.append("снят meta:generator")
                    text = new

                def _creator(m):
                    if AI_META_NAME_RE.search(m.group(0)):
                        actions.append("вычищен creator-подобный meta")
                        return ""
                    return m.group(0)

                text = re.sub(r"<dc:creator\b[^>]*>.*?</dc:creator\s*>", _creator, text, flags=re.I | re.DOTALL)
                raw = text.encode("utf-8")
            else:
                c2, ai, _ = _blob_hits(raw)
                if (c2 or ai) and name not in ("content.xml", "styles.xml", "mimetype", "META-INF/manifest.xml"):
                    actions.append("снята часть %s (AI/C2PA-маркеры)" % name)
                    continue
            zout.writestr(info, raw)
    if not actions:
        actions.append("ODT-метаданных нет")
    return out_buf.getvalue(), actions


def inspect_pdf(path, data):
    findings = []
    has_c2pa, has_ai, hits = _blob_hits(data)
    findings.extend("pdf-bytes:%s" % h for h in hits)
    if b"<x:xmpmeta" in data or b"application/rdf+xml" in data:
        findings.append("XMP-пакет присутствует")
        has_ai = has_ai or bool(re.search(rb"digitalSourceType|trainedAlgorithmicMedia|SoftwareAgent|c2pa", data, re.I))
    tools = run_optional_tools(Path(path))
    ct = tools.get("c2patool") or {}
    if ct.get("has_manifest"):
        has_c2pa = True
        findings.append("c2patool сообщает C2PA-манифест")
    return has_c2pa, has_ai or has_c2pa, findings, {"tools": tools}


def clean_pdf(path, dest):
    actions = []
    data = Path(path).read_bytes()
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    exiftool = which("exiftool")
    if exiftool:
        safe_write_bytes(dest, data)
        try:
            r = subprocess.run([exiftool, "-all=", "-overwrite_original", safe_arg(str(dest))],
                               capture_output=True, text=True, timeout=60, check=False,
                               preexec_fn=preexec())
            actions.append("exiftool -all= (rc=%d)" % r.returncode)
        except Exception as exc:
            actions.append("exiftool не сработал: %s" % exc)
        return actions, {"mode": "exiftool"}
    new, n = re.subn(rb"""<\?xpacket begin.*?<\?xpacket end[^?]*\?>""", b"", data, flags=re.I | re.DOTALL)
    if n:
        actions.append("сняты XMP-xpacket x%d (урезанный режим; возможны битые смещения)" % n)
        safe_write_bytes(dest, new)
        actions.append("предупреждение: чистый stdlib-режим PDF снимает не все метки; поставьте exiftool")
        return actions, {"mode": "stdlib-xmp", "degraded": True}
    safe_write_bytes(dest, data)
    actions.append("очиститель PDF не найден (поставьте exiftool); скопировано как есть")
    return actions, {"mode": "copy", "degraded": True}


def inspect_container(path):
    data = Path(path).read_bytes()
    fmt = detect_container_format(path, data)
    tools, details = {}, {}
    if fmt == "svg":
        has_c2pa, has_ai, findings, details = inspect_svg(data)
    elif fmt == "pdf":
        has_c2pa, has_ai, findings, details = inspect_pdf(path, data)
        tools = details.pop("tools", {})
    elif fmt == "docx":
        has_c2pa, has_ai, findings, details = inspect_docx(data)
    elif fmt == "odt":
        has_c2pa, has_ai, findings, details = inspect_odt(data)
    elif fmt == "html":
        has_c2pa, has_ai, findings, details = inspect_html(data.decode("utf-8", errors="replace"))
    elif fmt == "markdown":
        has_c2pa, has_ai, findings, details = inspect_markdown(data.decode("utf-8", errors="replace"))
    else:
        has_c2pa, has_ai, findings = False, False, ["неподдерживаемый контейнер: %s" % fmt]
    if fmt in ("svg", "pdf", "docx") and not tools:
        tools = run_optional_tools(Path(path))
    return {"path": str(path), "format": fmt, "has_c2pa": has_c2pa,
            "has_ai_metadata": has_ai, "findings": findings, "tools": tools, "details": details}


def clean_container(path, dest, also_layer_a_text=True):
    data = Path(path).read_bytes()
    fmt = detect_container_format(path, data)
    actions = []
    meta = {"format": fmt}
    if fmt == "svg":
        cleaned, actions = clean_svg(data)
        safe_write_bytes(dest, cleaned)
    elif fmt == "pdf":
        actions, meta_extra = clean_pdf(path, dest)
        meta.update(meta_extra)
    elif fmt == "docx":
        cleaned, actions = clean_docx(data)
        safe_write_bytes(dest, cleaned)
    elif fmt == "odt":
        cleaned, actions = clean_odt(data)
        safe_write_bytes(dest, cleaned)
    elif fmt in ("html", "markdown"):
        text = data.decode("utf-8", errors="surrogateescape")
        if fmt == "html":
            text, actions = clean_html(text)
        else:
            text, actions = clean_markdown(text)
        if also_layer_a_text:
            from text_layer import clean_text_layer
            text, n = clean_text_layer(text)
            if n:
                actions.append("снято невидимых (слой A): %d" % n)
        safe_write_text(dest, text)
    else:
        raise ValueError("неподдерживаемый формат контейнера: %s" % fmt)
    after = inspect_container(dest)
    return {"input": str(path), "output": str(dest), "format": fmt, "actions": actions,
            "bytes_in": len(data), "bytes_out": Path(dest).stat().st_size,
            "still_has_c2pa": after["has_c2pa"], "still_has_ai_metadata": after["has_ai_metadata"],
            "post_findings": after["findings"], "meta": meta}
