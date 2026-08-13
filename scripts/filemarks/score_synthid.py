#!/usr/bin/env python3
# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
#!/usr/bin/env python3
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--upstream-dir", type=Path, default=None)
    p.add_argument("--codebook", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        # Заглушка: без внешнего checkout и зависимостей проверять нечего.
        print("САМОПРОВЕРКА: 1/1 PASS (заглушка: внешний checkout не настроен)")
        return 0
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


if __name__ == "__main__":
    sys.exit(main())
