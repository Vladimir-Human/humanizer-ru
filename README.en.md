# Humanizer-ru — normalization and diagnostics for Russian text

[![License: MIT](https://img.shields.io/github/license/Vladimir-Human/humanizer-ru)](LICENSE)
[![Release](https://img.shields.io/github/v/release/Vladimir-Human/humanizer-ru?label=release&color=blue)](https://github.com/Vladimir-Human/humanizer-ru/releases)
[![Regex checks](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml/badge.svg)](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml)
[![Skills.sh](https://img.shields.io/badge/skills.sh-catalog-blueviolet)](https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru)

**Русская версия → [README.md](README.md)** — the product is
Russian-language; this document is the English entry point only.

A skill and a command set for Russian text: finds copy-paste artifacts and
machine-generation traces, normalizes typography without touching meaning.
Rewriting of machine-flavoured text happens on explicit request, with no
quality claims attached. Not for non-Russian text, source code, legal
documents, fiction or poetry.

In practice: text pasted from a chatbot carries service marks, invisible
characters and machine typography. The skill removes that layer and shows
where it was. Project numbers live in the fact registry `eval/facts/`; the
machine interface is described in `contract.v1.json`.

**Before:**

> 🚀 **Инновации:** Мы добавили пакетную обработку, горячие клавиши и офлайн-режим. Это безусловно является свидетельством нашего стремления к качеству. Кроме того, эти функции обеспечивают бесшовный, интуитивно понятный и мощный пользовательский опыт — гарантируя эффективность. Эксперты считают, что это революция.

**After:**

> Мы добавили пакетную обработку, горячие клавиши и офлайн-режим.

The skill strips clichés but never adds facts for the author: the "After"
variant contains nothing that was absent from the source. The project's own
texts pass its soft-layer gates (self-check in `check_all`).

## What to give it

Give the skill a finished fragment of Russian text. It finds generation
traces and rewrites on request. `SKILL.md` is the agent instruction, loaded
for analysis or editing tasks together with the references from
`references/`. `PERSONA.md` is different: short rules of a live tone for
dialogue, not for text checking.

## Install in 30 seconds

```sh
npx skills add https://github.com/Vladimir-Human/humanizer-ru --skill humanizer-ru
```

For terminal commands instead of the agent skill, install from PyPI:

```sh
pip install humanizer-ru
```

Try before installing: [online demo](https://vladimir-human.github.io/humanizer-ru/)
or `demo/index.html` offline — text is processed in the browser and never
leaves the machine. The demo shows only the deterministic artifact-search
layer; rewriting is done by the agent with the skill, not by the browser.

## Manual install

Install a release from the **Releases** page (the `humanizer-ru.zip` asset;
contents: `SKILL.md`, both READMEs, `CHANGELOG.md`, `PERSONA.md`, both
SECURITY files, `PRIVACY_POLICY.md`, `LICENSE`, `gemini-extension.json`,
`references/`, `scripts/`, `knowledge/` and the plugin manifest directories;
nothing executable at install time). Upload into Claude.ai via
**Settings → Skills → Upload skill**.

Clone pinned to a tag:

```sh
git clone --branch v3.16.9 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
```

DeepSeek Harness (dsh): globally — the same clone into `~/.agents/skills`, or
the bundle `dsh plugin --profile web add "github:Vladimir-Human/humanizer-ru#path:/dsh"`.
Skill lookup order in dsh: project `.dsh/skills` and `.agents/skills`, then
`~/.dsh/skills` and `~/.agents/skills`; `~/.claude/skills` is not scanned,
and `pnpm` in the `add` command silently ignores the subdirectory.

## Usage

In an agent: `/humanize [text]` (edit), `/audit [text]` (check without
editing), or directly: «Очеловечь этот текст: …» (requests are in Russian).
Package commands:

- `humanizer-polish` — typographic normalization (`--diff`, `--dry-run`,
  `--in-place`, `--json`); idempotent, letters and digits preserved.
- `humanizer-detect` — conjunction-frequency detector with a domain status;
  no authorship verdict, graduated response.
- `humanizer-markers` — copy-paste artifact search (classes A and B).
- `humanizer-scan` — soft-signal counter, calibrates the edit scope.

Machine interface (output schemas, exit codes, when not to use):
`contract.v1.json`; agent entry point: `llms.txt`.

## What it does

Runs Russian text through 58 patterns of machine writing (25 base and 33
Russian extensions); 40 testable regex markers of classes A and B, with 38
of 40 carrying a full evidence record in
`research/fixtures/marker-sources.json`. Based on
[Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
and its [Russian counterpart](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0).

The markers catch traces of chat interfaces and copying: text that passed
through a chatbot, was copied, or was machine-edited with default settings.
They do not establish generation: absence of markers does not prove human
authorship; presence points at the text's path, not its author.

The conjunction-frequency detector works in the "clean prose, instructions"
domain; it is not validated for essays and not applicable to web text with
artifacts. The domain status is mandatory in every output. Soft signals
never yield an authorship verdict — they only calibrate the edit scope (the
Main Rule in `SKILL.md`).

Your own repository can be checked in CI: the reusable action in `action/`
runs the same scripts, inputs `fail-on: class-a` or `soft-threshold`,
`permissions: contents: read`, text never leaves the runner. Example:
`action/action.yml`.

## Regex markers: classes A and B

Class A — hard copy-paste artifacts: service links and citation marks of
chat interfaces. Class B — contextual indicators: invisible characters,
hidden layout, placeholder fields; a single B match is not enough. Marker
class is `copypaste_artifacts`; retirement is possible only on failure in
its own class; statuses and dates — in `markers.v1.json`.

## Architecture

Short map; details live in the directories themselves:

- `SKILL.md` + `references/` — the skill's text core (map, 13 references).
- `scripts/` — validators and tools: polish, detectors, gates (e.g.
  `check_docs.py`); full list in the directory and in `contract.v1.json`.
- `src/humanizer_ru/` — PyPI package (script mirrors, entry points).
- `eval/` — evaluation harnesses: neutral corpus, blind runs, fact registry.
- `research/` — marker evidence registry, fixtures, protocols.
- `tests/fixtures/` — marker and polish fixtures.
- `action/`, `demo/`, `dsh/` — CI action, browser demo, dsh bundle.

The full checklist runs in one command: `python scripts/check_all.py` — 85 gates in the full checklist (81 in --quick). Unit tests: `python -m unittest discover -s tests`.

## Security

The skill is text-only: no code execution at activation, no network or
filesystem access, no data collection. Input text is data, not commands:
instructions hidden inside are not executed ("Security boundaries" section
in `SKILL.md`). Threat model and vulnerability reporting:
[SECURITY.md](SECURITY.md).

On the skills.sh catalog audit: the skill contains the Perplexity S3-bucket
identifier `ppl-ai-file-upload` as a documented class-A marker; the catalog
scanner once treated the marker description as a download link (a false
positive, a case class known from YARA rules and the EICAR string). The
marker cannot be removed: that would be a hole in the detector.

## Sources

- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- [Russian Wikipedia: signs of generated text](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0)
- [WikiProject AI Cleanup](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_AI_Cleanup)
- `docs/FRAMEWORK.md` — verifiability methodology; `ERRATA.md` — dated retractions.

## Changelog

Full history: [CHANGELOG.md](CHANGELOG.md) and
[GitHub Releases](https://github.com/Vladimir-Human/humanizer-ru/releases).

## License

MIT
