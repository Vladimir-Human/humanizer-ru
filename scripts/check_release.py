#!/usr/bin/env python3
"""Сборка и проверка детерминированного релизного архива humanizer-ru.

Только стандартная библиотека. Архив предназначен для ревью и загрузки
скилла, а не для замены исходного архива GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import warnings
import zipfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT_FILES = {
    "SKILL.md", "README.md", "README.en.md", "CHANGELOG.md", "PERSONA.md",
    "SECURITY.md", "SECURITY.en.md", "LICENSE",
    # C10: плагин-манифесты и политика конфиденциальности в корне архива.
    "PRIVACY_POLICY.md", "gemini-extension.json",
}
# C10: каталоги плагин-манифестов, агентских деклараций и слэш-команд
# попадают в релизный архив вместе со скиллом.
ROOT_DIRS = {
    "references", "scripts", "knowledge",
    ".claude-plugin", ".codex-plugin", ".cursor-plugin", "agents", "commands",
}
# Манифесты, чья version обязана совпадать с version из metadata SKILL.md (C10).
MANIFEST_JSON = [
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    "gemini-extension.json",
]
MANIFEST_YAML = ["agents/openai.yaml"]
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".json", ".txt", ".sh"}
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
# SECURITY обещает чистый ASCII в адресах: кириллические пути допустимы
# только в процентной нотации. Ищем URL со схемой в байтовом тексте.
URL_RE = re.compile(rb"https?://[^\s\"'<>`\[\]{}\x00-\x1f]+")
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
        raise ReleaseError(f"обратный слеш в пути архива: {path!r}")
    p = PurePosixPath(path)
    if p.is_absolute() or not p.parts or any(part in {"", ".", ".."} for part in p.parts):
        raise ReleaseError(f"небезопасный путь архива: {path!r}")
    return p

def _allowed(p: PurePosixPath) -> bool:
    if len(p.parts) == 1:
        return p.name in ROOT_FILES
    return p.parts[0] in ROOT_DIRS

def _validate_name(p: PurePosixPath) -> None:
    if any(part in FORBIDDEN_PARTS for part in p.parts):
        raise ReleaseError(f"запрещённый путь: {p}")
    if str(p) in EXCLUDED_SCRIPTS:
        raise ReleaseError(f"скрипт исключён из релизного архива: {p}")
    if p.name in FORBIDDEN_NAMES or SECRET_NAME_RE.search(p.name):
        raise ReleaseError(f"чувствительное или служебное имя файла: {p}")
    if not _allowed(p):
        raise ReleaseError(f"путь вне белого списка релиза: {p}")

def _validate_text(name: str, data: bytes) -> None:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseError(f"текстовый файл не в UTF-8: {name}: {exc}") from exc
    # I.21: чистота переносов — единый LF в отслеживаемых текстовых файлах.
    # CRLF-дрейф у Windows-клонов делал грязным дерево замороженных JSON
    # лидерборда; архив обязан нести канонические переводы.
    if b"\r" in data and name.endswith((".md", ".py", ".yml", ".yaml",
                                        ".json", ".txt", ".sh", ".cff")):
        raise ReleaseError(f"CRLF/CR в текстовом файле архива: {name} "
                           "(переносы должны быть LF)")

def _validate_ascii_urls(name: str, data: bytes) -> None:
    for match in URL_RE.finditer(data):
        url = match.group(0)
        if not url.isascii():
            shown = url.decode("utf-8", "replace")
            raise ReleaseError(
                f"не-ASCII адрес (риск гомоглифа) в {name}: {shown}")

# ---- C10: гейт паритета версий манифестов ----------------------------------

def _skill_version(data: bytes) -> str | None:
    """Версия из metadata SKILL.md (форма X.Y.Z)."""
    text = data.decode("utf-8")
    m = re.search(r'version:\s*"?(\d+\.\d+\.\d+)"?', text)
    return m.group(1) if m else None

def _manifest_version(rel: str, data: bytes) -> str | None:
    """Top-level поле version манифеста: JSON — через json, YAML — строкой."""
    text = data.decode("utf-8")
    if rel.endswith(".json"):
        try:
            return json.loads(text).get("version")
        except ValueError as exc:
            raise ReleaseError(f"невалидный JSON в манифесте {rel}: {exc}") from exc
    # Плоский YAML: version на верхнем уровне без отступа.
    m = re.match(r'^\s*version:\s*[\'"]?([^\'"\s]+)[\'"]?\s*$', text, re.M)
    return m.group(1) if m else None

def _check_manifest_parity(rel_bytes: dict[str, bytes]) -> None:
    """Все присутствующие манифесты несут version, равную version SKILL.md."""
    skill_bytes = rel_bytes.get("SKILL.md", b"")
    skill_ver = _skill_version(skill_bytes)
    if skill_ver is None:
        # Без версии скилла сравнивать не с чем; самого SKILL.md ловит collect.
        return
    for rel in MANIFEST_JSON + MANIFEST_YAML:
        data = rel_bytes.get(rel)
        if data is None:
            continue  # манифеста нет в этом дереве/архиве — нечего сверять
        ver = _manifest_version(rel, data)
        if ver != skill_ver:
            raise ReleaseError(
                f"манифест {rel}: version {ver!r} != версии скилла {skill_ver}")

def collect(root: Path) -> list[tuple[PurePosixPath, bytes]]:
    root = root.resolve()
    if not root.is_dir():
        raise ReleaseError(f"корень релиза не каталог: {root}")
    skill = root / "SKILL.md"
    if not skill.is_file():
        raise ReleaseError("SKILL.md обязан быть обычным файлом в корне архива")
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
            raise ReleaseError(f"симлинки не допускаются: {rel}")
        _validate_name(rel)
        data = path.read_bytes()
        if path.suffix.lower() in TEXT_SUFFIXES or rel.name in ROOT_FILES:
            _validate_text(str(rel), data)
            _validate_ascii_urls(str(rel), data)
        found.append((rel, data))
    names = {str(p) for p, _ in found}
    if "SKILL.md" not in names:
        raise ReleaseError("SKILL.md отсутствует среди собранных файлов")
    if not any(name.startswith("references/") for name in names):
        raise ReleaseError("в references/ должен быть хотя бы один файл")
    _check_manifest_parity({str(p): data for p, data in found})
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
    os.replace(tmp, output)
    verify(output)
    return sha256(output)

def verify(archive: Path) -> str:
    if not archive.is_file():
        raise ReleaseError(f"архив не найден: {archive}")
    seen: set[str] = set()
    rel_bytes: dict[str, bytes] = {}
    with zipfile.ZipFile(archive, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise ReleaseError(f"битый элемент ZIP: {bad}")
        for info in zf.infolist():
            if info.is_dir():
                continue
            p = _safe_rel(info.filename)
            _validate_name(p)
            if info.filename in seen:
                raise ReleaseError(f"дубликат элемента ZIP: {info.filename}")
            seen.add(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ReleaseError(f"симлинк внутри ZIP: {info.filename}")
            data = zf.read(info)
            if p.suffix.lower() in TEXT_SUFFIXES or p.name in ROOT_FILES:
                _validate_text(info.filename, data)
                _validate_ascii_urls(info.filename, data)
            if info.filename == "SKILL.md" or info.filename in MANIFEST_JSON or info.filename in MANIFEST_YAML:
                rel_bytes[info.filename] = data
        if "SKILL.md" not in seen:
            raise ReleaseError("SKILL.md не в корне ZIP")
        if not any(name.startswith("references/") for name in seen):
            raise ReleaseError("references/ отсутствует в ZIP")
        _check_manifest_parity(rel_bytes)
    return sha256(archive)

def _minimal(root: Path) -> None:
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: humanizer-ru\ndescription: Test.\n---\n", encoding="utf-8", newline="\n")
    (root / "references" / "test.md").write_text("Тест \uea01 1 \uea02\n", encoding="utf-8", newline="\n")
    (root / "scripts" / "noop.py").write_text("print('ok')\n", encoding="utf-8", newline="\n")

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
            raise AssertionError(f"ожидался провал: {label}")
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
        (missing / "references" / "x.md").write_text("x", encoding="utf-8", newline="\n")
        expect_fail(lambda: collect(missing), "missing SKILL.md")

        nested = base / "nested"; (nested / "humanizer-ru" / "references").mkdir(parents=True)
        (nested / "humanizer-ru" / "SKILL.md").write_text("x", encoding="utf-8", newline="\n")
        (nested / "humanizer-ru" / "references" / "x.md").write_text("x", encoding="utf-8", newline="\n")
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
        (scripts_dir / "check_corpus.py").write_text("# заглушка\n", encoding="utf-8", newline="\n")
        (scripts_dir / "check_markers.py").write_text("# заглушка\n", encoding="utf-8", newline="\n")
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

        # ASCII-чистота адресов: кириллический URL отвергается при сборке.
        # Домен склеивается из двух литералов: сам скрипт обязан проходить
        # собственную проверку (в исходнике нет готового не-ASCII URL).
        homograph = base / "homograph"; homograph.mkdir(); _minimal(homograph)
        (homograph / "references" / "homograph.md").write_text(
            "Ссылка: https://" + "пример.рф/страница\n", encoding="utf-8", newline="\n")
        expect_fail(lambda: collect(homograph), "non-ASCII address")

        # ...процентная нотация для кириллицы законна...
        encoded = base / "encoded"; encoded.mkdir(); _minimal(encoded)
        (encoded / "references" / "encoded.md").write_text(
            "https://ru.wikipedia.org/wiki/%D0%A2%D0%B5%D1%81%D1%82\n", encoding="utf-8", newline="\n")
        build(encoded, base / "encoded.zip")
        passed += 1
        total += 1

        # ...а подсунутый в архив кириллический URL отвергается верификацией.
        sneaked_url = base / "sneaked-url.zip"
        with zipfile.ZipFile(sneaked_url, "w") as zf:
            zf.writestr("SKILL.md", "x")
            zf.writestr("references/x.md", "https://" + "пример.рф/")
        expect_fail(lambda: verify(sneaked_url), "non-ASCII address inside archive")

        # C10: гейт паритета версий манифестов.
        def _parity_ok(root: Path) -> None:
            (root / "references").mkdir(exist_ok=True)
            (root / "references" / "test.md").write_text("Тест\n", encoding="utf-8", newline="\n")
            (root / "SKILL.md").write_text(
                "---\nname: humanizer-ru\ndescription: Test.\n"
                "metadata:\n  version: \"3.15.0\"\n---\n", encoding="utf-8", newline="\n")
            (root / ".claude-plugin").mkdir(exist_ok=True)
            (root / ".claude-plugin" / "plugin.json").write_text(
                '{"name": "humanizer-ru", "version": "3.15.0"}\n', encoding="utf-8", newline="\n")
            (root / "agents").mkdir(exist_ok=True)
            (root / "agents" / "openai.yaml").write_text(
                'version: "3.15.0"\n', encoding="utf-8", newline="\n")

        # Совпадающие версии во всех манифестах — сборка зелёная.
        parity_ok = base / "parity-ok"; parity_ok.mkdir(); _parity_ok(parity_ok)
        build(parity_ok, base / "parity-ok.zip")
        passed += 1
        total += 1

        # Рассинхрон версии (plugin.json != SKILL.md) обязан валить гейт.
        parity_bad = base / "parity-bad"; parity_bad.mkdir(); _parity_ok(parity_bad)
        (parity_bad / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "humanizer-ru", "version": "9.9.9"}\n', encoding="utf-8", newline="\n")
        expect_fail(lambda: collect(parity_bad), "manifest version mismatch")

        # Нечётный YAML с чужой версией тоже обязан падать.
        parity_yaml = base / "parity-yaml"; parity_yaml.mkdir(); _parity_ok(parity_yaml)
        (parity_yaml / "agents" / "openai.yaml").write_text(
            'version: "0.0.1"\n', encoding="utf-8", newline="\n")
        expect_fail(lambda: collect(parity_yaml), "openai.yaml version mismatch")

        # Подсунутый в архив рассинхроненный манифест отвергается верификацией.
        parity_sneak = base / "parity-sneak.zip"
        with zipfile.ZipFile(parity_sneak, "w") as zf:
            zf.writestr("SKILL.md",
                        "---\nmetadata:\n  version: \"3.15.0\"\n---\n")
            zf.writestr("references/x.md", "x")
            zf.writestr(".claude-plugin/plugin.json",
                        '{"name": "humanizer-ru", "version": "2.0.0"}\n')
        expect_fail(lambda: verify(parity_sneak), "archive manifest version mismatch")
    print(f"САМОПРОВЕРКА релизного префлайта: {passed}/{total} PASS")

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
                parser.error("--build требует --root")
            digest = build(args.root, args.build)
            print(f"собрано: {args.build}")
            print(f"sha256: {digest}")
        elif args.root:
            files = collect(args.root)
            print(f"релизное дерево: {len(files)} файлов, ОК")
        if args.verify:
            print(f"проверено: {args.verify}")
            print(f"sha256: {verify(args.verify)}")
        if not any((args.selftest, args.root, args.verify)):
            parser.error("выберите --selftest, --root/--build или --verify")
        return 0
    except (ReleaseError, OSError, zipfile.BadZipFile, AssertionError) as exc:
        print(f"предрелизная проверка: ПРОВАЛ: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
