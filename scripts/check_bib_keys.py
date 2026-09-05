#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_bib_keys.py — разрешённость ключей [bib:*]: каждый ключ,
использованный в публичных .md, определён в research/BIBLIOGRAPHY.md.
Selftest с негативом."""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIB = os.path.join(ROOT, "research", "BIBLIOGRAPHY.md")
DEF_RX = re.compile(r"^- \[bib:([A-Za-z0-9_]+)\]", re.M)
USE_RX = re.compile(r"\[bib:([A-Za-z0-9_]+)\]")


def md_files(root=None):
    root = root or ROOT
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__",
                                                "node_modules")]
        for f in files:
            if f.endswith(".md"):
                out.append(os.path.join(base, f))
    return sorted(out)


def defined_keys(bib_path=None):
    with open(bib_path or BIB, encoding="utf-8") as fh:
        return set(DEF_RX.findall(fh.read()))


def check(defs=None, uses=None, root=None):
    if defs is None:
        defs = defined_keys()
    errs = []
    if uses is None:
        uses = {}
        for path in md_files(root):
            with open(path, encoding="utf-8", errors="replace") as fh:
                for k in USE_RX.findall(fh.read()):
                    uses.setdefault(k, []).append(
                        os.path.relpath(path, root or ROOT))
    for k in sorted(uses):
        if k not in defs:
            errs.append("[bib:%s] не определён в research/BIBLIOGRAPHY.md "
                        "(используется: %s)" % (k, ", ".join(sorted(set(uses[k]))[:3])))
    return errs


def selftest():
    checks = [
        ("репозиторий: все ключи разрешены", check() == []),
        ("неопределённый ключ ловится",
         check({"a2020"}, {"b2021": ["README.md"]}) != []),
        ("определённый ключ проходит",
         check({"a2020"}, {"a2020": ["README.md"]}) == []),
    ]
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА bib-keys: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    errs = check()
    for e in errs:
        print("[FAIL] %s" % e)
    if errs:
        print("BIB-KEYS: %d неразрешённых ключей" % len(errs))
        return 1
    print("BIB-KEYS: все ключи [bib:*] определены в BIBLIOGRAPHY.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
