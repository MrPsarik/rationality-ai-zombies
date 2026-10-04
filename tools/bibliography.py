#!/usr/bin/env python3
"""Split bibliography.tex into one bibliography per volume.

An entry belongs to a volume when the volume's text cites the entry's title
(the footnotes cite works by author and title).  Output:
build/src/volN-bib.tex and build/bibliography.json (assignment, for checks).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare import ROOT, VOLUMES, read_volume_source  # noqa: E402
import links_tex  # noqa: E402


def norm(t):
    t = re.sub(r'\\url\{[^}]*\}', ' ', t)
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    t = t.replace('--', '-')
    t = re.sub(r"``|''|[`'{}\\~]", '', t)
    t = t.lower().replace('&', 'and')
    return ' '.join(re.findall(r'[a-z0-9]+', t))


def entries():
    src = open(os.path.join(ROOT, 'bibliography.tex'), encoding='utf-8').read()
    src = src.split(r'\mysectionnn{Bibliography}', 1)[1]
    out = []
    prev_author = ''
    for block in re.split(r'\n\s*\n', src):
        b = block.strip()
        if not b or b in (r'\bigskip', r'\clearpage'):
            continue
        b = re.sub(r'^\\clearpage\s*|\s*\\bigskip$', '', b).strip()
        if b.startswith('{') and b.endswith('}'):
            b = b[1:-1].strip()
        if not b:
            continue
        ms = [m for m in (
            re.search(r"``(.+?)(?:,|\.)?''", b, re.S),
            re.search(r'\\textit\{((?:[^{}]|\{[^{}]*\})+)\}', b, re.S)) if m]
        m = min(ms, key=lambda m: m.start()) if ms else None
        title = m.group(1) if m else ''
        author = norm(b.split(',')[0].split('.')[0])
        if not author:          # "---. Title": same author as above
            author = prev_author
        prev_author = author
        out.append({'tex': b, 'title': title, 'author': author})
    return out


def keyphrase(title):
    words = norm(title).split()
    # drop subtitle after a colon only if the main title is long enough
    main = norm(re.split(r':', title)[0]).split()
    w = main if len(main) >= 3 else words
    return ' '.join(w[:5])


def near(text, phrase, surname, dist=400):
    for m in re.finditer(r'\b%s\b' % re.escape(phrase), text):
        if surname in text[max(0, m.start() - dist):m.end() + dist]:
            return True
    return False


def load_bibplace():
    p = os.path.join(ROOT, 'links', 'placements.json')
    if not os.path.exists(p):
        return []
    return json.load(open(p, encoding='utf-8')).get('bib', [])


BIBPLACE = load_bibplace()


def main():
    ents = entries()
    texts = {}
    for vol, _, _, files in VOLUMES:
        texts[vol] = norm(read_volume_source(files))
    assign = []
    unassigned = []
    for e in ents:
        k = keyphrase(e['title'])
        surname = e['author'].split()[0] if e['author'] else ''
        if not k:
            # no title: cited by author name only
            vols = [v for v in texts if surname and
                    re.search(r'\b%s\b' % surname, texts[v])]
        elif len(k.split()) >= 3:
            vols = [v for v in texts if k in texts[v]]
        else:
            # short title: author surname must appear close to it
            vols = [v for v in texts if near(texts[v], k, surname)]
        e['vols'] = vols
        if not vols:
            unassigned.append(e)
        assign.append({'title': norm(e['title'])[:80], 'vols': vols})
    regfile = os.path.join(ROOT, 'build', 'links_registry.json')
    registry = json.load(open(regfile, encoding='utf-8'))
    registry['links'] = [l for l in registry['links'] if l['where'] != 'bib']
    for vol, title, _, _ in VOLUMES:
        mine = [e for e in ents if vol in e['vols']]
        # URLs continue the volume's link numbering after the body text
        reg = links_tex.Registry(vol, registry['count'][str(vol)])
        with open(os.path.join(ROOT, 'build', 'src', 'vol%d-bib.tex' % vol),
                  'w', encoding='utf-8') as f:
            f.write('\\RAZbibliography{\n')
            for e in mine:
                tex = e['tex']
                sites = links_tex.url_sites(tex)
                # ebook links of this entry (DOIs, ...): short URL after them
                for p in BIBPLACE:
                    i = tex.find(p['needle'])
                    if i >= 0:
                        pos = i + len(p['needle'])
                        sites.append({'pos': pos, 'end': pos, 'url': p['url'],
                                      'text': p['text'], 'kind': 'ext'})
                sites.sort(key=lambda x: x['pos'])
                if sites:
                    for st in sites:
                        st['code'] = reg.new(st['url'], st['text'], st['kind'], 'bib')
                    for st in reversed(sites):
                        rep = '\\RAZurl{%s}' % st['code']
                        if st['kind'] == 'ext':
                            rep = ', ' + rep
                        tex = tex[:st['pos']] + rep + tex[st['end']:]
                    tex = '\\RAZqrfoot{%s}{%s}' % (
                        ','.join(st['code'] for st in sites), tex)
                f.write('\\RAZbibitem{%s}\n\n' % tex)
            f.write('}\n')
        registry['links'].extend(reg.items)
    json.dump(registry, open(regfile, 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)
    json.dump({'entries': assign,
               'unassigned': [norm(e['tex'])[:120] for e in unassigned]},
              open(os.path.join(ROOT, 'build', 'bibliography.json'), 'w'),
              indent=1)
    print('bibliography: %d entries, %d unassigned; per volume: %s'
          % (len(ents), len(unassigned),
             {v: sum(v in e['vols'] for e in ents) for v in texts}))
    for e in unassigned:
        print('  unassigned:', norm(e['tex'])[:100])


if __name__ == '__main__':
    main()
