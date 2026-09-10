#!/usr/bin/env python3
"""Generate a machine-readable Agent Skills distribution receipt.

This is a project receipt, not an official lockfile or a security certificate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/Vladimir-Human/humanizer-ru"
TARGETS = {
    "root-skill": ("SKILL.md", "references"),
    "dsh-skill": ("dsh/skills/humanizer-ru",),
    "mcp-contract": ("contract.v1.json",),
}
VERIFY_COMMANDS = ("python scripts/check_bundle_sync.py",
                   "python scripts/check_mcp.py",
                   "python scripts/check_identity.py")


def _version():
    text = (ROOT / "src" / "humanizer_ru" / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__ = "):
            return line.split('"', 2)[1]
    raise ValueError("package version is missing")


def _git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _files(paths):
    found = []
    for name in paths:
        path = ROOT / name
        if path.is_file():
            found.append((name.replace("\\", "/"), path.read_bytes()))
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_symlink():
                    raise OSError("symlink is not a distributable file: %s" % child)
                if child.is_file():
                    found.append((child.relative_to(ROOT).as_posix(), child.read_bytes()))
        else:
            raise FileNotFoundError(name)
    return sorted(found, key=lambda item: item[0])


def _tracked_target_files(paths):
    """Return regular files in HEAD under paths, including their blob ids."""
    args = ["git", "ls-tree", "-r", "-z", "HEAD", "--", *paths]
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    result = {}
    for entry in p.stdout.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, obj_type, oid = meta.split()
        if obj_type != b"blob" or mode != b"100644":
            return None
        result[name.decode("utf-8")] = oid.decode("ascii")
    return result


def _matches_head(paths):
    tracked = _tracked_target_files(paths)
    if tracked is None:
        return False
    try:
        current = dict(_files(paths))
    except (OSError, FileNotFoundError):
        return False
    if set(current) != set(tracked):
        return False
    algorithm = "sha256" if len(next(iter(tracked.values()), "")) == 64 else "sha1"
    for name, data in current.items():
        blob = ("blob %d\0" % len(data)).encode("ascii") + data
        if hashlib.new(algorithm, blob).hexdigest() != tracked[name]:
            return False
    return True


def _output_is_safe(output):
    if output is None:
        return True
    try:
        output.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return True
    return False


def _hash(paths):
    digest = hashlib.sha256(); files = _files(paths)
    for name, data in files:
        digest.update(name.encode("utf-8")); digest.update(b"\0")
        digest.update(data); digest.update(b"\0")
    return digest.hexdigest(), len(files)


def receipt():
    artifacts = []
    for target, paths in TARGETS.items():
        digest, count = _hash(paths)
        artifacts.append({"target": target, "paths": list(paths),
                          "file_count": count, "sha256": digest})
    return {"schema": 1, "product": "humanizer-ru", "version": _version(),
            "source": {"repository": REPOSITORY,
                       "commit": _git("rev-parse", "HEAD"),
                       "clean": _git("status", "--porcelain") == "" and
                                all(_matches_head(paths) for paths in TARGETS.values())},
            "artifacts": artifacts,
            "verification": [{"command": c} for c in VERIFY_COMMANDS],
            "note": "local distribution receipt; not an official Agent Skills lockfile"}


def selftest():
    data = receipt(); first = _hash(("SKILL.md",))[0]; second = _hash(("SKILL.md",))[0]
    checks = [("schema and product", data["schema"] == 1 and data["product"] == "humanizer-ru"),
              ("stable hash", first == second),
              ("targets represented", {a["target"] for a in data["artifacts"]} == set(TARGETS))]
    for label, ok in checks: print(("PASS: " if ok else "FAIL: ") + label)
    print("САМОПРОВЕРКА install_receipt: %d/%d PASS" % (sum(ok for _, ok in checks), len(checks)))
    return 0 if all(ok for _, ok in checks) else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true"); p.add_argument("--out", type=Path)
    p.add_argument("--strict", action="store_true"); p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest: return selftest()
    try: data = receipt()
    except (OSError, ValueError, FileNotFoundError) as exc:
        print("receipt unavailable: %s" % exc, file=sys.stderr); return 2
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not _output_is_safe(args.out):
        print("receipt unavailable: --out must be outside repository", file=sys.stderr)
        return 2
    if args.out: args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(text, encoding="utf-8")
    if args.json or not args.out: print(text, end="")
    if args.strict and (not data["source"]["commit"] or not data["source"]["clean"]): return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
