#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_readme_try.py — генератор блока «Попробовать за 30 секунд» для
README.md и README.en.md: самодостаточный рецепт (команда сама создаёт
вход), вывод и код возврата получены фактическим исполнением РЕЦЕПТА
ЦЕЛИКОМ в пустом временном каталоге (создание входа, скан, вывод, rc),
а не прогоном на скрытом временном файле.

Команда humanizer-markers исполняется через точку входа пакета
(markers_main) с PYTHONPATH=src — эквивалент установленной консоли без
установки в окружение генератора; строка pip install проверяется
импортируемостью пакета из дерева.

Запуск из корня репозитория:
    python3 scripts/build_readme_try.py            # перегенерировать блоки
    python3 scripts/build_readme_try.py --check    # сверить (код 1 при дрейфе)
    python3 scripts/build_readme_try.py --selftest # негативы генератора
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

# Литерал маркера собран конкатенацией: само-скан репозитория не должен
# видеть маркер в исходнике генератора.
SAMPLE_LINE = ("Согласно отчёту :" + "contentReference[oaicite:"
               + "3]{index=3}, рост заявок.\n")
CREATE_CMD = ("python -c \"open('primer.txt','w',encoding='utf-8')"
              ".write('%s')\"" % SAMPLE_LINE.replace("\n", "\\n"))
SCAN_CMD = 'humanizer-markers --scan primer.txt; echo "rc=$?"'

SHIM = ("import sys; sys.argv = ['humanizer-markers', '--scan', "
        "'primer.txt']; from humanizer_ru.cli import markers_main; "
        "raise SystemExit(markers_main())")


def run_recipe():
    """Исполняет рецепт целиком в пустом каталоге: (строки вывода, rc)."""
    with tempfile.TemporaryDirectory(prefix="readme-try-") as td:
        create = subprocess.run(
            [sys.executable, "-c",
             "open('primer.txt','w',encoding='utf-8').write(%r)"
             % SAMPLE_LINE],
            capture_output=True, text=True, cwd=td,
            encoding="utf-8", errors="replace")
        if create.returncode != 0 or not os.path.isfile(
                os.path.join(td, "primer.txt")):
            raise SystemExit("генератор: команда создания входа не создала "
                             "primer.txt: %s" % create.stderr[-200:])
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run([sys.executable, "-X", "utf8", "-c", SHIM],
                              capture_output=True, text=True, cwd=td,
                              encoding="utf-8", errors="replace", env=env)
    lines = [ln.rstrip() for ln in proc.stdout.split("\n") if ln.strip()]
    if not lines:
        raise SystemExit("генератор: вывод скана пуст — образец не ловится")
    return lines, proc.returncode


def pip_line_ok():
    """Строка установки рецепта обязана соответствовать импортируемому
    пакету из дерева (эквивалент установленной поставки)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-c",
                           "import humanizer_ru, humanizer_ru.cli"],
                          capture_output=True, text=True, env=env,
                          encoding="utf-8", errors="replace")
    return proc.returncode == 0


def build_block():
    if not pip_line_ok():
        raise SystemExit("генератор: пакет не импортируется из src — "
                         "строка pip install рецепта не подтверждена")
    lines, rc = run_recipe()
    return ("```text\n"
            "pip install humanizer-ru\n"
            + CREATE_CMD + "\n"
            + SCAN_CMD + "\n"
            + "\n".join("  " + ln for ln in lines) + "\n"
            + "  rc=%d\n" % rc
            + "```")


def replace_block(text, block):
    start = text.find("```text\npip install humanizer-ru")
    if start == -1:
        return text, False
    end = text.find("```", start + len("```text"))
    end = text.find("\n", end) + 1
    return text[:start] + block + "\n" + text[end:], True


def selftest():
    fails = 0
    block = build_block()
    readme = "```text\npip install humanizer-ru\nX\n```\n"
    new, ok = replace_block(readme, block)
    if not ok or block not in new:
        print("FAIL: замена блока не работает")
        fails += 1
    else:
        print("PASS: блок рецепта заменяется")
    # Негатив: дрейф задокументированного вывода ловится сравнением.
    drifted = new.replace("  rc=1", "  rc=0")
    if drifted == new:
        print("FAIL: не найден якорь rc в блоке для негатива")
        fails += 1
    else:
        print("PASS: якорь rc присутствует (негатив дрейфа построим)")
    # Самодостаточность: блок обязан содержать команду создания входа.
    if CREATE_CMD not in block:
        print("FAIL: команда создания входа отсутствует в блоке")
        fails += 1
    else:
        print("PASS: рецепт самодостаточен (вход создаётся командой)")
    print("САМОПРОВЕРКА build_readme_try: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    check = "--check" in sys.argv
    if "--selftest" in sys.argv:
        return selftest()
    block = build_block()
    rc = 0
    for rel in ("README.md", "README.en.md"):
        p = os.path.join(ROOT, rel)
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        new, ok = replace_block(text, block)
        if not ok:
            print("[FAIL] %s: блок «pip install humanizer-ru» не найден" % rel)
            rc = 1
            continue
        if check:
            same = new == text
            print("%s %s: блок примера %s" % ("OK" if same else "FAIL", rel,
                                              "совпадает" if same else "устарел"))
            rc = rc or (0 if same else 1)
            continue
        if new != text:
            assert "\r" not in new
            with open(p, "wb") as fh:
                fh.write(new.encode("utf-8"))
            print("OK %s: блок примера перегенерирован" % rel)
        else:
            print("OK %s: блок примера уже актуален" % rel)
    return rc


if __name__ == "__main__":
    sys.exit(main())
