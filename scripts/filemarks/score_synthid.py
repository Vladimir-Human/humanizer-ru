#!/usr/bin/env python3
# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
"""score_synthid.py — опциональная оценка пиксельного SynthID (внешний скоринг).

Внешний скоринг (aloshdenny/reverse-SynthID) НЕ поставляется с проектом:
это сторонний ресерч-код под некоммерческой лицензией, и это не официальный
детектор Google. Скрипт лишь подключает его, если владелец сам выкачал
checkout и указал путь (REVERSE_SYNTHID_DIR или --upstream-dir).

Коды: 0 — оценка получена, 1 — ошибка скоринга, 2 — плохой вход,
3 — скоринг недоступен (не настроен/нет зависимостей/нет codebook).
"""
import argparse
import json
import os
import sys
from pathlib import Path


# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--upstream-dir", type=Path, default=None)
    p.add_argument("--codebook", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.path or not args.path.is_file():
        print("не файл: %s" % args.path, file=sys.stderr)
        return 2
    if args.path.stat().st_size > 256 << 20:
        print("отказ: изображение больше лимита", file=sys.stderr)
        return 2
    upstream = args.upstream_dir or (Path(os.environ["REVERSE_SYNTHID_DIR"])
                                     if os.environ.get("REVERSE_SYNTHID_DIR") else None)
    if upstream is None or not Path(upstream).is_dir():
        print("скоринг не настроен: задайте REVERSE_SYNTHID_DIR или --upstream-dir",
              file=sys.stderr)
        return 3
    extraction = Path(upstream) / "src" / "extraction"
    codebook = args.codebook or Path(upstream) / "artifacts" / "spectral_codebook_v4.npz"
    if not extraction.is_dir() or not Path(codebook).is_file():
        print("в checkout не найдены extraction/codebook: %s" % upstream, file=sys.stderr)
        return 3
    sys.path.insert(0, str(extraction))
    try:
        import cv2  # noqa: F401
        from robust_extractor import RobustSynthIDExtractor  # noqa: F401
        from synthid_bypass_v4 import SpectralCodebookV4  # noqa: F401
    except ImportError as exc:
        print("нет зависимостей внешнего скоринга: %s" % exc, file=sys.stderr)
        return 3
    try:
        img = cv2.imread(str(args.path))
        if img is None:
            print("не удалось прочитать изображение", file=sys.stderr)
            return 2
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        codebook_v4 = SpectralCodebookV4()
        codebook_v4.load(str(codebook))
        extractor = RobustSynthIDExtractor()
        result = extractor.detect_from_v4_codebook(rgb, codebook_v4)
    except Exception as exc:
        print("ошибка скоринга: %s" % exc, file=sys.stderr)
        return 1
    payload = {"available": True, "upstream_dir": str(upstream),
               "codebook": str(codebook), "result": str(result)[:2000]}
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print("SynthID-оценка (внешний скоринг, best-effort): %s" % str(result)[:2000])
    return 0


def selftest():
    """Реальная самопроверка кодов: 3 (не настроен), 2 (плохой вход), отказ без args.

    Без сети и внешнего кода: коды 3 и 2 проверяются до импорта сторонних
    зависимостей, поэтому selftest детерминирован и не требует checkout.
    """
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    # Отказ без аргументов: нет path → код 2.
    case("отказ без args (код 2)", main([]) == 2)
    # Плохой вход: несуществующий файл → код 2.
    case("несуществующий файл (код 2)",
         main([os.path.join(".", "нет_такого_файла.png")]) == 2)

    # Код 3 (скоринг не настроен). Нужен СУЩЕСТВУЮЩИЙ файл (иначе код 2),
    # но отсутствующий REVERSE_SYNTHID_DIR и --upstream-dir → код 3.
    saved_env = os.environ.pop("REVERSE_SYNTHID_DIR", None)
    saved_cwd = os.getcwd()
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake = os.path.join(td, "img.png")
            with open(fake, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
            case("файл есть, скоринг не настроен (код 3)", main([fake]) == 3)
            case("--upstream-dir указывает на несуществующий каталог (код 3)",
                 main([fake, "--upstream-dir", os.path.join(td, "нет_checkout")]) == 3)
    finally:
        if saved_env is not None:
            os.environ["REVERSE_SYNTHID_DIR"] = saved_env
        os.chdir(saved_cwd)

    # Умеет падать: неверное ожидание — считаем, что отказ без args должен
    # дать код 1, но фактический код 2 → это FAIL (ловит «убедилась, что
    # проверка настоящая, а не вечно PASS»).
    case("неверное ожидание кода ловится (без args != 1)",
         main([]) != 1)

    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())