#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_demo_browser.py — браузерная проверка демо: DOM-подсветка
режет исходный текст точно (комбинируемые знаки, астральные невидимые
символы, теневые находки), совпадения в code spans подавляются,
URL-маркеры находятся, состояния пусто/чисто/найдено различимы,
горячая клавиша запускает проверку, копирование отчёта до завершения
debounce даёт согласованный отчёт, мобильная ширина без горизонтального
переполнения, работа без сети не теряет детекцию (движок локальный).

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
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const marks = () => Array.from(document.getElementById('preview')
    .querySelectorAll('mark')).map(m => m.textContent);
  const type = async (text) => {
    ta.value = text;
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    await wait(400);
  };
  // Литералы маркеров собраны конкатенацией: само-скан репозитория не
  // должен видеть маркер в исходнике проверки.
  const MARK = ':content' + 'Reference[oaicite:' + '3]{index=3}';
  const TAG = String.fromCodePoint(0xE0061);
  showAll.checked = true;
  showAll.dispatchEvent(new Event('change', { bubbles: true }));
  await wait(100);

  // 1. Комбинируемый знак перед маркером: срез подсветки дословный.
  await type('и\\u0306 ' + MARK);
  out.combining_exact = marks().some(t => t === MARK);

  // 2. Астральный невидимый тег внутри маркера: теневая находка режет
  //    ИСХОДНЫЙ текст точно ([start,end) включают обе UTF-16-единицы
  //    тега), а не укороченный на 2 юнита фрагмент.
  await type('Русский :cont' + TAG + 'ent' + 'Reference[oaicite:' + '3]{index=3} конец.');
  out.astral_slice_exact = marks().some(
    t => t === ':cont' + TAG + 'ent' + 'Reference[oaicite:' + '3]{index=3}');

  // 3. Теневая находка с ZWSP и прямая находка позже по строке.
  await type('\\u200b:cont\\u200bent' + 'Reference[oaicite:' + '3]{index=3}'
    + ' и позже oai_citation:7\\u2021');
  const marks3 = marks();
  out.shadow_present = marks3.some(
    t => t.replace(/[\\u200b]/g, '') === MARK);
  out.direct_present = marks3.some(t => t === 'oai_citation:7\\u2021');

  // 4. Многострочный вход: маркер на второй строке находится.
  await type('первая строка\\n' + MARK);
  out.multiline_second_line = marks().some(t => t === MARK);

  // 5. Code span: совпадение внутри обратных кавычек подавляется.
  await type('x `' + MARK + '` y');
  out.code_span_suppressed = !marks().some(t => t.includes('Reference[oaicite'));

  // 6. URL-маркер внутри ссылки находится (паттерн включает ведущий
  //    разделитель [?&]; литерал собран конкатенацией — само-скан
  //    репозитория не должен видеть маркер в исходнике проверки).
  const UTM = '?utm_' + 'source=openai';
  await type('https://ex.org/' + UTM);
  out.url_marker_found = marks().some(t => t === UTM);

  // 7. Состояния: чисто (совпадений нет) и пусто (приглашение вставить текст).
  await type('Обычный рукописный текст без следов.');
  const cleanNote = document.getElementById('matches').textContent;
  out.clean_state = !marks().length && cleanNote.includes('Совпадений не найдено');
  await type('');
  const emptyNote = document.getElementById('matches').textContent;
  out.empty_state = !marks().length && emptyNote.includes('Вставьте текст');

  // 8. Горячая клавиша Ctrl+Enter запускает проверку немедленно.
  ta.value = MARK;
  ta.dispatchEvent(new KeyboardEvent('keydown',
    { key: 'Enter', ctrlKey: true, bubbles: true }));
  await wait(150);
  out.hotkey_runs = marks().some(t => t === MARK);

  // 9. Копирование отчёта до завершения debounce даёт согласованный отчёт.
  const captured = [];
  Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: t => { captured.push(t); return Promise.resolve(); } } });
  await type('Чистый рукописный текст без следов.');
  ta.value = 'Отчёт ' + MARK + ' конец.';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  document.getElementById('copyReport').click();
  await wait(100);
  const rep = captured[captured.length - 1] || '';
  out.copy_consistent = rep.includes('Найдено 1 след')
    && rep.includes('Reference[oaicite:') && !rep.includes('0 следов');
  return out;
}
"""

MOBILE_JS = """
async () => {
  const ta = document.getElementById('text');
  const MARK = ':content' + 'Reference[oaicite:' + '3]{index=3}';
  ta.value = 'Мобильная проверка ' + MARK;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  const found = Array.from(document.getElementById('preview')
    .querySelectorAll('mark')).some(m => m.textContent === MARK);
  const overflow = document.documentElement.scrollWidth
    > window.innerWidth + 1;
  return { mobile_found: found, mobile_no_overflow: !overflow };
}
"""

OFFLINE_JS = """
async () => {
  const ta = document.getElementById('text');
  const MARK = ':content' + 'Reference[oaicite:' + '3]{index=3}';
  ta.value = 'Работа без сети ' + MARK;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  const found = Array.from(document.getElementById('preview')
    .querySelectorAll('mark')).some(m => m.textContent === MARK);
  return { offline_works: found };
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
        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(200)
        result.update(page.evaluate(MOBILE_JS))
        page.context.set_offline(True)
        result.update(page.evaluate(OFFLINE_JS))
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
