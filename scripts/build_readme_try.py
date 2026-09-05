#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_readme_try.py — генератор блока «Попробовать за 30 секунд» для
README.md и README.en.md: реальный вывод humanizer-markers --scan на
образце, нейтральный путь primer.txt (вход и вывод — один и тот же прогон).

Запуск из корня репозитория:
    python3 scripts/build_readme_try.py [--check]

--check — не писать, а сверить текущий блок с регенерацией (код 1 при
расхождении). Генератор детерминирован: образец фиксирован, вывод CLI
стабилен, путь заменяется на primer.txt.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE = ("Согласно отчёту :" + "contentReference[oaicite:" + "3]{index=3}, "
          "рост заявок за неделю 12%: https://example.com/r?utm_source=" +
          "chatgpt.com\nДанные подтверждены ассистентом\u200b, подробности "
          "в чате.\n")


def build_block():
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(SAMPLE)
        proc = subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "scripts", "check_markers.py"),
             "--scan", path],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=ROOT)
    finally:
        os.unlink(path)
    lines = []
    for ln in proc.stdout.split("\n"):
        ln = ln.rstrip()
        if not ln or ln.startswith("Найдено"):
            continue
        # нейтральный путь: временный файл прогона заменяется на primer.txt
        if ln.startswith(path):
            ln = "primer.txt" + ln[len(path):]
        lines.append("  " + ln)
        if len(lines) == 3:
            break
    if not lines:
        raise SystemExit("генератор: вывод скана пуст — образец не ловится")
    return ("```text\n"
            "pip install humanizer-ru\n"
            "humanizer-markers --scan primer.txt\n"
            + "\n".join(lines) + "\n"
            "```")


def replace_block(text, block):
    start = text.find("```text\npip install humanizer-ru")
    if start == -1:
        return text, False
    end = text.find("```", start + len("```text"))
    end = text.find("\n", end) + 1
    return text[:start] + block + "\n" + text[end:], True


def main():
    check = "--check" in sys.argv
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
