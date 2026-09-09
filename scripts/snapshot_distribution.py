#!/usr/bin/env python3
"""Create a read-only snapshot of public distribution surfaces.

The command is diagnostic: network failures are reported as ``unavailable``
and never treated as a healthy release.  It does not read user text or use
credentials and is intentionally separate from publication workflows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "humanizer-ru-distribution-snapshot"}
SOURCES = {
    "github": "https://api.github.com/repos/Vladimir-Human/humanizer-ru/commits/main",
    "pypi": "https://pypi.org/pypi/humanizer-ru/json",
    "mcp_registry": "https://registry.modelcontextprotocol.io/v0.1/servers/io.github.Vladimir-Human%2Fhumanizer-ru/versions/latest",
    "pages": "https://vladimir-human.github.io/humanizer-ru/status.json",
    "glama": "https://glama.ai/mcp/servers/Vladimir-Human/humanizer-ru",
    "skills_sh": "https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru",
}


def _local_version() -> str:
    text = (ROOT / "src" / "humanizer_ru" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not m:
        raise ValueError("local package version is missing")
    return m.group(1)


def _fetch(url: str, opener=None):
    fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers=UA)
    with fn(req, timeout=20) as response:
        status = getattr(response, "status", 200)
        data = response.read()
    if status != 200:
        raise RuntimeError("HTTP %s" % status)
    return data


def _surface(name: str, url: str, version: str, opener=None) -> dict:
    try:
        raw = _fetch(url, opener=opener)
        item = {"status": "ok", "http": 200,
                "sha256": hashlib.sha256(raw).hexdigest()}
        if name == "github":
            item["main_sha"] = json.loads(raw.decode("utf-8")).get("sha")
        elif name == "pypi":
            item["version"] = json.loads(raw.decode("utf-8")).get("info", {}).get("version")
            if item["version"] != version:
                item["status"] = "drift"
        elif name == "mcp_registry":
            doc = json.loads(raw.decode("utf-8")); server = doc.get("server") or {}
            item["version"] = server.get("version")
            item["official_status"] = ((doc.get("_meta") or {}).get(
                "io.modelcontextprotocol.registry/official") or {}).get("status")
            package = next((p for p in server.get("packages") or []
                            if p.get("registryType") == "pypi"), {})
            item["package_identifier"] = package.get("identifier")
            item["package_version"] = package.get("version")
            item["transport"] = (package.get("transport") or {}).get("type")
            item["runtime_hint"] = package.get("runtimeHint")
            if (item["version"] != version or item["package_version"] != version
                    or item["package_identifier"] != "humanizer-ru"
                    or item["transport"] != "stdio"
                    or item["runtime_hint"] != "uvx"
                    or item["official_status"] != "active"):
                item["status"] = "drift"
        elif name == "pages":
            doc = json.loads(raw.decode("utf-8"))
            for key in ("published_tag", "published_commit", "parity", "tests_passed"):
                if key in doc:
                    item[key] = doc[key]
        return item
    except Exception as exc:  # network and malformed public responses are unavailable
        return {"status": "unavailable", "reason": "%s: %s" % (type(exc).__name__, exc)}


def snapshot(opener=None) -> dict:
    version = _local_version()
    surfaces = {name: _surface(name, url, version, opener=opener)
                for name, url in SOURCES.items()}
    statuses = {value["status"] for value in surfaces.values()}
    overall = "drift" if "drift" in statuses else ("unavailable" if "unavailable" in statuses else "ok")
    return {"schema": 1, "local_version": version, "status": overall,
            "surfaces": surfaces}


def selftest() -> int:
    class Response:
        status = 200
        def __init__(self, data): self.data = data
        def read(self): return self.data
        def __enter__(self): return self
        def __exit__(self, *args): return False

    def opener(req, timeout=20):
        url = req.full_url
        if "pypi.org" in url:
            return Response(json.dumps({"info": {"version": _local_version()}}).encode())
        if "registry.modelcontextprotocol" in url:
            return Response(json.dumps({"server": {"version": _local_version(), "packages": [{"registryType": "pypi", "identifier": "humanizer-ru", "version": _local_version(), "runtimeHint": "uvx", "transport": {"type": "stdio"}}]}, "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}}).encode())
        if "api.github.com" in url:
            return Response(b'{"sha":"abc"}')
        if "status.json" in url:
            return Response(json.dumps({"published_tag": "v" + _local_version(),
                                       "parity": "ok", "tests_passed": True}).encode())
        return Response(b"catalog")

    good = snapshot(opener=opener)
    def drift_opener(req, timeout=20):
        if "pypi.org" in req.full_url:
            drift_version = "0" + ".0.0"
            return Response(json.dumps({"info": {"version": drift_version}}).encode())
        return opener(req, timeout)

    def unavailable_opener(req, timeout=20):
        raise OSError("synthetic network failure")

    drift = _surface("pypi", SOURCES["pypi"], _local_version(), drift_opener)
    unavailable = _surface("pypi", SOURCES["pypi"], _local_version(), unavailable_opener)
    cases = [good["status"] == "ok",
             all(v["status"] == "ok" for v in good["surfaces"].values()),
             drift["status"] == "drift",
             unavailable["status"] == "unavailable"]
    for ok, label in zip(cases, ("synthetic snapshot is ok", "all surfaces represented", "drift is detected", "unavailable is explicit")):
        print(("PASS: " if ok else "FAIL: ") + label)
    print("САМОПРОВЕРКА snapshot_distribution: %d/%d PASS" % (sum(cases), len(cases)))
    return 0 if all(cases) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    result = snapshot()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("distribution snapshot: %s (local %s)" % (result["status"], result["local_version"]))
        for name, value in result["surfaces"].items():
            print("- %s: %s" % (name, value["status"]))
    return {"ok": 0, "drift": 1, "unavailable": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
