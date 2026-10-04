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
    t = norm_text(t).lower()
    t = re.sub(r'^(interlude|part [a-z])\s*[:.]?\s*', '', t)
    t = re.sub(r'\s*by rob bensinger$', '', t)
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def url_key(u):
    u = links_tex.unescape_url(u).lower()
    u = re.sub(r'^https?://(www\.)?', '', u)
    return u.rstrip('/').split('#')[0]


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
    proj = {}
    for vol, *_ in VOLUMES:
        src = data[vol]['src']
        proj[vol] = plain_with_map(src)
    placements = {str(v): [] for v, *_ in VOLUMES}
    notplaced = []
    stats = Counter()
    used_needles = set()
    for rec in links:
        t = rec['type']
        if t not in ('internal', 'external'):
            stats['skipped_' + t] += 1
            continue
        stats['total'] += 1
        here = by_title.get(tnorm(rec['essay']))
        vols = [here[0]] if here else [v for v, *_ in VOLUMES]
        target = None
        if t == 'internal':
            target = by_title.get(tnorm(rec.get('target_title', ''))) or \
                chapters.get(tnorm(rec.get('target_title', '')))
            if not target:
                notplaced.append(dict(rec, reason='target is not an essay of'
                                      ' the book: %r' % rec.get('target_title')))
                continue
            if here and target == here:
                notplaced.append(dict(rec, reason='link to the essay itself'))
                continue
        hit = None
        for vol in vols:
            text, offs = proj[vol]
            lo, hi = 0, len(text)
            if here:
                a, b = regions[here]
                lo = next(i for i, o in enumerate(offs) if o >= a)
                hi = next((i for i, o in enumerate(offs) if o >= b), len(text))
            hit = locate(text[lo:hi], rec)
            if hit is not None:
                s, e = hit[0] + lo, hit[1] + lo
                hit = (vol, s, e)
                break
        if hit is None:
            notplaced.append(dict(rec, reason='link text not found in the'
                                  ' .tex essay (text differs)'))
            continue
        vol, s, e = hit
        src = data[vol]['src']
        offs = proj[vol][1]
        tex_s, tex_e = offs[s], offs[e - 1] + 1
        # step over closing braces and closing quotes after the link text
        while tex_e < len(src) and (src[tex_e] == '}' or src.startswith("''", tex_e)):
            tex_e += 2 if src.startswith("''", tex_e) else 1
        if t == 'external':
            near = src[max(0, tex_s - 300):tex_e + 900]
            if any(url_key(u) == url_key(rec['href'])
                   for u in re.findall(r'\\url\{([^}]*)\}', near)):
                stats['placed_existing_url'] += 1
                stats['placed'] += 1
                stats['external'] += 1
                continue
        needle = make_needle(src, tex_s, tex_e)
        if needle is None or (vol, needle) in used_needles:
            notplaced.append(dict(rec, reason='no unique anchor in the .tex'))
            continue
        used_needles.add((vol, needle))
        item = {'kind': 'ext' if t == 'external' else 'int', 'needle': needle,
                'text': rec['text'], 'essay': rec['essay']}
        if t == 'external':
            item['url'] = rec['href']
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
           'notplaced': stats['notplaced'],
           'skipped': {k[8:]: v for k, v in stats.items() if k.startswith('skipped_')},
           'not_placed': [{k: r.get(k) for k in ('essay', 'text', 'href',
                                                 'target_title', 'reason')}
                          for r in notplaced]}
    json.dump(rep, open(os.path.join(ROOT, 'links', 'placements_report.json'),
                        'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('EPUB links: %d; placed %d (internal %d, external %d of which %d already'
          ' in the text as URL); not placed %d; skipped %s'
          % (rep['total'], rep['placed'], rep['internal'], rep['external'],
             rep['already_in_text'], rep['notplaced'], rep['skipped']))
    for r in notplaced:
        print('  NOT PLACED [%s] %r in %r: %s' % (r['type'], r['text'],
                                                   r['essay'], r['reason']))


def locate(text, rec):
    """(start, end) of the link text in the projected essay text."""
    lt = norm_text(rec['text'])
    if not lt:
        return None
    before = norm_text(rec.get('before', ''))
    after = norm_text(rec.get('after', ''))
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
    # case-insensitive last resort
    low = text.lower()
    pos = find_unique(low, lt.lower())
    if pos is not None:
        return pos, pos + len(lt)
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
