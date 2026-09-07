#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_browser.py — браузерная проверка демо: DOM-подсветка
режет исходный текст точно (комбинируемые знаки, теневые находки),
копирование отчёта до завершения debounce даёт согласованный отчёт.

Требует playwright (python) и запущенный сервер демо:
    python3 -m http.server 8478 --directory demo   # из корня репозитория
    python3 scripts/check_demo_browser.py --url http://localhost:8478/index.html

Без playwright — код 2 (UNAVAILABLE): браузерная проверка не подменяется
статическими гейтами, но и не блокирует CI без среды.
"""
import argparse
import sys

CHECKS_JS = """
async () => {
  const ta = document.getElementById('text');
  const showAll = document.getElementById('showAll');
  const out = {};
  ta.value = 'и\\u0306 :contentReference[oaicite:3]{index=3}';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  showAll.checked = true;
  showAll.dispatchEvent(new Event('change', { bubbles: true }));
  await new Promise(r => setTimeout(r, 100));
  const marks1 = Array.from(document.getElementById('preview')
    .querySelectorAll('mark')).map(m => m.textContent);
  out.combining_exact = marks1.some(
    t => t === ':contentReference[oaicite:3]{index=3}');
  ta.value = '\\u200b:cont\\u200bentReference[oaicite:3]{index=3}'
    + ' и позже oai_citation:7\\u2021';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  const marks3 = Array.from(document.getElementById('preview')
    .querySelectorAll('mark')).map(m => m.textContent);
  out.shadow_present = marks3.some(
    t => t.replace(/[\\u200b]/g, '') === ':contentReference[oaicite:3]{index=3}');
  out.direct_present = marks3.some(t => t === 'oai_citation:7\\u2021');
  const captured = [];
  Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: t => { captured.push(t); return Promise.resolve(); } } });
  ta.value = 'Чистый рукописный текст без следов.';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  ta.value = 'Отчёт :contentReference[oaicite:3]{index=3} конец.';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  document.getElementById('copyReport').click();
  await new Promise(r => setTimeout(r, 100));
  const rep = captured[captured.length - 1] || '';
  out.copy_consistent = rep.includes('Найдено 1 след')
    && rep.includes('contentReference') && !rep.includes('0 следов');
  return out;
}
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url",
                    default="http://localhost:8478/index.html")
    args = ap.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("UNAVAILABLE: playwright не установлен — браузерная "
              "проверка не выполнена (не PASS)")
        return 2
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(args.url)
        page.wait_for_timeout(500)
        result = page.evaluate(CHECKS_JS)
        browser.close()
    fails = [k for k, v in sorted(result.items()) if v is not True]
    for k, v in sorted(result.items()):
        print("%s: %s" % ("PASS" if v is True else "FAIL", k))
    if fails:
        print("БРАУЗЕР-ПРОВЕРКА: провалов %d" % len(fails))
        return 1
    print("БРАУЗЕР-ПРОВЕРКА: все проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
