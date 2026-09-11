# Plugin scanner notes

Rule-level notes for the HOL AI Plugin Scanner
(`hashgraph-online/ai-plugin-scanner-action`, PyPI package
`plugin-scanner`). Each section records one scanner rule: what triggers it
in this repository, the disposition (fixed or documented), and the evidence
a reviewer can re-run.

Reproduction (catalog `hashgraph-online/awesome-ai-plugins` pins the
workflow `sweep-open-prs.yml` at action SHA
`caba2e96aa8ad2feb6cf6fca52442b52e22e779f`, which installs
`plugin-scanner==3.0.123`; the repository's own advisory workflow
`.github/workflows/hol-plugin-scanner.yml` pins SHA
`bb4f519048c0fd1cd9d7b42056072d6070b8ad7d` = `plugin-scanner==3.0.143`):

```sh
pip install plugin-scanner==3.0.123
plugin-scanner scan . --profile default --min-score 80 \
  --fail-on-severity high --cisco-skill-scan auto --cisco-policy balanced
```

Both pinned versions report the same result on the current tree:
score 98/100, findings `critical:0, high:0, medium:1, low:0, info:0`,
exit code 0. The catalog sweep of 2026-09-11 (job
<https://github.com/hashgraph-online/awesome-ai-plugins/actions/runs/34609031384/job/103294663075>)
reported 79/100 with `high:6, medium:6, low:3, info:6` on commit 60bcf8d;
every finding from that report is addressed below.

## DSH_RUNTIME_APPLY_MISSING — documented boundary (not fixed)

- Rule: `DSH_RUNTIME_APPLY_MISSING` (medium, category deepseek-harness).
  The scanner discovers `dsh/package.json` as a native DeepSeek Harness
  package and requires `main`/`exports` to reference an in-package module
  exporting Cordis `apply(ctx)`.
- Trigger: this repository intentionally ships `dsh/` as a patch-only skill
  bundle: `dsh/cordis.patch.yml` adds the packaged skill directory through
  the host's filesystem plugin. It has no JavaScript runtime entry point
  and does not claim to be an executable Cordis plugin. Adding a JS module
  with a fabricated `apply(ctx)` just to satisfy the rule would misstate
  what the bundle is.
- Status: still reported by `plugin-scanner` 3.0.123 and 3.0.143. Upstream
  report `hashgraph-online/hol-guard#2862` was closed as completed on
  2026-09-09; the rule nevertheless remains active in both pinned
  versions, so the finding is documented rather than fixed.
- Evidence: the supported installation contract is exercised by
  `.github/workflows/dsh-install.yml`: it installs the bundle into a clean
  DSH profile, verifies the patch and skill files, then removes the bundle
  and checks that the profile returns to its prior state. The Python
  package and MCP server are separate entry points documented in
  `README.md`, `docs/USAGE.md` and `server.json`.

## DANGEROUS_DYNAMIC_EXECUTION — fixed (2026-09-11)

- Rule: `DANGEROUS_DYNAMIC_EXECUTION` (high, category code-quality). The
  scanner greps every `.py/.js/.mjs/.cjs/.ts/.jsx/.tsx` file for the
  literal regex patterns `\beval\s*\(` and `new\s+Function\s*\(`.
- Trigger (sweep of 2026-09-11): the Node harnesses inside
  `scripts/check_demo_parity.py` and `scripts/check_demo_perf.py` loaded
  `demo/markers.js` with JS `eval(fs.readFileSync(...))`. The input was
  always the repository's own generated file, never untrusted data, but
  dynamic execution was avoidable.
- Fix: both harnesses now load `demo/markers.js` via `require(path)` after
  `global.window = global;` — `markers.js` publishes itself through a
  `typeof window !== "undefined"` guard, so module execution is
  observationally identical. Verified by
  `python scripts/check_demo_parity.py --selftest` (10/10 PASS, including
  mutation negatives) and `python scripts/check_demo_perf.py --selftest`
  (quadratic mutant still caught, ratio 13.7 > 8.0).

## DEPENDENCY_LOCKFILE_MISSING — fixed (2026-09-11)

- Rule: `DEPENDENCY_LOCKFILE_MISSING` (medium, category
  operational-security). A dependency manifest (`package.json`,
  `pyproject.toml`, `requirements.txt`) must sit next to a lockfile
  (`uv.lock`/`poetry.lock`/`Pipfile.lock`/`requirements.lock` for Python,
  `package-lock.json`/`pnpm-lock.yaml`/`yarn.lock`/`bun.lock*` for Node)
  or a fully pinned requirements file.
- Trigger: root `pyproject.toml` (flagged once per ecosystem section) and
  `dsh/package.json` had no lockfiles.
- Fix: `uv.lock` at the repository root (generated with `uv lock`; the
  product is stdlib-only, so the lock records the zero-dependency
  resolution) and `dsh/pnpm-lock.yaml` (generated with
  `pnpm install --lockfile-only` using pnpm 10.28.0, the version pinned in
  `dsh-install.yml`; the bundle has no dependencies). Neither lockfile
  embeds the product version, so version bumps do not stale them.

## DEPENDABOT_MISSING (dsh scope) — fixed (2026-09-11)

- Rule: `DEPENDABOT_MISSING` (low, category operational-security). The DSH
  ecosystem section is scoped to `dsh/` as the package root and looks for
  `<package>/.github/dependabot.yml`.
- Trigger: GitHub reads Dependabot configuration only from the repository
  root, and the root `.github/dependabot.yml` covered only the
  `github-actions` ecosystem; the npm surface `dsh/package.json` had no
  coverage, and no configuration file existed inside `dsh/`.
- Fix: the root `.github/dependabot.yml` gained an `npm` entry for
  `directory: "/dsh"` (weekly, same commit-message prefix and labels as
  the existing entry) — this is the configuration GitHub actually runs.
  `dsh/.github/dependabot.yml` declares the same policy for tools that
  treat the package directory as the root; its header comment states
  plainly that the authoritative file is the repository-root one, so the
  copy cannot be mistaken for an active GitHub configuration.

## SECURITY_MD_MISSING / LICENSE_MISSING (dsh scope) — fixed (2026-09-11)

- Rules: `SECURITY_MD_MISSING`, `LICENSE_MISSING` (low, category security).
  The DSH-scoped section looks for `SECURITY.md` and `LICENSE` inside
  `dsh/`.
- Trigger: both files existed only at the repository root. The bundle
  declares `"license": "MIT"` in `dsh/package.json`, and a package
  installed from that directory previously carried no license text of its
  own.
- Fix: `dsh/LICENSE` is a byte-identical copy of the root MIT license
  (compared with `fc /b`). `dsh/SECURITY.md` is a short bundle-scoped
  note: what the bundle contains, its no-code/no-network boundary, and a
  pointer to the root security policy (threat model, reporting channel,
  response times) instead of a second copy that could drift.

## SKILLS_DIR_MISSING — fixed (2026-09-11)

- Rule: `SKILLS_DIR_MISSING` (medium, category best-practices). The
  `skills` field of `.codex-plugin/plugin.json` must point at a directory;
  skill documents are then discovered as `<skills>/*/SKILL.md`.
- Trigger: the manifest declared `"skills": "./SKILL.md"` — a file, not a
  directory. The Cisco skill-scan integration was skipped for the same
  reason ("Skills directory ./SKILL.md is missing").
- Fix: the manifest now points at `./dsh/skills`, the packaged skills
  directory that already ships the skill in the standard layout
  (`humanizer-ru/SKILL.md` plus `references/` and `knowledge/`). Its
  `SKILL.md` is byte-synced with the root copy under
  `scripts/check_bundle_sync.py`, so both entry points serve identical
  content and the frontmatter rule (`name`/`description`) passes on it.

## PLUGIN_JSON_RECOMMENDED_AUTHOR — fixed (2026-09-11)

- Rule: `PLUGIN_JSON_RECOMMENDED_AUTHOR` (info, category
  manifest-validation). The recommended `author` field must be an object
  with a non-empty `name`.
- Trigger: `.codex-plugin/plugin.json` carried `"author":
  "Vladimir-Human"` (a plain string).
- Fix: `author` is now `{"name": "Vladimir-Human", "url":
  "https://github.com/Vladimir-Human"}` — same fact, documented shape.

## PLUGIN_JSON_INTERFACE_ASSET_* — fixed (2026-09-11)

- Rules: `PLUGIN_JSON_INTERFACE_ASSET_TERMSOFSERVICEURL`,
  `..._COMPOSERICON`, `..._LOGO`, `..._SCREENSHOTS` (info, category
  manifest-validation). When an `interface` block is declared, the
  scanner requires HTTPS URLs for `websiteURL`, `privacyPolicyURL`,
  `termsOfServiceURL`, and existing `./`-relative in-repo assets for
  `composerIcon`, `logo`, `screenshots`.
- Trigger: the interface declared no terms-of-service URL and no visual
  assets.
- Fix: `termsOfServiceURL` points at the MIT license text
  (<https://github.com/Vladimir-Human/humanizer-ru/blob/main/LICENSE>) —
  the project has no separate terms of service, and the license is the
  actual set of terms under which the plugin is provided. Visual fields
  reference existing project assets: `composerIcon` —
  `./demo/favicon.svg` (the project icon), `logo` — `./assets/hero.svg`
  (the README brand visual), `screenshots` —
  `./assets/demo-screenshot.png` (a screenshot of the browser demo).

## CODEXIGNORE_MISSING — fixed (2026-09-11)

- Rule: `CODEXIGNORE_MISSING` (info, category best-practices): no
  `.codexignore` at the repository root.
- Fix: added `.codexignore` listing what Codex agents should not pull into
  context here — research corpora and run outputs, test fixtures with
  deliberate artifact samples, build outputs, local virtual environments,
  and secret-bearing local state. The delivered skill surface (`SKILL.md`,
  `references/`, `knowledge/`, `commands/`, `scripts/`, plugin manifests)
  is intentionally not excluded. The file is registered in the top-level
  composition manifest (`TOP_LEVEL_MANIFEST` in `scripts/check_docs.py`)
  together with `uv.lock`, as that gate requires for new root objects.

## Scanner report handling

The repository workflow `.github/workflows/hol-plugin-scanner.yml` runs the
scanner in `verify` mode with `continue-on-error: true` and uploads its
full text report: HOL's scanner is an external advisory surface while
product CI remains governed by repository gates. This file records the
rule-level state so a catalog reviewer can distinguish documented
boundaries from unaddressed findings.
