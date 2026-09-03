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
- `--strict-publication` (релизный режим перед пушем): дополнительно ни один
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
PRIVATE_MARK = "артефакт приватного прогона"
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
                if PRIVATE_MARK not in note:
                    problems.append(
                        "запись %s: артефакт %s указывает приватный прогон без "
                        "пометки «%s»%s" % (
                            fid, part, PRIVATE_MARK,
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
         rc == 1 and any(PRIVATE_MARK in p for p in probs))

    run_marked = _registry([_entry(
        artifact="run:w1/x.json",
        note="артефакт приватного прогона, публикация — RR-03")])
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

    data, errs = load_registry(ROOT)
    case("реальный реестр читается", data is not None and not errs)
    case("реальный реестр структурно валиден", not schema_errors(data))
    case("реальный реестр: артефакты доступны",
         not artifact_problems(ROOT, data))

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
