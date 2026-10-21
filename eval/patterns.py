#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Free secondary check of a comparison run: for each fixed AI-text pattern, in how many
#          texts it occurs in the source, in how many of those texts each system left it, and how
#          many new occurrences each system introduced. No API calls, no judgment of quality.
# SCOPE: reads eval/corpus/texts and results/<run>/outputs; writes results/<run>/patterns.md.
#        The pattern list is fixed here before the texts of a new set exist (R-PATTERN-COUNT);
#        a surviving pattern can be legitimate (a real contrast, a hedge, a quote), so the table
#        says where to look, it is not a score.
# DEPENDS: Python 3.9+ stdlib; evallib (IO helpers only).
# LINKS: M-EVAL-PATTERNS; R-PATTERN-COUNT; V-M-EVAL-PATTERNS.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# PATTERNS: id -> (regex, source of the pattern).
# survival: sources + outputs -> per pattern and system: source texts, survived, introduced.
# render: survival table -> Markdown.
# main: CLI --run [--set]; prints the table and writes patterns.md.
# END_MODULE_MAP
from __future__ import annotations

import argparse
import re
from typing import Dict

import evallib as lib

# START_BLOCK_PATTERNS
# Sources: SKILL.md sign table (#N) and ru.wikipedia «Признаки сгенерированности текста»
# (revision of 2026-10-08). «В целом», «по состоянию на…», «от X до Y» are left out on
# purpose: they are hedges, dates and real ranges far more often than machine habits.
PATTERNS = {
    "ne_pro": (r"\b[Ээ]то\s+не\s+про\b|\bне\s+про\b[^.!?\n]{0,80}?\bпро\b|\b[Рр]ечь\s+не\s+(?:о|об|про)\b",
               "#2; ВП: параллелизмы"),
    "ne_prosto": (r"\bне\s+просто\b[^.!?\n]{0,80}?,\s*а\b", "#2"),
    "delo_ne_v": (r"\b[Дд]ело\s+не\s+в\b", "#2"),
    "important_to_note": (r"\b(?:[Вв]ажно|[Сс]тоит|[Нн]еобходимо)\s+(?:отметить|подчеркнуть|учитывать)\b", "#1; ВП: дидактические оговорки"),
    "summary_opener": (r"(?m)^\s*(?:В заключение|Подводя итог|Вкратце|Резюмируя|Таким образом)\b", "#9; ВП: раздел-резюме"),
    "despite_challenges": (r"\b[Нн]есмотря на\b[^.!?\n]{0,120}?(?:сталкива|вызов|трудност)", "#9; ВП: проблемы и перспективы"),
    "symbolism": (r"символизир|служит напоминанием|неизгладим|поворотн(?:ый|ым|ого) момент", "#3; ВП: символизм"),
    "gerund_tail": (r",\s+(?:подч[её]ркивая|демонстрируя|отражая|свидетельствуя|способствуя|содействуя)\b", "#6; ВП: поверхностный анализ"),
    "promo_place": (r"в самом сердце|может похвастаться|богат(?:ое|ым|ой)\s+(?:культурн\w+\s+)?наследи|захватывающ", "#3, #18; ВП: рекламный язык"),
    "anonymous_authority": (r"[Ээ]ксперты\s+(?:отмечают|считают|рекомендуют)|[Ии]сследования\s+показывают|[Пп]о словам экспертов", "#7; ВП: обтекаемые формулировки"),
    "calque_greeting": (r"застанет вас|в добром здравии", "#5; ВП: шаблонные письма"),
    "assistant_context": (r"в предоставленн(?:ых|ой)\s+(?:результат|источник|данн)|по имеющейся у меня информации|[Нн]а момент моего (?:обучения|последнего обновления)", "шаг 1; ВП: отказ от ответственности"),
    "assistant_utm": (r"utm_source=(?:chatgpt\.com|openai)\b", "шаг 1; ВП: UTM-метки"),
}
COMPILED = {k: re.compile(rx) for k, (rx, _) in PATTERNS.items()}
# END_BLOCK_PATTERNS


# START_CONTRACT: survival
# PURPOSE: Count, per pattern and system, the source texts that have the pattern, how many of
#          those still have it after the edit, and occurrences the edit added where the source
#          had fewer.
# INPUTS: sources {text_id: str}; outputs {system: {text_id: str}} (missing outputs are skipped).
# OUTPUTS: {pattern: {"in_sources": int, system: {"survived": int, "of": int, "introduced": int}}}.
# SIDE_EFFECTS: none.
# END_CONTRACT: survival
def survival(sources: Dict[str, str], outputs: Dict[str, Dict[str, str]]) -> Dict[str, dict]:
    table: Dict[str, dict] = {}
    for name, rx in COMPILED.items():
        src_counts = {tid: len(rx.findall(text)) for tid, text in sources.items()}
        row: dict = {"in_sources": sum(1 for n in src_counts.values() if n)}
        for system, outs in outputs.items():
            survived = of = introduced = 0
            for tid, out in outs.items():
                if tid not in sources:
                    continue
                n_out = len(rx.findall(out))
                if src_counts[tid]:
                    of += 1
                    survived += 1 if n_out else 0
                introduced += max(0, n_out - src_counts[tid])
            row[system] = {"survived": survived, "of": of, "introduced": introduced}
        table[name] = row
    return table


def render(table: Dict[str, dict], systems: list, run: str) -> str:
    lines = ["# Шаблоны ИИ-текста: %s" % run, "",
             "Ячейка: осталось в правке / было в исходниках, в скобках — сколько добавлено. "
             "Оставшийся шаблон может быть законным (настоящий контраст, цитата), это подсказка, "
             "где смотреть глазами, а не оценка.", "",
             "| Шаблон | Откуда | Текстов с ним | " + " | ".join(systems) + " |",
             "|---|---|---|" + "---|" * len(systems)]
    for name, row in table.items():
        cells = ["%d/%d (+%d)" % (row[s]["survived"], row[s]["of"], row[s]["introduced"]) for s in systems]
        lines.append("| %s | %s | %d | %s |" % (name, PATTERNS[name][1], row["in_sources"], " | ".join(cells)))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    run_dir = lib.EVAL_DIR / "results" / args.run
    out_root = run_dir / "outputs"
    systems = sorted(p.name for p in out_root.iterdir() if p.is_dir())
    outputs = {s: {f.stem: lib.read_text(f) for f in sorted((out_root / s).glob("*.txt"))} for s in systems}
    ids = sorted({tid for outs in outputs.values() for tid in outs})
    sources = {tid: lib.read_text(lib.EVAL_DIR / "corpus" / "texts" / (tid + ".txt")) for tid in ids}
    md = render(survival(sources, outputs), systems, args.run)
    lib.write_text(run_dir / "patterns.md", md)
    print("[M-EVAL-PATTERNS][main] run=%s texts=%d systems=%d -> %s" % (args.run, len(ids), len(systems), run_dir / "patterns.md"))
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
