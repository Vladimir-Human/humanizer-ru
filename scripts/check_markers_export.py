#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт синхронности machine-readable реестра markers.v1.json.

Проверяет, что файл `markers.v1.json` в корне репозитория байтово
соответствует регенерации из `scripts/export_markers.py`. `export_markers.py`
строит документ из CASES и источников и сериализует его детерминированно;
этот гейт не даёт реестру устареть после правки regex, справочников или
research/fixtures/marker-sources.json.

Правила:
1. `scripts/export_markers.py` импортируется и способен построить документ.
2. Построенный документ проходит ручную валидацию схемы markers.v1.
3. Файл `markers.v1.json` существует и побайтово равен сериализации
   (с точностью до CRLF/LF в рабочем дереве Windows).

Запуск из корня репозитория:
    python3 scripts/check_markers_export.py            # проверка
    python3 scripts/check_markers_export.py --selftest # самопроверка

Коды: 0 — реестр синхронен; 1 — расхождение; 2 — ошибка запуска/импорта.
Только стандартная библиотека.
"""
import importlib.util
import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

EXPORT_MODULE = "scripts/export_markers.py"


def _load_export_module(root):
    path = os.path.join(root, EXPORT_MODULE)
    if not os.path.isfile(path):
        raise FileNotFoundError("нет %s" % path)
    spec = importlib.util.spec_from_file_location("_humanizer_export_markers_check", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _norm_bytes(data):
    """Байты с нормализованными переносами строк (CRLF/CR -> LF)."""
    return bytes(data).replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _file_matches(path, expected_norm_bytes):
    try:
        with open(path, "rb") as fh:
            actual = _norm_bytes(fh.read())
    except OSError as exc:
        return "не читается %s: %r" % (path, exc)
    if actual != expected_norm_bytes:
        return "файл не соответствует регенерации: %s" % os.path.relpath(path)
    return ""


def check(root):
    errors = []
    try:
        em = _load_export_module(root)
    except (OSError, FileNotFoundError, SyntaxError) as exc:
        return ["не удалось импортировать %s: %s" % (EXPORT_MODULE, exc)]
    try:
        doc = em.build_document(root)
    except Exception as exc:  # noqa: BLE001 — сюда попадают ValueError/JSONDecodeError и т.д.
        return ["не удалось построить документ: %s" % exc]
    errors.extend(em.validate_document(doc))
    if not errors:
        expected = em.serialize_document(doc)
        expected_norm = _norm_bytes(expected.encode("utf-8"))
        out_path = os.path.join(root, em.OUT_FILENAME)
        if not os.path.isfile(out_path):
            errors.append("нет файла %s" % os.path.relpath(out_path))
        else:
            err = _file_matches(out_path, expected_norm)
            if err:
                errors.append(err)
    return errors


def selftest():
    passed = 0
    failed = 0
    NL = chr(10)

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    # CRLF/LF не должны давать ложный провал.
    with tempfile.TemporaryDirectory(prefix="markers-export-selftest-") as td:
        f = os.path.join(td, "markers.v1.json")
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write("A" + NL)
        case("контроль LF/CRLF",
             _norm_bytes(b"A" + NL.encode()) == _norm_bytes(b"A" + chr(13).encode() + NL.encode())
             and not _file_matches(f, _norm_bytes(b"A" + NL.encode())))

        # Создаём минимальный export_markers.py для проверки гейта.
        os.makedirs(os.path.join(td, "scripts"))
        fake = os.path.join(td, "scripts", "export_markers.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("""
SCHEMA_VERSION = "markers.v1"
OUT_FILENAME = "markers.v1.json"

def build_document(root=None):
    return {"schema_version": SCHEMA_VERSION, "id": "humanizer-ru-markers",
            "count": 0, "markers": []}

def validate_document(doc):
    return []

def serialize_document(doc):
    return "OK"
""")
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write("OK")
        cases = [("синхронный реестр проходит", check(td) == [])]
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("BAD")
        cases.append(("дрейф файла виден", any("не соответствует" in e for e in check(td))))
        os.remove(f)
        cases.append(("отсутствующий файл виден", any("нет файла" in e for e in check(td))))
        for name, ok in cases:
            case(name, ok)

    print("Самопроверка: %d/%d" % (passed, passed + failed))
    return 0 if failed == 0 else 1

def main(argv):
    if "--selftest" in argv:
        return selftest()
    errors = check(ROOT)
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("Итог: расхождений реестра %d" % len(errors))
        return 1
    print("OK markers.v1.json: реестр синхронен с регенерацией")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
