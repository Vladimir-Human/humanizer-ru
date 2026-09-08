#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_release_pipeline_contract.py — путь публикации блокируется
при неверном SHA, неподходящей подписи или непроверенном артефакте;
CI-связки исполняемы и неотделимы от поставки.

Правило интервала публикаций (>= 86400 с) отменено приказом владельца от
2026-09-08 и удалено из проекта: механизмы, флаги, workflow-шаги и файл
одноразовых приказов отсутствуют — это закреплено тестами ниже, чтобы
правило не вернулось случайным образом и его удаление не было частичным.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = (os.path.isdir(os.path.join(ROOT, "scripts"))
             and os.path.isfile(os.path.join(ROOT, ".github", "workflows",
                                             "release-check.yml")))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): workflows и scripts/ недоступны")
if REPO_ONLY:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import check_release as CR  # noqa: E402
else:  # pragma: no cover — sdist без scripts/
    CR = None
sys.path.insert(0, os.path.join(ROOT, "src"))

RELEASE_CHECK = os.path.join(ROOT, ".github", "workflows",
                             "release-check.yml")
PYPI_PUBLISH = os.path.join(ROOT, ".github", "workflows",
                            "pypi-publish.yml")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@SKIP_OUTSIDE
class WorkflowBindingTests(unittest.TestCase):
    """Проверки исполняемых зависимостей публикации (текст workflow)."""

    def setUp(self):
        self.rc = _read(RELEASE_CHECK)
        self.pp = _read(PYPI_PUBLISH)
        self.build_section = self.pp.split("  publish:")[0]

    def test_release_check_strict(self):
        self.assertIn("check_all.py --strict", self.rc)

    def test_release_check_crypto(self):
        self.assertIn("--release-contract", self.rc)

    def test_release_check_explicit_tag_input(self):
        self.assertIn("workflow_dispatch", self.rc)
        self.assertIn("inputs:", self.rc)
        self.assertIn("inputs.tag", self.rc)
        self.assertIn("required: true", self.rc)
        self.assertIn("ref: ${{ inputs.tag || github.ref_name }}", self.rc)

    def test_publish_workflows_checkout_selected_tag(self):
        self.assertIn("inputs.tag", self.pp)
        self.assertIn("required: true", self.pp)
        self.assertIn("ref: ${{ inputs.tag || github.ref_name }}", self.pp)

    def test_publish_needs_verified_build(self):
        self.assertIn("needs: build-and-test", self.pp)

    def test_interval_steps_absent_from_workflows(self):
        # Правило отменено: шаги интервала отсутствуют в обоих workflow;
        # необратимый шаг публикации по-прежнему отделён приёмкой
        # (sdist-test и metadata исполняются до артефакта).
        for text, name in ((self.rc, "release-check"),
                           (self.pp, "pypi-publish")):
            self.assertNotIn("--pre-release-interval", text, name)
            self.assertNotIn("--post-publication-interval", text, name)
        self.assertLess(self.build_section.index("--sdist-test"),
                        self.build_section.index("upload-artifact"))
        self.assertLess(self.build_section.index("check_pypi_metadata.py"),
                        self.build_section.index("upload-artifact"))

    def test_strict_and_facts_in_publish_path(self):
        self.assertIn("check_all.py --strict", self.build_section)
        self.assertIn("check_facts.py --strict-publication",
                      self.build_section)
        self.assertIn("check_compatibility.py", self.build_section)

    def test_same_artifacts_for_metadata_and_publish(self):
        # metadata сверяются у тех же dist-файлов, которые уходят в
        # артефакт публикации (path: dist/).
        self.assertIn("--sdist dist/humanizer_ru-*.tar.gz",
                      self.build_section)
        self.assertIn("path: dist/", self.pp)


@SKIP_OUTSIDE
class IntervalRetirementTests(unittest.TestCase):
    """Отмена правила интервала: механизм удалён целиком, не частично."""

    def test_interval_machinery_absent_from_module(self):
        for name in ("MIN_RELEASE_INTERVAL", "interval_errors",
                     "load_interval_waivers", "waiver_allows",
                     "pre_release_interval", "post_release_interval",
                     "WAIVED_INTERVAL_PAIRS"):
            self.assertFalse(hasattr(CR, name),
                             "check_release всё ещё несёт %s" % name)

    def test_waivers_file_removed(self):
        self.assertFalse(os.path.exists(
            os.path.join(ROOT, "docs", "release-waivers.json")),
            "docs/release-waivers.json должен быть удалён вместе с "
            "правилом")

    def test_cli_rejects_interval_flags(self):
        # Флаги удалены из CLI: argparse отвечает кодом 2 (неизвестный
        # аргумент) — тихого принятия удалённого флага нет.
        for flag in ("--pre-release-interval",
                     "--post-publication-interval"):
            proc = subprocess.run(
                [sys.executable, "-X", "utf8",
                 os.path.join(ROOT, "scripts", "check_release.py"), flag],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120)
            self.assertEqual(proc.returncode, 2,
                             "%s принят после отмены правила" % flag)

    def test_release_md_records_retirement(self):
        text = _read(os.path.join(ROOT, "RELEASE.md")).lower()
        self.assertIn("отменено", text)
        self.assertIn("2026-09-08", text)


@SKIP_OUTSIDE
class AcceptanceBlockingTests(unittest.TestCase):
    """Приёмка статуса: непроверенное не утверждается."""

    def test_foreign_sha_blocked(self):
        status = {"commit": "abc1234", "tests_passed": True, "parity": "ok"}
        result = {"sha": "deadbeef", "tests_passed": True, "parity": "ok"}
        errs = CR.status_acceptance_errors(status, result, "deadbeef")
        self.assertTrue(errs)

    def test_missing_run_result_blocked(self):
        status = {"commit": "abc1234", "tests_passed": True, "parity": "ok"}
        self.assertTrue(CR.status_acceptance_errors(status, None, "abc1234f"))

    def test_false_tests_passed_blocked(self):
        status = {"commit": "abc1234", "tests_passed": True, "parity": "ok"}
        result = {"sha": "abc1234f", "tests_passed": False, "parity": "ok"}
        self.assertTrue(CR.status_acceptance_errors(status, result,
                                                    "abc1234f"))


if __name__ == "__main__":
    unittest.main()
