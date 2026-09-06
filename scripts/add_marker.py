#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_marker.py — мастер нового regex-маркера: полный конвейер инварианта 3
из одного запуска (приказ 2026-09-05, L6).

Делает: запись в CASES и CLASS_OF (scripts/check_markers.py) + зеркало пакета,
фикстуру tests/fixtures/<id>.txt, секцию в tests/test-fixtures-cases.md,
строку таблицы в references/chatbot-artifacts-*.md, запись в
research/fixtures/marker-sources.json, регенерацию markers.v1.json
(корень, demo, src) и demo/markers.js + sw.js, прогон профильных гейтов.

Запуск:
    python3 scripts/add_marker.py --id мой_маркер --class B \\
        --pattern 'мой\\s+паттерн' --description "Что это" \\
        --source-url https://example.com/page --platform "модель/площадка" \\
        --positive "пример, где срабатывает" \\
        --negative "пример, где молчит" \\
        --multi "два мой паттерн и ещё мой паттерн" --multi-count 2 \\
        [--refs-file references/chatbot-artifacts-links.md] \\
        [--refs-example "мой паттерн"] [--accessed 2026-09-05] [--dry-run]

    python3 scripts/add_marker.py --selftest

--dry-run печатает все правки, ничего не записывая. Граница честности:
мастер не придумывает доказательства — source_url и дословный образец
обязательны и проверяются человеком до запуска.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID_RX = re.compile(r"^[a-z0-9_]{3,40}$")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _write(rel, text):
    assert "\r" not in text, "CRLF запрещён (инвариант 2)"
    with open(os.path.join(ROOT, rel), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(text)


def validate(args, cases):
    errs = []
    if not ID_RX.match(args.id):
        errs.append("id должен соответствовать ^[a-z0-9_]{3,40}$: %r" % args.id)
    if args.id in cases:
        errs.append("id уже есть в CASES: %s" % args.id)
    try:
        rx = re.compile(args.pattern)
    except re.error as exc:
        errs.append("паттерн не компилируется: %s" % exc)
        rx = None
    if rx is not None:
        for s in args.positive:
            if not rx.search(s):
                errs.append("прямой образец не срабатывает: %r" % s)
        for s in args.negative:
            if rx.search(s):
                errs.append("отрицательный образец срабатывает: %r" % s)
        if rx.search(""):
            errs.append("паттерн срабатывает на пустой строке")
        if args.multi:
            got = len(rx.findall(args.multi))
            if got != args.multi_count:
                errs.append("multi: ожидалось %d, найдено %d"
                            % (args.multi_count, got))
    if not args.positive or not args.negative:
        errs.append("нужны минимум один прямой и один отрицательный образец")
    if not re.match(r"^https?://", args.source_url or ""):
        errs.append("source-url обязан быть http(s) ссылкой на живой пример")
    if not args.multi:
        errs.append("граничный (многократный) образец обязателен: --multi")
    return errs


def build_case_entry(args):
    lines = ['    "%s": (' % args.id,
             "        %r," % args.pattern]
    pos = ",\n".join("            %r" % s for s in args.positive)
    neg = ",\n".join("            %r" % s for s in args.negative)
    lines.append("        [\n%s\n        ]," % pos)
    lines.append("        [\n%s\n        ]," % neg)
    lines.append("        (%r, %d)," % (args.multi, args.multi_count))
    lines.append("    ),")
    entry = "\n".join(lines)
    validate_entry(entry)
    return entry


def validate_entry(entry):
    """Сгенерированный фрагмент CASES обязан компилироваться ДО записи в
    дерево (аудит N45): SyntaxError прерывает мастер до любых правок."""
    try:
        compile("CASES = {\n" + entry + "\n}\n", "<add_marker>", "exec")
    except SyntaxError as exc:
        raise SystemExit("Сгенерированный фрагмент CASES не компилируется: "
                         "%s (строка %s); дерево не изменено"
                         % (exc.msg, exc.lineno))


def build_fixtures_section(args):
    rows = ["", "#### Регулярное выражение: `%s`" % args.pattern, "",
            "| Тип | Образец | Ожидание |", "|---|---|---|"]
    for s in args.positive:
        rows.append("| Прямой | `%s` | срабатывает |" % s.replace("`", ""))
    for s in args.negative:
        rows.append("| Отрицательный | `%s` | не срабатывает |" % s.replace("`", ""))
    rows.append("| Граничный | несколько маркеров в одной строке | срабатывает %d раза |"
                % args.multi_count)
    rows.append("")
    return "\n".join(rows)


def build_refs_row(args):
    example = args.refs_example or args.positive[0]
    desc = args.description
    if args.cls == "B":
        desc += " (класс B)"
    return "| `%s` | %s | `%s` |" % (example.replace("`", ""), desc,
                                     args.pattern.replace("`", ""))


def build_registry_record(args, existing_shape_keys):
    rec = {
        "case": args.id,
        "status": "confirmed",
        "evidence_class": "primary",
        "source_url": args.source_url,
        "accessed": args.accessed or datetime.date.today().isoformat(),
        "platform": args.platform,
        "verbatim_sample": args.positive[0],
        "fixture_file": "../../tests/fixtures/%s.txt" % args.id.replace("_", "-"),
        "evidence_note": "Запись создана мастером scripts/add_marker.py; "
                         "образец дословный из источника, проверен человеком "
                         "до запуска мастера.",
    }
    ordered = {k: rec[k] for k in existing_shape_keys if k in rec}
    for k in rec:
        if k not in ordered:
            ordered[k] = rec[k]
    return ordered


def apply_edits(args, dry):
    plan = []
    # 1) CASES + CLASS_OF
    rel = "scripts/check_markers.py"
    t = _read(rel)
    i = t.find("CASES = {")
    assert i != -1
    j = t.find("\n}\n", i)
    assert j != -1
    entry = build_case_entry(args)
    t2 = t[:j] + "\n" + entry + t[j:]
    k = t2.find("CLASS_OF = {")
    assert k != -1
    m = t2.find("\n", k)
    t2 = t2[:m + 1] + '    "%s": "%s",\n' % (args.id, args.cls) + t2[m + 1:]
    plan.append((rel, t2))
    plan.append(("src/humanizer_ru/check_markers.py", t2))  # зеркало (инвариант 1)
    # 2) фикстура
    fx_rel = "tests/fixtures/%s.txt" % args.id.replace("_", "-")
    plan.append((fx_rel, "\n".join(args.positive) + "\n"))
    # 3) секция образцов
    rel = "tests/test-fixtures-cases.md"
    t = _read(rel).rstrip("\n")
    plan.append((rel, t + "\n" + build_fixtures_section(args)))
    # 4) строка references — после последней строки таблицы
    rel = args.refs_file
    t = _read(rel)
    lines = t.split("\n")
    last_row = max(i for i, ln in enumerate(lines) if ln.startswith("|"))
    lines.insert(last_row + 1, build_refs_row(args))
    plan.append((rel, "\n".join(lines)))
    # 5) запись реестра
    rel = "research/fixtures/marker-sources.json"
    reg = json.loads(_read(rel))
    shape = list(reg[0].keys())
    reg.append(build_registry_record(args, shape))
    plan.append((rel, json.dumps(reg, ensure_ascii=False, indent=2) + "\n"))
    if dry:
        for prel, ptext in plan:
            print("--- %s ---" % prel)
            cur = _read(prel) if os.path.isfile(os.path.join(ROOT, prel)) else ""
            added = [ln for ln in ptext.split("\n") if ln not in cur.split("\n")]
            print("\n".join(added[:25]) or "(без новых строк)")
        return 0
    for prel, ptext in plan:
        _write(prel, ptext)
        print("записан %s" % prel)
    # 6) регенерация markers.v1.json и demo: сначала экспорт и копирование
    # реестра в demo/ и src/, затем генерация JS-правил — иначе markers.js
    # соберётся из устаревшей копии demo/markers.v1.json.
    cmd = [sys.executable, "-X", "utf8", "scripts/export_markers.py"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((r.stdout or r.stderr).strip().splitlines()[-1:])
    if r.returncode != 0:
        print("ПРОВАЛ регенерации: %s" % cmd)
        return 1
    shutil.copyfile(os.path.join(ROOT, "markers.v1.json"),
                    os.path.join(ROOT, "demo", "markers.v1.json"))
    shutil.copyfile(os.path.join(ROOT, "markers.v1.json"),
                    os.path.join(ROOT, "src", "humanizer_ru", "markers.v1.json"))
    print("markers.v1.json скопирован в demo/ и src/")
    r = subprocess.run([sys.executable, "-X", "utf8",
                        "demo/generate_js_rules.py"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print((r.stdout or r.stderr).strip().splitlines()[-1:])
    if r.returncode != 0:
        print("ПРОВАЛ регенерации demo/markers.js")
        return 1
    # 7) профильные гейты
    fails = 0
    for gate in ([sys.executable, "scripts/check_markers.py"],
                 [sys.executable, "scripts/check_markers.py", "--parity"],
                 [sys.executable, "scripts/check_fixture_sources.py"],
                 [sys.executable, "scripts/check_markers_export.py"],
                 [sys.executable, "scripts/check_pkg_sync.py"]):
        r = subprocess.run(gate, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        status = "OK" if r.returncode == 0 else "ПРОВАЛ"
        print("%s: %s" % (status, " ".join(gate[1:])))
        fails += 0 if r.returncode == 0 else 1
    if fails:
        print("Гейты не зелёные — откатите правку (git checkout -- .) и "
              "исправьте входные данные мастера.")
        return 1
    print("ГОТОВО: маркер %s добавлен полным конвейером. Следующие шаги: "
          "python scripts/check_all.py --quick, тесты, коммит." % args.id)
    return 0


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from check_markers import CASES
    ns = argparse.Namespace(
        id="zz_probe", cls="A", pattern=r"zz\\s+probe", description="проба",
        source_url="https://example.org/x", platform="проба",
        positive=["zz  probe здесь"], negative=["обычная строка"],
        multi="zz probe и zz probe", multi_count=2,
        refs_file="references/chatbot-artifacts-links.md",
        refs_example=None, accessed="2026-09-05")
    ns.pattern = r"zz\s+probe"
    case("валидный набор проходит валидацию", validate(ns, CASES) == [])
    bad = argparse.Namespace(**dict(vars(ns), id="contentReference"))
    case("дубликат id отклоняется", validate(bad, CASES) != [])
    bad = argparse.Namespace(**dict(vars(ns), positive=["не то"]))
    case("несрабатывающий прямой образец отклоняется",
         validate(bad, CASES) != [])
    bad = argparse.Namespace(**dict(vars(ns), negative=["zz probe"]))
    case("срабатывающий отрицательный образец отклоняется",
         validate(bad, CASES) != [])
    bad = argparse.Namespace(**dict(vars(ns), multi_count=3))
    case("неверный счёт multi отклоняется", validate(bad, CASES) != [])
    bad = argparse.Namespace(**dict(vars(ns), source_url="ftp://x"))
    case("не-http источник отклоняется", validate(bad, CASES) != [])
    entry = build_case_entry(ns)
    case("запись CASES: кортеж без r-префикса (удвоения слэшей нет)",
         ("r'zz" not in entry) and (", 2)," in entry))
    row = build_refs_row(argparse.Namespace(**dict(vars(ns), cls="B")))
    case("строка references для класса B несёт пометку", "(класс B)" in row)
    import types
    ns = types.SimpleNamespace(
        id="zz_multi2", pattern=r"zz\s+multi", description="описание",
        positive=["zz multi раз", "ещё zz multi два"],
        negative=["обычный текст один", "обычный текст два"],
        multi="zz multi и ещё zz multi", multi_count=2)
    entry = build_case_entry(ns)
    try:
        compile("CASES = {\n" + entry + "\n}\n", "<selftest>", "exec")
        ok_multi = True
    except SyntaxError:
        ok_multi = False
    case("несколько positive/negative дают компилируемый CASES", ok_multi)
    try:
        validate_entry("    \"zz\": (\n        'x',,\n    ),")
        ok_bad = False
    except SystemExit:
        ok_bad = True
    case("валидатор прерывает мастер на битом фрагменте", ok_bad)
    print("САМОПРОВЕРКА add_marker: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--id")
    ap.add_argument("--class", dest="cls", choices=("A", "B"))
    ap.add_argument("--pattern")
    ap.add_argument("--description")
    ap.add_argument("--source-url")
    ap.add_argument("--platform")
    ap.add_argument("--positive", action="append", default=[])
    ap.add_argument("--negative", action="append", default=[])
    ap.add_argument("--multi")
    ap.add_argument("--multi-count", type=int, default=0)
    ap.add_argument("--refs-file",
                    default="references/chatbot-artifacts-links.md")
    ap.add_argument("--refs-example")
    ap.add_argument("--accessed")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    missing = [f for f in ("id", "cls", "pattern", "description",
                           "source_url", "platform")
               if not getattr(args, f)]
    if missing:
        ap.error("не заданы: %s" % ", ".join("--" + m.replace("_", "-")
                                             for m in missing))
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from check_markers import CASES
    errs = validate(args, CASES)
    if errs:
        for e in errs:
            print("[FAIL] %s" % e)
        return 1
    return apply_edits(args, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
