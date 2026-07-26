#!/usr/bin/env python3
"""run_eval.py — нейтральный прогон корпуса humanizer-ru-eval.

Любой скилл-кандидат прогоняет manifest.v1.json одной командой.
По умолчанию использует regex из check_markers.py как reference-кандидат;
через --candidate можно подключить внешний runner-скрипт. Протокол runner:
путь к файлу приходит первым аргументом командной строки (argv[1]), а список
совпадений [{line, case}] возвращается в stdout как JSON.

Прогон падает, если файл корпуса пропал, если хеш не сошёлся, если на
человеческом тексте есть совпадения или если запись корпуса не совпала с
объявленным expected_hits.

Запуск:
  python3 eval/run_eval.py
  python3 eval/run_eval.py --candidate /path/to/runner.py
  python3 eval/run_eval.py --selftest

Только стандартная библиотека.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.v1.json")

try:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from check_markers import CASES, _inside_backticks, _console_text
except Exception as exc:  # noqa: BLE001
    print("Не удалось импортировать check_markers: %s" % exc, file=sys.stderr)
    CASES = {}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_default(path, compiled):
    hits = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh.read().splitlines(), 1):
            for name, rx in compiled.items():
                for m in rx.finditer(line):
                    if _inside_backticks(line, m.start(), m.end()):
                        continue
                    hits.append({"line": lineno, "case": name,
                                 "fragment": _console_text(line.strip()[:80])})
    return hits


def _scan_candidate(path, runner):
    proc = subprocess.run([sys.executable, runner, path], capture_output=True, text=True)
    if proc.returncode != 0:
        return [{"error": proc.stderr.strip()[:200]}]
    try:
        data = json.loads(proc.stdout)
        return data if isinstance(data, list) else [{"error": "runner returned non-list"}]
    except json.JSONDecodeError:
        return [{"error": "runner returned non-JSON"}]


def run(manifest_path=MANIFEST, candidate=None, root=ROOT):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    compiled = {name: re.compile(case[0]) for name, case in CASES.items()} if not candidate else None

    summary = {"manifest_version": manifest.get("version", "?"),
               "candidate": "check_markers.py (reference)" if not candidate else candidate,
               "files": 0, "files_missing": 0, "hash_mismatches": 0,
               "human_hits": 0, "ai_hits": 0, "ai_unexpected": 0,
               "boundary_expected_ok": 0,
               "boundary_unexpected": 0, "details": []}

    for entry in manifest["corpus"]:
        rel = entry["path"]
        path = os.path.join(root, rel)
        summary["files"] += 1
        if not os.path.isfile(path):
            # Пропавший файл корпуса — провал прогона, а не примечание в details:
            # иначе удаление всего корпуса давало бы зелёный отчёт.
            summary["files_missing"] += 1
            summary["details"].append({"file": rel, "error": "file missing"})
            continue
        actual = _sha256(path)
        if actual != entry["sha256"]:
            summary["hash_mismatches"] += 1
            summary["details"].append({"file": rel, "error": "hash mismatch",
                                        "expected": entry["sha256"], "actual": actual})
            continue
        if candidate:
            hits = _scan_candidate(path, candidate)
        else:
            hits = _scan_default(path, compiled)
        kind = entry.get("kind")
        expected = entry.get("expected_hits")
        expected_case = entry.get("expected_case")
        actual_names = {h.get("case") for h in hits if "case" in h}
        if kind == "human":
            if hits:
                summary["human_hits"] += len(hits)
                summary["details"].append({"file": rel, "kind": "human",
                                           "hits": hits[:3], "fp": True})
        elif kind == "ai":
            summary["ai_hits"] += len(hits)
            # Если запись объявила ожидание, оно проверяется так же строго,
            # как у boundary: иначе expected_hits в манифесте — мёртвые данные.
            if expected is not None:
                if len(hits) != expected or (expected_case and expected_case not in actual_names):
                    summary["ai_unexpected"] += 1
                    summary["details"].append({"file": rel, "kind": "ai",
                                               "expected": expected, "actual": len(hits),
                                               "cases": sorted(n for n in actual_names if n)})
        elif kind == "boundary":
            if expected is not None:
                if len(hits) == expected and (not expected_case or expected_case in actual_names):
                    summary["boundary_expected_ok"] += 1
                else:
                    summary["boundary_unexpected"] += 1
                    summary["details"].append({"file": rel, "kind": "boundary",
                                               "expected": expected, "actual": len(hits),
                                               "cases": list(actual_names)})
    return summary


def _problems(summary):
    return (summary["files_missing"] + summary["hash_mismatches"] + summary["human_hits"]
            + summary["ai_unexpected"] + summary["boundary_unexpected"])


# ------------------------------------------------------------------ selftest

_SELFTEST_HUMAN = "Обычный человеческий абзац без служебных меток.\n"
# Образец собирается из частей намеренно: в памяти это настоящий маркер,
# в тексте файла — нет, иначе самопроверка репозитория справедливо падает
# на этом файле (тот же приём в eval/blind_eval.py).
_MARKER = "turn" + "0" + "search" + "0"
_SELFTEST_AI = "Ответ модели со следом поиска %s в тексте.\n" % _MARKER
_SELFTEST_BOUNDARY = "Пограничный текст: сочетание Excel и таблиц.\n"


def _selftest_corpus(root):
    """Готовит временный корпус и манифест; возвращает путь к манифесту."""
    files = {"human.txt": _SELFTEST_HUMAN,
             "ai.txt": _SELFTEST_AI,
             "boundary.txt": _SELFTEST_BOUNDARY}
    corpus = []
    for name, body in files.items():
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        entry = {"path": name, "sha256": _sha256(path),
                 "kind": {"human.txt": "human", "ai.txt": "ai",
                          "boundary.txt": "boundary"}[name]}
        if name == "ai.txt":
            entry["expected_hits"] = 1
            entry["expected_case"] = "turn_search"
        if name == "boundary.txt":
            entry["expected_hits"] = 0
        corpus.append(entry)
    manifest_path = os.path.join(root, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"version": "selftest", "corpus": corpus}, fh, ensure_ascii=False)
    return manifest_path


def selftest():
    import shutil
    import tempfile

    cases = []

    def case(name, mutate, expect_key):
        cases.append((name, mutate, expect_key))

    def _drop_file(root):
        os.remove(os.path.join(root, "human.txt"))

    def _tamper(root):
        with open(os.path.join(root, "human.txt"), "a", encoding="utf-8") as fh:
            fh.write("дописанная строка\n")

    def _break_expectation(root):
        # Манифест ждёт одно совпадение, а в файле их два.
        with open(os.path.join(root, "ai.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_SELFTEST_AI)
            fh.write("Ещё одна метка %s во второй строке.\n" % _MARKER)
        manifest_path = os.path.join(root, "manifest.json")
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data["corpus"]:
            if entry["path"] == "ai.txt":
                entry["sha256"] = _sha256(os.path.join(root, "ai.txt"))
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False)

    case("целый корпус -> прогон чистый", lambda r: None, None)
    case("пропал файл корпуса -> провал", _drop_file, "files_missing")
    case("изменены байты файла -> провал", _tamper, "hash_mismatches")
    case("нарушен expected_hits у ai -> провал", _break_expectation, "ai_unexpected")

    passed = 0
    for name, mutate, expect_key in cases:
        root = tempfile.mkdtemp()
        try:
            manifest_path = _selftest_corpus(root)
            mutate(root)
            summary = run(manifest_path, None, root)
            if expect_key is None:
                ok = _problems(summary) == 0
                detail = json.dumps(summary["details"], ensure_ascii=False)
            else:
                ok = summary.get(expect_key, 0) > 0 and _problems(summary) > 0
                detail = "ожидался счётчик %s > 0, получено %r" % (expect_key, summary.get(expect_key))
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if ok:
            print("PASS: %s" % name)
            passed += 1
        else:
            print("FAIL: %s (%s)" % (name, detail))
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, len(cases)))
    return 0 if passed == len(cases) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--candidate", help="внешний runner-скрипт")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    summary = run(args.manifest, args.candidate)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if _problems(summary) else 0


if __name__ == "__main__":
    sys.exit(main())
