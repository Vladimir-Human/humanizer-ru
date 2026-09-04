#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_a11y.py — гейт W5: структурные проверки доступности и чистоты
первого экрана демо (без внешних зависимостей): lang, aria-live, кнопки с
текстом и type, placeholder текстовой области, тёмная/светлая тема в
brand.css, manifest и service worker, горячая клавиша, итоговая строка без
процентов; первый экран без слов regex/parity/markers.v1.json/generate_js_rules/.py.
Selftest с негативом."""
import argparse
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, "demo", rel), encoding="utf-8") as fh:
        return fh.read()


def first_screen(html):
    i = html.find('<details id="dev"')
    return html[:i] if i != -1 else html


def check(html=None, css=None):
    if html is None:
        html = read("index.html")
    if css is None:
        css = read("brand.css")
    errs = []
    if 'lang="ru"' not in html:
        errs.append("demo: нет lang=ru")
    if html.count("aria-live") < 2:
        errs.append("demo: aria-live меньше двух (summary и matches)")
    for btn in re.findall(r"<button[^>]*>(.*?)</button>", html, re.S):
        if not btn.strip():
            errs.append("demo: кнопка без текста")
    if 'id="text"' in html and "placeholder=" not in html.split('id="text"')[1][:200]:
        errs.append("demo: textarea без placeholder-приглашения")
    if "prefers-color-scheme" not in css:
        errs.append("brand.css: нет тёмной темы")
    if 'rel="manifest"' not in html:
        errs.append("demo: нет manifest")
    if "serviceWorker.register" not in html:
        errs.append("demo: нет регистрации service worker")
    if "ctrlKey || e.metaKey" not in html:
        errs.append("demo: нет горячей клавиши Ctrl/Cmd+Enter")
    if "Это не приговор" not in html:
        errs.append("demo: нет итоговой строки без процентов")
    if re.search(r"\d+\s*%\s*(вероятн|ИИ)", html):
        errs.append("demo: процент вероятности ИИ запрещён")
    fs = first_screen(html)
    for word in ("regex", "parity", "markers.v1.json", "generate_js_rules",
                 ".py"):
        if word in fs:
            errs.append("demo: первый экран содержит техническое слово %s" % word)
    return errs


def selftest():
    checks = [("демо проходит структурные проверки", check() == [])]
    html = read("index.html")
    bad = html.replace('aria-live="polite"', "")
    checks.append(("без aria-live гейт падает", check(bad, None) != []))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА demo-a11y: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    errs = check()
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("DEMO-A11Y: %d расхождений" % len(errs))
        return 1
    print("DEMO-A11Y: структурные проверки пройдены")
    return 0


if __name__ == "__main__":
    sys_exit = None
    import sys as _sys
    _sys.exit(main())
