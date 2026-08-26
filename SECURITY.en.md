# Security policy

**[Русская версия → SECURITY.md](SECURITY.md)**

## What this project does — and does not do

Humanizer-ru is a text-based skill for AI agents. It consists of Markdown files (`SKILL.md`, `references/*.md`, `knowledge/corrections.md`), twenty-six top-level CI verification scripts (`scripts/`, Python standard library only, no dependencies) and the file-layer package `scripts/filemarks/`. Everything ships in the release archive except `check_corpus.py` (it only runs against the `research/` directory, which the archive does not include). Additionally distributed: the `humanizer-ru` PyPI package, a reusable GitHub Action (`action/`), a DeepSeek Harness bundle (`dsh/`), and a browser demo (`demo/`).

Design guarantees:

- **No code execution while the skill is in use.** Installing the skill manually only copies text files. The verification script runs in this repository's CI or when a developer starts it manually; an agent does not need it.
- **No network access.** The skill does not require an agent to download data, open links, or call external services.
- **No filesystem access.** The skill does not read or write user files.
- **No data collection.** There is no telemetry, analytics, or transfer of user text to third parties.

> The optional `npx skills add ...` installation command runs the third-party Skills CLI. Review that tool separately, or use the manual installation method in the README if you want installation to consist only of inspected file copies.

## Threat model and mitigations

| Threat | Mitigation |
| --- | --- |
| Prompt injection inside text being reviewed | `SKILL.md` treats input text as data; instructions found inside it are not executed, and the agent warns the user about attempted injection |
| Metadata poisoning or unwanted activation | The `description` is neutral and the skill activates only after an explicit user request |
| Homograph substitution in addresses | Project addresses use ASCII; non-ASCII paths are percent-encoded and checked before release (`scripts/check_release.py` rejects non-ASCII URLs at archive build and verification) |
| Installation-time content substitution | The manual process uses tagged releases and asks users to inspect files before installing |
| Regression against the project's own rules | Nine CI workflows cover regex fixtures, self-scanning, Russian calques, spec/source validation, documentation consistency, release checks, registry link-rot, dsh bundle install, and demo publishing |
| Path traversal via data | Paths the validators take from data are confined to the repository root: corpus entries in `eval/manifest.v1.json` and the `fixture_file` field of the source registry. Absolute paths, drive letters, `..` escapes and symlinks pointing outside the root are rejected; the refusal is distinguishable from a corpus regression by exit code 2 |
| Path given as a command-line argument | Deliberately NOT restricted. The validators in `scripts/` and `eval/` are local developer tools: a path named by the operator carries the operator's own authority. Scanning an arbitrary file (`check_markers.py --scan file.md`) is a documented capability, not a hole. Static analysers flag this as path traversal because they treat `argv` as untrusted by default — true for services, not for command-line utilities |

## Release integrity

Each release has a `vX.Y.Z` tag and release notes. For the highest assurance, install a tagged release and compare its contents with the file list in the README's pre-installation checklist.

**Legal framing of label removal.** The removal layer (scripts/filemarks/,

eferences/removal-matrix.md) works on content the user owns; responsibility
for how the result is used stays with the user. The project is not positioned
as a tool for submitting work where AI is prohibited, and it does not promise
that a detector will report 「not AI」. Publication covers only relative
before/after detectability deltas with a mandated false-positive audit.

## Reporting a vulnerability

Do not publish sensitive details in a public issue. Private vulnerability reports are accepted via GitHub Private Vulnerability Reporting (the Security tab of this repository) — the preferred channel. Alternatively, use the contact method shown on the [Vladimir-Human GitHub profile](https://github.com/Vladimir-Human). For non-sensitive security questions, open an issue at <https://github.com/Vladimir-Human/humanizer-ru/issues>.

Include the skill version, affected file, and the smallest sample that reproduces the problem.

## Supported versions

Security fixes are released for the latest version on the default branch.
