"""Browser cleanup parity and independent preservation regression vectors.

Node runs the shipped JavaScript; Python supplies the canonical cleaner, not
expected values generated from the JavaScript rules. Explicit examples below
also pin user-visible text independently of either implementation.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
NODE_HARNESS = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
let cleaner;
if (request.browser) {
  const context = vm.createContext({ console });
  context.window = context;
  context.self = context;
  for (const name of ['engine.js', 'cleaner-rules.js', 'cleaner.js']) {
    vm.runInContext(fs.readFileSync(path.join('demo', name), 'utf8'), context,
                    { filename: name });
  }
  cleaner = vm.runInContext('HumanizerCleaner', context);
} else {
  cleaner = require(path.resolve('demo/cleaner.js'));
}
const results = request.texts.map(text => {
  const first = cleaner.cleanText(text);
  const second = cleaner.cleanText(first.text);
  return { first, second };
});
process.stdout.write(JSON.stringify(results));
"""


class DemoCleanerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DEMO.exists() and not (ROOT / ".git").exists():
            raise unittest.SkipTest("demo/ is not included in the sdist")
        for relative in ("demo/cleaner.js", "demo/cleaner-rules.js",
                         "demo/engine.js", "scripts/filemarks/text_layer.py"):
            if not (ROOT / relative).is_file():
                raise AssertionError("Missing browser-cleaner input: " + relative)
        cls.node = shutil.which("node")
        if cls.node is None:
            raise AssertionError("Node.js is required for browser-cleaner regression tests")
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location(
            "demo_cleaner_reference", ROOT / "scripts/filemarks/text_layer.py")
        cls.reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.reference)
        if not cls.reference.DETECTOR_OK or cls.reference._PR is None:
            raise AssertionError("Canonical cleanup dependencies did not load")

    def run_cleaner(self, texts, browser=False):
        proc = subprocess.run(
            [self.node, "-e", NODE_HARNESS], cwd=ROOT,
            input=json.dumps({"texts": texts, "browser": browser}),
            encoding="utf-8", capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        results = json.loads(proc.stdout)
        self.assertEqual(len(results), len(texts))
        return results

    def assert_parity(self, texts):
        results = self.run_cleaner(texts)
        for text, result in zip(texts, results):
            with self.subTest(text=text):
                first, second = result["first"], result["second"]
                expected, counts = self.reference.clean_supported(text)
                repeated, _ = self.reference.clean_supported(expected)
                _, problems = self.reference._protected_report(text, expected)
                self.assertEqual(first["text"], expected)
                self.assertIs(type(first["removed_invisible"]), int)
                self.assertIs(type(first["removed_markup"]), int)
                self.assertEqual(first["removed_invisible"], counts["invisible"])
                self.assertEqual(first["removed_markup"], counts["markup"])
                self.assertIsInstance(first["invariants"], list)
                self.assertTrue(all(isinstance(item, str) and item
                                    for item in first["invariants"]))
                self.assertEqual(bool(first["invariants"]),
                                 bool(problems) or repeated != expected)
                self.assertEqual(second["text"], repeated)
                if repeated == expected:
                    self.assertEqual(second["removed_invisible"], 0)
                    self.assertEqual(second["removed_markup"], 0)
        return results

    def assert_examples(self, pairs):
        results = self.assert_parity([before for before, _ in pairs])
        for (before, expected), result in zip(pairs, results):
            with self.subTest(before=before):
                self.assertEqual(result["first"]["text"], expected)
        return results

    def test_entire_marker_catalogue_positive_negative_and_multi(self):
        vectors = []
        for name, (_pattern, positives, negatives, multi) in (
                self.reference._MARKER_CASES.items()):
            vectors.extend((name + ":positive", value) for value in positives)
            vectors.extend((name + ":negative", value) for value in negatives)
            if multi:
                vectors.append((name + ":multi", multi[0]))
        self.assertGreater(len(vectors), 100, "Catalogue unexpectedly empty or truncated")
        self.assert_parity([text for _name, text in vectors])

    def test_independent_ru_en_text_and_facts(self):
        self.assert_examples([
            ("", ""),
            ("Стоимость 42 EUR; дата 2026-09-12.", "Стоимость 42 EUR; дата 2026-09-12."),
            ("Revenue grew by 12%. turn0search0", "Revenue grew by 12%. "),
            ("По отчёту :contentReference[oaicite:7]{index=2}: 12%.", "По отчёту : 12%."),
            ("Author  spacing stays.\n\n", "Author  spacing stays.\n\n"),
            ("Это е\u0308ж, а не ёж.\t42", "Это е\u0308ж, а не ёж.\t42"),
            ("Alpha \u200b beta; слово\u00adслово", "Alpha beta; словослово"),
        ])

    def test_tracking_parameters_preserve_urls_and_markdown(self):
        self.assert_examples([
            ("[Read](https://example.org/a?utm_source=openai&id=42#part)",
             "[Read](https://example.org/a?id=42#part)"),
            ("https://example.org/a?id=42&utm_source=chatgpt.com#part",
             "https://example.org/a?id=42#part"),
            ("https://example.org/?utm_source=copilot.com&x=1&y=2#end",
             "https://example.org/?x=1&y=2#end"),
            ("https://example.org/?referrer=grok.com#part",
             "https://example.org/#part"),
            ("[Read](https://example.org/?utm_source=openai \"A title\")",
             "[Read](https://example.org/ \"A title\")"),
            ("https://example.org/?utm_source=openair&x=1",
             "https://example.org/?utm_source=openair&x=1"),
            ("https://example.org/?utm_source=chatgpt.com.example#part",
             "https://example.org/?utm_source=chatgpt.com.example#part"),
            ("https://example.org/turn0search0?q=oaicite:3#turn1search1",
             "https://example.org/turn0search0?q=oaicite:3#turn1search1"),
        ])

    def test_code_runs_closed_fences_and_frontmatter(self):
        self.assert_examples([
            ("`turn0search0` and turn1search1", "`turn0search0` and "),
            ("``a ` turn0search0`` turn1search1", "``a ` turn0search0`` "),
            ("`unclosed turn0search0", "`unclosed turn0search0"),
            ("```text\nturn0search0\n```\nturn1search1", "```text\nturn0search0\n```\n"),
            ("~~~text\nturn0search0\n~~~~\nturn1search1", "~~~text\nturn0search0\n~~~~\n"),
            ("---\ntitle: turn0search0\n---\nturn1search1", "---\ntitle: turn0search0\n---\n"),
            ("`https://example.org/?utm_source=openai`",
             "`https://example.org/?utm_source=openai`"),
        ])

    def test_unicode_emoji_flags_and_astral_offsets(self):
        flag = "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f"
        self.assert_examples([
            ("👩‍💻 👨‍👩‍👧‍👦 ❤️", "👩‍💻 👨‍👩‍👧‍👦 ❤️"),
            (flag + " A\U000e0061B", flag + " AB"),
            ("😀 turn0search0 русский", "😀  русский"),
            ("😀`turn0search0`😀turn1search1", "😀`turn0search0`😀"),
            ("A\U000e0061\U000e0062B", "AB"),
            ("а\u200dб", "аб"),
        ])

    def test_crlf_tabs_and_other_line_separators(self):
        self.assert_examples([
            ("A\r\nturn0search0\r\nB\r\n", "A\r\n\r\nB\r\n"),
            ("```\r\nturn0search0\r\n```\r\nturn1search1", "```\r\nturn0search0\r\n```\r\n"),
            ("A\tturn0search0\u2028B\u2029C", "A\t\u2028B\u2029C"),
            ("A\rturn0search0\vB\fC", "A\r\vB\fC"),
        ])

    def test_nested_markers_and_sources_reach_fixed_point(self):
        self.assert_examples([
            ("turn0sea\u200brch0", ""),
            ("turn0seaturn1search1rch0", ""),
            ("Reuters+3BBC+2 reports 42.", "ReutersBBC reports 42."),
            ("Excel+1С remains.", "Excel+1С remains."),
        ])

    def test_unicode_regex_digits_words_and_whitespace(self):
        self.assert_examples([
            ("turn١search٢", ""),
            (":::письмо{subject=\"Тема\"}Текст", "Текст"),
            ("A+١B+٢ reports 42.", "AB reports 42."),
        ])
        texts = []
        for separator in ("\x1c", "\x1d", "\x1e", "\x1f", "\x85", "\xa0", "\ufeff"):
            texts.extend([
                "https://example.org/?utm_source=openai" + separator + "keep=42",
                "https://example.org/a" + separator + "turn0search0",
                "ppl-ai-file-upload/object" + separator + "keep=42",
            ])
        self.assert_parity(texts)

    def test_combined_payloads_in_different_protected_contexts(self):
        payloads = ["turn0search0", "oaicite:12", "a\u200bb", "👩‍💻turn0search0",
                    "https://example.org/?utm_source=openai&n=7#end",
                    "<think>reason</think>"]
        wrappers = ["{}", "`{}`", "``a `{}` z``", "```\n{}\n```",
                    "~~~\n{}\n~~~", "---\ntitle: {}\n---\nBody",
                    '<span title="{}">Body</span>', "[Read]({})"]
        self.assert_parity([wrapper.format(payload) + "\nEnd turn1search1"
                            for payload in payloads for wrapper in wrappers])

    def test_unsafe_html_candidates_report_invariants(self):
        texts = [
            '<a title="turn0search0">Read</a>',
            '<a title="a > turn0search0">Read</a>',
            '<a\n title="turn0search0">Read</a>',
            '<a title="turn0search0\nRead',
            '<think>private reasoning</think>Answer',
            '<thinking>line one\nline two</thinking>Answer',
            '<!-- turn0search0 -->',
            '<a href="https://example.org/?utm_source=openai">Read</a>',
        ]
        for result in self.assert_parity(texts):
            self.assertTrue(result["first"]["invariants"])

    def test_invisible_changes_in_protected_content_are_blocked(self):
        texts = ["`a\u200bb`", "```\na\u200bb\n```",
                 "---\ntitle: a\u200bb\n---\nBody",
                 '<span title="a\u200bb">Body</span>']
        for result in self.assert_parity(texts):
            self.assertTrue(result["first"]["invariants"])

    def test_round_limit_cannot_claim_idempotency(self):
        text = "turn0search0"
        for _ in range(12):
            text = "turn0sea" + text + "rch0"
        result = self.assert_parity([text])[0]
        self.assertNotEqual(result["first"]["text"], result["second"]["text"])
        self.assertTrue(result["first"]["invariants"])

    def test_unsupported_markers_remain_visible(self):
        self.assert_examples([
            ("[Download](sandbox:/mnt/data/report.pdf)", "[Download](sandbox:/mnt/data/report.pdf)"),
            ('<ref name="0search12">source</ref>', '<ref name="0search12">source</ref>'),
            ("https://example.com and YYYY-MM-DD", "https://example.com and YYYY-MM-DD"),
        ])

    def test_literal_html_stays_text_in_core(self):
        payload = '<img src=x onerror="throw new Error(42)"><script>throw 43</script>'
        self.assert_examples([(payload + " turn0search0", payload + " ")])

    def test_browser_global_matches_commonjs(self):
        texts = ["Привет\u200b, world turn0search0", "👩‍💻 `turn0search0`",
                 "[Read](https://example.org/?utm_source=openai&n=7#end)"]
        self.assertEqual(self.run_cleaner(texts, browser=True), self.run_cleaner(texts))

    def test_generated_rules_match_canonical_source(self):
        saved_path = sys.path[:]
        try:
            sys.path.insert(0, str(DEMO))
            spec = importlib.util.spec_from_file_location(
                "demo_cleaner_generator", DEMO / "generate_cleaner_rules.py")
            generator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(generator)
            expected = generator.build_js()
        finally:
            sys.path[:] = saved_path
        actual = (DEMO / "cleaner-rules.js").read_bytes().decode("utf-8")
        self.assertEqual(actual, expected,
                         "Regenerate with python demo/generate_cleaner_rules.py")

    def test_missing_or_incompatible_rules_do_not_expose_cleaner(self):
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('demo/cleaner.js', 'utf8');
const valid = require('./demo/cleaner-rules.js');
const mutations = [
  rules => undefined,
  rules => ({...rules, schema_version: -1}),
  rules => ({...rules, layer_a: undefined}),
  rules => ({...rules, markup: []}),
  rules => ({...rules, utm: []}),
  rules => ({...rules, rounds: 0}),
  rules => ({...rules, layer_a: {...rules.layer_a, flags: 'g'}}),
  rules => ({...rules, markup: rules.markup.map(r => ({...r, protect_urls: undefined}))}),
];
const results = mutations.map(mutate => {
  const context = vm.createContext({
    HUMANIZER_CLEANER_RULES: mutate(JSON.parse(JSON.stringify(valid))),
  });
  let error = '';
  try { vm.runInContext(source, context); } catch (e) { error = e.message; }
  return {error, exposed: typeof context.HumanizerCleaner !== 'undefined'};
});
process.stdout.write(JSON.stringify(results));
"""
        proc = subprocess.run([self.node, "-e", script], cwd=ROOT,
                              encoding="utf-8", capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        results = json.loads(proc.stdout)
        self.assertEqual(len(results), 8)
        for index, result in enumerate(results):
            with self.subTest(mutation=index):
                self.assertTrue(result["error"])
                self.assertFalse(result["exposed"])


if __name__ == "__main__":
    unittest.main()
