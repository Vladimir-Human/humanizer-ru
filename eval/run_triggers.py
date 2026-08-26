#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_triggers.py — детерминированный гейт границы активации скилла.

run_eval.py меряет КАЧЕСТВО очеловечивания; этот харнес следит за границей
АКТИВАЦИИ: на каких запросах humanizer-ru обязан сработать (позитив), а на
каких молчать (near-miss: код с русскими комментариями, английский текст,
юридический документ). Описание фронтматтера SKILL.md перечисляет
фразы-активаторы («очеловечь», «убери гпт-шность», «звучит как нейросеть»,
«проверь на ИИ», «убери штампы», «убери канцелярит», «сделай живым»).

Слой чисто детерминированный, без LLM, ключей и сети — гоняется в CI:

  (а) 10 позитивных кейсов — запросы, чья ключевая фраза-активатор обязана
      присутствовать в description SKILL.md (простое строковое сравнение);
  (б) 8 near-miss — код, английский, юридический документ — не должны
      совпадать ни с одной фразой-активатором, присутствующей в описании;
  (в) гейт падает (exit 1), если хоть одна scope-фраза пропала из description
      (сигнал, что «pushy»-описание размыло границу, либо фразу выпилили);
      если near-miss случайно совпал с фразой-активатором — предупреждение,
      но прогон проходит.

Описание читается живьём из SKILL.md — тест проверяет ТЕКУЩУЮ границу,
а не зашитую копию: так он ловит рассинхрон при редактировании описания.

Кейсы — встроенный список в этом скрипте (не JSON, не отдельный файл).

Запуск:
    python3 eval/run_triggers.py            # режим гейта (гоняется в CI)
    python3 eval/run_triggers.py --selftest # самопроверка, умеет падать

Коды: 0 — граница цела; 1 — провал гейта (пропала scope-фраза) либо провал
самопроверки; 2 — ошибка запуска (нет SKILL.md / нет description).
Только стандартная библиотека.
"""
import argparse
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_MD = os.path.join(ROOT, "SKILL.md")

# Фразы-активаторы, которые описание SKILL.md обязано содержать: они задают
# границу активации скилла. Если любая исчезнет — «pushy»-описание размыло
# границу, и trigger-eval теряет смысл: ловим это в CI, без LLM.
REQUIRED_PHRASES = [
    "очеловечь",
    "убери гпт-шность",
    "звучит как нейросеть",
    "проверь на ИИ",
    "убери штампы",
    "убери канцелярит",
    "сделай живым",
]

# 10 позитивных кейсов: каждый — реалистичный русский запрос, который ДОЛЖЕН
# активировать скилл. Ключевая фраза из description обязана быть в description
# SKILL.md (проверка строковым сравнением, без LLM).
POSITIVE_CASES = [
    {"id": "pos_ochelovech_01", "phrase": "очеловечь",
     "prompt": "Очеловечь этот текст: «Данная статья является комплексным "
               "решением, которое позволяет оптимизировать рабочие процессы.»"},
    {"id": "pos_gptshnost_02", "phrase": "убери гпт-шность",
     "prompt": "Убери гпт-шность из этого абзаца про виртуальные серверы: "
               "«Решение обеспечивает максимальную эффективность и "
               "надёжность инфраструктуры.»"},
    {"id": "pos_neyroset_03", "phrase": "звучит как нейросеть",
     "prompt": "Слишком звучит как нейросеть, перепиши по-человечески: "
               "«Необходимо отметить, что внедрение технологий способствует "
               "достижению поставленных целей.»"},
    {"id": "pos_prover_na_ii_04", "phrase": "проверь на ИИ",
     "prompt": "Проверь на ИИ и очеловечь: «В современном мире важно "
               "понимать, что эффективность является ключевым фактором.»"},
    {"id": "pos_shtampy_05", "phrase": "убери штампы",
     "prompt": "Убери штампы из этого пресс-релиза: «Компания гордится "
               "революционными решениями, открывающими новые горизонты.»"},
    {"id": "pos_kancelyarit_06", "phrase": "убери канцелярит",
     "prompt": "Убери канцелярит: «Осуществление контроля за исполнением "
               "поручений производится в рамках установленного регламента.»"},
    {"id": "pos_zhivym_07", "phrase": "сделай живым",
     "prompt": "Сделай живым этот скучный текст для блога: «Реализация "
               "данного подхода обеспечивает повышение качества.»"},
    {"id": "pos_ochelovech_08", "phrase": "очеловечь",
     "prompt": "Очеловечь и упрости текст письма клиенту, слишком сухо и "
               "казённо: «Уведомляем вас, что услуга будет активирована "
               "в течение пяти рабочих дней.»"},
    {"id": "pos_gptshnost_09", "phrase": "убери гпт-шность",
     "prompt": "Звучит как типичная нейросетка, убери гпт-шность: "
               "«Безусловно, крайне важно раскрыть потенциал синергии.»"},
    {"id": "pos_neyroset_10", "phrase": "звучит как нейросеть",
     "prompt": "Помоги переписать лендинг, он звучит как нейросеть: "
               "«Наш продукт — это не просто инструмент, а целая "
               "экосистема для роста вашего бизнеса.»"},
]

# 8 near-miss кейсов: скилл НЕ должен активироваться. Код на русских
# комментариях, английский текст, юридический документ. Промпты намеренно
# НЕ содержат фраз-активаторов; если какая-то случайно совпадёт — гейт
# предупредит, но не упадёт (forgiving-сторона near-miss).
NEAR_MISS_CASES = [
    {"id": "near_code_ru_01", "note": "код на Python с русским комментарием",
     "prompt": "Помоги разобраться, вот функция на Python с русскими "
               "комментариями:\n```python\n# считаем сумму заказов\ndef "
               "total(orders):\n    return sum(o.price for o in orders)\n```"},
    {"id": "near_code_ru_02", "note": "SQL с русским комментарием",
     "prompt": "Объясни, что делает этот запрос:\n```sql\nSELECT city, count(*) "
               "FROM users WHERE active = 1 GROUP BY city;\n```"},
    {"id": "near_code_ru_03", "note": "bash-скрипт с русским комментарием",
     "prompt": "Вот скрипт для бэкапа, проверь на ошибки:\n```bash\n"
               "# архивируем каталог логов\ntar -czf logs.tar.gz /var/log\n```"},
    {"id": "near_en_01", "note": "английский текст",
     "prompt": "Humanize this text so it doesn't sound like AI: In today's "
               "fast-paced world, cutting-edge solutions drive meaningful "
               "results across the organization."},
    {"id": "near_en_02", "note": "английский текст",
     "prompt": "Rewrite this to sound more natural and less robotic: It is "
               "important to note that effective communication serves as a "
               "key driver of success."},
    {"id": "near_en_03", "note": "английский текст",
     "prompt": "Remove the AI tells from this paragraph: Furthermore, this "
               "comprehensive approach not only enhances efficiency but also "
               "fosters innovation."},
    {"id": "near_legal_01", "note": "юридический документ",
     "prompt": "Составьте договор оказания услуг между ООО «Ромашка» и ИП "
               "Ивановым. Включите порядок расчётов, сроки и ответственность "
               "сторон за нарушение обязательств."},
    {"id": "near_legal_02", "note": "юридический документ",
     "prompt": "Проверьте исковое заявление о взыскании задолженности на "
               "процессуальные ошибки и подготовьте возражения на отзыв "
               "ответчика."},
]


def read_skill_description(skill_md=SKILL_MD):
    """Достаёт поле description из YAML-фронтматтера SKILL.md (живьём)."""
    with open(skill_md, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---"):
        raise ValueError("нет YAML-фронтматтера: %s" % skill_md)
    end = text.find("\n---", 3)
    front = text[3:end] if end != -1 else text
    m = re.search(r'^description:\s*(.+?)\s*$', front, re.MULTILINE)
    if not m:
        raise ValueError("не найдено поле description: %s" % skill_md)
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
        val = val[1:-1]
    return val


def activators_present(description):
    """scope-фразы описания, реально присутствующие в description."""
    return [p for p in REQUIRED_PHRASES if p in description]


def missing_scope_phrases(description):
    """scope-фразы, пропавшие из description (пусто = граница цела)."""
    return [p for p in REQUIRED_PHRASES if p not in description]


def check_positives(description, cases):
    """Позитивные кейсы, чья ключевая фраза пропала из description."""
    return [c for c in cases if c["phrase"] not in description]


def check_near_miss(prompt, activators):
    """Фразы-активаторы, случайно совпавшие с near-miss промптом."""
    return [p for p in activators if p in prompt]


def evaluate(description):
    """Возвращает (results_pos, results_near, warnings, failures).

    results_pos: список (case, present) для позитивных кейсов.
    results_near: список (case, accidental) для near-miss (accidental —
        список совпавших фраз-активаторов; пусто = гейт держит).
    failures: причины падения гейта (пропавшие scope-фразы и позитив-фразы).
    warnings: предупреждения (near-miss случайно совпал) — не роняют гейт.
    """
    activators = activators_present(description)
    results_pos = [(c, c["phrase"] in description) for c in POSITIVE_CASES]
    results_near = [(c, check_near_miss(c["prompt"], activators))
                    for c in NEAR_MISS_CASES]

    failures = []
    missing_scope = missing_scope_phrases(description)
    for p in missing_scope:
        failures.append("scope-фраза пропала из description: «%s»" % p)
    for c, present in results_pos:
        if not present:
            failures.append("позитив-кейс %s: ключевая фраза «%s» не в "
                            "description" % (c["id"], c["phrase"]))

    warnings = []
    for c, matched in results_near:
        if matched:
            warnings.append("near-miss %s (%s) совпал с фразой-активатором: %s"
                            % (c["id"], c["note"], ", ".join(matched)))
    return results_pos, results_near, warnings, failures


def render(description, results_pos, results_near, warnings, failures):
    out = []
    out.append("== Trigger-eval humanizer-ru (граница активации)")
    out.append(" description: %s" % description[:80] + ("…" if len(description) > 80 else ""))
    out.append(" scope-фразы (N=%d):" % len(REQUIRED_PHRASES))
    for p in missing_scope_phrases(description):
        out.append("   [ПРОПАЛА] «%s»" % p)
    out.append(" Позитивных кейсов: %d" % len(results_pos))
    for c, present in results_pos:
        out.append("   %s: фраза «%s» в description — %s"
                   % (c["id"], c["phrase"], "да" if present else "НЕТ"))
    out.append(" Near-miss кейсов: %d" % len(results_near))
    for c, matched in results_near:
        if matched:
            out.append("   %s (%s): СОВПАЛ с фразами: %s"
                       % (c["id"], c["note"], ", ".join(matched)))
        else:
            out.append("   %s (%s): не совпал с фразами-активаторами — ок"
                       % (c["id"], c["note"]))
    for w in warnings:
        out.append(" [предупреждение] %s" % w)
    for f in failures:
        out.append(" [ПРОВАЛ] %s" % f)
    return "\n".join(out)


def selftest():
    """Проверяет, что харнес умеет падать: находит пропавшую scope-фразу
    и случайное совпадение near-miss. Гоняется на синтетических данных,
    SKILL.md не трогает."""
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    # Живое описание содержит все scope-фразы: иначе харнес был бы сломан.
    try:
        desc = read_skill_description()
        case("живое description содержит все scope-фразы",
             missing_scope_phrases(desc) == [])
    except (OSError, ValueError) as exc:
        case("живое description читается (%s)" % exc, False)
        desc = ""

    # Харнес умеет падать: убрали одну scope-фразу — гейт фиксирует провал.
    stripped = desc.replace("очеловечь", "", 1) if desc else ""
    case("харнес ловит пропавшую scope-фразу",
         "очеловечь" in missing_scope_phrases(stripped))

    # Позитив-кейс, чья фраза пропала, помечается как провал.
    case("харнес ловит позитив-кейс без ключевой фразы",
         any(c["id"] == "pos_ochelovech_01" and not c["phrase"] in stripped
             for c in POSITIVE_CASES)
         if stripped else False)

    # Near-miss, содержащий фразу-активатор, даёт предупреждение.
    _results_pos, _results_near, warnings, _failures = evaluate(
        desc or "нет описания")
    fake_near = {"id": "test", "note": "синтетика",
                 "prompt": "Пользователь попросил: «очеловечь это»."}
    matched = check_near_miss(fake_near["prompt"], activators_present(desc or "x"))
    case("харнес предупреждает о совпадении near-miss",
         "очеловечь" in matched and bool(matched))

    # Реальный near-miss-набор не должен случайно совпасть с активаторами.
    accidental = [c["id"] for c, m in _results_near if m]
    case("встроенные near-miss не совпадают с фразами-активаторами",
         accidental == [])

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Trigger-eval humanizer-ru: граница активации скилла "
                    "(детерминированный guard фраз-активаторов)")
    ap.add_argument("--skill", default=SKILL_MD,
                    help="путь к SKILL.md (источник живого description)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        description = read_skill_description(args.skill)
    except (OSError, ValueError) as exc:
        print("ОШИБКА: не прочитать описание скилла: %s" % exc, file=sys.stderr)
        return 2
    results_pos, results_near, warnings, failures = evaluate(description)
    print(render(description, results_pos, results_near, warnings, failures))
    for w in warnings:
        print("ПРЕДУПРЕЖДЕНИЕ: %s" % w, file=sys.stderr)
    if failures:
        for f in failures:
            print("ПРОВАЛ: %s" % f, file=sys.stderr)
        print("Trigger-eval: граница активации размыта.", file=sys.stderr)
        return 1
    print("Trigger-eval: граница активации цела, near-miss держится.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
