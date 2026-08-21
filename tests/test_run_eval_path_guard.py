#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты path-guard'а _safe_path и интеграции run() из eval/run_eval.py.

Манифест eval-прогона — недоверенный ввод: путь записи корпуса не должен
уводить за корень репозитория. Проверяем отказ при:
  - абсолютном пути;
  - выходе через «..»;
  - букве диска Windows и обратном слэше;
  - символической ссылке внутри корня на файл вне корня (если symlink
    доступен на платформе).

И положительный контроль: обычный относительный путь внутри корня проходит
и разворачивается в realpath.
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "eval")
if EVAL not in sys.path:
    sys.path.insert(0, EVAL)

import run_eval  # noqa: E402


class TestSafePathRejectsTraversal(unittest.TestCase):
    def test_absolute_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            secret = os.path.join(root, "secret.txt")
            with self.assertRaises(run_eval.ManifestError):
                run_eval._safe_path(secret, root)

    def test_parent_directory_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            rel = os.path.join("..", "outside.txt")
            with self.assertRaises(run_eval.ManifestError):
                run_eval._safe_path(rel, root)

    def test_parent_with_backslash_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(run_eval.ManifestError):
                run_eval._safe_path(r"..\outside.txt", root)

    def test_windows_drive_letter_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(run_eval.ManifestError):
                run_eval._safe_path(r"C:\Windows\system32\drivers\etc\hosts", root)

    def test_empty_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(run_eval.ManifestError):
                run_eval._safe_path("", root)
            with self.assertRaises(run_eval.ManifestError):
                run_eval._safe_path("   ", root)

    def test_symlink_pointing_outside_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with tempfile.TemporaryDirectory() as outside:
                secret = os.path.join(outside, "secret.txt")
                with open(secret, "w", encoding="utf-8") as fh:
                    fh.write("данные вне корня")
                link = os.path.join(root, "link.txt")
                try:
                    os.symlink(secret, link)
                except (OSError, NotImplementedError, AttributeError):
                    self.skipTest("симлинки недоступны на этой платформе")
                with self.assertRaises(run_eval.ManifestError):
                    run_eval._safe_path("link.txt", root)

    def test_relative_path_inside_root_is_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            inside = os.path.join(root, "inside.txt")
            with open(inside, "w", encoding="utf-8") as fh:
                fh.write("корпус")
            resolved = run_eval._safe_path("inside.txt", root)
            self.assertEqual(resolved, os.path.realpath(inside))


class TestRunIntegrationPathGuard(unittest.TestCase):
    def test_run_rejects_absolute_path_in_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            body = os.path.join(root, "inside.txt")
            with open(body, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("обычный текст")
            manifest = {"version": "guard", "corpus": [
                {"path": body, "kind": "human",
                 "sha256": run_eval._sha256(body)}]}
            manifest_path = os.path.join(root, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(manifest, fh, ensure_ascii=False)
            with self.assertRaises(run_eval.ManifestError):
                run_eval.run(manifest_path, None, root)

    def test_run_rejects_parent_traversal_in_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            body = os.path.join(root, "inside.txt")
            with open(body, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("обычный текст")
            manifest = {"version": "guard", "corpus": [
                {"path": os.path.join("..", "outside.txt"), "kind": "human",
                 "sha256": run_eval._sha256(body)}]}
            manifest_path = os.path.join(root, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(manifest, fh, ensure_ascii=False)
            with self.assertRaises(run_eval.ManifestError):
                run_eval.run(manifest_path, None, root)


if __name__ == "__main__":
    unittest.main()
