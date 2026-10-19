"""Render the player pages (privacy and contact, model guide) from docs/ Markdown for the web build.

One source serves the README on GitHub and the pages the game links to. Only the Markdown
those two files use is supported: headings, paragraphs, lists, **bold**, `code` and links.
"""
import html
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGES = {'privacy.md': 'privacy.html', 'model-guide.md': 'model-guide.html'}
STYLE = ('body{margin:0;background:#fdf3e1;color:#2b1a12;font:16px/1.7 system-ui,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif}'
         'main{max-width:760px;margin:0 auto;padding:24px 16px 48px}h1{font-size:28px;line-height:1.3}h2{margin-top:32px;font-size:22px}'
         'h3{font-size:18px}a{color:#2a5a9e}code{padding:1px 4px;background:#f0d9b5;font-size:14px;overflow-wrap:anywhere}'
         'ul,ol{padding-left:22px}hr{margin:32px 0;border:0;border-top:2px solid #6b3418}')


def inline(text):
    def link(match):
        label, url = match[1], PAGES.get(match[2], match[2])
        if not re.fullmatch(r'https://[^\s"<>]+|#[a-z-]+|' + '|'.join(map(re.escape, PAGES.values())), url):
            raise ValueError('Unsupported link in player page: ' + url)
        outside = ' target="_blank" rel="noopener noreferrer"' if url.startswith('https://') else ''
        return f'<a href="{url}"{outside}>{label}</a>'
    text = html.escape(text, quote=False)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', link, text)


def render(markdown):
    out, items, paragraph, title = [], [], [], 'ChefJeff'
    def flush():
        if paragraph: out.append('<p>' + inline(' '.join(paragraph)) + '</p>'); paragraph.clear()
    def close_list():
        if not items: return
        # A two-space indent nests a list under the item before it.
        top = []
        for depth, text in items:
            if depth and top: top[-1][1].append(text)
            else: top.append((text, []))
        out.append('<ul>' + ''.join('<li>' + inline(t) + (('<ul>' + ''.join('<li>' + inline(c) + '</li>' for c in sub) + '</ul>') if sub else '') + '</li>'
                                    for t, sub in top) + '</ul>')
        items.clear()
    for line in markdown.splitlines():
        heading, item = re.match(r'(#{1,3}) (.+)', line), re.match(r'( *)- (.+)', line)
        if item: flush(); items.append((len(item[1]) >= 2, item[2])); continue
        close_list()
        if not line.strip(): flush()
        elif heading:
            flush(); level, text = len(heading[1]), heading[2]
            if level == 1: title = text
            anchor = f' id="{text.lower()}"' if re.fullmatch(r'[A-Za-z-]+', text) else ''
            out.append(f'<h{level}{anchor}>{inline(text)}</h{level}>')
        elif line.strip() == '---': flush(); out.append('<hr>')
        else: paragraph.append(line.strip())
    flush(); close_list()
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><link rel="icon" href="favicon.ico"><style>{STYLE}</style></head>'
            '<body><main>' + '\n'.join(out) + '</main></body></html>\n')


def write_pages(folder):
    for source, target in PAGES.items():
        (Path(folder) / target).write_text(render((ROOT / 'docs' / source).read_text()))
