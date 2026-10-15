#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Put the instruction files (.md) of every compared skill into eval/.cache/systems/<name>/
#          at a pinned commit, so runs are reproducible without vendoring other projects.
# SCOPE: downloads only Markdown files of the skill folder (scripts are never fetched or run);
#        README/CHANGELOG/AGENTS/CONTRIBUTING are skipped as not part of the instructions.
# DEPENDS: gh CLI (authenticated) for GitHub; git for the local tag; eval/systems.json.
# LINKS: M-EVAL-FETCH; DF-EVAL.
# END_MODULE_CONTRACT
# START_MODULE_MAP
# fetch_github: list the tree at sha, download .md files under path via the contents API.
# fetch_tag: git archive of the listed paths at a tag.
# main: refresh every non-local system, or only the names given as arguments; prints file lists.
# END_MODULE_MAP
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import evallib as lib

REPO = lib.EVAL_DIR.parent
OUT = lib.CACHE_DIR / "systems"
SKIP = ("readme", "changelog", "agents", "contributing", "license")


def _keep(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1].lower()
    return name.endswith(".md") and not name.startswith(SKIP)


def fetch_github(repo: str, sha: str, path: str, dest: Path) -> list:
    tree = json.loads(subprocess.run(
        ["gh", "api", "repos/%s/git/trees/%s?recursive=1" % (repo, sha)],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    prefix = (path.rstrip("/") + "/") if path else ""
    got = []
    for node in tree["tree"]:
        if node["type"] != "blob" or not node["path"].startswith(prefix):
            continue
        rel = node["path"][len(prefix):]
        if not _keep(rel):
            continue
        raw = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw",
             "repos/%s/contents/%s?ref=%s" % (repo, node["path"], sha)],
            capture_output=True, check=True).stdout
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        got.append(rel)
    return got


def fetch_tag(ref: str, paths: list, dest: Path) -> list:
    data = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", ref] + paths,
                          capture_output=True, check=True).stdout
    got = []
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if member.isfile() and _keep(member.name):
                target = dest / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
                got.append(member.name)
    return got


def main(argv=None) -> int:
    only = set(sys.argv[1:] if argv is None else argv)
    for sysdef in lib.read_json(lib.EVAL_DIR / "systems.json"):
        if sysdef["kind"] not in ("github", "tag") or (only and sysdef["name"] not in only):
            continue
        dest = OUT / sysdef["name"]
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        if sysdef["kind"] == "github":
            files = fetch_github(sysdef["repo"], sysdef["sha"], sysdef["path"], dest)
        else:
            files = fetch_tag(sysdef["ref"], sysdef["paths"], dest)
        size = sum((dest / f).stat().st_size for f in files)
        print("%-9s %2d files, %6d bytes: %s" % (sysdef["name"], len(files), size, ", ".join(sorted(files))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
