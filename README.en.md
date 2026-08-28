# Humanizer-ru — Russian AI text humanizer

[![License: MIT](https://img.shields.io/github/license/Vladimir-Human/humanizer-ru)](LICENSE)
[![GitHub stars](https://badgen.net/github/stars/Vladimir-Human/humanizer-ru)](https://github.com/Vladimir-Human/humanizer-ru/stargazers)
[![Version](https://img.shields.io/github/v/release/Vladimir-Human/humanizer-ru?label=version&color=blue)](https://github.com/Vladimir-Human/humanizer-ru/releases)
[![Regex checks](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml/badge.svg)](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml)
[![Skills.sh](https://img.shields.io/badge/skills.sh-catalog-blueviolet)](https://skills.sh/vladimir-human/humanizer-ru/humanizer-ru)

**[Русская версия → README.md](README.md)**

An agent skill that finds and removes traces of machine generation from Russian-language text. It rewrites AI-sounding prose into human prose without distorting the meaning, and it leaves live human writing alone: a false positive costs more than a miss.

It ships 56 patterns (25 base + 31 Russian-specific extensions) and 40 testable regex markers (38 with a full evidence record) split into hard copy-paste artifacts and contextual indicators; all checks run automatically in CI. [skills.sh](https://skills.sh/vladimir-human/humanizer-ru/humanizer-ru) reports passing audits by Gen Agent Trust Hub and Socket; the red Snyk badge is explained under Security.

**Before** — typical AI-generated Russian copy: vague superlatives, forced triads, "experts believe":

> 🚀 **Инновации:** Мы добавили пакетную обработку, горячие клавиши и офлайн-режим. Это безусловно является свидетельством нашего стремления к качеству. Кроме того, эти функции обеспечивают бесшовный, интуитивно понятный и мощный пользовательский опыт — гарантируя эффективность. Эксперты считают, что это революция.

**After** — only the facts that were in the source, noise removed:

> Мы добавили пакетную обработку, горячие клавиши и офлайн-режим.

The skill removes stock phrasing but never adds facts for the author. Everything in the “After” version above was already present in the source.

## What to give it

Give the skill a finished passage. It will find traces of generated prose and,
on request, rewrite the text. Do not put the full SKILL.md in a chat client's
system prompt: it will slow replies without making the conversation more
natural. For live dialogue, use the short rules in [PERSONA.md](PERSONA.md).

## Same-named projects — don't confuse us

There are other repositories named `humanizer-ru` on GitHub, unaffiliated
with this project. Their stances differ:

| Project | Focus | Stance on detectors |
|---|---|---|
| [Vladimir-Human/humanizer-ru](https://github.com/Vladimir-Human/humanizer-ru) — this project | A Russian-language editing skill: 56 patterns, 40 regex markers, blind pairwise runs | Removes labels in text and files the user owns (invisible characters, statistical markers, C2PA/EXIF/XMP; non-deterministic techniques are best-effort, pixel-level SynthID is out of scope — see the removal matrix) and reduces statistical traces of machine generation in text the user owns; label removal is an open product capability. Detector bypass is not claimed as a guarantee: only relative before/after detectability deltas with false-positive control are published. Do not harm live writing and do not add facts — inviolable principles. |
| [smixs/humanizer-ru](https://github.com/smixs/humanizer-ru) | A "humanizer & detector" skill: rewriting and detection in one tool; the leaderboard runs its deterministic linter | — |
| [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) | A humanizer skill: its tagline claims tuning for GPTZero/DivEye/RuBERT metrics; its FAQ shows a bypass technique | The bypass technique is in their FAQ |
| [blader/humanizer](https://github.com/blader/humanizer) | An English-language skill of the same kind, published three days earlier | — |

We are not affiliated with any of them. This project's declaration: "label
removal is an open product capability; detector bypass is not claimed as a
guarantee". The frame is described in docs/FRAMEWORK.md; the limits of removal techniques — in references/removal-matrix.md.

## Install in 30 seconds

```sh
npx skills add https://github.com/vladimir-human/humanizer-ru --skill humanizer-ru
```

If you want a plain terminal command instead of an agent skill — the package installs from PyPI:

```sh
pip install humanizer-ru
```

Try before installing: the [regex-layer online demo](https://vladimir-human.github.io/humanizer-ru/) or [demo/index.html](demo/index.html) offline — it runs entirely in your browser and the text never leaves your machine. The demo covers the deterministic layer only (artifact detection); rewriting is done by the agent with the skill, not by the browser.

The `npx skills add` installer lets you pick target agents: Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and other environments that support the Agent Skills format. The repository also ships plugin manifests (`.claude-plugin/` for the Claude marketplace, `.codex-plugin/`, `.cursor-plugin/`, `agents/openai.yaml`) and the `commands/` slash-commands — `/humanize` (rewrite) and `/audit` (check for AI traces without rewriting). The skill itself contains plain-text instructions and does not execute code during use. The `npx` command does run the third-party Skills CLI; if you prefer to inspect every file before installing, use the [manual method](#manual-install).

## Manual install

1. Open the **Releases** page, pick the latest release, and download the attached `humanizer-ru.zip`. That is the built skill archive: `SKILL.md`, `README.md`, `README.en.md`, `SECURITY.md`, `SECURITY.en.md`, `CHANGELOG.md`, `PERSONA.md`, `PRIVACY_POLICY.md`, `LICENSE`, `gemini-extension.json`, the `references/`, `scripts/` and `knowledge/` directories, the plugin manifests `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `agents/`, and the `commands/` slash-commands — nothing executable at install time. `Source code (zip)`, which GitHub attaches to every release, is the full repository tree including `.github/`, `research/` and `tests/` — take it only if you intend to run the validators. Review `SKILL.md` and `references/` before installing.
2. **Claude.ai**: Settings → Skills → Upload skill. In `humanizer-ru.zip` `SKILL.md` already sits at the archive root, so no re-zipping is needed.
3. **Organizations (Enterprise & Team)**: the administrator verifies the release
   (step 1 covers the review) and uploads it to the shared library — the skill
   becomes available to the whole team.
4. **Claude Code (local)**:

```sh
mkdir -p ~/.claude/skills
git clone --branch v3.15.1 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
```

### DeepSeek Harness (dsh)

dsh looks for skills in its own directories. Verified with dsh 0.1.0-rc.6 and 0.1.0-rc.8 (CI pins rc.8). This is a developer preview: breaking changes are promised, so check your own version's documentation.

Global install (all projects and agents):

```sh
mkdir -p ~/.agents/skills
git clone --branch v3.15.1 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.agents/skills/humanizer-ru
```

The second way is the bundle in the `dsh/` subdirectory, installed by the plugin manager. The profile is created on first use, and `pnpm` must be on PATH:

```sh
dsh plugin --profile web add "github:Vladimir-Human/humanizer-ru#path:/dsh"
```

The bundle carries a copy of `SKILL.md`, `references/` and `knowledge/`; the `check_bundle_sync.py` gate keeps it equal to the source. To remove it: `dsh plugin --profile web remove humanizer-ru-dsh`.

The command tracks the default branch. Pinning a tag and a subdirectory in one spec does not work, and it fails silently: `pnpm` drops the subdirectory, installs the whole repository as a plain dependency and exits 0, leaving the profile without the layer. Verified on dsh 0.1.0-rc.6.

dsh search precedence (nearest directory wins): `<project>/.dsh/skills`, `<project>/.agents/skills`, `~/.dsh/skills`, `~/.agents/skills`. dsh never scans `~/.claude/skills`: a skill installed there via the Claude Code steps above stays invisible to dsh.

## Usage

```text
/humanize [paste your text]
```

Check without editing:

```text
/audit [paste your text]
```

Or directly:

```text
Очеловечь этот текст: [your text]
```

## CI gate for your own repositories

The repository ships a reusable composite action in the `action/` directory.
It runs exactly the same scripts as this project's CI on your files —
standard-library Python, no external services, and no text leaves the
GitHub Actions runner. It only needs `permissions: contents: read`
(the action checks out and reads files).

A minimal workflow in your repository, e.g. `.github/workflows/humanizer.yml`:

```yaml
name: humanizer-ru

on:
  push:
    paths: ['content/**/*.md', 'docs/**/*.md']
  pull_request:
    paths: ['content/**/*.md', 'docs/**/*.md']
  workflow_dispatch:

permissions:
  contents: read

jobs:
  humanizer:
    name: Machine-generation traces
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: Vladimir-Human/humanizer-ru/action@v3.15.1
        with:
          files: 'content/**/*.md docs/**/*.md'   # bash glob(s)
          genre: neutral                          # used in soft-threshold mode
          fail-on: class-a                        # or soft-threshold
          ref: ''                                 # checkout of your repo (empty — HEAD)
```

Action inputs:

| Input | Default | What it does |
|---|---|---|
| `files` | `**/*.md` | Files to scan: one bash glob or several separated by spaces. The action enables `globstar` and `nullglob`, so `**/*.md` recurses into subdirectories. |
| `genre` | `neutral` | Genre for soft signals: `neutral`, `fiction`, `legal`, `academic`, `marketing`, `chat`. Used only with `fail-on: soft-threshold`. |
| `fail-on` | `class-a` | `class-a` — hard regex layer (`check_markers.py --scan --class a`): only class A markers fail the gate; contextual class B markers (placeholder dates, `referrer=grok.com`, zero-width chars) are printed as warnings and do not fail the build; `soft-threshold` — soft-signal counter (`scan_soft_signals.py --fail-multicat 3`). |
| `fix` | `false` | Autofix (only with `fail-on: class-a`): files carrying class A markers are cleaned by the deterministic `filemarks.py --clean` layer; files without markers are not rewritten at all. Changes stay in the working directory — the calling workflow commits them. A re-scan follows the cleanup: residual markers fail the gate. Measured boundaries: cleanup neutrality is confirmed on 49 reference-corpus files (0 bytes changed); cleaning a marked file normalizes line endings to LF. |
| `ref` | empty | Ref of your repository for checkout. Empty — current HEAD (for pull_request — the default merge commit). |

The action version is pinned by the `uses` string
`Vladimir-Human/humanizer-ru/action@v3.15.1`, not by the `ref` input.
The `ref` input controls which state of the scanned repository is checked out.

Limitations and security policy:

- `permissions: contents: read`; the action publishes and comments nothing.
- Text never leaves the runner: the scripts from `action/../scripts` run locally and do not open the network.
- Only standard-library Python and the official `actions/checkout` (pinned by SHA) are used.

Which gate to choose:

- `class-a` — the pipeline minimum: catches interface artifacts and service links (`ppl-ai-file-upload`, `[citation:3]`, etc.). Only class A markers fail the gate; class B markers (soft hyphen from typesetting, placeholder dates, `referrer=grok.com`) are printed as warnings — per the project policy they never yield a verdict on their own.
- `soft-threshold` — linguistic signalling: `--fail-multicat 3` fails the gate when a text has 3 or more soft signals spanning 2 or more categories. One or two are not enough: the script deliberately counts patterns conservatively and never issues an authorship verdict. Thresholds hold until validation on a representative corpus; the threshold sweep lives in research/soft-threshold-sweep/.

## What it does

Detects and fixes 56 patterns of machine-generated Russian text (25 base + 31 Russian-specific extensions), grouped into four families:

| Family | Examples |
|---|---|
| Content | vague praise instead of specifics, "experts believe" without a source, bureaucratic officialese |
| Language | machine lexicon, forced rule-of-three, "not only... but also" parallelisms, hedging cascades |
| Structure & style | dash and bold overuse, emoji lists, Markdown remnants in plain text, broken heading hierarchy |
| Communication | chat remnants ("Hope this helps!"), sycophancy, generic upbeat closings |

Based on [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) and its [Russian counterpart](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0).

Since v3.8 the soft layer has become measurable. `scripts/scan_soft_signals.py` finds candidates across the four families above, counts each pattern once per text, and applies the decision-tree thresholds; genre exceptions follow `references/false-positives.md`. It prints quotes and a recommended scope of editing and never issues an authorship verdict — per the Main Rule, the final call stays with the agent. The behaviour on the human control corpus is verifiable: across the 26 human texts no file accumulates signals in 2+ categories (the `--max-cats 1` gate); the stray dashes and triples in the classics remain within a single category and do not fail the gate. On Russian model outputs it surfaces candidates where the regex layer stays silent. Only mechanical axes are published outward — marker removal, fact cleanliness, false edits (see [LEADERBOARD.md](LEADERBOARD.md)); readability is scored by an internal judge panel and stays an internal signal: the panel is single-family, and positional noise is documented in the runs.

Shares of “0 of N” are published with a confidence interval: 0 false positives on 11 human texts is an observation of 0/11, not a proven zero — Wilson 95% CI [0%; 25.9%]. scripts/check_confidence.py recomputes and cross-checks the intervals.

## Architecture

```
humanizer-ru/
├── SKILL.md                      # Map, decision tree, checklist
├── PERSONA.md                    # Compact ruleset for live dialogue
├── README.md                     # Russian README
├── README.en.md                  # This file
├── CHANGELOG.md                  # Full version history
├── LEADERBOARD.md                # Mechanical axes: detector runs
├── SECURITY.md / SECURITY.en.md  # Security policy and threat model
├── CITATION.cff                  # Citation card
├── LICENSE                       # MIT
├── dsh/                            # DeepSeek Harness bundle (vendored SKILL.md + references/ + knowledge/)
├── GOVERNANCE.md              # Release roles and rights, dormant policy
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md
├── PRIVACY_POLICY.md           # Short privacy policy (text-only skill)
├── AGENTS.md                   # Repository map for editing agents
├── gemini-extension.json       # Gemini CLI extension manifest
├── .claude-plugin/             # Claude plugin + marketplace manifests
├── .codex-plugin/              # Codex plugin manifest
├── .cursor-plugin/             # Cursor plugin manifest
├── agents/                     # Agent declaration (openai.yaml)
├── commands/                   # Slash-commands /humanize and /audit
├── knowledge/                  # Owner feedback log (corrections.md)
├── docs/
│   └── FRAMEWORK.md            # Public verifiability methodology
├── scripts/
│   ├── check_markers.py          # Regex test runner and text scanner
│   ├── check_spec.py             # Agent Skills spec compliance
│   ├── check_fixture_sources.py  # Fixture source verification
│   ├── check_link_rot.py         # Fixture source link-rot gate
│   ├── check_outward.py          # Outward-draft validator (issues, PRs)
│   ├── check_fixture_refs.py     # Fixture reference integrity gate
│   ├── check_version_literals.py # Hardcoded version literals gate
│   ├── check_git_depth.py        # Shallow-clone detection gate
│   ├── check_superposition.py    # Superposition run integrity gate
│   ├── apply_patch.py            # Exact-match patches from patch.json
│   ├── check_docs.py             # Documentation consistency checks
│   ├── check_examples.py         # Before/After example honesty gate
│   ├── check_budget.py           # Context budget vs the official spec
│   ├── check_readme_parity.py    # RU/EN showcase parity and honesty
│   ├── check_own_style.py        # Soft-signal threshold on own prose
│   ├── check_self_prose.py      # Self-application: display prose below the soft-layer threshold
│   ├── check_reference_maps.py   # Split-reference map integrity
│   ├── check_corpus.py           # Validation corpus regression
│   ├── check_adversarial.py      # Adversarial false-positive corpus gate
│   ├── check_perf.py             # Expression speed on a large input
│   ├── check_release.py          # Release archive build and verification
│   ├── check_bundle_sync.py      # dsh/ bundle vendor sync
│   ├── check_pkg_sync.py         # PyPI package sync with the root scripts
│   ├── export_markers.py         # markers.v1.json machine-readable registry generator
│   ├── check_markers_export.py   # markers.v1.json regeneration sync gate
│   ├── check_removal_parity.py   # removal↔detector parity gate
│   ├── filemarks/                # Layer A/B and file metadata (inspect/clean)
│   ├── count_style_markers.py    # Style marker counter for A/B runs
│   ├── scan_soft_signals.py      # Measurable soft-signal scanner
│   ├── check_json_output.py     # UTF-8 machine-readable stdout gate
│   ├── check_confidence.py       # Wilson CI for leaderboard shares
│   ├── threshold_sweep.py        # Soft-layer threshold sweep
│   └── check_all.py              # Full release checklist in one command
├── eval/
│   ├── run_eval.py               # Neutral corpus any candidate skill can run
│   ├── blind_eval.py             # Blind paired evaluation of the skill effect
│   ├── detect_eval.py            # Detector harness: before/after detectability delta
│   ├── detectors/                # Local detectors (0..1 contract, graceful)
│   ├── run_triggers.py           # Skill activation boundary gate
│   ├── scenarios/                # Skill-level scenario evals (12 cases)
│   ├── ainl_calibration.py       # Soft-feature calibration on AINL-Eval
│   ├── detect-results/           # JSON of detector runs for the axis
│   ├── HOW-TO-RUN.md             # Evaluation protocol and metric boundaries
│   ├── README.md                 # Eval map and metric glossary
│   ├── manifest.v1.json          # Neutral corpus schema
│   ├── runs/                     # Paired runs (12 records; see runs/README.md)
│   └── results/                  # Full run reports, including metrics that
│                                 #   do not favour the skill
├── references/                   # 12 reference files (two split into parts = 17 files)
├── research/                     # Protocols, raw model outputs, pilot results
├── tests/fixtures/               # Marker test fixtures
└── .github/workflows/            # CI: 9 pipelines (regex, self-scan, link-rot,
                                  #     validators, docs, style, release, install, demo)
```

The full checklist runs in one command: `python scripts/check_all.py` — 66 gates in the full checklist (62 in --quick). Unit tests: `python -m unittest discover -s tests`.

The release policy separates a stable core (genre rules, false-positive boundaries, and the decision tree) from a fast marker layer. A fast-layer marker needs positive, negative, and boundary fixtures plus an evidence record in `research/fixtures/marker-sources.json`; it does not become a hard marker merely because it is new.

## Security

- Text-only skill: no code execution during use, no network or filesystem access, no data collection. The validators in `scripts/` (`check_markers.py`, `check_docs.py` and others) run only in the repository's CI or manually by the developer.
- Input text is treated as data: instructions hidden inside the text being checked are not executed.
- Threat model and vulnerability reporting: [SECURITY.en.md](SECURITY.en.md) · [Русская версия](SECURITY.md).
- **On the red Snyk badge in the skills.sh catalogue.** The automated audit flags this skill with E005, "suspicious download URL". The finding is a false positive: the scanner sees the Perplexity S3 bucket identifier `ppl-ai-file-upload` — a documented Class A marker this skill uses to recognise machine-generated text — and reads the description of a marker as an instruction to download a file. The skill downloads nothing: following links from the text under review is forbidden by the safety-boundaries section of `SKILL.md` («Границы безопасности», the file is in Russian). This is the same class of false positive familiar from YARA rule sets and the EICAR test string: a tool that looks for an indicator has to contain that indicator. The catalogue's two other auditors return PASS. We will not drop the marker to satisfy a verdict — that would be a hole in the detector.

## Regex markers: classes A and B

40 regular expressions catch traces of machine generation. They fall into two classes:

- **Class A — hard copy-paste artifacts** that almost certainly mean AI: ChatGPT `:contentReference[oaicite:N]` and `utm_source=chatgpt.com`, Gemini `[cite: N]` and span markers, grounding redirect links, Grok citation cards, Copilot `[^N^]`, DeepSeek reasoning-tag leftovers, Perplexity `ppl-ai-file-upload` S3 links.
- **Class B — contextual indicators** that need human judgement: placeholder URLs and dates, `referrer=grok.com`, invisible private-use-area citation separators (`U+E200–E204`), the short-footnote form (`U+EA01`/`U+EA02` around a digit), zero-width characters, invisible layout marks (soft hyphen, exotic spaces, variation selectors outside emoji), hidden ASCII payloads in the Unicode Tags block (`U+E0000`–`U+E007F`; steganographic watermarks per arXiv:2605.16336 — emoji flags are excluded by a guard), and reference names containing internal-tool identifiers (`<ref name="0searchN">`). A B marker alone is never an authorship verdict.

Run all markers against test fixtures:

```sh
python3 scripts/check_markers.py
```

Scan any text for markers:

```sh
python3 scripts/check_markers.py --scan file.md
```

Note: `references/test-fixtures*.md` intentionally contain markers as reference samples, so scanning those files reports matches by design; the CI self-scan excludes these paths.


## Sources

The pattern base draws on
[Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
and its Russian counterpart
[Википедия:Признаки сгенерированности текста](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0).

A full evidence record — an immutable source URL, the date it was accessed,
a verbatim sample, an evidence class, and a fixture in
`research/fixtures/marker-sources.json` — currently exists for 38 of 40
markers; the rest are covered by fixtures only. Coverage is reported as-is.

- [docs/FRAMEWORK.md](docs/FRAMEWORK.md) — the public verifiability methodology
- `research/fixtures/marker-sources.json` — the evidence registry (38 of 40 markers with an immutable source link)

Citation metadata for this repository lives in [CITATION.cff](CITATION.cff).

## Changelog

The current version is shown on the badge at the top. Full history:
[CHANGELOG.md](CHANGELOG.md) and
[GitHub Releases](https://github.com/Vladimir-Human/humanizer-ru/releases).

## License

MIT
