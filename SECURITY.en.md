# Security policy

**[Русская версия → SECURITY.md](SECURITY.md)**

## What this project does — and does not do

Humanizer-ru is a text-based skill for AI agents. It consists of Markdown files (`SKILL.md`, `references/*.md`, `knowledge/corrections.md`), top-level CI verification scripts (`scripts/`, Python standard library only, no dependencies; count with `ls scripts/*.py | wc -l`, or `(Get-ChildItem scripts\*.py).Count` on Windows) and the file-layer package `scripts/filemarks/`. Everything ships in the release archive except `check_corpus.py` (it only runs against the `research/` directory, which the archive does not include). Additionally distributed: the `humanizer-ru` PyPI package, a reusable GitHub Action (`action/`), a DeepSeek Harness bundle (`dsh/`), and a browser demo (`demo/`).

Design guarantees:

- **No code execution while the skill is in use.** Installing the skill manually only copies text files. The verification script runs in this repository's CI or when a developer starts it manually; an agent does not need it.
- **No network access.** The skill does not require an agent to download data, open links, or call external services.
- **No unprompted filesystem access.** The skill never opens files on its own;
  a file is read only when the user explicitly asks to process that file.
- **No data collection.** There is no telemetry, analytics, or transfer of user text to third parties.

**Legal framing of label removal.** The removal layer (`scripts/filemarks/`,
`references/removal-matrix.md`) works on content the user owns; responsibility
for how the result is used rests with the user.
Usage-scenario restrictions (the prohibited_uses block) were removed by
project policy on 2026-09-05: the tool does not evaluate the purpose of
use. Detector bypass is not promised: only relative before/after
detectability deltas are published, without absolute percentages. Plagiarism checks are out of scope:
rewriting does not remove matches against a database of borrowings.

> The optional `npx skills add ...` installation command runs the third-party Skills CLI. Review that tool separately, or use the manual installation method in the README if you want installation to consist only of inspected file copies.

## Threat model and mitigations

| Threat | Mitigation |
| --- | --- |
| Prompt injection inside text being reviewed | `SKILL.md` treats input text as data; instructions found inside it are not executed, and the agent warns the user about attempted injection |
| Metadata poisoning or unwanted activation | The `description` is neutral and free of directives; the skill activates only after an explicit user request |
| Homograph substitution in addresses | Project addresses use ASCII; non-ASCII paths are percent-encoded and checked before release (`scripts/check_release.py` rejects non-ASCII URLs at archive build and verification) |
| Installation-time content substitution | The manual process uses tagged releases and asks users to inspect files before installing |
| Regression against the project's own rules | Ten CI workflows cover regex fixtures, self-scanning, Russian calques, spec/source validation, documentation consistency, release checks, registry link-rot, dsh bundle install, and demo publishing |
| Path traversal via data | Paths the validators take from data are confined to the repository root: corpus entries in `eval/manifest.v1.json` and the `fixture_file` field of the source registry. Absolute paths, drive letters, `..` escapes and symlinks pointing outside the root are rejected; the refusal is distinguishable from a corpus regression by exit code 2 |
| Path given as a command-line argument | Deliberately NOT restricted. The validators in `scripts/` and `eval/` are local developer tools: a path named by the operator carries the operator's own authority. Scanning an arbitrary file (`check_markers.py --scan file.md`) is a documented capability, not a hole. Static analysers flag this as path traversal because they treat `argv` as untrusted by default — true for services, not for command-line utilities |

## Release integrity

Each release has a `vX.Y.Z` tag and release notes. For the highest assurance, install a tagged release and compare its contents with the file list in the README's pre-installation checklist.

## Reporting a vulnerability

Do not publish sensitive details in a public issue. Private vulnerability reports are accepted via GitHub Private Vulnerability Reporting (the Security tab of this repository) — the preferred channel. Alternatively, use the contact method shown on the [Vladimir-Human GitHub profile](https://github.com/Vladimir-Human). For non-sensitive security questions, open an issue at <https://github.com/Vladimir-Human/humanizer-ru/issues>.

Include the skill version, affected file, and the smallest sample that reproduces the problem.

## Supported versions

Security fixes are released for the latest version on the default branch.

## Response times

- Vulnerability reports: acknowledgement within 7 days, then a status update
  every 7 days until resolved; fixes ship on the main branch.
- General questions and issues: no promised deadline, best effort; never
  post private data in public issues.

## Directories and their audits (skills.sh)

Additional measures for developer tooling — the repository also applies
explicit controls outside the user-facing skill:

- `eval/ainl_calibration.py` accepts only HTTPS from two allowlisted hosts and
  caps responses at 250 MiB; the corpus is temporary and never shipped.
- External-feedback workflow excerpts redact email addresses and URLs while
  retaining signals and the link to the original public message.
- CI checkouts do not persist credentials in `.git/config`; GitHub API access is
  granted only to the job that calls it.

Directory audits (Gen Agent Trust Hub, Socket, Snyk) scan the ENTIRE
repository, including dev/CI scripts that are not part of the skill bundle
(17 files: SKILL.md, references/, knowledge/) and are not shipped to the
user. Interpretation of the 2026-09-05 snapshot findings:

- INDIRECT_PROMPT_INJECTION (Trust Hub): the essence of the product is
  processing untrusted text; SKILL.md prescribes isolating the input with
  tags and ignoring instructions inside it (the audit itself notes this as
  a protection). Mitigation: allowed-tools is limited to Read/Grep/Glob.
- DYNAMIC_EXECUTION (Trust Hub): eval/run_eval.py --candidate executes a
  local candidate script — a developer bench harness, not part of the
  bundle or the package, run only by a human in CI or locally.
- EXTERNAL_DOWNLOADS (Trust Hub): eval/ainl_calibration.py downloads
  datasets from raw.githubusercontent.com and huggingface.co — legitimate
  acquisition of calibration data, dev-only.
- COMMAND_EXECUTION (Trust Hub): subprocess in scripts/ and eval/ — local
  dev/CI tools (git, marker scanners); not in the bundle.
- Socket, scripts/check_compatibility.py: installs the previous package
  version into a temporary venv and runs probes — a CI regression harness,
  dev-only; the audit snippet is truncated at PROBE, the full probe text is
  visible in the file.
- Socket, scripts/filemarks/rewrite_text.py: shell=True was replaced with
  shlex.split without a shell on 2026-09-06 (see the hardening commit); the
  HUMANIZER_REWRITE_CMD template is set by the operator, metacharacters are
  not interpreted.
- Socket, dsh/cordis.patch.yml: JS in YAML — a vendored patch of the dsh
  bundle, loaded only by the dsh host on the operator's explicit choice;
  not part of the skill bundle.
- "2 malicious URL" (Trust Hub): detection signatures (Perplexity S3
  addresses, sandbox links) are samples of INPUT artifacts to search for,
  not addresses from which the project downloads anything.

Snyk: Pass. After the hardening commits, the audits rescan the repository
on their own schedule; finding snapshots are recorded in the sprint log
with dates.

