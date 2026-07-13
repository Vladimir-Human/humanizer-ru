#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка реестра источников для живых образцов маркеров v3.1–v3.2 (issue #18).

Реестр — JSON-файл (по умолчанию research/fixtures/v3.1-v3.2-sources.json) со списком записей:
  case            — ключ из CASES в scripts/check_markers.py (область v3.1–v3.2)
  status          — confirmed | lead | none
  source_url      — публичный URL (для confirmed — обязателен, желателен permalink)
  accessed        — дата обращения YYYY-MM-DD
  platform        — модель/платформа-источник, если установима
  verbatim_sample — дословный фрагмент; для confirmed обязан ловиться regex своего case
  evidence_note   — почему источник доказывает происхождение (а не просто совпадение строки)
  fixture_file    — опционально: путь к сырому файлу-образцу (обязателен для невидимых символов)

Гейт закрытия #18: все 11 ключей покрыты записями со статусом confirmed.
Без флага --allow-pending любой непокрытый ключ даёт код возврата 1.

Запуск:
  python3 scripts/check_fixture_sources.py [путь_к_json] [--allow-pending] [--selftest]
Только стандартная библиотека. Коды возврата: 0 — гейт пройден, 1 — нарушения, 2 — ошибка входа.
"""

import json
import os
import re
import sys

# Точная область issue #18: выражения, добавленные в v3.1–v3.2
# (должны байт-в-байт совпадать с CASES в scripts/check_markers.py).
SCOPE = {
    "utm_copilot": r"[?&]utm_source=copilot\.com",
    "grok_referrer": r"[?&]referrer=grok\.com",
    "grok_render_json": r"grok_render_citation_card_json",
    "grok_card_tag": r"<grok-card\b[^>]*\bcitation_card\b",
    "turn_other": r"turn\d+(?:image|news|video|ref)\d+",
    "attached_web_bracket": r"\[(?:attached_file|web):\d+\]",
    "generated_ref_id": r"citegenerated-reference-identifier",
    "placeholder_url": r"\b(?:INSERT_SOURCE_URL(?:_\d+)?|URL_HERE|PASTE_\w+_URL_HERE)\b",
    "placeholder_date": r"\b\d{4}-(?:\d{2}|[Xx]{2})-[Xx]{2}\b",
    "deepseek_line_ref": "\u3010\\d+\u2020L\\d+(?:-L?\\d+)?\u3011",
    "openai_pua_short": "[\uea01\uea02]",
}

STATUSES = {"confirmed", "lead", "none"}
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RX = re.compile(r"^https?://\S+$")
REQUIRED = ["case", "status", "evidence_note"]
REQUIRED_CONFIRMED = ["source_url", "accessed", "verbatim_sample"]


def validate(entries, base_dir=".", allow_pending=False):
    errors, warnings = [], []
    if not isinstance(entries, list) or not entries:
        return ["реестр должен быть непустым JSON-списком"], []
    confirmed_urls = set()
    covered = set()
    for i, e in enumerate(entries):
        tag = f"запись {i} ({e.get('case', '?')})"
        if not isinstance(e, dict):
            errors.append(f"{tag}: не объект")
            continue
        for f in REQUIRED:
            if not str(e.get(f, "")).strip():
                errors.append(f"{tag}: пустое обязательное поле {f}")
        case = e.get("case")
        if case not in SCOPE:
            errors.append(f"{tag}: case вне области v3.1–v3.2")
            continue
        status = e.get("status")
        if status not in STATUSES:
            errors.append(f"{tag}: недопустимый status {status!r}")
            continue
        if status != "confirmed":
            continue
        for f in REQUIRED_CONFIRMED:
            if not str(e.get(f, "")).strip():
                errors.append(f"{tag}: confirmed без поля {f}")
        url = str(e.get("source_url", ""))
        if url and not URL_RX.match(url):
            errors.append(f"{tag}: некорректный source_url")
        if url:
            if url in confirmed_urls and case != "attached_web_bracket":
                warnings.append(f"{tag}: повторный source_url — проверьте, что это осознанно")
            confirmed_urls.add(url)
        accessed = str(e.get("accessed", ""))
        if accessed and not DATE_RX.match(accessed):
            errors.append(f"{tag}: accessed не в формате YYYY-MM-DD")
        sample = e.get("verbatim_sample", "")
        if sample and not re.search(SCOPE[case], sample):
            errors.append(f"{tag}: verbatim_sample НЕ ловится выражением своего case")
        fixture = e.get("fixture_file")
        if case == "openai_pua_short" and not fixture:
            errors.append(f"{tag}: для невидимых символов обязателен fixture_file с сырым образцом")
        if fixture:
            path = os.path.join(base_dir, fixture)
            if not os.path.isfile(path):
                errors.append(f"{tag}: fixture_file не найден: {fixture}")
            else:
                with open(path, encoding="utf-8") as fh:
                    if not re.search(SCOPE[case], fh.read()):
                        errors.append(f"{tag}: fixture_file не содержит маркер {case}")
        if not errors or all(tag not in x for x in errors):
            covered.add(case)
    missing = sorted(set(SCOPE) - covered)
    if missing:
        msg = "без подтверждённого источника: " + ", ".join(missing)
        (warnings if allow_pending else errors).append(msg)
    return errors, warnings


def run(path, allow_pending):
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Не удалось прочитать {path}: {exc}", file=sys.stderr)
        return 2
    errors, warnings = validate(entries, base_dir=os.path.dirname(path) or ".",
                                allow_pending=allow_pending)
    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[FAIL] {e}")
    confirmed = {x["case"] for x in entries
                 if isinstance(x, dict) and x.get("status") == "confirmed"}
    print(f"Покрыто confirmed: {len(confirmed & set(SCOPE))}/{len(SCOPE)}")
    if errors:
        print("ГЕЙТ #18: НЕ ПРОЙДЕН — закрывать issue нельзя.")
        return 1
    print("ГЕЙТ #18: пройден" + (" (режим --allow-pending, закрытие ещё не разрешено)" if allow_pending and warnings else ""))
    return 0


def selftest():
    ok = [{"case": c, "status": "confirmed", "source_url": f"https://example.org/{c}",
           "accessed": "2026-07-13", "verbatim_sample": s, "evidence_note": "n"}
          for c, s in {
              "utm_copilot": "https://a.b/?utm_source=copilot.com",
              "grok_referrer": "https://a.b/?referrer=grok.com",
              "grok_render_json": '[](grok_render_citation_card_json={"cardIds":["1"]})',
              "grok_card_tag": '<grok-card data-id="1" data-type="citation_card">',
              "turn_other": "turn0image0",
              "attached_web_bracket": "[attached_file:1]",
              "generated_ref_id": "citegenerated-reference-identifier",
              "placeholder_url": "URL_HERE",
              "placeholder_date": "2025-XX-XX",
              "deepseek_line_ref": "\u301085\u2020L261-269\u3011",
              "openai_pua_short": "текст.\uea012\uea02",
          }.items()]
    # PUA-запись требует fixture-файл — в самопроверке отключаем это требование через временный файл.
    import tempfile
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write("известная по ролям.\uea012\uea02\n")
    tmp.close()
    for e in ok:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = os.path.basename(tmp.name)
    base = os.path.dirname(tmp.name)
    checks = []
    err, _ = validate(ok, base_dir=base)
    checks.append(("полный корректный реестр 11/11", not err))
    err, _ = validate(ok[:-1], base_dir=base)
    checks.append(("пропущен case → FAIL", any("без подтверждённого" in x for x in err)))
    _, warn = validate(ok[:-1], base_dir=base, allow_pending=True)
    checks.append(("--allow-pending → WARN вместо FAIL", any("без подтверждённого" in x for x in warn)))
    bad = json.loads(json.dumps(ok)); bad[0]["verbatim_sample"] = "обычный текст"
    err, _ = validate(bad, base_dir=base)
    checks.append(("sample не ловится regex → FAIL", any("НЕ ловится" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[1]["source_url"] = "ftp://x"
    err, _ = validate(bad, base_dir=base)
    checks.append(("некорректный URL → FAIL", any("некорректный source_url" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[2]["accessed"] = "13.07.2026"
    err, _ = validate(bad, base_dir=base)
    checks.append(("дата не ISO → FAIL", any("YYYY-MM-DD" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[3]["case"] = "gemini_cite_start"
    err, _ = validate(bad, base_dir=base)
    checks.append(("case вне области → FAIL", any("вне области" in x for x in err)))
    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            del e["fixture_file"]
    err, _ = validate(bad, base_dir=base)
    checks.append(("PUA без fixture → FAIL", any("fixture_file" in x for x in err)))
    os.unlink(tmp.name)
    fails = [n for n, passed in checks if not passed]
    for n, passed in checks:
        print(("PASS: " if passed else "FAIL: ") + n)
    print(f"САМОПРОВЕРКА: {len(checks) - len(fails)}/{len(checks)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    allow = "--allow-pending" in args
    paths = [a for a in args if not a.startswith("--")]
    sys.exit(run(paths[0] if paths else "research/fixtures/v3.1-v3.2-sources.json", allow))
