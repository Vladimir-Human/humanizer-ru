#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_external_feedback.py — воспроизводимый сбор кандидатов внешней
обратной связи за период наблюдения (KPI 30 дней).

Кандидат — issue или discussion от автора, не являющегося сопровождающим
или служебным ботом. Автоматический фильтр даёт кандидатов, но не
доказывает подлинность пользовательского опыта: решение о зачёте принимает
человек-сопровождающий с объяснением и ссылкой (план наблюдения —
research/SPRINT-LEADERSHIP-2026-09-05.md).

Запуск:
    python3 scripts/collect_external_feedback.py --since 2026-09-07
Вывод: markdown-таблица (автор, тип, URL, дата, тема, бот/не бот, признак
внешнего автора) в stdout или --out файл. Только стандартная библиотека и
CLI gh.
"""
import argparse
import json
import subprocess
import sys

OWNER = "Vladimir-Human"
REPO = "Vladimir-Human/humanizer-ru"
BOT_SUFFIX = "[bot]"
SERVICE_LOGINS = {"dependabot[bot]", "renovate[bot]", "github-actions[bot]",
                  "vercel[bot]"}


def gh_json(args):
    r = subprocess.run(["gh", "api", "--paginate"] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        print("gh error: %s" % r.stderr.strip()[:200], file=sys.stderr)
        return []
    out = []
    for chunk in r.stdout.splitlines():
        chunk = chunk.strip()
        if not chunk:
            continue
        data = json.loads(chunk)
        if isinstance(data, list):
            out.extend(data)
        else:
            out.append(data)
    return out


def is_bot(login):
    return login.endswith(BOT_SUFFIX) or login in SERVICE_LOGINS


def collect(since):
    rows = []
    for item in gh_json(["repos/%s/issues" % REPO,
                         "--jq", "."]):
        if item.get("pull_request"):
            continue
        login = (item.get("user") or {}).get("login", "")
        created = item.get("created_at", "")[:10]
        if since and created < since:
            continue
        rows.append({
            "author": login,
            "kind": "issue",
            "url": item.get("html_url", ""),
            "date": created,
            "title": item.get("title", ""),
            "bot": is_bot(login),
            "external": login != OWNER and not is_bot(login),
        })
    disc = gh_json(["graphql", "-f",
                    "query={ repository(owner: \"%s\", name: \"%s\") { "
                    "discussions(first: 100) { nodes { number title "
                    "createdAt author { login } } } } }" % (OWNER,
                                                            "humanizer-ru")])
    for repo in disc:
        for node in ((repo.get("discussions") or {}).get("nodes") or []):
            login = ((node.get("author") or {}).get("login") or "")
            created = (node.get("createdAt") or "")[:10]
            if since and created < since:
                continue
            rows.append({
                "author": login,
                "kind": "discussion",
                "url": "https://github.com/%s/discussions/%s"
                       % (REPO, node.get("number")),
                "date": created,
                "title": node.get("title", ""),
                "bot": is_bot(login),
                "external": login != OWNER and not is_bot(login),
            })
    return rows


def render(rows):
    lines = ["| Автор | Тип | URL | Дата | Тема | Бот | Внешний |",
             "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: x["date"]):
        lines.append("| %s | %s | %s | %s | %s | %s | %s |"
                     % (r["author"], r["kind"], r["url"], r["date"],
                        r["title"].replace("|", "/"),
                        "да" if r["bot"] else "нет",
                        "да" if r["external"] else "нет"))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="дата начала наблюдения")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rows = collect(args.since)
    text = render(rows)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print("записано: %s (строк: %d)" % (args.out, len(rows)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
