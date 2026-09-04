# USAGE - detailed humanizer-ru guide

The short screen and trust section live in README.en.md; details live here.

## What to give it

Give the skill a finished fragment of Russian text. It finds generation
traces and rewrites on request. `SKILL.md` is the agent instruction, loaded
for analysis or editing tasks together with the references from
`references/`. `PERSONA.md` is different: short rules of a live tone for
dialogue, not for text checking.

## Rewriting

On explicit request only. The agent layer strips clichés and never adds
facts for the author — for example, from marketing copy:

**Before:**

> 🚀 **Инновации:** Мы добавили пакетную обработку, горячие клавиши и офлайн-режим. Это безусловно является свидетельством нашего стремления к качеству. Кроме того, эти функции обеспечивают бесшовный, интуитивно понятный и мощный пользовательский опыт — гарантируя эффективность. Эксперты считают, что это революция.

**After:**

> Мы добавили пакетную обработку, горячие клавиши и офлайн-режим.

This is done by the agent layer; the deterministic layer does not mark
such text up: it carries no copy-paste artifacts (markers stay silent),
while the soft-signal counter `humanizer-scan` shows the clichés as an
edit scope, not as a verdict.

## Install in 30 seconds

```sh
npx skills add https://github.com/Vladimir-Human/humanizer-ru --skill humanizer-ru
```

For terminal commands instead of the agent skill, install from PyPI:

```sh
pip install humanizer-ru
```

Upgrade: `pip install --upgrade humanizer-ru`; freshness feed — [releases.atom](https://github.com/Vladimir-Human/humanizer-ru/releases.atom).

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
git clone --branch v3.30.0 --depth 1 https://github.com/Vladimir-Human/humanizer-ru.git ~/.claude/skills/humanizer-ru
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
  Do not run on Markdown or markup: it strips `##`, `**`, guillemets,
  dashes, ellipsis; for markup use `--preserve-markup` (invisibles/NBSP
  only) or `--typographic` (Russian publishing typography: paired straight
  quotes to guillemets, single-character ellipsis; code, fences and
  frontmatter untouched — zero diff on this project's own docs, gate
  `scripts/check_polish_modes.py`).
- `humanizer-detect` — conjunction-frequency detector with a domain status;
  no authorship verdict, graduated response.
- `humanizer-markers` — copy-paste artifact search (classes A and B);
  `--remove` strips invisible marks by risk class: safe automatically,
  ambiguous only with `--include-ambiguous` and a warning, dangerous is
  reported and never removed (table: `references/removal-matrix.md`).
- The project deterministically removes copy-paste traces of chat interfaces
  (contentReference, utm tags, invisible characters) with zero false positives on 40 Class split of false positives, exploratory, outside the F16 prereg: class A: 0 out of 12314 non-carrier texts; class B: 8 out of 12314, i.e. 0.00065, Wilson 95% CI from 0.0003 to 0.0013; control set of 40 texts: 0 flags; heavy domain S4 legal and official, n=381, volume deficit fixed in the prereg: 18 out of 381, i.e. 0.0472, Wilson 95% CI from 0.0301 to 0.0734; denominators: 12354 full F16 corpus, 12314 validation stratum.
  non-carrier control texts (fact registry; number updates after the F16 measurement).
  The market sells this as detector evasion; here evasion is neither promised nor measured: prohibited_uses.
- `humanizer-scan` — soft-signal counter, calibrates the edit scope.
- `humanizer-facts` — fact diff of two text versions (numbers, dates, URLs, names, quotes, negations, modals): lost/added/changed with positions; exit 1 on lost or inverted fact; no authorship or quality verdicts.

All four commands read stdin via `-`. Sample output (markers on a chat
interface line):

```sh
$ echo "Согласно отчёту :contentReference[oaicite:0]{index=0}, рынок вырос." | humanizer-markers --scan -
<stdin>:1 [contentReference] Согласно отчёту :contentReference[oaicite:0]{index=0}, рынок вырос.

Найдено маркеров: 1.
```

Sample output (soft-signal counter, contract envelope; the tool answers
in Russian):

```sh
$ humanizer-scan --json notes.txt
{
  "tool": "humanizer-scan",
  "schema": 1,
  "files": [
    {
      "genre": "neutral",
      "findings": [],
      "categories": {},
      "features_total": 0,
      "categories_total": 0,
      "recommendation": "мягких признаков-кандидатов не найдено; правка не требуется",
      "note": "",
      "file": "notes.txt"
    }
  ]
}
```

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

Prohibited uses (full list in the `prohibited_uses` block of
`contract.v1.json`): submitting work where AI is prohibited (exams,
coursework, professional certification); evading plagiarism or attribution
systems; concealing AI use where disclosure is required; stripping
watermarks from content the user does not own; attributing machine text to
another person. The legitimate area is your own text and honest reporting
without authorship verdicts.

## Sources

- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- [Russian Wikipedia: signs of generated text](https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8%D0%BF%D0%B5%D0%B4%D0%B8%D1%8F%3A%D0%9F%D1%80%D0%B8%D0%B7%D0%BD%D0%B0%D0%BA%D0%B8_%D1%81%D0%B3%D0%B5%D0%BD%D0%B5%D1%80%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D0%B8_%D1%82%D0%B5%D0%BA%D1%81%D1%82%D0%B0)
- [WikiProject AI Cleanup](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_AI_Cleanup)
- `docs/FRAMEWORK.md` — verifiability methodology; `ERRATA.md` — dated retractions.
- The validation corpora (`eval/manifest.v1.json`) contain verbatim
  fragments of public-domain works (Wikisource) and texts written by the
  project in the register of Wikipedia/Wikinews for the corpus; sources
  and per-file licenses: `research/validation/README.md`. Borrowed
  fragments stay under their own licenses; the project MIT covers the
  code and original texts, not third-party inserts.

