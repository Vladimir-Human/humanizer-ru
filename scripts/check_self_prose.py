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

# Скоуп объединён с check_own_style.py (приказ владельца 2026-09-03):
# публичные файлы поставки, каждый своим методом. CHANGELOG.md здесь
# проверяется методом витринной прозы (цитаты и таблицы снимаются),
# а не сырым счётом, которым журнал заведомо выше любого порога.
FILES = ["README.md", "README.en.md", "README.pypi.md", "SKILL.md",
         "LEADERBOARD.md", "CHANGELOG.md", "docs/FRAMEWORK.md",
         "PERSONA.md", "CONTRIBUTING.md", "SECURITY.md", "SECURITY.en.md",
         "CODE_OF_CONDUCT.md", "GOVERNANCE.md", "AGENTS.md", "ERRATA.md",
         "PRIVACY_POLICY.md", "llms.txt", "eval/README.md",
         "eval/HOW-TO-RUN.md", "eval/runs/README.md",
         ".github/pull_request_template.md", "docs/INDEX.md",
         "METRICS.md", "RELEASE.md"]
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


REPEAT_RX = None


def _levenshtein(a, b):
    if abs(len(a) - len(b)) > 3:
        return 99
    prev = list(range(len(b) + 1))
    for ia, ca in enumerate(a, 1):
        cur = [ia]
        for ib, cb in enumerate(b, 1):
            cur.append(min(prev[ib] + 1, cur[ib - 1] + 1,
                           prev[ib - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[-1]


def find_repeats(text: str):
    """Повтор соседних лексем: два слова подряд (регистронезависимо) с
    общим началом корня (первые 5 символов) и редакционным расстоянием <=3.
    Ловит «в финальном финальный релизный цикле» и «от записанных —
    записанные числа». Не ловит: пары разных инструментов с общим префиксом
    (humanizer-markers humanizer-report — расстояние больше 3), файловые
    дубли регистра (persona in PERSONA.md), ссылки и бэктики (снимаются до
    токенизации), пары через короткое слово (Claude.ai и Claude Code)."""
    import re
    out = []
    for ln in prose(text).splitlines():
        # содержимое бэктиков, бейджей и URL — не проза: не токенизируется
        ln = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", " ", ln)
        ln = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", ln)
        ln = re.sub(r"\[([^\]]*)\]\([^)]*\)", r" \1 ", ln)
        ln = re.sub(r"`[^`]*`", " ", ln)
        ln = re.sub(r"https?://\S+", " ", ln)
        ln = re.sub(r"\]\([^)]*\)?", " ", ln)
        # токенизация с сохранением коротких слов: они разрывают adjacency;
        # граница предложения или клаузы (. ! ? : ;) пару тоже разрывает:
        # новое предложение легитимно начинается с того же корня
        matches = list(re.finditer(r"[\wёЁ]+(?:-[\wёЁ]+)*", ln))
        for ma, mb in zip(matches, matches[1:]):
            a, b = ma.group(0), mb.group(0)
            gap = ln[ma.end():mb.start()]
            if re.search(r"[.!?::;]", gap):
                continue
            la, lb = a.lower(), b.lower()
            if len(la) < 6 or len(lb) < 6:
                continue
            if any(c.isdigit() for c in la) or any(c.isdigit() for c in lb):
                continue  # даты, версии, числа — легитимные соседи
            if la == lb and a != b:
                continue  # файловый дубликат регистра (persona PERSONA)
            if la[:5] == lb[:5] and _levenshtein(la, lb) <= 3:
                out.append("%s %s" % (a, b))
    return out


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
        if not rel.endswith("CHANGELOG.md"):
            # журнал изменений append-only: исторические секции не
            # переписываются, детектор повторов применяется к текущей витрине
            for rep in find_repeats(text):
                problems.append("%s: повтор соседних лексем: «%s»" % (rel, rep))
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
        # 6. детектор повтора соседних лексем
        case("повтор соседних лексем ловится",
             find_repeats("решение о финальном финальный релизный цикле") != [])
        case("повтор через тире ловится",
             find_repeats("может отличаться от записанных — записанные числа") != [])
        case("живая проза без повторов лексем",
             find_repeats(clean) == [])
        case("пары инструментов с общим префиксом не ловятся",
             find_repeats("команды humanizer-markers humanizer-report работают") == [])
        case("файловый дубль регистра не ловится",
             find_repeats("persona in PERSONA.md описана подробно") == [])
        case("пара через короткое слово не ловится",
             find_repeats("Claude.ai и Claude Code поддерживают скилл") == [])
        case("граница предложения разрывает пару",
             find_repeats("следы в русском тексте. Текстовое ядро исполняет агент") == [])
        case("двоеточие разрывает пару",
             find_repeats("не пересказывать в промпте исполнителя: исполнитель читает сам") == [])
        case("соседние даты и версии не ловятся",
             find_repeats("протокол от 2025-06-18 и протокол от 2025-03-26 рядом") == [])
    rep_wrap = find_repeats("текст в финальном\nфинальный релиз")
    case("перенос строки разрывает пару повтора (граница)", not rep_wrap)
    rep_end = find_repeats("проверка проверочная проверка проверочная")
    case("разные окончания вне расстояния не ловятся",
         not any(a == b for a, b in rep_end))
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