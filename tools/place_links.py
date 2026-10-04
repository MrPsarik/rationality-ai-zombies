#!/usr/bin/env python3
"""Place the hyperlinks of the EPUB in the .tex text.

Reads links/epub_links.json (tools/epub_links.py) and finds, for every
internal and external link, the place in the volume source where its link
text ends, using the text before the link as context.  Output:

  links/placements.json         {volume: [{kind, needle, url|target, text}]}
                                (read by tools/prepare.py)
  links/placements_report.json  counts, and every link not placed with the
                                reason

A "needle" is a piece of the original .tex source, unique within its volume,
that ends exactly where the reference / QR footnote is inserted.

External links whose URL is already printed in the .tex at that place
(\\url in a footnote or the bibliography) are not inserted twice: they are
counted as placed ("already in text") and use the existing QR code.
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare import ROOT, VOLUMES, read_volume_source, scan_essays, HEAD_RE  # noqa
from texplain import plain_with_map, norm_text  # noqa: E402
import links_tex  # noqa: E402


def tnorm(t):
    if '\\' in t or '``' in t:
        t = plain_with_map(t)[0]
    t = norm_text(t).lower()
    t = re.sub(r'^(interlude|part [a-z])\s*[:.]?\s*', '', t)
    t = re.sub(r'^the\s+', '', t)
    t = re.sub(r'\s*by rob bensinger$', '', t)
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def enorm(t):
    """Title as the EPUB writes it: "13 Making Beliefs Pay Rent"."""
    return tnorm(re.sub(r'^\s*\d+\s+', '', norm_text(t)))


def url_key(u):
    u = links_tex.unescape_url(u).lower()
    u = re.sub(r'^https?://(www\.)?', '', u)
    return u.rstrip('/').split('#')[0]


def same_url(a, b):
    a, b = url_key(a), url_key(b)
    return a == b or (min(len(a), len(b)) > 30 and (a.startswith(b) or b.startswith(a)))


def main():
    links = json.load(open(os.path.join(ROOT, 'links', 'epub_links.json'),
                           encoding='utf-8'))
    data = scan_essays()
    # essay title -> (vol, essay id, region)
    by_title = {}
    regions = {}
    chapters = {}
    for vol, *_ in VOLUMES:
        src = data[vol]['src']
        es = data[vol]['essays']
        for k, e in enumerate(es):
            end = es[k + 1]['pos'] if k + 1 < len(es) else len(src)
            regions[(vol, e['id'])] = (e['pos'], end)
            by_title.setdefault(tnorm(e['title']), (vol, e['id']))
        for m in re.finditer(r'\\chapter\{([^}]*)\}', src):
            # a Part: link to it lands on its first essay
            nxt = [e for e in es if e['pos'] > m.start()]
            if nxt:
                chapters.setdefault(tnorm(m.group(1)), (vol, nxt[0]['id']))
    proj, projbody = {}, {}
    for vol, *_ in VOLUMES:
        src = data[vol]['src']
        proj[vol] = plain_with_map(src)
        projbody[vol] = plain_with_map(src, skip_notes=True)
    placements = {str(v): [] for v, *_ in VOLUMES}
    notplaced = []
    stats = Counter()
    used_needles = set()
    # word-by-word runs: every word of a phrase links to another essay
    runs = {}
    for rec in links:
        if rec.get('run') is not None:
            runs.setdefault(rec['run'], []).append(rec)
    wordrun = {k for k, r in runs.items()
               if sum(len(x['text'].split()) == 1 for x in r) >= 0.8 * len(r)}
    bibsrc = open(os.path.join(ROOT, 'bibliography.tex'), encoding='utf-8').read()
    bibtext, biboffs = plain_with_map(bibsrc)
    placements['bib'] = []
    for rec in links:
        t = rec['type']
        if t == 'external' and tnorm(rec['essay']) == 'bibliography':
            stats['total'] += 1
            stats['external'] += 1
            if any(same_url(u, rec['href'])
                   for u in re.findall(r'\\url\{([^}]*)\}', bibsrc)):
                stats['placed_existing_url'] += 1
                stats['placed'] += 1
                continue
            hit = locate(bibtext, rec)
            if hit is None:
                stats['external'] -= 1
                notplaced.append(dict(rec, reason='entry not found in bibliography.tex'))
                continue
            e = biboffs[hit[1] - 1] + 1
            needle = make_needle(bibsrc, biboffs[hit[0]], e)
            url = re.sub(r'^https?://dx\.doi\.org/', 'https://doi.org/', rec['href'])
            placements['bib'].append({'kind': 'ext', 'needle': needle,
                                      'url': url, 'text': rec['text']})
            stats['placed'] += 1
            continue
        if rec.get('run') in wordrun:
            r = runs[rec['run']]
            if rec is not r[-1]:
                continue        # placed together with the last word
            rec = dict(rec, members=r)
            t = 'run'
            stats['total'] += len(r) - 1
        elif t not in ('internal', 'external'):
            stats['skipped_' + t] += 1
            continue
        stats['total'] += 1
        here = by_title.get(enorm(rec['essay']))
        vols = [here[0]] if here else [v for v, *_ in VOLUMES]
        target = None
        if t == 'run':
            members = []
            for x in rec['members']:
                tg = by_title.get(enorm(x.get('target_title', ''))) or \
                    chapters.get(enorm(x.get('target_title', '')))
                if tg:
                    members.append({'word': x['text'], 'target': tg[1]})
            rec['resolved'] = members
        if t == 'internal':
            target = by_title.get(enorm(rec.get('target_title', ''))) or \
                chapters.get(enorm(rec.get('target_title', '')))
            if not target:
                notplaced.append(dict(rec, reason='target is not an essay of'
                                      ' the book: %r' % rec.get('target_title')))
                continue
            if here and target == here:
                notplaced.append(dict(rec, reason='link to the essay itself'))
                continue
        urltext = t == 'external' and re.match(r'(?i)(https?://|www\.)', rec['text'])
        if t == 'external' and here:
            a, b = regions[here]
            region = data[here[0]]['src'][a:b]
            if any(same_url(u, rec['href'])
                   for u in re.findall(r'\\url\{([^}]*)\}', region)):
                stats['placed_existing_url'] += 1
                stats['placed'] += 1
                stats['external'] += 1
                continue
        hit = None
        for vol in vols:
            text, offs = (proj if rec.get('in_note') else projbody)[vol]
            lo, hi = 0, len(text)
            if here:
                a, b = regions[here]
                lo = next(i for i, o in enumerate(offs) if o >= a)
                hi = next((i for i, o in enumerate(offs) if o >= b), len(text))
            hit = locate(text[lo:hi], rec)
            if hit is None and urltext:
                # the URL itself is not printed in the .tex: anchor on the
                # citation text before it
                hit = locate_before(text[lo:hi], rec)
            if hit is not None:
                s, e = hit[0] + lo, hit[1] + lo
                hit = (vol, s, e)
                break
        if hit is None and t == 'internal' and here:
            a, b = regions[here]
            region = data[here[0]]['src'][a:b]
            words = r'\s+'.join(map(re.escape, rec['text'].split()))
            if re.search(words + r'\s*\(page\s*\\pageref', region):
                stats['placed_existing_pageref'] += 1
                stats['placed'] += 1
                stats['internal'] += 1
                continue
        if hit is None and tnorm(rec['essay']) == 'rationality':
            notplaced.append(dict(rec, reason='title page of the ebook; this'
                                  ' edition has its own license page, which'
                                  ' prints the address'))
            continue
        if hit is None and re.match(r'Figure \d', rec['text']):
            notplaced.append(dict(rec, reason='link to a figure; the figure'
                                  ' number is printed in the text'))
            continue
        if hit is None:
            notplaced.append(dict(rec, reason='link text not found in the'
                                  ' .tex essay (text differs)'))
            continue
        vol, s, e = hit
        src = data[vol]['src']
        offs = (proj if rec.get('in_note') else projbody)[vol][1]
        tex_s, tex_e = offs[s], offs[e - 1] + 1
        # step over closing braces and closing quotes after the link text
        while tex_e < len(src) and (src[tex_e] == '}' or src.startswith("''", tex_e)):
            tex_e += 2 if src.startswith("''", tex_e) else 1
        if t == 'external':
            near = src[max(0, tex_s - 300):tex_e + 900]
            if any(same_url(u, rec['href'])
                   for u in re.findall(r'\\url\{([^}]*)\}', near)):
                stats['placed_existing_url'] += 1
                stats['placed'] += 1
                stats['external'] += 1
                continue
        if t == 'internal' and '\\pageref' in src[tex_e:tex_e + 60]:
            # the .tex already gives a page reference right here
            stats['placed_existing_pageref'] += 1
            stats['placed'] += 1
            stats['internal'] += 1
            continue
        needle = make_needle(src, tex_s, tex_e)
        if needle is None or (vol, needle) in used_needles:
            notplaced.append(dict(rec, reason='no unique anchor in the .tex'))
            continue
        used_needles.add((vol, needle))
        item = {'kind': {'external': 'ext', 'internal': 'int', 'run': 'run'}[t],
                'needle': needle, 'text': rec['text'], 'essay': rec['essay']}
        if t == 'run':
            item['members'] = rec['resolved']
            item['text'] = ' '.join(x['text'] for x in rec['members'])
            stats['internal'] += len(rec['members'])
            stats['placed'] += len(rec['members'])
            stats['runs'] += 1
            placements[str(vol)].append(item)
            continue
        if t == 'external':
            item['url'] = rec['href']
            if urltext:
                item['urltext'] = True
            stats['external'] += 1
        else:
            item['target'] = target[1]
            stats['internal'] += 1
        placements[str(vol)].append(item)
        stats['placed'] += 1
    stats['notplaced'] = len(notplaced)
    json.dump(placements, open(os.path.join(ROOT, 'links', 'placements.json'),
                               'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    rep = {'total': stats['total'], 'placed': stats['placed'],
           'internal': stats['internal'], 'external': stats['external'],
           'already_in_text': stats['placed_existing_url'],
           'already_pageref': stats['placed_existing_pageref'],
           'notplaced': stats['notplaced'],
           'skipped': {k[8:]: v for k, v in stats.items() if k.startswith('skipped_')},
           'not_placed': [{k: r.get(k) for k in ('essay', 'text', 'href',
                                                 'target_title', 'reason')}
                          for r in notplaced]}
    json.dump(rep, open(os.path.join(ROOT, 'links', 'placements_report.json'),
                        'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('EPUB links: %d; placed %d (internal %d, of which %d already had a'
          ' page reference; external %d, of which %d already printed as URL);'
          ' not placed %d; skipped %s'
          % (rep['total'], rep['placed'], rep['internal'],
             rep['already_pageref'], rep['external'], rep['already_in_text'],
             rep['notplaced'], rep['skipped']))
    for r in notplaced:
        print('  NOT PLACED [%s] %r in %r: %s' % (r['type'], r['text'],
                                                   r['essay'], r['reason']))


def locate(text, rec):
    """(start, end) of the link text in the projected essay text."""
    lt = norm_text(rec['text'])
    if not lt:
        return None
    # footnote numbers glued to words ("Inference1 and", "said:2") are
    # not in the .tex text
    before = re.sub(NOTEMARK, '', edge_norm(rec.get('before', '')))
    after = re.sub(NOTEMARK, '', edge_norm(rec.get('after', '')))
    for k in (60, 40, 25, 12, 0):
        key = (before[-k:] if k else '') + lt
        pos = find_unique(text, key)
        if pos is not None:
            return pos + len(key) - len(lt), pos + len(key)
    for k in (40, 20, 8):
        key = lt + after[:k]
        pos = find_unique(text, key)
        if pos is not None:
            return pos, pos + len(lt)
    # spacing-insensitive (math, symbols)
    nospace = [(i, c) for i, c in enumerate(text) if not c.isspace()]
    squeezed = ''.join(c for _, c in nospace).lower()
    key = ''.join(lt.split()).lower()
    pos = find_unique(squeezed, key)
    if pos is not None:
        return nospace[pos][0], nospace[pos + len(key) - 1][0] + 1
    # case-insensitive last resort
    low = text.lower()
    pos = find_unique(low, lt.lower())
    if pos is not None:
        return pos, pos + len(lt)
    return None


NOTEMARK = r'(?<=[A-Za-z.,;:!?"\')\]])(?<!\d[.,])\d+(?=\s|$)'


def edge_norm(t):
    """norm_text, but keep a single space at either edge."""
    n = norm_text(t)
    if n and t[:1].isspace():
        n = ' ' + n
    if n and t[-1:].isspace():
        n += ' '
    return n


def locate_before(text, rec):
    before = edge_norm(rec.get('before', '')).rstrip()
    for k in (60, 40, 25):
        key = before[-k:]
        if len(key) < 12:
            continue
        pos = find_unique(text, key)
        if pos is not None:
            return pos + len(key) - 1, pos + len(key)
    return None


def find_unique(text, key):
    i = text.find(key)
    if i < 0 or text.find(key, i + 1) >= 0:
        return None
    return i


def make_needle(src, s, e):
    start = s
    while start > max(0, s - 400):
        nd = src[start:e]
        if len(nd) >= 12 and src.count(nd) == 1:
            return nd
        start -= 8
    return None


if __name__ == '__main__':
    main()
