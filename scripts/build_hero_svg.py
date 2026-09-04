#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_hero_svg.py — генерирует assets/hero.svg из РЕАЛЬНОГО вывода CLI
humanizer-markers на образце из fixtures. Чистый SVG+SMIL, без внешних
зависимостей, цикл 12 секунд, размер целимся <= 150 KB.

Каждый запуск детерминирован: вывод CLI на фиксированном образце.
"""
import os
import subprocess
import sys
import tempfile
import xml.sax.saxutils as su

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE = ("Согласно отчёту :contentReference[oaicite:12]{index=12}, число "
          "заявок за неделю выросло на 12% — источник: "
          "https://example.com/report?utm_source=chatgpt.com\n"
          "Данные подтверждены ассистентом​, подробности см. в чате.\n")

REASONS = {
    "contentReference": "служебная метка вставки из ответа ассистента",
    "utm_chatgpt": "utm-метка провайдера в ссылке из чат-интерфейса",
    "zero_width": "невидимый символ нулевой ширины внутри слова",
}

ACCENT = "#2f6feb"
ACCENT2 = "#8250df"
NEUTRAL_BG = "#0d1117"
NEUTRAL_FG = "#e6edf3"


def run_cli(path):
    r = subprocess.run([sys.executable, "-X", "utf8",
                        os.path.join(ROOT, "scripts", "check_markers.py"),
                        "--scan", path],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return [ln for ln in (r.stdout or "").split("\n") if ln.strip()]


def parse(lines):
    hits = []
    for ln in lines:
        if "] " in ln and ":" in ln:
            head, _, frag = ln.partition("] ")
            marker = head.rsplit("[", 1)[-1] if "[" in head else ""
            if marker:
                hits.append((marker, frag.strip()))
    return hits


def build(hits):
    rows = []
    y = 118
    rows.append((y, "$ humanizer-markers --scan primer.txt", NEUTRAL_FG, None))
    y += 30
    for i, (marker, frag) in enumerate(hits[:3]):
        rows.append((y, "primer.txt:%d [%s] %s" % (i + 1, marker, frag[:52]),
                     NEUTRAL_FG, ACCENT if i == 0 else ACCENT2))
        y += 26
    y += 8
    reason = "; ".join(REASONS.get(m, "служебный след чат-интерфейса")
                       for m, _ in hits[:2]) or "служебный след чат-интерфейса"
    rows.append((y, "почему: " + reason, "#9da7b3", None))
    y += 26
    rows.append((y, "это не приговор — смотрите объяснения каждого флага",
                 "#9da7b3", None))
    height = y + 34
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="880" height="%d" '
        'viewBox="0 0 880 %d" role="img" '
        'aria-label="Терминал: команда humanizer-markers подсвечивает следы '
        'машинного текста и объясняет причину">' % (height, height),
        '<rect width="880" height="%d" rx="14" fill="%s"/>' % (height,
                                                               NEUTRAL_BG),
        '<circle cx="26" cy="26" r="6" fill="#ff5f56"/>',
        '<circle cx="46" cy="26" r="6" fill="#ffbd2e"/>',
        '<circle cx="66" cy="26" r="6" fill="#27c93f"/>',
        '<text x="26" y="64" fill="%s" font-family="monospace" '
        'font-size="15">humanizer-ru — проверка русского текста</text>'
        % NEUTRAL_FG,
    ]
    for i, (yy, text, color, hl) in enumerate(rows):
        begin = "%0.1fs" % (0.6 + i * 1.6)
        if hl:
            parts.append('<rect x="20" y="%d" width="840" height="22" '
                         'rx="5" fill="%s" opacity="0.18">'
                         '<animate attributeName="opacity" values="0;0.18;'
                         '0.18;0.10;0.18" dur="12s" repeatCount="indefinite"/>'
                         '</rect>' % (yy - 16, hl))
        parts.append('<text x="26" y="%d" fill="%s" font-family="monospace" '
                     'font-size="15" opacity="0">%s<animate '
                     'attributeName="opacity" values="0;0;1;1" keyTimes="0;'
                     '%.2f;%.2f;1" dur="12s" repeatCount="indefinite"/>'
                     '</text>' % (yy, color, su.escape(text),
                                  (0.6 + i * 1.6) / 12.0,
                                  (0.6 + i * 1.6 + 0.4) / 12.0))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="hero-primer-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SAMPLE)
    try:
        lines = run_cli(path)
    finally:
        os.unlink(path)
    hits = parse(lines)
    if not hits:
        print("HERO: CLI не дал находок на образце — отказ")
        return 1
    svg = build(hits)
    out = os.path.join(ROOT, "assets", "hero.svg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
    size = os.path.getsize(out)
    print("OK assets/hero.svg: %d байт, находок: %d" % (size, len(hits)))
    return 0 if size <= 150 * 1024 else 1


if __name__ == "__main__":
    sys.exit(main())
