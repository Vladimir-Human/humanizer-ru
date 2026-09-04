#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_social_preview.py — детерминированный social-preview 1280x640:
assets/social-preview.png (+ копия demo/og-image.png) и SVG-исходник
assets/social-preview.svg. Слоган + мини-подсветка следа + URL проекта.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHORT_RU = "Находит следы машинного текста в русском и объясняет их вам"
URL = "vladimir-human.github.io/humanizer-ru"
BG = (13, 17, 23)
FG = (230, 237, 243)
MUTED = (157, 167, 179)
ACCENT = (47, 111, 235)
ACCENT2 = (130, 80, 223)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def font(size):
    from PIL import ImageFont
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1280, 640), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([24, 24, 1256, 616], radius=24,
                        outline=(48, 54, 61), width=2)
    f_title = font(44)
    f_body = font(28)
    f_mono = font(24)
    d.text((64, 72), "humanizer-ru", font=f_title, fill=FG)
    d.text((64, 140), SHORT_RU, font=f_body, fill=FG)
    # мини-терминал с подсветкой
    d.rounded_rectangle([64, 220, 1216, 420], radius=12, fill=(22, 27, 34))
    d.text((88, 244), "$ humanizer-markers --scan primer.txt",
           font=f_mono, fill=MUTED)
    d.rounded_rectangle([88, 288, 1100, 322], radius=6,
                        fill=(ACCENT[0], ACCENT[1], ACCENT[2]), outline=None)
    d.rounded_rectangle([88, 288, 1100, 322], radius=6,
                        fill=(22, 27, 34))
    d.rectangle([88, 288, 640, 322], fill=(47, 111, 235, 60) if False
                else (35, 45, 66))
    d.text((96, 292), "primer.txt:1 [contentReference] Согласно отчёту "
                      ":contentRef…", font=f_mono, fill=FG)
    d.text((88, 344), "почему: служебная метка вставки из ответа ассистента",
           font=f_mono, fill=MUTED)
    d.text((88, 380), "это не приговор — смотрите объяснения каждого флага",
           font=f_mono, fill=MUTED)
    d.text((64, 470), "офлайн, без отправки текста · каждый флаг с причиной "
                      "и советом", font=f_body, fill=MUTED)
    d.text((64, 540), URL, font=f_body, fill=ACCENT2)
    out = os.path.join(ROOT, "assets", "social-preview.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, "PNG")
    import shutil
    shutil.copyfile(out, os.path.join(ROOT, "demo", "og-image.png"))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" '
           'viewBox="0 0 1280 640"><rect width="1280" height="640" '
           'fill="#0d1117"/><rect x="24" y="24" width="1232" height="592" '
           'rx="24" fill="none" stroke="#30363d" stroke-width="2"/>'
           '<text x="64" y="110" fill="#e6edf3" font-family="sans-serif" '
           'font-size="44">humanizer-ru</text>'
           '<text x="64" y="168" fill="#e6edf3" font-family="sans-serif" '
           'font-size="28">%s</text>'
           '<rect x="64" y="220" width="1152" height="200" rx="12" '
           'fill="#161b22"/>'
           '<text x="88" y="268" fill="#9da7b3" font-family="monospace" '
           'font-size="24">$ humanizer-markers --scan primer.txt</text>'
           '<rect x="88" y="288" width="552" height="34" fill="#232d42"/>'
           '<text x="96" y="312" fill="#e6edf3" font-family="monospace" '
           'font-size="24">primer.txt:1 [contentReference] Согласно отчёту '
           ':contentRef…</text>'
           '<text x="88" y="368" fill="#9da7b3" font-family="monospace" '
           'font-size="24">почему: служебная метка вставки из ответа '
           'ассистента</text>'
           '<text x="64" y="500" fill="#9da7b3" font-family="sans-serif" '
           'font-size="28">офлайн, без отправки текста · каждый флаг с '
           'причиной и советом</text>'
           '<text x="64" y="570" fill="#8250df" font-family="sans-serif" '
           'font-size="28">%s</text></svg>\n' % (SHORT_RU, URL))
    with open(os.path.join(ROOT, "assets", "social-preview.svg"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
    print("OK social-preview png+svg, og-image.png обновлён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
