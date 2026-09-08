#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_compatibility.py — compatibility-тест против предыдущей опубликованной версии.

Правило плана v2: каждый релиз сверяется с предыдущей ОПУБЛИКОВАННОЙ
версией. Аддитивные поля разрешены; изменение кодов возврата, формы
конверта и результатов детекции на одинаковых входах — несовместимость.

Механика:
  1. Предыдущая версия определяется с PyPI: максимальная строго меньше
     версии дерева (src/humanizer_ru/__init__.py).
  2. Она ставится во временное чистое venv (pip; сеть).
  3. Фиксированная матрица входов (русский текст с артефактами, чистый
     русский, английский, пустой, Markdown, не-UTF-8, нечитаемый файл)
     прогоняется через ВСЕ общие операции в двух окружениях: OLD
     (установленный пакет) и NEW (пакет дерева, PYTHONPATH=src):
     scan, markers, polish, detect, clean (если есть в OLD/NEW —
     отсутствие в OLD фиксируется как аддитивность), пары facts и report,
     MCP-сессия (состав инструментов и схемы параметров, поведение
     вызова, ошибка и восстановление; тексты описаний не сравниваются —
     они генерируются из контракта и сверяются с ним каждой версией
     отдельно через check_mcp).
  4. Сравнение: rc равен; поля, присутствующие в OLD-ответе, равны в NEW;
     NEW может добавлять поля (аддитивность), но не менять и не удалять.
     Исключение — CONTRACT_RESTORED: точечные восстановления уже
     обещанного контрактом поведения (OLD нарушал опубликованный
     контракт той же версии); вейвер применяется только когда OLD и NEW
     соответствуют заявленным предикатам, иначе это несовместимость.

Запуск:
    python3 scripts/check_compatibility.py             # проверка
    python3 scripts/check_compatibility.py --selftest  # негативные кейсы

Коды: 0 — совместимо; 1 — несовместимость; 2 — отказ среды (нет сети,
venv или PyPI). Только стандартная библиотека (pip — из venv).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYPI_JSON = "https://pypi.org/pypi/humanizer-ru/json"
# Явный список нормализуемых нестабильных полей: тексты причин ошибок
# зависят от путей окружения (сравниваются наличие и тип, не текст).
# Пути файлов нормализует проба (к именам файлов). Иного нормализующего
# списка нет: значения и типы всех остальных полей сравниваются как есть.
NORM_TEXT_KEYS = ("error", "env_error")

PROBE = '''# -*- coding: utf-8 -*-
import contextlib, io, json, os, tempfile
from humanizer_ru.cli import scan_main, markers_main, polish_main, detect_main


def opt(mod, name):
    """Необязательный вход: отсутствует в старых опубликованных версиях."""
    try:
        m = __import__("humanizer_ru." + mod, fromlist=[name])
        return getattr(m, name, None)
    except Exception:
        return None


clean_main = opt("cli", "clean_main")
facts_main = opt("facts_diff", "main")
report_main = opt("edit_report", "main")

T = tempfile.mkdtemp(prefix="compat-probe-")

# Явный список нормализуемых нестабильных значений: тексты причин ошибок
# зависят от путей окружения, пути файлов — от временного каталога пробы
# (ключ file, before/after и строковые элементы files у humanizer-facts).
# Ничего остального проба не нормализует: сравниваются все файлы и все
# вложенные поля конвертов, рекурсивно, с различением типов JSON.
NORM_TEXT_KEYS = ("error", "env_error")
NORM_PATH_KEYS = ("file", "before", "after", "files")

def norm(value, key=None):
    if isinstance(value, dict):
        return {k: norm(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [norm(v, key) for v in value]
    if isinstance(value, str):
        if key in NORM_TEXT_KEYS:
            return "<текст причины нормализован>"
        if key in NORM_PATH_KEYS:
            return os.path.basename(value)
        return value
    return value


SCHEMA_KEYS = {
    "type", "enum", "const", "required", "additionalProperties",
    "minItems", "maxItems", "minLength", "maxLength", "pattern",
    "items", "properties", "anyOf", "oneOf",
}

def schema_shape(value, key=None):
    """Сохранить структурные ограничения inputSchema, отбросив описания."""
    if isinstance(value, dict):
        return {k: schema_shape(v, k) for k, v in value.items()
                if k in SCHEMA_KEYS}
    if isinstance(value, list):
        out = [schema_shape(v, key) for v in value]
        if key in ("required", "enum"):
            return sorted(out, key=repr)
        return out
    return value


def w(name, text):
    p = os.path.join(T, name)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return p

def wb(name, data):
    p = os.path.join(T, name)
    with open(p, "wb") as fh:
        fh.write(data)
    return p

ru = w("ru.txt", "\\u0421\\u043e\\u0433\\u043b\\u0430\\u0441\\u043d\\u043e \\u043e\\u0442\\u0447\\u0451\\u0442\\u0443 :contentReference[oaicite:12]{index=12}, \\u0437\\u0430\\u044f\\u0432\\u043e\\u043a \\u0441\\u0442\\u0430\\u043b\\u043e \\u0431\\u043e\\u043b\\u044c\\u0448\\u0435 \\u043d\\u0430 12% \\u2014 \\u0438\\u0441\\u0442\\u043e\\u0447\\u043d\\u0438\\u043a: https://example.com/r?utm_source=chatgpt.com\\n\\u0414\\u0430\\u043d\\u043d\\u044b\\u0435 \\u043f\\u043e\\u0434\\u0442\\u0432\\u0435\\u0440\\u0436\\u0434\\u0435\\u043d\\u044b \\u0430\\u0441\\u0441\\u0438\\u0441\\u0442\\u0435\\u043d\\u0442\\u043e\\u043c\\u200b.\\n")
clean = w("clean.txt", "\\u041e\\u0431\\u044b\\u0447\\u043d\\u044b\\u0439 \\u0440\\u0443\\u0441\\u0441\\u043a\\u0438\\u0439 \\u0442\\u0435\\u043a\\u0441\\u0442 \\u0431\\u0435\\u0437 \\u0434\\u0435\\u0444\\u0435\\u043a\\u0442\\u043e\\u0432. \\u0412\\u0442\\u043e\\u0440\\u043e\\u0439 \\u0430\\u0431\\u0437\\u0430\\u0446.\\n")
en = w("en.txt", "Plain English text without any Russian words.\\n")
empty = w("empty.txt", "")
md = w("md.txt", "# \\u0417\\u0430\\u0433\\u043e\\u043b\\u043e\\u0432\\u043e\\u043a\\n\\n**\\u0416\\u0438\\u0440\\u043d\\u044b\\u0439** \\u0438 \\u00ab\\u0451\\u043b\\u043e\\u0447\\u043a\\u0438\\u00bb \\u2014 \\u0442\\u0438\\u0440\\u0435\\u2026\\n")
good = w("good.txt", "\\u0412\\u0441\\u0442\\u0440\\u0435\\u0447\\u0430 \\u0441\\u043e\\u0441\\u0442\\u043e\\u044f\\u043b\\u0430\\u0441\\u044c. \\u0426\\u0435\\u043d\\u0430 100 \\u0440\\u0443\\u0431\\u043b\\u0435\\u0439.\\n")
bad = wb("bad.txt", bytes([0xFF, 0xFE]) + "\\u0426\\u0435\\u043d\\u0430 100 \\u0440\\u0443\\u0431\\u043b\\u0435\\u0439.\\n".encode("utf-8"))
missing = os.path.join(T, "no-such-file.txt")

out = []

def run(label, fn, argv):
    if fn is None:
        out.append({"label": label, "absent": True})
        return
    buf = io.StringIO()
    ebuf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
        try:
            rc = fn(argv)
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:
            # Поведение старой поставки на плохом входе фиксируется как
            # есть (traceback-класс), а не роняет пробу: восстановление
            # контракта сверяется отдельно (CONTRACT_RESTORED).
            rc = "EXC:" + type(exc).__name__
    rec = {"label": label, "rc": rc}
    try:
        payload = json.loads(buf.getvalue())
    except Exception:
        payload = None
    rec["payload"] = norm(payload)
    out.append(rec)

for p in (ru, clean, en, empty, md, bad, missing):
    name = os.path.basename(p)
    run("markers:" + name, markers_main, ["--scan", "--json", p])
    run("scan:" + name, scan_main, ["--json", p])
    run("polish:" + name, polish_main, ["--json", p])
    run("detect:" + name, detect_main, ["--json", p])
    run("clean:" + name, clean_main, ["--json", "--", p])

# Пары facts/report: идентичная, правка со снятием, порченый UTF-8,
# отсутствующий файл, пустая пара, английская пара, порча «после».
PAIRS = [(ru, ru), (ru, clean), (bad, good), (missing, good),
         (empty, empty), (en, en), (good, bad)]
for a, b in PAIRS:
    label = "%s+%s" % (os.path.basename(a), os.path.basename(b))
    run("facts:" + label, facts_main, ["diff", a, b, "--json"])
    run("report:" + label, report_main, [a, b, "--json"])

# MCP: сессия in-process (discovery + вызовы + ошибка + восстановление).
# Сравниваются состав инструментов, схемы параметров и поведение вызова;
# тексты описаний не сравниваются: они генерируются из контракта и
# сверяются с контрактом каждой версии отдельно (check_mcp).
try:
    from humanizer_ru import mcp_server as ms
    defs = ms.generate_tool_defs(ms.load_contract())
    # Словарь по имени инструмента: аддитивный инструмент — новое поле
    # словаря (допустимо), аддитивный параметр — новый элемент списка
    # props (каждый OLD-элемент обязан иметь типизированную пару в NEW).
    tools_rec = {d["name"]: {
        # Старые поля сохраняются для читаемого отчёта; полная структурная
        # форма нужна, чтобы ловить смену type/enum/required, а не только
        # переименование свойства.
        "props": sorted(d["inputSchema"]["properties"]),
        "required": sorted(d["inputSchema"]["required"]),
        "input_schema": schema_shape(d["inputSchema"])}
        for d in defs}
    out.append({"label": "mcp:tools", "rc": 0, "payload": tools_rec})
    state = {}
    r = ms.handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"}}), state, defs)
    out.append({"label": "mcp:initialize", "rc": 0,
                "payload": {"protocolVersion":
                            r["result"]["protocolVersion"]}})
    with open(ru, encoding="utf-8") as fh:
        ru_text = fh.read()
    r = ms.handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "humanizer_markers",
                   "arguments": {"text": ru_text}},
    }, ensure_ascii=False), state, defs)
    res = r.get("result", {})
    sc = res.get("structuredContent") or {}
    out.append({"label": "mcp:call-markers", "rc": 0,
                "payload": {"isError": bool(res.get("isError")),
                            "tool": sc.get("tool"),
                            "count": (sc.get("files") or [{}])[0].get("count")}})
    r = ms.handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "humanizer_markers",
                   "arguments": {"text": ru_text, "\\u043b\\u0438\\u0448\\u043d\\u0438\\u0439": 1}},
    }, ensure_ascii=False), state, defs)
    out.append({"label": "mcp:error-extra-param", "rc": 0,
                "payload": {"code": (r.get("error") or {}).get("code")}})
    r = ms.handle_message(json.dumps({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "humanizer_scan",
                   "arguments": {"text": ru_text}},
    }, ensure_ascii=False), state, defs)
    res = r.get("result", {})
    sc = res.get("structuredContent") or {}
    out.append({"label": "mcp:call-scan-after-error", "rc": 0,
                "payload": {"isError": bool(res.get("isError")),
                            "tool": sc.get("tool"),
                            "nfiles": len(sc.get("files") or [])}})
except Exception as exc:
    out.append({"label": "mcp:session", "rc": "EXC:" + type(exc).__name__,
                "payload": None})

print(json.dumps(out, ensure_ascii=False, sort_keys=True))
'''


def tree_version() -> str:
    with open(os.path.join(ROOT, "src", "humanizer_ru", "__init__.py"),
              encoding="utf-8") as fh:
        m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', fh.read())
    if not m:
        raise ValueError("__version__ не найден")
    return m.group(1)


def prev_published(current: str):
    """Максимальная опубликованная версия строго меньше current."""
    req = urllib.request.Request(
        PYPI_JSON, headers={"User-Agent": "humanizer-ru-check-compatibility"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    cur = tuple(int(x) for x in current.split("."))
    best = None
    for rel in doc.get("releases", {}):
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", rel)
        if not m or not doc["releases"][rel]:
            continue
        ver = tuple(int(g) for g in m.groups())
        if ver < cur and (best is None or ver > best):
            best = ver
    return ".".join(str(x) for x in best) if best else None


def _tname(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _compat_problems(old, new, path, key=None) -> list:
    """Рекурсивное сравнение с типами JSON: 1 и True — разные типы,
    удалённое поле OLD — несовместимость, добавленное поле NEW — нет.

    Списки: каждый элемент OLD обязан иметь типизированную пару в NEW
    (добавления допустимы, удаления и подмены элементов — нет).
    """
    if key in NORM_TEXT_KEYS and isinstance(old, str):
        if isinstance(new, str):
            return []
        return ["%s: поле %s: OLD текст причины, NEW тип %s"
                % (path, key, _tname(new))]
    t_old, t_new = _tname(old), _tname(new)
    if t_old != t_new:
        return ["%s: поле %s: тип OLD=%s NEW=%s (в JSON-контракте это "
                "разные типы)" % (path, key or "-", t_old, t_new)]
    if t_old == "dict":
        problems = []
        for k in old:
            if k not in new:
                problems.append("%s: поле %s удалено в новой версии"
                                % (path, k))
            else:
                problems.extend(_compat_problems(old[k], new[k], path, k))
        return problems
    if t_old == "list":
        if key == "required":
            old_set, new_set = set(old), set(new)
            problems = []
            for item in sorted(old_set - new_set, key=repr):
                problems.append("%s: обязательное поле %r удалено "
                                "в новой версии" % (path, item))
            for item in sorted(new_set - old_set, key=repr):
                problems.append("%s: добавлено новое обязательное поле %r "
                                "(ломает старых клиентов)" % (path, item))
            return problems
        problems = []
        pool = list(new)
        for i, item in enumerate(old):
            hit = None
            best = None
            for j, cand in enumerate(pool):
                sub = _compat_problems(item, cand, path, key)
                if not sub:
                    hit = j
                    break
                if best is None or len(sub) < len(best[1]):
                    best = (j, sub)
            if hit is None:
                detail = ""
                if best is not None:
                    detail = "; ближайшее расхождение: %s" % best[1][0]
                    pool.pop(best[0])
                problems.append("%s: элемент %d списка %s отсутствует "
                                "или изменён в новой версии%s"
                                % (path, i, key or "-", detail))
            else:
                pool.pop(hit)
        return problems
    if key == "type" and old != new:
        return ["%s: поле type: тип OLD=%r NEW=%r"
                % (path, old, new)]
    if old != new:
        return ["%s: поле %s: OLD=%r NEW=%r" % (path, key or "-", old, new)]
    return []


def _is_exc(rec, name=None):
    rc = rec.get("rc")
    if not isinstance(rc, str) or not rc.startswith("EXC:"):
        return False
    return name is None or rc == "EXC:" + name


def _is_code2_envelope(rec, tool=None):
    if rec.get("rc") != 2:
        return False
    payload = rec.get("payload")
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("error"), str):
        return False
    return tool is None or payload.get("tool") == tool


def _report_facts_lost(rec):
    try:
        return rec["payload"]["files"][0]["facts"]["lost"]
    except (TypeError, KeyError, IndexError):
        return None


# Восстановление уже обещанного поведения (приказ цикла: «если
# исправление меняет наблюдаемую семантику — докажи, что оно
# восстанавливает уже обещанное поведение»). Каждая запись: ярлык пробы,
# описание, пункт контракта/документации, предикат OLD-поведения и
# предикат NEW-поведения. Вейвер применяется ТОЛЬКО когда оба предиката
# выполнены: произвольная смена поведения под видом восстановления
# невозможна; если NEW не соответствует контракту — это несовместимость.
CONTRACT_RESTORED = {
    "facts:bad.txt+good.txt": (
        "не-UTF-8 вход: traceback с пустым stdout заменён кодом 2 "
        "с конвертом ошибки",
        'contract.v1.json exit_codes."2": «вход не читается (нет файла, '
        'не UTF-8); с --json конверт ошибки в stdout»',
        lambda o: _is_exc(o, "UnicodeDecodeError"),
        lambda n: _is_code2_envelope(n, "humanizer-facts")),
    "report:bad.txt+good.txt": (
        "повреждённый UTF-8: молчаливый успех (errors=replace, код 0) "
        "заменён кодом 2 с конвертом ошибки",
        'contract.v1.json exit_codes."2"; docstring humanizer-report: '
        '«Коды: 0 — отчёт построен; 2 — ошибка входа»',
        lambda o: o.get("rc") == 0,
        lambda n: _is_code2_envelope(n, "humanizer-report")),
    "report:no-such-file.txt+good.txt": (
        "отсутствующий файл: traceback заменён кодом 2 с конвертом ошибки",
        'contract.v1.json exit_codes."2"',
        lambda o: _is_exc(o, "FileNotFoundError"),
        lambda n: _is_code2_envelope(n, "humanizer-report")),
    "facts:good.txt+bad.txt": (
        "не-UTF-8 вход «после»: traceback с пустым stdout заменён кодом 2 "
        "с конвертом ошибки",
        'contract.v1.json exit_codes."2"',
        lambda o: _is_exc(o, "UnicodeDecodeError"),
        lambda n: _is_code2_envelope(n, "humanizer-facts")),
    "report:good.txt+bad.txt": (
        "повреждённый UTF-8 «после»: молчаливый успех (errors=replace) "
        "заменён кодом 2 с конвертом ошибки",
        'contract.v1.json exit_codes."2"; docstring humanizer-report: '
        '«Коды: 0 — отчёт построен; 2 — ошибка входа»',
        lambda o: o.get("rc") == 0,
        lambda n: _is_code2_envelope(n, "humanizer-report")),
    "report:ru.txt+clean.txt": (
        "сверка фактов установленной поставки: OLD учитывал payload "
        "маркеров копипасты (числа oaicite/index/utm) как авторские факты "
        "— _strip_markers вне дерева репозитория не находил выражения и "
        "молча пропускал снятие; NEW восстанавливает документированный "
        "принцип «payload маркеров не является фактом автора» "
        "(lost 4 -> 2 на фиксированной паре проб)",
        "принцип edit_report._strip_markers («Payload маркеров копипасты "
        "не является фактом автора — check_examples делает то же через "
        "_loss_text»); пакетный импорт check_markers первичен",
        lambda o: _report_facts_lost(o) == 4,
        lambda n: _report_facts_lost(n) == 2),
}


def compare(old_recs, new_recs):
    """Несовместимости: записи OLD обязаны совпасть в NEW по типам и
    значениям всех полей (включая вложенные конверты всех файлов);
    NEW может добавлять поля. Возвращает (problems, restored, additions):
      problems  — человекочитаемые нарушения (несовместимость);
      restored  — ярлыки CONTRACT_RESTORED: поведение OLD нарушало
                  опубликованный контракт, NEW восстановило обещанное
                  (сверка предикатов обязательна — вейвер не маскирует
                  произвольную смену поведения);
      additions — ярлыки новых проб, отсутствующих в OLD (аддитивность).
    Нормализуются только явно нестабильные значения (NORM_TEXT_KEYS в
    пробе: тексты причин ошибок; пути файлов приводятся к именам).
    """
    problems = []
    restored = []
    additions = []
    old_by = {r["label"]: r for r in old_recs}
    new_by = {r["label"]: r for r in new_recs}
    for label, old in sorted(old_by.items()):
        new = new_by.get(label)
        if new is None:
            problems.append("%s: проба исчезла в новой версии" % label)
            continue
        if old.get("absent"):
            if new.get("absent"):
                problems.append("%s: проба отсутствует с обеих сторон — "
                                "матрица сломана" % label)
            else:
                additions.append(label)
            continue
        if new.get("absent"):
            problems.append("%s: операция удалена в новой версии" % label)
            continue
        waiver = CONTRACT_RESTORED.get(label)
        if waiver:
            _desc, _clause, old_pred, new_pred = waiver
            if old_pred(old) and new_pred(new):
                restored.append(label)
                continue
            if not new_pred(new):
                problems.append("%s: заявленное восстановление контракта "
                                "не выполнено — NEW не соответствует пункту "
                                "(%s)" % (label, _clause))
                continue
            # OLD не соответствует предпосылке вейвера (например, будущая
            # опубликованная версия уже несёт исправление) — обычное
            # сравнение.
        problems.extend(_compat_problems(old, new, label))
    for label in sorted(new_by):
        if label not in old_by:
            problems.append("%s: новая проба без пары (матрица разъехалась)"
                            % label)
    return problems, restored, additions


def _venv_python(venvdir: str) -> str:
    if os.name == "nt":
        return os.path.join(venvdir, "Scripts", "python.exe")
    return os.path.join(venvdir, "bin", "python")


def run_check() -> int:
    try:
        current = tree_version()
    except (OSError, ValueError) as exc:
        print("ОТКАЗ: версия дерева не читается: %r" % exc, file=sys.stderr)
        return 2
    try:
        prev = prev_published(current)
    except (OSError, ValueError, KeyError) as exc:
        print("ОТКАЗ: PyPI недоступен: %r" % exc, file=sys.stderr)
        return 2
    if prev is None:
        print("ОТКАЗ: нет опубликованной версии старше %s" % current,
              file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="compat-venv-")
    probe_path = os.path.join(tmp, "probe.py")
    with open(probe_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PROBE)
    try:
        venv = os.path.join(tmp, "venv")
        proc = subprocess.run([sys.executable, "-m", "venv", venv],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            print("ОТКАЗ: venv не создан: %s" % proc.stderr[-200:],
                  file=sys.stderr)
            return 2
        vpy = _venv_python(venv)
        proc = subprocess.run(
            [vpy, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "humanizer-ru==" + prev],
            capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            print("ОТКАЗ: установка humanizer-ru==%s не удалась (сеть?): %s"
                  % (prev, proc.stderr[-200:]), file=sys.stderr)
            return 2
        proc_old = subprocess.run([vpy, "-X", "utf8", probe_path],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=300)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep \
            + env.get("PYTHONPATH", "")
        proc_new = subprocess.run([sys.executable, "-X", "utf8", probe_path],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=300, env=env, cwd=ROOT)
        for name, proc in (("OLD", proc_old), ("NEW", proc_new)):
            if proc.returncode != 0:
                print("ОТКАЗ: пробный прогон %s упал: %s"
                      % (name, proc.stderr[-300:]), file=sys.stderr)
                return 2
        try:
            old_recs = json.loads(proc_old.stdout.strip().splitlines()[-1])
            new_recs = json.loads(proc_new.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            print("ОТКАЗ: вывод проб не JSON: %r" % exc, file=sys.stderr)
            return 2
        problems, restored, additions = compare(old_recs, new_recs)
        for p in problems:
            print("[FAIL] " + p)
        for label in restored:
            desc, clause, _o, _n = CONTRACT_RESTORED[label]
            print("[ВОССТАНОВЛЕНО] %s: %s — %s" % (label, desc, clause))
        for label in additions:
            print("[АДДИТИВНО] %s: новая проба (в OLD операции не было)"
                  % label)
        if problems:
            print("СОВМЕСТИМОСТЬ: %s -> %s — нарушений %d"
                  % (prev, current, len(problems)))
            return 1
        print("СОВМЕСТИМОСТЬ: %s -> %s — %d проб, аддитивность соблюдена "
              "(rc, конверты и детекция совпадают; новые поля разрешены); "
              "восстановлений контракта %d; новых операций %d"
              % (prev, current, len(new_recs), len(restored),
                 len(additions)))
        return 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("ОТКАЗ: среда: %r" % exc, file=sys.stderr)
        return 2
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    old = [{"label": "scan:a", "rc": 0, "features_total": 3},
           {"label": "markers:a", "rc": 1, "count": 2,
            "markers": ["utm_chatgpt", "zero_width"]}]
    p, _r, _a = compare(old, [dict(r) for r in old])
    case("идентичные прогоны совместимы", p == [])
    new_added = [{"label": "scan:a", "rc": 0, "features_total": 3,
                  "status": "out-of-scope"},
                 {"label": "markers:a", "rc": 1, "count": 2,
                  "markers": ["utm_chatgpt", "zero_width"]}]
    p, _r, _a = compare(old, new_added)
    case("новое поле — аддитивно, совместимо", p == [])
    rc_changed = [{"label": "scan:a", "rc": 2, "features_total": 3},
                  {"label": "markers:a", "rc": 1, "count": 2,
                   "markers": ["utm_chatgpt", "zero_width"]}]
    p, _r, _a = compare(old, rc_changed)
    case("смена rc ловится (негатив)", any("rc" in x for x in p))
    val_changed = [{"label": "scan:a", "rc": 0, "features_total": 4},
                   {"label": "markers:a", "rc": 1, "count": 2,
                   "markers": ["utm_chatgpt", "zero_width"]}]
    p, _r, _a = compare(old, val_changed)
    case("изменение значения поля ловится (негатив)",
         any("features_total" in x for x in p))
    dropped = [{"label": "scan:a", "rc": 0, "features_total": 3}]
    p, _r, _a = compare(old, dropped)
    case("исчезновение пробы ловится (негатив)",
         any("исчезла" in x for x in p))
    err_text = [{"label": "scan:a", "rc": 0, "features_total": 3},
                {"label": "markers:a", "rc": 1, "count": 2,
                 "markers": ["utm_chatgpt", "zero_width"],
                 "error": "путь /tmp/old-xxxx"}]
    err_new = [{"label": "scan:a", "rc": 0, "features_total": 3},
               {"label": "markers:a", "rc": 1, "count": 2,
                "markers": ["utm_chatgpt", "zero_width"],
                "error": "путь /tmp/new-yyyy"}]
    p, _r, _a = compare(err_text, err_new)
    case("текст error зависит от среды и не считается несовместимостью",
         p == [])
    err_gone = [{"label": "scan:a", "rc": 0, "features_total": 3},
                {"label": "markers:a", "rc": 1, "count": 2,
                 "markers": ["utm_chatgpt", "zero_width"]}]
    p, _r, _a = compare(err_text, err_gone)
    case("пропажа поля error ловится (негатив)",
         any("error" in x for x in p))
    typed_old = [{"label": "scan:a", "rc": 0,
                  "payload": {"tool": "humanizer-scan", "schema": 1,
                              "files": [{"file": "a.txt", "count": 2,
                                         "invariants": []}]}}]
    typed_bool = [{"label": "scan:a", "rc": 0,
                   "payload": {"tool": "humanizer-scan", "schema": True,
                               "files": [{"file": "a.txt", "count": 2,
                                          "invariants": []}]}}]
    p, _r, _a = compare(typed_old, typed_bool)
    case("schema 1 против True — разные типы JSON (негатив)",
         any("тип" in x for x in p))
    typed_rc_bool = [{"label": "scan:a", "rc": False,
                      "payload": typed_old[0]["payload"]}]
    p, _r, _a = compare(typed_old, typed_rc_bool)
    case("rc 0 против False — разные типы JSON (негатив)",
         any("тип" in x for x in p))
    typed_dropped = [{"label": "scan:a", "rc": 0,
                      "payload": {"tool": "humanizer-scan", "schema": 1,
                                  "files": [{"file": "a.txt",
                                             "count": 2}]}}]
    p, _r, _a = compare(typed_old, typed_dropped)
    case("удалённое вложенное поле invariants ловится (негатив)",
         any("invariants" in x for x in p))
    typed_added = [{"label": "scan:a", "rc": 0,
                    "payload": {"tool": "humanizer-scan", "schema": 1,
                                "files": [{"file": "a.txt", "count": 2,
                                           "invariants": [],
                                           "date_like": True}]}}]
    p, _r, _a = compare(typed_old, typed_added)
    case("добавленное вложенное поле аддитивно", p == [])

    schema_old = [{"label": "mcp:tools", "rc": 0, "payload": {
        "humanizer_scan": {"required": ["text"], "input_schema": {
            "type": "object", "required": ["text"],
            "properties": {"text": {"type": "string"}}}}}}]
    schema_required = [{"label": "mcp:tools", "rc": 0, "payload": {
        "humanizer_scan": {"required": ["text", "genre"],
                            "input_schema": {
                                "type": "object",
                                "required": ["text", "genre"],
                                "properties": {
                                    "text": {"type": "string"},
                                    "genre": {"type": "string"}}}}}}]
    p, _r, _a = compare(schema_old, schema_required)
    case("новый required-параметр MCP ловится (негатив)",
         any("обязательное поле" in x for x in p))
    schema_type = [{"label": "mcp:tools", "rc": 0, "payload": {
        "humanizer_scan": {"required": ["text"], "input_schema": {
            "type": "object", "required": ["text"],
            "properties": {"text": {"type": "integer"}}}}}}]
    p, _r, _a = compare(schema_old, schema_type)
    case("смена type MCP ловится (негатив)",
         any("тип" in x for x in p))

    # Новые операции: отсутствует в OLD, присутствует в NEW — аддитивность.
    absent_old = [{"label": "clean:a", "absent": True}]
    present_new = [{"label": "clean:a", "rc": 0,
                    "payload": {"tool": "humanizer-clean", "schema": 1,
                                "files": []}}]
    p, _r, additions = compare(absent_old, present_new)
    case("новая операция (нет в OLD) — аддитивна, не несовместимость",
         p == [] and additions == ["clean:a"])
    p, _r, _a = compare(present_new, absent_old)
    case("удаление операции в NEW ловится (негатив)",
         any("удалена" in x for x in p))
    p, _r, _a = compare(absent_old, [{"label": "clean:a", "absent": True}])
    case("проба отсутствует с обеих сторон — матрица сломана (негатив)",
         any("матрица" in x for x in p))

    # Вейверы восстановления контракта: применяются только когда OLD
    # нарушал контракт, а NEW ему соответствует.
    exc_old = [{"label": "facts:bad.txt+good.txt",
                "rc": "EXC:UnicodeDecodeError", "payload": None}]
    env_new = [{"label": "facts:bad.txt+good.txt", "rc": 2,
                "payload": {"tool": "humanizer-facts", "schema": 1,
                            "files": ["bad.txt", "good.txt"],
                            "error": "вход не читается (код 2)"}}]
    p, restored, _a = compare(exc_old, env_new)
    case("traceback -> код 2 с конвертом: восстановление контракта",
         p == [] and restored == ["facts:bad.txt+good.txt"])
    silent_new = [{"label": "facts:bad.txt+good.txt", "rc": 0,
                   "payload": {"tool": "humanizer-facts", "schema": 1,
                               "files": ["bad.txt", "good.txt"],
                               "counts": {"lost": 0, "added": 0,
                                          "changed": 0},
                               "diff": {"lost": [], "added": [],
                                        "changed": []}}}]
    p, _r2, _a = compare(exc_old, silent_new)
    case("вейвер НЕ маскирует молчаливый успех (негатив)", p != [])
    p, _r2, _a = compare(env_old := [dict(env_new[0])], env_new)
    case("OLD уже соответствует контракту — обычное сравнение, вейвер спит",
         p == [])
    rep_old = [{"label": "report:bad.txt+good.txt", "rc": 0,
                "payload": {"tool": "humanizer-report", "schema": 1,
                            "files": [{"before": "bad.txt",
                                       "after": "good.txt",
                                       "tokens": {"keep": 1, "add": 1,
                                                  "delete": 0}}]}}]
    rep_new = [{"label": "report:bad.txt+good.txt", "rc": 2,
                "payload": {"tool": "humanizer-report", "schema": 1,
                            "files": [{"before": "bad.txt",
                                       "after": "good.txt",
                                       "error": "причина"}],
                            "error": "вход не читается (код 2)"}}]
    p, restored3, _a = compare(rep_old, rep_new)
    case("report: молчаливый replace -> код 2: восстановление контракта",
         p == [] and restored3 == ["report:bad.txt+good.txt"])
    rep4_old = [{"label": "report:ru.txt+clean.txt", "rc": 0,
                 "payload": {"tool": "humanizer-report", "schema": 1,
                             "files": [{"before": "ru.txt",
                                        "after": "clean.txt",
                                        "facts": {"lost": 4, "changed": 0,
                                                  "unchanged": False}}]}}]
    rep2_new = [{"label": "report:ru.txt+clean.txt", "rc": 0,
                 "payload": {"tool": "humanizer-report", "schema": 1,
                             "files": [{"before": "ru.txt",
                                        "after": "clean.txt",
                                        "facts": {"lost": 2, "changed": 0,
                                                  "unchanged": False}}]}}]
    p, restored4, _a = compare(rep4_old, rep2_new)
    case("report: payload маркеров не факт — восстановление принципа",
         p == [] and restored4 == ["report:ru.txt+clean.txt"])
    rep3_new = [{"label": "report:ru.txt+clean.txt", "rc": 0,
                 "payload": {"tool": "humanizer-report", "schema": 1,
                             "files": [{"before": "ru.txt",
                                        "after": "clean.txt",
                                        "facts": {"lost": 3, "changed": 0,
                                                  "unchanged": False}}]}}]
    p, _r4, _a = compare(rep4_old, rep3_new)
    case("вейвер lost 4->2 не маскирует lost 4->3 (негатив)", p != [])
    print("САМОПРОВЕРКА check_compatibility: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Совместимость с предыдущей опубликованной версией "
                    "(аддитивность без смены rc и детекции).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
