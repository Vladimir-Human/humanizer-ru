#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_all.py — весь релизный чек-лист одной командой.

До этого скрипта релизный чек-лист состоял из восьми команд, которые
запускались по памяти; пропуск любой из них CI ловил только после пуша. Здесь
тот же набор гейтов собран в один прогон с итоговой таблицей.

Скрипт честно различает три исхода:
- PASS — гейт прошёл;
- FAIL — гейт упал (итоговый код возврата 1);
- SKIP — гейта нет в этой поставке. Архив скилла не содержит research/,
  tests/ и eval/ (см. check_release.py), поэтому в нём корпусные гейты
  пропускаются с пояснением, а не имитируют успех.

Запуск из корня репозитория:
    python3 scripts/check_all.py            # полный прогон
    python3 scripts/check_all.py --quick    # без перф-гейта, полного eval
                                            # и сборки архива
    python3 scripts/check_all.py --selftest

Код возврата: 0 — ни одного FAIL, 1 — есть FAIL или провал самопроверки,
2 — ошибка запуска. Только стандартная библиотека.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable or "python3"


def _gates(quick, tmpdir):
    """Список гейтов: (метка, argv, обязательные пути, допустимые коды)."""
    # Каноническое имя скилла, а не имя каталога клона: гейт обязан быть
    # зелёным при любом имени каталога (SPEC_MERGED, Н-1). Сверка name из
    # шапки SKILL.md с каноном ловит опечатки в самом имени.
    d = "humanizer-ru"
    zip_path = os.path.join(tmpdir, "humanizer-ru.zip")
    gates = [
        ("spec: самопроверка", [PY, "scripts/check_spec.py", "--selftest"], [], {0}),
        ("spec: SKILL.md строгий", [PY, "scripts/check_spec.py", "SKILL.md",
                                    "--strict", "--expect-dir", d], [], {0}),
        ("budget: самопроверка", [PY, "scripts/check_budget.py", "--selftest"], [], {0}),
        ("budget: лимиты SKILL.md", [PY, "scripts/check_budget.py", "SKILL.md",
                                     "--expect-dir", d], [], {0}),
        ("docs: самопроверка", [PY, "scripts/check_docs.py", "--selftest"], [], {0}),
        ("docs: согласованность", [PY, "scripts/check_docs.py"], [], {0}),
        ("markers: три уровня образцов", [PY, "scripts/check_markers.py"], [], {0}),
        ("markers: паритет md-py", [PY, "scripts/check_markers.py", "--parity"],
         ["references/chatbot-artifacts.md",
          "references/chatbot-artifacts-links.md",
          "references/chatbot-artifacts-markup.md",
          "references/chatbot-artifacts-legacy.md"], {0}),
        ("style: самопроверка", [PY, "scripts/count_style_markers.py", "--selftest"], [], {0}),
        ("style: самопроверка порога", [PY, "scripts/check_own_style.py", "--selftest"], [], {0}),
        ("style: порог на собственные файлы", [PY, "scripts/check_own_style.py"], [], {0}),
        ("self-prose: самопроверка", [PY, "scripts/check_self_prose.py", "--selftest"], [], {0}),
        ("self-prose: витринная проза", [PY, "scripts/check_self_prose.py"], [], {0}),
        ("soft-signals: самопроверка", [PY, "scripts/scan_soft_signals.py", "--selftest"], [], {0}),
        ("confidence: самопроверка", [PY, "scripts/check_confidence.py", "--selftest"], [], {0}),
        ("confidence: сверка лидерборда", [PY, "scripts/check_confidence.py", "--check"],
         ["LEADERBOARD.md", "research/leaderboard"], {0}),
        ("facts: самопроверка", [PY, "scripts/check_facts.py", "--selftest"],
         ["scripts/check_facts.py"], {0}),
        ("facts: реестр и витрина", [PY, "scripts/check_facts.py"],
         ["eval/facts/facts.v1.json"], {0}),
        ("soft: threshold_sweep самопроверка", [PY, "scripts/threshold_sweep.py", "--selftest"], [], {0}),
        ("examples: самопроверка", [PY, "scripts/check_examples.py", "--selftest"], [], {0}),
        ("examples: честность До/После", [PY, "scripts/check_examples.py"], [], {0}),
        ("fp-report: самопроверка", [PY, "scripts/check_fp_report.py",
         "--selftest"], [], {0}),
        ("fp-report: числа отчёта равны снимку", [PY,
         "scripts/check_fp_report.py"], [], {0}),
        ("perf-regex: самопроверка", [PY, "scripts/check_perf_regex.py",
         "--selftest"], [], {0}),
        ("perf-regex: линейность и ReDoS", [PY,
         "scripts/check_perf_regex.py"], [], {0}),
        ("robustness: самопроверка мутаций", [PY,
         "scripts/check_robustness.py", "--selftest"], [], {0}),
        ("docx-evidence: самопроверка", [PY, "tools/docx_evidence.py",
         "--selftest"], [], {0}),
        ("marker-lr: самопроверка", [PY, "scripts/check_marker_lr.py",
         "--selftest"], [], {0}),
        ("marker-lr: числа отчёта равны снимку", [PY,
         "scripts/check_marker_lr.py"], [], {0}),
        ("report: самопроверка отчёта правки", [PY,
         "scripts/check_report.py", "--selftest"], [], {0}),
        ("robustness-v2: самопроверка", [PY,
         "scripts/check_robustness_v2.py", "--selftest"], [], {0}),
        ("robustness-v2: числа отчёта равны снимку", [PY,
         "scripts/check_robustness_v2.py"], [], {0}),
        ("f8-umbrella: самопроверка", [PY,
         "scripts/check_f8_umbrella.py", "--selftest"], [], {0}),
        ("f8-umbrella: числа отчётов равны снимку, П6 в носителях",
         [PY, "scripts/check_f8_umbrella.py"], [], {0}),
        ("positioning-sync: самопроверка", [PY,
         "scripts/check_positioning_sync.py", "--selftest"], [], {0}),
        ("positioning-sync: формулы во всех поверхностях", [PY,
         "scripts/check_positioning_sync.py"], [], {0}),
        ("readme-first-screen: самопроверка", [PY,
         "scripts/check_readme_first_screen.py", "--selftest"], [], {0}),
        ("readme-first-screen: первый экран по схеме", [PY,
         "scripts/check_readme_first_screen.py"], [], {0}),
        ("demo-a11y: самопроверка", [PY,
         "scripts/check_demo_a11y.py", "--selftest"], [], {0}),
        ("demo-a11y: доступность и чистота первого экрана", [PY,
         "scripts/check_demo_a11y.py"], [], {0}),
        ("facts-diff: selftest модуля (F1)", [PY, "scripts/check_facts_diff.py", "--selftest"], [], {0}),
        ("facts-diff: CLI-коды и продукт (F1)", [PY, "scripts/check_facts_diff.py"], [], {0}),
        ("readme-parity: самопроверка", [PY, "scripts/check_readme_parity.py", "--selftest"], [], {0}),
        ("readme-parity: витрина", [PY, "scripts/check_readme_parity.py"],
         ["README.md", "README.en.md"], {0}),
        ("json-output: самопроверка", [PY, "scripts/check_json_output.py",
                                     "--selftest"], [], {0}),
        ("outward: самопроверка", [PY, "scripts/check_outward.py", "--selftest"],
         [], {0}),
        ("fixture-refs: самопроверка", [PY, "scripts/check_fixture_refs.py", "--selftest"],
         [], {0}),
        ("fixture-refs: целостность ссылок", [PY, "scripts/check_fixture_refs.py"],
         [], {0}),
        ("version-literals: самопроверка", [PY, "scripts/check_version_literals.py", "--selftest"],
         [], {0}),
        ("version-literals: зашитые версии", [PY, "scripts/check_version_literals.py"],
         [], {0}),
        ("git-depth: самопроверка", [PY, "scripts/check_git_depth.py", "--selftest"],
         [], {0}),
        ("git-depth: shallow-клон", [PY, "scripts/check_git_depth.py"],
         [], {0}),
        ("superposition: самопроверка", [PY, "scripts/check_superposition.py",
                                        "--selftest"], [], {0}),
        ("superposition: целостность прогонов",
         [PY, "scripts/check_superposition.py"],
         ["research/superposition"], {0}),
        ("action-yaml: самопроверка", [PY, "scripts/check_action_yaml.py",
                                       "--selftest"], [], {0}),
        ("action-yaml: action.yml парсится", [PY, "scripts/check_action_yaml.py"],
         ["action/action.yml"], {0}),
        ("action-fix: самопроверка", [PY, "scripts/action_fix.py",
                                      "--selftest"], [], {0}),
        ("version-sync: самопроверка", [PY, "scripts/check_version_sync.py",
                                        "--selftest"], [], {0}),
        ("version-sync: __version__ == SKILL.md",
         [PY, "scripts/check_version_sync.py"], [], {0}),
        ("skill-reviewed: самопроверка", [PY, "scripts/check_skill_reviewed.py",
                                          "--selftest"], [], {0}),
        ("skill-reviewed: last_reviewed >= коммит",
         [PY, "scripts/check_skill_reviewed.py"],
         ["SKILL.md", "references"], {0}),
        ("json-output: UTF-8 stdout CLI",
         [PY, "scripts/check_json_output.py"], [], {0}),
        ("maps: самопроверка", [PY, "scripts/check_reference_maps.py", "--selftest"], [], {0}),
        ("maps: карты справочников", [PY, "scripts/check_reference_maps.py"], [], {0}),
        ("bundle-sync: самопроверка", [PY, "scripts/check_bundle_sync.py", "--selftest"], [], {0}),
        ("bundle-sync: вендор бандла dsh/", [PY, "scripts/check_bundle_sync.py"],
         ["dsh/package.json", "dsh/cordis.patch.yml"], {0}),
        ("pkg-sync: самопроверка", [PY, "scripts/check_pkg_sync.py", "--selftest"], [], {0}),
        ("pkg-sync: синхронность пакета", [PY, "scripts/check_pkg_sync.py"],
         ["src/humanizer_ru"], {0}),
        ("polish: самопроверка", [PY, "scripts/polish.py", "--selftest"], [], {0}),
        ("polish: инварианты на фикстурах", [PY, "scripts/polish.py", "--gate",
                                             os.path.join("tests", "fixtures", "polish")],
         [os.path.join("tests", "fixtures", "polish")], {0}),
        ("conj: самопроверка", [PY, "scripts/detect_conj.py", "--selftest"], [], {0}),
        ("conj: градуированный ответ", [PY, "scripts/detect_conj.py", "--gate",
                                        os.path.join("tests", "fixtures", "polish")],
         [os.path.join("tests", "fixtures", "polish")], {0}),
        ("selfattack: самопроверка", [PY, "scripts/check_self_attack.py", "--selftest"], [], {0}),
        ("selfattack: полировка не трогает признак", [PY, "scripts/check_self_attack.py"],
         [os.path.join("tests", "fixtures", "polish")], {0}),
        ("contract: самопроверка", [PY, "scripts/check_contract.py", "--selftest"], [], {0}),
        ("contract: машинный интерфейс", [PY, "scripts/check_contract.py"],
         ["contract.v1.json"], {0}),
        ("registry: самопроверка", [PY, "scripts/check_fixture_sources.py", "--selftest"], [], {0}),
        ("registry: реестр доказательств", [PY, "scripts/check_fixture_sources.py",
                                            "research/fixtures/marker-sources.json"],
         ["research/fixtures/marker-sources.json"], {0}),
        ("markers-export: гейт синхронности", [PY, "scripts/check_markers_export.py"],
         ["demo/markers.v1.json"], {0}),
        ("removal-parity: самопроверка", [PY, "scripts/check_removal_parity.py", "--selftest"], [], {0}),
        ("removal-parity: снятие↔детектор", [PY, "scripts/check_removal_parity.py"],
         ["scripts/filemarks/text_layer.py"], {0}),
        ("link-rot: offline формат URL", [PY, "scripts/check_link_rot.py",
                                         "--offline"],
         ["research/fixtures/marker-sources.json"], {0}),
        ("corpus: регрессия корпусов", [PY, "scripts/check_corpus.py"],
         ["research/validation/human"], {0}),
        ("corpus: мягкие сигналы человеческих текстов",
         [PY, "scripts/scan_soft_signals.py", "--max-cats", "1"] + (
             [os.path.join("research", "validation", "human", name)
              for name in sorted(os.listdir(os.path.join(ROOT, "research",
                                                         "validation", "human")))
              if name.endswith(".txt")]
             if os.path.isdir(os.path.join(ROOT, "research", "validation",
                                           "human")) else []),
         ["research/validation/human"], {0}),
        ("adversarial: FP-корпус", [PY, "scripts/check_adversarial.py"],
         ["research"], {0}),
        ("perf: самопроверка", [PY, "scripts/check_perf.py", "--selftest"], [], {0}),
    ]
    if not quick:
        gates.append(("perf: все выражения CASES на 30k", [PY, "scripts/check_perf.py"], [], {0}))
    gates += [
        ("eval: самопроверка гарнесса", [PY, "eval/run_eval.py", "--selftest"],
         ["eval/run_eval.py"], {0}),
    ]
    if not quick:
        gates.append(("eval: manifest.v1.json", [PY, "eval/run_eval.py"],
                      ["eval/run_eval.py", "eval/manifest.v1.json",
                       "research/validation/human"], {0}))
    # blind-eval — самые долгие гейты (~150 с на целостности results):
    # в --quick не входят, быстрый режим обязан оставаться быстрым
    # (обещание AGENTS.md сверяется замером, критерий --quick ≤ 120 с).
    if not quick:
        gates += [
            ("blind-eval: самопроверка", [PY, "eval/blind_eval.py", "--selftest"],
             ["eval/blind_eval.py"], {0}),
            ("blind-eval: целостность results", [PY, "eval/blind_eval.py",
                                                  "--verify-results"],
             ["eval/blind_eval.py", "eval/results", "eval/runs"], {0}),
        ]
    gates += [
        # Без парных прогонов гарнесс обязан отказать кодом 2 (fail-closed);
        # при собранных данных законен и код 0 — оба исхода не ошибка.
        ("blind-eval: отказ без данных", [PY, "eval/blind_eval.py"],
         ["eval/blind_eval.py"], {0, 2}),
        # Детектор-харнес «до/после». В CI — только selftest:
        # реальный прогон требует живого демона Ollama (его в CI нет), поэтому
        # гейт запускает детерминированную самопроверку агрегации и FP-блока.
        ("detect-eval: самопроверка", [PY, "eval/detect_eval.py", "--selftest"],
         ["eval/detect_eval.py"], {0}),
        # REPRODUCE-кит оси «дельта детектируемости»: пересчёт опубликованного
        # числа из открытых данных репо. Самопроверка — негативные кейсы;
        # второй гейт сверяет флагманский отчёт llm_rubric с пересчётом
        # (витринное число = гейт: падает, если число разошлось с данными).
        ("reproduce: самопроверка", [PY, "eval/reproduce.py", "--selftest"],
         ["eval/reproduce.py"], {0}),
        ("reproduce: флагманский отчёт оси", [PY, "eval/reproduce.py"],
         ["eval/reproduce.py",
          "eval/detect-results/2026-08-25-detect-axis-12-glm53.json"], {0}),
        ("reproduce: все отчёты оси", [PY, "eval/reproduce.py", "--all-reports"],
         ["eval/reproduce.py", "eval/detect-results"], {0}),
        ("pages-router: самопроверка",
         [PY, "scripts/check_pages_router.py", "--selftest"],
         ["scripts/check_pages_router.py"], {0}),
        ("demo-parity: самопроверка",
         [PY, "scripts/check_demo_parity.py", "--selftest"],
         ["scripts/check_demo_parity.py"], {0}),
        ("demo-parity: демо и CLI на фикстуре",
         [PY, "scripts/check_demo_parity.py"],
         ["scripts/check_demo_parity.py", "demo/engine.js", "demo/sample.js",
          "demo/markers.js", "tests/fixtures/demo-parity/sample.txt",
          "tests/fixtures/demo-parity/expected.json"], {0}),
        ("polish-modes: самопроверка",
         [PY, "scripts/check_polish_modes.py", "--selftest"],
         ["scripts/check_polish_modes.py"], {0}),
        ("polish-modes: typographic не трогает витрину, strip честен",
         [PY, "scripts/check_polish_modes.py"],
         ["scripts/check_polish_modes.py", "scripts/polish.py", "README.md",
          "SKILL.md", "CONTRIBUTING.md", "llms.txt"], {0}),
        ("compatibility: самопроверка",
         [PY, "scripts/check_compatibility.py", "--selftest"],
         ["scripts/check_compatibility.py"], {0}),
        ("mcp: самопроверка", [PY, "scripts/check_mcp.py", "--selftest"],
         ["scripts/check_mcp.py", "scripts/mcp/humanizer_mcp.py"], {0}),
        ("mcp: conformance-ядро и схемы из контракта",
         [PY, "scripts/check_mcp.py"],
         ["scripts/check_mcp.py", "scripts/mcp/humanizer_mcp.py",
          "contract.v1.json"], {0}),
        ("invisible-removal: самопроверка",
         [PY, "scripts/check_invisible_removal.py", "--selftest"],
         ["scripts/check_invisible_removal.py",
          "scripts/filemarks/text_layer.py"], {0}),
        ("invisible-removal: классификация, фикстуры, реестр, CLI",
         [PY, "scripts/check_invisible_removal.py"],
         ["scripts/check_invisible_removal.py", "markers.v1.json",
          "references/removal-matrix.md"], {0}),
        ("identity: самопроверка",
         [PY, "scripts/check_identity.py", "--selftest"],
         ["scripts/check_identity.py"], {0}),
        ("identity: identity.v1.json синхронен с носителями",
         [PY, "scripts/check_identity.py"],
         ["scripts/check_identity.py", "identity.v1.json", "llms.txt",
          "pyproject.toml"], {0}),
        ("self-audit: самопроверка", [PY, "scripts/self_audit.py", "--selftest"],
         ["scripts/self_audit.py"], {0}),
        ("attribution: самопроверка",
         [PY, "scripts/check_attribution.py", "--selftest"],
         ["scripts/check_attribution.py"], {0}),
        ("attribution: коммиты после якоря и срез GOVERNANCE",
         [PY, "scripts/check_attribution.py"],
         ["scripts/check_attribution.py", "GOVERNANCE.md"], {0}),
        ("triggers: самопроверка", [PY, "eval/run_triggers.py", "--selftest"],
         ["eval/run_triggers.py"], {0}),
        ("triggers: граница активации", [PY, "eval/run_triggers.py"],
         ["eval/run_triggers.py"], {0}),
        ("compile: scripts", [PY, "-m", "compileall", "-q", "scripts"], [], {0}),
        ("release: самопроверка", [PY, "scripts/check_release.py", "--selftest"], [], {0}),
        ("filemarks: самопроверка", [PY, "scripts/filemarks/filemarks.py",
                                          "--selftest"], [], {0}),
        ("rhythm: самопроверка", [PY, "scripts/filemarks/rhythm.py", "--selftest"], [], {0}),
        ("rewrite-text: самопроверка", [PY, "scripts/filemarks/rewrite_text.py", "--selftest"], [], {0}),
        ("rewrite-delta: самопроверка",
         [PY, "scripts/filemarks/check_rewrite_delta.py", "--selftest"], [], {0}),
        ("score-synthid: самопроверка",
         [PY, "scripts/filemarks/score_synthid.py", "--selftest"], [], {0}),
    ]
    if not quick:
        gates += [
            ("release: сборка архива", [PY, "scripts/check_release.py",
                                        "--root", ".", "--build", zip_path], [], {0}),
            ("release: верификация архива", [PY, "scripts/check_release.py",
                                             "--verify", zip_path], [], {0}),
            ("release: контракт выпуска", [PY, "scripts/check_release.py",
                                           "--release-contract"], [], {0}),
            # Сетевой гейт (HEAD ссылок llms.txt): в --quick не входит —
            # быстрый режим не должен зависеть от сети.
            ("pages-router: ссылки llms.txt и состав Pages",
             [PY, "scripts/check_pages_router.py"],
             ["scripts/check_pages_router.py", "llms.txt",
              ".github/workflows/demo-pages.yml", "demo/robots.txt"], {0}),
            # Self-audit — прогон всех инструментов по всем публичным файлам
            # (~30 с): в --quick не входит, быстрый режим остаётся быстрым.
            ("self-audit: отчёт соответствует факту",
             [PY, "scripts/self_audit.py", "--check"],
             ["scripts/self_audit.py", "eval/facts/self-audit.v1.json"], {0}),
            # sdist -> чистое venv -> тесты: требует сеть (pip) и модуль build;
            # отказ среды (код 2) в локальном прогоне законен и печатается,
            # в CI публикации (pypi-publish.yml) гейт обязан дать 0.
            ("release: sdist -> чистое venv -> тесты",
             [PY, "scripts/check_release.py", "--sdist-test"], [], {0, 2}),
            # Compatibility-тест против предыдущей опубликованной версии
            # (PyPI + чистое venv): аддитивность без смены rc и детекции.
            # Отказ среды (нет сети) законен локально; в релизном цикле
            # выполняется до тега.
            ("compatibility: против опубликованной версии",
             [PY, "scripts/check_compatibility.py"],
             ["scripts/check_compatibility.py"], {0, 2}),
        ]
    return gates


def run_gates(gates, root):
    """Выполняет гейты; возвращает (строки отчёта, число FAIL, число SKIP)."""
    rows, fails, skips = [], 0, 0
    for label, argv, needs, ok_codes in gates:
        script = argv[1] if len(argv) > 1 and argv[1].endswith(".py") else None
        missing = [p for p in needs if not os.path.exists(os.path.join(root, p))]
        if script and not os.path.exists(os.path.join(root, script)):
            missing.insert(0, script)
        if missing:
            skips += 1
            rows.append(("SKIP", label, "нет в этой поставке: %s" % ", ".join(missing), 0.0))
            continue
        started = time.time()
        try:
            proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            rows.append(("FAIL", label, "не запустился: %s" % exc, 0.0))
            fails += 1
            continue
        took = time.time() - started
        if proc.returncode in ok_codes:
            rows.append(("PASS", label, "", took))
        else:
            fails += 1
            tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
            detail = "; ".join(tail[-3:]) if tail else "код %d" % proc.returncode
            rows.append(("FAIL", label, "код %d: %s" % (proc.returncode, detail[:220]), took))
    return rows, fails, skips


def render(rows, fails, skips):
    width = max(len(label) for _s, label, _d, _t in rows)
    out = []
    for status, label, detail, took in rows:
        line = "%-4s %-*s %5.1fс" % (status, width, label, took)
        if detail:
            line += "  — " + detail
        out.append(line)
    out.append("ИТОГ: %d гейтов, FAIL: %d, SKIP: %d." % (len(rows), fails, skips))
    return "\n".join(out)


# --------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    ok_gate = ("зелёный гейт", [PY, "-c", "print('ok')"], [], {0})
    bad_gate = ("красный гейт", [PY, "-c", "import sys; sys.exit(3)"], [], {0})
    code2_gate = ("контролируемый отказ", [PY, "-c", "import sys; sys.exit(2)"], [], {0, 2})
    missing_gate = ("гейт без файла", [PY, "scripts/нет_такого_скрипта.py"], [], {0})

    rows, fails, skips = run_gates([ok_gate], ROOT)
    case("зелёный гейт даёт PASS и ноль FAIL", fails == 0 and rows[0][0] == "PASS")

    rows, fails, skips = run_gates([ok_gate, bad_gate], ROOT)
    case("красный гейт даёт FAIL (раннер умеет падать)",
         fails == 1 and rows[1][0] == "FAIL")

    rows, fails, skips = run_gates([code2_gate], ROOT)
    case("допустимый код 2 не считается провалом", fails == 0 and rows[0][0] == "PASS")

    rows, fails, skips = run_gates([missing_gate], ROOT)
    case("отсутствующий скрипт даёт SKIP, а не ложный PASS/FAIL",
         skips == 1 and rows[0][0] == "SKIP" and fails == 0)

    with tempfile.TemporaryDirectory() as td:
        quick = {g[0] for g in _gates(True, td)}
        full = {g[0] for g in _gates(False, td)}
    case("--quick строго уже полного набора", quick < full)

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Все гейты проекта одной командой.")
    ap.add_argument("--quick", action="store_true",
                    help="без перф-гейта, полного eval и сборки архива")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not os.path.isfile(os.path.join(ROOT, "SKILL.md")):
        print("SKILL.md не найден рядом со scripts/ — запуск не из корня скилла",
              file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="humanizer-check-all-") as td:
        rows, fails, skips = run_gates(_gates(args.quick, td), ROOT)
    print(render(rows, fails, skips))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
