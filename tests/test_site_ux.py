#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# START_MODULE_CONTRACT
# PURPOSE: Verify Browser Studio UX, accessibility, CSP, offline integrity, responsive touch targets,
#          one-row desktop toolbar, bidirectional sessionStorage handoff, Service Worker retirement
#          isolation, and notes.js linear-time/CRLF/null guards across site/.
# SCOPE: Offline stdlib static assertions, Node unit checks for site/sverka/notes.js, and headless
#        Playwright Chromium end-to-end checks across 6 viewports and light/dark color schemes.
# DEPENDS: Python 3.8+ stdlib; node (for notes.js tests); playwright (optional locally, full browser checks).
# LINKS: M-SITE-CHECK; M-SITE-SVERKA; V-M-SITE-CHECK; V-M-SITE-SVERKA; R-DETECTOR-RISK; R-NOTES-NOT-TEXT.
# END_MODULE_CONTRACT
import functools
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
NODE = shutil.which("node")
REQUIRE_NODE = os.environ.get("REQUIRE_NODE") == "1"

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class _SiteServer:
    def __init__(self, directory: Path, sw_override=None):
        self.directory = directory
        self.sw_override = sw_override
        self.httpd = None
        self.thread = None
        self.port = None

    def __enter__(self):
        sw_override = self.sw_override

        class Handler(_QuietHandler):
            def do_GET(self):
                if sw_override is not None and self.path.split("?", 1)[0] == "/sw.js":
                    body = sw_override().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

        handler = functools.partial(Handler, directory=str(self.directory))
        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def __exit__(self, *exc):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=3)


class SiteStaticContractsTest(unittest.TestCase):
    def _skill_version(self) -> str:
        text = (ROOT / "skills" / "humanizer-ru" / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r'^\s*version:\s*"([^"]+)"', text, re.M)
        self.assertIsNotNone(match, "version missing from SKILL.md frontmatter")
        return match.group(1)

    def test_index_is_zero_js_and_keeps_version(self):
        ver = self._skill_version()
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("default-src 'none'", html)
        self.assertNotIn("unsafe-eval", html)
        self.assertNotIn("script-src", html)
        self.assertIn(f'"softwareVersion":"{ver}"', html)
        exec_scripts = re.findall(r"<script(?![^>]*application/ld\+json)[^>]*>", html, re.I)
        self.assertEqual(exec_scripts, [])
        self.assertIn('href="sverka/#step1"', html)
        self.assertIn("с двумя исполнителями", html)
        self.assertNotIn("в два исполнителя", html)
        # Top-level landmarks: header before main, footer after main
        self.assertLess(html.index("<header"), html.index("<main"))
        self.assertLess(html.index("</header>"), html.index("<main"))
        self.assertLess(html.index("</main>"), html.index("<footer"))

    def test_csp_a11y_and_sw_contracts(self):
        for rel in ("index.html", "check/index.html", "sverka/index.html"):
            raw = (SITE / rel).read_bytes()
            self.assertNotIn(b"\r", raw, f"CRLF in site/{rel}")
            html = raw.decode("utf-8")
            self.assertIn("default-src 'none'", html)
            self.assertNotIn("unsafe-eval", html)
            self.assertNotRegex(html, r'<script[^>]+src="https?://', f"external script in {rel}")
            self.assertNotRegex(html, r'<link[^>]+rel="stylesheet"[^>]+href="https?://', f"external css in {rel}")
            self.assertLess(html.index("</header>"), html.index("<main"), f"header inside main in {rel}")
            self.assertLess(html.index("</main>"), html.index("<footer"), f"footer not after main in {rel}")

        check_html = (SITE / "check" / "index.html").read_text(encoding="utf-8")
        self.assertIn("[hidden] { display: none !important; }", check_html)
        self.assertNotRegex(check_html, r'<section[^>]+id="results"[^>]+aria-live=')
        self.assertIn('aria-describedby="text-help privacy-note form-status"', check_html)
        self.assertIn('метки цитат ИИ (oaicite / citeturn)', check_html)

        sverka_html = (SITE / "sverka" / "index.html").read_text(encoding="utf-8")
        self.assertIn("[hidden] { display: none !important; }", sverka_html)
        self.assertNotIn('toggleAttribute("aria-invalid"', sverka_html)
        self.assertNotRegex(sverka_html, r'<div[^>]+id="result-body"[^>]+aria-live=')
        self.assertEqual(sverka_html.count('aria-describedby="privacy-note form-status"'), 2)
        self.assertIn('"имени или названия"', sverka_html)
        self.assertIn('"имён или названий"', sverka_html)

        sw_js = (SITE / "sw.js").read_text(encoding="utf-8")
        self.assertIn('startsWith("humanizer-ru")', sw_js)
        self.assertIn("isV4ToolRoute", sw_js)
        self.assertIn("unregister()", sw_js)

    def test_llms_and_sitemap_consistency(self):
        ver = self._skill_version()
        llms = (SITE / "llms.txt").read_text(encoding="utf-8")
        self.assertIn(f"v{ver}", llms)
        self.assertIn("npx skills add Vladimir-Human/humanizer-ru -a cursor", llms)
        self.assertIn("git clone --depth 1", llms)

        sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
        locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
        self.assertGreaterEqual(len(locs), 4)
        base = "https://vladimir-human.github.io/humanizer-ru/"
        for loc in locs:
            self.assertTrue(loc.startswith(base), loc)
            rel = loc[len(base):]
            target = SITE / (rel + "index.html" if (not rel or rel.endswith("/")) else rel)
            self.assertTrue(target.is_file(), f"Missing sitemap target: {target}")


class NotesJsExtendedTest(unittest.TestCase):
    def setUp(self):
        if not NODE:
            if REQUIRE_NODE:
                self.fail("REQUIRE_NODE=1 but node is missing")
            self.skipTest("node is missing")

    def test_notes_js_null_crlf_and_redos_bounds(self):
        js = r"""
        const { splitNotes } = require(process.argv[1]);
        const t0 = performance.now();
        const nullRes = splitNotes(null, undefined);
        const numRes = splitNotes(123, null);
        const crlfRes = splitNotes("Основной текст.\r\n\r\n---\r\nУбрал повтор.\r\n", "Исходник.\r\n");
        const bomRes = splitNotes("\ufeffТекст.", "");
        const spaces = "x" + " ".repeat(100000) + "x";
        const redos1 = splitNotes(spaces, "");
        const redos2 = splitNotes("Текст.\n---\n" + " ".repeat(50000) + "убрал повтор", "Текст.");
        const dt = (performance.now() - t0) / 1000;
        process.stdout.write(JSON.stringify({
          nullRes, numRes, crlfRes, bomKept: bomRes[0].startsWith("\ufeff"),
          redos1Len: redos1[0].length, redos2Text: redos2[0], dt
        }));
        """
        res = subprocess.run(
            [NODE, "-e", js, str(SITE / "sverka" / "notes.js")],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        got = json.loads(res.stdout)
        self.assertEqual(got["nullRes"], ["", ""])
        self.assertEqual(got["numRes"], ["123", ""])
        self.assertEqual(got["crlfRes"], ["Основной текст.", "Убрал повтор."])
        self.assertTrue(got["bomKept"])
        self.assertEqual(got["redos1Len"], 100002)
        self.assertEqual(got["redos2Text"], "Текст.")
        self.assertLess(got["dt"], 0.5)


@unittest.skipUnless(sync_playwright is not None, "playwright is not installed")
class SiteBrowserUxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()

    def _new_context(self, viewport=(1280, 900), color_scheme="light", permissions=None):
        kwargs = {
            "viewport": {"width": viewport[0], "height": viewport[1]},
            "color_scheme": color_scheme,
        }
        if permissions:
            kwargs["permissions"] = permissions
        return self._browser.new_context(**kwargs)

    def _attach_watchers(self, page, origin):
        errors = {"console": [], "page": [], "csp": [], "external": []}
        page.on("console", lambda m: errors["console"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors["page"].append(str(e)))
        page.on("request", lambda r: errors["external"].append(r.url)
                if not (r.url.startswith(origin) or r.url.startswith("data:") or r.url.startswith("about:")) else None)
        page.add_init_script("""
            window.__cspViolations = [];
            document.addEventListener("securitypolicyviolation", (e) => {
              window.__cspViolations.push({
                directive: e.violatedDirective,
                blocked: e.blockedURI,
                line: e.lineNumber
              });
            });
        """)
        return errors

    def test_responsive_layout_csp_touch_targets_and_one_row_toolbar(self):
        viewports = [(320, 568), (375, 812), (412, 915), (680, 900), (768, 1024), (1280, 900)]
        pages = ["/", "/check/", "/sverka/"]
        with _SiteServer(SITE) as srv:
            origin = srv.url("")
            for scheme in ("light", "dark"):
                for vp in viewports:
                    ctx = self._new_context(viewport=vp, color_scheme=scheme)
                    try:
                        page = ctx.new_page()
                        errs = self._attach_watchers(page, origin)
                        for path in pages:
                            page.goto(srv.url(path), wait_until="networkidle")
                            if path == "/check/":
                                page.wait_for_function("() => !document.getElementById('check-button').disabled")
                            elif path == "/sverka/":
                                page.wait_for_function("() => !document.getElementById('check-button').disabled")

                            metrics = page.evaluate("""() => {
                              const overflow = document.documentElement.scrollWidth - window.innerWidth;
                              const smallTargets = [];
                              for (const el of document.querySelectorAll('.top-nav a, .back-link, button, summary')) {
                                const style = getComputedStyle(el);
                                if (style.display === 'none' || style.visibility === 'hidden' || el.closest('[hidden]')) continue;
                                const r = el.getBoundingClientRect();
                                if (r.width === 0 && r.height === 0) continue;
                                if (r.height < 43.5) {
                                  smallTargets.push({tag: el.tagName, id: el.id, text: el.textContent.trim().slice(0, 30), h: r.height});
                                }
                              }
                              const smallTextareas = [];
                              for (const ta of document.querySelectorAll('textarea')) {
                                const fs = parseFloat(getComputedStyle(ta).fontSize);
                                if (fs < 16) smallTextareas.push({id: ta.id, fs});
                              }
                              const formActionTops = Array.from(document.querySelectorAll('.form-actions button'))
                                .filter(b => !b.hidden && getComputedStyle(b).display !== 'none')
                                .map(b => Math.round(b.getBoundingClientRect().top));
                              return {
                                overflow, smallTargets, smallTextareas, formActionTops,
                                csp: window.__cspViolations || []
                              };
                            }""")
                            label = f"{path} @ {vp[0]}x{vp[1]} ({scheme})"
                            self.assertEqual(errs["console"], [], f"console errors on {label}: {errs['console']}")
                            self.assertEqual(errs["page"], [], f"page errors on {label}: {errs['page']}")
                            self.assertEqual(errs["external"], [], f"external requests on {label}: {errs['external']}")
                            self.assertEqual(metrics["csp"], [], f"CSP violations on {label}: {metrics['csp']}")
                            self.assertLessEqual(metrics["overflow"], 0, f"horizontal overflow {metrics['overflow']} on {label}")
                            self.assertEqual(metrics["smallTargets"], [], f"touch target <44px on {label}: {metrics['smallTargets']}")
                            self.assertEqual(metrics["smallTextareas"], [], f"textarea <16px on {label}: {metrics['smallTextareas']}")
                            if path == "/check/" and vp == (1280, 900):
                                tops = metrics["formActionTops"]
                                self.assertGreaterEqual(len(tops), 4, f"expected 4 form-actions buttons on {label}")
                                self.assertLessEqual(max(tops) - min(tops), 2, f"/check/ action buttons wrapped on 1280x900: {tops}")
                    finally:
                        ctx.close()

    def test_check_page_interactive_ux_undo_highlights_stale_and_xss(self):
        with _SiteServer(SITE) as srv:
            ctx = self._new_context(viewport=(1280, 900), permissions=["clipboard-read", "clipboard-write"])
            try:
                page = ctx.new_page()
                errs = self._attach_watchers(page, srv.url(""))
                page.goto(srv.url("/check/"), wait_until="networkidle")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")

                # Empty submit marks invalid & focuses textarea
                page.click("#check-button")
                self.assertEqual(page.get_attribute("#text-input", "aria-invalid"), "true")
                self.assertEqual(page.evaluate("() => document.activeElement.id"), "text-input")

                # Demo button populates and runs check
                page.click("#demo-button")
                page.wait_for_selector("#annotated-text mark.hl")
                self.assertGreater(page.locator("#annotated-text mark.hl-phrase").count(), 0)
                self.assertGreater(page.locator("#annotated-text mark.hl-mixed").count(), 0)
                self.assertGreater(page.locator("#annotated-text mark.hl-invisible").count(), 0)

                # Collapsed all-11 metrics disclosure present with минимум/максимум
                summary_text = page.locator("#all-metrics summary").text_content()
                self.assertIn("11", summary_text)
                page.click("#all-metrics summary")
                all_metrics_text = page.locator("#all-metrics").text_content()
                self.assertIn("минимум", all_metrics_text)
                self.assertIn("максимум", all_metrics_text)

                # Legend toggle hides layer; clicking example jump re-enables and pulses mark
                phrase_toggle = page.locator('.hl-badge[data-filter="phrase"]')
                phrase_toggle.click()
                self.assertEqual(phrase_toggle.get_attribute("aria-pressed"), "false")
                self.assertTrue(page.locator("#annotated-text").evaluate("el => el.classList.contains('hide-phrase')"))

                page.locator(".example-jump").first.click()
                self.assertEqual(phrase_toggle.get_attribute("aria-pressed"), "true")
                self.assertFalse(page.locator("#annotated-text").evaluate("el => el.classList.contains('hide-phrase')"))
                self.assertGreater(page.locator("#annotated-text mark.hl.is-active").count(), 0)
                self.assertTrue(page.locator("#hl-detail").evaluate("el => el.classList.contains('is-active')"))

                # Escape clears active pulse
                page.keyboard.press("Escape")
                self.assertEqual(page.locator("#annotated-text mark.hl.is-active").count(), 0)

                # Clean + 1-step Undo restores exact text and re-runs lint
                before_clean = page.input_value("#text-input")
                self.assertTrue(page.locator("#undo-clean").is_hidden())
                page.click("#clean-button")
                after_clean = page.input_value("#text-input")
                self.assertNotEqual(after_clean, before_clean)
                self.assertNotIn("utm_source=chatgpt.com", after_clean)
                self.assertNotIn("\u200b", after_clean)
                self.assertFalse(page.locator("#undo-clean").is_hidden())

                # Copy cleaned text via #copy-button (Windows clipboard normalizes LF -> CRLF)
                page.click("#copy-button")
                page.wait_for_function("() => document.getElementById('form-status').textContent.includes('скопирован')")
                copied = page.evaluate("async () => await navigator.clipboard.readText()")
                self.assertEqual(copied.replace("\r\n", "\n"), after_clean)

                page.click("#undo-clean")
                self.assertEqual(page.input_value("#text-input"), before_clean)
                self.assertTrue(page.locator("#undo-clean").is_hidden())

                # Non-destructive editing marks results stale instead of wiping them
                page.focus("#text-input")
                page.keyboard.type(" ")
                self.assertTrue(page.locator("#results").evaluate("el => el.classList.contains('is-stale')"))
                self.assertGreater(page.locator("#results .summary").count(), 0)

                # Ctrl+Enter re-runs check and clears stale state
                page.keyboard.press("Control+Enter")
                self.assertFalse(page.locator("#results").evaluate("el => el.classList.contains('is-stale')"))

                # Clean text early-returns without duplicating clean text in #annotated-text
                page.fill("#text-input", "Обычная короткая фраза без штампов.")
                page.click("#check-button")
                self.assertEqual(page.locator("#annotated-text").count(), 0)
                self.assertIn("Подсвечивать в тексте нечего", page.locator("#results").text_content())

                # Split phrase around inner mixed + invisible renders all 3 badges with deduplicated phrase count
                page.fill("#text-input", "Это не просто cиcтeма\u200bтест, а решение.")
                page.click("#check-button")
                page.wait_for_selector("#annotated-text mark.hl")
                badges = page.locator(".hl-badge").all_text_contents()
                self.assertIn("Фразы: 1", badges)
                self.assertTrue(any("Смешение кириллицы с латиницей или греческим: 1" in b for b in badges), badges)
                self.assertIn("Невидимые символы: 1", badges)

                # XSS payload stays inert
                page.fill("#text-input", '<img src=x onerror="window.__xss=1"> Это не просто тест, а cиcтeма\u200b.')
                page.click("#check-button")
                self.assertIsNone(page.evaluate("() => window.__xss"))
                self.assertEqual(page.locator("#results img").count(), 0)
                self.assertIn("<img src=x", page.locator("#annotated-text").text_content())

                self.assertEqual(errs["console"], [])
                self.assertEqual(errs["page"], [])
                self.assertEqual(errs["external"], [])
            finally:
                ctx.close()

    def test_sverka_interactive_ux_validation_stale_notes_and_xss(self):
        with _SiteServer(SITE) as srv:
            ctx = self._new_context(viewport=(1280, 900), permissions=["clipboard-read", "clipboard-write"])
            try:
                page = ctx.new_page()
                errs = self._attach_watchers(page, srv.url(""))
                page.goto(srv.url("/sverka/"), wait_until="networkidle")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")

                # Empty submit: explicit aria-invalid="true" & focus #before
                page.click("#check-button")
                self.assertEqual(page.get_attribute("#before", "aria-invalid"), "true")
                self.assertEqual(page.get_attribute("#after", "aria-invalid"), "true")
                self.assertEqual(page.evaluate("() => document.activeElement.id"), "before")

                # Fill #before only: #before valid, #after aria-invalid="true" & focused
                page.fill("#before", "Около 10 человек пришли 5 мая.")
                page.click("#check-button")
                self.assertIsNone(page.get_attribute("#before", "aria-invalid"))
                self.assertEqual(page.get_attribute("#after", "aria-invalid"), "true")
                self.assertEqual(page.evaluate("() => document.activeElement.id"), "after")

                # Identical text warning + #fix-row hidden
                page.fill("#after", "Около 10 человек пришли 5 мая.")
                page.click("#check-button")
                self.assertGreater(page.locator("#result-body .verdict.warn").count(), 0)
                self.assertTrue(page.locator("#fix-row").is_hidden())

                # Checks-only fixRequest has no dangling error header
                page.fill("#after", "10 человек пришли 5 мая.")
                page.click("#check-button")
                self.assertFalse(page.locator("#fix-row").is_hidden())
                self.assertEqual(page.locator("#copy-fix").text_content().strip(), "Скопировать просьбу проверить")
                page.click("#copy-fix")
                page.wait_for_function("() => document.getElementById('fix-status').textContent.includes('Скопировано')")
                checks_fix = page.evaluate("async () => await navigator.clipboard.readText()").replace("\r\n", "\n")
                self.assertNotIn("только исправь это:", checks_fix)
                self.assertIn("только проверь, не изменился ли смысл", checks_fix)
                self.assertIn("Верни текст целиком.", checks_fix)

                # Demo pair: swap + lost date + cut notes preview + clean copy without --- notes
                page.click("#demo-pair")
                self.assertGreater(page.locator("#result-body .verdict.bad").count(), 0)
                self.assertFalse(page.locator("#fix-row").is_hidden())
                self.assertFalse(page.locator("#clean-row").is_hidden())
                self.assertEqual(page.locator("#cut-notes-details").count(), 1)
                self.assertIn("Убрал лишние слова", page.locator("#cut-notes-details pre").text_content())
                page.click("#copy-clean")
                page.wait_for_function("() => document.getElementById('clean-status').textContent.includes('скопирована')")
                clean_copied = page.evaluate("async () => await navigator.clipboard.readText()").replace("\r\n", "\n")
                self.assertNotIn("---", clean_copied)
                self.assertNotIn("Убрал лишние слова", clean_copied)
                self.assertIn("Тариф Базовый", clean_copied)

                # Editing marks stale & disables #copy-fix and #copy-clean
                page.focus("#after")
                page.keyboard.type(" ")
                self.assertTrue(page.locator("#result").evaluate("el => el.classList.contains('is-stale')"))
                self.assertTrue(page.locator("#copy-fix").is_disabled())
                self.assertTrue(page.locator("#copy-clean").is_disabled())

                # Ctrl+Enter re-runs check and re-enables copy buttons
                page.keyboard.press("Control+Enter")
                self.assertFalse(page.locator("#result").evaluate("el => el.classList.contains('is-stale')"))
                self.assertFalse(page.locator("#copy-fix").is_disabled())

                # XSS in text & cut notes stays inert
                page.fill("#before", '<img src=x onerror="window.__xss=1"> Итог — 500 ₽.')
                page.fill("#after", '<img src=x onerror="window.__xss=1"> Итог — 600 ₽.\n\n---\nУбрал <img src=x onerror="window.__xss=2">.')
                page.click("#check-button")
                self.assertIsNone(page.evaluate("() => window.__xss"))
                self.assertEqual(page.locator("#result img").count(), 0)

                self.assertEqual(errs["console"], [])
                self.assertEqual(errs["page"], [])
                self.assertEqual(errs["external"], [])
            finally:
                ctx.close()

    def test_sverka_prompt_fetch_failure_fallback(self):
        with _SiteServer(SITE) as srv:
            ctx = self._new_context(viewport=(1280, 900))
            try:
                page = ctx.new_page()
                page.route("**/prompt.txt", lambda route: route.fulfill(status=500, body="err"))
                page.goto(srv.url("/sverka/"), wait_until="networkidle")
                page.wait_for_function("() => document.getElementById('prompt-status').classList.contains('is-error')")
                fallback = page.locator("#prompt-text").text_content()
                self.assertIn("prompt/chat.md", fallback)
                self.assertTrue(page.locator("#copy-prompt").is_disabled())
            finally:
                ctx.close()

    def test_bidirectional_sessionstorage_handoff_and_delta(self):
        with _SiteServer(SITE) as srv:
            ctx = self._new_context(viewport=(1280, 900))
            try:
                page = ctx.new_page()
                # 1. /sverka/ -> /check/ passes edit + before + origin="after", shows До -> После delta, clears keys
                page.goto(srv.url("/sverka/"), wait_until="networkidle")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")
                src_text = "В современном мире цифровая система играет ключевую роль и открывает новые возможности."
                edt_text = "Цифровая система ускоряет оплату в магазине."
                page.fill("#before", src_text)
                page.fill("#after", edt_text + "\n\n---\nУбрал штампы.")
                page.click("#to-check")
                page.wait_for_url("**/check/")
                page.wait_for_selector("#score-delta")

                self.assertEqual(page.input_value("#text-input"), edt_text)
                delta_text = page.locator("#score-delta").text_content()
                self.assertIn("До → После: балл", delta_text)
                leftover = page.evaluate("() => [sessionStorage.getItem('humanizer_check'), sessionStorage.getItem('humanizer_before'), sessionStorage.getItem('humanizer_origin')]")
                self.assertEqual(leftover, [None, None, None])

                # 2. /check/ -> /sverka/ when origin was "after" puts edited text into #after (NOT #before!)
                edited_more = edt_text + " Всё работает офлайн."
                page.fill("#text-input", edited_more)
                page.click("#to-sverka")
                page.wait_for_url("**/sverka/")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")
                self.assertEqual(page.input_value("#before"), src_text)
                self.assertEqual(page.input_value("#after"), edited_more)
                leftover2 = page.evaluate("() => [sessionStorage.getItem('humanizer_source'), sessionStorage.getItem('humanizer_after')]")
                self.assertEqual(leftover2, [None, None])

                # 3. Fresh /check/ draft -> /sverka/ puts text into #before and focuses #after
                page.goto(srv.url("/check/"), wait_until="networkidle")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")
                page.fill("#text-input", "Новый черновик для сверки.")
                page.click("#to-sverka")
                page.wait_for_url("**/sverka/")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")
                self.assertEqual(page.input_value("#before"), "Новый черновик для сверки.")
                self.assertEqual(page.input_value("#after"), "")
                self.assertEqual(page.evaluate("() => document.activeElement.id"), "after")
            finally:
                ctx.close()

    def test_sw_retires_humanizer_caches_only_and_skips_v4_reload(self):
        legacy_sw = """
        self.addEventListener("install", () => self.skipWaiting());
        self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
        """
        real_sw = (SITE / "sw.js").read_text(encoding="utf-8")
        mode = {"v4": False}

        def serve_sw():
            return real_sw if mode["v4"] else legacy_sw

        with _SiteServer(SITE, sw_override=serve_sw) as srv:
            ctx = self._new_context(viewport=(1280, 900))
            try:
                # Tab 1: v4 tool route (/check/) — must NOT reload or lose textarea draft
                page = ctx.new_page()
                page.goto(srv.url("/check/"), wait_until="networkidle")
                page.wait_for_function("() => !document.getElementById('check-button').disabled")
                page.evaluate("""async () => {
                  await caches.open("humanizer-ru-v3-cache");
                  await caches.open("other-app-cache");
                  await navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
                  await navigator.serviceWorker.ready;
                  window.__marker = "alive";
                }""")
                page.fill("#text-input", "Несохранённый текст пользователя на /check/")

                # Tab 2: legacy root route (/) — SHOULD navigate into v4 with controller=null
                root_page = ctx.new_page()
                root_page.goto(srv.url("/"), wait_until="networkidle")
                root_page.evaluate("() => { window.__v3marker = 'old'; }")

                # Flip /sw.js to our v4 retirement worker and trigger update
                mode["v4"] = True
                with root_page.expect_navigation(timeout=10000):
                    done = page.evaluate("""async () => {
                      const regs = await navigator.serviceWorker.getRegistrations();
                      for (const r of regs) await r.update();
                      const deadline = Date.now() + 8000;
                      while (Date.now() < deadline) {
                        const cur = await navigator.serviceWorker.getRegistrations();
                        const keys = await caches.keys();
                        if (cur.length === 0 && !keys.includes("humanizer-ru-v3-cache")) {
                          return { regs: cur.length, keys };
                        }
                        await new Promise(r => setTimeout(r, 50));
                      }
                      return {
                        regs: (await navigator.serviceWorker.getRegistrations()).length,
                        keys: await caches.keys()
                      };
                    }""")
                root_page.wait_for_load_state("networkidle")

                self.assertEqual(done["regs"], 0)
                self.assertNotIn("humanizer-ru-v3-cache", done["keys"])
                self.assertIn("other-app-cache", done["keys"])
                # /check/ tab was NOT force-reloaded: JS marker & textarea survived!
                self.assertEqual(page.evaluate("() => window.__marker"), "alive")
                self.assertEqual(page.input_value("#text-input"), "Несохранённый текст пользователя на /check/")
                # / tab navigated cleanly into v4 with no controlling SW
                self.assertIsNone(root_page.evaluate("() => window.__v3marker"))
                self.assertIsNone(root_page.evaluate("() => navigator.serviceWorker.controller"))
            finally:
                ctx.close()


if __name__ == "__main__":
    unittest.main()
