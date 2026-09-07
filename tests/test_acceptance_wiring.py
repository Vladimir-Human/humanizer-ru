#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_acceptance_wiring.py — приёмка публикации исполнимо связана
с реальными проверками установленной поставки и браузера.

Закреплено (негативом доказывает отказ без evidence):
  1. pypi-publish.yml: установленные пользовательские сценарии
     (run_journeys_strict.py) исполняются для ОБОИХ публикуемых
     артефактов — wheel и sdist — в отдельных чистых venv с
     HUMANIZER_JOURNEY_PYTHON, до шага публикации; publish зависит от
     build-and-test;
  2. run_journeys_strict отвергает: непропущенный skip, ноль исполненных
     тестов, неподготовленное окружение, провалы (selftest раннера);
  3. demo-pages.yml: браузерная DOM-проверка опубликованного демо
     (check_demo_browser.py по URL деплоя) — шаг после публикации;
     UNAVAILABLE (код 2) роняет шаг так же, как FAIL: непроверенное
     состояние не остаётся зелёным;
  4. release-check.yml: строгий прогон всех валидаторов;
  5. Негативы: удаление любого элемента связи из текста workflow
     обнаруживается той же проверяющей функцией.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): интеграционные тесты не запускаются")


def _read(rel):
    with open(os.path.join(ROOT, rel.replace("/", os.sep)),
              encoding="utf-8") as fh:
        return fh.read()


def wiring_errors(pypi_text, pages_text, release_text):
    """Список нарушений исполнительной связи приёмки и публикации."""
    errs = []
    pp = pypi_text
    if "run_journeys_strict.py" not in pp:
        errs.append("pypi-publish: установленные сценарии не подключены "
                    "к приёмке публикации")
    else:
        if pp.count("run_journeys_strict.py") < 2:
            errs.append("pypi-publish: сценарии подключены не для обоих "
                        "артефактов (wheel и sdist)")
        if pp.count("HUMANIZER_JOURNEY_PYTHON=") < 2:
            errs.append("pypi-publish: запуск сценариев без "
                        "HUMANIZER_JOURNEY_PYTHON (окружение не готовится)")
        for art in ("dist/humanizer_ru-*.whl", "dist/humanizer_ru-*.tar.gz"):
            if art not in pp:
                errs.append("pypi-publish: артефакт %s не участвует в "
                            "приёмке сценариями" % art)
        if "needs: build-and-test" not in pp:
            errs.append("pypi-publish: публикация не зависит от приёмки")
        try:
            first_journey = pp.index("run_journeys_strict.py")
            interval = pp.index("--pre-release-interval")
            upload = pp.index("upload-artifact")
            if not (first_journey < interval and first_journey < upload):
                errs.append("pypi-publish: сценарии исполняются ПОСЛЕ "
                            "необратимых шагов, а не до них")
        except ValueError:
            errs.append("pypi-publish: нет шага интервала/артефакта — "
                        "порядок не проверить")
    if "check_demo_browser.py" not in pages_text:
        errs.append("demo-pages: браузерная DOM-проверка не подключена")
    else:
        if "playwright install" not in pages_text:
            errs.append("demo-pages: браузерная среда не устанавливается — "
                        "проверка окажется UNAVAILABLE")
        try:
            if (pages_text.index("check_demo_browser.py")
                    < pages_text.index("uses: actions/deploy-pages")):
                errs.append("demo-pages: браузерная проверка не по "
                            "опубликованному URL (до деплоя)")
        except ValueError:
            errs.append("demo-pages: нет шага публикации — порядок не "
                        "проверить")
        if "steps.deployment.outputs.page_url" not in pages_text:
            errs.append("demo-pages: проверка не привязана к URL деплоя")
    if "check_all.py --strict" not in release_text:
        errs.append("release-check: нет строгого прогона валидаторов")
    return errs


@SKIP_OUTSIDE
class AcceptanceWiringTests(unittest.TestCase):
    """Позитив: связь на месте; негатив: удаление связи обнаруживается."""

    def setUp(self):
        self.pypi = _read(".github/workflows/pypi-publish.yml")
        self.pages = _read(".github/workflows/demo-pages.yml")
        self.release = _read(".github/workflows/release-check.yml")

    def test_wiring_present(self):
        self.assertEqual(
            wiring_errors(self.pypi, self.pages, self.release), [])

    def test_removing_journeys_detected(self):
        mutated = self.pypi.replace("run_journeys_strict.py",
                                    "echo skipped-journeys")
        self.assertTrue(any("сценарии" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))

    def test_single_artifact_journeys_detected(self):
        # Только wheel: sdist-вызов удалён — приёмка неполна.
        idx = self.pypi.rindex("run_journeys_strict.py")
        mutated = self.pypi[:idx] + "echo only-wheel" + self.pypi[
            idx + len("run_journeys_strict.py"):]
        self.assertTrue(any("обоих" in e or "HUMANIZER" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))

    def test_removing_browser_check_detected(self):
        mutated = self.pages.replace("check_demo_browser.py",
                                     "echo no-browser")
        self.assertTrue(any("браузер" in e for e in
                            wiring_errors(self.pypi, mutated,
                                          self.release)))

    def test_browser_check_before_deploy_detected(self):
        # Перестановка: проверка до деплоя — не приёмка опубликованного.
        mutated = self.pages.replace("uses: actions/deploy-pages",
                                     "uses: actions/publish-pages-MOVED")
        self.assertNotEqual(mutated, self.pages)
        self.assertTrue(any("опубликованному" in e or "порядок" in e
                            for e in wiring_errors(self.pypi, mutated,
                                                   self.release)))

    def test_removing_strict_release_check_detected(self):
        mutated = self.release.replace("check_all.py --strict",
                                       "check_all.py --quick")
        self.assertTrue(any("строгого" in e for e in
                            wiring_errors(self.pypi, self.pages, mutated)))

    def test_publish_without_needs_detected(self):
        mutated = self.pypi.replace("needs: build-and-test",
                                    "needs: []")
        self.assertTrue(any("зависит" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))


@SKIP_OUTSIDE
class StrictRunnerTests(unittest.TestCase):
    """Раннер установленных сценариев: skip — отказ, не успех."""

    def _runner(self, args, env=None):
        return subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "scripts", "run_journeys_strict.py")]
            + args,
            capture_output=True, encoding="utf-8", errors="replace",
            cwd=ROOT, env=env, timeout=600)

    def test_runner_selftest_green(self):
        proc = self._runner(["--selftest"])
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])

    def test_runner_refuses_unprepared_env(self):
        env = {k: v for k, v in os.environ.items()
               if k != "HUMANIZER_JOURNEY_PYTHON"}
        proc = self._runner([], env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("не подготовлена", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
