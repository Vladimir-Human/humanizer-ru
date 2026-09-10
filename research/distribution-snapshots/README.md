# Distribution snapshots

`scripts/snapshot_distribution.py` creates a dated, read-only view of the
public distribution surfaces: GitHub, PyPI, MCP Registry, Pages, Glama and
skills.sh. It prints no user text and never uses credentials.

Run from the repository root:

```text
python scripts/snapshot_distribution.py --json > distribution-snapshot.json
```

The top-level status is `ok`, `drift`, or `unavailable`. `drift` means a
machine-readable version/status disagrees with the local package. `unavailable`
means a public source could not be fetched or parsed; it is not a passing
result. Catalog HTML hashes are diagnostic only and do not gate releases.

The command is deliberately outside the release workflow. Reproduce a local
check with `python scripts/snapshot_distribution.py --selftest`.

For a machine-readable Agent Skills installation receipt, run
`python scripts/install_receipt.py --json`. It records the source commit and
deterministic hashes for the root skill, the DSH skill, and the MCP contract.
This is a project receipt, not an official Agent Skills lockfile or a security
certificate. Use `--strict` when the receipt must describe a clean git tree.
The script requires Git for strict acceptance; it reads local files and makes
no network requests. Listed verification commands are suggestions, not test
results recorded by the receipt.

`source.clean` requires a clean Git status and exact raw-byte agreement with
the recorded commit for all target files and the version source. Extra files
inside a target, including ignored files, invalidate strict acceptance.
CRLF and LF produce different hashes even when Git normalizes them. Symlinks
and Windows junctions in target paths are rejected.

For each target, paths are relative to the repository root and sorted
lexicographically. SHA-256 receives each UTF-8 path and its raw file content,
each preceded by its byte length as an unsigned 8-byte big-endian integer.
Root and DSH targets use different paths, so their digests are not a parity
comparison; use the bundle-sync command for that.

`--out` accepts a new file outside the repository and refuses to overwrite
an existing file. Strict rejection produces no output file. Exit codes are
0 for success, 1 for strict rejection, and 2 for input or output errors.
Generate receipts while the checkout is idle; this command does not lock Git
or the filesystem against concurrent writers.
