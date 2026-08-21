#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_json_output.py — машиночитаемый stdout всех CLI парсится как UTF-8.

Этот гейт закрывает баг кодировки: на Windows при перенаправлении stdout
Python по умолчанию использует кодировку консоли (cp866/cp1251), поэтому
JSON с кириллицей писался байтами cp1251, хотя потребители (check_all.py,
eval/run_eval.py, jq и т.п.) читают stdout как UTF-8. Гейт запускает каждый
публичный JSON-вывод в subprocess с stdout=PIPE и без PYTHONIOENCODING/
PYTHONUTF8, читает байты stdout строго в UTF-8 и затем парсит JSON.

Прогон из корня репозитория:
    python scripts/check_json_output.py
    python scripts/check_json_output.py --selftest

Порядок кодов, как у соседних гейтов:
    0 — все доступные JSON-выводы прочитались как UTF-8 и разобрались;
    1 — хотя бы один JSON-вывод побит;
    2 — отказ инструмента (нужный скрипт не найден, таймаут). Только
        стандартная библиотека.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять сам гейт на кириллице;
# вывод гейта тоже обязан быть читаемым для CI как UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable or "python3"

PROBE_TIMEOUT = 120  # секунд; обычный прогон занимает доли секунды.


class GateError(Exception):
    """Отказ инструмента: гейт не может выполнить проверку, код 2."""


def _clean_env():
    """Копия окружения без UTF-8-костылей Python.

    Кодировку stdout обязан обеспечить сам скрипт, а не переменная окружения.
    Иначе гейт на машине с PYTHONIOENCODING/PYTHONUTF8 давал бы ложный PASS:
    проверялось бы не исправление скрипта, а окружение.
    """
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    return env


def _parse_stdout(proc):
    """Возвращает (ok, payload-or-detail) для завершённого subprocess.

    Сначала честно декодирует stdout как UTF-8; парсинг выполняем только после
    успешного декодирования, чтобы отличать «не UTF-8» от «не JSON».
    """
    try:
        text = proc.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, "stdout не UTF-8: %s" % exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, "stdout не JSON: %s" % exc
    return True, data


def _call(script_rel, args):
    """Запускает project-скрипт с чистыми PYTHONIOENCODING/PYTHONUTF8.

    cwd — корень репозитория, stdout/stderr — байтовые трубы. Сбой запуска или
    исчезнувший скрипт — отказ инструмента, а не провал кодировки.
    """
    script = os.path.join(ROOT, script_rel)
    if not os.path.isfile(script):
        raise GateError("скрипт не найден: %s" % script_rel)
    argv = [PY, script] + list(args)
    try:
        return subprocess.run(
            argv,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_clean_env(),
            timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise GateError("таймаут %s: %s" % (script_rel, exc))


def _stderr_tail(proc, limit=220):
    text = proc.stderr.decode("utf-8", "replace")
    tail = text.strip().splitlines()[-3:]
    return "; ".join(tail)[:limit]


def _fail_row(proc, detail):
    stderr_tail = _stderr_tail(proc)
    return "FAIL", detail, "код %d%s" % (
        proc.returncode,
        ("; stderr: " + stderr_tail) if stderr_tail else "")


def _make_text_file(td):
    """Создаёт UTF-8-файл с кириллическим путём.

    Не-ASCII путь обязан попасть в JSON-отчёты: если stdout сломан, байты
    вывода не совпадут с UTF-8. Если бы путь был ASCII, scan_soft_signals всё
    равно печатал бы кириллические названия признаков и жанров, но filemarks
    и score_synthid могли бы случайно остаться без кириллицы в выводе.
    """
    sub = os.path.join(td, "кириллица")
    os.makedirs(sub, exist_ok=True)
    path = os.path.join(sub, "образец.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("Обычный человеческий текст для проверки кодировки.\n")
        fh.write("Второе предложение без маркеров.\n")
    return path


def _check_scan_soft_signals(td):
    path = _make_text_file(td)
    proc = _call("scripts/scan_soft_signals.py", ["--json", path])
    ok, payload = _parse_stdout(proc)
    if not ok:
        return _fail_row(proc, payload)
    if proc.returncode not in (0,):
        return _fail_row(proc, "scan_soft_signals --json вернул код %d" % proc.returncode)
    if not isinstance(payload, list) or not payload or payload[0].get("file") != path:
        return "FAIL", "scan_soft_signals --json: неожиданная форма ответа", ""
    return "PASS", "UTF-8 JSON: список из %d записей" % len(payload), ""


def _check_filemarks(td):
    path = _make_text_file(td)
    proc = _call("scripts/filemarks/filemarks.py", ["--inspect", "--json", path])
    ok, payload = _parse_stdout(proc)
    if not ok:
        return _fail_row(proc, payload)
    if proc.returncode not in (0,):
        return _fail_row(proc, "filemarks --inspect --json вернул код %d" % proc.returncode)
    if not isinstance(payload, dict) or payload.get("path") != path:
        return "FAIL", "filemarks --inspect --json: неожиданная форма ответа", ""
    return "PASS", "UTF-8 JSON: kind=%s" % payload.get("kind"), ""


def _check_score_synthid(td):
    # score_synthid --json достижим только при настроенном внешнем checkout.
    # Чтобы проверить его stdout без сторонних зависимостей, в temp-каталоге
    # создаётся фейковый upstream с теми же путями и классами, которые скрипт
    # импортирует из reverse-SynthID.
    upstream = os.path.join(td, "апстрим")
    extraction = os.path.join(upstream, "src", "extraction")
    artifacts = os.path.join(upstream, "artifacts")
    os.makedirs(extraction, exist_ok=True)
    os.makedirs(artifacts, exist_ok=True)
    codebook = os.path.join(artifacts, "spectral_codebook_v4.npz")
    with open(codebook, "wb") as fh:
        fh.write(b"fake codebook\n")
    with open(os.path.join(extraction, "cv2.py"), "w", encoding="utf-8") as fh:
        fh.write('def imread(path):\n    return {"pixels": b"fake"}\n\n'
                 'def cvtColor(img, code):\n    return img\n\n'
                 'COLOR_BGR2RGB = 1\n')
    with open(os.path.join(extraction, "robust_extractor.py"), "w", encoding="utf-8") as fh:
        fh.write('class RobustSynthIDExtractor:\n'
                 '    def detect_from_v4_codebook(self, rgb, codebook_v4):\n'
                 '        return {"score": 0.42, "заключение": "слабый сигнал"}\n')
    with open(os.path.join(extraction, "synthid_bypass_v4.py"), "w", encoding="utf-8") as fh:
        fh.write('class SpectralCodebookV4:\n    def load(self, path):\n        pass\n')
    image = os.path.join(td, "изображение.png")
    with open(image, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    proc = _call("scripts/filemarks/score_synthid.py",
                 ["--json", "--upstream-dir", upstream, "--codebook", codebook, image])
    ok, payload = _parse_stdout(proc)
    if not ok:
        return _fail_row(proc, payload)
    if proc.returncode not in (0,):
        return _fail_row(proc, "score_synthid --json вернул код %d" % proc.returncode)
    if not isinstance(payload, dict) or payload.get("available") is not True:
        return "FAIL", "score_synthid --json: неожиданная форма ответа", ""
    return "PASS", "UTF-8 JSON: available=%s" % payload.get("available"), ""


def _check_run_eval(td):
    # run_eval печатает итоговый summary в stdout всегда. Прогон полного
    # eval/manifest.v1.json здесь не нужен: собираем однострочный манифест на
    # README.md и подсовываем кандидата, путь к которому содержит кириллицу.
    # Тогда summary["candidate"] гарантированно включает кириллицу и баг
    # кодировки воспроизводится на Windows.
    script_rel = "eval/run_eval.py"
    if not os.path.isfile(os.path.join(ROOT, script_rel)):
        return "SKIP", "eval/run_eval.py нет в этой поставке", ""

    readme = os.path.join(ROOT, "README.md")
    if not os.path.isfile(readme):
        return "SKIP", "README.md нет в этой поставке", ""

    runner_dir = os.path.join(td, "эвал-кандидат")
    os.makedirs(runner_dir, exist_ok=True)
    runner = os.path.join(runner_dir, "раннер.py")
    with open(runner, "w", encoding="utf-8") as fh:
        fh.write('import json, sys\n'
                 'if hasattr(sys.stdout, "reconfigure"):\n'
                 '    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")\n'
                 'json.dump([], sys.stdout)\n')
    with open(os.path.join(ROOT, "README.md"), "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    manifest = os.path.join(td, "манифест.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"version": "самопроверка-utf8", "corpus": [
            {"path": "README.md", "sha256": sha, "kind": "human"}]},
                  fh, ensure_ascii=False)
    proc = _call(script_rel, ["--manifest", manifest, "--candidate", runner])
    ok, payload = _parse_stdout(proc)
    if not ok:
        return _fail_row(proc, payload)
    if proc.returncode not in (0,):
        return _fail_row(proc, "run_eval вернул код %d" % proc.returncode)
    if (not isinstance(payload, dict) or payload.get("manifest_version") != "самопроверка-utf8"
            or payload.get("candidate") != runner or payload.get("files") != 1):
        return "FAIL", "run_eval: неожиданная форма summary", ""
    return "PASS", "UTF-8 JSON: files=%d, candidate с кириллицей" % payload.get("files"), ""


PROBES = [
    ("scan_soft_signals --json", _check_scan_soft_signals),
    ("filemarks --inspect --json", _check_filemarks),
    ("score_synthid --json", _check_score_synthid),
    ("eval/run_eval summary", _check_run_eval),
]


def render(rows, fails, skips):
    out = []
    for status, label, detail in rows:
        line = "%-4s %s" % (status, label)
        if detail:
            line += "  — " + detail
        out.append(line)
    out.append("ИТОГ: %d проверок, FAIL: %d, SKIP: %d." % (len(rows), fails, skips))
    return "\n".join(out)


# --------------------------------------------------------------- selftest

def selftest():
    cases = []

    def case(name, ok):
        cases.append((name, bool(ok)))

    good_bytes = json.dumps({"сообщение": "привет, мир"}, ensure_ascii=False).encode("utf-8")
    good_data = json.loads(good_bytes.decode("utf-8"))
    ok, payload = _parse_stdout(type("Proc", (), {"stdout": good_bytes})())
    case("UTF-8 JSON разбирается", ok and payload == good_data)

    bad_bytes = json.dumps({"сообщение": "привет, мир"}, ensure_ascii=False).encode("cp1251")
    ok, detail = _parse_stdout(type("Proc", (), {"stdout": bad_bytes})())
    case("cp1251-JSON ловится как не UTF-8", (not ok) and "не UTF-8" in detail)

    ok, detail = _parse_stdout(type("Proc", (), {"stdout": "обычный текст".encode("utf-8")})())
    case("не-JSON в UTF-8 ловится", (not ok) and "не JSON" in detail)

    os.environ["HUMANIZER_GATE_ENV_PROBE"] = "1"
    try:
        env = _clean_env()
        case("чистое окружение сохраняет прочие переменные",
             "HUMANIZER_GATE_ENV_PROBE" in env and "PYTHONIOENCODING" not in env and "PYTHONUTF8" not in env)
    finally:
        del os.environ["HUMANIZER_GATE_ENV_PROBE"]

    env = _clean_env()
    case("PYTHONIOENCODING/PYTHONUTF8 снимаются",
         "PYTHONIOENCODING" not in env and "PYTHONUTF8" not in env)

    failed = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print("%s: %s" % ("PASS" if ok else "FAIL", n))
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка UTF-8 машиночитаемого вывода всех CLI.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    rows, fails, skips = [], 0, 0
    try:
        with tempfile.TemporaryDirectory(prefix="humanizer-json-output-") as td:
            for label, checker in PROBES:
                try:
                    status, detail, _ = checker(td)
                except GateError as exc:
                    print("ОТКАЗ: %s" % exc)
                    return 2
                rows.append((status, label, detail))
                if status == "FAIL":
                    fails += 1
                elif status == "SKIP":
                    skips += 1
    except GateError as exc:
        print("ОТКАЗ: %s" % exc)
        return 2
    print(render(rows, fails, skips))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
