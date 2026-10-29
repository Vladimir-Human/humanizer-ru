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

| Participant | Stars on 2026-10-28 | Mean place of 5 | Ours ranked higher | Texts with a meaning error, of 24 |
|---|---|---|---|---|
| **humanizer-ru 4.1.1** | 134 | **2.38** | — | 2 |
| ilyautov/humanizer-ru | 493 | 3.10 | 65% | 2 |
| ormeilu/avoid-ai-writing-russian | 23 | 3.18 | 69% | 9 |
| one-line prompt, no skill | — | 3.74 | 77% | 8 |

The fifth participant was a new variant of our instructions from three tuning cycles. It did
not beat the previous instructions (49% of comparisons, same number of errors), so 4.1.1 does
not ship it. Gemini and Kimi rank humanizer-ru above both rivals; Muse Spark ranks it above
avoid-ai-writing-russian and level with ilyautov. The skill left all six trap texts intact;
the one-line prompt damaged three.

A fresh reduced run on 21.10.2026 (`final4`): 12 new texts by GPT-6.1 Sol and Gemini 4 Argon,
Sonnet 5.5 as the executor, places by Gemini 4 Argon and Claude Opus 5.5. humanizer-ru 4.1.1 came
first of three, above ilyautov/humanizer-ru v3.32.0 in 83% of comparisons; no judge found a meaning
error in anyone's edits. A variant with more Wikipedia markers lost to 4.1.1 (42%) and was not shipped.

The 4.1.0 run had eight participants: blader/humanizer (57k stars) came seventh with the most
errors; stop-slop, no-ai-slop and avoid-ai-writing did not pass the qualifying round. Every
text, answer and judgment: [eval/](https://github.com/Vladimir-Human/humanizer-ru/tree/main/eval/). The judges are models, not human editors.

## Scripts

The skill folder has two helper scripts, standard library only. An agent with a terminal runs
them itself; you can run them by hand:

```bash
python skills/humanizer-ru/scripts/check_facts.py before.txt after.txt
python skills/humanizer-ru/scripts/clean_paste.py text.txt --in-place
```

`check_facts.py` compares the original with the edit and reports lost or new numbers, dates,
names and links, flipped negations, swapped amounts, weakened or strengthened claims and lost
HTML tags. `clean_paste.py` removes chat-paste leftovers: contentReference, 【N†source】,
`utm_source=chatgpt.com` tails, invisible characters. The scripts work only on the files they
are given (`clean_paste.py` rewrites a file only with `--in-place`), do not use the network and
do not start other programs.

## AI detectors

The skill edits text for readers. We did not test it against AI detectors and make no promises
about them. What is known about them (checked 2026-10-21):

- Results depend on the detector version. Since 2026-09-25 Antiplagiat prints the model version
  in its report to explain why two checks of one text differ
  ([news](https://antiplagiat.ru/news/kakya-model-ii-detectora-poteryala-tekst/)).
- Detectors err on short texts and on bureaucratic prose: Text.ru's help names texts under
  1,000 characters and texts full of officialese or clichés ([Text.ru](https://text.ru/neuro/detector)).
- Detectors trained on Russian text are almost error-free on their own corpus: in LLMTrace,
  fine-tuned models reach F1 0.97–0.99 on Russian, the zero-shot Binoculars 0.02
  ([arXiv 2509.21269](https://arxiv.org/abs/2509.21269)).
- Russian Wikipedia advises against trusting detectors and notes that AI-like features do not
  prove authorship ([ВП:ПРГЕН](https://ru.wikipedia.org/wiki/Википедия:Признаки_сгенерированности_текста)).

## Version 3

The previous version (research, PyPI package, MCP server) lives in the
[`legacy-v3`](https://github.com/Vladimir-Human/humanizer-ru/tree/legacy-v3) branch and the
`v3.36.4` tag.

## License

MIT
