#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_pages_router.py — гейт машинного входа: ссылки llms.txt и копии на Pages.

llms.txt отдаётся с двух хостов (GitHub и Pages), поэтому все его ссылки
обязаны быть абсолютными и разрешаться (HTTP 200) из любого контекста;
витринные копии (README, SKILL, FRAMEWORK, реестр фактов, контракт,
эррата, robots.txt, /.well-known/llms.txt) обязаны быть перечислены в
шаге копирования workflow Pages и, после деплоя, отдаваться с Pages.

Режимы:
    python3 scripts/check_pages_router.py              # ссылки llms.txt (HEAD)
                                                       # + статика workflow
    python3 scripts/check_pages_router.py --live-pages # дополнительно HEAD
                                                       # всех копий на Pages
                                                      # (после деплоя)
    python3 scripts/check_pages_router.py --selftest   # негативные кейсы,
                                                       # без сети

Коды: 0 — маршруты целы; 1 — битая ссылка/отсутствующая копия/относительная
ссылка; 2 — проверка невозможна (сеть/файлы недоступны). Только стандартная
библиотека.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LLMS = os.path.join(ROOT, "llms.txt")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "demo-pages.yml")
PAGES_BASE = "https://vladimir-human.github.io/humanizer-ru/"
# Что обязано отдаваться с Pages (копии из шага workflow + ассеты демо).
PAGES_PATHS = ["llms.txt", ".well-known/llms.txt", "contract.v1.json",
               "ERRATA.md", "README.md", "README.en.md", "SKILL.md",
               "docs/FRAMEWORK.md", "eval/facts/facts.v1.json", "robots.txt",
               "favicon.svg", "identity.v1.json", "og-image.png",
               "sitemap.xml", "eval/facts/self-audit.v1.json"]
# Строки, которые обязан содержать шаг копирования workflow (статическая
# проверка до деплоя: на PR ветке Pages ещё старый, сеть по Pages не
# проверяется, но состав артефакта виден из workflow).
WORKFLOW_REQUIRED = ["llms.txt", "contract.v1.json", "ERRATA.md", "README.md",
                     "README.en.md", "SKILL.md", "docs/FRAMEWORK.md",
                     "eval/facts/facts.v1.json", ".well-known",
                     "identity.v1.json"]

LINK_RX = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def extract_links(text: str) -> list:
    return LINK_RX.findall(text)


def links_absolute(links) -> list:
    """Относительные ссылки llms.txt — дефект: файл живёт на двух хостах."""
    return [u for u in links if not u.startswith(("http://", "https://"))]


def http_status(url: str) -> int:
    """HTTP-код HEAD-запроса (редиректы разрешены); OSError пробрасывается."""
    req = urllib.request.Request(url, method="HEAD", headers={
        "User-Agent": "humanizer-ru-check-pages-router"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def check_static() -> list:
    errors = []
    if not os.path.isfile(os.path.join(ROOT, "demo", "robots.txt")):
        errors.append("demo/robots.txt отсутствует (Pages отдаёт /robots.txt)")
    try:
        with open(WORKFLOW, encoding="utf-8") as fh:
            wf = fh.read()
    except OSError as exc:
        return ["workflow demo-pages.yml не читается: %r" % exc]
    for needle in WORKFLOW_REQUIRED:
        if needle not in wf:
            errors.append("demo-pages.yml: шаг копирования не несёт %s — "
                          "копия не попадёт в артефакт Pages" % needle)
    return errors


def check_links(do_pages: bool) -> tuple:
    """(ошибки, отказ-сети)."""
    errors = []
    try:
        with open(LLMS, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return ["llms.txt не читается: %r" % exc], False
    links = extract_links(text)
    if not links:
        errors.append("llms.txt без ссылок — маршрутизатор пуст")
    relative = links_absolute(links)
    for u in relative:
        errors.append("llms.txt: относительная ссылка %s — с Pages не "
                      "разрешится; нужны абсолютные URL" % u)
    network_fail = False
    for u in [x for x in links if x.startswith(("http://", "https://"))]:
        try:
            status = http_status(u)
        except OSError:
            network_fail = True
            break
        if status != 200:
            errors.append("llms.txt: ссылка %s -> HTTP %d" % (u, status))
    if network_fail:
        return errors, True
    if do_pages:
        for rel in PAGES_PATHS:
            url = PAGES_BASE + rel
            try:
                status = http_status(url)
            except OSError:
                network_fail = True
                break
            if status != 200:
                errors.append("Pages: %s -> HTTP %d (копия не опубликована)"
                              % (url, status))
    return errors, network_fail


def selftest() -> int:
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    text = ("- [a](https://github.com/x/y/blob/main/a.md)\n"
            "- [b](https://example.com/b)\n")
    case("извлечение markdown-ссылок", extract_links(text) ==
         ["https://github.com/x/y/blob/main/a.md", "https://example.com/b"])
    case("абсолютные ссылки проходят", links_absolute(extract_links(text)) == [])
    mixed = "- [c](README.md)\n- [d](https://example.com/d)\n"
    case("относительная ссылка ловится (негатив)",
         links_absolute(extract_links(mixed)) == ["README.md"])
    wf_missing = "name: x\nsteps:\n  - run: cp llms.txt demo/\n"
    miss = [n for n in WORKFLOW_REQUIRED if n not in wf_missing]
    case("неполный шаг копирования ловится (негатив)", len(miss) >= 5)
    print("САМОПРОВЕРКА check_pages_router: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Машинный вход: абсолютность и разрешимость ссылок "
                    "llms.txt, состав копий Pages.")
    ap.add_argument("--live-pages", action="store_true",
                    help="дополнительно HEAD всех копий на Pages (после деплоя)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errors = check_static()
    link_errors, network_fail = check_links(args.live_pages)
    errors.extend(link_errors)
    for e in errors:
        print("[FAIL] " + e)
    if errors:
        print("PAGES-МАРШРУТ: нарушений %d" % len(errors))
        return 1
    if network_fail:
        print("PAGES-МАРШРУТ: проверка невозможна (сеть недоступна)",
              file=sys.stderr)
        return 2
    scope = "ссылки llms.txt + состав workflow"
    if args.live_pages:
        scope += " + копии на Pages"
    print("PAGES-МАРШРУТ: %s — целы" % scope)
    return 0


if __name__ == "__main__":
    sys.exit(main())
