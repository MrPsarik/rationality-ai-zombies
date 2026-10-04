#!/usr/bin/env python3
"""Prepare the six print volumes from the original .tex sources.

The original sources are never modified.  This script writes, for every
volume N, build/src/volN-body.tex (the essays, with essay labels, internal
cross references and external-link footnotes inserted) and
build/src/volN-meta.tex (title, starting counters, cross-volume imports).

Links are placed from links/placements.json (see tools/place_links.py) and
the short-URL codes come from links/links.json.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import links_tex  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build', 'src')

VOLUMES = [
    # (number, title, short spine title, [(file, start-marker or None)])
    (1, 'Map and Territory', 'Map and Territory',
     [('front.tex', r'\mysectionnn{Preface}'), ('map_and_territory.tex', None)]),
    (2, 'How to Actually Change Your Mind', 'How to Actually Change Your Mind',
     [('change_mind.tex', None)]),
    (3, 'The Machine in the Ghost', 'The Machine in the Ghost',
     [('machine_in_ghost.tex', None)]),
    (4, 'Mere Reality', 'Mere Reality', [('mere_reality.tex', None)]),
    (5, 'Mere Goodness', 'Mere Goodness', [('mere_goodness.tex', None)]),
    (6, 'Becoming Stronger', 'Becoming Stronger',
     [('becoming_stronger.tex', None)]),
]

HEAD_RE = re.compile(
    r'\\(mysection|mysectionnn)\{((?:[^{}]|\{[^{}]*\})*)\}'
    r'|\\mysectiontwo\{((?:[^{}]|\{[^{}]*\})*)\}\{')


def slug(title):
    t = re.sub(r'\\[a-zA-Z]+', '', title)
    t = re.sub(r"``|''|[`'{}\\]", '', t)
    t = re.sub(r'[^A-Za-z0-9]+', '-', t).strip('-').lower()
    return t


def read_volume_source(files):
    parts = []
    for fn, marker in files:
        text = open(os.path.join(ROOT, fn), encoding='utf-8').read()
        if marker:
            i = text.index(marker)
            text = text[i:]
        parts.append(text)
    return '\n'.join(parts)


def scan_essays():
    """Return {vol: [essay dicts]} with global 2015 numbering."""
    num = 0
    chap = 0
    out = {}
    for vol, title, _, files in VOLUMES:
        src = read_volume_source(files)
        essays = []
        start_chap, start_num = chap, num
        for m in re.finditer(HEAD_RE.pattern + r'|\\chapter\{', src):
            s = m.group(0)
            if s.startswith(r'\chapter'):
                chap += 1
                continue
            if m.group(1) == 'mysection':
                num += 1
                t = m.group(2)
                eid = 'e%d' % num
            else:
                t = m.group(2) if m.group(1) else m.group(3)
                eid = slug(t)
            essays.append({'id': eid, 'title': t, 'number': num
                           if m.group(1) == 'mysection' else None,
                           'pos': m.start(), 'end': m.end(),
                           'chapter': chap})
        out[vol] = {'essays': essays, 'start_chapter': start_chap,
                    'start_number': start_num, 'src': src}
    return out


def old_labels(src):
    return re.findall(r'\\label\{([^}]+)\}', src)


def main():
    os.makedirs(BUILD, exist_ok=True)
    data = scan_essays()
    # map of every old \label to its volume (for \pageref conversion)
    label_vol = {}
    for vol in data:
        for lab in old_labels(data[vol]['src']):
            label_vol[lab] = vol
    essays_index = {}
    for vol in data:
        for e in data[vol]['essays']:
            essays_index[e['id']] = {'vol': vol, 'title': e['title'],
                                     'number': e['number']}
    ESSAYS.update(essays_index)
    placements = load_placements()
    for vol, title, short, files in VOLUMES:
        d = data[vol]
        body = transform(vol, d, label_vol, placements.get(str(vol), []))
        with open(os.path.join(BUILD, 'vol%d-body.tex' % vol), 'w',
                  encoding='utf-8') as f:
            f.write(body)
        with open(os.path.join(BUILD, 'vol%d-meta.tex' % vol), 'w',
                  encoding='utf-8') as f:
            f.write('\\def\\RAZVolume{%d}\n' % vol)
            f.write('\\def\\RAZBookTitle{%s}\n' % title)
            f.write('\\def\\RAZShortTitle{%s}\n' % short)
            f.write('\\setcounter{chapter}{%d}\n' % d['start_chapter'])
            f.write('\\setcounter{mysection}{%d}\n' % d['start_number'])
            for other in range(1, 7):
                if other != vol:
                    f.write('\\zexternaldocument[v%d-]{build/tex/vol%d}\n'
                            % (other, other))
    with open(os.path.join(ROOT, 'build', 'essays.json'), 'w') as f:
        json.dump(essays_index, f, indent=1)
    with open(os.path.join(ROOT, 'build', 'discussions.json'), 'w') as f:
        json.dump(DISCUSSIONS, f, indent=1, ensure_ascii=False)
    with open(os.path.join(ROOT, 'build', 'links_registry.json'), 'w') as f:
        json.dump({'links': REGISTRY, 'count': LINKCOUNT}, f, indent=1,
                  ensure_ascii=False)
    with open(os.path.join(ROOT, 'build', 'labels.json'), 'w') as f:
        json.dump(label_vol, f, indent=1)


REGISTRY = []
LINKCOUNT = {}
ESSAYS = {}
LW = json.load(open(os.path.join(ROOT, 'links', 'lw_posts.json'),
                    encoding='utf-8'))
DISCUSSIONS = {}


def load_placements():
    p = os.path.join(ROOT, 'links', 'placements.json')
    if not os.path.exists(p):
        return {}
    return json.load(open(p, encoding='utf-8'))


def transform(vol, d, label_vol, placements):
    src = d['src']
    # 1. external links / internal refs from the EPUB, placed by context
    src = apply_placements(vol, src, placements)
    # 2. essay labels right after each heading
    out = []
    last = 0
    for m in re.finditer(HEAD_RE.pattern, src):
        if m.group(0).startswith(r'\mysectiontwo'):
            # skip the second argument
            depth, i = 1, m.end()
            while depth:
                c = src[i]
                depth += c == '{'
                depth -= c == '}'
                i += 1
            end = i
            t = m.group(3)
            eid = slug(t)
        else:
            end = m.end()
            if m.group(1) == 'mysection':
                eid = None  # numbered, computed below
            else:
                eid = slug(m.group(2))
        out.append(src[last:end])
        out.append('\\RAZlabel{%s}' % (eid or '@NUM@'))
        last = end
    out.append(src[last:])
    src = ''.join(out)
    n = d['start_number']

    def num(_):
        nonlocal n
        n += 1
        return 'e%d' % n
    src = re.sub('@NUM@', num, src)
    # 2b. discussion QR code (LessWrong comments) at every essay
    k = 0

    def disc(m):
        nonlocal k
        eid = m.group(1)
        post = LW['posts'].get(eid)
        if not post:
            return m.group(0)
        k += 1
        code = '%d-c%d' % (vol, k)
        DISCUSSIONS[code] = {'vol': vol, 'essay': eid, 'url': post['url'],
                             'title': post['title']}
        return m.group(0) + '\\RAZdiscuss{%s}' % code
    src = re.sub(r'\\RAZlabel\{([^}]+)\}', disc, src)
    # 2c. Part divider illustrations
    c = d['start_chapter']

    def chap(m):
        nonlocal c
        c += 1
        return m.group(0) + '\n\\RAZpartillus{%02d}\n' % c
    src = re.sub(r'\\chapter\{[^}]*\}', chap, src)
    # 3. old labels: also as zref labels so other volumes can see them
    src = re.sub(r'\\label\{([^}]+)\}', r'\\RAZoldlabel{\1}', src)
    # 4. \pageref -> (vol. X, p. N) scheme
    src = convert_pagerefs(vol, src, label_vol)
    return src


def convert_pagerefs(vol, src, label_vol):
    def rep(m):
        lab = m.group(2)
        v = label_vol.get(lab)
        if v is None:
            sys.exit('unknown \\pageref label %s' % lab)
        return '\\RAZoldpage{%d}{%s}' % (v, lab)
    # "pg \pageref", "pg.\ \pageref", "page \pageref", bare \pageref
    return re.sub(r'(\b(?:pg\.?\\?|page)\s*~?)?\\pageref\{([^}]+)\}', rep, src)


def apply_placements(vol, src, placements):
    """External links (\\url in the source and hyperlinks of the ebook) and
    internal ebook links to other essays.

    placements: [{kind: ext|int, needle: unique source text that ends where
    the link text ends, url | target, text}] from tools/place_links.py."""
    sites = links_tex.url_sites(src)
    inserts = []
    for p in placements:
        i = src.find(p['needle'])
        if i < 0 or src.find(p['needle'], i + 1) >= 0:
            sys.exit('placement not unique/not found in vol %d: %r'
                     % (vol, p['needle']))
        pos = i + len(p['needle'])
        if p['kind'] == 'ext':
            sites.append({'pos': pos, 'end': pos, 'url': p['url'],
                          'text': p['text'], 'kind': 'ext'})
        else:
            tv = ESSAYS[p['target']]['vol']
            inserts.append((pos, '~\\RAZref{%d}{%s}' % (tv, p['target'])))
    # internal references first (pure insertions, back to front) so that
    # footnote spans seen by the external-link rewrite are final
    for pos, text in sorted(inserts, reverse=True):
        src = src[:pos] + text + src[pos:]
        for s in sites:
            if s['pos'] >= pos:
                s['pos'] += len(text)
                s['end'] += len(text)
    reg = links_tex.Registry(vol)
    src = links_tex.rewrite(src, sites, reg)
    REGISTRY.extend(reg.items)
    LINKCOUNT[vol] = reg.n
    return src


if __name__ == '__main__':
    main()
