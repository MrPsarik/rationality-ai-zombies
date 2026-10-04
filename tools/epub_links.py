#!/usr/bin/env python3
"""Extract every hyperlink of the 2015 EPUB.

usage: epub_links.py path/to/rationality.epub

Writes links/epub_links.json: one record per <a href> in reading order:
  file, essay (title of the essay the link is in), text, href,
  type: external | internal | footnote | toc | self
  target_file, target_anchor, target_title (internal links)
  before / after: plain text around the link in its paragraph
  in_note: link sits inside a footnote
"""
import json
import os
import posixpath
import re
import sys
import zipfile
from urllib.parse import unquote, urldefrag

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from texplain import norm_text  # noqa: E402

BLOCK = ('p', 'li', 'blockquote', 'div', 'td', 'dd', 'dt', 'aside',
         'h1', 'h2', 'h3', 'h4', 'section')


def spine(z):
    container = BeautifulSoup(z.read('META-INF/container.xml'), 'xml')
    opf_path = container.find('rootfile')['full-path']
    opf = BeautifulSoup(z.read(opf_path), 'xml')
    base = posixpath.dirname(opf_path)
    items = {i['id']: i for i in opf.find_all('item')}
    order = [posixpath.normpath(posixpath.join(base, unquote(items[r['idref']]['href'])))
             for r in opf.find('spine').find_all('itemref')]
    navs = {posixpath.normpath(posixpath.join(base, unquote(i['href'])))
            for i in items.values()
            if 'nav' in (i.get('properties') or '') or
            i.get('media-type') == 'application/x-dtbncx+xml'}
    return order, navs


def heading(soup):
    for tag in ('h1', 'h2', 'h3'):
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            return norm_text(h.get_text(' '))
    t = soup.find('title')
    return norm_text(t.get_text(' ')) if t else ''


def is_note(a):
    t = ' '.join([a.get('epub:type', ''), a.get('role', ''),
                  ' '.join(a.get('class', []))]).lower()
    href = a.get('href', '')
    return ('noteref' in t or 'footnote' in t or 'backlink' in t or
            'doc-noteref' in t or 'doc-backlink' in t or
            re.search(r'#(fn|ftn|footnote|note|nref|fnref|_ftn|en)[-_:.]?\w*',
                      href, re.I) is not None and len(a.get_text(strip=True)) <= 4)


def in_footnote(a):
    for p in a.parents:
        t = ' '.join([p.get('epub:type', ''), p.get('role', ''),
                      ' '.join(p.get('class', [])) if p.get('class') else '',
                      p.get('id', '')]).lower()
        if re.search(r'footnote|endnote|rearnote|doc-endnote|\bnotes?\b|fn\d', t):
            return True
    return False


def block_of(a):
    for p in a.parents:
        if p.name in BLOCK:
            return p
    return a.parent


def context(a):
    blk = block_of(a)
    marker = ''
    a.insert_before(marker)
    a.insert_after(marker)
    text = blk.get_text('')
    a.previous_sibling.extract()
    a.next_sibling.extract()
    parts = text.split(marker)
    before = norm_text(parts[0]) if len(parts) == 3 else ''
    after = norm_text(parts[2]) if len(parts) == 3 else ''
    return before[-120:], after[:80]


def main():
    epub = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'links', 'rationality.epub')
    z = zipfile.ZipFile(epub)
    order, navs = spine(z)
    titles, ids = {}, {}
    soups = {}
    for f in order:
        s = BeautifulSoup(z.read(f), 'lxml')
        soups[f] = s
        titles[f] = heading(s)
        for el in s.find_all(id=True):
            h = el if el.name in ('h1', 'h2', 'h3') else el.find(['h1', 'h2', 'h3'])
            ids[(f, el['id'])] = norm_text(h.get_text(' ')) if h else None
    out = []
    for f in order:
        s = soups[f]
        is_toc = f in navs or re.search(r'(toc|contents|nav)', f, re.I)
        cur = titles[f]
        for el in s.find_all(['h1', 'h2', 'h3', 'a']):
            if el.name != 'a':
                cur = norm_text(el.get_text(' ')) or cur
                continue
            href = el.get('href')
            if href is None:
                continue
            rec = {'file': f, 'essay': cur, 'text': norm_text(el.get_text(' ')),
                   'href': href}
            if re.match(r'(?i)(https?|ftp|mailto):', href):
                rec['type'] = 'external'
            else:
                path, frag = urldefrag(href)
                tf = posixpath.normpath(posixpath.join(posixpath.dirname(f),
                                                       unquote(path))) if path else f
                rec.update(target_file=tf, target_anchor=frag,
                           target_title=ids.get((tf, frag)) or titles.get(tf, ''))
                if is_toc:
                    rec['type'] = 'toc'
                elif is_note(el):
                    rec['type'] = 'footnote'
                elif tf == f and frag and not ids.get((tf, frag)):
                    rec['type'] = 'self'
                else:
                    rec['type'] = 'internal'
            rec['in_note'] = in_footnote(el)
            rec['before'], rec['after'] = context(el)
            out.append(rec)
    json.dump(out, open(os.path.join(ROOT, 'links', 'epub_links.json'), 'w',
                        encoding='utf-8'), indent=1, ensure_ascii=False)
    from collections import Counter
    print('EPUB: %d files, %d links: %s' % (len(order), len(out),
                                           dict(Counter(r['type'] for r in out))))


if __name__ == '__main__':
    main()
