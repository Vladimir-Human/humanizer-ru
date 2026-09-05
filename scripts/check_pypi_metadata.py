#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_pypi_metadata.py — сверка метаданных дистрибутива с pyproject.toml
(приказ 2026-09-05, L7, N3): Name, Version, Summary, Keywords, Project-URL,
Classifiers в PKG-INFO собранного sdist обязаны соответствовать pyproject.
Без сети: sdist собирается локально (python -m build --sdist); отказ среды
(нет модуля build/venv) — код 2, не провал (как у --sdist-test).

Запуск:
    python3 scripts/check_pypi_metadata.py [--selftest] [--sdist путь.tar.gz]
"""
import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from email.parser import Parser
from email.policy import compat32

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_pyproject(text):
    """Минимальный разбор pyproject.toml: tomllib (3.11+) либо регэксы."""
    try:
        import tomllib
        doc = tomllib.loads(text)
        proj = doc.get("project", {})
        urls = proj.get("urls", {}) or {}
        return {
            "name": proj.get("name"),
            "version": proj.get("version"),
            "description": proj.get("description"),
            "keywords": list(proj.get("keywords", []) or []),
            "urls": {k: v for k, v in sorted(urls.items())},
            "classifiers": sorted(proj.get("classifiers", []) or []),
        }
    except ImportError:
        import re
        def grab(key):
            m = re.search(r'^%s\s*=\s*"([^"]*)"' % key, text, re.M)
            return m.group(1) if m else None
        kw = re.search(r"keywords\s*=\s*\[(.*?)\]", text, re.S)
        kws = re.findall(r'"([^"]+)"', kw.group(1)) if kw else []
        cls = re.search(r"classifiers\s*=\s*\[(.*?)\]", text, re.S)
        clss = re.findall(r'"([^"]+)"', cls.group(1)) if cls else []
        urls = dict(re.findall(r'^(\w[\w ]*)\s*=\s*"(https?://[^"]+)"',
                               text, re.M))
        return {"name": grab("name"), "version": None,
                "description": grab("description"), "keywords": kws,
                "urls": {k: v for k, v in sorted(urls.items())},
                "classifiers": sorted(clss)}


def parse_pkginfo(text):
    msg = Parser(policy=compat32).parsestr(text)
    keywords = [k.strip() for k in (msg.get("Keywords") or "").split(",")
                if k.strip()]
    urls = {}
    for header in msg.get_all("Project-URL", []):
        parts = header.split(",", 1)
        if len(parts) == 2:
            urls[parts[0].strip()] = parts[1].strip()
        else:
            urls[parts[0].strip()] = ""
    return {
        "name": msg.get("Name"),
        "version": msg.get("Version"),
        "description": msg.get("Summary"),
        "keywords": keywords,
        "urls": {k: v for k, v in sorted(urls.items())},
        "classifiers": sorted(m for m in msg.get_all("Classifier", [])),
    }


def compare(pkg, proj, dynamic_version=False):
    errs = []
    for field in ("name", "description"):
        if pkg.get(field) != proj.get(field):
            errs.append("%s: PKG-INFO %r != pyproject %r"
                        % (field, pkg.get(field), proj.get(field)))
    if not dynamic_version and pkg.get("version") != proj.get("version"):
        errs.append("version: PKG-INFO %r != pyproject %r"
                    % (pkg.get("version"), proj.get("version")))
    if pkg.get("keywords") != proj.get("keywords"):
        errs.append("keywords: PKG-INFO %r != pyproject %r"
                    % (pkg.get("keywords"), proj.get("keywords")))
    for key, val in proj.get("urls", {}).items():
        if pkg.get("urls", {}).get(key) != val:
            errs.append("Project-URL %s: PKG-INFO %r != pyproject %r"
                        % (key, pkg.get("urls", {}).get(key), val))
    missing_cls = set(proj.get("classifiers", [])) - set(pkg.get("classifiers", []))
    if missing_cls:
        errs.append("classifiers: в PKG-INFO нет %s" % sorted(missing_cls))
    return errs


def build_sdist(outdir):
    r = subprocess.run([sys.executable, "-m", "build", "--sdist",
                        "--outdir", outdir], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    for name in os.listdir(outdir):
        if name.endswith(".tar.gz"):
            return os.path.join(outdir, name)
    return None


def extract_pkginfo(sdist_path):
    with tarfile.open(sdist_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith("PKG-INFO"):
                fh = tf.extractfile(member)
                return fh.read().decode("utf-8", errors="replace")
    return None


def check(sdist_arg=None):
    tmp = tempfile.mkdtemp(prefix="pypi-meta-")
    try:
        sdist = sdist_arg
        if not sdist:
            sdist = build_sdist(tmp)
        if not sdist or not os.path.isfile(sdist):
            print("ОТКАЗ СРЕДЫ: нет модуля build или сборка не удалась "
                  "(код 2, не провал)")
            return 2
        pkginfo = extract_pkginfo(sdist)
        if pkginfo is None:
            print("[FAIL] в sdist нет PKG-INFO")
            return 1
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            proj = parse_pyproject(fh.read())
        pkg = parse_pkginfo(pkginfo)
        # version в pyproject динамический (attr) — сверяем с __init__
        init_path = os.path.join(ROOT, "src", "humanizer_ru", "__init__.py")
        with open(init_path, encoding="utf-8") as fh:
            import re
            m = re.search(r'__version__\s*=\s*"([^"]+)"', fh.read())
        if m:
            proj["version"] = m.group(1)
            errs = compare(pkg, proj)
        else:
            errs = compare(pkg, proj, dynamic_version=True)
            errs.append("не найден __version__ в src/humanizer_ru/__init__.py")
        for e in errs:
            print("[FAIL] %s" % e)
        if errs:
            print("PYPI-METADATA: %d расхождений" % len(errs))
            return 1
        print("PYPI-METADATA: PKG-INFO соответствует pyproject (%s %s)"
              % (pkg["name"], pkg["version"]))
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def selftest():
    _ver = "%d.%d.%d" % (1, 2, 3)
    proj = {"name": "demo", "version": _ver,
            "description": "формула", "keywords": ["русский текст"],
            "urls": {"Demo": "https://example.org/"},
            "classifiers": ["Natural Language :: Russian"]}
    good = dict(proj)
    errs = compare(good, proj)
    bad = dict(proj, keywords=["other"])
    errs_bad = compare(bad, proj)
    bad_url = dict(proj, urls={"Demo": "https://other.org/"})
    checks = [
        ("идентичные метаданные без расхождений", errs == []),
        ("расхождение keywords ловится", errs_bad != []),
        ("расхождение Project-URL ловится", compare(bad_url, proj) != []),
        ("пропавший classifier ловится",
         compare(dict(proj, classifiers=[]), proj) != []),
    ]
    fails = 0
    for name, ok in checks:
        print("%s: %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("САМОПРОВЕРКА pypi-metadata: %d FAIL" % fails)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sdist", default=None)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return check(args.sdist)


if __name__ == "__main__":
    sys.exit(main())
