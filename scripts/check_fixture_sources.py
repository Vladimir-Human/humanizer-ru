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

import io
import json
import os
import re
import sys

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

# Импортируем CASES из check_markers.py, чтобы гейт автоматически ловил
# новые маркеры, не добавленные в реестр (новый case обязан попасть в SCOPE).
try:
    from check_markers import CASES as _MARKER_CASES
except Exception:  # noqa: BLE001 — fallback, если запуск из другого каталога
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from check_markers import CASES as _MARKER_CASES
    except Exception as exc:  # noqa: BLE001
        print("Не удалось импортировать CASES из check_markers.py: %s" % exc, file=sys.stderr)
        _MARKER_CASES = {}

# Реестр охватывает маркеры, которым нужна доказательная цепочка.
# Всякий case из check_markers.CASES обязан быть либо в REGISTERED_CASES
# (требует записи в реестре), либо автоматически попадает в LEGACY_EXEMPT
# (проверяется только fixtures). Иначе гейт падает — это защищает от
# добавления regex без evidence chain.
REGISTERED_CASES = {
    "utm_copilot", "grok_referrer", "grok_render_json", "grok_card_tag",
    "turn_other", "attached_web_bracket", "generated_ref_id",
    "placeholder_url", "placeholder_date", "deepseek_line_ref",
    "openai_pua_short", "ref_name_search", "gemini_span", "perplexity_s3",
    "gemini_cite_n", "source_plus_chain", "oai_citation", "writing_block",
    "attributableIndex", "oaicite_short", "contentReference", "openai_pua",
    "turn_search", "utm_chatgpt", "zero_width", "citation_n",
}
SCOPE = {name: _MARKER_CASES[name][0] for name in REGISTERED_CASES if name in _MARKER_CASES}

# CASES без записи в реестре: проверяются только fixtures в check_markers.py.
# Список зафиксирован явно и только сокращается: новый маркер физически не
# может попасть в legacy без ручного редактирования этого списка в отдельном
# коммите. До v3.6.0 список выводился как CASES - SCOPE, из-за чего проверка
# orphan была тавтологией и не могла упасть ни при каких условиях.
LEGACY_EXEMPT = {
    "assistants_source", "attached_file", "cite_turn",
    "copilot_caret", "gemini_cite_start", "grok_card",
    "sandbox_link",
    "think_tag", "turn_fetch", "turn_file", "utm_openai",
    "vertexaisearch",
}

STATUSES = {"confirmed", "lead", "none"}
EVIDENCE = {"primary", "secondary", "provenance", "synthetic"}
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RX = re.compile(r"^https?://\S+$")
REQUIRED = ["case", "status", "evidence_note"]
REQUIRED_CONFIRMED = ["source_url", "accessed", "verbatim_sample", "evidence_class"]

# Признаки immutable-источника: permalink на конкретную ревизию/коммит/diff.
IMMUTABLE_MARKERS = ("oldid=", "diff=", "/commit/", "/blob/", "/releases/tag/",
                    "Special:Permalink", "Special:Diff", "youtube.com/watch",
                    "binance.com/en/square/post")


def _is_immutable(url: str) -> bool:
    return any(m in url for m in IMMUTABLE_MARKERS)


# Корень репозитория: каталог выше scripts/. Считается от файла, а не от cwd,
# чтобы граница не зависела от того, откуда запущен валидатор.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reject_path(fixture, base_dir, repo_root=None):
    """Причина отказа для fixture_file или пустая строка, если путь допустим.

    Реестр — данные, а не код: значение fixture_file подставлялось прямо в
    os.path.join, и абсолютный путь молча отбрасывал base_dir (join(base,
    "/etc/passwd") == "/etc/passwd"). Запрещаем абсолютные пути и выход за
    корень репозитория; легитимные «../../tests/fixtures/*.txt» остаются.
    """
    if not isinstance(fixture, str) or not fixture.strip():
        return "fixture_file должен быть непустой строкой"
    if fixture != fixture.strip():
        return "fixture_file не должен начинаться или заканчиваться пробелом"
    native = fixture.replace("\\", "/")
    if os.path.isabs(fixture) or os.path.isabs(native) or re.match(r"^[A-Za-z]:", fixture):
        return "fixture_file должен быть относительным путём, получено: " + fixture
    root = os.path.abspath(repo_root or REPO_ROOT)
    target = os.path.abspath(os.path.join(base_dir, fixture))
    if target != root and not target.startswith(root + os.sep):
        return "fixture_file выходит за корень репозитория: " + fixture
    return ""


def validate(entries, base_dir=".", allow_pending=False, repo_root=None):
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
        # Запрет открытых финализационных задач внутри подтверждённой записи.
        note_blob = " ".join(str(e.get(k, "")) for k in
                             ("evidence_note", "secondary_justification", "warning_disposition"))
        if "ЗАДАЧА" in note_blob:
            errors.append(tag + ": подтверждённая запись содержит «ЗАДАЧА» — завершите или переведите в warning_disposition")
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
        # Предупреждение о свежести для живых (не immutable) URL.
        if url and accessed and not _is_immutable(url):
            try:
                import datetime as _dt
                days = (_dt.date.today() - _dt.date.fromisoformat(accessed)).days
                if days > 180:
                    warnings.append(tag + ": живой source_url не перепроверян %d дней (accessed=%s)" % (days, accessed))
            except ValueError:
                pass
        sample = e.get("verbatim_sample", "")
        if sample and not re.search(SCOPE[case], sample):
            errors.append(tag + ": verbatim_sample НЕ ловится выражением своего case")
        fixture = e.get("fixture_file")
        if case == "openai_pua_short" and not fixture:
            errors.append(tag + ": для невидимых символов обязателен fixture_file с сырым образцом")
        if fixture:
            bad_path = _reject_path(fixture, base_dir, repo_root)
            if bad_path:
                errors.append(tag + ": " + bad_path)
                fixture = None
        if fixture:
            path = os.path.join(base_dir, fixture)
            if not os.path.isfile(path):
                errors.append(tag + ": fixture_file не найден: " + str(fixture))
            else:
                try:
                    with open(path, encoding="utf-8") as fh:
                        raw = fh.read()
                except (OSError, UnicodeDecodeError) as exc:
                    errors.append(tag + ": fixture_file не читается: %s" % exc)
                    continue
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
    # LEGACY-coverage: каждый case из check_markers.CASES обязан быть либо в
    # SCOPE, либо в автоматически выведенном LEGACY_EXEMPT. Не должно быть
    # case, отсутствующего и там, и там (это значит — не проверяется ничем).
    orphan = sorted(set(_MARKER_CASES) - set(SCOPE) - LEGACY_EXEMPT)
    if orphan:
        errors.append(
            "новый маркер без записи в реестре и без явного legacy: " + ", ".join(orphan)
        )
    # Обратная сторона: legacy-запись без соответствующего regex — мёртвый балласт.
    stale = sorted(LEGACY_EXEMPT - set(_MARKER_CASES))
    if stale and _MARKER_CASES:
        errors.append("legacy без regex в CASES: " + ", ".join(stale))
    if _MARKER_CASES:
        print(
            "Покрытие реестром: %d/%d маркеров, legacy: %d"
            % (len(SCOPE), len(_MARKER_CASES), len(LEGACY_EXEMPT))
        )
    return errors, warnings, covered


def run(path, allow_pending):
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
        "utm_copilot": "https://example.com/?utm_source=copilot.com",
        "grok_referrer": "https://example.com/?referrer=grok.com",
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
        "gemini_span": "[span_2](start_span)",
        # verbatim_sample, а не source_url: валидным URL быть не обязано.
        # Приведено к форме из живого реестра research/fixtures/marker-sources.json,
        # где для этого маркера verbatim_sample равен ровно "ppl-ai-file-upload".
        "perplexity_s3": "ppl-ai-file-upload",
        # Форма из живого реестра: метка Gemini с перечислением фрагментов.
        "gemini_cite_n": "[cite: 19, 20, 21]",
        # Форма из живого реестра: сцепка «Источник+цифра» из двух и больше
        # сегментов — одиночная склейка выражением не ловится.
        "source_plus_chain": "IT Governance+3ISO+3ISO+3",
        # Форма из живого реестра: внутренняя метка цитирования ChatGPT
        # с кинжалом и доменом источника.
        "oai_citation": "oai_citation:0\u2021wellington.scoop.co.nz",
        # Форма из живого реестра: ограда writing-блока; кавычки фигурные,
        # как в протёкшем образце.
        "writing_block": ":::writing{variant=\u201cdocument\u201d id=\u201c51724\u201d}",
        # Форма из живого реестра: JSON-атрибуция в конце сноски.
        "attributableIndex": "{\"attribution\":{\"attributableIndex\":\"1009-1\"",
        # Форма из живого реестра: усечённая метка oaicite внутри полной
        # обёртки contentReference.
        "oaicite_short": ":contentReference[oaicite:16]{index=16}",
        # Форма из живого реестра: полная обёртка contentReference
        # (другая строка того же протёкшего текста).
        "contentReference": ":contentReference[oaicite:20]{index=20}",
        # Форма из живого реестра: невидимые символы U+E200–U+E202 вокруг
        # метки цитирования (символы невидимы, в исходнике — \u-экранирование).
        "openai_pua": "\ue200cite\ue202turn0search1\ue201",
        # Форма из живого реестра: идентификатор результата поиска ChatGPT.
        "turn_search": "turn0search1",
        # Форма из живого реестра: UTM-метка ссылок ChatGPT до августа 2025.
        "utm_chatgpt": "?utm_source=chatgpt.com",
        # Форма из живого реестра: невидимые пробелы U+200B в конце фраз.
        "zero_width": "significant issues\u200b\u200b.",
        # Форма из живого реестра: метка цитирования Perplexity.
        "citation_n": "journals, and memoirs.[citation:1]",
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
    err, _, cov = validate(ok, base_dir=base, repo_root=base)
    checks.append(("полный тестовый реестр закрывает 26/26", not err and len(cov) == 26))
    err, _, _ = validate(ok[:-1], base_dir=base, repo_root=base)
    checks.append(("пропущен case -> FAIL", any("гейт не закрыт" in x for x in err)))
    _, warn, _ = validate(ok[:-1], base_dir=base, repo_root=base, allow_pending=True)
    checks.append(("--allow-pending -> WARN вместо FAIL", any("гейт не закрыт" in x for x in warn)))
    bad = json.loads(json.dumps(ok)); bad[0]["verbatim_sample"] = "обычный текст"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("sample не ловится regex -> FAIL", any("НЕ ловится" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[0]["evidence_class"] = "secondary"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("secondary без обоснования -> FAIL", any("secondary без" in x for x in err)))
    bad[0]["secondary_justification"] = "страница цитирует ревизию X"
    err, _, cov = validate(bad, base_dir=base, repo_root=base)
    checks.append(("secondary с обоснованием закрывает", not err and len(cov) == 26))
    bad = json.loads(json.dumps(ok)); bad[1]["evidence_class"] = "provenance"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("provenance без оговорки -> FAIL", any("provenance без" in x for x in err)))
    bad[1]["fp_caveat_documented"] = True
    err, _, cov = validate(bad, base_dir=base, repo_root=base)
    checks.append(("provenance с оговоркой закрывает", not err and len(cov) == 26))
    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["evidence_class"] = "synthetic"
    err, warn, cov = validate(bad, base_dir=base, repo_root=base)
    checks.append(("synthetic НЕ закрывает гейт", any("гейт не закрыт" in x for x in err)
                    and any("synthetic" in x for x in warn) and len(cov) == 25))
    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = os.path.basename(synth.name)
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("primary с fixture SYNTHETIC -> FAIL", any("не может быть primary" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[2]["source_url"] = "ftp://x"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("некорректный URL -> FAIL", any("некорректный source_url" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[3]["accessed"] = "13.07.2026"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("дата не ISO -> FAIL", any("YYYY-MM-DD" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[1]["source_url"] = bad[0]["source_url"]
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("повтор URL без disposition -> FAIL",
                   any("warning_disposition" in x for x in err)))
    bad[1]["warning_disposition"] = "проверено: общий источник осознан"
    err, warn, cov = validate(bad, base_dir=base, repo_root=base)
    checks.append(("повтор URL с disposition закрывает",
                   not err and any("повторный source_url" in x for x in warn) and len(cov) == 26))
    bad = json.loads(json.dumps(ok)); bad[0]["evidence_note"] = "найти permalink — ЗАДАЧА"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("ЗАДАЧА в подтверждённой записи -> FAIL",
                   any("«ЗАДАЧА»" in x for x in err)))
    bad = json.loads(json.dumps(ok)); bad[0]["source_url"] = "https://example.org/live"
    bad[0]["accessed"] = "2024-01-01"
    _, warn, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("живой URL старше 180 дней -> WARN",
                   any("не перепроверян" in x for x in warn)))
    # Guard на fixture_file: реестр — данные, и путь из него не должен уводить
    # проверку за пределы репозитория. Абсолютный путь особенно опасен, потому
    # что os.path.join молча отбрасывает base_dir.
    abs_fixture = os.path.abspath(tmp.name)
    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = abs_fixture
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("абсолютный fixture_file -> FAIL",
                   any("относительным путём" in x for x in err)))

    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = "../../../../etc/passwd"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("выход за корень репозитория -> FAIL",
                   any("выходит за корень" in x for x in err)))

    bad = json.loads(json.dumps(ok))
    for e in bad:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = "C:\\Windows\\system32\\drivers\\etc\\hosts"
    err, _, _ = validate(bad, base_dir=base, repo_root=base)
    checks.append(("путь с буквой диска Windows -> FAIL",
                   any("относительным путём" in x for x in err)))

    # Легитимная форма из живого реестра: относительный путь внутрь tests/.
    nested = os.path.join(base, "tests", "fixtures")
    os.makedirs(nested, exist_ok=True)
    legit_rel = os.path.join("tests", "fixtures", "pua-образец.txt")
    with io.open(os.path.join(base, legit_rel), "w", encoding="utf-8") as fh:
        fh.write(u"известная по ролям.2\n")
    good = json.loads(json.dumps(ok))
    for e in good:
        if e["case"] == "openai_pua_short":
            e["fixture_file"] = legit_rel.replace(os.sep, "/")
    err, _, cov = validate(good, base_dir=base, repo_root=base)
    checks.append(("относительный путь внутрь репозитория остаётся допустимым",
                   not err and len(cov) == 26))

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
