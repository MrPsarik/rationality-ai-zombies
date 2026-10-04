"""Rewrite external links in LaTeX source into the print-edition scheme.

Every external link gets a code "<volume>-<n>" (numbered in text order
within the volume) and is printed as the short URL sharov.me/r/<code>
together with a QR code in a footnote:

* \\url{...} inside an existing footnote: the URL text is replaced by the
  short URL and the footnote gets QR codes at its right;
* \\url{...} in running text: the domain stays in the text and a new QR
  footnote is added;
* a hyperlink of the ebook (placed by context, see place_links.py): a new QR
  footnote after the link text (or, inside a footnote, the QR is added to
  that footnote and the short URL follows the link text).
"""
import json
import os
import re
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(ROOT, 'links', 'url_status.json')


def load_status():
    if os.path.exists(STATUS_FILE):
        return json.load(open(STATUS_FILE, encoding='utf-8'))
    return {}


STATUS = load_status()


def unescape_url(u):
    return re.sub(r'\\([%_#&~$])', r'\1', u).replace('\\textasciitilde{}', '~')


def tex_escape(s):
    s = s.replace('\\', '\\textbackslash{}')
    for c in '%&#_${}':
        s = s.replace(c, '\\' + c)
    return s.replace('~', '\\textasciitilde{}').replace('^', '\\^{}')


def domain(url):
    d = urlsplit(url).netloc.lower()
    return d[4:] if d.startswith('www.') else d


def label_for(url):
    """Title of the target (from the link check) or its domain."""
    st = STATUS.get(url) or {}
    if st.get('status') == 'archived':
        orig = re.sub(r'^https?://web\.archive\.org/web/\d+/', '', url)
        return '%s, archived copy' % tex_escape(domain(orig))
    t = (st.get('title') or '').strip()
    if t and len(t) <= 90:
        return '%s \\textbullet\\ %s' % (tex_escape(t), tex_escape(domain(st.get('final') or url)))
    return tex_escape(domain(st.get('final') or url))


def footnote_spans(src):
    """(start, body_start, body_end, end) of every \\footnote / \\footnotetext."""
    spans = []
    for m in re.finditer(r'\\footnote(?:text)?(?:\[[^\]]*\])?\{', src):
        depth, i = 1, m.end()
        while depth and i < len(src):
            c = src[i]
            if c == '\\':
                i += 2
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        spans.append((m.start(), m.end(), i - 1, i))
    return spans


def find_span(spans, pos):
    for s in spans:
        if s[1] <= pos < s[2]:
            return s
    return None


class Registry:
    """Codes in text order for one volume."""

    def __init__(self, vol, start=0):
        self.vol = vol
        self.n = start
        self.items = []

    def new(self, url, text, kind, where):
        self.n += 1
        code = '%d-%d' % (self.vol, self.n)
        self.items.append({'code': code, 'vol': self.vol, 'url': url,
                           'text': text, 'kind': kind, 'where': where})
        return code


def rewrite(src, sites, reg, where_default='body'):
    """sites: list of dicts with 'pos', 'end' (span to replace, may be
    empty for insertions), 'url', 'text', 'kind' ('url' or 'ext').
    Returns the new source."""
    sites = sorted(sites, key=lambda s: s['pos'])
    spans = footnote_spans(src)
    # assign codes in text order
    for s in sites:
        fn = find_span(spans, s['pos'])
        s['fn'] = fn
        where = 'footnote' if fn else where_default
        s['code'] = reg.new(s['url'], s['text'], s['kind'], where)
    edits = []
    by_fn = {}
    for s in sites:
        if s['fn']:
            by_fn.setdefault(s['fn'], []).append(s)
        else:
            edits.append((s['pos'], s['end'], body_replacement(s)))
    for fn, ss in by_fn.items():
        start, bstart, bend, end = fn
        body = src[bstart:bend]
        rest = re.sub(r'\\comment\{[^}]*\}|\\url\{[^}]*\}|[\s.,;]', '',
                      body)
        if not rest and len(ss) == 1 and ss[0]['kind'] == 'url':
            # footnote that is only a URL: short address + title/domain
            s = ss[0]
            edits.append((start, end, '%s\\RAZqrfoot{%s}{\\RAZshort{%s}'
                          '\\\\[0.2ex]{\\itshape %s}}}' % (
                              src[start:bstart], s['code'], s['code'],
                              label_for(s['url']))))
            continue
        for s in sorted(ss, key=lambda s: s['pos'], reverse=True):
            a, b = s['pos'] - bstart, s['end'] - bstart
            body = body[:a] + footnote_inner(s) + body[b:]
        codes = ','.join(s['code'] for s in ss)
        head = src[start:bstart]
        edits.append((start, end,
                      '%s\\RAZqrfoot{%s}{%s}}' % (head, codes, body)))
    # back to front; at the same start the longer replacement goes first,
    # so that an insertion there does not shift it
    for a, b, rep in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        src = src[:a] + rep + src[b:]
    return src


def body_replacement(s):
    if s['kind'] == 'url':
        # the URL printed in running text: keep the domain, add QR footnote
        return '\\mbox{%s}\\RAZlinknote{%s}{%s}' % (
            tex_escape(domain(s['url'])), s['code'], label_for(s['url']))
    # ebook hyperlink: footnote after the link text
    return '\\RAZlinknote{%s}{%s}' % (s['code'], label_for(s['url']))


def footnote_inner(s):
    if s['kind'] == 'url':
        return '\\RAZurl{%s}' % s['code']
    if s['kind'] == 'exturl':
        return ' \\RAZurl{%s}' % s['code']
    return ' (\\RAZurl{%s})' % s['code']


def plain(t):
    t = re.sub(r'\\comment\{[^}]*\}', '', t)
    t = re.sub(r'\\(textit|emph|textsc|textbf|em)\b', '', t)
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    t = t.replace('``', '\u201c').replace("''", '\u201d').replace('---', '\u2014')
    t = t.replace('--', '\u2013').replace('~', ' ').replace('\\', '')
    t = re.sub(r'[{}]', '', t)
    return ' '.join(t.split())


def cited_title(src, pos):
    """The work cited just before a URL: last quoted or italic title."""
    before = src[max(0, pos - 600):pos]
    cut = max(before.rfind('\\footnote'), before.rfind('\\RAZbibitem'))
    if cut < 0:
        return ''               # not a citation
    before = before[cut:]
    ms = list(re.finditer(r"``((?:(?!``).)+?)''", before, re.S)) or \
        list(re.finditer(r'\\textit\{((?:[^{}]|\{[^{}]*\})+)\}', before, re.S))
    if not ms:
        return ''
    return plain(ms[-1].group(1)).rstrip(',.')


def url_sites(src):
    out = []
    for m in re.finditer(r'\\url\{([^}]*)\}', src):
        u = unescape_url(m.group(1))
        out.append({'pos': m.start(), 'end': m.end(), 'url': u,
                    'text': cited_title(src, m.start()) or u, 'kind': 'url'})
    return out
