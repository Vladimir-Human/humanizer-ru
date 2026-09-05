#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_links.py — W10: проверка мёртвых ссылок по всем .md и docs/
(stdlib urllib, таймаут). Запускается в nightly-workflow, не в PR-гейте.

Локовые относительные ссылки проверяются на существование файла;
http(s) — запросом с таймаутом; сетевые ошибки (таймаут, 429, DNS) считаются
предупреждениями, мёртвые статусы (404, 410) — ошибкой.
"""
import argparse
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK_RX = re.compile(r"\[[^\]]*\]\(([^)\s]+)[^)]*\)")
RAW_RX = re.compile(r"(?<!\()(https?://[^\s<>\"')]+)")
TIMEOUT = 10


def md_files():
    out = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules",
                                                ".venv", "venv", "dist",
                                                "__pycache__", "archive")]
        for f in files:
            if f.endswith(".md"):
                out.append(os.path.join(base, f))
    return sorted(out)


def _strip_code(text):
    """Убрать fenced-блоки и инлайновые бэктик-спаны: фикстуры и регулярки
    не являются ссылками."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


KNOWN_EXT = (".md", ".py", ".json", ".html", ".css", ".js", ".yml", ".yaml",
             ".txt", ".svg", ".png", ".cff", ".toml", ".atom")


def links_of(path):
    text = _strip_code(open(path, encoding="utf-8", errors="replace").read())
    seen = set()
    for m in LINK_RX.finditer(text):
        seen.add(m.group(1))
    for m in RAW_RX.finditer(text):
        seen.add(m.group(1))
    return sorted(seen)


def slug(head):
    """Slug заголовка по правилам GitHub: нижний регистр, пробелы в дефисы,
    пунктуация снимается (кроме дефисов и подчёркиваний)."""
    import re as _re
    s = head.strip().lower()
    s = s.replace("`", "")
    s = _re.sub(r"[^\w\s-]", "", s, flags=_re.U)
    s = _re.sub(r"\s+", "-", s.strip())
    return s


def headings_of(path):
    out = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                m = re.match(r"^(#{1,6})\s+(.*)$", ln)
                if m:
                    out.add(slug(m.group(2)))
    except OSError:
        pass
    return out


def _check_paths(pairs):
    dead = []
    for path, link in pairs:
        if "#" in link and not link.startswith("#"):
            fpart, anchor = link.split("#", 1)
            if fpart and not fpart.startswith("http"):
                fpath = os.path.normpath(os.path.join(
                    os.path.dirname(path), fpart))
                if os.path.isfile(fpath) and anchor:
                    if anchor not in headings_of(fpath):
                        dead.append((path, link, "битый якорь"))
    return dead


def check(dead_only=False):
    dead = []
    warns = []
    for path in md_files():
        for link in links_of(path):
            if link.startswith("#"):
                continue
            if link.startswith("http://") or link.startswith("https://"):
                if dead_only:
                    continue
                req = urllib.request.Request(
                    link, headers={"User-Agent": "humanizer-ru-linkcheck"})
                try:
                    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                        if r.status >= 400:
                            dead.append((path, link, r.status))
                except urllib.error.HTTPError as e:
                    if e.code in (404, 410):
                        dead.append((path, link, e.code))
                    else:
                        warns.append((path, link, e.code))
                except Exception as e:  # таймаут, DNS, 429 — предупреждение
                    warns.append((path, link, type(e).__name__))
            else:
                if "#" in link and not link.startswith("#"):
                    fpart, anchor = link.split("#", 1)
                    if fpart and not fpart.startswith("http"):
                        fpath = os.path.normpath(os.path.join(
                            os.path.dirname(path), fpart))
                        if os.path.isfile(fpath) and anchor:
                            if anchor not in headings_of(fpath):
                                dead.append((path, link, "битый якорь"))
                        continue
                target = link.split("#")[0]
                if not target:
                    continue
                if "/" not in target and not any(target.endswith(e)
                                                 for e in KNOWN_EXT):
                    continue  # одиночное слово или регулярка — не ссылка
                full = os.path.normpath(os.path.join(os.path.dirname(path),
                                                     target))
                if not os.path.exists(full):
                    dead.append((path, link, "local-missing"))
    return dead, warns


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.md")
        b = os.path.join(td, "b.md")
        with open(a, "w", encoding="utf-8") as fh:
            fh.write("[ссылка](b.md#нет-такого)\n")
        with open(b, "w", encoding="utf-8") as fh:
            fh.write("# Заголовок\n\nтекст\n")
        neg_ok = any(reason == "битый якорь"
                     for _p, _l, reason in _check_paths([(a, "b.md#нет-такого")]))
    with tempfile.TemporaryDirectory() as td2:
        a2 = os.path.join(td2, "a.md")
        b2 = os.path.join(td2, "b.md")
        with open(a2, "w", encoding="utf-8") as fh:
            fh.write("[ссылка](b.md#заголовок)\n")
        with open(b2, "w", encoding="utf-8") as fh:
            fh.write("# Заголовок\n\nтекст\n")
        pos_ok = _check_paths([(a2, "b.md#заголовок")]) == []
    checks = [("битый якорь ловится", neg_ok),
              ("живой якорь не ловится", pos_ok)]
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА links: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="проверять только локальные относительные ссылки")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    dead, warns = check(dead_only=args.offline)
    for path, link, code in warns:
        print("WARN %s: %s (%s)" % (os.path.relpath(path, ROOT), link, code))
    for path, link, code in dead:
        print("DEAD %s: %s (%s)" % (os.path.relpath(path, ROOT), link, code))
    print("LINKS: мёртвых %d, предупреждений %d" % (len(dead), len(warns)))
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
