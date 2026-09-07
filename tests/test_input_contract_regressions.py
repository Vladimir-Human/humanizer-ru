#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессии машинного ввода: ни один непрочитанный вход не выглядит проверенным.

Закреплено (воспроизведено на опубликованной поставке до правки):
  1. Имя файла «--class»/«--json» — операнд, а не флаг:
     - humanizer-markers --scan --json -- --class давал код 2 с ПУСТЫМ
       stdout: cli.py подмешивал строки флагов в операнды, а
       check_markers.scan() переразбирал список и поглощал имя;
     - scripts/check_markers.py --scan --class a --json молча терял файл
       с именем --json (глобальный фильтр флагоподобных строк),
       files=[] и код 0 выглядели как успешная проверка;
     - граница «--» доходит до конечного исполнителя: всё после первого
       «--» — пути и повторно не интерпретируется.
  2. Любая предусмотренная ошибка кода 2 с --json печатает конверт
     контракта в stdout (error_rule): --remove без файлов, нераспознанные
     аргументы, нечитаемый файл, не-UTF-8.
  3. Не-UTF-8 — ошибка входа (код 2), а не traceback с пустым stdout
     (humanizer-facts) и не молчаливая замена байтов на U+FFFD
     (humanizer-report: errors="replace" давал код 0 на повреждённом входе).
  4. Обе точки входа равноправны: console-main и python -m модуля дают
     одинаковый конверт на одинаковом входе.

Отрицательные проверки прежнего поведения входят в таблицу: пустой stdout
при коде 2 с --json, «Traceback» в stderr, files=[] при коде 0 для
переданного операнда — запрещены.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ONLY = os.path.isdir(os.path.join(ROOT, "scripts"))
SKIP_OUTSIDE = unittest.skipUnless(
    REPO_ONLY, "вне репозитория (sdist): интеграционные тесты не запускаются")
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from humanizer_ru import check_markers  # noqa: E402

ARTIFACT = "Русский :contentReference[oaicite:3]{index=3} текст.\n"
CLEAN = "Обычный русский текст без артефактов.\n"

TMP = tempfile.mkdtemp(prefix="input-contract-")


def _write(name, text=None, data=None):
    path = os.path.join(TMP, name)
    if data is not None:
        with open(path, "wb") as fh:
            fh.write(data)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return name


_write("art.txt", ARTIFACT)
_write("clean.txt", CLEAN)
_write("--class", ARTIFACT)
_write("--json", ARTIFACT)
_write("--version", ARTIFACT)
_write("файл с пробелом.md", ARTIFACT)
_write("файл‑артефакт.md", ARTIFACT)  # U+2011 в имени
_write("bad.txt", data=b"\xff\xfe" + "Цена 100 рублей.\n".encode("utf-8"))
_write("good.txt", "Встреча состоялась. Цена 100 рублей.\n")
try:
    _write("имя\nс\nпереводом.txt", ARTIFACT)
    NEWLINE_NAME_OK = True
except OSError:
    NEWLINE_NAME_OK = False  # файловая система не допускает \n в имени


def _run_entry(module, func, argv, stdin_text=None, timeout=120):
    """Точка входа console-script'а: humanizer_ru.<module>.<func>(argv)."""
    code = ("import sys; sys.path.insert(0, %r);"
            "from humanizer_ru.%s import %s;"
            "sys.exit(%s(%r))") % (SRC, module, func, func, argv)
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                       input=stdin_text, capture_output=True,
                       encoding="utf-8", errors="replace",
                       cwd=TMP, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def _run_module(module, argv, stdin_text=None, timeout=120):
    """Вторая точка входа: python -m humanizer_ru.<module>."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    p = subprocess.run([sys.executable, "-X", "utf8", "-m",
                        "humanizer_ru." + module] + list(argv),
                       input=stdin_text, capture_output=True,
                       encoding="utf-8", errors="replace",
                       cwd=TMP, env=env, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def _run_script(argv, stdin_text=None, timeout=120):
    """Action-скрипт репозитория: scripts/check_markers.py."""
    script = os.path.join(ROOT, "scripts", "check_markers.py")
    p = subprocess.run([sys.executable, "-X", "utf8", script] + list(argv),
                       input=stdin_text, capture_output=True,
                       encoding="utf-8", errors="replace",
                       cwd=TMP, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def _envelope(test, out, tool):
    """stdout обязан быть одним JSON-документом контракта."""
    test.assertTrue(out.strip(), "пустой stdout при --json запрещён")
    doc = json.loads(out)
    test.assertEqual(doc["tool"], tool)
    test.assertEqual(doc["schema"], 1)
    test.assertIsInstance(doc["files"], list)
    return doc


class MarkersNameAsOperandTests(unittest.TestCase):
    """Имя файла, похожее на флаг, — путь; «--» доходит до исполнителя."""

    def test_console_file_named_class_after_ddash(self):
        rc, out, err = _run_entry("cli", "markers_main",
                                  ["--scan", "--json", "--", "--class"])
        self.assertEqual(rc, 1, "артефакт в файле --class обязан находиться")
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--class")
        self.assertGreaterEqual(doc["files"][0]["count"], 1)
        self.assertNotIn("ожидает значение", err)

    def test_console_file_named_class_with_class_flag(self):
        rc, out, err = _run_entry(
            "cli", "markers_main",
            ["--scan", "--class", "a", "--json", "--", "--class"])
        self.assertEqual(rc, 1)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--class")
        self.assertGreaterEqual(doc["files"][0]["count"], 1)
        self.assertNotIn("ожидает значение", err)

    def test_console_file_named_json_after_ddash(self):
        rc, out, _err = _run_entry("cli", "markers_main",
                                   ["--scan", "--json", "--", "--json"])
        self.assertEqual(rc, 1)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--json")
        self.assertGreaterEqual(doc["files"][0]["count"], 1)

    def test_console_file_named_version_after_ddash(self):
        # Существующая граница (test_interface_edges) остаётся в силе.
        rc, out, _err = _run_entry("cli", "markers_main",
                                   ["--json", "--", "--version"])
        self.assertEqual(rc, 1, "файл --version с артефактом сканируется")
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--version")

    @SKIP_OUTSIDE
    def test_action_script_file_named_json_after_ddash(self):
        rc, out, _err = _run_script(["--scan", "--class", "a", "--json",
                                     "--", "--json"])
        self.assertEqual(rc, 1, "файл --json обязан проверяться, не теряться")
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--json")
        self.assertGreaterEqual(doc["files"][0]["count"], 1)

    @SKIP_OUTSIDE
    def test_action_script_file_named_class_after_ddash(self):
        rc, out, err = _run_script(["--scan", "--json", "--", "--class"])
        self.assertEqual(rc, 1)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--class")
        self.assertNotIn("ожидает значение", err)

    @SKIP_OUTSIDE
    def test_action_script_flags_without_ddash_stay_flags(self):
        # Без «--» флагоподобный токен — флаг (POSIX): операнды не заданы,
        # поглощения входа нет; пустой список файлов честен.
        rc, out, _err = _run_script(["--scan", "--class", "a", "--json",
                                     "--json"])
        self.assertEqual(rc, 0)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"], [])

    @SKIP_OUTSIDE
    def test_action_script_versions_flag_is_not_a_file(self):
        # --versions в текстовом режиме снимается как флаг, а не открывается
        # как файл (прежде: код 2 «не удалось прочитать --versions»).
        rc, out, err = _run_script(["--scan", "--versions", "art.txt"])
        self.assertEqual(rc, 1)
        self.assertIn("art.txt", out)
        self.assertNotIn("--versions", err)

    def test_scan_paths_typed_entry_does_not_reparse(self):
        # Типизированный вход: операнды не интерпретируются повторно.
        self.assertTrue(callable(check_markers.scan_paths))
        cwd = os.getcwd()
        try:
            os.chdir(TMP)
            rc = check_markers.scan_paths(["--json"], class_filter="all",
                                          as_json=True)
        finally:
            os.chdir(cwd)
        self.assertEqual(rc, 1, "файл --json сканируется как путь")

    def test_names_with_space_unicode_duplicates_newline(self):
        argv = ["--scan", "--json", "--",
                "файл с пробелом.md", "файл‑артефакт.md",
                "art.txt", "art.txt"]
        if NEWLINE_NAME_OK:
            argv.append("имя\nс\nпереводом.txt")
        rc, out, _err = _run_entry("cli", "markers_main", argv)
        self.assertEqual(rc, 1)
        doc = _envelope(self, out, "humanizer-markers")
        names = [e["file"] for e in doc["files"]]
        self.assertEqual(names[0], "файл с пробелом.md")
        self.assertEqual(names[1], "файл‑артефакт.md")
        self.assertEqual(names.count("art.txt"), 2,
                         "повторяющийся путь — две записи, не одна")
        if NEWLINE_NAME_OK:
            self.assertIn("имя\nс\nпереводом.txt", names)
        for e in doc["files"]:
            self.assertGreaterEqual(e["count"], 1)

    def test_stdin_dash_still_reads_stdin(self):
        rc, out, _err = _run_entry("cli", "markers_main",
                                   ["--scan", "--json", "-"],
                                   stdin_text=ARTIFACT)
        self.assertEqual(rc, 1)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "<stdin>")
        self.assertGreaterEqual(doc["files"][0]["count"], 1)

    def test_unreadable_file_gives_envelope_not_silence(self):
        rc, out, _err = _run_entry("cli", "markers_main",
                                   ["--scan", "--json", "нет-такого.txt"])
        self.assertEqual(rc, 2)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertIn("error", doc)
        self.assertEqual(doc["files"][0]["file"], "нет-такого.txt")
        self.assertIn("error", doc["files"][0])

    def test_bad_bytes_f13_heuristic_no_crash(self):
        # F13 — документированное поведение markers: BOM-детект и
        # эвристика cp1251/KOI8-R вместо жёсткого отказа; инвариант —
        # без traceback и с валидным JSON-конвертом в stdout.
        rc, out, err = _run_entry("cli", "markers_main",
                                  ["--scan", "--json", "bad.txt"])
        self.assertIn(rc, (0, 1, 2))
        self.assertNotIn("Traceback", err)
        if out.strip():
            json.loads(out)


class RemoveJsonEnvelopeTests(unittest.TestCase):
    """--remove без файлов: код 2 с конвертом в stdout (error_rule)."""

    def test_remove_no_files_json_envelope(self):
        rc, out, err = _run_entry("cli", "markers_main",
                                  ["--remove", "--json"])
        self.assertEqual(rc, 2)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertIn("код 2", doc["error"])
        self.assertEqual(doc["files"][0]["file"], "<argv>")
        self.assertIn("нет файлов", err)

    def test_remove_no_files_text_mode_unchanged(self):
        rc, out, err = _run_entry("cli", "markers_main", ["--remove"])
        self.assertEqual(rc, 2)
        self.assertEqual(out.strip(), "", "текстовый режим: stdout пуст")
        self.assertIn("нет файлов", err)

    def test_remove_still_removes_invisible(self):
        # Узкое назначение --remove сохранено: невидимая метка снимается.
        rc, out, _err = _run_entry("cli", "markers_main",
                                   ["--remove", "--json", "--", "clean.txt"],
                                   stdin_text=None)
        self.assertEqual(rc, 0)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["mode"], "remove")


class FactsInputErrorTests(unittest.TestCase):
    """humanizer-facts: не-UTF-8 и отсутствующий файл — код 2 с конвертом."""

    def test_bad_utf8_json_envelope(self):
        rc, out, err = _run_entry("facts_diff", "main",
                                  ["diff", "bad.txt", "good.txt", "--json"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        doc = _envelope(self, out, "humanizer-facts")
        self.assertIn("код 2", doc["error"])
        self.assertEqual(doc["files"], ["bad.txt", "good.txt"])

    def test_bad_utf8_text_mode_no_traceback(self):
        rc, out, err = _run_entry("facts_diff", "main",
                                  ["diff", "bad.txt", "good.txt"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertTrue(out.strip())  # конверт, как и прежде, печатается

    def test_missing_file_json_envelope(self):
        rc, out, err = _run_entry("facts_diff", "main",
                                  ["diff", "нет-такого.txt", "good.txt",
                                   "--json"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        doc = _envelope(self, out, "humanizer-facts")
        self.assertIn("код 2", doc["error"])
        self.assertEqual(doc["files"], ["нет-такого.txt", "good.txt"])

    def test_argparse_error_with_json_gives_envelope(self):
        rc, out, err = _run_entry("facts_diff", "main", ["--json"])
        self.assertEqual(rc, 2)
        doc = _envelope(self, out, "humanizer-facts")
        self.assertIn("код 2", doc["error"])
        self.assertNotIn("Traceback", err)

    def test_protect_missing_file_gives_envelope(self):
        rc, out, err = _run_entry(
            "facts_diff", "main",
            ["diff", "good.txt", "good.txt", "--protect", "нет-protect.txt",
             "--json"])
        self.assertEqual(rc, 2)
        doc = _envelope(self, out, "humanizer-facts")
        self.assertIn("код 2", doc["error"])
        self.assertNotIn("Traceback", err)

    def test_module_entry_parity(self):
        rc1, out1, _e1 = _run_entry("facts_diff", "main",
                                    ["diff", "bad.txt", "good.txt", "--json"])
        rc2, out2, _e2 = _run_module("facts_diff",
                                     ["diff", "bad.txt", "good.txt", "--json"])
        self.assertEqual((rc1, out1), (rc2, out2),
                         "console-функция и python -m дают один конверт")


class ReportInputErrorTests(unittest.TestCase):
    """humanizer-report: повреждённый и отсутствующий вход — код 2."""

    def test_bad_utf8_is_input_error_not_replace(self):
        rc, out, err = _run_entry("edit_report", "main",
                                  ["bad.txt", "good.txt", "--json"])
        self.assertEqual(rc, 2, "прежний rc=0 с errors=replace запрещён")
        self.assertNotIn("Traceback", err)
        doc = _envelope(self, out, "humanizer-report")
        self.assertIn("код 2", doc["error"])
        self.assertNotIn("sari_adapted", out,
                         "отчёт по повреждённому входу не строится")
        self.assertNotIn("\ufffd", out)

    def test_missing_file_json_envelope(self):
        rc, out, err = _run_entry("edit_report", "main",
                                  ["нет-такого.txt", "good.txt", "--json"])
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        doc = _envelope(self, out, "humanizer-report")
        self.assertIn("код 2", doc["error"])
        self.assertEqual(doc["files"][0]["before"], "нет-такого.txt")

    def test_missing_file_text_mode(self):
        rc, out, err = _run_entry("edit_report", "main",
                                  ["нет-такого.txt", "good.txt"])
        self.assertEqual(rc, 2)
        self.assertEqual(out.strip(), "")
        self.assertNotIn("Traceback", err)
        self.assertIn("не удалось прочитать", err)

    def test_argparse_error_with_json_gives_envelope(self):
        rc, out, err = _run_entry("edit_report", "main", ["--json"])
        self.assertEqual(rc, 2)
        doc = _envelope(self, out, "humanizer-report")
        self.assertIn("код 2", doc["error"])
        self.assertNotIn("Traceback", err)

    def test_good_pair_keeps_contract_fields(self):
        # Совместимость: успешная пара не меняет ни поля, ни семантику
        # (включая facts.unchanged — его границы правит отдельный поток).
        rc, out, _err = _run_entry("edit_report", "main",
                                   ["good.txt", "good.txt", "--json"])
        self.assertEqual(rc, 0)
        doc = _envelope(self, out, "humanizer-report")
        f = doc["files"][0]
        for key in ("tokens", "sari_adapted", "edit_types", "facts", "mtld"):
            self.assertIn(key, f)
        self.assertIn("unchanged", f["facts"])
        self.assertIn("lost", f["facts"])
        self.assertIn("changed", f["facts"])

    def test_module_entry_parity(self):
        rc1, out1, _e1 = _run_entry("edit_report", "main",
                                    ["bad.txt", "good.txt", "--json"])
        rc2, out2, _e2 = _run_module("edit_report",
                                     ["bad.txt", "good.txt", "--json"])
        self.assertEqual((rc1, out1), (rc2, out2))


class ModuleEntryMarkersTests(unittest.TestCase):
    """python -m humanizer_ru.check_markers — та же граница «--»."""

    def test_module_scan_file_named_class(self):
        rc, out, err = _run_module("check_markers",
                                   ["--scan", "--json", "--", "--class"])
        self.assertEqual(rc, 1)
        doc = _envelope(self, out, "humanizer-markers")
        self.assertEqual(doc["files"][0]["file"], "--class")
        self.assertNotIn("ожидает значение", err)

    def test_module_and_script_agree(self):
        if not REPO_ONLY:
            self.skipTest("вне репозитория")
        rc1, out1, _e1 = _run_module("check_markers",
                                     ["--scan", "--json", "--", "--json"])
        rc2, out2, _e2 = _run_script(["--scan", "--json", "--", "--json"])
        self.assertEqual((rc1, out1), (rc2, out2))


if __name__ == "__main__":
    unittest.main()
