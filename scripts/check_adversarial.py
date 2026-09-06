#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_adversarial.py - CI-гейт adversarial-FP корпуса humanizer-ru.

Проверяет:
  1. Каждый файл манифеста существует, читается как UTF-8, его sha256 совпадает.
  2. Regex-слой (check_markers.CASES, классы A/B) не находит ни одного маркера.
  3. Мягкий слой scan_soft_signals.analyze() по жанру, указанному в манифесте,
     даёт не более --max-features признаков на файл (по умолчанию 2);
     при 0-2 признаках дерево решений SKILL.md рекомендует «не править».

Использование:
    python3 scripts/check_adversarial.py
    python3 scripts/check_adversarial.py --json
    python3 scripts/check_adversarial.py --max-features 0
Коды возврата: 0 - гейт пройден, 1 - есть нарушение, 2 - ошибка входа.
"""
import argparse
import hashlib
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

WORD_RX = re.compile(r"[А-Яа-яЁёA-Za-z0-9-]+")
MANIFEST_DEFAULT = "research/validation/adversarial/manifest.v1.json"


def _load_libs(repo):
    scripts_dir = os.path.join(repo, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import scan_soft_signals as sss
        import check_markers as cm
    except Exception as exc:
        print("ОШИБКА ВХОДА: не удалось импортировать детекторы "
              "из %s (%s)" % (scripts_dir, exc), file=sys.stderr)
        return None, None
    return sss, cm


def _word_count(text):
    return len(WORD_RX.findall(text))


def _marker_hits(text, compiled, cm):
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        spans = cm._code_spans(line)
        for name, rx in compiled.items():
            for m in rx.finditer(line):
                if cm._inside_code_span(spans, m.start(), m.end()):
                    continue
                hits.append((lineno, name, line.strip()[:90]))
    return hits

def _check_file(path, expected_sha256, genre, sss, cm, limits):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    problems = []
    if expected_sha256:
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual != expected_sha256:
            problems.append("hash: ожидался %s, получен %s"
                            % (expected_sha256, actual))
    words = _word_count(text)
    if words < limits["min_words"]:
        problems.append("слов %d < %d" % (words, limits["min_words"]))
    if words > limits["max_words"]:
        problems.append("слов %d > %d" % (words, limits["max_words"]))
    compiled = {name: re.compile(case[0]) for name, case in cm.CASES.items()}
    markers = _marker_hits(text, compiled, cm)
    if len(markers) > limits["max_markers"]:
        problems.append("regex-маркеров %d > %d: %s"
                        % (len(markers), limits["max_markers"],
                           [(m[0], m[1]) for m in markers[:5]]))
    if genre not in sss.GENRES:
        problems.append("жанр %r не входит в %s" % (genre, sss.GENRES))
    else:
        report = sss.analyze(text, genre=genre)
        features = report["features_total"]
        cats = report["categories_total"]
        if features > limits["max_features"]:
            problems.append("мягких признаков %d > %d: %s"
                            % (features, limits["max_features"],
                               [(f["id"], f["count"]) for f in report["findings"]]))
        if limits["max_cats"] and cats > limits["max_cats"]:
            problems.append("категорий %d > %d: %s"
                            % (cats, limits["max_cats"], report["categories"]))
    return text, markers, report if genre in sss.GENRES else None, problems

def run(repo, manifest_path, limits, as_json=False):
    repo = os.path.abspath(repo)
    if not os.path.isdir(os.path.join(repo, "scripts")):
        print("ОШИБКА ВХОДА: %s не похож на корень репозитория (нет scripts/)"
              % repo, file=sys.stderr)
        return 2
    sss, cm = _load_libs(repo)
    if sss is None or cm is None:
        return 2
    full_manifest = manifest_path if os.path.isabs(manifest_path) else os.path.join(repo, manifest_path)
    if not os.path.isfile(full_manifest):
        print("ОШИБКА ВХОДА: манифест не найден: %s" % full_manifest,
              file=sys.stderr)
        return 2
    try:
        with open(full_manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
        entries = manifest["corpus"]
    except Exception as exc:
        print("ОШИБКА ВХОДА: не удалось прочитать манифест %s: %s"
              % (full_manifest, exc), file=sys.stderr)
        return 2

    fails = []
    files = []
    total_markers = 0
    total_features = 0
    for i, e in enumerate(entries, 1):
        rel = e.get("path") if isinstance(e, dict) else None
        if not rel:
            fails.append("запись %d: нет path" % i)
            continue
        path = rel if os.path.isabs(rel) else os.path.join(repo, rel)
        if not os.path.isfile(path):
            fails.append("%s: файл не найден" % rel)
            continue
        expected_sha256 = e.get("sha256")
        genre = e.get("genre", "neutral")
        kind = e.get("kind")
        if kind != "human":
            fails.append("%s: kind=%r (корпус принимает только human)"
                         % (rel, kind))
            continue
        text, markers, report, problems = _check_file(
            path, expected_sha256, genre, sss, cm, limits)
        for p in problems:
            fails.append("%s: %s" % (rel, p))
        total_markers += len(markers)
        features = report["features_total"] if report else 0
        cats = report["categories_total"] if report else 0
        total_features += features
        files.append({
            "file": rel,
            "genre": genre,
            "words": _word_count(text),
            "features": features,
            "categories": cats,
            "findings": [(f["id"], f["pattern"], f["count"])
                         for f in (report or {}).get("findings", [])],
            "markers": [(m[0], m[1]) for m in markers],
        })

    if not entries:
        fails.append("манифест пуст")
    if not files and not fails:
        fails.append("в манифесте нет обработанных файлов")

    if not as_json:
        if fails:
            for f in fails:
                print("[FAIL] " + f)
            print("ADVERSARIAL-CORPUS: регрессия - %d проблем." % len(fails))
        else:
            print("ADVERSARIAL-CORPUS: %d файлов, мягких признаков всего %d, "
                  "regex-маркеров %d; гейт пройден (порог soft=%d)."
                  % (len(files), total_features, total_markers,
                     limits["max_features"]))
    if as_json:
        print(json.dumps({
            "repo": repo,
            "manifest": full_manifest,
            "passed": not fails,
            "limits": limits,
            "files": files,
            "fails": fails,
        }, ensure_ascii=False, indent=2))
    return 0 if not fails else 1


def selftest():
    """Самопроверка обвязки гейта на временном репозитории.

    В temp-репозиторий копируются настоящие scan_soft_signals.py и
    check_markers.py из каталога этого скрипта; проверяется контракт гейта
    (hash, словообъём, regex, мягкий порог, коды возврата), а не сами
    детекторы - их самопроверка живёт в собственных скриптах.
    """
    import shutil
    import tempfile
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sss_src = os.path.join(script_dir, "scan_soft_signals.py")
    cm_src = os.path.join(script_dir, "check_markers.py")
    if not (os.path.isfile(sss_src) and os.path.isfile(cm_src)):
        print("ADVERSARIAL-SELFTEST: FAIL (нет соседних scan_soft_signals.py/"
              "check_markers.py)")
        return 1

    tmp = tempfile.mkdtemp(prefix="adv-selftest-")
    repo = os.path.join(tmp, "repo")
    scripts_dir = os.path.join(repo, "scripts")
    corpus_dir = os.path.join(repo, "research", "validation", "adversarial")
    os.makedirs(scripts_dir)
    os.makedirs(corpus_dir)
    shutil.copy(sss_src, os.path.join(scripts_dir, "scan_soft_signals.py"))
    shutil.copy(cm_src, os.path.join(scripts_dir, "check_markers.py"))

    good_text = ("Короткий человеческий текст без маркеров. Автор пишет по делу. "
                 "Здесь нет ни одного машинного оборота из чужого каталога.")
    good_path = os.path.join(corpus_dir, "01-good.txt")
    with open(good_path, "w", encoding="utf-8") as fh:
        fh.write(good_text)
    manifest = {
        "version": 1, "created": "2026-08-21", "description": "selftest",
        "corpus": [{
            "path": "research/validation/adversarial/01-good.txt",
            "kind": "human", "genre": "neutral",
            "sha256": hashlib.sha256(good_text.encode("utf-8")).hexdigest(),
        }],
    }
    manifest_path = os.path.join(corpus_dir, "manifest.v1.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False)

    limits = {"max_features": 2, "max_cats": 0, "min_words": 3,
              "max_words": 400, "max_markers": 0}
    ok = run(repo, "research/validation/adversarial/manifest.v1.json",
             limits) == 0
    with open(good_path, "a", encoding="utf-8") as fh:
        fh.write(" хвост")
    bad = run(repo, "research/validation/adversarial/manifest.v1.json",
              limits) == 1
    print("ADVERSARIAL-SELFTEST: %s" % ("OK" if ok and bad else "FAIL"))
    return 0 if ok and bad else 1
def main(argv=None):
    ap = argparse.ArgumentParser(description="CI-гейт adversarial-FP корпуса")
    ap.add_argument("--manifest", default=MANIFEST_DEFAULT,
                    help="путь к манифесту относительно --repo")
    ap.add_argument("--repo", default=None,
                    help="корень репозитория; по умолчанию - родитель scripts/")
    ap.add_argument("--max-features", type=int, default=2,
                    help="максимум мягких признаков на файл (2)")
    ap.add_argument("--max-cats", type=int, default=0,
                    help="максимум категорий мягких признаков; 0 - выключено")
    ap.add_argument("--min-words", type=int, default=150,
                    help="минимум слов в файле (150)")
    ap.add_argument("--max-words", type=int, default=400,
                    help="максимум слов в файле (400)")
    ap.add_argument("--max-markers", type=int, default=0,
                    help="максимум regex-маркеров на файл (0)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    repo = args.repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    limits = {
        "max_features": args.max_features,
        "max_cats": args.max_cats,
        "min_words": args.min_words,
        "max_words": args.max_words,
        "max_markers": args.max_markers,
    }
    return run(repo, args.manifest, limits, as_json=args.as_json)


if __name__ == "__main__":
    sys.exit(main())
