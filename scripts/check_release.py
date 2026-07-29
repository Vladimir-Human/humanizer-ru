#!/usr/bin/env python3
"""Build and verify a deterministic humanizer-ru skill archive.

Standard-library only. The archive is intended for review and skill upload,
not as a replacement for GitHub's source archive.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import stat
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path, PurePosixPath

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

ROOT_FILES = {
    "SKILL.md", "README.md", "README.en.md", "CHANGELOG.md", "PERSONA.md",
    "SECURITY.md", "SECURITY.en.md", "LICENSE",
}
ROOT_DIRS = {"references", "scripts"}
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".json", ".txt"}
FORBIDDEN_PARTS = {
    ".git", ".github", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".idea", ".vscode",
    "research", "tests",
}
FORBIDDEN_NAMES = {".env", ".DS_Store", "Thumbs.db"}
# Скрипты, которые в архив не попадают. check_corpus.py работает только по
# каталогу research/, а его allowlist в архив не включает: с версии 3.7.0
# валидатор отказывает кодом 2 вместо доклада «ОК» ни о чём, и держать его
# в архиве значит отдавать пользователю заведомо неработающий инструмент.
# check_fixture_sources.py остаётся: его импортирует check_readme_parity.py.
EXCLUDED_SCRIPTS = {"scripts/check_corpus.py"}
SECRET_NAME_RE = re.compile(r"(?:^|[._-])(secret|token|credential|private[_-]?key)(?:$|[._-])", re.I)
FIXED_TIME = (2026, 7, 21, 0, 0, 0)


class ReleaseError(ValueError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(path: str) -> PurePosixPath:
    if "\\" in path:
        raise ReleaseError(f"backslash in archive path: {path!r}")
    p = PurePosixPath(path)
    if p.is_absolute() or not p.parts or any(part in {"", ".", ".."} for part in p.parts):
        raise ReleaseError(f"unsafe archive path: {path!r}")
    return p


def _allowed(p: PurePosixPath) -> bool:
    if len(p.parts) == 1:
        return p.name in ROOT_FILES
    return p.parts[0] in ROOT_DIRS


def _validate_name(p: PurePosixPath) -> None:
    if any(part in FORBIDDEN_PARTS for part in p.parts):
        raise ReleaseError(f"forbidden path: {p}")
    if str(p) in EXCLUDED_SCRIPTS:
        raise ReleaseError(f"script excluded from release archive: {p}")
    if p.name in FORBIDDEN_NAMES or SECRET_NAME_RE.search(p.name):
        raise ReleaseError(f"sensitive or temporary filename: {p}")
    if not _allowed(p):
        raise ReleaseError(f"path is outside release allowlist: {p}")


def _validate_text(name: str, data: bytes) -> None:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseError(f"text file is not UTF-8: {name}: {exc}") from exc


def collect(root: Path) -> list[tuple[PurePosixPath, bytes]]:
    root = root.resolve()
    if not root.is_dir():
        raise ReleaseError(f"release root is not a directory: {root}")
    skill = root / "SKILL.md"
    if not skill.is_file():
        raise ReleaseError("SKILL.md must be a regular file at archive root")
    found: list[tuple[PurePosixPath, bytes]] = []
    candidates: list[Path] = []
    candidates.extend(root / name for name in sorted(ROOT_FILES) if (root / name).is_file())
    for dirname in sorted(ROOT_DIRS):
        directory = root / dirname
        if directory.exists():
            candidates.extend(path for path in directory.rglob("*") if path.is_file() or path.is_symlink())
    for path in sorted(candidates, key=lambda x: x.relative_to(root).as_posix()):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if any(part in FORBIDDEN_PARTS for part in rel.parts) or rel.name in FORBIDDEN_NAMES:
            continue
        if str(rel) in EXCLUDED_SCRIPTS:
            continue
        if path.is_symlink():
            raise ReleaseError(f"symlinks are not allowed: {rel}")
        _validate_name(rel)
        data = path.read_bytes()
        if path.suffix.lower() in TEXT_SUFFIXES or rel.name in ROOT_FILES:
            _validate_text(str(rel), data)
        found.append((rel, data))
    names = {str(p) for p, _ in found}
    if "SKILL.md" not in names:
        raise ReleaseError("SKILL.md missing from collected files")
    if not any(name.startswith("references/") for name in names):
        raise ReleaseError("references/ must contain at least one file")
    return found


def build(root: Path, output: Path) -> str:
    files = collect(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, data in files:
            info = zipfile.ZipInfo(str(rel), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits |= 0x800
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    Path(tmp).replace(output)
    verify(output)
    return sha256(output)


def verify(archive: Path) -> str:
    if not archive.is_file():
        raise ReleaseError(f"archive not found: {archive}")
    seen: set[str] = set()
    with zipfile.ZipFile(archive, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise ReleaseError(f"corrupt ZIP member: {bad}")
        for info in zf.infolist():
            if info.is_dir():
                continue
            p = _safe_rel(info.filename)
            _validate_name(p)
            if info.filename in seen:
                raise ReleaseError(f"duplicate ZIP member: {info.filename}")
            seen.add(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ReleaseError(f"symlink in ZIP: {info.filename}")
            data = zf.read(info)
            if p.suffix.lower() in TEXT_SUFFIXES or p.name in ROOT_FILES:
                _validate_text(info.filename, data)
        if "SKILL.md" not in seen:
            raise ReleaseError("SKILL.md is not at ZIP root")
        if not any(name.startswith("references/") for name in seen):
            raise ReleaseError("references/ missing from ZIP")
    return sha256(archive)


def _minimal(root: Path) -> None:
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: humanizer-ru\ndescription: Test.\n---\n", encoding="utf-8")
    (root / "references" / "test.md").write_text("Тест \uea01 1 \uea02\n", encoding="utf-8")
    (root / "scripts" / "noop.py").write_text("print('ok')\n", encoding="utf-8")


def selftest() -> None:
    passed = 0
    total = 0

    def expect_fail(fn, label: str) -> None:
        nonlocal passed, total
        total += 1
        try:
            fn()
        except (ReleaseError, zipfile.BadZipFile):
            passed += 1
        else:
            raise AssertionError(f"expected failure: {label}")
    with tempfile.TemporaryDirectory(prefix="humanizer-release-") as td:
        base = Path(td)
        good = base / "good"; good.mkdir(); _minimal(good)
        a = base / "a.zip"; b = base / "b.zip"
        digest_a = build(good, a); digest_b = build(good, b)
        assert digest_a == digest_b and a.read_bytes() == b.read_bytes()
        assert verify(a) == digest_a
        passed += 3
        total += 3

        missing = base / "missing"; missing.mkdir(); (missing / "references").mkdir()
        (missing / "references" / "x.md").write_text("x", encoding="utf-8")
        expect_fail(lambda: collect(missing), "missing SKILL.md")

        nested = base / "nested"; (nested / "humanizer-ru" / "references").mkdir(parents=True)
        (nested / "humanizer-ru" / "SKILL.md").write_text("x", encoding="utf-8")
        (nested / "humanizer-ru" / "references" / "x.md").write_text("x", encoding="utf-8")
        expect_fail(lambda: collect(nested), "nested skill root")

        forbidden = base / "forbidden.zip"
        with zipfile.ZipFile(forbidden, "w") as zf:
            zf.writestr("SKILL.md", "x")
            zf.writestr("references/x.md", "x")
            zf.writestr(".env", "TOKEN=x")
        expect_fail(lambda: verify(forbidden), "secret filename")

        outside = base / "outside"; outside.mkdir(); _minimal(outside)
        (outside / "random.bin").write_bytes(b"x")
        outside_zip = base / "outside.zip"; build(outside, outside_zip)
        with zipfile.ZipFile(outside_zip) as zf:
            assert "random.bin" not in zf.namelist()
        passed += 1
        total += 1

        bad_utf = base / "bad-utf"; bad_utf.mkdir(); _minimal(bad_utf)
        (bad_utf / "references" / "bad.md").write_bytes(b"\xff")
        expect_fail(lambda: collect(bad_utf), "invalid UTF-8")

        traversal = base / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as zf:
            zf.writestr("../SKILL.md", "x")
            zf.writestr("references/x.md", "x")
        expect_fail(lambda: verify(traversal), "path traversal")

        duplicate = base / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as zf:
                zf.writestr("SKILL.md", "x")
                zf.writestr("SKILL.md", "y")
                zf.writestr("references/x.md", "x")
        expect_fail(lambda: verify(duplicate), "duplicate member")

        corrupt = base / "corrupt.zip"; corrupt.write_bytes(b"not a zip")
        expect_fail(lambda: verify(corrupt), "corrupt ZIP")

        # 6.5: исключённые скрипты. Сборка их не берёт...
        excluded = base / "excluded"; excluded.mkdir(); _minimal(excluded)
        scripts_dir = excluded / "scripts"; scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "check_corpus.py").write_text("# заглушка\n", encoding="utf-8")
        (scripts_dir / "check_markers.py").write_text("# заглушка\n", encoding="utf-8")
        excluded_zip = base / "excluded.zip"; build(excluded, excluded_zip)
        with zipfile.ZipFile(excluded_zip) as zf:
            members = zf.namelist()
        assert "scripts/check_corpus.py" not in members, "исключённый скрипт попал в архив"
        assert "scripts/check_markers.py" in members, "нужный скрипт пропал из архива"
        passed += 1
        total += 1

        # ...а верификация отвергает архив, в который его подсунули (fail-closed).
        sneaked = base / "sneaked.zip"
        with zipfile.ZipFile(sneaked, "w") as zf:
            zf.writestr("SKILL.md", "x")
            zf.writestr("references/x.md", "x")
            zf.writestr("scripts/check_corpus.py", "# подсунуто\n")
        expect_fail(lambda: verify(sneaked), "excluded script inside archive")
    print(f"release preflight selftest: {passed}/{total} PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--build", type=Path, metavar="ZIP")
    parser.add_argument("--verify", type=Path, metavar="ZIP")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            selftest()
        if args.build:
            if not args.root:
                parser.error("--build requires --root")
            digest = build(args.root, args.build)
            print(f"built: {args.build}")
            print(f"sha256: {digest}")
        elif args.root:
            files = collect(args.root)
            print(f"release tree: {len(files)} files PASS")
        if args.verify:
            print(f"verified: {args.verify}")
            print(f"sha256: {verify(args.verify)}")
        if not any((args.selftest, args.root, args.verify)):
            parser.error("choose --selftest, --root/--build, or --verify")
        return 0
    except (ReleaseError, OSError, zipfile.BadZipFile, AssertionError) as exc:
        print(f"release preflight: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
