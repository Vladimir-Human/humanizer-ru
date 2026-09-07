#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_perf_regex.py — F13: статический ReDoS-контроль сигнатур маркеров
(вложенные кванторы) + линейность scan на 5 МБ фикстуре + bounded-time
прогон всех выражений по провокационным входам в дочернем процессе.

Опасной считается группа с внешним квантором + или *, внутри которой есть
собственный квантор + или * без обязательного разделителя (запятая, точка
с запятой, двоеточие) между итерируемыми частями: перекрытие итераций даёт
квадратичный и хуже перебор. Внешний квантор ? безопасен (одна итерация).
Исключения привязаны к СОДЕРЖАНИМУ выражения, а не к имени правила:
подмена паттерна у ранее безопасного имени ловится гейтом.

Запуск:
  python3 scripts/check_perf_regex.py
  python3 scripts/check_perf_regex.py --selftest
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import check_markers as cm  # noqa: E402

# Группа с внешним квантором (тело без вложенных скобок, экранирования
# допускаются); внешний квантор берём сразу за закрывающей скобкой.
GROUP_Q_RX = re.compile(r"\((?:[^()\\]|\\.)*\)([+*?]|\{\d+,?\d*\})")
_INNER_Q_RX = re.compile(r"[+*]")
_SEP_RX = re.compile(r"[,;:]")


def _group_dangerous(pat: str, m) -> bool:
    outer = m.group(1)
    if outer.startswith("?"):
        return False
    if outer.startswith("{") and "," not in outer:
        return False  # {n} — фиксированное число повторений
    body = pat[m.start() + 1:m.end() - len(outer) - 1]
    if not _INNER_Q_RX.search(body):
        return False
    return not _SEP_RX.search(body)


def nested_patterns():
    """Имена правил с опасными вложенными кванторами (структурно)."""
    out = []
    for name, case in cm.CASES.items():
        pat = case[0]
        for m in GROUP_Q_RX.finditer(pat):
            if _group_dangerous(pat, m):
                out.append(name)
                break
    return out


# Имена, ранее освобождённые именным белым списком (до 2026-09-07):
# безопасность каждого теперь проверяется структурно (_group_dangerous);
# список сохранён как документ истории и для самопроверки того, что
# содержательное правило покрывает прежние исключения.
SAFE_NESTED = {"assistants_source", "gemini_cite_n", "deepseek_line_ref",
               "placeholder_url"}


_CHILD_PROBE = (
    "import re, sys, time\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import check_markers as cm\n"
    "texts = ['a' * 300 + '!', '0' * 300 + '!', ' ' * 300 + '!',\n"
    "         ': ' * 150 + '!', 'a,' * 150 + '!']\n"
    "t0 = time.time()\n"
    "for name, case in cm.CASES.items():\n"
    "    rx = re.compile(case[0])\n"
    "    for t in texts:\n"
    "        rx.search(t)\n"
    "print('OK %.2f' % (time.time() - t0))\n"
)


def bounded_probe(timeout_s=60):
    """Прогон всех выражений по провокационным входам в дочернем процессе
    с ограничением времени: зависшее выражение не тянет гейт в
    бесконечность. Возвращает (ok, сообщение)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(_CHILD_PROBE)
        child = fh.name
    try:
        proc = subprocess.run([sys.executable, "-X", "utf8", child, HERE],
                              capture_output=True, text=True,
                              timeout=timeout_s, encoding="utf-8",
                              errors="replace")
    except subprocess.TimeoutExpired:
        return False, ("дочерний прогон выражений не уложился в %d с "
                       "(подозрение на катастрофический перебор)" % timeout_s)
    finally:
        try:
            os.unlink(child)
        except OSError:
            pass
    if proc.returncode != 0:
        return False, ("дочерний прогон выражений упал: %s"
                       % proc.stderr[-200:])
    return True, "bounded-прогон выражений: %s" % proc.stdout.strip()


def linearity_ok(limit_s=30.0):
    text = ("Живой человеческий текст без артефактов копипасты. "
            "Обычные предложения без служебных меток чат-интерфейсов.\n") * 60000
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        t0 = time.time()
        cm.scan([path])
        dt = time.time() - t0
    finally:
        os.unlink(path)
    return dt <= limit_s, dt


def selftest():
    checks = []
    checks.append(("чистые сигнатуры без опасных вложенных кванторов",
                   nested_patterns() == []))
    bad = {"x": ["(a+)+ b", "A"]}
    saved = cm.CASES
    cm.CASES = dict(saved)
    cm.CASES["__quadratic__"] = bad["x"]
    try:
        checks.append(("квадратичное правило ловится статически",
                       "__quadratic__" in nested_patterns()))
        # Мутант name-exempt: подмена паттерна у имени из прежнего белого
        # списка обязана ловиться (исключение содержательное, не именное).
        cm.CASES["assistants_source"] = ["(a+)+$"] + list(
            saved["assistants_source"][1:])
        checks.append(("подмена паттерна у освобождённого имени ловится",
                       "assistants_source" in nested_patterns()))
    finally:
        cm.CASES = saved
    ok, dt = linearity_ok()
    checks.append(("линейность scan на 5 МБ не выше 30 с (%.1f с)" % dt, ok))
    ok_b, msg_b = bounded_probe()
    checks.append((msg_b, ok_b))
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА perf-regex: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    bad = nested_patterns()
    if bad:
        print("PERF-REGEX: опасные вложенные кванторы в сигнатурах: %s" % bad)
        return 1
    ok, dt = linearity_ok()
    if not ok:
        print("PERF-REGEX: scan 5 МБ занял %.1f с выше порога 30 с" % dt)
        return 1
    ok_b, msg_b = bounded_probe()
    if not ok_b:
        print("PERF-REGEX: %s" % msg_b)
        return 1
    print("PERF-REGEX: пройден (опасных вложенных кванторов нет, 5 МБ за "
          "%.1f с, %s)" % (dt, msg_b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
