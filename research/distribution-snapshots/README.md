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
