# humanizer-ru

An agent skill that rewrites AI-written **Russian** text so it can be sent as is: no
bureaucratese, stock phrases, empty openers, "not just X but Y", template bold and emoji,
or chat paste leftovers. Numbers, dates, names, conditions and negations stay in place and
are checked.

Works in Claude Code, Codex, Cursor, Claude.ai and other agents that support
[Agent Skills](https://agentskills.io). The skill itself speaks Russian and edits Russian
text only.

[Русский](README.md)

## Install

```bash
npx skills add Vladimir-Human/humanizer-ru
```

Claude Code plugin:

```text
/plugin marketplace add Vladimir-Human/humanizer-ru
/plugin install humanizer-ru@humanizer-ru
```

Claude.ai: download `humanizer-ru-skill.zip` from
[Releases](https://github.com/Vladimir-Human/humanizer-ru/releases/latest) and upload it in
Settings → Capabilities → Skills.

## Use

- «Очеловечь этот текст: …» — returns the rewritten text and 1–3 notes.
- «Проверь, что выдаёт ИИ, но не правь» — up to 10 findings, no edits.
- «Убери только канцелярит» — edits one layer only.
- «Поправь README.md» — edits prose, keeps code, commands and links.

Good human text, contracts and laws are left almost untouched.

## Does it help

Blind comparison on 36 Russian texts (24 written by 11 models, 6 saved chatbot answers,
6 human or legal texts). One executor (Claude Sonnet 5.5) applied every skill; two judges
from other labs (Gemini 4 Argon, GPT-6.1 Sol) ranked shuffled variants four times per text
by "which would you send with the least editing".

On 30 AI texts humanizer-ru 4.0 had the best mean place (2.02 of 6) and ranked above
ilyautov/humanizer-ru in 66% of judgments, blader/humanizer in 81%, a one-line prompt in
82%. It also left human and legal texts almost intact (best place, 1.75). Weak spot: judges
flagged meaning shifts in 5 of 30 texts (ilyautov: 1) — none in numbers, dates, names or
negations; all in degree of certainty ("may need" became "will need"). Details and all
outputs: [eval/](eval/).

The skill does not promise to fool AI detectors.

## Version 3

The previous version (research, 156 checks, PyPI package, MCP server) lives in the
[`legacy-v3`](https://github.com/Vladimir-Human/humanizer-ru/tree/legacy-v3) branch and the
`v3.36.4` tag.

MIT license.
