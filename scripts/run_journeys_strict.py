#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_journeys_strict.py — установленные пользовательские сценарии БЕЗ skips.

Приёмка публикации неотделима от исполненных сценариев установленной
поставки: отсутствие подготовленного окружения — ОШИБКА публикации, а не
успешный skip. Раннер исполняет tests/test_installed_user_journeys.py
обычным unittest-прогоном и отвергает результат, если:
  - HUMANIZER_JOURNEY_PYTHON не задан (окружение не подготовлено);
  - хотя бы один тест пропущен (skipped) — обязательные сценарии обязаны
    исполниться, а не молча пропуститься;
  - есть провал или ошибка;
  - исполнено ноль тестов (фикстура отсутствует — это FAIL, не PASS).

CLI:
    python3 scripts/run_journeys_strict.py             # строгий прогон
    python3 scripts/run_journeys_strict.py --selftest  # негативы раннера

Коды: 0 — все сценарии исполнены и зелёные; 1 — skip/провал/ошибка/
окружение не подготовлено/ноль исполненных тестов; 2 — ошибка раннера
(тестовый файл не найден).
"""
import os
import sys
import tempfile
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JOURNEYS = os.path.join(ROOT, "tests", "test_installed_user_journeys.py")


def run_suite(tests_dir, pattern):
    """Прогон набора unittest; (rc, сводка). Ядро раннера — selftest
    вызывает его же на временных заглушках."""
    loader = unittest.TestLoader()
    try:
        suite = loader.discover(tests_dir, pattern=pattern,
                                top_level_dir=tests_dir)
    except Exception as exc:
        return 2, "набор не собран: %r" % exc
    result = unittest.TextTestRunner(verbosity=1, stream=sys.stdout).run(suite)
    executed = result.testsRun
    skipped = [(str(t), r) for t, r in result.skipped]
    summary = ("исполнено %d; пропущено %d; провалов %d; ошибок %d"
               % (executed, len(skipped), len(result.failures),
                  len(result.errors)))
    if executed == 0:
        return 1, "ноль исполненных тестов — фикстура отсутствует: " + summary
    if skipped:
        reasons = "; ".join("%s: %s" % (name.split(" ")[0], reason)
                            for name, reason in skipped[:4])
        return 1, ("обязательные сценарии ПРОПУЩЕНЫ (skip недопустим в "
                   "приёмке публикации): %s | %s" % (reasons, summary))
    if result.failures or result.errors:
        return 1, "провалы/ошибки сценариев: " + summary
    return 0, "все сценарии исполнены: " + summary


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return selftest()
    if not os.path.isfile(JOURNEYS):
        print("ОТКАЗ: %s не найден" % JOURNEYS, file=sys.stderr)
        return 2
    py = os.environ.get("HUMANIZER_JOURNEY_PYTHON") or ""
    if not py or not os.path.isfile(py):
        print("ОТКАЗ: HUMANIZER_JOURNEY_PYTHON не задан или не существует — "
              "установленная поставка не подготовлена; это ошибка приёмки, "
              "а не успешный skip", file=sys.stderr)
        return 1
    rc, summary = run_suite(os.path.dirname(JOURNEYS),
                            "test_installed_user_journeys.py")
    print(("ПРИЁМКА СЦЕНАРИЕВ: " if rc == 0 else "ОТКАЗ: ") + summary)
    return rc


def selftest():
    fails = 0

    def case(name, ok):
        nonlocal fails
        print(("PASS: " if ok else "FAIL: ") + name)
        if not ok:
            fails += 1

    green = ('import unittest\n'
             'class T(unittest.TestCase):\n'
             '    def test_ok(self):\n'
             '        self.assertTrue(True)\n')
    skipping = ('import unittest\n'
                'class T(unittest.TestCase):\n'
                '    @unittest.skip("окружение не подготовлено")\n'
                '    def test_skipped(self):\n'
                '        pass\n'
                '    def test_ok(self):\n'
                '        self.assertTrue(True)\n')
    failing = ('import unittest\n'
               'class T(unittest.TestCase):\n'
               '    def test_fail(self):\n'
               '        self.assertEqual(1, 2)\n')
    with tempfile.TemporaryDirectory(prefix="journeys-strict-") as td:
        with open(os.path.join(td, "test_stub_green.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(green)
        rc, _ = run_suite(td, "test_stub_green.py")
        case("зелёный набор принимается", rc == 0)
        with open(os.path.join(td, "test_stub_skip.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(skipping)
        rc, summary = run_suite(td, "test_stub_skip.py")
        case("skip отвергается (недовольство слышно в сводке)",
             rc == 1 and "ПРОПУЩЕНЫ" in summary)
        os.unlink(os.path.join(td, "test_stub_skip.py"))
        with open(os.path.join(td, "test_stub_fail.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(failing)
        rc, _ = run_suite(td, "test_stub_fail.py")
        case("провал отвергается", rc == 1)
        os.unlink(os.path.join(td, "test_stub_fail.py"))
        os.unlink(os.path.join(td, "test_stub_green.py"))
        empty = tempfile.mkdtemp(prefix="journeys-empty-", dir=td)
        rc, summary = run_suite(empty, "test_*.py")
        case("ноль исполненных тестов отвергается",
             rc == 1 and "ноль исполненных" in summary)
    print("САМОПРОВЕРКА run_journeys_strict: %s"
          % ("OK" if fails == 0 else "ПРОВАЛОВ %d" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
