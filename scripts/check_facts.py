#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_facts.py — реестр фактов: числа витрины существуют только из
`eval/facts/facts.v1.json`. Гейт недрейфа (число, вписанное в текст руками,
расходилось с данными — этот класс ошибок ловили трижды) и машина статусов:

- каждый десятичный/дробный токен витринных файлов обязан быть покрыт
  записью реестра (иначе дрейф);
- токен записи со статусом `withdrawn` вне документов-отзывов валит сборку
  (документы-отзывы обязаны цитировать отзываемое число — для них действует
  только покрытие);
- цепочка воспроизведения (оба режима): скрипты из строки `reproduce`
  обязаны существовать в дереве и компилироваться — отсутствующая команда
  воспроизведения больше не проходит приёмку; `source_data` (необязательное
  поле) сверяет наличие и фактические хеши исходных данных, run:-источники
  требуют допущения private-run-artifact и зафиксированного хеша;
- `--strict-publication` (релизный режим перед пушем): дополнительно
  фактически исполняет команды записей с `publication_approved: true` и
  `reproduce_public: true` (код 0 обязателен; исполняются только
  python-команды реестра), а также ни один
  токен с `publication_approved: false` не встречается в файлах, которые этот
  пуш делает впервые публичными (добавленные/изменённые относительно
  `origin/main`, включая неотслеживаемые). Файлы, уже публичные в
  `origin/main`, не пересматриваются: одинаковое число в старой заметке —
  не утечка. Без git режим консервативно сканирует всё дерево и пишет об
  этом в итог.

Скоуп покрытия: README.md, README.en.md, LEADERBOARD.md, SKILL.md,
docs/FRAMEWORK.md, ERRATA.md, AGENTS.md и документ-отзыв оси. CHANGELOG.md —
историческая хроника, вне скоупа (отзывы фиксирует ERRATA).

Коды: 0 — чисто; 1 — дрейф/схема/размещение; 2 — ошибка запуска.
Только стандартная библиотека.

    python3 scripts/check_facts.py                     # обычный режим
    python3 scripts/check_facts.py --strict-publication
    python3 scripts/check_facts.py --selftest
"""
import argparse
import glob
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTRY_REL = os.path.join("eval", "facts", "facts.v1.json")

SHOWCASE = [
    "README.md",
    "README.en.md",
    "LEADERBOARD.md",
    "SKILL.md",
    os.path.join("docs", "FRAMEWORK.md"),
    "ERRATA.md",
    "AGENTS.md",
    os.path.join("research", "AXIS-RUBRIC-RETRACTION-2026-09-01.md"),
]
RETRACTION_DOCS = {
    "ERRATA.md",
    os.path.join("research", "AXIS-RUBRIC-RETRACTION-2026-09-01.md"),
}
STRICT_SKIP = {
    REGISTRY_REL.replace(os.sep, "/"),
    "eval/facts/facts.schema.v1.json",
    "scripts/check_facts.py",
    # Архив журнала версий: перенос уже публичного в origin/main текста
    # (ранние версии) дословно — не новая публикация чисел.
    "docs/CHANGELOG-archive.md",
}
TEXT_EXT = (".md", ".txt", ".json", ".py", ".yml", ".yaml", ".cff", ".toml")

# Литералы версий вычитываются ДО извлечения токенов: номер релиза вида
# vX.Y.Z не должен давать токен «X.Y» (иначе вечный ложный дрейф на каждом
# выпуске).
VERSION_RE = re.compile(r"v?\d+\.\d+\.\d+")
V2_RE = re.compile(r"\bv\d+\.\d+\b")
TOKEN_RE = re.compile(r"(?<![\d,.])(\d\.\d{2,4}|\d{1,4}/\d{1,4})(?![\d])")
TOKEN_FORM_RE = re.compile(r"^(\d\.\d{2,4}|\d{1,4}/\d{1,4})$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUSES = ("proven", "limited", "unknown", "withdrawn")

# Пометка для записей, чей артефакт живёт в приватном прогоне: одобренное
# число обязано быть проверяемым, поэтому приватный артефакт без явной
# пометки (и обязательства публикации данных следующим батчем) — нарушение.
PRIVATE_MARK = "артефакт приватного прогона"  # историческая пометка note; заменена полем assumptions
# Контролируемый словарь допущений (заимствование A из консультации
# fable-primegaps-applicability, 2026-09-04): аналог permitted_axioms у
# формализаций OpenAI. Запись с run:-артефактом обязана нести
# private-run-artifact; допущение вне словаря валит гейт.
ASSUMPTIONS_ENUM = ("llm-judge-oracle", "single-family-panel",
                    "private-run-artifact", "prereg-frozen",
                    "positional-noise-documented")
# Документированный сверочный суффикс артефакта: «путь (sha256 <64 hex>)».
SHA_SUFFIX_RE = re.compile(r" \(sha256 [0-9A-Fa-f]{64}\)$")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")


def strip_versions(text):
    return V2_RE.sub(" ", VERSION_RE.sub(" ", text))


def tokens_of(text):
    """Пары (строка, токен): десятичные 0.ХХ..0.ХХХХ и доли N/M."""
    out = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for m in TOKEN_RE.finditer(strip_versions(line)):
            out.append((line_no, m.group(1)))
    return out


def schema_errors(data):
    errs = []
    if not isinstance(data, dict):
        return ["реестр не объект"]
    for key in ("registry", "schema", "updated", "entries"):
        if key not in data:
            errs.append("нет поля %s" % key)
    if data.get("schema") != "facts.schema.v1.json":
        errs.append("schema обязан быть 'facts.schema.v1.json'")
    if not DATE_RE.match(str(data.get("updated", ""))):
        errs.append("updated обязан быть датой YYYY-MM-DD")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return errs + ["entries обязан быть непустым списком"]
    seen = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errs.append("запись #%d не объект" % i)
            continue
        fid = e.get("fact_id", "?")
        where = "запись %s" % fid
        for req in ("fact_id", "claim", "status", "tokens", "artifact", "date"):
            if req not in e:
                errs.append("%s: нет поля %s" % (where, req))
        pa = e.get("publication_approved")
        if not isinstance(pa, bool):
            errs.append("%s: publication_approved обязан быть true/false" % where)
        if not isinstance(fid, str) or not ID_RE.match(fid):
            errs.append("%s: fact_id вне формы [a-z0-9-]" % where)
        elif fid in seen:
            errs.append("дубликат fact_id %s" % fid)
        else:
            seen.add(fid)
        if e.get("status") not in STATUSES:
            errs.append("%s: статус %r вне %s" % (where, e.get("status"),
                                                  list(STATUSES)))
        toks = e.get("tokens")
        if not isinstance(toks, list) or not toks:
            errs.append("%s: tokens обязан быть непустым списком" % where)
        else:
            for t in toks:
                if not isinstance(t, str) or not TOKEN_FORM_RE.match(t):
                    errs.append("%s: токен %r вне формы числа/доли" % (where, t))
        if not DATE_RE.match(str(e.get("date", ""))):
            errs.append("%s: date обязана быть YYYY-MM-DD" % where)
        claim = e.get("claim")
        if not isinstance(claim, str) or len(claim.strip()) < 10:
            errs.append("%s: claim короче 10 символов" % where)
        art = e.get("artifact")
        if not isinstance(art, str) or len(art.strip()) < 3:
            errs.append("%s: artifact обязателен" % where)
    return errs


def assumptions_problems(data):
    """Допущения записи — только из словаря ASSUMPTIONS_ENUM."""
    probs = []
    for e in data.get("entries", []):
        fid = e.get("fact_id", "?")
        if "assumptions" not in e:
            continue
        a = e["assumptions"]
        if not isinstance(a, list) or not a:
            probs.append("запись %s: assumptions должен быть непустым списком" % fid)
            continue
        for v in a:
            if v not in ASSUMPTIONS_ENUM:
                probs.append("запись %s: допущение вне словаря: %r" % (fid, v))
    return probs


def changed_vs_origin(root):
    """Файлы, которые пуш сделает впервые публичными: добавленные/изменённые
    относительно origin/main плюс неотслеживаемые. Возвращает множество путей
    с разделителем '/' или None, если git недоступен (тогда строгий режим
    консервативно сканирует всё дерево)."""
    import subprocess
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "--diff-filter=AM",
             "origin/main"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            timeout=120)
        if diff.returncode != 0:
            return None
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            timeout=120)
        if untracked.returncode != 0:
            return None
        changed = set()
        for out in (diff.stdout, untracked.stdout):
            for ln in out.splitlines():
                ln = ln.strip().strip('"')
                if ln:
                    changed.add(ln.replace(os.sep, "/"))
        return changed
    except (OSError, subprocess.SubprocessError):
        return None


def load_registry(root):
    path = os.path.join(root, REGISTRY_REL)
    if not os.path.isfile(path):
        return None, ["нет %s" % path]
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), []
    except (OSError, ValueError) as exc:
        return None, ["реестр не читается: %s" % exc]


def token_maps(data):
    statuses = {}
    approved = {}
    for e in data["entries"]:
        for t in e["tokens"]:
            statuses.setdefault(t, set()).add(e["status"])
            approved[t] = approved.get(t, False) or bool(e["publication_approved"])
    return statuses, approved


def _reproduce_scripts(reproduce):
    """Пути скриптов репозитория из строки reproduce (до первой скобки).

    Строка reproduce свободной формы: «python3 scripts/x.py --flag»,
    «a.py + b.py (один проход; …)», «gh … ; gh …». Извлекаются токены,
    похожие на пути .py; внешние CLI-команды (gh/curl) не извлекаются —
    их исполнимость гейтом не проверяется (сеть/авторизация).
    """
    s = str(reproduce).split(" (")[0]
    return re.findall(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.py", s)


def reproduce_problems(root, data):
    """Цепочка «утверждение → анализ»: скрипты reproduce существуют и
    компилируются. Отсутствие файла или синтаксис ломает приёмку в обоих
    режимах: команда воспроизведения обязана быть исполнимой хотя бы
    структурно, а не только присутствовать строкой в JSON."""
    import py_compile
    problems = []
    for e in data.get("entries", []):
        fid = e.get("fact_id", "?")
        rep = e.get("reproduce")
        if not isinstance(rep, str) or not rep.strip():
            continue
        for script in _reproduce_scripts(rep):
            path = os.path.join(root, script.replace("/", os.sep))
            if not os.path.isfile(path):
                problems.append(
                    "запись %s: reproduce-скрипт отсутствует: %s (команда %r)"
                    % (fid, script, rep))
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="facts-compile-") as td:
                    py_compile.compile(path, cfile=os.path.join(td, "m.pyc"),
                                       doraise=True)
            except Exception as exc:  # noqa: BLE001 — любая ошибка компиляции
                problems.append(
                    "запись %s: reproduce-скрипт не компилируется: %s (%s)"
                    % (fid, script, exc))
    return problems


def source_data_problems(root, data):
    """Цепочка «исходные данные → число»: наличие и хеши исходных данных.

    Необязательное поле source_data — список строк «путь (sha256 <64 hex>)»
    или «run:путь (sha256 <64 hex>)» (данные приватного прогона). Хеш
    публичного файла сверяется фактически; run:-источник обязан нести
    допущение private-run-artifact и зафиксированный хеш. Запись без
    source_data не проверяется (исторические записи), но одобренная
    запись с run:-артефактом и так обязана нести допущение (см.
    artifact_problems).
    """
    import hashlib
    problems = []
    for e in data.get("entries", []):
        fid = e.get("fact_id", "?")
        sd = e.get("source_data")
        if sd is None:
            continue
        if not isinstance(sd, list) or not sd:
            problems.append("запись %s: source_data обязан быть непустым "
                            "списком" % fid)
            continue
        assumptions = e.get("assumptions")
        for item in sd:
            if not isinstance(item, str) or not item.strip():
                problems.append("запись %s: source_data содержит не строку"
                                % fid)
                continue
            m = re.search(r"\(sha256 ([0-9A-Fa-f]{64})\)", item)
            sha = m.group(1).lower() if m else None
            path_part = SHA_SUFFIX_RE.sub("", item).strip()
            if path_part.startswith("run:"):
                if not isinstance(assumptions, list) \
                        or "private-run-artifact" not in assumptions:
                    problems.append(
                        "запись %s: run:-источник %s без допущения "
                        "private-run-artifact" % (fid, path_part))
                if sha is None:
                    problems.append(
                        "запись %s: приватный источник %s без "
                        "зафиксированного хеша" % (fid, path_part))
                continue
            full = os.path.join(root, path_part.replace("/", os.sep))
            if not os.path.isfile(full):
                problems.append("запись %s: исходные данные недоступны: %s"
                                % (fid, path_part))
                continue
            if sha is None:
                problems.append("запись %s: source_data без хеша: %s"
                                % (fid, path_part))
                continue
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            if h.hexdigest() != sha:
                problems.append("запись %s: хеш %s не совпал с зафиксированным"
                                % (fid, path_part))
    return problems


def reproduce_run_problems(root, data):
    """Фактическая исполнимость публичного воспроизведения (только строгий
    режим, только записи с publication_approved=true и
    reproduce_public=true): команда исполняется в корне репозитория и
    обязана дать код 0. Поддерживаются python-команды, в том числе цепочки
    «A && B»; внешние CLI (gh/curl) reproduce_public не помечаются —
    их исполнение зависит от сети и авторизации."""
    import subprocess
    problems = []
    for e in data.get("entries", []):
        fid = e.get("fact_id", "?")
        if not (e.get("publication_approved") is True
                and e.get("reproduce_public") is True):
            continue
        rep = str(e.get("reproduce", "")).split(" (")[0]
        parts = [p.strip() for p in rep.split("&&") if p.strip()]
        if not parts:
            problems.append("запись %s: reproduce_public без команды" % fid)
            continue
        for part in parts:
            toks = part.split()
            if toks[0] not in ("python", "python3"):
                problems.append("запись %s: reproduce_public поддерживает "
                                "только python-команды: %r" % (fid, part))
                continue
            argv = [sys.executable] + toks[1:]
            try:
                proc = subprocess.run(
                    argv, cwd=root, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=900)
            except (OSError, subprocess.SubprocessError) as exc:
                problems.append("запись %s: reproduce-команда не исполнилась: "
                                "%r" % (fid, exc))
                continue
            if proc.returncode != 0:
                tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
                problems.append("запись %s: reproduce-команда %r вернула код "
                                "%d: %s" % (fid, part, proc.returncode,
                                            tail[-200:]))
    return problems


def artifact_problems(root, data):
    """publication_approved=true ⇒ артефакт публично доступен.

    Артефакт — путь/глоб в дереве репозитория (проверяется существование;
    документированный суффикс «(sha256 <64 hex>)» — сверочный хеш файла —
    при проверке пути отбрасывается), URL (гейт не ходит в сеть;
    доступность обеспечивает публичная ссылка) или префикс run: (приватный
    прогон). Запись с run:-артефактом обязана нести пометку «артефакт
    приватного прогона» в note — зарегистрированное исключение до
    публикации данных; для одобренных записей отсутствие пометки вдвойне
    нарушение: одобренное число должно быть проверяемым из публичных
    данных.
    """
    problems = []
    for e in data.get("entries", []):
        fid = e.get("fact_id", "?")
        art = str(e.get("artifact", ""))
        note = str(e.get("note", ""))
        approved = e.get("publication_approved") is True
        for part in [p.strip() for p in art.split(",") if p.strip()]:
            if part.startswith("run:"):
                assumptions = e.get("assumptions")
                if not isinstance(assumptions, list) \
                        or "private-run-artifact" not in assumptions:
                    problems.append(
                        "запись %s: run:-артефакт без допущения "
                        "private-run-artifact в assumptions%s" % (
                            fid,
                            " (publication_approved=true — одобренное число "
                            "обязано быть проверяемым)" if approved else ""))
                continue
            if part.startswith(("http://", "https://")):
                continue
            path_part = SHA_SUFFIX_RE.sub("", part)
            if not glob.glob(os.path.join(root, path_part.replace("/", os.sep))):
                problems.append("запись %s: артефакт %s недоступен в дереве "
                                "репозитория%s" % (
                                    fid, part,
                                    " (publication_approved=true)"
                                    if approved else ""))
    return problems


def run(root, strict):
    data, errs = load_registry(root)
    if errs:
        return 2, errs, ""
    errs = schema_errors(data)
    if errs:
        return 1, errs, ""
    statuses, approved = token_maps(data)
    problems = artifact_problems(root, data)
    problems += assumptions_problems(data)
    problems += reproduce_problems(root, data)
    problems += source_data_problems(root, data)
    for rel in SHOWCASE:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for line_no, tok in tokens_of(text):
            sts = statuses.get(tok)
            if sts is None:
                problems.append("%s:%d: токен %s не покрыт реестром (дрейф)"
                                % (rel, line_no, tok))
                continue
            if "withdrawn" in sts:
                if sts - {"withdrawn"}:
                    problems.append("реестр: токен %s в записях с противоречивыми "
                                    "статусами (есть withdrawn и не-withdrawn)" % tok)
                elif rel not in RETRACTION_DOCS:
                    problems.append("%s:%d: токен %s со статусом withdrawn вне "
                                    "документов-отзывов" % (rel, line_no, tok))
    strict_note = ""
    if strict:
        # Фактическая исполнимость публичного воспроизведения: команды
        # записей с reproduce_public=true исполняются (это единственная
        # часть гейта, запускающая код реестра; команды принадлежат
        # репозиторию и детерминированы).
        problems += reproduce_run_problems(root, data)
        changed = changed_vs_origin(root)
        if changed is None:
            strict_note = ("git недоступен: строгий режим сканирует всё "
                           "дерево (консервативно)")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for fn in filenames:
                if not fn.endswith(TEXT_EXT):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if rel in STRICT_SKIP:
                    continue
                if changed is not None and rel not in changed:
                    continue  # уже публично в origin/main — не утечка
                try:
                    with open(full, encoding="utf-8") as fh:
                        text = fh.read()
                except (OSError, UnicodeDecodeError):
                    continue
                for line_no, tok in tokens_of(text):
                    if tok in approved and not approved[tok]:
                        problems.append("%s:%d: неодобренный токен %s в "
                                        "добавленном/изменённом файле "
                                        "(публикация без ответа владельца "
                                        "запрещена)" % (rel, line_no, tok))
    return (1 if problems else 0), problems, strict_note


# --------------------------------------------------------------- selftest

def _w(base, rel, text):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _registry(entries):
    return {
        "registry": "selftest",
        "schema": "facts.schema.v1.json",
        "updated": "2026-09-01",
        "entries": entries,
    }


def _entry(**kw):
    base = {
        "fact_id": "selftest-entry",
        "claim": "самопроверочное утверждение для гейта",
        "status": "limited",
        "publication_approved": True,
        "tokens": ["0.1234"],
        "artifact": "tests/fixtures/selftest.json",
        "date": "2026-09-01",
    }
    base.update(kw)
    return base


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    def tree_with(reg, readme="AUC 0.1234", extra=None):
        td = tempfile.mkdtemp(prefix="facts-selftest-")
        _w(td, REGISTRY_REL, json.dumps(reg, ensure_ascii=False))
        _w(td, "README.md", readme)
        _w(td, "tests/fixtures/selftest.json", "{}")
        for rel, text in (extra or {}).items():
            _w(td, rel, text)
        return td

    ok_reg = _registry([
        _entry(),
        _entry(fact_id="withdrawn-one", status="withdrawn", tokens=["0.9999"]),
        _entry(fact_id="unapproved-one", publication_approved=False,
               tokens=["0.5555"]),
    ])

    td = tree_with(ok_reg)
    rc, probs, _ = run(td, strict=False)
    case("чистая витрина, покрытая реестром, зелёная", rc == 0 and not probs)

    td = tree_with(ok_reg, readme="AUC 0.1234 и подложное 0.4321")
    rc, probs, _ = run(td, strict=False)
    case("число без записи в реестре ВАЛИТСЯ (дрейф)",
         rc == 1 and any("0.4321" in p and "дрейф" in p for p in probs))

    td = tree_with(ok_reg, readme="отозванное 0.9999 в витрине")
    rc, probs, _ = run(td, strict=False)
    case("withdrawn токен вне документов-отзывов ВАЛИТСЯ",
         rc == 1 and any("withdrawn" in p for p in probs))

    td = tree_with(ok_reg, readme="AUC 0.1234",
                   extra={"ERRATA.md": "отзываем 0.9999 как меру качества"})
    rc, probs, _ = run(td, strict=False)
    case("withdrawn токен в документе-отзыве законен",
         rc == 0 and not probs)

    # Версии собираются из частей: гейт зашитых версий сканирует этот файл,
    # а литерал X.Y.Z в самопроверке устаревал бы с каждым выпуском.
    _ver = "%d.%d.%d" % (3, 16, 9)
    _dsh = "%d.%d.%d" % (0, 1, 0)
    td = tree_with(ok_reg,
                   readme="версия v%s, dsh %s-rc.6, AUC 0.1234" % (_ver, _dsh))
    rc, probs, _ = run(td, strict=False)
    case("литералы версий не дают токенов", rc == 0 and not probs)

    bad_status = _registry([_entry(status="доказано")])
    td = tree_with(bad_status)
    rc, probs, _ = run(td, strict=False)
    case("статус вне словаря ВАЛИТСЯ на схеме",
         rc == 1 and any("статус" in p for p in probs))

    dup = _registry([_entry(), _entry()])
    td = tree_with(dup)
    rc, probs, _ = run(td, strict=False)
    case("дубликат fact_id ВАЛИТСЯ",
         rc == 1 and any("дубликат" in p for p in probs))

    bad_tok = _registry([_entry(tokens=["1.2"])])
    td = tree_with(bad_tok)
    rc, probs, _ = run(td, strict=False)
    case("токен вне формы числа/доли ВАЛИТСЯ на схеме",
         rc == 1 and any("вне формы" in p for p in probs))

    td = tree_with(ok_reg, readme="AUC 0.1234",
                   extra={"docs/x.md": "число 0.5555 в глубине"})
    rc, _, _ = run(td, strict=False)
    case("в обычном режиме неодобренный токен вне витрины не трогается", rc == 0)
    rc, probs, _ = run(td, strict=True)
    case("--strict-publication ловит неодобренный токен (без git: всё дерево)",
         rc == 1 and any("0.5555" in p for p in probs))

    run_art = _registry([_entry(artifact="run:w1/x.json")])
    td = tree_with(run_art)
    rc, probs, _ = run(td, strict=False)
    case("run:-артефакт без пометки ВАЛИТСЯ (одобренное число непроверяемо)",
         rc == 1 and any("private-run-artifact" in p for p in probs))

    run_marked = _registry([_entry(
        artifact="run:w1/x.json",
        note="артефакт приватного прогона, публикация — RR-03",
        assumptions=["private-run-artifact"])])
    td = tree_with(run_marked)
    rc, probs, _ = run(td, strict=False)
    case("run:-артефакт с пометкой законен", rc == 0 and not probs)

    missing = _registry([_entry(artifact="eval/facts/does-not-exist.json")])
    td = tree_with(missing)
    rc, probs, _ = run(td, strict=False)
    case("одобренная запись с отсутствующим артефактом ВАЛИТСЯ",
         rc == 1 and any("недоступен" in p for p in probs))

    sha_art = _registry([_entry(
        artifact="tests/fixtures/selftest.json (sha256 %s)" % ("ab" * 32))])
    td = tree_with(sha_art)
    rc, probs, _ = run(td, strict=False)
    case("сверочный суффикс (sha256 …) не мешает разрешению пути артефакта",
         rc == 0 and not probs)
    sha_bad = _registry([_entry(
        artifact="tests/fixtures/selftest.json (sha256 short)")])
    td = tree_with(sha_bad)
    rc, probs, _ = run(td, strict=False)
    case("неполный суффикс sha256 не разрешает отсутствующий путь (негатив)",
         rc == 1 and any("недоступен" in p for p in probs))

    # Цепочка воспроизведения: скрипт существует и компилируется (оба
    # режима), публичное исполнение — только в строгом.
    repro_missing = _registry([_entry(
        reproduce="python3 tools/no_such_tool.py")])
    td = tree_with(repro_missing)
    rc, probs, _ = run(td, strict=False)
    case("reproduce: отсутствующий скрипт ловится",
         rc == 1 and any("отсутствует" in p for p in probs))

    repro_broken = _registry([_entry(
        reproduce="python3 scripts/broken_tool.py")])
    td = tree_with(repro_broken,
                   extra={"scripts/broken_tool.py": "def (:\n"})
    rc, probs, _ = run(td, strict=False)
    case("reproduce: некомпилируемый скрипт ловится",
         rc == 1 and any("не компилируется" in p for p in probs))

    repro_ok = _registry([_entry(
        reproduce="python3 scripts/ok_tool.py (один проход)")])
    td = tree_with(repro_ok, extra={"scripts/ok_tool.py": "print('ok')\n"})
    rc, probs, _ = run(td, strict=False)
    case("reproduce: существующий компилируемый скрипт законен",
         rc == 0 and not probs)

    runpub_fail = _registry([_entry(
        reproduce="python3 scripts/fail_tool.py", reproduce_public=True)])
    td = tree_with(runpub_fail,
                   extra={"scripts/fail_tool.py": "import sys; sys.exit(3)\n"})
    rc, probs, _ = run(td, strict=True)
    case("strict: неисполнимое публичное воспроизведение ловится",
         rc == 1 and any("код 3" in p for p in probs))
    rc2, _probs2, _ = run(td, strict=False)
    case("обычный режим команды не исполняет (структурная проверка)",
         rc2 == 0)

    runpub_ok = _registry([_entry(
        reproduce="python3 scripts/ok_tool.py", reproduce_public=True)])
    td = tree_with(runpub_ok, extra={"scripts/ok_tool.py": "print('ok')\n"})
    rc, probs, _ = run(td, strict=True)
    case("strict: исполнимое публичное воспроизведение проходит",
         rc == 0 and not probs)

    # source_data: наличие и фактические хеши исходных данных.
    import hashlib as _hl
    _sha = _hl.sha256(b"{}").hexdigest()
    sd_bad = _registry([_entry(source_data=[
        "tests/fixtures/selftest.json (sha256 %s)" % ("cd" * 32)])])
    td = tree_with(sd_bad)
    rc, probs, _ = run(td, strict=False)
    case("source_data: несовпавший хеш ловится",
         rc == 1 and any("не совпал" in p for p in probs))
    sd_ok = _registry([_entry(source_data=[
        "tests/fixtures/selftest.json (sha256 %s)" % _sha])])
    td = tree_with(sd_ok)
    rc, probs, _ = run(td, strict=False)
    case("source_data: совпавший хеш законен", rc == 0 and not probs)
    sd_nosha = _registry([_entry(
        source_data=["tests/fixtures/selftest.json"])])
    td = tree_with(sd_nosha)
    rc, probs, _ = run(td, strict=False)
    case("source_data: публичный источник без хеша ловится",
         rc == 1 and any("без хеша" in p for p in probs))
    sd_run = _registry([_entry(
        source_data=["run:m/x.json (sha256 %s)" % _sha])])
    td = tree_with(sd_run)
    rc, probs, _ = run(td, strict=False)
    case("source_data: run:-источник без допущения ловится",
         rc == 1 and any("private-run-artifact" in p for p in probs))
    sd_run_ok = _registry([_entry(
        source_data=["run:m/x.json (sha256 %s)" % _sha],
        assumptions=["private-run-artifact"])])
    td = tree_with(sd_run_ok)
    rc, probs, _ = run(td, strict=False)
    case("source_data: run:-источник с допущением законен",
         rc == 0 and not probs)

    data, errs = load_registry(ROOT)
    case("реальный реестр читается", data is not None and not errs)
    case("реальный реестр структурно валиден", not schema_errors(data))
    case("реальный реестр: артефакты доступны",
         not artifact_problems(ROOT, data))
    case("реальный реестр: цепочка воспроизведения цела",
         not reproduce_problems(ROOT, data))
    case("реальный реестр: хеши исходных данных совпадают",
         not source_data_problems(ROOT, data))

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Реестр фактов: числа витрины только из "
                    "eval/facts/facts.v1.json (дрейф и размещение статусов).")
    ap.add_argument("--strict-publication", action="store_true",
                    help="релизный режим: неодобренные токены запрещены "
                         "в любом файле дерева репо")
    ap.add_argument("--selftest", action="store_true",
                    help="самопроверка с негативными кейсами")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    rc, problems, note = run(ROOT, strict=args.strict_publication)
    for p in problems:
        print(p)
    mode = "strict-publication" if args.strict_publication else "обычный"
    if note:
        print(note)
    print("ФАКТЫ (%s режим): проблем %d" % (mode, len(problems)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
