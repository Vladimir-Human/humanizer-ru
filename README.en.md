# humanizer-ru

An agent skill for Claude Code, Codex, Cursor and Claude.ai that edits Russian text written by
an AI model. It removes bureaucratese, stock phrases and ChatGPT-style formatting and checks
that numbers, dates, names and hedges stay as they were. The skill speaks Russian and edits
Russian text only.

[Русский](README.md) · [Site with the comparison](https://vladimir-human.github.io/humanizer-ru/)

## Install

```bash
npx skills add Vladimir-Human/humanizer-ru
```

Claude Code plugin:

```text
/plugin marketplace add Vladimir-Human/humanizer-ru
/plugin install humanizer-ru@humanizer-ru
```

Claude.ai: download `humanizer-ru-skill.zip` from the
[latest release](https://github.com/Vladimir-Human/humanizer-ru/releases/latest) and upload it
in Settings → Capabilities → Skills.

## Use

Paste the text and ask «очеловечь». Other requests: «проверь, что выдаёт ИИ, но не правь»
(findings only), «убери только канцелярит» (one layer), «поправь README.md» (prose only, code
and links kept), or give a sample of your own writing to match your style. Good human text,
contracts and laws are left almost untouched.

## Comparison

We compared the notable skills of this kind on Russian texts, blind. One executor (Claude
Sonnet 5.5) applied every skill; Gemini 4 Argon and Kimi K3 ranked the shuffled results by
"which would you send with the least editing". Twelve skills went through a qualifying round on
12 texts; the final used 24 fresh AI texts that no version of this skill had seen.

| Skill | Stars | Mean place of 8 | Ours ranked higher | Texts with a meaning error |
|---|---|---|---|---|
| **humanizer-ru 4.1** | 125 | **3.08** | — | 4 |
| ormeilu/avoid-ai-writing-russian | 18 | 3.43 | 54% | 8 |
| ilyautov/humanizer-ru | 452 | 3.79 | 65% | 3 |
| fsbtactic-code/pishi-normalno | 5 | 4.72 | 72% | 3 |
| one-line prompt, no skill | — | 4.88 | 67% | 7 |
| beaverbeard/chukovsky | 10 | 4.94 | 71% | 10 |
| blader/humanizer | 57,210 | 5.43 | 83% | 14 |
| beaverbeard/slopotron | 64 | 5.72 | 79% | 11 |

stop-slop, no-ai-slop, avoid-ai-writing and five more skills did not pass the qualifying round.
Against avoid-ai-writing-russian the result is close: Gemini puts us first by a clear margin,
Kimi puts them first and us second. Details, every text, answer and judgment: [eval/](eval/).
The judges are models, not human editors.

## AI detectors

The skill edits text for readers. We did not test it against AI detectors and make no promises
about them.

## Version 3

The previous version (research, PyPI package, MCP server) lives in the
[`legacy-v3`](https://github.com/Vladimir-Human/humanizer-ru/tree/legacy-v3) branch and the
`v3.36.4` tag.

## License

MIT
