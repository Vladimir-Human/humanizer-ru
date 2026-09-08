# Plugin scanner notes

The HOL Plugin Scanner currently discovers `dsh/package.json` as a native
DeepSeek Harness executable package and reports `DSH_RUNTIME_APPLY_MISSING`.
This repository intentionally ships `dsh/` as a patch-only skill bundle:
`dsh/cordis.patch.yml` adds the packaged skill directory through the host's
filesystem plugin. It has no JavaScript runtime entry point and does not claim
to be an executable Cordis plugin.

The supported installation contract is exercised by
`.github/workflows/dsh-install.yml`: it installs the bundle into a clean DSH
profile, verifies the patch and skill files, then removes the bundle and checks
that the profile returns to its prior state. The Python package and MCP server
are separate entry points documented in `README.md`, `docs/USAGE.md` and
`server.json`.

The repository workflow runs the scanner in `verify` mode and uploads its full
text report. This note records the boundary so a catalog reviewer can
distinguish a patch-only bundle finding from a missing runtime in the Python or
MCP product.
