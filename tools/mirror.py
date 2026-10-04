#!/usr/bin/env python3
"""Private copy of everything the edition links to (except the LessWrong
discussion pages).

For every external target in dist/links.csv:
  * the file itself (PDF, image, plain text, ...) or the page's HTML, and
  * for web pages, a PDF of the page as rendered by Chromium (readable on
    its own, also for pages that need JavaScript).
Output: mirror/files/<name>.*, mirror/index.csv (codes -> files) and
mirror/index.md.  Resumable: existing files are kept.

This is a personal archive; most linked works are under copyright, so the
mirror belongs in a private repository and must not be published.

usage: tools/mirror.py [--retry-failed]
"""
import csv
import concurrent.futures as cf
import datetime
import hashlib
import json
import mimetypes
import os
import re
import sys
from urllib.parse import urlsplit

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'mirror')
FILES = os.path.join(OUT, 'files')
STATE = os.path.join(OUT, 'state.json')
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
      ' Chrome/124.0 Safari/537.36')
MAX_BYTES = 95 * 1024 * 1024        # GitHub refuses files over 100 MB
CHROMIUM = os.environ.get('CHROMIUM', '/opt/pw-browsers/chromium')


def slug(url):
    p = urlsplit(url)
    s = re.sub(r'[^A-Za-z0-9]+', '-', (p.netloc + p.path).lower()).strip('-')
    h = hashlib.sha1(url.encode()).hexdigest()[:8]
    return '%s-%s' % (s[:70].rstrip('-'), h)


def targets():
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'dist', 'links.csv'),
                                    encoding='utf-8')))
    out = {}
    for r in rows:
        if r['kind'].startswith('discussion'):
            continue
        key = r['final URL']
        t = out.setdefault(key, {'final': key, 'original': r['original URL'],
                                 'status': r['status'], 'codes': [],
                                 'text': r['link text']})
        t['codes'].append(r['code'])
    return list(out.values())


def ext_for(ctype, url):
    ctype = (ctype or '').split(';')[0].strip().lower()
    if ctype in ('text/html', 'application/xhtml+xml'):
        return '.html'
    e = mimetypes.guess_extension(ctype) if ctype else None
    if not e:
        e = os.path.splitext(urlsplit(url).path)[1][:6] or '.bin'
    return {'.htm': '.html', '.jpe': '.jpg'}.get(e, e)


def fetch(t):
    """Download the target itself.  Returns the updated record."""
    base = os.path.join(FILES, slug(t['final']))
    if t.get('raw') and os.path.exists(os.path.join(OUT, t['raw'])):
        return t
    for url in dict.fromkeys([t['final'], t['original']]):
        try:
            r = requests.get(url, headers={'User-Agent': UA}, timeout=60,
                             stream=True, allow_redirects=True)
        except requests.RequestException as e:
            t['error'] = '%s: %s' % (url, type(e).__name__)
            continue
        if r.status_code >= 400:
            t['error'] = '%s: HTTP %d' % (url, r.status_code)
            continue
        ctype = r.headers.get('content-type', '')
        path = base + ext_for(ctype, r.url)
        size = 0
        with open(path, 'wb') as f:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if size > MAX_BYTES:
                    break
                f.write(chunk)
        if size > MAX_BYTES:
            os.remove(path)
            t['error'] = 'larger than 95 MB, not kept'
            return t
        t.update(raw=os.path.relpath(path, OUT), ctype=ctype.split(';')[0],
                 bytes=size, fetched_from=r.url)
        t.pop('error', None)
        return t
    return t


def render_all(todo):
    """PDF of every HTML page (and of pages the plain download could not
    get, which a real browser often can)."""
    from playwright.sync_api import sync_playwright
    proxy = os.environ.get('HTTPS_PROXY')
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM,
                              proxy={'server': proxy} if proxy else None)
        ctx = b.new_context(user_agent=UA, viewport={'width': 1200, 'height': 1600})
        for i, t in enumerate(todo, 1):
            pdf = os.path.join(FILES, slug(t['final']) + '.page.pdf')
            if os.path.exists(pdf):
                t['page_pdf'] = os.path.relpath(pdf, OUT)
                continue
            pg = ctx.new_page()
            try:
                url = t.get('fetched_from') or t['final']
                pg.goto(url, timeout=60000, wait_until='load')
                pg.wait_for_timeout(2500)
                pg.emulate_media(media='screen')
                pg.pdf(path=pdf, format='A4', print_background=True,
                       margin={'top': '12mm', 'bottom': '12mm',
                               'left': '10mm', 'right': '10mm'})
                t['page_pdf'] = os.path.relpath(pdf, OUT)
                t['page_title'] = pg.title()[:200]
                if not t.get('raw'):
                    html = os.path.join(FILES, slug(t['final']) + '.html')
                    open(html, 'w', encoding='utf-8').write(pg.content())
                    t['raw'] = os.path.relpath(html, OUT)
                    t.pop('error', None)
            except Exception as e:      # noqa: BLE001 - keep going
                t['render_error'] = str(e).splitlines()[0][:200]
            finally:
                pg.close()
            if i % 20 == 0:
                print('  rendered %d/%d' % (i, len(todo)), flush=True)
                save(todo_all)
        b.close()


def save(ts):
    json.dump(ts, open(STATE, 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)


def write_index(ts):
    with open(os.path.join(OUT, 'index.csv'), 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['codes', 'link text', 'url', 'status', 'file',
                    'page pdf', 'bytes', 'note'])
        for t in sorted(ts, key=lambda t: code_key(t['codes'][0])):
            w.writerow([' '.join(t['codes']), t['text'], t['final'],
                        t['status'], t.get('raw', ''), t.get('page_pdf', ''),
                        t.get('bytes', ''),
                        t.get('error') or t.get('render_error') or ''])
    ok = sum(1 for t in ts if t.get('raw') or t.get('page_pdf'))
    with open(os.path.join(OUT, 'index.md'), 'w', encoding='utf-8') as f:
        f.write('# Private copy of the linked material\n\n'
                'Made %s for personal use. Most of these works are under '
                'copyright: keep this archive private.\n\n'
                '%d of %d targets saved. `index.csv` maps the short codes '
                '(sharov.me/r/<code>) to the files.\n\n'
                % (datetime.date.today().isoformat(), ok, len(ts)))
        f.write('| codes | link | saved |\n|---|---|---|\n')
        for t in sorted(ts, key=lambda t: code_key(t['codes'][0])):
            files = ', '.join('[%s](%s)' % (os.path.basename(x), x)
                              for x in (t.get('raw'), t.get('page_pdf')) if x)
            f.write('| %s | %s | %s |\n' % (
                ' '.join(t['codes']), t['text'].replace('|', '/')[:70],
                files or 'not saved: ' + (t.get('error') or '')))
    return ok


def code_key(c):
    v, n = c.split('-')
    return (int(v), int(n.lstrip('c')))


def main():
    global todo_all
    os.makedirs(FILES, exist_ok=True)
    old = {}
    if os.path.exists(STATE):
        old = {t['final']: t for t in json.load(open(STATE, encoding='utf-8'))}
    ts = []
    for t in targets():
        o = old.get(t['final'], {})
        o.update({k: t[k] for k in ('codes', 'status', 'text', 'original')})
        o['final'] = t['final']
        ts.append(o)
    todo_all = ts
    retry = '--retry-failed' in sys.argv
    need = [t for t in ts if not t.get('raw') or (retry and t.get('error'))]
    print('%d targets, %d to download' % (len(ts), len(need)), flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        for i, _ in enumerate(ex.map(fetch, need), 1):
            if i % 50 == 0:
                print('  downloaded %d/%d' % (i, len(need)), flush=True)
                save(ts)
    save(ts)
    pages = [t for t in ts if not t.get('page_pdf') and
             (not t.get('raw') or t['raw'].endswith('.html'))]
    print('%d pages to render' % len(pages), flush=True)
    render_all(pages)
    save(ts)
    ok = write_index(ts)
    print('saved %d of %d targets; see mirror/index.md' % (ok, len(ts)))


todo_all = []

if __name__ == '__main__':
    main()
