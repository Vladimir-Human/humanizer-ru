# humanizer-ru

An agent skill for Claude Code, Codex, Cursor, Gemini CLI and Claude.ai: turns stiff,
machine-sounding Russian prose into live, natural Russian, verifies numbers, currencies, dates,
citations (`[14, с. 52]`) and item/person bindings via `check_facts.py`, and lowers trigger risk in
Antiplagiat and AI detectors while curing homoglyphs and hidden watermarks.

[Русский](README.md) · [Site](https://vladimir-human.github.io/humanizer-ru/) · [Style check](https://vladimir-human.github.io/humanizer-ru/check/) · [Fact check](https://vladimir-human.github.io/humanizer-ru/sverka/) · [Chat prompt](prompt/chat.md)

## Install

Any agent supporting [Agent Skills](https://agentskills.io) — Claude Code, Codex, Cursor, Gemini CLI
and others:

```bash
npx skills add Vladimir-Human/humanizer-ru
```

Claude Code plugin (receives updates through `/plugin`):

```text
/plugin marketplace add Vladimir-Human/humanizer-ru
/plugin install humanizer-ru@humanizer-ru
```

For Claude's plugin directory the package is built under `humanizer-russian`; the skill itself is
named `humanizer-ru` everywhere.

Gemini CLI extension:

```bash
gemini extensions install https://github.com/Vladimir-Human/humanizer-ru
```

Cursor also loads the repository directly from its local plugin folder via `.cursor-plugin/plugin.json`:

```bash
git clone https://github.com/Vladimir-Human/humanizer-ru ~/.cursor/plugins/local/humanizer-ru
```

Claude.ai: download `humanizer-ru-skill.zip` from the
[latest release](https://github.com/Vladimir-Human/humanizer-ru/releases/latest) and upload it
in Settings → Capabilities → Skills.

## Without installing

- [Style and text-hygiene check in the browser](https://vladimir-human.github.io/humanizer-ru/check/) —
  highlights stock phrases, monotonous sentence and paragraph rhythm, genitive nominalization chains,
  invisible characters and Latin or Greek lookalike letters inside Cyrillic words that trip
  Antiplagiat's «Подозрительный документ» flag. One click strips chat paste garbage, repairs
  homoglyphs and hands the source over to the fact-check page. Runs offline; nothing leaves the tab.
- [Fact check in the browser](https://vladimir-human.github.io/humanizer-ru/sverka/) — compares the
  source and any model's edit with the exact logic of `check_facts.py`. Missing, swapped or added
  numbers, currencies, dates, names, citations and hedges appear right away, with a one-click handoff
  back to the style check.
- [Chat prompt](prompt/chat.md) — a compressed version of the skill under 4,000 characters for chat
  interfaces that cannot load skills (system prompt or project instructions in GigaChat, YandexGPT,
  DeepSeek, ChatGPT and Claude).

## Use

Paste a Russian text and ask «очеловечь». Other modes:

- «проверь, что выдаёт ИИ, но не правь» — findings only, text untouched;
- «подготовь главу ВКР / статью к Антиплагиату и детектору ИИ» — clause restructuring and technical
  cleanup while preserving academic register, terms and `[14, с. 52]` references;
- «убери только канцелярит» (or dashes only, bold only) — single-layer edit;
- «поправь README.md» — edits prose while leaving code, commands and links intact;
- paste a sample of your own writing + request — matches your sentence cadence, punctuation and tone.

Well-written human prose, contracts and statutes are left almost untouched. Genre rules — from posts,
product cards and job listings to theses and research papers — live in
[references/genres.md](skills/humanizer-ru/references/genres.md).

## Comparison with other skills

Over twenty GitHub skills target the same problem. We evaluate them blind on unseen Russian texts:
one executor applies every skill, and judges from independent labs rank shuffled outputs by "which
would you send with the least editing" while listing meaning errors. Each judge has one vote; a
meaning error counts when a majority of judges flag it. Acceptance gates are fixed before generating
the evaluation texts.

### 4.3.0 benchmark (November 2026)

Blind terminal comparison on 12 fresh AI texts and 2 human/legal traps. Executor: Claude Sonnet 4.6;
three flagship judges from separate labs — Claude Opus 4.6 Thinking, Gemini 4 Argon High and OpenAI
GPT-6.2 Astra Thinking — with two independent shuffles per judge (84 passes). Alongside it, 64
deterministic probes test all 16 instruction rules.

| Participant | Mean rank (3 flagship judges: Opus 4.6, Argon 4, GPT-6.2 Astra) | 1st places of 72 | Real fact losses (`check_facts`) | Style score (`8.83` raw) | 64 rule probes |
|---|---|---|---|---|---|
| **humanizer-ru 4.3.0** | **2.22** (#1) | **29** | **0** | **1.22** (−86%) | **124 / 128** (96.9%) |
| [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) | 2.26 | 21 | 1 | 4.31 | 48 / 64 (75.0%) |
| humanizer-ru 4.2.1 | 2.40 | 20 | 2 | 3.61 | 117 / 128 (91.4%) |
| one-line prompt | 3.11 | 2 | 1 | 3.50 | 87 / 128 (68.0%) |

- Blind ranking and meaning preservation. Version 4.3.0 ranks above the one-line prompt in 64% of
  comparisons (95% CI 44–81%, agreed wins 4:1), above 4.2.1 in 60% (44–75%, 2:1) and above
  lighter-touch `ilyautov/humanizer-ru` in 54% (36–74%, 3:1; `ilyautov` leaves source similarity at
  0.81 vs 0.53 for 4.3.0). With free GPT-6.1 Sol in the third judge slot 4.3.0 takes 26 of 72 first
  places, and across all four judges combined — 39 of 96. Majority meaning-error flags dropped from
  7 on 4.2.1 and 11 on the one-line prompt to 3 of 12: the strict ≤1/12 ceiling was missed because
  Argon and the OpenAI judges counted nominalization and subheading compression as losses on three
  texts where Opus flagged 0 and `check_facts.py` confirmed 0 real fact losses. On both traps
  (contract clause and footnoted classic prose) 4.3.0 ranked #1 with 0 errors, and the
  «Сверка скриптом: …» receipt appeared in 12 of 12 answers, matching the script in 10 of 12.
  Reports: [summary-3flagship.md](eval/results/holdout5-2026-11-17/summary-3flagship.md),
  [summary.md](eval/results/holdout5-2026-11-17/summary.md),
  [summary-4judge.md](eval/results/holdout5-2026-11-17/summary-4judge.md),
  [frontier.md](eval/results/holdout5-2026-11-17/frontier.md) and
  [receipt.md](eval/results/holdout5-2026-11-17/receipt.md) (in Russian).
- 64 rule probes and rival audit. Across two tool-less passes on `MiniMax M3.1 Flash` (`--bare`),
  the skill passed 124 of 128 with 0 fact errors, hitting 8/8 on 13 of 16 rules. The portable
  [prompt/chat.md](prompt/chat.md) passed 110 of 128 with 8/8 prompt-injection resistance. On the
  same 64 probes `ilyautov/humanizer-ru` scored 48 of 64 (0/4 on grammatical dashes and author
  interview) and [avoid-ai-writing-russian](https://github.com/ormeilu/avoid-ai-writing-russian)
  v2.10.0 scored 49 of 64 with 5 fact-oracle failures. Reports:
  [probes.md](eval/results/probes-430-2026-11-17/probes.md) and
  [rivals-430/summary.md](eval/results/rivals-430-2026-11-17/summary.md).
- Human controls. Across 39 human texts and 6 traps, mean similarity to the original is 0.87, rising
  to 0.98 on the 6 traps. All 6 traps passed with 0 fact errors — keeping Herzen's footnote numbers
  `23`, `(27)` and `24` intact — and only 1 text of 45 had a fact-check error vs 4 in 4.2.0 and 6 in
  4.1.7. Report: [m2-human-430/summary.md](eval/results/m2-human-430-2026-11-17/summary.md).
- Style shift without a terminal. On 24 short texts across two executors (`MiniMax` and `Sol`, 144
  answers) and 36 `holdout4` texts, the one-line prompt increases em-dashes by 8–18% and leaves
  chatbot chatter inside the output, whereas `humanizer-ru` cuts mean style-linter scores by 79–90%
  (`2.51 → 0.53` and `0.26`) with 0 fact errors. Report:
  [leap-style/summary.md](eval/results/leap-style-2026-11-13/summary.md).

### 4.2.0 benchmark (November 2026)

Deterministic suite run on 2026-11-09–10 at $0 API cost, testing mandatory script receipts, rule
probes and restraint on human prose. Full log: [eval/README.md](eval/README.md) (in Russian).

- Terminal run (Claude Sonnet 5.5 subagents on 12 new AI texts): the skill ran `check_facts.py` and
  appended «Сверка скриптом: …» in 12 of 12 answers, matching script counts in all 12. All systems
  kept the facts; the one-line prompt left a ChatGPT `utm_source` tracking tail in one text.
- 60 probes over 15 rules (`MiniMax M3.1 Flash`, two runs): 4.2.0 passed 109 of 120 vs 108 for 4.1.7
  and 79 for the one-line prompt. On "make it livelier" template requests, 4.2.0 edited without
  inventing details and asked clarifying questions in 12 of 12 cases (4.1.7 asked in 0).
- 39 human texts: source similarity reached 0.87 vs 0.85 for 4.1.7, with fact-check flags on 3 texts
  vs 6; the Herzen footnote drop seen in 4.2.0 is fixed in 4.3.0. Automatic voice-profile matching
  missed its gate (7 of 12 vs 10 required) and was excluded.

### 4.1.1 and 4.1.0 benchmarks

Blind run 4.1.1 evaluated 24 unseen AI texts from eleven models and 6 human traps with Claude
Sonnet 5.5 as executor and Gemini 4 Argon, Kimi K3 and Muse Spark 1.3 as judges. Star counts below
are updated as of 2026-11-17.

| Participant | Stars on 2026-11-17 | Mean rank of 5 | Ours ranked higher (95% CI) | Texts with a meaning error, of 24 |
|---|---|---|---|---|
| **humanizer-ru 4.1.1** | 152 | **2.38** | — | 2 |
| [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) | 581 | 3.10 | 65% (52–78%) | 2 |
| [avoid-ai-writing-russian](https://github.com/ormeilu/avoid-ai-writing-russian) | 42 | 3.18 | 69% (58–81%) | 9 |
| one-line prompt | — | 3.74 | 77% (67–85%) | 8 |

All three leads clear 50% under paired text bootstrap (`report.py`). The skill left all 6 traps
intact while the one-line prompt damaged 3. In the follow-up `final4` run on 12 texts from GPT-6.1
Sol and Gemini 4 Argon, 4.1.1 placed first again and beat `ilyautov/humanizer-ru` in 83% of
comparisons with zero meaning errors.

The initial 4.1.0 screening tested eight skills: English-centric `blader/humanizer` (70k stars on
2026-11-17) placed seventh with the most errors, while `stop-slop`, `no-ai-slop` and
`avoid-ai-writing` failed qualification. Every text, output, judgment and reproduction script lives
in [eval/](eval/). All judges are language models, not human editors.

## Scripts

Three zero-dependency Python 3.8+ standard-library scripts ship inside the skill folder. Terminal
agents invoke them automatically; you can also run them directly:

```bash
python skills/humanizer-ru/scripts/check_facts.py before.txt after.txt
python skills/humanizer-ru/scripts/clean_paste.py text.txt --in-place
python skills/humanizer-ru/scripts/lint_style.py text.txt
```

- `check_facts.py` compares source and edit to flag missing or added numbers, currencies, dates,
  names, `[14, с. 52]` literature citations and URLs, flipped negations, amounts swapped across
  people, products or tariffs, shifted hedges and dropped HTML tags. It ends with the
  «Сверка скриптом: …» receipt copied verbatim into the skill's notes. Values removed with chatbot
  wrapper lines around the text are listed separately rather than counted as errors.
- `clean_paste.py` strips chat-paste leftovers (`contentReference`, `citeturn…`, `[cite: N]`,
  `[citation:N]`, `[span_N]`, `[^N^]`, `【N†source】`), assistant `utm_source` tails, invisible
  characters and non-emoji variation selectors, turns space spoofers like Braille Blank `U+2800` into
  plain spaces without gluing words, and repairs Latin and Greek lookalike letters inside Russian
  words. Code, URLs, emails, author `utm_campaign` tags, `U+0301` stress marks and pre-1918 Cyrillic
  (`ѣ`, `і`) stay untouched. With `--in-place`, it saves a `.bak` backup before writing.
- `lint_style.py` detects stock phrases and measures dash, bold, emoji and heading density, sentence
  and paragraph cadence (`sentence_cv`, `paragraph_cv`), nominalization-to-verb ratio and genitive
  chains (`nom_to_verb`, `nominal_chain`), invisible characters (`invisible`) and mixed-script words
  (`mixed_script`). Quotes and code blocks are skipped; `--json` outputs structured data. Rules are
  shared with `/check/` via `scripts/rules.json`.

All three scripts read only the files passed to them, make no network calls and spawn no subprocesses.

## Data and privacy

The plugin has no MCP servers, background hooks or network requests, and stores no user data. Text
you paste is handled solely by your agent like any normal chat message. Terminal agents write the
source and draft to temporary files outside your project, run the check and delete them right away.

## Troubleshooting

- Skill does not trigger: start your message with «очеловечь» or name `humanizer-ru` explicitly.
- `python` not found: on Windows try `py`; without Python the skill still works and checks facts by
  hand against its anchor list.
- False positive in `check_facts.py`: please open an issue with a minimal pair in
  [Issues](https://github.com/Vladimir-Human/humanizer-ru/issues).
- Claude.ai rejects upload: upload `humanizer-ru-skill.zip` from the release as-is without unpacking.

## AI detectors and Antiplagiat

Full skill reference: [references/detectors.md](skills/humanizer-ru/references/detectors.md) (in Russian).

Russian academic and enterprise platforms such as «Антиплагиат.ВУЗ» run four separate modules:
shingle overlap, semantic paraphrase matching, probabilistic AI detection («Сгенерированный текст» on
DOCX and PDF files from 2 pages without OCR; since 2026-09-25 reports print the detector model
version — [announcement](https://antiplagiat.ru/news/kakya-model-ii-detectora-poteryala-tekst/)) and
technical tamper detection («Подозрительный документ»).

### Why technical "bypassers" backfire

Swapping Cyrillic letters for Latin or Greek homoglyphs, inserting zero-width characters or `U+2800`
Braille blanks, or running dictionary synonymizers leaves clause-level rhythm intact for neural
detectors such as GigaCheck ([arXiv 2410.23728](https://arxiv.org/abs/2410.23728)) and fine-tuned
classifiers in LLMTrace ([arXiv 2509.21269](https://arxiv.org/abs/2509.21269)), while immediately
triggering the red «Подозрительный документ» flag. Commercial automated "humanizers" carry a second
hazard: a November 2026 audit of 11 services ([arXiv 2611.00359](https://arxiv.org/abs/2611.00359))
found that all 11 corrupted checkable numbers, dates, names or quotes in 35–65% of documents. That is
why `humanizer-ru` pairs editing with deterministic `check_facts.py` and `/sverka/`, while
`clean_paste.py` and `/check/` strip hidden characters and repair homoglyphs.

### What actually lowers trigger probability

Detectors primarily lock onto RLHF scaffolding and symmetrical formatting
([arXiv 2605.19516](https://arxiv.org/abs/2605.19516)). Detector robustness benchmarks
([RAID, arXiv 2405.07940](https://arxiv.org/abs/2405.07940);
[Adversarial Paraphrasing, arXiv 2506.07001](https://arxiv.org/abs/2506.07001)) and measurements on
our Russian corpus show the strongest drop comes from clause-level restructuring. Russian LLM prose
uses nearly twice as many `-ение/-ание/-ость` verbal nouns per finite verb as human writing, so the
skill unpacks nominalization cascades into active verbs, varies sentence and paragraph length, and
cuts framing filler in introductions and conclusions. Already natural human paragraphs are left alone
to avoid a uniform auto-paraphraser fingerprint ([DAMAGE, arXiv 2501.03437](https://arxiv.org/abs/2501.03437);
[NeurIPS 2026, arXiv 2606.25152](https://arxiv.org/abs/2606.25152)). Verbatim quotes, `[14, с. 52]`
citations and author AI-disclosure notes (GOST R 70949-2023, GOST R 71657-2024) stay untouched.

### Honest boundary, no guarantees

No editor can promise a 100% pass across closed detectors. Outcomes depend on model version, passage
length and genre stiffness: short excerpts and dry legal or textbook prose produce false positives on
human writing as well, as documented by [Text.ru](https://text.ru/neuro/detector) and Russian
Wikipedia's [ВП:ПРГЕН](https://ru.wikipedia.org/wiki/Википедия:Признаки_сгенерированности_текста).
Perturbation-invariant classifiers such as [PIFE, arXiv 2510.02319](https://arxiv.org/abs/2510.02319)
and statistical sampling watermarks also cannot always be removed by prose editing. The skill
evaluates style and technical hygiene only and never issues authorship verdicts.

## Version 3

The earlier PyPI package and MCP server live on the
[`legacy-v3`](https://github.com/Vladimir-Human/humanizer-ru/tree/legacy-v3) branch and `v3.36.4`
tag: `pip install humanizer-ru` installs the v3 server, not the agent skill.

## License

MIT
