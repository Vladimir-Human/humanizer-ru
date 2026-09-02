#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Экспорт machine-readable реестра маркеров markers.v1.json.

Источники истины:
  1. `scripts/check_markers.py` — CASES: id, pattern, fixtures (positive,
     negative, multi).
  2. `references/chatbot-artifacts*.md` — описания маркеров и пометки
     «(класс B)»; маркер без пометки класса — класс A.
  3. `research/fixtures/marker-sources.json` — доказательная цепочка
     (source_url, accessed, platform, status, evidence_class).
  4. `README.md` — резервная таблица маркеров для описаний.

Экспорт детерминирован: порядок маркеров — порядок CASES (Python dict),
ключи записываются в фиксированном порядке, файл пишется с LF и одним
финальным переводом строки. Временных меток в документе нет, повторная
генерация даёт байт-в-байт одинаковый результат.

Переподпись класса (2.3): документ несёт `target_class`
(copypaste_artifacts — маркеры ловят следы чат-интерфейсов и копирования,
а не факт генерации), `live_policy` (ретайр только по провалу на своём
классе), `suite_checked` (дата последней зафиксированной прогонки фикстур)
и `live_status` у каждого маркера (live/retired; retired требует даты и
причины).

Запуск:
    python3 scripts/export_markers.py            # перезаписать markers.v1.json
    python3 scripts/export_markers.py --check    # только проверить, не писать
    python3 scripts/export_markers.py --selftest # самопроверка

Коды: 0 — успех; 1 — ошибка валидации/расхождение; 2 — ошибка входа.
Только стандартная библиотека.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCHEMA_VERSION = "markers.v1"
OUT_FILENAME = "markers.v1.json"
SOURCE_JSON_PATH = os.path.join("research", "fixtures", "marker-sources.json")
README_PATH = os.path.join("README.md")
REFERENCES_GLOB = "references/chatbot-artifacts*.md"
CHECK_MARKERS_PATH = os.path.join("scripts", "check_markers.py")
BS = chr(92)

DATE_RX = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
URL_RX = re.compile(r"^https?://[^ ]+$")

STATUSES = {"confirmed", "lead", "none", "fixture-only"}
EVIDENCE_CLASSES = {None, "primary", "secondary", "provenance", "synthetic"}

# Переподпись класса (2.3): маркеры ловят следы чат-интерфейсов и копипасты,
# а не сам факт генерации. Значения полей документа фиксированы здесь:
# экспорт детерминирован, правка поля — осознанное изменение с историей.
TARGET_CLASS = "copypaste_artifacts"
TARGET_CLASS_NOTE = ("Маркеры ловят следы чат-интерфейсов и копирования: "
                     "текст, который прошёл через чат-бот, был скопирован "
                     "или отредактирован машиной с настройками по умолчанию. "
                     "Они не определяют факт генерации: отсутствие маркеров "
                     "не доказывает авторство человека, а их наличие указывает "
                     "на путь текста, а не на автора.")
LIVE_POLICY = ("Ретайр только по провалу на своём классе: маркер уходит из "
               "активного слоя, если перестаёт ловить артефакт копипасты, на "
               "который нацелен, или начинает срабатывать на чистом "
               "человеческом тексте. Отсутствие срабатываний на выводах "
               "новых генераторов основанием для ретайра не является — это "
               "другой класс задач, не класс этого маркера.")
# Дата последней зафиксированной прогонки фикстурного набора (все маркеры:
# прямой/отрицательный/граничный образцы зелёные). Меняется только вместе с
# фактическим прогоном и его фиксацией в истории.
SUITE_CHECKED = "2026-09-01"
LIVE_STATUSES = {"live", "retired"}

def _load_check_markers(root):
    """Импорт CASES из scripts/check_markers.py по образцу check_fixture_sources.py.

    Безопасность: это штатный для репозитория способ получить единый источник
    регулярных выражений; файл исполняется в текущем процессе, что и делают
    существующие валидаторы (аналог `from check_markers import CASES`).
    """
    path = os.path.join(root, CHECK_MARKERS_PATH)
    if not os.path.isfile(path):
        raise FileNotFoundError("нет scripts/check_markers.py: %s" % path)
    spec = importlib.util.spec_from_file_location("_humanizer_check_markers_export", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _split_row(line):
    """Ячейки табличной строки; экранированный | не считается разделителем."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        ch = s[i]
        if ch == BS and i + 1 < len(s) and s[i + 1] == "|":
            cur.append(s[i:i + 2])
            i += 2
            continue
        if ch == "|":
            cells.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    return cells


def _table_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        print("Не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
        return rows
    for line in lines:
        if line.lstrip().startswith("|"):
            cells = _split_row(line)
            if len(cells) >= 2:
                rows.append(cells)
    return rows


def _reference_rows_by_sorted_files(root):
    files = tuple(sorted(glob.glob(os.path.join(root, REFERENCES_GLOB))))
    return [(md_path, _table_rows(md_path)) for md_path in files]


def _row_description(cells):
    for cell in cells[1:2]:
        cell = cell.strip()
        if cell and not cell.startswith("`") and len(cell) > 3:
            return cell
    return cells[0].strip() if cells else ""


def _detect_class_and_description(pattern, canon_func, ref_pairs):
    """Класс A/B по пометкам в reference-таблицах.

    Маркер без явной пометки класса — класс A (chatbot-artifacts.md, вводная).
    """
    cp = canon_func(pattern)
    rows_found = []
    for _md_path, rows in ref_pairs:
        for cells in rows:
            if cells and canon_func(" | ".join(cells)).find(cp) >= 0:
                rows_found.append(cells)
    if not rows_found:
        return "A", ""
    classes = set()
    description = ""
    for cells in rows_found:
        joined = " ".join(cells[:2])
        if "класс B" in joined:
            classes.add("B")
        elif "класс A" in joined:
            classes.add("A")
        if not description:
            row_desc = _row_description(cells)
            if row_desc:
                description = row_desc
    if len(classes) > 1:
        raise ValueError("Конфликт класса A/B для маркера %r" % rows_found[0][0])
    cls = classes.pop() if classes else "A"
    return cls, description


def _readme_rows(root):
    path = os.path.join(root, README_PATH)
    if os.path.isfile(path):
        return _table_rows(path)
    return []


def _description_for_case(pattern, canon_func, ref_desc, readme_rows):
    if ref_desc:
        return ref_desc
    cp = canon_func(pattern)
    for cells in readme_rows:
        if canon_func(" | ".join(cells)).find(cp) >= 0:
            return " | ".join(c for c in cells[:2] if c).strip()
    return ""


def _load_sources(root):
    path = os.path.join(root, SOURCE_JSON_PATH)
    if not os.path.isfile(path):
        raise FileNotFoundError("нет реестра источников: %s" % path)
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        raise ValueError("реестр источников должен быть JSON-списком")
    by_case = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("запись %d реестра источников: не объект" % i)
        case = entry.get("case")
        if not case or not isinstance(case, str):
            raise ValueError("запись %d реестра источников без case" % i)
        if case in by_case:
            raise ValueError("дубль case в реестре источников: %s" % case)
        by_case[case] = entry
    return by_case

def build_document(root=ROOT):
    """Строит документ markers.v1 из источников репозитория."""
    cm = _load_check_markers(root)
    cases = cm.CASES
    canon_func = cm._canon_pattern
    ref_pairs = _reference_rows_by_sorted_files(root)
    readme_rows = _readme_rows(root)
    sources = _load_sources(root)

    markers = []
    for name, case in cases.items():
        pattern, positives, negatives, multi = case
        cls, ref_desc = _detect_class_and_description(pattern, canon_func, ref_pairs)
        description = _description_for_case(pattern, canon_func, ref_desc, readme_rows)
        if not description:
            description = "Маркер %s" % name

        source_obj = None
        evidence_status = "fixture-only"
        evidence_class = None
        src = sources.get(name)
        if src is not None:
            evidence_status = str(src.get("status", "fixture-only")).strip() or "fixture-only"
            evidence_class = src.get("evidence_class") or None
            url = src.get("source_url") or ""
            accessed = src.get("accessed") or ""
            platform = src.get("platform") or ""
            if url or platform:
                source_obj = {
                    "url": url,
                    "accessed": accessed,
                    "platform": platform,
                }

        multi_obj = None
        if multi is not None:
            text, expected = multi
            multi_obj = {"text": text, "expected": int(expected)}

        marker = {
            "id": name,
            "class": cls,
            "live_status": "live",
            "pattern": pattern,
            "description": description,
            "source": source_obj,
            "fixtures": {
                "positive": list(positives),
                "negative": list(negatives),
                "multi": multi_obj,
            },
            "evidence_status": evidence_status,
            "evidence_class": evidence_class,
        }
        markers.append(marker)

    class_b_count = sum(1 for m in markers if m["class"] == "B")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": "humanizer-ru-markers",
        "target_class": TARGET_CLASS,
        "target_class_note": TARGET_CLASS_NOTE,
        "live_policy": LIVE_POLICY,
        "suite_checked": SUITE_CHECKED,
        "count": len(markers),
        "class_a_count": len(markers) - class_b_count,
        "class_b_count": class_b_count,
        "live_count": sum(1 for m in markers if m["live_status"] == "live"),
        "markers": markers,
    }


def validate_document(doc):
    """Ручная валидация схемы markers.v1 без внешних зависимостей."""
    errors = []
    if not isinstance(doc, dict):
        return ["документ должен быть объектом"]
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version должен быть %r" % SCHEMA_VERSION)
    if doc.get("id") != "humanizer-ru-markers":
        errors.append("id должен быть humanizer-ru-markers")
    if doc.get("target_class") != TARGET_CLASS:
        errors.append("target_class должен быть %r" % TARGET_CLASS)
    if not isinstance(doc.get("target_class_note"), str) \
            or not doc.get("target_class_note"):
        errors.append("target_class_note должен быть непустой строкой")
    if not isinstance(doc.get("live_policy"), str) or not doc.get("live_policy"):
        errors.append("live_policy должен быть непустой строкой")
    if not isinstance(doc.get("suite_checked"), str) \
            or not DATE_RX.match(doc.get("suite_checked", "")):
        errors.append("suite_checked должен быть датой YYYY-MM-DD")
    markers = doc.get("markers")
    if not isinstance(markers, list) or len(markers) != doc.get("count"):
        errors.append("markers должен быть списком длины count")

    seen = set()
    live_total = 0
    for i, marker in enumerate(markers or []):
        tag = "marker[%d]" % i
        if not isinstance(marker, dict):
            errors.append("%s: не объект" % tag)
            continue
        for field in ("id", "class", "live_status", "pattern", "description",
                      "source", "fixtures", "evidence_status", "evidence_class"):
            if field not in marker:
                errors.append("%s: нет поля %s" % (tag, field))
        mid = marker.get("id")
        if not isinstance(mid, str) or not mid:
            errors.append("%s: id должен быть непустой строкой" % tag)
        elif mid in seen:
            errors.append("%s: дубль id %s" % (tag, mid))
        seen.add(mid)
        if marker.get("class") not in ("A", "B"):
            errors.append("%s: class должен быть A или B" % tag)
        live_status = marker.get("live_status")
        if live_status not in LIVE_STATUSES:
            errors.append("%s: live_status должен быть одним из %s"
                          % (tag, sorted(LIVE_STATUSES)))
        elif live_status == "live":
            live_total += 1
        else:
            retired_date = marker.get("retired_date", "")
            if not isinstance(retired_date, str) or not DATE_RX.match(retired_date):
                errors.append("%s: retired требует retired_date YYYY-MM-DD" % tag)
            if not isinstance(marker.get("retired_reason"), str) \
                    or not marker.get("retired_reason"):
                errors.append("%s: retired требует retired_reason" % tag)
        if not isinstance(marker.get("pattern"), str) or not marker.get("pattern"):
            errors.append("%s: pattern должен быть непустой строкой" % tag)
        if not isinstance(marker.get("description"), str) or not marker.get("description"):
            errors.append("%s: description должен быть непустой строкой" % tag)
        source = marker.get("source")
        if source is not None and not isinstance(source, dict):
            errors.append("%s: source должен быть null или объектом" % tag)
        elif isinstance(source, dict):
            url = source.get("url", "")
            if not isinstance(url, str) or (url and not URL_RX.match(url)):
                errors.append("%s: source.url должен быть http(s) URL" % tag)
            accessed = source.get("accessed", "")
            if accessed and not DATE_RX.match(accessed):
                errors.append("%s: source.accessed должен быть YYYY-MM-DD" % tag)
        fixtures = marker.get("fixtures")
        if not isinstance(fixtures, dict):
            errors.append("%s: fixtures должен быть объектом" % tag)
        else:
            pos = fixtures.get("positive")
            neg = fixtures.get("negative")
            multi = fixtures.get("multi")
            if not isinstance(pos, list) or not all(isinstance(s, str) for s in pos):
                errors.append("%s: fixtures.positive должен быть списком строк" % tag)
            if not isinstance(neg, list) or not all(isinstance(s, str) for s in neg):
                errors.append("%s: fixtures.negative должен быть списком строк" % tag)
            if multi is not None:
                if not isinstance(multi, dict) or not isinstance(multi.get("text"), str) \
                        or not isinstance(multi.get("expected"), int):
                    errors.append("%s: fixtures.multi должен быть null или "
                                  "{text: str, expected: int}" % tag)
        status = marker.get("evidence_status")
        if status not in STATUSES:
            errors.append("%s: evidence_status должен быть одним из %s"
                          % (tag, sorted(STATUSES)))
        if marker.get("evidence_class") not in EVIDENCE_CLASSES:
            errors.append("%s: evidence_class должен быть одним из %s"
                          % (tag, sorted(EVIDENCE_CLASSES, key=str)))
        if status == "confirmed":
            if not isinstance(source, dict) or not source.get("url") or not source.get("accessed"):
                errors.append("%s: confirmed требует source.url и source.accessed" % tag)
    if isinstance(markers, list) and doc.get("live_count") != live_total:
        errors.append("live_count должен равняться числу маркеров со статусом live")
    return errors

def serialize_document(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def write_document(root, doc):
    out_path = os.path.join(root, OUT_FILENAME)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(serialize_document(doc))
    return out_path


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    _sample = ('| `turn0image0` | OpenAI | `turn' + BS + 'd+(?:image' + BS + '|news' + BS +
               '|video' + BS + '|ref)' + BS + 'd+` |')
    cells = _split_row(_sample)
    case("splitter не режет экранированный |", len(cells) == 3
         and cells[1] == "OpenAI" and ("|" in cells[2] or cells[2].count(BS) >= 1))

    d1 = serialize_document({"a": 1, "b": [{"x": 2}]})
    d2 = serialize_document({"a": 1, "b": [{"x": 2}]})
    case("сериализация детерминирована", d1 == d2)

    bad = {"schema_version": SCHEMA_VERSION, "id": "humanizer-ru-markers",
           "count": 1, "markers": [{"id": "", "class": "C", "pattern": "",
                                     "description": "", "source": None,
                                     "fixtures": {"positive": [], "negative": [],
                                                   "multi": None},
                                     "evidence_status": "confirmed",
                                     "evidence_class": None}]}
    errs = validate_document(bad)
    case("валидатор видит ошибки схемы", len(errs) >= 5)
    case("нет target_class — видно",
         any("target_class" in e for e in errs))
    case("нет live_status у маркера — видно",
         any("нет поля live_status" in e for e in errs))

    def _good_marker(**over):
        m = {"id": "m1", "class": "A", "live_status": "live", "pattern": "x",
             "description": "маркер", "source": None,
             "fixtures": {"positive": [], "negative": [], "multi": None},
             "evidence_status": "fixture-only", "evidence_class": None}
        m.update(over)
        return m

    def _good_doc(**over):
        d = {"schema_version": SCHEMA_VERSION, "id": "humanizer-ru-markers",
             "target_class": TARGET_CLASS, "target_class_note": "нота",
             "live_policy": "правило", "suite_checked": "2026-09-01",
             "count": 1, "class_a_count": 1, "class_b_count": 0,
             "live_count": 1, "markers": [_good_marker()]}
        d.update(over)
        return d

    case("валидный документ с переподписью класса проходит",
         validate_document(_good_doc()) == [])
    retired_errs = validate_document(_good_doc(live_count=0, markers=[_good_marker(
        live_status="retired")]))
    case("retired без даты и причины валится",
         any("retired_date" in e for e in retired_errs)
         and any("retired_reason" in e for e in retired_errs))
    case("retired с датой и причиной проходит",
         validate_document(_good_doc(live_count=0, markers=[_good_marker(
             live_status="retired", retired_date="2026-09-01",
             retired_reason="провал на своём классе")])) == [])
    case("неверный счётчик live виден",
         any("live_count" in e for e in validate_document(_good_doc(live_count=0))))

    print("Самопроверка: %d/%d" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Экспорт markers.v1.json из CASES и источников.")
    ap.add_argument("--check", action="store_true",
                    help="только проверить файл, не перезаписывая")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        doc = build_document(ROOT)
    except (OSError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print("Не удалось собрать документ: %s" % exc, file=sys.stderr)
        return 2
    errors = validate_document(doc)
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("Экспорт: схема не пройдена (%d ошибок)" % len(errors))
        return 1
    expected_bytes = serialize_document(doc).replace("\r\n", "\n").replace("\r", "\n")
    out_path = os.path.join(ROOT, OUT_FILENAME)
    if args.check:
        if os.path.isfile(out_path):
            with open(out_path, "rb") as fh:
                actual = fh.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if actual == expected_bytes.encode("utf-8"):
                print("OK markers.v1.json: экспорт актуален, маркеров %d" % doc["count"])
                return 0
            print("ПРОВАЛ markers.v1.json: файл не соответствует регенерации")
            return 1
        print("ПРОВАЛ markers.v1.json: файл отсутствует", file=sys.stderr)
        return 1
    write_document(ROOT, doc)
    print("Записан %s: маркеров %d (A=%d, B=%d)"
          % (out_path, doc["count"], doc["class_a_count"], doc["class_b_count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
