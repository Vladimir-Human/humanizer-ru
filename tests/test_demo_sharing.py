"""Regression tests for the demo's consent-gated share flow."""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "demo" / "index.html"


def _inline_app() -> str:
    source = PAGE.read_text(encoding="utf-8")
    match = re.search(r"<script>\s*(\(\(\) => \{.*?\n\}\)\(\);)\s*</script>", source, re.S)
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
    id, value: '', checked: id === 'showAll', innerHTML: '', textContent: '',
    returnValue: '', focused: false, shown: 0,
    addEventListener(type, fn) { (handlers[type] ||= []).push(fn); },
    emit(type, event = {}) { for (const fn of (handlers[type] || [])) fn(event); },
    focus() { this.focused = true; },
    showModal() { this.shown++; },
    appendChild() {},
  };
  elements.set(id, e); return e;
}
for (const id of ['text', 'matches', 'preview', 'summary', 'onlyA', 'showAll',
                  'run', 'insertSample', 'ownText', 'copyReport', 'copyStatus',
                  'shareBtn', 'counts', 'scanState', 'shareDialog']) element(id);
const documentHandlers = Object.create(null);
const document = {
  getElementById(id) { return elements.get(id) || element(id); },
  createElement() { return { className: '', innerHTML: '', appendChild() {} }; },
  addEventListener(type, fn) { (documentHandlers[type] ||= []).push(fn); },
};
let hash = '';
let hashWrites = 0;
const location = {
  pathname: '/', search: '',
  get hash() { return hash; },
  set hash(value) { hash = value && value[0] === '#' ? value : '#' + value; hashWrites++; },
};
const context = {
  document, location, navigator: {}, history: { replaceState() {} },
  HUMANIZER_MARKERS: { rules: [] }, HUMANIZER_SAMPLE: '',
  TextEncoder, encodeURIComponent, decodeURIComponent, setTimeout, clearTimeout,
  console, JSON, Object, String, Array, RegExp, Error,
};
vm.runInNewContext(app, context, { filename: 'demo/index.html' });
const text = elements.get('text');
const share = elements.get('shareBtn');
const dialog = elements.get('shareDialog');
function click() { share.emit('click'); }
  function close(value) { dialog.returnValue = value; dialog.emit('close'); }
  // Model Escape as the dialog's close event without rewriting returnValue.
  // The page must reset it before every showModal() call.
  function escapeDialog() { dialog.emit('close'); }
function result() {
  text.value = '';
  click();
  const empty = { shown: dialog.shown, writes: hashWrites, hash };
  text.value = 'проверяемый текст';
  click();
  const pending = { shown: dialog.shown, writes: hashWrites, hash };
  close('cancel');
  const cancelled = { writes: hashWrites, hash };
  text.value = 'текущий текст';
  click(); close('share');
  const confirmed = { writes: hashWrites, hash, expected: encodeURIComponent('текущий текст') };
  text.value = 'новый текст после ссылки';
  click(); escapeDialog();
  const escaped = { writes: hashWrites, hash };
  text.value = 'a'.repeat(65536);
  const beforeBoundary = { shown: dialog.shown, writes: hashWrites, hash };
  click();
  const boundary = { shown: dialog.shown, writes: hashWrites, hash };
  close('cancel');
  text.value = 'a'.repeat(65537);
  const beforeOversize = { shown: dialog.shown, writes: hashWrites, hash };
  click();
  const oversize = { shown: dialog.shown, writes: hashWrites, hash };
  text.value = '\ud800';
  const beforeMalformed = { shown: dialog.shown, writes: hashWrites, hash };
  click();
  const malformed = { shown: dialog.shown, writes: hashWrites, hash };
  return { empty, pending, cancelled, confirmed, escaped, boundary, oversize,
           beforeBoundary, beforeOversize, malformed, beforeMalformed };
}
process.stdout.write(JSON.stringify(result()));
"""


class DemoSharingTests(unittest.TestCase):
    def test_share_requires_explicit_confirmation_and_uses_current_text(self):
        if not PAGE.exists():
            if (ROOT / ".git").exists():
                self.fail("demo/index.html отсутствует в checkout")
            self.skipTest("demo/index.html не входит в sdist")
        node = shutil.which("node")
        self.assertIsNotNone(node, "node не найден: demo sharing regression requires Node.js")
        script = NODE_HARNESS.replace("__APP__", json.dumps(_inline_app()))
        proc = subprocess.run([node, "-e", script], cwd=ROOT, text=True,
                              capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)

        self.assertEqual(data["empty"]["writes"], 0)
        self.assertEqual(data["empty"]["shown"], 0)
        self.assertEqual(data["pending"]["shown"], 1)
        self.assertEqual(data["pending"]["writes"], 0)
        self.assertEqual(data["cancelled"]["writes"], 0)
        self.assertEqual(data["confirmed"]["hash"], "#" + data["confirmed"]["expected"])
        self.assertEqual(data["confirmed"]["writes"], 1)
        self.assertEqual(data["escaped"]["hash"], data["confirmed"]["hash"])
        self.assertEqual(data["escaped"]["writes"], 1)
        self.assertEqual(data["boundary"]["shown"], data["beforeBoundary"]["shown"] + 1)
        self.assertEqual(data["boundary"]["writes"], 1)
        self.assertEqual(data["oversize"]["hash"], data["confirmed"]["hash"])
        self.assertEqual(data["oversize"]["writes"], 1)
        self.assertEqual(data["oversize"]["shown"], data["beforeOversize"]["shown"])
        self.assertEqual(data["malformed"]["hash"], data["confirmed"]["hash"])
        self.assertEqual(data["malformed"]["writes"], 1)
        self.assertEqual(data["malformed"]["shown"], data["beforeMalformed"]["shown"])


if __name__ == "__main__":
    unittest.main()
