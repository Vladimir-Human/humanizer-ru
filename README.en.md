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

We compare skills of this kind on Russian texts, blind. One executor (Claude Sonnet 5.5)
applies every skill; three judges from other labs (Gemini 4 Argon, Kimi K3, Muse Spark 1.3)
rank the shuffled results by "which would you send with the least editing" and list meaning
errors. Each judge has one vote; an error counts when two of three judges flag it. The
thresholds were written down before the texts existed.

Latest run, 4.1.1: 24 fresh AI texts from eleven models that the skill had never seen, plus
six human "trap" texts.

| Participant | Stars | Mean place of 5 | Ours ranked higher | Texts with a meaning error, of 24 |
|---|---|---|---|---|
| **humanizer-ru 4.1.1** | 125 | **2.38** | — | 2 |
| ilyautov/humanizer-ru | 452 | 3.10 | 65% | 2 |
| ormeilu/avoid-ai-writing-russian | 18 | 3.18 | 69% | 9 |
| one-line prompt, no skill | — | 3.74 | 77% | 8 |

The fifth participant was a new variant of our instructions from three tuning cycles. It did
not beat the previous instructions (49% of comparisons, same number of errors), so 4.1.1 does
not ship it. Gemini and Kimi rank humanizer-ru above both rivals; Muse Spark ranks it above
avoid-ai-writing-russian and level with ilyautov. The skill left all six trap texts intact;
the one-line prompt damaged three.

The 4.1.0 run had eight participants: blader/humanizer (57k stars) came seventh with the most
errors; stop-slop, no-ai-slop and avoid-ai-writing did not pass the qualifying round. Every
text, answer and judgment: [eval/](eval/). The judges are models, not human editors.

## AI detectors

The skill edits text for readers. We did not test it against AI detectors and make no promises
about them.

## Version 3

The previous version (research, PyPI package, MCP server) lives in the
[`legacy-v3`](https://github.com/Vladimir-Human/humanizer-ru/tree/legacy-v3) branch and the
`v3.36.4` tag.

## License

MIT
