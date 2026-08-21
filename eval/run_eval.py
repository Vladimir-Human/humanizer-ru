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
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.v1.json")

try:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from check_markers import CASES, _console_text, _line_matches
except Exception as exc:  # noqa: BLE001
    print("Не удалось импортировать check_markers: %s" % exc, file=sys.stderr)
    CASES = {}

    def _console_text(text, encoding=None):
        return text

    def _line_matches(line, compiled):
        return []


class ManifestError(Exception):
    """Отказ инструмента: манифест недоверенный и нарушил границу репозитория.

    Отличается от обычной регрессии корпуса (пропал файл, разошёлся хеш):
    те копятся в summary и дают код возврата 1, а ManifestError — код 2,
    как отказ инструмента в check_corpus.py и check_fixture_sources.py.
    """


def _safe_path(rel, root):
    """Абсолютный путь к записи корпуса внутри root либо ManifestError.

    Манифест приходит через --candidate/--manifest и по замыслу гарнесса
    может быть сторонним — то есть это недоверенный ввод. Значение entry["path"]
    подставлялось прямо в os.path.join(root, rel), а join молча отбрасывает
    base при абсолютном аргументе (join(root, "/etc/passwd") == "/etc/passwd")
    и не мешает выходу через "..". Запрещаем всё, что уводит за корень:
    абсолютный путь, букву диска Windows, обратный слэш, выход через ".."
    и символическую ссылку, чья цель лежит вне корня.

    Границу проводим по корню репозитория (research/fixtures/*.txt законно
    указывают в ../../tests/fixtures/), а не по каталогу запуска. root задаётся
    от __file__, поэтому не зависит от того, откуда валидатор вызван.
    """
    if not isinstance(rel, str) or not rel.strip():
        raise ManifestError("путь записи корпуса должен быть непустой строкой")
    native = rel.replace("\\", "/")
    if os.path.isabs(rel) or os.path.isabs(native) or re.match(r"^[A-Za-z]:", rel):
        raise ManifestError("путь записи корпуса должен быть относительным, получено: " + rel)
    if "\\" in rel:
        raise ManifestError("обратный слэш в пути записи корпуса запрещён: " + rel)
    root_real = os.path.realpath(root)
    # realpath снимает "." и "..", а также разворачивает символические ссылки,
    # поэтому ссылка на файл вне корня будет поймана этим же сравнением.
    target = os.path.realpath(os.path.join(root_real, rel))
    if target != root_real and not target.startswith(root_real + os.sep):
        raise ManifestError("путь записи корпуса выходит за корень репозитория: " + rel)
    return target


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_default(path, compiled):
    """Скан файла эталонным кандидатом: та же логика, что у --scan.

    Вложенные дубли одного артефакта схлопываются в check_markers.
    _line_matches, поэтому expected_hits манифеста считают артефакты,
    а не число совпавших выражений.
    """
    hits = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh.read().splitlines(), 1):
            for _start, _end, name in _line_matches(line, compiled):
                hits.append({"line": lineno, "case": name,
                             "fragment": _console_text(line.strip()[:80])})
    return hits


def _scan_candidate(path, runner):
    proc = subprocess.run([sys.executable, runner, path], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return [{"error": proc.stderr.strip()[:200]}]
    try:
        data = json.loads(proc.stdout)
        return data if isinstance(data, list) else [{"error": "runner returned non-list"}]
    except json.JSONDecodeError:
        return [{"error": "runner returned non-JSON"}]


def run(manifest_path=MANIFEST, candidate=None, root=ROOT):
    # Манифест приходит из --manifest, то есть от вызывающего. Сбой чтения — это
    # отказ инструмента (код 2), а не регрессия корпуса и не traceback: тот же
    # порядок разделения кодов, что в scripts/check_budget.py.
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except OSError as exc:
        raise ManifestError("не удалось прочитать манифест %s: %s" % (manifest_path, exc))
    except UnicodeDecodeError as exc:
        raise ManifestError("манифест %s не читается как UTF-8: %s" % (manifest_path, exc))
    except json.JSONDecodeError as exc:
        raise ManifestError("манифест %s не является корректным JSON: %s" % (manifest_path, exc))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("corpus"), list):
        raise ManifestError("манифест %s: ожидается объект с полем corpus в виде списка"
                            % manifest_path)
    compiled = {name: re.compile(case[0]) for name, case in CASES.items()} if not candidate else None

    summary = {"manifest_version": manifest.get("version", "?"),
               "candidate": "check_markers.py (reference)" if not candidate else candidate,
               "files": 0, "files_missing": 0, "hash_mismatches": 0,
               "human_hits": 0, "ai_hits": 0, "ai_unexpected": 0,
               "boundary_expected_ok": 0,
               "boundary_unexpected": 0, "details": []}

    for pos, entry in enumerate(manifest["corpus"], 1):
        # Манифест недоверенный целиком, а не только в поле пути: запись может
        # оказаться строкой, а обязательного ключа может не быть. Раньше это
        # давало AttributeError и KeyError наружу, то есть traceback с кодом 1
        # вместо честного отказа инструмента.
        if not isinstance(entry, dict):
            raise ManifestError("запись корпуса %d должна быть объектом, получено: %s"
                                % (pos, type(entry).__name__))
        for field in ("path", "sha256"):
            if not str(entry.get(field, "")).strip():
                raise ManifestError("запись корпуса %d: пустое или отсутствующее поле %s"
                                    % (pos, field))
        rel = entry.get("path")
        # Проверка границы — до любого обращения к файловой системе: недоверенный
        # путь не должен даже проверяться на существование за пределами корня.
        path = _safe_path(rel, root)
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

    # Граница пути: недоверенный манифест не должен читать файлы вне корня.
    # Каждый кейс обязан быть отвергнут ManifestError (отказ инструмента, код 2),
    # а не превратиться в тихий files_missing (регрессия корпуса, код 1).
    passed += _boundary_selftest()

    # Сбой чтения самого манифеста: отказ инструмента, а не traceback.
    input_cases = []
    tmp_input = tempfile.mkdtemp()
    missing = os.path.join(tmp_input, "нет-такого.json")
    input_cases.append(("отсутствующий манифест -> отказ", missing))
    broken = os.path.join(tmp_input, "битый.json")
    with open(broken, "w", encoding="utf-8") as fh:
        fh.write("{не json")
    input_cases.append(("манифест не является JSON -> отказ", broken))
    not_object = os.path.join(tmp_input, "список.json")
    with open(not_object, "w", encoding="utf-8") as fh:
        fh.write("[1, 2, 3]")
    input_cases.append(("манифест без поля corpus -> отказ", not_object))
    for name, path in input_cases:
        try:
            run(path)
            print("FAIL: %s (отказа не было)" % name)
        except ManifestError:
            passed += 1
            print("PASS: %s" % name)
        except Exception as exc:  # noqa: BLE001 — любой иной сбой считаем провалом
            print("FAIL: %s (вместо отказа %s)" % (name, type(exc).__name__))

    total = len(cases) + _BOUNDARY_TOTAL + len(input_cases)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, total))
    return 0 if passed == total else 1


# Кейсы границы пути живут отдельно: их проверка — «поднят ли ManifestError»,
# а не «выставлен ли счётчик summary», как у регрессионных кейсов выше.
_BOUNDARY_TOTAL = 5


def _boundary_selftest():
    """Отрицательные кейсы обхода пути плюс положительный контроль.

    Доказывает, что гейт умеет падать на абсолютном пути, выходе через "..",
    букве диска Windows и символической ссылке за корень — и что нормальный
    относительный манифест по-прежнему проходит. Возвращает число PASS.
    """
    import shutil
    import tempfile

    def _run_probe(root, rel):
        """Собирает манифест на одну запись с путём rel и запускает run()."""
        payload = _SELFTEST_HUMAN
        body = os.path.join(root, "внутри.txt")
        with open(body, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        manifest = {"version": "boundary", "corpus": [
            {"path": rel, "kind": "human", "sha256": _sha256(body)}]}
        manifest_path = os.path.join(root, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(manifest, fh, ensure_ascii=False)
        return run(manifest_path, None, root)

    def _rejected(root, rel):
        try:
            _run_probe(root, rel)
            return False
        except ManifestError:
            return True

    negatives = [
        ("абсолютный путь в манифесте -> ОТКАЗ",
         lambda root: os.path.join(tempfile.gettempdir(), "секрет.txt")),
        ("выход за корень через .. -> ОТКАЗ",
         lambda root: os.path.join("..", "..", "..", "..", "etc", "passwd")),
        ("буква диска Windows -> ОТКАЗ",
         lambda root: "C:\\Windows\\system32\\drivers\\etc\\hosts"),
    ]

    passed = 0
    for name, make_rel in negatives:
        root = tempfile.mkdtemp()
        try:
            ok = _rejected(root, make_rel(root))
        finally:
            shutil.rmtree(root, ignore_errors=True)
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0

    # Символическая ссылка внутри корня, но с целью за его пределами.
    name = "симлинк за пределы корня -> ОТКАЗ"
    root = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    try:
        secret = os.path.join(outside, "секрет.txt")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("данные вне корня\n")
        link = os.path.join(root, "ссылка.txt")
        supported = True
        try:
            os.symlink(secret, link)
        except (OSError, NotImplementedError, AttributeError):
            # Платформа без symlink (например, Windows без прав): кейс не
            # применим, засчитываем как пройденный, чтобы не давать ложный сбой.
            supported = False
        if supported:
            ok = _rejected(root, "ссылка.txt")
        else:
            ok = True
            name += " (симлинки недоступны — кейс пропущен)"
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
    print(("PASS: " if ok else "FAIL: ") + name)
    passed += 1 if ok else 0

    # Положительный контроль: нормальный относительный путь внутри корня.
    name = "нормальный относительный манифест по-прежнему проходит"
    root = tempfile.mkdtemp()
    try:
        summary = _run_probe(root, "внутри.txt")
        ok = summary["files"] == 1 and _problems(summary) == 0
    except ManifestError:
        ok = False
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(("PASS: " if ok else "FAIL: ") + name)
    passed += 1 if ok else 0

    return passed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--candidate", help="внешний runner-скрипт")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        summary = run(args.manifest, args.candidate)
    except ManifestError as exc:
        # Отказ инструмента (код 2) — не регрессия корпуса (код 1).
        print("ОТКАЗ: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if _problems(summary) else 0


if __name__ == "__main__":
    sys.exit(main())
