# Security policy

**[Русская версия → SECURITY.md](SECURITY.md)**

## What this project does — and does not do

Humanizer-ru is a text-based skill for AI agents. It consists of Markdown files (`SKILL.md`, `references/*.md`) and eleven CI verification scripts (`scripts/`, Python standard library only, no dependencies).

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
| Homograph substitution in addresses | Project addresses use ASCII; non-ASCII paths are percent-encoded and checked before release |
| Installation-time content substitution | The manual process uses tagged releases and asks users to inspect files before installing |
| Regression against the project's own rules | Six CI workflows cover regex fixtures, self-scanning, Russian calques, spec/source validation, documentation consistency, and release checks |
| Path traversal via data | Paths the validators take from data are confined to the repository root: corpus entries in `eval/manifest.v1.json` and the `fixture_file` field of the source registry. Absolute paths, drive letters, `..` escapes and symlinks pointing outside the root are rejected; the refusal is distinguishable from a corpus regression by exit code 2 |
| Path given as a command-line argument | Deliberately NOT restricted. The validators in `scripts/` and `eval/` are local developer tools: a path named by the operator carries the operator's own authority. Scanning an arbitrary file (`check_markers.py --scan file.md`) is a documented capability, not a hole. Static analysers flag this as path traversal because they treat `argv` as untrusted by default — true for services, not for command-line utilities |

## Release integrity

Each release has a `vX.Y.Z` tag and release notes. For the highest assurance, install a tagged release and compare its contents with the file list in the README's pre-installation checklist.

## Reporting a vulnerability

Do not publish sensitive details in a public issue. Contact the maintainer privately using the contact method shown on the [Vladimir-Human GitHub profile](https://github.com/Vladimir-Human). For non-sensitive security questions, open an issue at <https://github.com/Vladimir-Human/humanizer-ru/issues>.

Include the skill version, affected file, and the smallest sample that reproduces the problem.

## Supported versions

Security fixes are released for the latest version on the default branch.
