# Humanizer-ru — Russian AI text humanizer

[![License: MIT](https://img.shields.io/github/license/Vladimir-Human/humanizer-ru)](LICENSE)
[![GitHub stars](https://badgen.net/github/stars/Vladimir-Human/humanizer-ru)](https://github.com/Vladimir-Human/humanizer-ru/stargazers)
[![Version](https://img.shields.io/github/v/release/Vladimir-Human/humanizer-ru?label=version&color=blue)](https://github.com/Vladimir-Human/humanizer-ru/releases)
[![Regex checks](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml/badge.svg)](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml)
[![Skills.sh](https://img.shields.io/badge/skills.sh-266%2B_installs-blueviolet)](https://skills.sh/vladimir-human/humanizer-ru/humanizer-ru)

**[Русская версия → README.md](README.md)**

An agent skill that finds and removes traces of machine generation from Russian-language text: 38 patterns, 35 unambiguous regex markers, all checks run automatically in CI. [skills.sh](https://skills.sh/vladimir-human/humanizer-ru/humanizer-ru) reports passing audits by Gen Agent Trust Hub, Socket, and Snyk.

**Before** — typical AI-generated Russian copy: vague superlatives, forced triads, "experts believe":

> 🚀 **Инновации:** Данное программное обеспечение безусловно является свидетельством нашего стремления к качеству. Кроме того, оно обеспечивает бесшовный, интуитивно понятный и мощный пользовательский опыт — гарантируя эффективность. Эксперты считают, что это революция.

**After** — specific facts, human rhythm:

> Мы добавили пакетную обработку, горячие клавиши и офлайн-режим. Тестировщики отмечают, что задачи выполняются быстрее.

## Scope: editing, not live dialogue

This skill is a text editor: give it a fragment and it finds AI-generated
patterns and, on request, rewrites them. You do not need to keep the full
SKILL.md in the system prompt of a chat client — responses would slow down
without becoming more natural, because editorial rules are not designed for
generating replies. For live dialogue there is a separate compact ruleset —
[PERSONA.md](PERSONA.md): copy its core into the system instructions of your
chat client.

## Install in 30 seconds

```sh
npx skills add https://github.com/vladimir-human/humanizer-ru --skill humanizer-ru
```

The installer lets you pick target agents: Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and other environments that support the Agent Skills format. The skill itself contains plain-text instructions and does not execute code during use. The `npx` command does run the third-party Skills CLI; if you prefer to inspect every file before installing, use the [manual method](#manual-install).

## Manual install

1. Open the **Releases** page, pick the latest release, and download `Source code (zip)`. Review `SKILL.md` and `references/` before installing.
2. **Claude.ai**: Settings → Skills → Upload skill (if the archive has a nested folder, re-zip so `SKILL.md` sits at the archive root).
3. **Claude Code (local)**:

```sh
mkdir -p ~/.claude/skills
git clone --branch v3.2.0 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
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

Detects and fixes 38 patterns of machine-generated Russian text (25 base + 13 Russian-specific), grouped into four families:

| Family | Examples |
|---|---|
| Content | vague praise instead of specifics, "experts believe" without a source, bureaucratic officialese |
| Language | machine lexicon, forced rule-of-three, "not only... but also" parallelisms, hedging cascades |
| Structure & style | em-dash and bold overuse, emoji lists, Markdown remnants in plain text, broken heading hierarchy |
| Communication | chat remnants ("Hope this helps!"), sycophancy, generic upbeat closings |

Based on [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) and its [Russian counterpart](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0).

## Unambiguous markers

35 regular expressions catch copy-paste artifacts that almost certainly mean AI: ChatGPT `:contentReference[oaicite:N]` and `utm_source=chatgpt.com`, invisible citation separators (`U+E200–E204`), Gemini `[cite: N]` and grounding redirect links, Grok citation cards, Copilot `[^N^]`, DeepSeek reasoning-tag leftovers, zero-width watermark characters, placeholder URLs and dates.

Run all markers against test fixtures:

```sh
python3 scripts/check_markers.py
```

Scan any text for markers:

```sh
python3 scripts/check_markers.py --scan file.md
```

## Architecture

```
humanizer-ru/
├── SKILL.md                 # Map, decision tree, checklist
├── README.md                # Russian README
├── README.en.md             # This file
├── SECURITY.md              # Security policy and threat model
├── scripts/check_markers.py # Regex test runner and text scanner
├── .github/workflows/       # CI: self-scan, regex tests, style checks
└── references/              # Full pattern descriptions, fixtures, model fingerprints
```

## Security

- Text-only skill: no code execution, no network or filesystem access, no data collection. `scripts/check_markers.py` runs only in CI and manually by the developer.
- Input text is treated as data: instructions hidden inside the text being checked are not executed.
- Threat model and vulnerability reporting: [SECURITY.en.md](SECURITY.en.md) · [Русская версия](SECURITY.md).

## Versions

Latest release: **v3.2.0** (July 7, 2026). The full changelog is kept in the [Russian README](README.md#версии).

## License

MIT
