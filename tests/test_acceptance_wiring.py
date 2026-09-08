#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_acceptance_wiring.py — приёмка публикации исполнимо связана
с реальными проверками установленной поставки и браузера.

Поиск строки в YAML не доказывает исполнение: связь проверяется по
ДЕЙСТВУЮЩИМ вхождениям команд. Вхождение считается недействующим
(отключённым), если: строка — комментарий; перед командой в строке есть
«||», «&&», «;», «echo», «false», «true», «if », «!» (обвязки вроде
`false || echo python3 …`); после команды — «||», «&&», «;» или
комментарий (`… || true`); шаг несёт `continue-on-error: true` или
`if: false`. Наличие хотя бы одного действующего вхождения обязательно
для каждой связи.

Закреплено (негативом доказывает отказ без evidence):
  1. pypi-publish.yml: установленные пользовательские сценарии
     (run_journeys_strict.py) исполняются для ОБОИХ публикуемых
     артефактов — wheel и sdist — в отдельных чистых venv с
     HUMANIZER_JOURNEY_PYTHON, до шага публикации; publish зависит от
     build-and-test;
  2. run_journeys_strict отвергает: любой skip, ноль исполненных тестов,
     неподготовленное окружение, провалы (selftest раннера);
  3. pypi-publish.yml: браузерная DOM-проверка демо КАНДИДАТА до
     публикации — блокирует саму публикацию;
  4. demo-pages.yml: браузерная DOM-проверка ОПУБЛИКОВАННОГО URL после
     деплоя — честное разделение: она НЕ отменяет уже выполненный deploy
     и не «предотвращает публикацию»; она роняет workflow Pages и
     блокирует ОБЪЯВЛЕНИЕ поставки проверенной (реестр поставки требует
     её результата). UNAVAILABLE (код 2) роняет шаг так же, как FAIL;
  5. release-check.yml: строгий прогон всех валидаторов;
  6. Негативы: удаление и ОТКЛЮЧЕНИЕ любого элемента связи
     (echo-обёртка, `false ||`, `|| true`, комментарий,
     continue-on-error) обнаруживается той же проверяющей функцией.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): интеграционные тесты не запускаются")

_STEP_START = re.compile(r"^\s*-\s+(name|uses|run|if|continue-on-error):")
_PREFIX_DISABLE = ("||", "&&", ";", "echo", "false", "true", "if ", "!")
_SUFFIX_DISABLE = ("||", "&&", ";")


def _read(rel):
    with open(os.path.join(ROOT, rel.replace("/", os.sep)),
              encoding="utf-8") as fh:
        return fh.read()


def _line_index(text, needle):
    """Номер первой строки, содержащей needle (None если нет)."""
    for i, ln in enumerate(text.split("\n")):
        if needle in ln:
            return i
    return None


def effective_lines(text, command):
    """Номера строк с ДЕЙСТВУЮЩИМ (не отключённым) вызовом command."""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if _STEP_START.match(ln)]
    hits = []
    for i, ln in enumerate(lines):
        pos = ln.find(command)
        if pos < 0:
            continue
        s = ln.strip()
        if s.startswith("#"):
            continue
        sp = s.find(command)
        prefix = s[:sp].lower()
        suffix = s[sp + len(command):].lower()
        if any(tok in prefix for tok in _PREFIX_DISABLE):
            continue
        if any(tok in suffix for tok in _SUFFIX_DISABLE) or " #" in suffix:
            continue
        # Уровень шага: continue-on-error / if: false внутри чанка шага.
        chunk_start = max((st for st in starts if st <= i), default=None)
        if chunk_start is not None:
            chunk_end = min((st for st in starts if st > i),
                            default=len(lines))
            body = "\n".join(lines[chunk_start:chunk_end]).lower()
            if "continue-on-error: true" in body or \
                    re.search(r"if:\s*false\b", body):
                continue
        hits.append(i)
    return hits


def wiring_errors(pypi_text, pages_text, release_text):
    """Список нарушений исполнительной связи приёмки и публикации."""
    errs = []
    pp = pypi_text
    journey_hits = effective_lines(pp, "run_journeys_strict.py")
    if not journey_hits:
        errs.append("pypi-publish: установленные сценарии не подключены "
                    "к приёмке публикации (или вызов отключён обёрткой)")
    else:
        if len(journey_hits) < 2:
            errs.append("pypi-publish: сценарии подключены не для обоих "
                        "артефактов (wheel и sdist)")
        pp_lines = pp.split("\n")
        env_hits = [i for i in journey_hits
                    if "HUMANIZER_JOURNEY_PYTHON=" in pp_lines[i]]
        if len(env_hits) < 2:
            errs.append("pypi-publish: запуск сценариев без "
                        "HUMANIZER_JOURNEY_PYTHON (окружение не готовится)")
        for art in ("dist/humanizer_ru-*.whl", "dist/humanizer_ru-*.tar.gz"):
            if art not in pp:
                errs.append("pypi-publish: артефакт %s не участвует в "
                            "приёмке сценариями" % art)
        if "needs: build-and-test" not in pp:
            errs.append("pypi-publish: публикация не зависит от приёмки")
        upload = _line_index(pp, "upload-artifact")
        if upload is None:
            errs.append("pypi-publish: нет шага артефакта — порядок не "
                        "проверить")
        elif min(journey_hits) > upload:
            errs.append("pypi-publish: сценарии исполняются ПОСЛЕ "
                        "необратимых шагов, а не до них")
    # Браузерная проверка кандидата — до публикации (в build-and-test).
    publish_job = _line_index(pp, "\n  publish:")
    cand_hits = effective_lines(pp, "check_demo_browser.py")
    if not cand_hits:
        errs.append("pypi-publish: браузерная проверка демо кандидата до "
                    "публикации отсутствует или отключена")
    elif publish_job is not None and min(cand_hits) > publish_job:
        errs.append("pypi-publish: браузерная проверка кандидата не в "
                    "build-and-test (после job публикации)")
    # Браузерная проверка ОПУБЛИКОВАННОГО URL — после деплоя; она не
    # отменяет deploy, но блокирует объявление поставки проверенной.
    pages_hits = effective_lines(pages_text, "check_demo_browser.py")
    if not pages_hits:
        errs.append("demo-pages: браузерная DOM-проверка опубликованного "
                    "демо отсутствует или отключена")
    else:
        if "playwright install" not in pages_text:
            errs.append("demo-pages: браузерная среда не устанавливается — "
                        "проверка окажется UNAVAILABLE")
        deploy = _line_index(pages_text, "uses: actions/deploy-pages")
        if deploy is None:
            errs.append("demo-pages: нет шага публикации — порядок не "
                        "проверить")
        elif min(pages_hits) < deploy:
            errs.append("demo-pages: браузерная проверка не по "
                        "опубликованному URL (до деплоя)")
        if "steps.deployment.outputs.page_url" not in pages_text:
            errs.append("demo-pages: проверка не привязана к URL деплоя")
    if not effective_lines(release_text, "check_all.py --strict"):
        errs.append("release-check: нет строгого прогона валидаторов "
                    "(или он отключён)")
    return errs


@SKIP_OUTSIDE
class AcceptanceWiringTests(unittest.TestCase):
    """Позитив: связь на месте; негатив: удаление И отключение связи
    обнаруживаются."""

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

    def test_disabled_journeys_with_false_prefix_detected(self):
        # Регрессия R4-класса: обёртка `false ||` делает вызов декорацией.
        mutated = self.pypi.replace(
            "python3 scripts/run_journeys_strict.py",
            "false || echo python3 scripts/run_journeys_strict.py")
        self.assertTrue(any("сценарии" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))

    def test_disabled_with_or_true_detected(self):
        mutated = self.pypi.replace(
            "python3 scripts/run_journeys_strict.py",
            "python3 scripts/run_journeys_strict.py || true")
        self.assertTrue(any("сценарии" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))

    def test_continue_on_error_step_detected(self):
        mutated = self.pages.replace(
            "      - name: Браузерная DOM-проверка опубликованного демо",
            "      - name: Браузерная DOM-проверка опубликованного демо\n"
            "        continue-on-error: true")
        self.assertNotEqual(mutated, self.pages)
        self.assertTrue(any("браузерная" in e.lower() for e in
                            wiring_errors(self.pypi, mutated,
                                          self.release)))

    def test_commented_candidate_browser_detected(self):
        mutated = self.pypi.replace(
            "python3 scripts/check_demo_browser.py",
            "# python3 scripts/check_demo_browser.py")
        self.assertTrue(any("кандидата" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))

    def test_missing_candidate_browser_detected(self):
        mutated = self.pypi.replace("check_demo_browser.py",
                                    "check_demo_absent.py")
        self.assertTrue(any("кандидата" in e for e in
                            wiring_errors(mutated, self.pages,
                                          self.release)))

    def test_removing_browser_check_detected(self):
        mutated = self.pages.replace("check_demo_browser.py",
                                     "echo no-browser")
        self.assertTrue(any("браузер" in e.lower() for e in
                            wiring_errors(self.pypi, mutated,
                                          self.release)))

    def test_disabled_browser_check_false_prefix_detected(self):
        # Точная репродукция подтверждённого обхода: замена браузерного
        # вызова на `false || echo python3 …` обязана обнаруживаться.
        mutated = self.pages.replace(
            "python3 scripts/check_demo_browser.py",
            "false || echo python3 scripts/check_demo_browser.py")
        self.assertTrue(any("браузер" in e.lower() for e in
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
