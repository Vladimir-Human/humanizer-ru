#!/usr/bin/env python3
"""Runner-адаптер: линтер smixs/humanizer-ru по протоколу кандидата run_eval.

Протокол кандидата: argv[1] — путь к файлу корпуса; stdout — JSON
[{line, case}]. Использует приколотую копию lint.py (коммит 91f70df,
MIT) — smixs_lint_pinned.py рядом. Линтер возвращает
(kind, line_no, rule, excerpt); в case идёт имя правила.
"""
import json
import os
import sys

import smixs_lint_pinned as lint_mod


def main():
    if len(sys.argv) < 2:
        print("нужен путь к файлу", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("не удалось прочитать %s: %s" % (sys.argv[1], exc),
              file=sys.stderr)
        return 2
    findings = lint_mod.lint(text)
    out = [{"line": line, "case": rule}
           for _kind, line, rule, _ctx in findings]
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
