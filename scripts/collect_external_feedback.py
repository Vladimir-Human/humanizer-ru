#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_external_feedback.py — воспроизводимый сбор кандидатов внешней
обратной связи за период наблюдения (KPI 30 дней).

Кандидат — issue, discussion, комментарий или ответ от автора, не
являющегося сопровождающим или служебным ботом. Автоматический фильтр
даёт кандидатов с проверяемыми признаками (внешний автор, не сервисная
автоматизация, признаки конкретного описания запуска/результата/
проблемы), но НЕ доказывает подлинность пользовательского опыта:
решение о зачёте принимает человек-сопровождающий с объяснением и
ссылкой (план наблюдения — research/DISTRIBUTION-JOURNAL.md).

Честность источников: «получено и пусто» и «не удалось получить»
различаются. Каждый источник несёт статус ok (с числом элементов) либо
unavailable (с причиной); ошибка gh не превращается в пустой список.

Запуск:
    python3 scripts/collect_external_feedback.py --since 2026-09-06
    python3 scripts/collect_external_feedback.py --since 2026-09-06 --json
    python3 scripts/collect_external_feedback.py --selftest
Вывод: markdown-таблица или --json (период, источники, кандидаты);
--out пишет в файл. Синтетические фикстуры самопроверки помечаются
"synthetic": true и в журнал KPI не попадают.
Коды: 0 — сбор выполнен (включая пустой результат при доступных
источниках); 1 — хотя бы один источник недоступен (UNAVAILABLE, не
«нуль кандидатов»); 2 — ошибка аргументов/записи.
Только стандартная библиотека и CLI gh.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys

OWNER = "Vladimir-Human"
REPO_NAME = "humanizer-ru"
REPO = "%s/%s" % (OWNER, REPO_NAME)
BOT_SUFFIX = "[bot]"
SERVICE_LOGINS = {"dependabot[bot]", "renovate[bot]", "github-actions[bot]",
                  "vercel[bot]"}

# Признаки конкретного описания реального запуска/результата/проблемы
# (эвристика для сортировки внимания; зачёт остаётся за человеком).
_SIGNAL_VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")
_SIGNAL_COMMAND = re.compile(
    r"(humanizer[-_](?:scan|markers|polish|detect|facts|report|mcp)"
    r"|pip install|python3? |check_all|unittest|--json|--remove)",
    re.IGNORECASE)
_SIGNAL_PROBLEM = re.compile(
    r"(ошибк|error|traceback|не работ|doesn'?t work|не запуска|failed"
    r"|exception|код(?:а)? возвра|exit code|expected|ожидал)",
    re.IGNORECASE)
# Признаки рекрутинга/накрутки (каталожные приглашения, star-ask):
# кандидат с такими сигналами помечается, зачёт не рекомендуется.
_SIGNAL_SOLICITATION = re.compile(
    r"(awesome[- ]|add .* to .*(list|repo)|would you be up for|submit"
    r"|star\b|upvote|приглаш|добавьте в каталог)", re.IGNORECASE)


def _default_runner(args):
    """Реальный вызов gh: (payload, error). payload — список объектов.

    Ответ gh api — это JSON-документ(ы) в форматированном виде (страницы
    пагинации идут подряд), поэтому разбор идёт raw_decode по всему
    stdout, а не по строкам. Метод REST-вызовов всегда GET: с полями -f
    gh api без явного метода переключается на POST. GraphQL-вызов идёт
    штатной командой gh api graphql (POST, своя обработка пагинации).
    """
    if args and args[0] == "graphql":
        cmd = ["gh", "api"] + args
    else:
        cmd = ["gh", "api", "--paginate", "-X", "GET"] + args
    try:
        r = subprocess.run(cmd,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "gh не запустился: %r" % (exc,)
    if r.returncode != 0:
        return None, "gh api %s: код %d: %s" % (
            args[0] if args else "?", r.returncode,
            (r.stderr or "").strip()[:200])
    out = []
    text = r.stdout or ""
    idx = 0
    dec = json.JSONDecoder()
    while idx < len(text):
        while idx < len(text) and text[idx] in " \r\n\t":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end = dec.raw_decode(text, idx)
        except ValueError as exc:
            return None, "gh api: ответ не JSON: %s" % exc
        if isinstance(obj, list):
            out.extend(obj)
        else:
            out.append(obj)
        idx = end
    return out, None


def is_bot(login):
    return login.endswith(BOT_SUFFIX) or login in SERVICE_LOGINS


def is_external(login):
    return bool(login) and login != OWNER and not is_bot(login)


def _signals(body):
    text = body or ""
    return {
        "has_version": bool(_SIGNAL_VERSION.search(text)),
        "has_command": bool(_SIGNAL_COMMAND.search(text)),
        "has_problem": bool(_SIGNAL_PROBLEM.search(text)),
        "solicitation": bool(_SIGNAL_SOLICITATION.search(text)),
    }


def _row(author, kind, url, date, title, body="", synthetic=False,
         thread=""):
    sig = _signals(body)
    concrete = (sig["has_command"] or sig["has_problem"]
                or sig["has_version"]) and not sig["solicitation"]
    return {
        "author": author,
        "kind": kind,
        "url": url,
        "date": date,
        "title": title,
        "thread": thread,
        "bot": is_bot(author),
        "external": is_external(author),
        "signals": sig,
        "concrete_usage_signs": concrete,
        "synthetic": synthetic,
        "body_excerpt": (body or "")[:200].replace("\n", " "),
    }


def _graphql_discussions(runner, since, synthetic=False):
    """Discussion-корни и комментарии к ним (курсорная пагинация).

    Ответ GraphQL читается через оболочку data.repository.discussions.
    Ответ внешнего пользователя в треде владельца рассматривается как
    кандидат (kind: discussion-comment) даже когда корень старше окна.
    """
    rows = []
    cursor = "null"
    while True:
        query = (
            '{ repository(owner: "%s", name: "%s") { discussions('
            "first: 50, after: %s, orderBy: {field: CREATED_AT, "
            "direction: ASC}) { pageInfo { hasNextPage endCursor } nodes { "
            "number title createdAt author { login } comments(first: 50) { "
            "nodes { createdAt author { login } url } } } } } }"
            % (OWNER, REPO_NAME, cursor))
        payload, err = runner(["graphql", "-f", "query=" + query])
        if err:
            return rows, err
        envelope = payload[0] if payload else {}
        data = (envelope or {}).get("data") or {}
        repo = data.get("repository") or {}
        disc = repo.get("discussions") or {}
        for node in disc.get("nodes") or []:
            login = ((node.get("author") or {}).get("login") or "")
            created = (node.get("createdAt") or "")[:10]
            number = node.get("number")
            url = "https://github.com/%s/discussions/%s" % (REPO, number)
            if not since or created >= since:
                rows.append(_row(login, "discussion", url, created,
                                 node.get("title", ""),
                                 synthetic=synthetic))
            comments = ((node.get("comments") or {}).get("nodes") or [])
            for c in comments:
                clogin = ((c.get("author") or {}).get("login") or "")
                ccreated = (c.get("createdAt") or "")[:10]
                if since and ccreated < since:
                    continue
                rows.append(_row(clogin, "discussion-comment",
                                 c.get("url") or url, ccreated,
                                 "ответ в #%s" % number,
                                 synthetic=synthetic, thread=url))
        page = disc.get("pageInfo") or {}
        if page.get("hasNextPage") and page.get("endCursor"):
            cursor = '"%s"' % page["endCursor"]
            continue
        return rows, None


def collect(since, runner=None, synthetic=False):
    """Возвращает (rows, sources): sources — статусы каждого источника.

    Источники: issues (state=all — закрытые не теряются), комментарии
    issues, discussions с комментариями (курсорная пагинация).
    """
    runner = runner or _default_runner
    rows = []
    sources = {}

    payload, err = runner(["repos/%s/issues" % REPO,
                           "-f", "state=all", "-f", "per_page=100"])
    if err:
        sources["issues"] = {"status": "unavailable", "reason": err}
    else:
        n = 0
        for item in payload or []:
            if item.get("pull_request"):
                continue
            login = (item.get("user") or {}).get("login", "")
            created = (item.get("created_at") or "")[:10]
            if since and created < since:
                continue
            rows.append(_row(login, "issue", item.get("html_url", ""),
                             created, item.get("title", ""),
                             item.get("body") or "", synthetic=synthetic))
            n += 1
        sources["issues"] = {"status": "ok", "items": n}

    payload, err = runner(["repos/%s/issues/comments" % REPO,
                           "-f", "per_page=100"]
                          + (["-f", "since=%sT00:00:00Z" % since]
                             if since else []))
    if err:
        sources["issue-comments"] = {"status": "unavailable", "reason": err}
    else:
        n = 0
        for item in payload or []:
            login = (item.get("user") or {}).get("login", "")
            created = (item.get("created_at") or "")[:10]
            if since and created < since:
                continue
            issue_url = item.get("html_url", "").split("#")[0]
            kind = ("pr-comment" if "/pull/" in issue_url
                    else "issue-comment")
            rows.append(_row(login, kind,
                             item.get("html_url", ""), created,
                             "комментарий в #%s" % issue_url.rsplit("/", 1)[-1],
                             item.get("body") or "", synthetic=synthetic,
                             thread=issue_url))
            n += 1
        sources["issue-comments"] = {"status": "ok", "items": n}

    disc_rows, err = _graphql_discussions(runner, since,
                                          synthetic=synthetic)
    if err:
        sources["discussions"] = {"status": "unavailable", "reason": err}
    else:
        rows.extend(disc_rows)
        sources["discussions"] = {"status": "ok", "items": len(disc_rows)}
    return rows, sources


def render(rows):
    lines = ["| Автор | Тип | URL | Дата | Тема | Бот | Внешний | Признаки | Синтетика |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: (x["date"], x["kind"])):
        sig = r["signals"]
        marks = ",".join(k for k, v in sorted(sig.items()) if v) or "-"
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (r["author"], r["kind"], r["url"], r["date"],
                        r["title"].replace("|", "/"),
                        "да" if r["bot"] else "нет",
                        "да" if r["external"] else "нет",
                        marks,
                        "да" if r["synthetic"] else "нет"))
    return "\n".join(lines)


# ---------------------------------------------------------------- selftest

def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    ver = "%d.%d.%d" % (3, 32, 1)
    issues_payload = [
        {"user": {"login": "external-user"},
         "created_at": "2026-09-07T10:00:00Z",
         "html_url": "https://github.com/%s/issues/1" % REPO,
         "title": "Не запускается --remove",
         "body": "python3 -m humanizer_ru ... ошибка, версия " + ver},
        {"user": {"login": OWNER}, "created_at": "2026-09-07T11:00:00Z",
         "html_url": "https://github.com/%s/issues/2" % REPO,
         "title": "своя задача", "body": ""},
        {"user": {"login": "dependabot[bot]"},
         "created_at": "2026-09-07T12:00:00Z",
         "html_url": "https://github.com/%s/issues/3" % REPO,
         "title": "bump", "body": ""},
        {"user": {"login": "old-user"},
         "created_at": "2026-08-01T12:00:00Z",
         "html_url": "https://github.com/%s/issues/0" % REPO,
         "title": "старое", "body": ""},
        {"user": {"login": "pr-author"},
         "created_at": "2026-09-07T13:00:00Z",
         "html_url": "https://github.com/%s/pull/9" % REPO,
         "title": "PR не issue", "body": "", "pull_request": {"url": "x"}},
    ]
    comments_payload = [
        {"user": {"login": "external-user"},
         "created_at": "2026-09-08T10:00:00Z",
         "html_url": "https://github.com/%s/issues/2#issuecomment-1" % REPO,
         "body": "воспроизвёл: exit code 2 на ubuntu"},
    ]
    discussions_envelope = [{"data": {"repository": {"discussions": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [
            {"number": 95, "title": "Обратная связь",
             "createdAt": "2026-09-06T00:00:00Z",
             "author": {"login": OWNER},
             "comments": {"nodes": [
                 {"createdAt": "2026-09-09T00:00:00Z",
                  "author": {"login": "reader-external"},
                  "url": "https://github.com/%s/discussions/95#c" % REPO}]}},
        ]}}}}]

    def make(overrides):
        mapping = {
            "issues-comments": ("repos/%s/issues/comments" % REPO,
                                (comments_payload, None)),
            "issues": ("repos/%s/issues" % REPO, (issues_payload, None)),
            "graphql": ("graphql", (discussions_envelope, None)),
        }
        for key, value in (overrides or {}).items():
            slot = mapping[key]
            mapping[key] = (slot[0], value)

        def runner(args):
            first = args[0]
            # comments проверяется РАНЬШЕ issues (префикс совпадает).
            for key in ("issues-comments", "issues", "graphql"):
                prefix, value = mapping[key]
                if first.startswith(prefix):
                    return value
            return [], None
        return runner

    rows, src = collect("2026-09-06", runner=make(None), synthetic=True)
    ext = [r for r in rows if r["external"]]
    case("внешний автор виден, владелец и бот — нет",
         any(r["author"] == "external-user" for r in ext)
         and not any(r["author"] == OWNER for r in ext)
         and not any(r["bot"] for r in ext))
    case("записи до --since отсекаются",
         not any(r["author"] == "old-user" for r in rows))
    case("PR не попадает как issue",
         not any(r["title"] == "PR не issue" for r in rows))
    case("ответ внешнего в треде владельца рассматривается",
         any(r["kind"] == "discussion-comment"
             and r["author"] == "reader-external" for r in rows)
         and any(r["kind"] == "issue-comment"
                 and r["author"] == "external-user" for r in rows))
    case("обсуждение читается через оболочку data.repository",
         any(r["kind"] == "discussion" for r in rows))
    case("признаки конкретного использования помечаются",
         any(r["concrete_usage_signs"] for r in ext))
    case("синтетика помечена", all(r["synthetic"] for r in rows))
    case("источники ok", all(s["status"] == "ok" for s in src.values()))

    # Негатив: ошибка gh — UNAVAILABLE, а не пустой список.
    _rows2, src2 = collect("2026-09-06", runner=make({
        "issues": (None, "gh api: код 1: rate limit"),
    }), synthetic=True)
    case("ошибка gh даёт unavailable источника (не пусто)",
         src2["issues"]["status"] == "unavailable"
         and "rate limit" in src2["issues"]["reason"])

    # Негатив: рекрутинг-приглашение не считается конкретным использованием.
    solicit = [{"user": {"login": "catalog-promo"},
                "created_at": "2026-09-07T10:00:00Z",
                "html_url": "https://github.com/%s/issues/5" % REPO,
                "title": "Add to awesome list?",
                "body": "We maintain awesome-ai-plugins. "
                        "Would you be up for adding?"}]
    rows3, _src3 = collect("2026-09-06", runner=make({
        "issues": (solicit, None),
    }), synthetic=True)
    cand = [r for r in rows3 if r["author"] == "catalog-promo"]
    case("каталожное приглашение помечается solicitation и не concrete",
         bool(cand) and cand[0]["signals"]["solicitation"]
         and not cand[0]["concrete_usage_signs"])

    # Пагинация discussions: два круга курсора.
    page1 = [{"data": {"repository": {"discussions": {
        "pageInfo": {"hasNextPage": True, "endCursor": "CUR1"},
        "nodes": [{"number": 1, "title": "d1",
                   "createdAt": "2026-09-07T00:00:00Z",
                   "author": {"login": "u1"},
                   "comments": {"nodes": []}}]}}}}]
    page2 = [{"data": {"repository": {"discussions": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [{"number": 2, "title": "d2",
                   "createdAt": "2026-09-08T00:00:00Z",
                   "author": {"login": "u2"},
                   "comments": {"nodes": []}}]}}}}]
    state = {"n": 0}

    def paging_runner(args):
        if args[0] == "graphql":
            state["n"] += 1
            return (page1 if state["n"] == 1 else page2), None
        return [], None

    _rows4, src4 = collect("2026-09-06", runner=paging_runner,
                           synthetic=True)
    case("курсорная пагинация discussions проходит обе страницы",
         state["n"] == 2 and src4["discussions"]["items"] == 2)

    print("САМОПРОВЕРКА collect_external_feedback: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(
        description="Сбор кандидатов внешней обратной связи (KPI-окно): "
                    "issues state=all, комментарии, discussions с ответами; "
                    "UNAVAILABLE отличается от пустого результата.")
    ap.add_argument("--since", default=None, help="дата начала наблюдения")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true",
                    help="машиночитаемый вывод: период, источники, кандидаты")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    rows, sources = collect(args.since)
    unavailable = sorted(k for k, v in sources.items()
                         if v.get("status") != "ok")
    if args.json:
        envelope = {
            "generated_at": datetime.datetime.now(
                datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "since": args.since,
            "sources": sources,
            "candidates": rows,
            "external_candidates": sum(1 for r in rows if r["external"]),
        }
        text = json.dumps(envelope, ensure_ascii=False, indent=2)
    else:
        text = render(rows)
        text += ("\n\nИсточники: " + "; ".join(
            "%s=%s" % (k, v.get("status"))
            for k, v in sorted(sources.items())))
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            print("не записано: %r" % exc, file=sys.stderr)
            return 2
        print("записано: %s (строк: %d)" % (args.out, len(rows)))
    else:
        print(text)
    if unavailable:
        print("UNAVAILABLE источники: %s — результат неполон, «нулём "
              "кандидатов» не считается" % ", ".join(unavailable),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
