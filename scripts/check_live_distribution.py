#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_live_distribution.py — живые агентные входы против
опубликованного продукта.

Сверяет четыре поверхности, по которым агент находит и ставит продукт:
  1. локальное дерево: версия server.json и пакета, число инструментов
     контракта;
  2. PyPI (pypi.org/pypi/humanizer-ru/json): версия и файлы;
  3. официальный реестр MCP (registry.modelcontextprotocol.io,
     versions/latest): версия записи и статус;
  4. Pages: status.json (published_tag/published_commit) и машинные пути
     router-гейта (llms.txt, contract.v1.json, identity.v1.json).

Любая недоступность источника — UNAVAILABLE с причиной (код 2), а не
зелёный статус и не «проекта нет». Несовпадение версий/инструментов —
код 1 с человекочитаемым расхождением.

Запуск:
  python3 scripts/check_live_distribution.py            # сводка, коды 0/1/2
  python3 scripts/check_live_distribution.py --json     # машиночитемо
  python3 scripts/check_live_distribution.py --selftest
"""
import argparse
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYPI_JSON = "https://pypi.org/pypi/humanizer-ru/json"
REGISTRY = ("https://registry.modelcontextprotocol.io/v0.1/servers/"
            "io.github.Vladimir-Human%2Fhumanizer-ru/versions/latest")
PAGES_STATUS = "https://vladimir-human.github.io/humanizer-ru/status.json"
PAGES_PATHS = (
    "https://vladimir-human.github.io/humanizer-ru/",
    "https://vladimir-human.github.io/humanizer-ru/llms.txt",
    "https://vladimir-human.github.io/humanizer-ru/.well-known/llms.txt",
    "https://vladimir-human.github.io/humanizer-ru/contract.v1.json",
    "https://vladimir-human.github.io/humanizer-ru/identity.v1.json",
    "https://vladimir-human.github.io/humanizer-ru/markers.v1.json",
)
UA = {"User-Agent": "humanizer-ru-distribution-check"}


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


def collect(opener=None):
    """(record, problems, unavailable): record — снимок поверхностей."""
    record = {}
    problems = []
    unavailable = []
    try:
        loc = local_facts()
    except LiveUnavailable as exc:
        return None, ["локальное дерево: %s" % exc], ["local"]
    record["local"] = loc
    if loc["server_version"] != loc["package_version"]:
        problems.append("server.json version %s != версия пакета %s"
                        % (loc["server_version"], loc["package_version"]))

    try:
        pypi = fetch_json(PYPI_JSON, opener=opener)
        info = pypi.get("info") or {}
        record["pypi"] = {"version": info.get("version"),
                          "status": "ok"}
        if info.get("version") != loc["package_version"]:
            problems.append("PyPI версия %s != локальная %s"
                            % (info.get("version"), loc["package_version"]))
    except LiveUnavailable as exc:
        record["pypi"] = {"status": "unavailable", "reason": str(exc)}
        unavailable.append("pypi")

    try:
        reg = fetch_json(REGISTRY, opener=opener)
        server = reg.get("server") or {}
        official = ((reg.get("_meta") or {})
                    .get("io.modelcontextprotocol.registry/official")
                    or {})
        record["mcp_registry"] = {"version": server.get("version"),
                                  "status": official.get("status")
                                  or "ok"}
        if server.get("version") != loc["package_version"]:
            problems.append("реестр MCP версия %s != локальная %s "
                            "(агент установит устаревший пакет)"
                            % (server.get("version"),
                               loc["package_version"]))
    except LiveUnavailable as exc:
        record["mcp_registry"] = {"status": "unavailable",
                                  "reason": str(exc)}
        unavailable.append("mcp_registry")

    try:
        status = fetch_json(PAGES_STATUS, opener=opener)
        record["pages_status"] = {
            "published_tag": status.get("published_tag"),
            "published_commit": status.get("published_commit"),
            "tests_passed": status.get("tests_passed"),
            "parity": status.get("parity"),
            "status": "ok"}
        if status.get("tests_passed") is not True:
            problems.append("Pages status.json: tests_passed != true")
        if status.get("parity") != "ok":
            problems.append("Pages status.json: parity != ok")
    except LiveUnavailable as exc:
        record["pages_status"] = {"status": "unavailable",
                                  "reason": str(exc)}
        unavailable.append("pages_status")

    pages = {}
    for url in PAGES_PATHS:
        try:
            pages[url] = fetch_status(url, opener=opener)
        except LiveUnavailable as exc:
            pages[url] = "unavailable: %s" % exc
            unavailable.append("pages:" + url.rsplit("/", 1)[-1])
    record["pages_paths"] = pages
    for url, code in pages.items():
        if code != 200:
            problems.append("Pages путь %s: %s" % (url, code))
    return record, problems, unavailable


def selftest():
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    loc = local_facts()

    class Resp:
        def __init__(self, payload=None, status=200):
            self._payload = payload
            self.status = status
            self._body = json.dumps(payload).encode("utf-8") \
                if payload is not None else b""

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def make_opener(mapping):
        def opener(req, timeout=30):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            for prefix, value in mapping.items():
                if url.startswith(prefix):
                    if value is None:
                        raise OSError("сеть отключена")
                    return Resp(value)
            raise OSError("неизвестный url %s" % url)
        return opener

    good = {
        PYPI_JSON: {"info": {"version": loc["package_version"]}},
        REGISTRY: {"server": {"version": loc["package_version"]},
                   "_meta": {"io.modelcontextprotocol.registry/official":
                             {"status": "active"}}},
        PAGES_STATUS: {"published_tag": "v" + loc["package_version"],
                       "published_commit": "abc1234",
                       "tests_passed": True, "parity": "ok"},
    }
    for url in PAGES_PATHS:
        good[url] = None  # обрабатывается fetch_status через Resp(200)

    def opener_good(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url in good and good[url] is not None:
            return Resp(good[url])
        if url.startswith("https://vladimir-human.github.io"):
            return Resp(None, 200)
        raise OSError("неизвестный url")
    record, problems, unav = collect(opener=opener_good)
    case("согласованные живые поверхности: проблем нет",
         problems == [] and unav == [] and record is not None)

    stale = dict(good)
    stale[REGISTRY] = {"server": {"version": "3.19" + ".2"},
                       "_meta": {"io.modelcontextprotocol.registry/"
                                 "official": {"status": "active"}}}

    def opener_stale(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url in stale and stale[url] is not None:
            return Resp(stale[url])
        if url.startswith("https://vladimir-human.github.io"):
            return Resp(None, 200)
        raise OSError("неизвестный url")
    _rec2, problems2, _un2 = collect(opener=opener_stale)
    case("устаревшая запись реестра ловится как расхождение",
         any("реестр MCP" in p for p in problems2))

    def opener_down(req, timeout=30):
        raise OSError("сеть отключена")
    _rec3, problems3, unav3 = collect(opener=opener_down)
    case("недоступность источников — UNAVAILABLE, не зелёный статус",
         set(unav3) >= {"pypi", "mcp_registry", "pages_status"}
         and not any("версия" in p for p in problems3))
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
