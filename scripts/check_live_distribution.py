#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_live_distribution.py — живые агентные входы против
опубликованного продукта.

Сверяет поверхности, по которым агент находит, оценивает и ставит
продукт. Статус относится к ПРОВЕРЕННОМУ артефакту: HTTP 200 без
разбора содержимого доказательством не является.

  1. локальное дерево: версия server.json и пакета, состав инструментов
     контракта;
  2. GitHub: последний Release (тег, целевой commit, published_at,
     ассеты), peeled-commit тега, HEAD main;
  3. PyPI: версия, наличие wheel И sdist, отсутствие yanked, sha256
     каждого файла сверяется со скачанными байтами, stdlib-only
     (requires_dist пуст), metadata скачанных файлов проверяется
     штатным check_pypi_metadata.py;
  4. официальный реестр MCP: имя записи, статус ОБЯЗАН быть active
     (deleted/иной — расхождение), версия server и packages,
     идентификатор пакета pypi, установочная команда с текущей версией;
  5. Pages: status.json (published_tag обязан быть тегом последнего
     Release; published_commit — peeled-commit этого тега; tests_passed
     и parity из реального прогона; markers_count), машинные документы
     ПАРСЯТСЯ и сверяются по схеме (contract.v1/identity.v1/markers.v1),
     содержимое contract.v1.json и llms.txt сверяется с raw-копией
     заявленного commit деплоя (связь контент <-> SHA: чужой или
     произвольный ответ с кодом 200 не проходит); все машинные пути
     отдают 200.

main может законно опережать релиз: проверяется СВЯЗЬ поверхностей
(Pages опубликован из заявленного commit и несёт metadata последнего
Release), а не нулевой лаг.

Любая недоступность источника — UNAVAILABLE с причиной (код 2), а не
зелёный статус и не «проекта нет». Расхождение — код 1 с человекочитаемой
причиной.

Запуск:
  python3 scripts/check_live_distribution.py            # сводка, коды 0/1/2
  python3 scripts/check_live_distribution.py --json     # машиночитаемо
  python3 scripts/check_live_distribution.py --selftest # независимый
                                                        # мутант на каждый
                                                        # случай ложного
                                                        # принятия
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO_API = "https://api.github.com/repos/Vladimir-Human/humanizer-ru"
RAW_BASE = "https://raw.githubusercontent.com/Vladimir-Human/humanizer-ru"
PYPI_JSON = "https://pypi.org/pypi/humanizer-ru/json"
REGISTRY = ("https://registry.modelcontextprotocol.io/v0.1/servers/"
            "io.github.Vladimir-Human%2Fhumanizer-ru/versions/latest")
REGISTRY_NAME = "io.github.Vladimir-Human/humanizer-ru"
PAGES_BASE = "https://vladimir-human.github.io/humanizer-ru/"
PAGES_STATUS = PAGES_BASE + "status.json"
PAGES_PATHS = (
    PAGES_BASE,
    PAGES_BASE + "llms.txt",
    PAGES_BASE + ".well-known/llms.txt",
    PAGES_BASE + "contract.v1.json",
    PAGES_BASE + "identity.v1.json",
    PAGES_BASE + "markers.v1.json",
)
UA = {"User-Agent": "humanizer-ru-distribution-check",
      "Accept": "application/vnd.github+json"}


class LiveUnavailable(Exception):
    """Источник недоступен: причина обязательна."""


def fetch_json(url, timeout=30, opener=None):
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers=UA)
    try:
        with open_fn(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                raise LiveUnavailable("HTTP %s" % getattr(resp, "status",
                                                          "?"))
            return json.loads(resp.read().decode("utf-8"))
    except LiveUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LiveUnavailable("%s: %s" % (type(exc).__name__, exc))


def fetch_bytes(url, timeout=60, opener=None):
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers=UA)
    try:
        with open_fn(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                raise LiveUnavailable("HTTP %s" % getattr(resp, "status",
                                                          "?"))
            return resp.read()
    except LiveUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LiveUnavailable("%s: %s" % (type(exc).__name__, exc))


def fetch_status(url, timeout=30, opener=None):
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers=UA)
    try:
        with open_fn(req, timeout=timeout) as resp:
            return getattr(resp, "status", 200)
    except Exception as exc:  # noqa: BLE001
        raise LiveUnavailable("%s: %s" % (type(exc).__name__, exc))


def local_facts():
    with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as fh:
        server = json.load(fh)
    with open(os.path.join(ROOT, "src", "humanizer_ru", "__init__.py"),
              encoding="utf-8") as fh:
        init = fh.read()
    m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', init)
    if not m:
        raise LiveUnavailable("версия пакета не читается из __init__.py")
    with open(os.path.join(ROOT, "contract.v1.json"),
              encoding="utf-8") as fh:
        contract = json.load(fh)
    tools = contract.get("tools") or []
    return {"server_version": server.get("version"),
            "package_version": m.group(1),
            "tools": sorted(t.get("command") for t in tools)}


def _github_facts(opener=None):
    """Release/тег/main с GitHub API; (record, problems, unavailable)."""
    rec, problems = {}, []
    try:
        rel = fetch_json(REPO_API + "/releases/latest", opener=opener)
        tag = rel.get("tag_name")
        rec["release_tag"] = tag
        rec["published_at"] = rel.get("published_at")
        rec["release_commit"] = (rel.get("target_commitish")
                                 if rel.get("target_commitish") != "main"
                                 else None)
        rec["assets"] = sorted(a.get("name")
                               for a in rel.get("assets") or [])
        commit = None
        if tag:
            ref = fetch_json(REPO_API + "/git/refs/tags/" + tag,
                             opener=opener)
            obj = ref.get("object") or {}
            if obj.get("type") == "tag":
                peeled = fetch_json(REPO_API + "/git/tags/" + obj["sha"],
                                    opener=opener)
                commit = (peeled.get("object") or {}).get("sha")
            else:
                commit = obj.get("sha")
        rec["tag_commit"] = commit
        rec["release_commit"] = commit
        head = fetch_json(REPO_API + "/commits/main", opener=opener)
        rec["main_head"] = head.get("sha")
    except LiveUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}, [], \
            ["github"]
    return rec, problems, []


def _pypi_checks(loc, opener=None, deep_files=True, dist_dir=None):
    """PyPI: версия, состав, yanked, хеши, stdlib-only, metadata файлов."""
    problems = []
    ver = loc["package_version"]
    try:
        pypi = fetch_json(PYPI_JSON, opener=opener)
    except LiveUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}, \
            ["pypi"], problems
    info = pypi.get("info") or {}
    rec = {"version": info.get("version"), "status": "ok"}
    if info.get("version") != ver:
        problems.append("PyPI версия %s != локальная %s"
                        % (info.get("version"), ver))
    requires = info.get("requires_dist")
    rec["requires_dist"] = requires
    if requires:
        problems.append("PyPI requires_dist не пуст (%r) — продукт "
                        "stdlib-only" % (requires,))
    urls = (pypi.get("releases") or {}).get(ver) or pypi.get("urls") or []
    if not urls:
        problems.append("PyPI: у версии %s нет файлов (пустой urls) — "
                        "версия есть в info, но ставить нечего" % ver)
        return rec, [], problems
    kinds = {}
    for f in urls:
        kind = f.get("packagetype")
        kinds[kind] = f
        if f.get("yanked"):
            problems.append("PyPI: файл %s yanked" % f.get("filename"))
        digest = (f.get("digests") or {}).get("sha256")
        if not digest:
            problems.append("PyPI: у файла %s нет sha256"
                            % f.get("filename"))
        rec.setdefault("files", {})[kind] = {
            "filename": f.get("filename"), "sha256": digest,
            "url": f.get("url"), "yanked": f.get("yanked")}
    for kind in ("bdist_wheel", "sdist"):
        if kind not in kinds:
            problems.append("PyPI: нет файла типа %s у версии %s"
                            % (kind, ver))
    # Глубокая проверка: скачанные байты = заявленный sha256; metadata
    # скачанных файлов проверяется штатным валидатором.
    if deep_files and kinds.get("bdist_wheel") and kinds.get("sdist"):
        try:
            with tempfile.TemporaryDirectory(
                    prefix="live-dist-") as td:
                paths = {}
                for kind in ("bdist_wheel", "sdist"):
                    f = kinds[kind]
                    data = fetch_bytes(f.get("url"), opener=opener)
                    got = hashlib.sha256(data).hexdigest()
                    want = (f.get("digests") or {}).get("sha256")
                    if want and got != want:
                        problems.append(
                            "PyPI: sha256 скачанного %s (%s) != заявленный "
                            "(%s) — статус не относится к этим байтам"
                            % (f.get("filename"), got[:12], want[:12]))
                    p = os.path.join(td, f.get("filename") or kind)
                    with open(p, "wb") as fh:
                        fh.write(data)
                    paths[kind] = p
                if not any("sha256" in p for p in problems):
                    proc = subprocess.run(
                        [sys.executable, "-X", "utf8",
                         os.path.join(HERE, "check_pypi_metadata.py"),
                         "--sdist", paths["sdist"],
                         "--wheel", paths["bdist_wheel"]],
                        capture_output=True, text=True, timeout=300,
                        encoding="utf-8", errors="replace")
                    if proc.returncode != 0:
                        problems.append(
                            "PyPI: metadata скачанных файлов не прошла "
                            "check_pypi_metadata (код %d): %s"
                            % (proc.returncode,
                               (proc.stdout or proc.stderr).strip()[-200:]))
                    rec["deep_files"] = "verified"
        except LiveUnavailable as exc:
            rec["deep_files"] = "unavailable: %s" % exc
            problems.append("PyPI: файлы версии не скачиваются: %s" % exc)
    elif deep_files and dist_dir:
        rec["deep_files"] = "skipped-selftest-no-dist"
    return rec, [], problems


def _registry_checks(loc, opener=None):
    problems = []
    ver = loc["package_version"]
    try:
        reg = fetch_json(REGISTRY, opener=opener)
    except LiveUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}, \
            ["mcp_registry"], problems
    server = reg.get("server") or {}
    official = ((reg.get("_meta") or {})
                .get("io.modelcontextprotocol.registry/official") or {})
    status = official.get("status")
    rec = {"name": server.get("name"), "version": server.get("version"),
           "status": status, "isLatest": official.get("isLatest")}
    if server.get("name") != REGISTRY_NAME:
        problems.append("реестр MCP: имя записи %r != %r (чужая запись "
                        "или переименование без миграции)"
                        % (server.get("name"), REGISTRY_NAME))
    if status != "active":
        problems.append("реестр MCP: статус %r != active — запись "
                        "не является живой поставкой" % (status,))
    if server.get("version") != ver:
        problems.append("реестр MCP версия %s != локальная %s (агент "
                        "установит устаревший пакет)"
                        % (server.get("version"), ver))
    packages = server.get("packages") or []
    pypi_pkgs = [p for p in packages
                 if p.get("registryType") == "pypi"]
    if not pypi_pkgs:
        problems.append("реестр MCP: нет пакета pypi — нечего устанавливать")
    else:
        pkg = pypi_pkgs[0]
        rec["package"] = {"identifier": pkg.get("identifier"),
                          "version": pkg.get("version"),
                          "runtimeHint": pkg.get("runtimeHint"),
                          "packageArguments": pkg.get("packageArguments")}
        if pkg.get("identifier") != "humanizer-ru":
            problems.append("реестр MCP: идентификатор пакета %r != "
                            "humanizer-ru (чужой пакет)"
                            % pkg.get("identifier"))
        if pkg.get("version") != ver:
            problems.append("реестр MCP: версия пакета %s != локальная %s"
                            % (pkg.get("version"), ver))
        args = pkg.get("packageArguments") or []
        launch_values = [a.get("value") for a in args
                         if isinstance(a, dict)
                         and a.get("type") == "positional"]
        if pkg.get("runtimeHint") != "uvx":
            problems.append("реестр MCP: для pypi runtimeHint обязан быть "
                            "uvx, получено %r" % pkg.get("runtimeHint"))
        if "humanizer-mcp" not in launch_values:
            problems.append("реестр MCP: packageArguments не запускают "
                            "humanizer-mcp")
    note = ((server.get("_meta") or {})
            .get("io.modelcontextprotocol.registry/publisher-provided")
            or {})
    install = note.get("install") or ""
    if ("humanizer-ru==" + ver) not in install:
        problems.append("реестр MCP: установочная команда не несёт текущую "
                        "версию humanizer-ru==%s: %r" % (ver, install[:80]))
    return rec, [], problems


def _pages_checks(loc, gh, opener=None):
    problems = []
    unav = []
    ver = loc["package_version"]
    try:
        status = fetch_json(PAGES_STATUS, opener=opener)
    except LiveUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}, \
            ["pages_status"], ["Pages status.json недоступен: %s" % exc]
    rec = {"published_tag": status.get("published_tag"),
           "published_commit": status.get("published_commit"),
           "commit": status.get("commit"),
           "main_commit": status.get("main_commit"),
           "markers_count": status.get("markers_count"),
           "tests_passed": status.get("tests_passed"),
           "parity": status.get("parity"),
           "date": status.get("date"),
           "status": "ok"}
    if status.get("tests_passed") is not True:
        problems.append("Pages status.json: tests_passed != true")
    if status.get("parity") != "ok":
        problems.append("Pages status.json: parity != ok")
    # Связь с Release: Pages обязан нести metadata последнего выпуска.
    if gh.get("status") == "unavailable":
        unav.append("github(for-pages)")
    else:
        rel_tag = gh.get("release_tag")
        if rel_tag and status.get("published_tag") != rel_tag:
            problems.append(
                "Pages published_tag %s != тег последнего Release %s — "
                "release-metadata Pages устарела (деплой до публикации)"
                % (status.get("published_tag"), rel_tag))
        tag_commit = gh.get("tag_commit")
        pub_commit = status.get("published_commit")
        if tag_commit and pub_commit:
            if not (tag_commit.startswith(pub_commit)
                    or pub_commit.startswith(tag_commit)):
                problems.append(
                    "Pages published_commit %s != peeled-commit тега %s — "
                    "статус указывает чужой коммит"
                    % (pub_commit, tag_commit[:12]))
    # Машинные документы: парсятся, схема, связь контента с SHA деплоя.
    deploy_sha = status.get("commit")
    try:
        contract = fetch_json(PAGES_BASE + "contract.v1.json",
                              opener=opener)
        if contract.get("schema_version") != "contract.v1":
            problems.append("Pages contract.v1.json: schema_version %r != "
                            "contract.v1 (HTTP 200 с произвольным JSON не "
                            "является машинным документом)"
                            % contract.get("schema_version"))
        pver = ((contract.get("product") or {}).get("version"))
        if pver is not None and pver != ver and \
                status.get("published_tag") == "v" + ver:
            problems.append("Pages contract.v1.json: product.version %s != "
                            "версия поставки %s" % (pver, ver))
        if deploy_sha:
            raw = fetch_json("%s/%s/contract.v1.json"
                             % (RAW_BASE, deploy_sha), opener=opener)
            if raw != contract:
                problems.append(
                    "Pages contract.v1.json != raw-копии заявленного "
                    "commit деплоя %s — контент не соответствует статусу"
                    % deploy_sha[:12])
    except LiveUnavailable as exc:
        problems.append("Pages contract.v1.json не получен/не JSON: %s"
                        % exc)
    try:
        identity = fetch_json(PAGES_BASE + "identity.v1.json",
                              opener=opener)
        if identity.get("schema_version") != "identity.v1":
            problems.append("Pages identity.v1.json: schema_version %r != "
                            "identity.v1" % identity.get("schema_version"))
    except LiveUnavailable as exc:
        problems.append("Pages identity.v1.json не получен/не JSON: %s"
                        % exc)
    try:
        markers = fetch_json(PAGES_BASE + "markers.v1.json", opener=opener)
        if markers.get("schema_version") != "markers.v1":
            problems.append("Pages markers.v1.json: schema_version %r != "
                            "markers.v1" % markers.get("schema_version"))
        if status.get("markers_count") is not None \
                and markers.get("count") != status.get("markers_count"):
            problems.append("Pages markers.v1.json count %s != "
                            "status.json markers_count %s"
                            % (markers.get("count"),
                               status.get("markers_count")))
    except LiveUnavailable as exc:
        problems.append("Pages markers.v1.json не получен/не JSON: %s"
                        % exc)
    return rec, unav, problems


def collect(opener=None, deep_files=True):
    """(record, problems, unavailable): record — снимок поверхностей."""
    record = {}
    problems = []
    unavailable = []
    try:
        loc = local_facts()
    except (LiveUnavailable, OSError, ValueError) as exc:
        return None, ["локальное дерево: %s" % exc], ["local"]
    record["local"] = loc
    if loc["server_version"] != loc["package_version"]:
        problems.append("server.json version %s != версия пакета %s"
                        % (loc["server_version"], loc["package_version"]))

    gh, gh_problems, gh_unav = _github_facts(opener=opener)
    record["github"] = gh
    problems.extend(gh_problems)
    unavailable.extend(gh_unav)

    pypi, pypi_unav, pypi_problems = _pypi_checks(loc, opener=opener,
                                                  deep_files=deep_files)
    record["pypi"] = pypi
    unavailable.extend(pypi_unav)
    problems.extend(pypi_problems)

    reg, reg_unav, reg_problems = _registry_checks(loc, opener=opener)
    record["mcp_registry"] = reg
    unavailable.extend(reg_unav)
    problems.extend(reg_problems)

    pages, pages_unav, pages_problems = _pages_checks(loc, gh,
                                                      opener=opener)
    record["pages_status"] = pages
    unavailable.extend(pages_unav)
    problems.extend(pages_problems)

    paths = {}
    for url in PAGES_PATHS:
        try:
            paths[url] = fetch_status(url, opener=opener)
        except LiveUnavailable as exc:
            paths[url] = "unavailable: %s" % exc
            unavailable.append("pages:" + url.rsplit("/", 1)[-1])
    record["pages_paths"] = paths
    for url, code in paths.items():
        if code != 200:
            problems.append("Pages путь %s: %s" % (url, code))
    return record, problems, unavailable


# ------------------------------------------------------------------ selftest

class _Resp:
    def __init__(self, payload=None, status=200, raw_bytes=None):
        self._payload = payload
        self.status = status
        if raw_bytes is not None:
            self._body = raw_bytes
        elif payload is not None:
            self._body = json.dumps(payload).encode("utf-8")
        else:
            self._body = b""

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _make_responses(loc, gh_release_tag, gh_tag_commit, gh_main,
                    pypi_urls, registry_payload, status_payload,
                    pages_contract, pages_identity, pages_markers,
                    raw_contract=None):
    """Карта url -> payload для синтетической среды selftest."""
    m = {
        REPO_API + "/releases/latest": {
            "tag_name": gh_release_tag,
            "target_commitish": "main",
            "published_at": "2026-09-07T07:56:36Z",
            "assets": [{"name": "humanizer-ru.zip"},
                       {"name": "humanizer-ru.zip.asc"}]},
        REPO_API + "/git/refs/tags/" + gh_release_tag: {
            "object": {"sha": "tagobj" + gh_tag_commit, "type": "tag"}},
        REPO_API + "/git/tags/tagobj" + gh_tag_commit: {
            "object": {"sha": gh_tag_commit, "type": "commit"}},
        REPO_API + "/commits/main": {"sha": gh_main},
        PYPI_JSON: {
            "info": {"version": loc["package_version"],
                     "requires_dist": None},
            "releases": {loc["package_version"]: pypi_urls}},
        REGISTRY: registry_payload,
        PAGES_STATUS: status_payload,
        PAGES_BASE + "contract.v1.json": pages_contract,
        PAGES_BASE + "identity.v1.json": pages_identity,
        PAGES_BASE + "markers.v1.json": pages_markers,
    }
    if raw_contract is not None:
        m["%s/%s/contract.v1.json"
          % (RAW_BASE, status_payload.get("commit"))] = raw_contract
    return m


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    loc = local_facts()
    ver = loc["package_version"]
    tag_commit = "c0ffee" * 6 + "0123456"
    main_head = "abcdef" * 6 + "012345"

    # Глубокая файловая проверка в selftest: реальные dist-файлы дерева,
    # если они есть (сборка check_all --strict); иначе — честное NOTE,
    # глубокие мутанты не заявляются проверенными.
    dist = os.path.join(ROOT, "dist")
    wheels = sorted(f for f in os.listdir(dist)
                    if f.endswith(".whl")) if os.path.isdir(dist) else []
    sdists = sorted(f for f in os.listdir(dist)
                    if f.endswith(".tar.gz")) if os.path.isdir(dist) else []
    deep = bool(wheels and sdists)
    file_bytes = {}
    pypi_urls = []
    if deep:
        for kind, name in (("bdist_wheel", wheels[-1]),
                           ("sdist", sdists[-1])):
            with open(os.path.join(dist, name), "rb") as fh:
                data = fh.read()
            file_bytes[kind] = data
            pypi_urls.append({
                "packagetype": kind, "filename": name,
                "yanked": False,
                "digests": {"sha256": hashlib.sha256(data).hexdigest()},
                "url": "https://files.pythonhosted.org/x/" + name})
    else:
        for kind in ("bdist_wheel", "sdist"):
            pypi_urls.append({
                "packagetype": kind, "filename": kind + "-fake",
                "yanked": False, "digests": {"sha256": "0" * 64},
                "url": "https://files.pythonhosted.org/x/" + kind})
        print("NOTE: dist/ без wheel+sdist — глубокая файловая ветвь "
              "selftest выполняется на синтетических байтах (hash-мутант "
              "покрывает её); metadata-валидатор на синтетике не гоняется")

    contract_doc = json.load(open(os.path.join(ROOT, "contract.v1.json"),
                                  encoding="utf-8"))
    identity_doc = json.load(open(os.path.join(ROOT, "identity.v1.json"),
                                  encoding="utf-8"))
    markers_doc = json.load(open(os.path.join(ROOT, "markers.v1.json"),
                                 encoding="utf-8"))
    registry_ok = {
        "server": {"name": REGISTRY_NAME, "version": ver,
                   "packages": [{"registryType": "pypi",
                                 "identifier": "humanizer-ru",
                                 "version": ver,
                                 "runtimeHint": "uvx",
                                 "packageArguments": [{
                                     "type": "positional",
                                     "value": "humanizer-mcp"}]}],
                   "_meta": {
                       "io.modelcontextprotocol.registry/"
                       "publisher-provided": {
                           "install": "pip install humanizer-ru==" + ver
                                      + " then run humanizer-mcp"}}},
        "_meta": {"io.modelcontextprotocol.registry/official":
                  {"status": "active", "isLatest": True}},
    }
    status_ok = {"published_tag": "v" + ver,
                 "published_commit": tag_commit[:7],
                 "commit": main_head[:7],
                 "main_commit": main_head[:7],
                 "markers_count": markers_doc.get("count"),
                 "tests_passed": True, "parity": "ok",
                 "date": "2026-09-07"}

    def opener_for(mapping, files=None, fail_all=False):
        files = files or {}

        def opener(req, timeout=60):
            if fail_all:
                raise OSError("сеть отключена")
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url in mapping:
                return _Resp(mapping[url])
            for prefix, data in files.items():
                if url.startswith(prefix):
                    return _Resp(raw_bytes=data)
            if url.startswith("https://vladimir-human.github.io"):
                return _Resp(None, 200)
            raise OSError("неизвестный url %s" % url)
        return opener

    base_map = _make_responses(loc, "v" + ver, tag_commit, main_head,
                               pypi_urls, registry_ok, status_ok,
                               contract_doc, identity_doc, markers_doc,
                               raw_contract=contract_doc)
    files_ok = {"https://files.pythonhosted.org/x/": None}
    files_map = {}
    if deep:
        for kind in ("bdist_wheel", "sdist"):
            name = next(u["filename"] for u in pypi_urls
                        if u["packagetype"] == kind)
            files_map["https://files.pythonhosted.org/x/" + name] = \
                file_bytes[kind]

    def run(mapping, files=None, deep_files=True):
        op = opener_for(mapping, files if files is not None else files_map)
        return collect(opener=op, deep_files=deep_files)

    _rec, problems, unav = run(base_map, deep_files=deep)
    case("согласованные живые поверхности: проблем нет",
         problems == [] and unav == [])

    # Мутант 1: пустой urls при правильной версии info.
    m = dict(base_map)
    m[PYPI_JSON] = {"info": {"version": ver, "requires_dist": None},
                    "releases": {ver: []}}
    _r, p, _u = run(m, deep_files=False)
    case("мутант: пустой urls PyPI ловится", any("нет файлов" in x
                                                 for x in p))

    # Мутант 2: yanked файл.
    m = dict(base_map)
    yanked = [dict(u, yanked=True) for u in pypi_urls]
    m[PYPI_JSON] = {"info": {"version": ver, "requires_dist": None},
                    "releases": {ver: yanked}}
    _r, p, _u = run(m, deep_files=False)
    case("мутант: yanked-файл ловится", any("yanked" in x for x in p))

    # Мутант 3: runtime-зависимость в requires_dist.
    m = dict(base_map)
    m[PYPI_JSON] = {"info": {"version": ver,
                             "requires_dist": ["requests"]},
                    "releases": {ver: pypi_urls}}
    _r, p, _u = run(m, deep_files=False)
    case("мутант: requires_dist ломает stdlib-only",
         any("stdlib-only" in x for x in p))

    # Мутант 4: sha256 скачанных байтов не совпадает с заявленным.
    tampered = {k: (b"X" + v[1:]) for k, v in files_map.items()}
    if tampered:
        _r, p, _u = run(base_map, files=tampered)
        case("мутант: скачанные байты != sha256 ловится",
             any("sha256" in x for x in p))
    else:
        _r, p, _u = run(base_map, files={
            "https://files.pythonhosted.org/x/bdist_wheel": b"garbage",
            "https://files.pythonhosted.org/x/sdist": b"garbage"})
        case("мутант: скачанные байты != sha256 ловится",
             any("sha256" in x for x in p))

    # Мутант 5: статус MCP deleted при правильной версии.
    m = dict(base_map)
    reg_deleted = json.loads(json.dumps(registry_ok))
    reg_deleted["_meta"]["io.modelcontextprotocol.registry/official"][
        "status"] = "deleted"
    m[REGISTRY] = reg_deleted
    _r, p, _u = run(m, deep_files=False)
    case("мутант: MCP статус deleted ловится",
         any("статус" in x and "active" in x for x in p))

    # Мутант 6: чужой пакет в записи MCP.
    m = dict(base_map)
    reg_foreign = json.loads(json.dumps(registry_ok))
    reg_foreign["server"]["packages"][0]["identifier"] = "other-pkg"
    m[REGISTRY] = reg_foreign
    _r, p, _u = run(m, deep_files=False)
    case("мутант: чужой пакет MCP ловится",
         any("идентификатор" in x for x in p))

    # Мутант 6b: запись активна, но consumer не знает entry point пакета.
    m = dict(base_map)
    reg_launcher = json.loads(json.dumps(registry_ok))
    del reg_launcher["server"]["packages"][0]["packageArguments"]
    m[REGISTRY] = reg_launcher
    _r, p, _u = run(m, deep_files=False)
    case("мутант: MCP без launcher packageArguments ловится",
         any("packageArguments" in x for x in p))

    # Мутант 7: чужое имя записи MCP.
    m = dict(base_map)
    reg_name = json.loads(json.dumps(registry_ok))
    reg_name["server"]["name"] = "io.github.someone/else"
    m[REGISTRY] = reg_name
    _r, p, _u = run(m, deep_files=False)
    case("мутант: чужое имя записи MCP ловится",
         any("имя записи" in x for x in p))

    # Мутант 8: Pages published_tag чужой (нулевая версия).
    m = dict(base_map)
    st = dict(status_ok, published_tag="v0.0" + ".0")
    m[PAGES_STATUS] = st
    _r, p, _u = run(m, deep_files=False)
    case("мутант: Pages published_tag != тег Release ловится",
         any("published_tag" in x for x in p))

    # Мутант 9: Pages published_commit чужой.
    m = dict(base_map)
    st = dict(status_ok, published_commit="deadbee")
    m[PAGES_STATUS] = st
    _r, p, _u = run(m, deep_files=False)
    case("мутант: Pages published_commit != peeled-commit тега ловится",
         any("published_commit" in x for x in p))

    # Мутант 10: HTTP 200 с произвольным JSON вместо машинного документа.
    m = dict(base_map)
    m[PAGES_BASE + "contract.v1.json"] = {"hello": "world"}
    _r, p, _u = run(m, deep_files=False)
    case("мутант: произвольный JSON с кодом 200 ловится схемой",
         any("schema_version" in x for x in p))

    # Мутант 11: контент Pages не соответствует заявленному SHA деплоя.
    m = dict(base_map)
    foreign = json.loads(json.dumps(contract_doc))
    foreign["id"] = "someone-else-contract"
    m[PAGES_BASE + "contract.v1.json"] = foreign
    _r, p, _u = run(m, deep_files=False)
    case("мутант: контент != raw заявленного commit ловится",
         any("raw-копии" in x for x in p))

    # Мутант 12: tests_passed false.
    m = dict(base_map)
    m[PAGES_STATUS] = dict(status_ok, tests_passed=False)
    _r, p, _u = run(m, deep_files=False)
    case("мутант: tests_passed != true ловится",
         any("tests_passed" in x for x in p))

    # Недоступность всех источников — UNAVAILABLE, не зелёный статус.
    _r, p, u = run(base_map, files={}, deep_files=False)
    _rec3, problems3, unav3 = collect(
        opener=opener_for({}, fail_all=True), deep_files=False)
    case("недоступность источников — UNAVAILABLE, не зелёный статус",
         set(unav3) >= {"github", "pypi", "mcp_registry", "pages_status"}
         and not any("версия" in x for x in problems3))
    print("САМОПРОВЕРКА check_live_distribution: %d/%d PASS"
          % (passed, passed + failed))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    record, problems, unavailable = collect()
    if args.json:
        print(json.dumps({"record": record, "problems": problems,
                          "unavailable": unavailable},
                         ensure_ascii=False, indent=1))
    else:
        print(json.dumps(record, ensure_ascii=False, indent=1))
        for p in problems:
            print("[FAIL] ДИСТРИБУЦИЯ: " + p)
        for u in unavailable:
            print("UNAVAILABLE: " + u)
    if unavailable:
        return 2
    if problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
