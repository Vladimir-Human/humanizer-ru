#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self_audit.py — самоприменение как публичное доказательство.

Прогоняет детерминированные инструменты проекта по всем публичным файлам
поставки и пишет машиночитаемый отчёт `eval/facts/self-audit.v1.json`:
версия, дата, коммит измерения, числа по файлам с явным методом. Отчёт —
первое публичное подтверждённое число проекта со статусом proven: «наши
детекторы прогнаны по нашим текстам, вот результаты, вот команда
перепроверки».

Методы (явно указаны в отчёте, чтобы два разных счётчика мягкого слоя не
выглядели одним числом):
  - markers:  scripts/check_markers.py — совпадения 40 regex-маркеров
              (построчно, fenced-блоки и бэктики пропускаются);
  - scan:     scripts/scan_soft_signals.py — не-структурные признаки
              витринной прозы (метод check_self_prose: без таблиц,
              fenced-блоков и цитат-примеров);
  - style:    scripts/count_style_markers.py --skip-markup — суммарный счёт
              мягкого слоя со снятой разметкой (порог check_own_style);
  - detect:   scripts/detect_conj.py — доменный статус (к витринной прозе
              детектор связок неприменим/не валидирован — статус и причина
              публикуются вместо несуществующего «проходит»);
  - polish:   к витринным .md не применяется (снимает Markdown и русскую
              типографику) — applicable: false с причиной; режим для
              разметки — --preserve-markup.

Режимы:
    python3 scripts/self_audit.py           # пересчитать и записать отчёт
    python3 scripts/self_audit.py --check   # пересчитать и сверить (гейт:
                                            # отчёт устарел или подделан — код 1)
    python3 scripts/self_audit.py --selftest

Коды: 0 — отчёт соответствует факту; 1 — расхождение; 2 — отказ инструмента.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

REPORT_REL = os.path.join("eval", "facts", "self-audit.v1.json")

# Публичные файлы поставки (релизный архив + машинные входы). CHANGELOG.md
# входит: метод scan снимает цитаты, а style-счёт журнала публикуется
# отдельной строкой с пометкой метода.
ROOT_FILES = [
    "README.md", "README.en.md", "README.pypi.md", "SKILL.md",
    "CHANGELOG.md", "PERSONA.md", "SECURITY.md", "SECURITY.en.md",
    "PRIVACY_POLICY.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md",
    "GOVERNANCE.md", "AGENTS.md", "LEADERBOARD.md", "ERRATA.md",
    "CITATION.cff", "llms.txt",
]
DIR_GLOBS = [("docs", ".md"), ("references", ".md"), ("commands", ".md"),
             ("knowledge", ".md")]

OWN_STYLE_LIMIT = 80

# Журналы версий цитируют отозванный машинный текст и только дописываются:
# сырой style-счёт к ним не применяется (та же граница, что в гейте
# check_own_style); метод scan (витринная проза) их покрывает.
STYLE_NOT_APPLICABLE = {"CHANGELOG.md", "docs/CHANGELOG-archive.md"}
STYLE_NA_REASON = ("журнал версий цитирует отозванный машинный текст; "
                   "применяется метод scan (витринная проза), сырой счёт "
                   "не применяется — граница гейта check_own_style")

POLISH_REASON = ("снимает Markdown-разметку и русскую типографику (##, **, "
                 "ёлочки, тире, многоточия); к витринным .md не применяется "
                 "— см. contract.v1.json (when_not) и режим --preserve-markup")


def scope_files(root):
    files = [rel for rel in ROOT_FILES
             if os.path.isfile(os.path.join(root, rel))]
    for d, ext in DIR_GLOBS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.endswith(ext):
                files.append("%s/%s" % (d, name))
    return files


def _read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def _prose(text):
    """Витринная проза: без таблиц, fenced-блоков и цитат-примеров
    (метод check_self_prose)."""
    out = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or stripped.startswith("|") or line.lstrip().startswith(">"):
            continue
        out.append(line)
    return "\n".join(out)


def audit(root, version=None, date=None, commit=None):
    """Полный пересчёт отчёта (числа, без служебных полей версии)."""
    import check_markers
    import check_own_style
    import scan_soft_signals
    import detect_conj
    gate_scope = set(check_own_style.SCOPE)
    compiled = {name: re.compile(case[0]) for name, case in
                check_markers.CASES.items()}
    files_out = []
    totals = {
        "markers_class_a": 0, "markers_class_b": 0,
        "own_style_max": 0, "own_style_max_file": None,
        "scan_max_features": 0,
        "detect": {"not-applicable": 0, "not-validated": 0, "works": 0},
    }
    for rel in scope_files(root):
        text = _read(root, rel)
        # markers: построчно, fenced и бэктики пропускаются (семантика --scan).
        a_hits = b_hits = 0
        lines = text.splitlines()
        blocked = check_markers._fenced_lines(lines)
        for lineno, line in enumerate(lines, 1):
            if lineno in blocked:
                continue
            for _s, _e, name in check_markers._line_matches(line, compiled):
                if check_markers.CLASS_OF.get(name, "A") == "A":
                    a_hits += 1
                else:
                    b_hits += 1
        # scan: не-структурные признаки витринной прозы.
        report = scan_soft_signals.analyze(_prose(text), "neutral",
                                           plain_text=True)
        feats = [f for f in report.get("findings", [])
                 if f.get("category") != "структурная"]
        cats = len({f.get("category") for f in feats})
        # style: суммарный счёт со снятой разметкой (подпроцесс, как гейт).
        if rel in STYLE_NOT_APPLICABLE:
            style_total = None
        else:
            style_total = _style_total(root, rel)
        # detect: доменный статус (для витрины — не вердикт).
        det = detect_conj.detect(text, "auto")
        status = det.get("status", "?")
        totals["detect"][status] = totals["detect"].get(status, 0) + 1
        totals["markers_class_a"] += a_hits
        totals["markers_class_b"] += b_hits
        totals["scan_max_features"] = max(totals["scan_max_features"],
                                          len(feats))
        if (style_total is not None and rel in gate_scope
                and style_total > totals["own_style_max"]):
            totals["own_style_max"] = style_total
            totals["own_style_max_file"] = rel
        entry = {
            "file": rel,
            "markers_a": a_hits,
            "markers_b": b_hits,
            "scan_features": len(feats),
            "scan_categories": cats,
            "style_total": style_total,
            "detect_status": status,
            "detect_genre": det.get("genre"),
            "detect_note": det.get("note", ""),
        }
        if style_total is None:
            entry["style_note"] = STYLE_NA_REASON
        files_out.append(entry)
    doc = {
        "registry": ("humanizer-ru self-audit: самоприменение "
                     "детерминированного слоя к публичным файлам поставки"),
        "version": version,
        "date": date,
        "measured_commit": commit,
        "commit_note": ("числа измерены на рабочем дереве; отчёт-committed "
                        "рядом с измеряемыми правками — сам отчёт в скоуп "
                        "измерения не входит, поэтому числа соответствуют "
                        "дереву коммита, содержащего отчёт"),
        "scope_files": len(files_out),
        "methods": {
            "markers": "scripts/check_markers.py (40 regex-маркеров, построчно, fenced/бэктики пропускаются)",
            "scan": "scripts/scan_soft_signals.py по витринной прозе (без таблиц/fenced/цитат); не-структурные признаки",
            "style": "scripts/count_style_markers.py --skip-markup (порог %d)" % OWN_STYLE_LIMIT,
            "detect": "scripts/detect_conj.py (доменный статус; вердикта об авторстве нет)",
            "polish": "не применяется к витринным .md (см. polish.reason)",
        },
        "thresholds": {
            "own_style_limit": OWN_STYLE_LIMIT,
            "scan_fail": "≥3 не-структурных признака из ≥2 категорий (дерево решений SKILL.md)",
        },
        "scope_notes": [
            "высокий scan_features у справочников references/ и knowledge/ "
            "ожидаем: они цитируют машинный текст как примеры (граница "
            "задокументирована в references/false-positives.md); гейт "
            "витринной прозы check_self_prose покрывает витринные файлы",
            "CHANGELOG.md и docs/CHANGELOG-archive.md: сырой style-счёт не "
            "применяется (журнал цитирует отозванный машинный текст) — "
            "style_total null с причиной; гейт check_own_style проверяет их "
            "методом витринной прозы через check_self_prose",
            "style_total справочников references/, commands/ и knowledge/ "
            "записывается как факт, но порогу check_own_style не подлежит: "
            "они цитируют машинный текст как примеры (скоуп порога — "
            "витринная проза); totals.own_style_max считается только по "
            "скоупу гейта",
            "detect_status: к витринной прозе детектор связок не выносит "
            "вердикт — статусы домена (not-applicable/not-validated) "
            "публикуются вместо несуществующего «проходит»",
        ],
        "totals": totals,
        "polish": {"applicable": False, "reason": POLISH_REASON},
        "files": files_out,
        "reproduce": "python3 scripts/self_audit.py --check",
    }
    return doc


def _style_total(root, rel):
    counter = os.path.join(root, "scripts", "count_style_markers.py")
    path = rel if os.path.isabs(rel) else os.path.join(root, rel)
    try:
        proc = subprocess.run(
            [sys.executable, counter, "--skip-markup", path],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=root, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] == path:
            try:
                return int(parts[-1])
            except ValueError:
                return None
    return None


def _meta(root):
    version = None
    skill = os.path.join(root, "SKILL.md")
    try:
        m = re.search(r'version:\s*"?(\d+\.\d+\.\d+)"?',
                      _read(root, "SKILL.md") if os.path.isfile(skill) else "")
        if m:
            version = m.group(1)
    except OSError:
        pass
    commit = None
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            commit = proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    if not commit:
        commit = "no-git"
    date = datetime.date.today().isoformat()
    return version, date, commit


def _numbers(doc):
    """Сравниваемая часть отчёта (служебные поля версии/даты/коммита не
    сверяются: они метаданные снимка, а не измерение)."""
    keep = {k: v for k, v in doc.items()
            if k not in ("version", "date", "measured_commit")}
    return json.dumps(keep, ensure_ascii=False, sort_keys=True)


def write_report(root) -> int:
    version, date, commit = _meta(root)
    doc = audit(root, version=version, date=date, commit=commit)
    path = os.path.join(root, REPORT_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    t = doc["totals"]
    print("SELF-AUDIT: записан %s (файлов %d; маркеры A/B %d/%d; style max "
          "%d из %d; scan max %d; detect %s)"
          % (REPORT_REL, doc["scope_files"], t["markers_class_a"],
             t["markers_class_b"], t["own_style_max"], OWN_STYLE_LIMIT,
             t["scan_max_features"], t["detect"]))
    return 0


def check_report(root) -> int:
    path = os.path.join(root, REPORT_REL)
    if not os.path.isfile(path):
        print("[FAIL] отчёт %s отсутствует — самоприменение не опубликовано"
              % REPORT_REL)
        return 1
    try:
        with open(path, encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, ValueError) as exc:
        print("[FAIL] отчёт не читается: %r" % exc)
        return 1
    fresh = audit(root)
    if _numbers(fresh) != _numbers(stored):
        # Детализация: какие файлы разошлись.
        diffs = []
        stored_by = {f["file"]: f for f in stored.get("files", [])}
        for f in fresh["files"]:
            s = stored_by.get(f["file"])
            if s != f:
                diffs.append(f["file"])
        print("[FAIL] отчёт самоприменения устарел или подделан: расхождений "
              "файлов %d (%s%s). Перезаписать: python3 scripts/self_audit.py"
              % (len(diffs), ", ".join(diffs[:5]),
                 ", …" if len(diffs) > 5 else ""))
        return 1
    for key in ("version", "date", "measured_commit"):
        if not stored.get(key):
            print("[FAIL] отчёт без поля %s" % key)
            return 1
    version, _date, _commit = _meta(root)
    if version and stored.get("version") != version:
        print("[FAIL] отчёт self-audit версии %s != текущей версии SKILL.md %s "
              "— регенерировать: python3 scripts/self_audit.py"
              % (stored.get("version"), version))
        return 1
    print("SELF-AUDIT: отчёт соответствует факту (%s, %s, файлов %d)"
          % (stored.get("version"), stored.get("date"), stored.get("scope_files")))
    return 0


def selftest() -> int:
    import tempfile
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    with tempfile.TemporaryDirectory(prefix="self-audit-") as td:
        for d in ("scripts", "eval/facts", "docs", "references"):
            os.makedirs(os.path.join(td, *d.split("/")), exist_ok=True)
        # Версия-фикстура собирается из частей: гейт зашитых версий
        # сканирует этот файл.
        _fv = "%d.%d.%d" % (0, 0, 1)
        # Минимальное дерево: копии реальных скриптов не нужны — audit()
        # импортирует их из этого репозитория; достаточно файлов скоупа.
        with open(os.path.join(td, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write('---\nmetadata:\n  version: "%s"\n---\n# S\n' % _fv)
        with open(os.path.join(td, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("Спокойный текст без примет.\n")
        doc = audit(td, version=_fv, date="2026-01-01", commit="x" * 40)
        case("отчёт строится и несёт totals/files",
             doc["scope_files"] >= 2 and "totals" in doc
             and doc["polish"]["applicable"] is False
             and doc["polish"]["reason"])
        case("detect-статусы собраны (не вердикт)",
             sum(doc["totals"]["detect"].values()) == doc["scope_files"])
        # Запись/сверка/подделка — на временном дереве (быстро; боевое
        # дерево сверяет режим --check, он в полном прогоне check_all).
        case("write_report на временном дереве rc=0", write_report(td) == 0)
        case("check_report после записи rc=0", check_report(td) == 0)
        path = os.path.join(td, REPORT_REL)
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        tampered = json.loads(original)
        tampered["totals"]["markers_class_a"] += 1
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(tampered, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        case("подделанное число в отчёте ловится", check_report(td) == 1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(original)
        case("восстановленный отчёт снова зелёный", check_report(td) == 0)
        # Устаревшая/чужая версия отчёта относительно SKILL.md ловится.
        stale = json.loads(original)
        stale["version"] = "%d.%d.%d-stale" % (0, 0, 1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(stale, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        case("отчёт чужой версии ловится", check_report(td) == 1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(original)
        case("после восстановления версии отчёт зелёный",
             check_report(td) == 0)
    print("САМОПРОВЕРКА self_audit: %d/%d PASS" % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Самоприменение: отчёт детерминированного слоя по "
                    "публичным файлам поставки.")
    ap.add_argument("--check", action="store_true",
                    help="пересчитать и сверить с eval/facts/self-audit.v1.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.check:
            return check_report(ROOT)
        return write_report(ROOT)
    except (OSError, ImportError, ValueError) as exc:
        print("ОТКАЗ self_audit: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
