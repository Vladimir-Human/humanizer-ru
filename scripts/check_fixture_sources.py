#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка реестра источников для образцов маркеров (issue #18). Версия 3.

Отличие от версии 1: статуса confirmed недостаточно, чтобы закрыть гейт.
Каждая подтверждённая запись обязана указывать класс доказательства:

  evidence_class:
    primary    - дословный образец находится по source_url в исходном публичном
                 тексте (пост, permalink-ревизия, описание видео). Закрывает гейт.
    secondary  - источник документирует маркер (обзорная страница, каталог
                 паттернов), но не является исходным сгенерированным текстом.
                 Закрывает гейт только с непустым secondary_justification.
    provenance - след говорит о происхождении ссылки, а не о генерации текста
                 (utm-метки, referrer). Закрывает гейт только при
                 fp_caveat_documented: true (оговорка описана в references/false-positives.md).
    synthetic  - образец сконструирован вручную. НИКОГДА не закрывает гейт.

Дополнительно: fixture-файл записи с классом primary не должен содержать
пометку SYNTHETIC.

Запуск:
    python3 scripts/check_fixture_sources.py [путь_к_json] [--allow-pending] [--selftest]
Только стандартная библиотека. Коды возврата: 0 - гейт пройден, 1 - нарушения, 2 - ошибка входа.
"""

import json
import os
import re
import sys

# Реестр охватывает маркеры, которым нужна доказательная цепочка.
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
    "ref_name_search": r"<ref\b[^>]*\bname=[\"']\d+(?:search|fetch|file|image|news|video|ref)\d+[\"']",
}

STATUSES = {"confirmed", "lead", "none"}
EVIDENCE = {"primary", "secondary", "provenance", "synthetic"}
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RX = re.compile(r"^https?://\S+$")
REQUIRED = ["case", "status", "evidence_note"]
REQUIRED_CONFIRMED = ["source_url", "accessed", "verbatim_sample", "evidence_class"]


def validate(entries, base_dir=".", allow_pending=False):
    errors, warnings, covered = [], [], set()
    if not isinstance(entries, list) or not entries:
        return ["реестр должен быть непустым JSON-списком"], [], covered
    confirmed_urls = set()
    for i, e in enumerate(entries):
        tag = "запись %d (%s)" % (i, e.get("case", "?") if isinstance(e, dict) else "?")
        if not isinstance(e, dict):
            errors.append(tag + ": не объект")
            continue
        before = len(errors)
        for f in REQUIRED:
            if not str(e.get(f, "")).strip():
                errors.append(tag + ": пустое обязательное поле " + f)
        case = e.get("case")
        if case not in SCOPE:
            errors.append(tag + ": case вне области реестра")
            continue
        status = e.get("status")
        if status not in STATUSES:
            errors.append("%s: недопустимый status %r" % (tag, status))
            continue
        if status != "confirmed":
            continue
        for f in REQUIRED_CONFIRMED:
            if not str(e.get(f, "")).strip():
                errors.append(tag + ": confirmed без поля " + f)
        ec = e.get("evidence_class")
        if ec is not None and ec not in EVIDENCE:
            errors.append("%s: недопустимый evidence_class %r" % (tag, ec))
            continue
        url = str(e.get("source_url", ""))
        if url and not URL_RX.match(url):
            errors.append(tag + ": некорректный source_url")
        if url:
            if url in confirmed_urls and case != "attached_web_bracket":
                warnings.append(tag + ": повторный source_url - проверьте, что это осознанно")
                if not str(e.get("warning_disposition", "")).strip():
                    errors.append(tag + ": повторный source_url без warning_disposition")
            confirmed_urls.add(url)
        accessed = str(e.get("accessed", ""))
        if accessed and not DATE_RX.match(accessed):
            errors.append(tag + ": accessed не в формате YYYY-MM-DD")
        sample = e.get("verbatim_sample", "")
        if sample and not re.search(SCOPE[case], sample):
            errors.append(tag + ": verbatim_sample НЕ ловится выражением своего case")
        fixture = e.get("fixture_file")
        if case == "openai_pua_short" and not fixture:
            errors.append(tag + ": для невидимых символов обязателен fixture_file с сырым образцом")
        if fixture:
            path = os.path.join(base_dir, fixture)
            if not os.path.isfile(path):
                errors.append(tag + ": fixture_file не найден: " + str(fixture))
            else:
                with open(path, encoding="utf-8") as fh:
                    raw = fh.read()
                if not re.search(SCOPE[case], raw):
                    errors.append(tag + ": fixture_file не содержит маркер " + case)
                if ec == "primary" and "SYNTHETIC" in raw.upper():
                    errors.append(tag + ": fixture помечен SYNTHETIC - не может быть primary")
        closes = False
        if ec == "primary":
            closes = True
        elif ec == "secondary":
            if str(e.get("secondary_justification", "")).strip():
                closes = True
            else:
                errors.append(tag + ": secondary без secondary_justification")
        elif ec == "provenance":
            if e.get("fp_caveat_documented") is True:
                closes = True
            else:
                errors.append(tag + ": provenance без fp_caveat_documented: true")
        elif ec == "synthetic":
            warnings.append(tag + ": synthetic не закрывает гейт - нужен реальный образец")
        if closes and len(errors) == before:
            covered.add(case)
    missing = sorted(set(SCOPE) - covered)
    if missing:
        msg = "гейт не закрыт для: " + ", ".join(missing)
        (warnings if allow_pending else errors).append(msg)
    return errors, warnings, covered


def run(path, allow_pending):
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("Не удалось прочитать %s: %s" % (path, exc), file=sys.stderr)
        return 2
    errors, warnings, covered = validate(
        entries, base_dir=os.path.dirname(path) or ".", allow_pending=allow_pending)
    for w in warnings:
        print("[WARN] " + w)
    for e in errors:
        print("[FAIL] " + e)
    print("Закрывает гейт: %d/%d" % (len(covered), len(SCOPE)))
    if errors:
        print("ГЕЙТ #18: НЕ ПРОЙДЕН - закрывать issue нельзя.")
        return 1
    print("ГЕЙТ #18: пройден" + (
        " (режим --allow-pending, закрытие ещё не разрешено)" if allow_pending and warnings else ""))
    return 0


def _mk(case, sample, ec="primary", **extra):
    e = {"case": case, "status": "confirmed", "evidence_class": ec,
         "source_url": "https://example.org/" + case, "accessed": "2026-07-13",
         "verbatim_sample": sample, "evidence_note": "n"}
    e.update(extra)
    return e


def selftest():
    import tempfile
    samples = {
        "utm_copilot": "https://a.b/?utm_source=copilot.com",
        "grok_referrer": "https://a.b/?referrer=grok.com",
        "grok_render_json": '[](grok_render_citation_card_json={"cardIds":["1"]})',
        "grok_card_tag": '<grok-card data-id="x" data-type="citation_card">',
        "turn_other": "turn0image0",
        "attached_web_bracket": "[attached_file:1]",
        "generated_ref_id": "citegenerated-reference-identifier",
        "placeholder_url": "URL_HERE",
        "placeholder_date": "2025-XX-XX",
        "deepseek_line_ref": "\u301085\u2020L261-269\u3011",
        "openai_pua_short": "текст.\uea012\uea02",
        "ref_name_search": '<ref name="0search12">',
    }
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write("известная по ролям.\uea012\uea02\n")
    tmp.close()
    base = os.path.dirname(tmp.name)
    ok = [_mk(c, s) for c, s in samples.items()]
    for e in ok:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = os.path.basename(tmp.name)
    synth = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    synth.write("# SYNTHETIC FIXTURE\nтекст.\uea012\uea02\n")
    synth.close()
    checks = []
    err, _, cov = validate(ok, base_dir=base)
    checks.append(("полный тестовый реестр закрывает 12/12", not err and len(cov) == 12))
    err, _, _ = validate(ok[:-1], base_dir=base)
    checks.append(("пропущен case -> FAIL", any("гейт не закрыт" in x for x in err)))
    _, warn, _ = validate(ok[:-1], base_dir=base, allow_pending=True)
    checks.append(("--allow-pending -> WARN вместо FAIL", any("гейт не закрыт" in x for x in warn)))
    bad = json.loads(json.dumps(ok)); bad[0]["verbatim_sample"] = "обычный текст"
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("sample не ловится regex -> FAIL", any("НЕ ловится" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[0]["evidence_class"] = "secondary"
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("secondary без обоснования -> FAIL", any("secondary без" in x for x in err)))
    bad[0]["secondary_justification"] = "страница цитирует ревизию X"
    err, _, cov = validate(bad, base_dir=base)
    checks.append(("secondary с обоснованием закрывает", not err and len(cov) == 12))
    bad = json.loads(json.dumps(ok)); bad[1]["evidence_class"] = "provenance"
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("provenance без оговорки -> FAIL", any("provenance без" in x for x in err)))
    bad[1]["fp_caveat_documented"] = True
    err, _, cov = validate(bad, base_dir=base)
    checks.append(("provenance с оговоркой закрывает", not err and len(cov) == 12))
    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["evidence_class"] = "synthetic"
    err, warn, cov = validate(bad, base_dir=base)
    checks.append(("synthetic НЕ закрывает гейт", any("гейт не закрыт" in x for x in err)
                    and any("synthetic" in x for x in warn) and len(cov) == 11))
    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = os.path.basename(synth.name)
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("primary с fixture SYNTHETIC -> FAIL", any("не может быть primary" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[2]["source_url"] = "ftp://x"
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("некорректный URL -> FAIL", any("некорректный source_url" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[3]["accessed"] = "13.07.2026"
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("дата не ISO -> FAIL", any("YYYY-MM-DD" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[1]["source_url"] = bad[0]["source_url"]
    err, _, _ = validate(bad, base_dir=base)
    checks.append(("повтор URL без disposition -> FAIL",
                   any("warning_disposition" in x for x in err)))
    bad[1]["warning_disposition"] = "проверено: общий источник осознан"
    err, warn, cov = validate(bad, base_dir=base)
    checks.append(("повтор URL с disposition закрывает",
                   not err and any("повторный source_url" in x for x in warn) and len(cov) == 12))
    os.unlink(tmp.name); os.unlink(synth.name)
    fails = [n for n, p in checks if not p]
    for n, p in checks:
        print(("PASS: " if p else "FAIL: ") + n)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    allow = "--allow-pending" in args
    paths = [a for a in args if not a.startswith("--")]
    sys.exit(run(paths[0] if paths else "research/fixtures/marker-sources.json", allow))
