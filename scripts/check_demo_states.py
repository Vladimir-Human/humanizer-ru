#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_states.py — состояния демо и честный статус (аудит L5).

Структурные проверки реального кода страницы и генератора статуса:
- отсутствие движка или правил даёт явный отказ, а не пустой «чистый» результат;
- предупреждение о помещении текста в ссылку стоит ДО изменения URL;
- переход к своему тексту очищает share-state;
- лимит ссылки считается в байтах после кодирования;
- футер различает null-lag (сведений о релизе нет) и нулевой лаг;
- write_status отдаёт null-lag при отсутствии тегов и целое при наличии.

Коды: 0 — проверки пройдены; 1 — есть нарушение; 2 — ошибка запуска.
Только стандартная библиотека.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def check_html(html):
    errs = []
    if "engineReady()" not in html or "if (!engineReady())" not in html:
        errs.append("demo: нет явной ветви недоступного движка/правил")
    if "проверка не выполнялась" not in html:
        errs.append("demo: отказ проверки не помечен текстом состояния")
    warn = html.find("Ссылка получит ваш текст")
    assign = html.find("location.hash = encodeURIComponent(text)")
    if warn == -1 or assign == -1 or warn > assign:
        errs.append("demo: предупреждение о тексте в ссылке не предшествует "
                    "изменению URL")
    if "history.replaceState" not in html:
        errs.append("demo: переход к своему тексту не очищает share-state")
    if "TextEncoder" not in html or "65536" not in html:
        errs.append("demo: лимит ссылки не считается в байтах после кодирования")
    if "сведений о релизе нет" not in html:
        errs.append("demo: футер не различает неизвестный релиз и нулевой лаг")
    return errs


def check_status_gen():
    errs = []
    with tempfile.TemporaryDirectory() as td:
        docs = os.path.join(td, "docs")
        demo = os.path.join(td, "demo")
        os.makedirs(docs)
        os.makedirs(demo)
        with open(os.path.join(td, "markers.v1.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"count": 40}, fh)
        env = dict(os.environ, GIT_CONFIG_COUNT="2",
                   GIT_CONFIG_KEY_0="user.name",
                   GIT_CONFIG_VALUE_0="t",
                   GIT_CONFIG_KEY_1="user.email",
                   GIT_CONFIG_VALUE_1="t@example.com")
        subprocess.run(["git", "init", "-q", td], check=True, env=env)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                       cwd=td, check=True, env=env)
        r = subprocess.run([sys.executable, os.path.join(HERE,
                            "write_status.py"), "--root", td, "--sha", "abc"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return ["write_status не запустился на пустом репозитории: "
                    + r.stderr.strip()[:120]]
        data = json.load(open(os.path.join(docs, "status.json"),
                              encoding="utf-8"))
        if data.get("lag_commits") is not None:
            errs.append("write_status: без тегов lag_commits обязан быть null")
        if data.get("published_commit") is not None:
            errs.append("write_status: без тегов published_commit обязан быть null")
        subprocess.run(["git", "tag", "v%d.%d.%d" % (1, 0, 0)], cwd=td,
                       check=True, env=env)
        subprocess.run([sys.executable, os.path.join(HERE, "write_status.py"),
                        "--root", td],
                       capture_output=True, text=True, check=True)
        data = json.load(open(os.path.join(docs, "status.json"),
                              encoding="utf-8"))
        if not isinstance(data.get("lag_commits"), int):
            errs.append("write_status: с тегом lag_commits обязан быть целым")
    return errs


def check():
    html = open(os.path.join(ROOT, "demo", "index.html"),
                encoding="utf-8").read()
    return check_html(html) + check_status_gen()


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    case("живая страница демо проходит проверки", check_html(
        open(os.path.join(ROOT, "demo", "index.html"),
             encoding="utf-8").read()) == [])
    bad = open(os.path.join(ROOT, "demo", "index.html"),
               encoding="utf-8").read()
    bad = bad.replace("Ссылка получит ваш текст", "Ссылка создана")
    case("предупреждение после изменения URL ловится",
         any("не предшествует" in e for e in check_html(bad)))
    bad2 = bad.replace("Ссылка создана", "Ссылка получит ваш текст")
    bad2 = bad2.replace("if (!engineReady())", "if (false)")
    case("скрытая ветвь отказа движка ловится",
         any("движка" in e for e in check_html(bad2)))
    case("генератор статуса: null без тегов, целое с тегом",
         check_status_gen() == [])
    print("САМОПРОВЕРКА demo-states: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    errs = check()
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("DEMO-STATES: %d нарушений" % len(errs))
        return 1
    print("DEMO-STATES: состояния демо и статус честные")
    return 0


if __name__ == "__main__":
    sys.exit(main())
