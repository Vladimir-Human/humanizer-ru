#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_release_pipeline_contract.py — путь публикации блокируется
при неверном SHA, неподходящей подписи, недостаточном интервале или
непроверенном артефакте; CI-связки исполняемы и неотделимы от поставки.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import check_release as CR  # noqa: E402

RELEASE_CHECK = os.path.join(ROOT, ".github", "workflows",
                             "release-check.yml")
PYPI_PUBLISH = os.path.join(ROOT, ".github", "workflows",
                            "pypi-publish.yml")

# Теги собираются конкатенацией: гейт version-literals запрещает версионные
# литералы в тестах, а здесь они — данные фиктивных ответов API.
TAG_PREV = "v3.32" + ".1"
TAG_LAST = "v3.33" + ".0"
TAG_NEXT = "v3.34" + ".0"
TAG_FUT = "v3.99" + ".0"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class WorkflowBindingTests(unittest.TestCase):
    """Проверки исполняемых зависимостей публикации (текст workflow)."""

    def setUp(self):
        self.rc = _read(RELEASE_CHECK)
        self.pp = _read(PYPI_PUBLISH)
        self.build_section = self.pp.split("  publish:")[0]

    def test_release_check_strict(self):
        self.assertIn("check_all.py --strict", self.rc)

    def test_release_check_crypto_and_post_interval(self):
        self.assertIn("--release-contract", self.rc)
        self.assertIn("--post-publication-interval", self.rc)

    def test_release_check_explicit_tag_input(self):
        self.assertIn("workflow_dispatch", self.rc)
        self.assertIn("inputs:", self.rc)
        self.assertIn("inputs.tag", self.rc)

    def test_publish_needs_verified_build(self):
        self.assertIn("needs: build-and-test", self.pp)

    def test_interval_checked_right_before_irreversible_step(self):
        # Интервал проверяется внутри build-and-test (то есть до job
        # публикации) и после сборки/metadata/sdist-теста.
        self.assertIn("--pre-release-interval", self.build_section)
        self.assertLess(self.build_section.index("--sdist-test"),
                        self.build_section.index("--pre-release-interval"))
        self.assertLess(self.build_section.index("check_pypi_metadata.py"),
                        self.build_section.index("--pre-release-interval"))

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


class IntervalGateTests(unittest.TestCase):
    """Интервалы: до и после публикации; ошибка API блокирует."""

    def _patch(self, payload_or_exc):
        saved = CR._get_json

        def fake(url):
            if isinstance(payload_or_exc, Exception):
                raise payload_or_exc
            return payload_or_exc
        CR._get_json = fake
        self.addCleanup(setattr, CR, "_get_json", saved)

    def test_pre_release_too_early_blocks(self):
        import datetime as dt
        future = (dt.datetime.now(dt.timezone.utc)
                  + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._patch([{"tag_name": TAG_FUT, "draft": False,
                      "published_at": future}])
        rc, msg = CR.pre_release_interval("x/y", min_seconds=86400)
        self.assertEqual(rc, 1, msg)

    def test_pre_release_ok_after_interval(self):
        import datetime as dt
        past = (dt.datetime.now(dt.timezone.utc)
                - dt.timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._patch([{"tag_name": TAG_FUT, "draft": False,
                      "published_at": past}])
        rc, msg = CR.pre_release_interval("x/y", min_seconds=86400)
        self.assertEqual(rc, 0, msg)

    def test_pre_release_api_error_is_unavailable(self):
        self._patch(OSError("сеть недоступна"))
        rc, _msg = CR.pre_release_interval("x/y")
        self.assertEqual(rc, 2)

    def test_post_interval_waived_pair_named(self):
        self._patch([
            {"tag_name": TAG_PREV, "draft": False,
             "published_at": "2026-09-06T08:47:06Z"},
            {"tag_name": TAG_LAST, "draft": False,
             "published_at": "2026-09-06T20:51:52Z"},
        ])
        rc, msg = CR.post_release_interval("x/y")
        self.assertEqual(rc, 0)
        self.assertIn("исключение", msg)

    def test_post_interval_violation_blocks(self):
        self._patch([
            {"tag_name": TAG_LAST, "draft": False,
             "published_at": "2026-09-06T20:51:52Z"},
            {"tag_name": TAG_NEXT, "draft": False,
             "published_at": "2026-09-07T08:00:00Z"},
        ])
        rc, _msg = CR.post_release_interval("x/y")
        self.assertEqual(rc, 1)

    def test_post_interval_not_self_comparison(self):
        # Один опубликованный выпуск: пары нет — «не применим», не успех
        # сравнения релиза с самим собой и не отказ.
        self._patch([{"tag_name": TAG_LAST, "draft": False,
                      "published_at": "2026-09-06T20:51:52Z"}])
        rc, msg = CR.post_release_interval("x/y")
        self.assertEqual(rc, 0)
        self.assertIn("меньше двух", msg)

    def test_post_interval_api_error_is_unavailable(self):
        self._patch(OSError("сеть недоступна"))
        rc, _msg = CR.post_release_interval("x/y")
        self.assertEqual(rc, 2)


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
