#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_feedback_evidence.py — проверка доказательств внешнего опыта.

Хранилище доказательств: research/external-feedback/evidence.v1.json —
структурированный журнал окна наблюдения: события с URL, цитатой,
обоснованием зачёта и пометкой qualified. Автоматические признаки
коллектора (signals) сами по себе зачётом НЕ являются: событие без
цитаты и содержательного обоснования, прочитанного сопровождением по
исходному сообщению, квалифицированным не считается.

Режимы:
  python3 scripts/check_feedback_evidence.py            # валидация файла
  python3 scripts/check_feedback_evidence.py --require-qualified-event
      0 — есть квалифицированное событие окна;
      1 — события нет: KPI_PENDING (в окне) или KPI_NOT_MET (окно
          закрыто, покрытие источников достаточное);
      2 — утверждать нельзя: покрытие источников недостаточное или
          файл/окно нечитаемы.
  python3 scripts/check_feedback_evidence.py --selftest
"""
import argparse
import datetime as _dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_EVIDENCE = os.path.join(ROOT, "research", "external-feedback",
                                "evidence.v1.json")
_URL_RX = re.compile(r"^https?://[^\s]+$")
_MIN_RATIONALE = 40


def _parse_date(value):
    try:
        return _dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_evidence(doc, now=None):
    """Список проблем документа доказательств; пуст — документ корректен."""
    problems = []
    if not isinstance(doc, dict):
        return ["документ доказательств не является объектом"]
    window = doc.get("window") or {}
    start = _parse_date(window.get("start"))
    end = _parse_date(window.get("end"))
    if start is None or end is None:
        problems.append("окно наблюдения не читается (window.start/end)")
    elif start > end:
        problems.append("начало окна позже конца")
    coverage = doc.get("coverage") or {}
    if not coverage.get("collected_at"):
        problems.append("нет снимка покрытия источников (coverage."
                        "collected_at): честный нуль не подтверждён")
    sources = coverage.get("sources") or {}
    if coverage and sources:
        for name, st in sorted(sources.items()):
            status = (st or {}).get("status")
            if status not in ("ok", "partial"):
                problems.append("источник %s не покрыт сбором: %r"
                                % (name, status))
    events = doc.get("events") or []
    if not isinstance(events, list):
        problems.append("events не список")
        return problems
    for i, ev in enumerate(events):
        where = "событие %d" % i
        if not isinstance(ev, dict):
            problems.append("%s: не объект" % where)
            continue
        url = ev.get("url") or ""
        if not _URL_RX.match(url):
            problems.append("%s: url не читается: %r" % (where, url))
        date = _parse_date(ev.get("date"))
        if date is None:
            problems.append("%s: дата не читается" % where)
        elif start and end and not (start <= date <= end):
            problems.append("%s: дата вне окна наблюдения" % where)
        quote = ev.get("quote") or ""
        if not quote.strip():
            problems.append("%s: нет цитаты исходного сообщения" % where)
        rationale = ev.get("rationale") or ""
        if len(rationale.strip()) < _MIN_RATIONALE:
            problems.append("%s: обоснование зачёта отсутствует или короче "
                            "%d символов (автоматические признаки зачётом "
                            "не являются)" % (where, _MIN_RATIONALE))
        if not ev.get("read_by"):
            problems.append("%s: не указано, кто прочитал исходное "
                            "сообщение" % where)
        if ev.get("synthetic") and ev.get("qualified"):
            problems.append("%s: синтетическое событие не может быть "
                            "квалифицированным" % where)
        if not isinstance(ev.get("qualified"), bool):
            problems.append("%s: qualified не булево" % where)
    return problems


def coverage_sufficient(doc):
    coverage = doc.get("coverage") or {}
    sources = coverage.get("sources") or {}
    if not coverage.get("collected_at") or not sources:
        return False
    return all((st or {}).get("status") in ("ok", "partial")
               for st in sources.values())


def require_qualified(doc, now=None):
    """(rc, сообщение) для --require-qualified-event."""
    now = now or _dt.date.today()
    problems = validate_evidence(doc, now)
    structural = [p for p in problems
                  if not p.startswith("источник ")
                  and "coverage" not in p]
    if structural:
        return 2, ("документ доказательств некорректен: %s"
                   % "; ".join(structural[:3]))
    events = doc.get("events") or []
    qualified = [ev for ev in events if ev.get("qualified")
                 and not ev.get("synthetic")]
    if qualified:
        return 0, ("KPI: квалифицированное событие есть: %s"
                   % qualified[0].get("url"))
    if not coverage_sufficient(doc):
        return 2, ("KPI: утверждать нельзя — покрытие источников "
                   "недостаточное (см. coverage)")
    window = doc.get("window") or {}
    end = _parse_date(window.get("end"))
    if end is not None and now > end:
        return 1, ("KPI_NOT_MET: окно %s..%s закрыто без квалифицированного "
                   "события при достаточном покрытии источников"
                   % (window.get("start"), window.get("end")))
    return 1, ("KPI_PENDING: окно %s..%s открыто, квалифицированного "
               "события нет" % (window.get("start"), window.get("end")))


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    now = _dt.date(2026, 9, 20)
    good_coverage = {"collected_at": "2026-09-20T00:00:00Z",
                     "sources": {"issues": {"status": "ok"},
                                 "issue-comments": {"status": "ok"},
                                 "discussions": {"status": "ok"}}}
    base = {"schema": 1,
            "window": {"start": "2026-09-06", "end": "2026-10-06"},
            "coverage": good_coverage, "events": []}
    qualified = dict(base)
    qualified["events"] = [{
        "date": "2026-09-15", "kind": "issue",
        "url": "https://github.com/x/y/issues/1#issuecomment-1",
        "author": "someone",
        "quote": "humanizer-markers --json поймал вставку из чата в моём "
                 "отчёте, спасибо за объяснения",
        "rationale": "Прочитал исходное сообщение целиком: человек описывает "
                     "собственную задачу и результат применения инструмента "
                     "на своём тексте; не рекрутинг и не синтетика.",
        "read_by": "сопровождение", "qualified": True, "synthetic": False}]
    case("валидный документ с квалифицированным событием чист",
         validate_evidence(qualified, now) == [])
    rc, msg = require_qualified(qualified, now)
    case("квалифицированное событие даёт rc 0", rc == 0 and "KPI:" in msg)

    rc, msg = require_qualified(base, now)
    case("в открытом окне без события — KPI_PENDING (rc 1)",
         rc == 1 and "KPI_PENDING" in msg)
    late_now = _dt.date(2026, 10, 20)
    rc, msg = require_qualified(base, late_now)
    case("после окна без события — KPI_NOT_MET (rc 1)",
         rc == 1 and "KPI_NOT_MET" in msg)
    no_cov = dict(base)
    no_cov["coverage"] = {}
    rc, msg = require_qualified(no_cov, late_now)
    case("без покрытия источников утверждать нельзя (rc 2)",
         rc == 2 and "покрытие" in msg)

    bad_synthetic = dict(base)
    bad_synthetic["events"] = [dict(qualified=True, synthetic=True,
                                    url="https://x/y", date="2026-09-15",
                                    quote="q", rationale="r" * 60,
                                    read_by="сопровождение")]
    case("синтетика не может быть квалифицированной",
         validate_evidence(bad_synthetic, now) != [])
    signals_only = dict(base)
    signals_only["events"] = [{
        "date": "2026-09-15", "url": "https://github.com/x/y/issues/2",
        "quote": "humanizer-markers --json " + "3.33" + ".0",
        "rationale": "коротко", "read_by": "сопровождение",
        "qualified": True, "synthetic": False}]
    case("признаки без содержательного обоснования не валидны",
         validate_evidence(signals_only, now) != [])
    out_window = dict(base)
    out_window["events"] = [{
        "date": "2026-08-01", "url": "https://github.com/x/y/issues/3",
        "quote": "цитата", "rationale": "о" * 60, "read_by": "сопровождение",
        "qualified": True, "synthetic": False}]
    case("событие вне окна не валидно",
         validate_evidence(out_window, now) != [])
    bad_src = dict(base)
    bad_src["coverage"] = {"collected_at": "2026-09-20T00:00:00Z",
                           "sources": {"issues": {"status": "unavailable"}}}
    case("непокрытый источник делает документ невалидным",
         validate_evidence(bad_src, now) != [])
    print("САМОПРОВЕРКА check_feedback_evidence: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    ap.add_argument("--require-qualified-event", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        with open(args.evidence, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print("[FAIL] ДОКАЗАТЕЛЬСТВА: файл не читается: %r" % (exc,),
              file=sys.stderr)
        return 2
    if args.require_qualified_event:
        rc, msg = require_qualified(doc)
        print(msg)
        return rc
    problems = validate_evidence(doc)
    if args.json:
        print(json.dumps({"problems": problems}, ensure_ascii=False))
    for p in problems:
        print("[FAIL] ДОКАЗАТЕЛЬСТВА: " + p)
    if problems:
        print("ДОКАЗАТЕЛЬСТВА: проблем %d" % len(problems))
        return 1
    print("ДОКАЗАТЕЛЬСТВА: документ корректен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
