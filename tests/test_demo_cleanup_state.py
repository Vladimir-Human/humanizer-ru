"""Regression tests for cleanup candidate and undo state invalidation."""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "demo" / "index.html"


def _inline_app():
    source = PAGE.read_text(encoding="utf-8")
    match = re.search(r"<script>\s*(\(\(\) => \{.*?\n\}\)\(\);)\s*</script>",
                      source, re.S)
    if not match:
        raise AssertionError("demo inline application script was not found")
    return match.group(1)


NODE_HARNESS = r"""
const vm = require('vm');
const app = __APP__;
const elements = new Map();
function element(id) {
  const handlers = Object.create(null);
  const e = {
    id, value: '', checked: id === 'showAll',
    hidden: ['applyCleanup', 'undoCleanup', 'copyCleaned', 'cleanupPreview'].includes(id), dataset: {},
    innerHTML: '', textContent: '', returnValue: '',
    addEventListener(type, fn) { (handlers[type] ||= []).push(fn); },
    emit(type, event = {}) { for (const fn of (handlers[type] || [])) fn(event); },
    focus() {}, showModal() {}, appendChild() {},
  };
  elements.set(id, e); return e;
}
for (const id of ['text', 'matches', 'preview', 'summary', 'onlyA', 'showAll',
  'run', 'insertSample', 'ownText', 'copyReport', 'copyStatus', 'shareBtn',
  'counts', 'scanState', 'shareDialog', 'previewSection', 'cleanupPreview',
  'applyCleanup', 'undoCleanup', 'copyCleaned', 'cleanupSummary', 'cleanupDiff'])
  element(id);
const documentHandlers = Object.create(null);
const document = {
  getElementById(id) { return elements.get(id) || element(id); },
  createElement() { return { className: '', innerHTML: '', appendChild() {} }; },
  addEventListener(type, fn) { (documentHandlers[type] ||= []).push(fn); },
};
const location = { pathname: '/', search: '', hash: '' };
const history = { replaceState(_a, _b, url) { location.hash = String(url).includes('#') ? '#' : ''; } };
let mode = 'first';
const cleaner = {
  cleanText(text) {
    if (mode === 'throw') throw new Error('cleaner unavailable');
    const cleaned = text.replace('turn0search0', '');
    return { text: cleaned, invariants: mode === 'blocked' ? ['facts changed'] : [] };
  },
};
const context = {
  document, location, history, navigator: {}, HUMANIZER_MARKERS: {
    rules: [{ id: 'x', class: 'A', description: 'x', flags: '' }]
  },
  HumanizerEngine: { scanText() { return []; } }, HumanizerCleaner: cleaner,
  HUMANIZER_SAMPLE: 'sample turn0search0', TextEncoder, encodeURIComponent,
  decodeURIComponent, setTimeout() { return 1; }, clearTimeout() {}, console, JSON, Object, String,
  Array, RegExp, Error,
};
vm.runInNewContext(app, context, { filename: 'demo/index.html' });
const text = elements.get('text');
const run = elements.get('run');
const apply = elements.get('applyCleanup');
const undo = elements.get('undoCleanup');
const copy = elements.get('copyCleaned');
function scan(value) { text.value = value; run.emit('click'); }
scan('first turn0search0');
const candidate = { cleaned: apply.dataset.cleaned, source: apply.dataset.source,
  visible: !apply.hidden };
text.value = 'second turn0search0';
apply.emit('click');
const staleApplyRejected = { text: text.value, undoVisible: !undo.hidden };
scan('first turn0search0');
apply.emit('click');
const applied = { text: text.value, undoVisible: !undo.hidden, copyVisible: !copy.hidden };
text.value = 'manual edit';
text.emit('input');
const manualInvalidated = { undoVisible: !undo.hidden, copyVisible: !copy.hidden };
undo.emit('click');
manualInvalidated.text = text.value;
scan('undo turn0search0');
apply.emit('click');
undo.emit('click');
const restored = text.value;
scan('clear turn0search0');
apply.emit('click');
elements.get('ownText').emit('click');
undo.emit('click');
const cleared = { text: text.value, undoVisible: !undo.hidden, copyVisible: !copy.hidden };
scan('sample turn0search0');
apply.emit('click');
elements.get('insertSample').emit('click');
undo.emit('click');
const sampled = { text: text.value, undoVisible: !undo.hidden, copyVisible: !copy.hidden };
scan('blocked turn0search0');
mode = 'blocked';
run.emit('click');
apply.emit('click');
const blocked = { text: text.value, applyVisible: !apply.hidden };
mode = 'first';
scan('third turn0search0');
mode = 'throw';
run.emit('click');
const failedCleaner = { hasCandidate: Object.prototype.hasOwnProperty.call(apply.dataset, 'cleaned'),
  applyVisible: !apply.hidden };
mode = 'first';
scan('fourth turn0search0');
context.HumanizerCleaner = undefined;
run.emit('click');
const missingCleaner = { hasCandidate: Object.prototype.hasOwnProperty.call(apply.dataset, 'cleaned'),
  applyVisible: !apply.hidden };
process.stdout.write(JSON.stringify({ candidate, staleApplyRejected, applied,
  manualInvalidated, restored, cleared, sampled, blocked, failedCleaner, missingCleaner }));
"""


class DemoCleanupStateTests(unittest.TestCase):
    def test_cleanup_actions_use_current_text_and_clear_stale_state(self):
        if not PAGE.exists():
            if (ROOT / ".git").exists():
                self.fail("demo/index.html отсутствует в checkout")
            self.skipTest("demo/index.html не входит в sdist")
        node = shutil.which("node")
        self.assertIsNotNone(node, "node не найден: cleanup state regression requires Node.js")
        script = NODE_HARNESS.replace("__APP__", json.dumps(_inline_app()))
        proc = subprocess.run([node, "-e", script], cwd=ROOT, text=True,
                              capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["candidate"]["visible"])
        self.assertEqual(data["candidate"]["source"], "first turn0search0")
        self.assertEqual(data["staleApplyRejected"]["text"], "second turn0search0")
        self.assertFalse(data["staleApplyRejected"]["undoVisible"])
        self.assertEqual(data["applied"]["text"], "first ")
        self.assertTrue(data["applied"]["undoVisible"])
        self.assertTrue(data["applied"]["copyVisible"])
        self.assertFalse(data["manualInvalidated"]["undoVisible"])
        self.assertFalse(data["manualInvalidated"]["copyVisible"])
        self.assertEqual(data["manualInvalidated"]["text"], "manual edit")
        self.assertEqual(data["restored"], "undo turn0search0")
        self.assertEqual(data["cleared"], {"text": "", "undoVisible": False, "copyVisible": False})
        self.assertEqual(data["sampled"], {"text": "sample turn0search0", "undoVisible": False, "copyVisible": False})
        self.assertEqual(data["blocked"], {"text": "blocked turn0search0", "applyVisible": False})
        self.assertFalse(data["failedCleaner"]["hasCandidate"])
        self.assertFalse(data["failedCleaner"]["applyVisible"])
        self.assertFalse(data["missingCleaner"]["hasCandidate"])
        self.assertFalse(data["missingCleaner"]["applyVisible"])


if __name__ == "__main__":
    unittest.main()
