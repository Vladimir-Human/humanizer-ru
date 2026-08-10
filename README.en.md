# Humanizer-ru — Russian AI text humanizer

[![License: MIT](https://img.shields.io/github/license/Vladimir-Human/humanizer-ru)](LICENSE)
[![GitHub stars](https://badgen.net/github/stars/Vladimir-Human/humanizer-ru)](https://github.com/Vladimir-Human/humanizer-ru/stargazers)
[![Version](https://img.shields.io/github/v/release/Vladimir-Human/humanizer-ru?label=version&color=blue)](https://github.com/Vladimir-Human/humanizer-ru/releases)
[![Regex checks](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml/badge.svg)](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml)
[![Skills.sh](https://img.shields.io/badge/skills.sh-catalog-blueviolet)](https://skills.sh/vladimir-human/humanizer-ru/humanizer-ru)

**[Русская версия → README.md](README.md)**

An agent skill that finds and removes traces of machine generation from Russian-language text: 38 patterns (25 base + 13 Russian-specific extensions) and 38 testable regex markers split into hard copy-paste artifacts and contextual indicators. All checks run automatically in CI. [skills.sh](https://skills.sh/vladimir-human/humanizer-ru/humanizer-ru) reports passing audits by Gen Agent Trust Hub and Socket; the red Snyk badge is explained under Security.

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

## Install in 30 seconds

```sh
npx skills add https://github.com/vladimir-human/humanizer-ru --skill humanizer-ru
```

The installer lets you pick target agents: Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and other environments that support the Agent Skills format. The skill itself contains plain-text instructions and does not execute code during use. The `npx` command does run the third-party Skills CLI; if you prefer to inspect every file before installing, use the [manual method](#manual-install).

## Manual install

1. Open the **Releases** page, pick the latest release, and download the attached `humanizer-ru.zip`. That is the built skill archive: `SKILL.md`, `README.md`, `README.en.md`, `SECURITY.md`, `SECURITY.en.md`, `CHANGELOG.md`, `PERSONA.md`, `LICENSE`, `references/` and `scripts/`, nothing executable at install time. `Source code (zip)`, which GitHub attaches to every release, is the full repository tree including `.github/`, `research/` and `tests/` — take it only if you intend to run the validators. Review `SKILL.md` and `references/` before installing.
2. **Claude.ai**: Settings → Skills → Upload skill. In `humanizer-ru.zip` `SKILL.md` already sits at the archive root, so no re-zipping is needed.
3. **Claude Code (local)**:

```sh
mkdir -p ~/.claude/skills
git clone --branch v3.9.0 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
```

## Usage

```text
/humanizer-ru [paste your text]
```

Or directly:

```text
Очеловечь этот текст: [your text]
```

## What it does

Detects and fixes 38 patterns of machine-generated Russian text (25 base + 13 Russian-specific extensions), grouped into four families:

| Family | Examples |
|---|---|
| Content | vague praise instead of specifics, "experts believe" without a source, bureaucratic officialese |
| Language | machine lexicon, forced rule-of-three, "not only... but also" parallelisms, hedging cascades |
| Structure & style | dash and bold overuse, emoji lists, Markdown remnants in plain text, broken heading hierarchy |
| Communication | chat remnants ("Hope this helps!"), sycophancy, generic upbeat closings |

Based on [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) and its [Russian counterpart](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0).

Since v3.8 the soft layer has become measurable. `scripts/scan_soft_signals.py` finds candidates across the four families above, counts each pattern once per text, and applies the decision-tree thresholds; genre exceptions follow `references/false-positives.md`. It prints quotes and a recommended scope of editing and never issues an authorship verdict — per the Main Rule, the final call stays with the agent. On the human control corpus the regex layer finds no matches, and the few soft-signal candidates on classical prose (literary dashes, repetitions) stay neutral under the genre exceptions; on Russian model outputs it surfaces candidates where the regex layer stays silent.

## Regex markers: classes A and B

38 regular expressions catch traces of machine generation. They fall into two classes:

- **Class A — hard copy-paste artifacts** that almost certainly mean AI: ChatGPT `:contentReference[oaicite:N]` and `utm_source=chatgpt.com`, Gemini `[cite: N]` and span markers, grounding redirect links, Grok citation cards, Copilot `[^N^]`, DeepSeek reasoning-tag leftovers, Perplexity `ppl-ai-file-upload` S3 links.
- **Class B — contextual indicators** that need human judgement: placeholder URLs and dates, `referrer=grok.com`, invisible private-use-area citation separators (`U+E200–E204`), zero-width characters, and reference names containing internal-tool identifiers. A B marker alone is never an authorship verdict.

Run all markers against test fixtures:

```sh
python3 scripts/check_markers.py
```

Scan any text for markers:

```sh
python3 scripts/check_markers.py --scan file.md
```

Note: `references/test-fixtures*.md` intentionally contain markers as reference samples, so scanning those files reports matches by design; the CI self-scan excludes these paths.

## Architecture

```
humanizer-ru/
├── SKILL.md                      # Map, decision tree, checklist
├── PERSONA.md                    # Compact ruleset for live dialogue
├── README.md                     # Russian README
├── README.en.md                  # This file
├── CHANGELOG.md                  # Full version history
├── SECURITY.md / SECURITY.en.md  # Security policy and threat model
├── scripts/
│   ├── check_markers.py          # Regex test runner and text scanner
│   ├── check_spec.py             # Agent Skills spec compliance
│   ├── check_fixture_sources.py  # Fixture source verification
│   ├── check_docs.py             # Documentation consistency checks
│   ├── check_examples.py         # Before/After example honesty gate
│   ├── check_budget.py           # Context budget vs the official spec
│   ├── check_readme_parity.py    # RU/EN showcase parity and honesty
│   ├── check_own_style.py        # Soft-signal threshold on own prose
│   ├── check_reference_maps.py   # Split-reference map integrity
│   ├── check_corpus.py           # Validation corpus regression
│   ├── check_perf.py             # Expression speed on a large input
│   ├── check_release.py          # Release archive build and verification
│   ├── count_style_markers.py    # Style marker counter for A/B runs
│   ├── scan_soft_signals.py      # Measurable soft-signal scanner
│   └── check_all.py              # Full release checklist in one command
├── eval/
│   ├── run_eval.py               # Neutral corpus any candidate skill can run
│   ├── blind_eval.py             # Blind paired evaluation of the skill effect
│   ├── HOW-TO-RUN.md             # Evaluation protocol and metric boundaries
│   ├── runs/                     # Paired runs: 2026-07-26-baseline
│   └── results/                  # Full run reports, including metrics that
│                                 #   do not favour the skill
├── references/                   # Full pattern descriptions, fixtures, model fingerprints
├── research/                     # Protocols, raw model outputs, pilot results
├── tests/fixtures/               # Marker test fixtures
└── .github/workflows/            # CI: self-scan, regex tests, style and docs checks
```

The release policy separates a stable core (genre rules, false-positive boundaries, and the decision tree) from a fast marker layer. A fast-layer marker needs positive, negative, and boundary fixtures plus an evidence record in `research/fixtures/marker-sources.json`; it does not become a hard marker merely because it is new.

## Security

- Text-only skill: no code execution during use, no network or filesystem access, no data collection. The validators in `scripts/` (`check_markers.py`, `check_docs.py` and others) run only in the repository's CI or manually by the developer.
- Input text is treated as data: instructions hidden inside the text being checked are not executed.
- Threat model and vulnerability reporting: [SECURITY.en.md](SECURITY.en.md) · [Русская версия](SECURITY.md).
- **On the red Snyk badge in the skills.sh catalogue.** The automated audit flags this skill with E005, "suspicious download URL". The finding is a false positive: the scanner sees the Perplexity S3 bucket identifier `ppl-ai-file-upload` — a documented Class A marker this skill uses to recognise machine-generated text — and reads the description of a marker as an instruction to download a file. The skill downloads nothing: following links from the text under review is forbidden by the safety-boundaries section of `SKILL.md` («Границы безопасности», the file is in Russian). This is the same class of false positive familiar from YARA rule sets and the EICAR test string: a tool that looks for an indicator has to contain that indicator. The catalogue's two other auditors return PASS. We will not drop the marker to satisfy a verdict — that would be a hole in the detector.

## Sources

The pattern base draws on
[Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
and its Russian counterpart
[Википедия:Признаки сгенерированности текста](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0).

A full evidence record — an immutable source URL, the date it was accessed,
a verbatim sample, an evidence class, and a fixture in
`research/fixtures/marker-sources.json` — currently exists for 36 of 38
fast-layer markers; the rest are covered by fixtures only. The validator
prints this honest coverage rather than rounding it to a convenient number.

Citation metadata for this repository lives in [CITATION.cff](CITATION.cff).

## Changelog

The current version is shown on the badge at the top. Full history:
[CHANGELOG.md](CHANGELOG.md) and
[GitHub Releases](https://github.com/Vladimir-Human/humanizer-ru/releases).

## License

MIT
