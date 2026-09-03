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
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
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

# ---- Контракт выпуска: подписанный тег + опубликованный Release ------------
# GOVERNANCE п.2: тег vX.Y.Z обязан быть annotated и GPG-подписан; лёгкие и
# неподписанные теги не являются выпусками. Зелёный чек-лист сам по себе
# выпуском не считается: выпуск существует, когда подписанный тег и
# соответствующий ему GitHub Release на месте.

GPG_SIG_MARKER = "-----BEGIN PGP SIGNATURE-----"


def _skill_version_file(root: Path) -> str | None:
    skill = root / "SKILL.md"
    if not skill.is_file():
        return None
    return _skill_version(skill.read_bytes())


def _tag_object_signed(tag_text: str) -> bool:
    """Объект тега несёт блок GPG-подписи."""
    return GPG_SIG_MARKER in tag_text


def _repo_slug_from_url(url: str) -> str | None:
    """owner/repo github из remote URL (https или ssh форма)."""
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None
    return "%s/%s" % (m.group(1), m.group(2))


def _release_status(slug: str, tag: str) -> int:
    """GET /releases/tags/<tag>: HTTP-код (200 опубликован, 404 нет).

    Сетевой отказ (URLError и прочее OSError) пробрасывается вызывающему —
    это код 2 «проверка невозможна», а не «Release отсутствует».
    """
    url = "https://api.github.com/repos/%s/releases/tags/%s" % (slug, tag)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "humanizer-ru-check-release",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def release_contract(root: Path) -> int:
    """Контракт выпуска для текущей версии SKILL.md.

    Состояние до выпуска (тег текущей версии ещё не создан) законно:
    проверка срабатывает, как только тег появился. Тогда тег обязан быть
    annotated и подписан, а Release — опубликован.

    Коды: 0 — контракт выполнен либо выпуск ещё не начат; 1 — нарушение;
    2 — проверка невозможна (git/сеть/API недоступны).
    """
    version = _skill_version_file(root)
    if version is None:
        print("RELEASE-КОНТРАКТ: версия SKILL.md не читается", file=sys.stderr)
        return 2
    tag = "v" + version

    def _git(*args):
        return subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=60,
                              encoding="utf-8", errors="replace")

    try:
        listed = _git("tag", "-l", tag)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("RELEASE-КОНТРАКТ: git недоступен: %r" % (exc,), file=sys.stderr)
        return 2
    if listed.returncode != 0:
        print("RELEASE-КОНТРАКТ: git tag -l code %d: %s"
              % (listed.returncode, listed.stderr.strip()[:200]), file=sys.stderr)
        return 2
    if not listed.stdout.strip():
        print("RELEASE-КОНТРАКТ: тег %s ещё не создан — состояние до выпуска "
              "допустимо; при выпуске тег обязан быть подписан, а Release "
              "опубликован" % tag)
        return 0
    try:
        obj = _git("cat-file", "tag", tag)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("RELEASE-КОНТРАКТ: git недоступен: %r" % (exc,), file=sys.stderr)
        return 2
    if obj.returncode != 0:
        print("[FAIL] RELEASE-КОНТРАКТ: тег %s не annotated — лёгкие теги не "
              "являются выпусками (GOVERNANCE п.2)" % tag)
        return 1
    if not _tag_object_signed(obj.stdout):
        print("[FAIL] RELEASE-КОНТРАКТ: тег %s не подписан GPG (GOVERNANCE п.2)" % tag)
        return 1
    try:
        remote = _git("config", "remote.origin.url")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("RELEASE-КОНТРАКТ: git недоступен: %r" % (exc,), file=sys.stderr)
        return 2
    slug = _repo_slug_from_url(remote.stdout) if remote.returncode == 0 else None
    if slug is None:
        print("RELEASE-КОНТРАКТ: репозиторий не определён из remote.origin.url "
              "— проверка Release невозможна", file=sys.stderr)
        return 2
    try:
        status = _release_status(slug, tag)
    except OSError as exc:
        print("RELEASE-КОНТРАКТ: проверка Release невозможна (сеть/API): %r"
              % (exc,), file=sys.stderr)
        return 2
    if status == 200:
        print("RELEASE-КОНТРАКТ: тег %s подписан, Release опубликован — "
              "выпуск действителен" % tag)
        return 0
    if status == 404:
        print("[FAIL] RELEASE-КОНТРАКТ: тег %s подписан, но Release не "
              "опубликован — зелёный чек-лист сам по себе выпуском не "
              "считается" % tag)
        return 1
    print("RELEASE-КОНТРАКТ: проверка Release невозможна, код API %d" % status,
          file=sys.stderr)
    return 2


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

        # Контракт выпуска: чистые помощники с негативными кейсами
        # (GPG-маркер в объекте тега; owner/repo из https и ssh remote).
        signed_tag = ("object d4a35cc\ntype commit\ntag v3.16.9\n"
                      "-----BEGIN PGP SIGNATURE-----\nabc\n"
                      "-----END PGP SIGNATURE-----\n")
        unsigned_tag = "object d4a35cc\ntype commit\ntag v3.16.9\n\nmessage\n"
        assert _tag_object_signed(signed_tag), "подписанный тег не распознан"
        assert not _tag_object_signed(unsigned_tag), "неподписанный тег принят"
        assert (_repo_slug_from_url(
            "https://github.com/Vladimir-Human/humanizer-ru.git")
            == "Vladimir-Human/humanizer-ru"), "https remote не разобран"
        assert (_repo_slug_from_url(
            "git@github.com:Vladimir-Human/humanizer-ru.git")
            == "Vladimir-Human/humanizer-ru"), "ssh remote не разобран"
        assert _repo_slug_from_url("https://example.com/repo") is None
        passed += 1
        total += 1
    # --sdist-test, негатив: несуществующий sdist — отказ среды (код 2),
    # а не молчаливый ноль.
    rc_missing = sdist_test(Path("."), "нет-такого-sdist.tar.gz")
    assert rc_missing == 2, f"несуществующий sdist: ждали 2, получили {rc_missing}"
    passed += 1
    total += 1
    print(f"САМОПРОВЕРКА релизного префлайта: {passed}/{total} PASS")

# ------------------------------------------------------- sdist -> venv -> тесты

class SdistEnvError(RuntimeError):
    """Среда отказала (нет сети, venv или модуля build) — код 2, не провал."""


def _venv_python(venvdir: Path) -> Path:
    if os.name == "nt":
        return venvdir / "Scripts" / "python.exe"
    return venvdir / "bin" / "python"


def _sdist_resolve(root: Path, arg: str) -> Path:
    if arg != "auto":
        p = Path(arg)
        if not p.is_file():
            raise SdistEnvError(
                f"sdist не найден: {p} (сборка: python -m build --sdist)")
        return p
    dist = root / "dist"
    cands = sorted(dist.glob("humanizer_ru-*.tar.gz")) if dist.is_dir() else []
    if cands:
        return cands[-1]
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(dist)],
        cwd=str(root), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SdistEnvError("сборка sdist не удалась (модуль build/сеть): "
                            + (proc.stderr or "")[-300:])
    cands = sorted(dist.glob("humanizer_ru-*.tar.gz"))
    if not cands:
        raise SdistEnvError("после сборки в dist/ нет sdist")
    return cands[-1]


def sdist_test(root: Path, arg: str) -> int:
    """sdist -> чистое venv -> тесты + CLI-зонды (housekeeping-патч).

    Устанавливает собранный sdist в свежее временное venv и проверяет, что
    поставка самодостаточна: тесты из sdist проходят (репо-only модули
    честно скипаются), --version печатает версию пакета, --contract —
    контракт из данных пакета, --json-выводы соответствуют конверту.
    Коды: 0 — пройдено; 1 — провал тестов/зондов/состава; 2 — отказ среды
    (нет сети, venv, модуля build или файла sdist).
    """
    import shutil
    import tarfile
    import tempfile
    import textwrap
    try:
        sdist = _sdist_resolve(root, arg)
    except SdistEnvError as exc:
        print(f"SDIST-TEST: отказ среды: {exc}", file=sys.stderr)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="sdist-test-"))
    try:
        with tarfile.open(sdist, "r:gz") as tf:
            try:
                tf.extractall(tmp, filter="data")
            except TypeError:      # Python < 3.12: аргумента filter нет
                tf.extractall(tmp)
        pkgs = [d for d in tmp.iterdir() if d.is_dir() and (d / "tests").is_dir()]
        if not pkgs:
            print("SDIST-TEST: в sdist нет tests/ — MANIFEST.in не сработал",
                  file=sys.stderr)
            return 1
        src = pkgs[0]
        venv = tmp / "venv"
        proc = subprocess.run([sys.executable, "-m", "venv", str(venv)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print("SDIST-TEST: venv не создан: " + (proc.stderr or "")[-200:],
                  file=sys.stderr)
            return 2
        vpy = _venv_python(venv)
        proc = subprocess.run(
            [str(vpy), "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", str(sdist)],
            capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            print("SDIST-TEST: установка sdist не удалась (сеть?): "
                  + (proc.stderr or "")[-300:], file=sys.stderr)
            return 2
        proc = subprocess.run(
            [str(vpy), "-m", "unittest", "discover", "-s", "tests"],
            capture_output=True, text=True, timeout=900, cwd=str(src))
        tail = [ln for ln in (proc.stderr or "").strip().splitlines() if ln][-3:]
        if proc.returncode != 0:
            print("SDIST-TEST: тесты в чистом venv ПРОВАЛЕНЫ:\n  "
                  + "\n  ".join(tail), file=sys.stderr)
            return 1
        print("SDIST-TEST: тесты: " + " | ".join(tail[-2:]))
        probe = textwrap.dedent("""
            import contextlib, io, json, os, tempfile
            from humanizer_ru import __version__
            from humanizer_ru.cli import scan_main, markers_main, polish_main
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = scan_main(["--version"])
            assert rc == 0 and buf.getvalue().strip() == __version__, "--version"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = markers_main(["--contract"])
            doc = json.loads(buf.getvalue())
            assert rc == 0 and doc["schema_version"] == "contract.v1", "--contract"
            assert len(doc["tools"]) == 4, "contract tools"
            fd, p = tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("Обычный русский текст без дефектов.\\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = polish_main(["--json", p])
            env = json.loads(buf.getvalue())
            assert rc == 0 and env["tool"] == "humanizer-polish" \\
                and env["schema"] == 1, "polish envelope"
            os.unlink(p)
            # MCP: точка входа humanizer-mcp установлена и сервер отвечает
            # на initialize (roundtrip одной строкой JSON-RPC).
            import subprocess as _sp, sys as _sys
            exe = "humanizer-mcp" + (".exe" if os.name == "nt" else "")
            mcp_exe = os.path.join(os.path.dirname(_sys.executable), exe)
            assert os.path.isfile(mcp_exe), \\
                "точка входа humanizer-mcp не установлена"
            init = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": "initialize",
                               "params": {"protocolVersion": "2025-06-18",
                                          "capabilities": {},
                                          "clientInfo": {"name": "sdist",
                                                         "version": "0"}}})
            mp = _sp.run([mcp_exe], input=init + "\\n",
                         stdout=_sp.PIPE, stderr=_sp.DEVNULL, timeout=120,
                         encoding="utf-8", errors="replace")
            mr = json.loads(mp.stdout.strip().splitlines()[0])
            assert mr["result"]["protocolVersion"] == "2025-06-18", \\
                "MCP initialize roundtrip"
            assert mr["result"]["serverInfo"]["version"] == __version__, \\
                "MCP serverInfo.version"
            print("PROBES OK " + __version__)
        """)
        proc = subprocess.run([str(vpy), "-c", probe], capture_output=True,
                              text=True, timeout=300)
        if proc.returncode != 0:
            print("SDIST-TEST: CLI-зонды ПРОВАЛЕНЫ: " + (proc.stderr or "")[-400:],
                  file=sys.stderr)
            return 1
        print("SDIST-TEST: " + proc.stdout.strip()
              + f" (чистое venv, sdist {sdist.name})")
        return 0
    except (OSError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        print(f"SDIST-TEST: отказ среды: {exc!r}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--build", type=Path, metavar="ZIP")
    parser.add_argument("--verify", type=Path, metavar="ZIP")
    parser.add_argument("--release-contract", action="store_true",
                        help="контракт выпуска: тег версии SKILL.md подписан "
                             "и GitHub Release опубликован (0 — выполнен или "
                             "выпуск не начат, 1 — нарушение, 2 — проверка "
                             "невозможна)")
    parser.add_argument("--sdist-test", nargs="?", const="auto",
                        default=None, metavar="SDIST",
                        help="sdist -> чистое venv -> тесты + CLI-зонды "
                             "(без значения: взять/собрать dist/*.tar.gz; "
                             "0 — пройдено, 1 — провал, 2 — отказ среды)")
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
        elif args.root and not args.release_contract and not args.sdist_test:
            files = collect(args.root)
            print(f"релизное дерево: {len(files)} файлов, ОК")
        if args.verify:
            print(f"проверено: {args.verify}")
            print(f"sha256: {verify(args.verify)}")
        rc_contract = 0
        if args.release_contract:
            rc_contract = release_contract(args.root or Path("."))
        rc_sdist = 0
        if args.sdist_test is not None:
            rc_sdist = sdist_test(args.root or Path("."), args.sdist_test)
        if not any((args.selftest, args.root, args.build, args.verify,
                    args.release_contract, args.sdist_test is not None)):
            parser.error("выберите --selftest, --root/--build, --verify, "
                         "--release-contract или --sdist-test")
        return rc_contract or rc_sdist
    except (ReleaseError, OSError, zipfile.BadZipFile, AssertionError) as exc:
        print(f"предрелизная проверка: ПРОВАЛ: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
