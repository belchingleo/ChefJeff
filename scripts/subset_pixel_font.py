#!/usr/bin/env python3
"""Subset the Fusion Pixel face to the characters the UI can show.

The full face (SIL OFL 1.1, https://github.com/TakWolf/fusion-pixel-font) covers
all of simplified Chinese at ~600 KB; the UI needs a small fraction of it.
Rerun after adding UI text:

    pip install fonttools brotli
    python3 scripts/subset_pixel_font.py path/to/fusion-pixel-12px-proportional-sc.woff2

The npm package @fontsource/fusion-pixel-12px-proportional-sc ships that file.
"""
import argparse
import json
from pathlib import Path
import re

from fontTools import subset

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cocos-kitchen' / 'fonts' / 'chefjeff-pixel.woff2'
SOURCES = ['cocos-kitchen/assets/scripts/KitchenClient.ts', 'cocos-kitchen/web-shell.html', 'hosted/contribution.html']


def ui_text():
    catalog = json.loads((ROOT / 'cocos-kitchen' / 'i18n.json').read_text())
    parts = [*catalog['messages'].keys(), *catalog['messages'].values()]
    parts += [text for pair in catalog['templates'] for text in pair]
    parts += [(ROOT / path).read_text() for path in SOURCES]
    # Printable ASCII, currency, arrows and the HUD's control glyphs are always kept.
    parts.append(''.join(chr(c) for c in range(0x20, 0x7f)) + '¥·–—…»←→↑↓ⅡⅠ▶■！？：；，。、（）「」“”')
    return ''.join(parts)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('font', type=Path, help='full Fusion Pixel 12px Proportional SC font (woff2/ttf/otf)')
    args = p.parse_args()
    chars = sorted({c for c in ui_text() if not re.match(r'\s', c) or c == ' '})
    options = subset.Options()
    options.flavor = 'woff2'
    options.layout_features = ['*']
    options.name_IDs = ['*']
    options.notdef_outline = True
    font = subset.load_font(str(args.font), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=''.join(chars))
    subsetter.subset(font)
    # A subset is a Modified Version under the OFL, which reserves the name "Fusion Pixel":
    # rename the family while keeping the copyright (0), license (13, 14) and designer records.
    names = {1: 'ChefJeff Pixel', 3: 'ChefJeff Pixel Regular (UI subset)', 4: 'ChefJeff Pixel Regular',
             6: 'ChefJeffPixel-Regular', 16: 'ChefJeff Pixel', 17: 'Regular'}
    table = font['name']
    table.names = [r for r in table.names if r.nameID not in (*names, 18, 21, 22, 25)]
    for name_id, text in names.items():
        table.setName(text, name_id, 3, 1, 0x409)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(OUT), options)
    print(f'{OUT.relative_to(ROOT)}: {len(chars)} characters, {OUT.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
