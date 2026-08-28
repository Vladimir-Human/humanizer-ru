#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_superposition.py — гейт целостности прогонов протокола суперпозиции.

Протокол суперпозиции (research/superposition/QUESTIONS.md) требует, чтобы
каждый прогон-каталог research/superposition/<дата>-<slug>/ был собран до
стандарта: реестр гипотез с полными слотами, предрегистрация с правилом
коллапса старше замерных данных, decision.md с условиями воскрешения
отколлапсированных веток. Гейт делает эти требования механикой:

1. Каталог прогона обязан содержать registry.md, preregistration.md и
   каталог evidence/ (без них суперпозиция не собрана — брак процесса).
2. В registry.md — не менее трёх гипотез (записи «- id: …») и оба
   обязательных слота: H0 («slot: null») и H-инверсия («slot: inversion»).
3. Если есть decision.md (коллапс оформлен):
   - в нём цитируется правило коллапса (раздел «Правило коллапса»);
   - предрегистрация не моложе НИ ОДНОГО замерного файла: mtime
     preregistration.md <= mtime каждого файла, лежащего в evidence/
     НЕПОСРЕДСТВЕННО (анти-HARKing: правило записано до данных; артефакты
     ранних фаз в подкаталогах evidence/ — входы генерации, не замер);
   - есть раздел «Отколлапсированные ветки», и каждый его пункт несёт
     условие воскрешения («воскреш…»/«воскрес…»/«переоткрывать»).
4. Пустой evidence/ при оформленном decision.md — ошибка: коллапс без
   данных не существует (fail-closed).

Гейт проверяет только структуру и хронологию, не содержание решений.

Запуск из корня репозитория:
    python3 scripts/check_superposition.py
    python3 scripts/check_superposition.py --selftest

Код возврата: 0 — все прогоны целостны; 1 — нарушения или провал
самопроверки; 2 — ошибка входа (нет research/superposition). Только
стандартная библиотека.
"""
import argparse
import os
import re
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, "research", "superposition")

HYPOTHESIS_RX = re.compile(r"^- id: \S+", re.M)
SLOT_RX = re.compile(r"^\s+slot: (\S+)", re.M)
RESURRECTION_RX = re.compile(r"воскреш|воскрес|переоткрыв", re.I)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def check_run_dir(run_dir):
    """Возвращает список ошибок одного прогона."""
    errors = []
    rel = os.path.relpath(run_dir, ROOT)
    registry = os.path.join(run_dir, "registry.md")
    prereg = os.path.join(run_dir, "preregistration.md")
    evidence = os.path.join(run_dir, "evidence")
    decision = os.path.join(run_dir, "decision.md")

    if not os.path.isfile(registry):
        errors.append("%s: нет registry.md — суперпозиция не собрана" % rel)
        return errors
    if not os.path.isfile(prereg):
        errors.append("%s: нет preregistration.md — правило коллапса не записано" % rel)
    if not os.path.isdir(evidence):
        errors.append("%s: нет каталога evidence/" % rel)

    text = _read(registry)
    hypotheses = HYPOTHESIS_RX.findall(text)
    if len(hypotheses) < 3:
        errors.append("%s: гипотез в реестре %d (нужно >= 3)"
                      % (rel, len(hypotheses)))
    # Слоты разбираются по записям, не подстрочным поиском: строка слота
    # валидна только внутри записи «- id: …» и только с каноническим
    # значением (null | mechanistic | inversion | out-of-frame).
    slots = SLOT_RX.findall(text)
    if "null" not in slots:
        errors.append("%s: пуст слот H0 (slot: null)" % rel)
    if "inversion" not in slots:
        errors.append("%s: пуст слот H-инверсия (slot: inversion)" % rel)
    if "out-of-frame" not in slots:
        errors.append("%s: пуст слот H-вне рамки (slot: out-of-frame)" % rel)
    if slots.count("mechanistic") < 2:
        errors.append("%s: механистических гипотез %d (нужно >= 2, слот mechanistic)"
                      % (rel, slots.count("mechanistic")))
    unknown = [s for s in slots if s not in ("null", "mechanistic",
                                             "inversion", "out-of-frame")]
    if unknown:
        errors.append("%s: неизвестные слоты в реестре: %s"
                      % (rel, ", ".join(sorted(set(unknown)))))

    if os.path.isfile(decision):
        dec = _read(decision)
        if "Правило коллапса" not in dec:
            errors.append("%s: decision.md не цитирует правило коллапса" % rel)
        if "Отколлапсированные ветки" not in dec:
            errors.append("%s: в decision.md нет раздела «Отколлапсированные ветки»"
                          % rel)
        else:
            section = dec.split("Отколлапсированные ветки", 1)[1]
            # Раздел кончается на следующем заголовке второго уровня.
            section = section.split("\n## ", 1)[0]
            # Буллет — строка «- …» плюс её продолжения (строки с отступом):
            # markdown переносит длинные пункты, условие воскрешения может
            # стоять на строке-продолжении.
            blocks = []
            current = None
            for line in section.splitlines():
                if line.startswith("- "):
                    if current is not None:
                        blocks.append(current)
                    current = line
                elif current is not None and (line.startswith("  ")
                                              or not line.strip()):
                    current += "\n" + line
                elif current is not None:
                    blocks.append(current)
                    current = None
            if current is not None:
                blocks.append(current)
            if not blocks:
                errors.append("%s: раздел «Отколлапсированные ветки» пуст" % rel)
            for block in blocks:
                first_line = block.splitlines()[0]
                if not RESURRECTION_RX.search(block):
                    errors.append(
                        "%s: отколлапсированная ветка без условия воскрешения: %s"
                        % (rel, first_line[:60]))

        # Анти-HARKing: правило не моложе замерных данных.
        if os.path.isdir(evidence):
            data_files = [os.path.join(evidence, name)
                          for name in sorted(os.listdir(evidence))
                          if os.path.isfile(os.path.join(evidence, name))]
            if not data_files:
                errors.append("%s: evidence/ пуст при оформленном decision.md — "
                              "коллапс без данных" % rel)
            elif os.path.isfile(prereg):
                rule_time = os.path.getmtime(prereg)
                for path in data_files:
                    if os.path.getmtime(path) < rule_time:
                        errors.append(
                            "%s: правило коллапса (preregistration.md) моложе "
                            "замерного файла evidence/%s"
                            % (rel, os.path.basename(path)))
    return errors


def check_all():
    if not os.path.isdir(TARGET):
        print("нет каталога %s — прогонов суперпозиции не существует"
              % os.path.relpath(TARGET, ROOT), file=sys.stderr)
        return None
    errors = []
    run_dirs = []
    for name in sorted(os.listdir(TARGET)):
        path = os.path.join(TARGET, name)
        if os.path.isdir(path):
            run_dirs.append(path)
            errors.extend(check_run_dir(path))
    # Каталог прогона без registry.md — брак; каталог вообще без файлов
    # протокола — мусор, тоже ошибка (замеченное должно быть записано).
    for name in sorted(os.listdir(TARGET)):
        path = os.path.join(TARGET, name)
        if os.path.isfile(path) and name != "QUESTIONS.md":
            errors.append("research/superposition/%s: файл вне прогона "
                          "(допустим только QUESTIONS.md)" % name)
    if not run_dirs:
        print("в research/superposition нет каталогов прогонов", file=sys.stderr)
        return None
    return errors


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    def make_run(root, name, hypotheses=5, with_null=True, with_inversion=True,
                 with_out_of_frame=True, with_prereg=True, with_evidence=True,
                 with_decision=False, empty_evidence=False,
                 rule_newer_than_data=False, with_resurrection=True,
                 with_rule_section=True, with_branches_section=True,
                 multiline_bullet=False):
        run = os.path.join(root, name)
        os.makedirs(run, exist_ok=True)
        # `hypotheses` — суммарное число записей «- id:»: сначала H0, затем
        # механистические (минимум 2 в полном наборе), вне-рамочная и
        # инверсия — в конце; счёт записей точный.
        lines = []
        remaining = hypotheses
        if with_null and remaining > 0:
            lines.append("- id: H0")
            lines.append("  slot: null")
            remaining -= 1
        tail = []
        if with_out_of_frame and remaining > 0:
            tail.append("- id: HF")
            tail.append("  slot: out-of-frame")
            remaining -= 1
        if with_inversion and remaining > 0:
            tail.append("- id: HX")
            tail.append("  slot: inversion")
            remaining -= 1
        idx = 1
        while remaining > 0:
            lines.append("- id: H%d" % idx)
            lines.append("  slot: mechanistic")
            idx += 1
            remaining -= 1
        lines.extend(tail)
        with open(os.path.join(run, "registry.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        if with_prereg:
            with open(os.path.join(run, "preregistration.md"), "w",
                      encoding="utf-8") as fh:
                fh.write("# предрегистрация\n\n## Правило коллапса\n\nтекст правила\n")
        if with_evidence:
            os.makedirs(os.path.join(run, "evidence"), exist_ok=True)
            if not empty_evidence:
                with open(os.path.join(run, "evidence", "stats.json"), "w",
                          encoding="utf-8") as fh:
                    fh.write("{}\n")
        if with_decision:
            body = ["# решение"]
            if with_rule_section:
                body.append("## Правило коллапса (дословно)")
                body.append("текст правила")
            if with_branches_section:
                body.append("## Отколлапсированные ветки")
                if with_resurrection and multiline_bullet:
                    # Условие воскрешения на строке-продолжении буллета.
                    body.append("- H0 — убита фальсификатором «другая гипотеза "
                                "даёт recall>0»")
                    body.append("  Воскрешение: новая репликация на другом корпусе")
                elif with_resurrection:
                    body.append("- H0 — убита; воскрешение: новая репликация")
                else:
                    body.append("- H0 — убита фальсификатором")
            with open(os.path.join(run, "decision.md"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(body) + "\n")
        if with_evidence and with_prereg and not empty_evidence:
            ev = os.path.join(run, "evidence", "stats.json")
            if rule_newer_than_data:
                # Данные «старше» правила: правило писалось после замера.
                os.utime(ev, (1000000000, 1000000000))
                os.utime(os.path.join(run, "preregistration.md"),
                         (2000000000, 2000000000))
            else:
                os.utime(os.path.join(run, "preregistration.md"),
                         (1000000000, 1000000000))
                os.utime(ev, (1500000000, 1500000000))
        return run

    import check_superposition as gate

    with tempfile.TemporaryDirectory() as td:
        # Подмена TARGET на временный каталог.
        original = gate.TARGET
        try:
            gate.TARGET = os.path.join(td, "superposition")

            # 1. Валидный прогон без decision (суперпозиция собрана, коллапса нет).
            os.makedirs(gate.TARGET)
            make_run(gate.TARGET, "2026-01-01-ok", with_out_of_frame=True)
            case("валидная суперпозиция без коллапса -> нет ошибок",
                 gate.check_all() == [])

            # 2. Валидный прогон с decision.
            make_run(gate.TARGET, "2026-01-02-ok-decision", with_decision=True,
                     with_out_of_frame=True)
            case("валидный прогон с decision.md -> нет ошибок",
                 gate.check_all() == [])

            # 3. Меньше трёх гипотез.
            make_run(gate.TARGET, "2026-01-03-few", hypotheses=2)
            errs = gate.check_all()
            case("меньше трёх гипотез -> FAIL",
                 any("гипотез" in e and "few" in e for e in errs))

            # 4. Нет слота H0.
            make_run(gate.TARGET, "2026-01-04-noh0", with_null=False)
            case("пустой слот H0 -> FAIL",
                 any("H0" in e and "noh0" in e for e in gate.check_all()))

            # 5. Нет слота H-инверсии.
            make_run(gate.TARGET, "2026-01-05-noinv", with_inversion=False)
            case("пустой слот H-инверсия -> FAIL",
                 any("инверсия" in e and "noinv" in e for e in gate.check_all()))

            # 6. Нет предрегистрации.
            make_run(gate.TARGET, "2026-01-06-noprereg", with_prereg=False,
                     with_decision=True)
            case("нет preregistration.md -> FAIL",
                 any("preregistration" in e and "noprereg" in e
                     for e in gate.check_all()))

            # 7. Правило моложе данных (HARKing).
            make_run(gate.TARGET, "2026-01-07-hark", with_decision=True,
                     rule_newer_than_data=True)
            case("правило коллапса моложе данных -> FAIL",
                 any("моложе" in e and "hark" in e for e in gate.check_all()))

            # 8. Ветка без условия воскрешения.
            make_run(gate.TARGET, "2026-01-08-noresurrect", with_decision=True,
                     with_resurrection=False)
            case("отколлапсированная ветка без воскрешения -> FAIL",
                 any("воскрешения" in e and "noresurrect" in e
                     for e in gate.check_all()))

            # 9. Decision без раздела веток.
            make_run(gate.TARGET, "2026-01-09-nobranches", with_decision=True,
                     with_branches_section=False)
            case("decision.md без раздела «Отколлапсированные ветки» -> FAIL",
                 any("Отколлапсированные" in e and "nobranches" in e
                     for e in gate.check_all()))

            # 10. Чужой файл в корне superposition.
            with open(os.path.join(gate.TARGET, "notes.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write("мусор")
            case("файл вне прогона -> FAIL",
                 any("notes.txt" in e for e in gate.check_all()))
            os.remove(os.path.join(gate.TARGET, "notes.txt"))

            # 10a. Условие воскрешения на строке-продолжении буллета.
            make_run(gate.TARGET, "2026-01-10-multiline", with_decision=True,
                     with_out_of_frame=True, multiline_bullet=True)
            case("условие воскрешения на строке-продолжении -> нет ошибки",
                 not any("multiline" in e for e in gate.check_all()))

            # 12. Нет слота H-вне рамки.
            make_run(gate.TARGET, "2026-01-12-nooof", with_out_of_frame=False)
            case("пустой слот H-вне рамки -> FAIL",
                 any("out-of-frame" in e and "nooof" in e
                     for e in gate.check_all()))

            # 13. Одна механистическая гипотеза.
            make_run(gate.TARGET, "2026-01-13-onemech", hypotheses=3,
                     with_out_of_frame=True)
            case("меньше двух механистических гипотез -> FAIL",
                 any("механистических" in e and "onemech" in e
                     for e in gate.check_all()))

            # 14. Пустой evidence при оформленном decision.
            make_run(gate.TARGET, "2026-01-14-emptyev", with_decision=True,
                     with_out_of_frame=True, empty_evidence=True)
            case("пустой evidence/ при decision.md -> FAIL",
                 any("пуст" in e and "emptyev" in e for e in gate.check_all()))

            # 15. Decision без цитаты правила коллапса.
            make_run(gate.TARGET, "2026-01-15-norule", with_decision=True,
                     with_out_of_frame=True, with_rule_section=False)
            case("decision.md без цитаты «Правило коллапса» -> FAIL",
                 any("правило коллапса" in e and "norule" in e
                     for e in gate.check_all()))

            # 11. Нет TARGET — fail-closed.
            gate.TARGET = os.path.join(td, "нет_такого")
            case("нет research/superposition -> отказ (None)",
                 gate.check_all() is None)
        finally:
            gate.TARGET = original

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Гейт целостности прогонов "
                                             "протокола суперпозиции.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errors = check_all()
    if errors is None:
        return 2
    for err in errors:
        print("FAIL: %s" % err)
    print("СУПЕРПОЗИЦИЯ: %s" % ("целостна" if not errors
                                else "нарушений %d" % len(errors)))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
