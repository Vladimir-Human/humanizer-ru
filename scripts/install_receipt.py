#!/usr/bin/env python3
"""Generate a machine-readable Agent Skills distribution receipt.

This is a project receipt, not an official lockfile or a security certificate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATH = "src/humanizer_ru/__init__.py"
REPOSITORY = "https://github.com/Vladimir-Human/humanizer-ru"
TARGETS = {
    "root-skill": ("SKILL.md", "references"),
    "dsh-skill": ("dsh/skills/humanizer-ru",),
    "mcp-contract": ("contract.v1.json",),
}
VERIFY_COMMANDS = ("python scripts/check_bundle_sync.py",
                   "python scripts/check_mcp.py",
                   "python scripts/check_identity.py")


def _version(data):
    text = data.decode("utf-8")
    for line in text.splitlines():
        if line.startswith("__version__ = "):
            parts = line.split('"')
            if len(parts) == 3 and parts[1]:
                return parts[1]
    raise ValueError("package version is missing")


def _git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _reject_link(path):
    """Reject links and Windows junctions before following any target path."""
    for item in (path, *path.parents):
        if item == ROOT:
            break
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("linked paths cannot be receipted")


def _files(paths):
    found = []
    for name in paths:
        path = ROOT / name
        _reject_link(path)
        if path.is_file():
            found.append((name.replace("\\", "/"), path.read_bytes()))
        elif path.is_dir():
            for child in path.rglob("*"):
                _reject_link(child)
                if child.is_file():
                    found.append((child.relative_to(ROOT).as_posix(), child.read_bytes()))
                elif not child.is_dir():
                    raise ValueError("only regular files can be receipted")
        else:
            raise FileNotFoundError(name)
    return sorted(found, key=lambda item: item[0])


def _tracked_target_files(paths, commit):
    """Return regular files in HEAD under paths, including their blob ids."""
    args = ["git", "ls-tree", "-r", "-z", commit, "--", *paths]
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
        if obj_type != b"blob" or mode not in (b"100644", b"100755"):
            return None
        result[name.decode("utf-8")] = oid.decode("ascii")
    return result


def _matches_commit(paths, current, commit):
    if not commit:
        return False
    tracked = _tracked_target_files(paths, commit)
    if tracked is None:
        return False
    current = dict(current)
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


def _hash(files):
    """Hash sorted paths and raw bytes, with 8-byte big-endian length framing."""
    digest = hashlib.sha256()
    for name, data in files:
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest(), len(files)


def receipt():
    commit = _git("rev-parse", "HEAD")
    clean_before = _git("status", "--porcelain", "--untracked-files=all") == ""
    artifacts = []
    matches_commit = True
    for target, paths in TARGETS.items():
        files = _files(paths)
        digest, count = _hash(files)
        matches_commit &= _matches_commit(paths, files, commit)
        artifacts.append({"target": target, "paths": list(paths),
                          "file_count": count, "sha256": digest})
    version_files = _files((VERSION_PATH,))
    matches_commit &= _matches_commit((VERSION_PATH,), version_files, commit)
    clean = (clean_before and matches_commit and
             _git("status", "--porcelain", "--untracked-files=all") == "" and
             _git("rev-parse", "HEAD") == commit)
    return {"schema": 1, "product": "humanizer-ru",
            "version": _version(version_files[0][1]),
            "source": {"repository": REPOSITORY,
                       "commit": commit, "clean": bool(clean)},
            "artifacts": artifacts,
            "verification": [{"command": c} for c in VERIFY_COMMANDS],
            "note": "local distribution receipt; not an official Agent Skills lockfile"}


def selftest():
    import contextlib
    import io
    import tempfile
    from unittest.mock import patch

    checks = []

    def case(label, ok):
        checks.append(ok)
        print(("PASS: " if ok else "FAIL: ") + label)

    def invoke(*argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(list(argv))

    global ROOT
    original = ROOT
    try:
        with tempfile.TemporaryDirectory(prefix="receipt-test-") as td:
            ROOT = Path(td) / "repo"
            ROOT.mkdir()
            zero_version = b"0." + b"0.0"
            hidden_version = b"9." + b"9.9"
            for name, data in {
                "SKILL.md": b"skill\n", "references/a.md": b"reference\n",
                "dsh/skills/humanizer-ru/SKILL.md": b"skill\n",
                "contract.v1.json": b"{}\n",
                VERSION_PATH: b'__version__ = "' + zero_version + b'"\n',
                ".gitignore": b"*.pyc\n", ".gitattributes": b"* text=auto eol=lf\n",
            }.items():
                target = ROOT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for args in [
                ("init", "-q"), ("add", "."),
                ("-c", "user.name=Receipt Test", "-c", "user.email=receipt@example.invalid",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + td,
                 "commit", "-qm", "fixture"),
            ]:
                if _git(*args) is None:
                    raise RuntimeError("could not create isolated Git fixture")
            baseline = receipt()
            case("clean committed fixture and strict success", baseline["source"]["clean"]
                 and invoke("--strict") == 0)
            case("stable receipt", receipt() == baseline)
            case("all targets", {a["target"] for a in baseline["artifacts"]} == set(TARGETS))
            for name in ("references/extra.pyc", "references/extra.md"):
                target = ROOT / name
                target.write_bytes(b"extra")
                data = receipt()
                case("extra file rejected: " + name,
                     not data["source"]["clean"] and data["artifacts"] != baseline["artifacts"]
                     and invoke("--strict") == 1)
                target.unlink()
            skill = ROOT / "SKILL.md"
            for content in (b"changed\n", b"skill\r\n"):
                skill.write_bytes(content)
                case("changed raw bytes rejected", not receipt()["source"]["clean"]
                     and invoke("--strict") == 1)
            skill.write_bytes(b"skill\n")
            _git("update-index", "--assume-unchanged", "SKILL.md")
            skill.write_bytes(b"hidden edit\n")
            case("assume-unchanged cannot hide edit", not receipt()["source"]["clean"])
            skill.write_bytes(b"skill\n")
            _git("update-index", "--no-assume-unchanged", "SKILL.md")
            _git("update-index", "--assume-unchanged", VERSION_PATH)
            (ROOT / VERSION_PATH).write_bytes(b'__version__ = "' + hidden_version + b'"\n')
            case("hidden version edit rejected", not receipt()["source"]["clean"]
                 and invoke("--strict") == 1)
            (ROOT / VERSION_PATH).write_bytes(b'__version__ = "' + zero_version + b'"\n')
            _git("update-index", "--no-assume-unchanged", VERSION_PATH)
            case("source output rejected without overwrite",
                 invoke("--out", str(skill)) == 2 and skill.read_bytes() == b"skill\n")
            out = Path(td) / "receipt.json"
            case("external output succeeds", invoke("--strict", "--out", str(out)) == 0
                 and json.loads(out.read_text(encoding="utf-8")) == baseline)
            case("existing output preserved", invoke("--out", str(out)) == 2
                 and json.loads(out.read_text(encoding="utf-8")) == baseline)
            out.unlink()
            (ROOT / "references/extra.pyc").write_bytes(b"extra")
            case("strict failure writes no file", invoke("--strict", "--out", str(out)) == 1
                 and not out.exists())
            (ROOT / "references/extra.pyc").unlink()
            with patch.object(Path, "is_symlink", lambda p: p == skill):
                case("linked target rejected", invoke("--json") == 2)
            with patch.object(Path, "is_symlink", lambda p: p == ROOT / "dsh"):
                case("linked ancestor rejected", invoke("--json") == 2)
            with patch.dict(os.environ, {"PATH": ""}):
                case("missing Git rejects strict", invoke("--strict") == 1)
            (ROOT / VERSION_PATH).write_bytes(b"invalid version\n")
            case("invalid version rejected", invoke("--json") == 2)
            (ROOT / VERSION_PATH).write_bytes(b'__version__ = "' + zero_version + b'"\n')
            skill.unlink()
            case("missing target rejected", invoke("--json") == 2)
            case("length framing distinguishes embedded separators",
                 _hash([("a", b"x"), ("b", b"y\0b\0z")])[0] !=
                 _hash([("a", b"x\0b\0y"), ("b", b"z")])[0])
    except (OSError, RuntimeError, ValueError) as exc:
        case("fixture execution: " + str(exc), False)
    finally:
        ROOT = original
    print("SELFTEST install_receipt: %d/%d PASS" % (sum(checks), len(checks)))
    return 0 if all(checks) else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true"); p.add_argument("--out", type=Path)
    p.add_argument("--strict", action="store_true"); p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest: return selftest()
    try:
        if not _output_is_safe(args.out):
            raise ValueError("--out must be outside repository")
        data = receipt()
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.strict and (not data["source"]["commit"] or not data["source"]["clean"]):
            print("receipt rejected: source bytes do not describe a clean commit", file=sys.stderr)
            return 1
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        if args.json or not args.out:
            print(text, end="")
    except (OSError, ValueError) as exc:
        print("receipt unavailable: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__": raise SystemExit(main())
