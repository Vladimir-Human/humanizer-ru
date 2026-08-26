#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_self_prose.py — гейт «проект применяет правила к самому себе».

Сканирует витринную прозу публичных файлов мягким слоем (scan_soft_signals)
и падает, если в прозе накопились 3+ признаков из 2+ НЕ-структурных
категорий — порог дерева решений SKILL.md («3–5 признаков из двух и более
категорий: выборочная правка»).

Проза = файл без:
  - строк таблиц (|…) — в таблицах живут реестры маркеров и примеры;
  - fenced-блоков — цитаты кода (сканер маскирует их и сам, дублируем явно);
  - строк-цитат (>) — демо-пары «До/После» из check_examples: они обязаны
    содержать слоп и спускаются отдельным гейтом честности примеров.

Структурные оси (#16/#17/#18/ось 4) не считаются: жирный, списки и
чекбоксы — жанр технической инструкции, границы ложных срабатываний
зафиксированы в references/false-positives.md и quantitative-heuristics.md.
Гейт — сигнализация регрессий, а не вердикт о «машинности» собственных
текстов (тот же Главный принцип, что и у самого сканера).

Использование:
    python scripts/check_self_prose.py [--selftest]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

FILES = ["README.md", "README.en.md", "SKILL.md", "LEADERBOARD.md",
         "CHANGELOG.md", "docs/FRAMEWORK.md"]
STRUCTURAL = "структурная"
FAIL_FEATURES = 3
FAIL_CATEGORIES = 2


def prose(text: str) -> str:
    """Витринная проза: без таблиц, fenced-блоков и цитат-примеров."""
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


def _import_scanner():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "scan_soft_signals_gate",
        os.path.join(ROOT, "scripts", "scan_soft_signals.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _non_structural(report):
    findings = [f for f in report.get("findings", [])
                if f.get("category") != STRUCTURAL]
    cats = {}
    for f in findings:
        cats.setdefault(f.get("category"), []).append(f.get("pattern"))
    return len(findings), len(cats), findings


def check_baselines(scanner, files=None):
    """Возвращает список mismatch-строк; пуст — проза в норме."""
    problems = []
    for rel in (files or FILES):
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            problems.append("%s: файл отсутствует" % rel)
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except (OSError, ValueError) as exc:
            problems.append("%s: не читается: %s" % (rel, exc))
            continue
        report = scanner.analyze(prose(text), "neutral", plain_text=True)
        feats, cats, findings = _non_structural(report)
        print("%-22s признаков=%d категорий=%d (не-структурные)"
              % (rel, feats, cats))
        if feats >= FAIL_FEATURES and cats >= FAIL_CATEGORIES:
            for f in findings:
                sample = (f.get("samples") or [{}])[0]
                problems.append("%s: [%s] %s — %s"
                                % (rel, f.get("category"),
                                   f.get("pattern"),
                                   str(sample.get("fragment", ""))[:90]))
    return problems


def selftest():
    import tempfile
    scanner = _import_scanner()
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    clean = ("В поезде я познакомился с лесником, он вёз в Москву бидоны "
             "с мёдом. Разговорились про обход, про осень, про то, что "
             "дороги опять размыло. К утру допили чай и разъехались.\n")
    slop = ("Безусловно, крайне важно раскрыть потенциал синергии. Более того, "
            "в контексте комплексного подхода это по сути главное. Организация "
            "осуществляет деятельность в рамках реализации программы в целях "
            "обеспечения качества. Эксперты считают, что река важна, а "
            "исследователи отмечают её характер. Несмотря на эти трудности, "
            "город продолжает процветать.\n")
    structural = ("## План проверки\n\n- **Шаг первый.** Прочитать вход.\n"
                  "- **Шаг второй.** Сверить факты.\n"
                  "- [x] Готово: отчёт сформирован.\n\n"
                  "Формат отчёта описан ниже.\n")
    table_slop = ("Вводный абзац без примет.\n\n"
                  "| Пример | Откуда |\n|---|---|\n"
                  "| Эксперты считают | регистр #6 |\n"
                  "| безусловно является | регистр #10 |\n\n"
                  "> Эксперты считают, что это безусловно прорыв.\n\n"
                  "Заключительное предложение о погоде сегодня.\n")

    with tempfile.TemporaryDirectory() as td:
        # 1. человечная проза — проходит
        probe = scanner.analyze(prose(clean), "neutral", plain_text=True)
        f1, c1, _ = _non_structural(probe)
        case("живая проза не даёт срабатывания", not (f1 >= FAIL_FEATURES and
                                                       c1 >= FAIL_CATEGORIES))
        # 2. слоп — ловится
        probe = scanner.analyze(prose(slop), "neutral", plain_text=True)
        f2, c2, _ = _non_structural(probe)
        case("инъекция слопа ловится (%d признаков, %d категорий)"
             % (f2, c2), f2 >= FAIL_FEATURES and c2 >= FAIL_CATEGORIES)
        # 3. структурные оси не дают срабатывания
        probe = scanner.analyze(prose(structural), "neutral", plain_text=True)
        f3, c3, _ = _non_structural(probe)
        case("жирный/списки/чекбоксы не считаются (%d/%d)" % (f3, c3),
             not (f3 >= FAIL_FEATURES and c3 >= FAIL_CATEGORIES))
        # 4. табличное и цитатное слоп-содержимое отфильтровано
        probe = scanner.analyze(prose(table_slop), "neutral", plain_text=True)
        f4, c4, _ = _non_structural(probe)
        case("таблицы и демо-цитаты отфильтрованы", f4 == 0)
        # 5. структурный жанр НЕ глушит слоп: жирный/списки + вшитые машинные
        #    обороты всё равно дают пороговое срабатывание.
        masked_slop = structural + "\n" + slop
        probe = scanner.analyze(prose(masked_slop), "neutral", plain_text=True)
        f5, c5, _ = _non_structural(probe)
        case("слоп под структурной формой ловится (%d/%d)" % (f5, c5),
             f5 >= FAIL_FEATURES and c5 >= FAIL_CATEGORIES)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    scanner = _import_scanner()
    problems = check_baselines(scanner)
    if problems:
        for p in problems:
            print("[FAIL] " + p)
        print("ВИТРИННАЯ ПРОЗА: убрать слоп по rewrite-guide.md или "
              "обосновать границу жанра; гейт падать должен.")
        return 1
    print("ВИТРИННАЯ ПРОЗА: пройдена (не-структурных признаков ниже порога).")
    return 0


if __name__ == "__main__":
    sys.exit(main())