# humanizer-ru
Verifiable chat-paste hygiene for Russian text

40 regex markers for chat-interface paste artifacts; 38 of them carry a full
evidence record. Class A false positives on 12314 non-carrier texts: zero;
class B: 8, that is 0.00065 (Wilson 95% CI from 0.0003 to 0.0013; measured
2026-09-04 under a frozen preregistration). Every number carries a date and a
reproduction command in [Project in numbers](#project-in-numbers).

Artifact cleanup and fact comparison also accept English input. Pass
`--language en` to `humanizer-clean`, `humanizer-polish`, `humanizer-facts`,
or `humanizer-report` (or use `--language auto`). This profile does not apply
Russian style heuristics and never infers authorship. It preserves code, URLs,
Markdown, and checked facts, and records the selected language in machine output.
The Russian profile remains the default for compatibility.

![The humanizer-markers terminal highlights machine-text traces and explains the reason behind each flag](assets/hero.svg)

[![License: MIT](https://img.shields.io/github/license/Vladimir-Human/humanizer-ru)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/humanizer-ru?label=PyPI&color=blue)](https://pypi.org/project/humanizer-ru/)
[![CI](https://img.shields.io/github/actions/workflow/status/Vladimir-Human/humanizer-ru/regex-check.yml?branch=main&label=CI)](https://github.com/Vladimir-Human/humanizer-ru/actions/workflows/regex-check.yml?query=branch%3Amain)

## Who needs it

- Editors and teachers: check text before publishing: `humanizer-markers --scan file.md`.
- Developers and CI: a gate against chat-interface paste: [action and contract](contract.v1.json).
- AI-assistant users: the same check inside agent environments: [MCP in one config block](#mcp-in-one-config) or the [demo](https://vladimir-human.github.io/humanizer-ru/).

## Try it in 30 seconds

- [Browser demo](https://vladimir-human.github.io/humanizer-ru/): nothing to install, your text never leaves the browser.
- Report a problem or share usage experience: [an issue in the repository](https://github.com/Vladimir-Human/humanizer-ru/issues/new); user text is never sent automatically by the demo or by the feedback collector.
- In a terminal:

```text
pip install humanizer-ru
python -c "open('primer.txt','w',encoding='utf-8').write('Согласно отчёту :contentReference[oaicite:3]{index=3}, рост заявок.\n')"
humanizer-markers --scan primer.txt; echo "rc=$?"
  primer.txt:1 [contentReference] Согласно отчёту :contentReference[oaicite:3]{index=3}, рост заявок.
  Найдено маркеров: 1.
  rc=1
```

rc=1 means "markers found" — the expected outcome on the sample carrying
a paste trace, not an error; rc=0 — no traces, rc=2 — input unreadable
(with --json the error envelope goes to stdout).

### MCP in one config

```json
{
  "mcpServers": {
    "humanizer-ru": {
      "command": "uvx",
      "args": ["--from", "humanizer-ru==3.35.2", "humanizer-mcp"]
    }
  }
}
```

The `uvx` form installs the pinned PyPI release and starts the stdio server.
With a local installation, `pip install humanizer-ru` followed by
`humanizer-mcp` is equivalent.

## Matrix of verified capabilities and boundaries

No leadership claims: there is no comparable external study in the niche
as of this writing (see LEADERBOARD.md). Rows list what the cycle's gates
and tests actually verify; boundaries list what a surface does not do.

| Surface | Known-artifact check | Safe cleanup | Fact cross-check | Machine envelope | Boundary |
|---|---|---|---|---|---|
| CLI (`humanizer-markers`, `-polish`, `-facts`, `-report`) | yes, with coordinates and classes A/B | strip / --preserve-markup / --typographic modes with preservation invariants | humanizer-facts (fact categories) | --json, exit codes per contract | does not check semantics; no authorship verdicts |
| MCP (`humanizer-mcp`, tool set of contract.v1.json) | same commands over stdio | same modes via humanizer_polish | humanizer_facts | JSON-RPC envelopes, isError per contract | text never leaves the process |
| Pages demo | yes, source-range highlighting in the browser | no (check and report only) | no | report copied from a single result | offline in browser, no install |
| GitHub Action | paste gate + text-path autofix (class A) | action_fix outside fenced/code | no | gate rc | fix never touches protected regions |
| Text skill (SKILL.md) | agent procedures via references | stylistic edits only on explicit request | no | none (skill prose) | no guarantees of naturalness or meaning preservation |

## What it does NOT do

- Rewritten text: paraphrasing hits the theoretical detection ceiling and zeroes out detectors.
- Natively smooth machine text without artifacts: population-level detection only, no per-document verdict.
- Short text: fewer signals than words; watermarks and statistics need length.
- Watermarks without the key: a distortion-free mark is undetectable to a third party by construction.

- The [bib:…] source keys cited in the Russian README are defined in [research/BIBLIOGRAPHY.md](research/BIBLIOGRAPHY.md).
- do not run on Markdown or markup: polish strips ##, **, guillemets, dashes; for markup use --preserve-markup.


## Why you can trust it

- [Methodology and benchmark: numbers with confidence intervals](research/F8-UMBRELLA-2026.md).
- [Public benchmark: table with CIs, reproduction commands and a where-we-are-worse column](demo/benchmark/index.html).
- [Threat model and detector boundaries](docs/THREAT-MODEL.md).
- [Python-JS parity gate for the rules](.github/workflows/regex-check.yml).
- [Self-audit: numbers, statuses, errata](eval/facts/self-audit.v1.json).
- Status of the last successful run and deploy: [status.json on Pages](https://vladimir-human.github.io/humanizer-ru/status.json) (generated by the deploy artifact from the exact SHA; updated only by a green run).

## Installing the skill in browser clients

- The demo needs no install: https://vladimir-human.github.io/humanizer-ru/ — your text never leaves the browser.
- Claude.ai and Claude Code: add the skill from `dsh/skills/humanizer-ru` following the install steps in [docs/USAGE.en.md](docs/USAGE.en.md#install-in-30-seconds).
- Agent clients supporting agentskills.io (opencode, DeepSeek Harness): unpack the text bundle from the release archive.
- A browser extension was declined: a new surface (permissions, store review) does not pay off; idea queue — [research/BACKLOG.md](research/BACKLOG.md).

Directories: [Glama MCP](https://glama.ai/mcp/servers/Vladimir-Human/humanizer-ru) · [skills.sh](https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru).

## Same-name projects

GitHub hosts skills with the same name and different content. Snapshot 2026-09-05
(check: `gh repo view <owner>/humanizer-ru --json stargazerCount`):

- [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) — 284 stars: positioned as "removes neural-network signs", no public numbers registry.
- [smixs/humanizer-ru](https://github.com/smixs/humanizer-ru) — 148 stars: a deterministic linter; the only same-name project included in [LEADERBOARD.md](LEADERBOARD.md) as a candidate (paired run 2026-09-03).
- This project — verifiable chat-paste hygiene: every number comes from deterministic snapshots and the [facts registry](eval/facts/facts.v1.json), boundaries in the [THREAT-MODEL](docs/THREAT-MODEL.md), false positives in the [benchmark](demo/benchmark/index.html).

Arrived by name — choose by the verification method, not by stars.

## Project in numbers

- 58 patterns of machine writing and 40 regex markers (classes A and B).
- Proof records: 38 of 40 markers (registry research/fixtures/marker-sources.json).
- Gates: 156 gates in the full check_all (145 in --quick); fixtures live in tests/fixtures/, docs are checked by check_docs.py, persona in PERSONA.md.

Class breakdown of FP, exploratory, outside the F16 prereg: class A: 0 cases per 12314 non-carrier texts; class B: 8 cases per 12314, that is 0.00065, Wilson 95% CI from 0.0003 to 0.0013; the 40-text control set: 0 flags; heavy domain S4 legal and official, n=381, the volume deficit is recorded in the prereg: 18 cases per 381, that is 0.0472, Wilson 95% CI from 0.0301 to 0.0734; denominators: 12354 full F16 corpus, 12314 validation stratum.

## More

- [What to feed it and how rewriting works](docs/USAGE.en.md#what-to-give-it)
- [Manual install and usage](docs/USAGE.en.md#usage)
- [Architecture and patterns](docs/USAGE.en.md#architecture)
- [Security and version differences](docs/USAGE.en.md#security)
- [Sources](docs/USAGE.en.md#sources)

## Regex markers: classes A and B

Class A — hard copy-paste artifacts: service links and citation marks of
chat interfaces. Class B — contextual indicators: invisible characters,
hidden layout, placeholder fields; a single B match is not enough. Marker
class is `copypaste_artifacts`; retirement is possible only on failure in
its own class; statuses and dates — in `markers.v1.json`.


## Changelog

Full history: [CHANGELOG.md](CHANGELOG.md) and
[GitHub Releases](https://github.com/Vladimir-Human/humanizer-ru/releases).


## License

MIT

## Project status

Dogfooding means the project checks its own texts with its own rules: the style-marker threshold for shipped files is enforced by `scripts/check_own_style.py` (its run prints the current maximum).

[![Версия](https://img.shields.io/github/v/release/Vladimir-Human/humanizer-ru?label=%D0%B2%D0%B5%D1%80%D1%81%D0%B8%D1%8F&color=blue)](https://github.com/Vladimir-Human/humanizer-ru/releases)
[![Skills.sh](https://img.shields.io/badge/skills.sh-%D0%BA%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3-blueviolet)](https://www.skills.sh/vladimir-human/humanizer-ru/humanizer-ru)
[![Догфудинг](https://img.shields.io/badge/%D1%81%D0%B2%D0%BE%D0%B8_%D0%B4%D0%B5%D1%82%D0%B5%D0%BA%D1%82%D0%BE%D1%80%D1%8B-%D0%BE%D1%82%D1%87%D1%91%D1%82-brightgreen)](https://github.com/Vladimir-Human/humanizer-ru/blob/main/eval/facts/self-audit.v1.json)
