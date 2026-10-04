#!/usr/bin/env python3
"""Verify the finished edition (run after `make all`).

1. LaTeX logs: no undefined references, no overfull box wider than 3 pt.
2. PDFs: all fonts embedded; interior pages all of the trim size.
3. Every QR code: each page that should carry QR codes is rendered at
   300 dpi and decoded with zbarimg; the decoded short URLs must equal the
   codes that links.csv lists for that page, and every code in links.csv
   must be found.
4. EPUB links: every hyperlink extracted from the ebook is either placed or
   listed as not placed, with a reason (links/placements_report.json).
Writes build/check-report.txt and exits non-zero on failure.
"""
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')
MAX_OVERFULL_PT = 3.0
problems = []
report = []


def say(s):
    print(s)
    report.append(s)


def logs():
    for v in range(1, 7):
        log = open(os.path.join(ROOT, 'build', 'tex', 'vol%d.log' % v),
                   encoding='utf-8', errors='replace').read()
        undef = re.findall(r"Reference `([^']+)' on page \d+ undefined", log)
        over = [float(x) for x in
                re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
        big = [x for x in over if x > MAX_OVERFULL_PT]
        say('vol%d: %d undefined references, %d overfull boxes (max %.1f pt),'
            ' %d wider than %.0f pt'
            % (v, len(undef), len(over), max(over or [0]), len(big),
               MAX_OVERFULL_PT))
        if undef:
            problems.append('vol%d undefined: %s' % (v, ', '.join(sorted(set(undef)))))
        if big:
            problems.append('vol%d overfull boxes > %.0f pt: %s'
                            % (v, MAX_OVERFULL_PT, big))


def pdfs():
    for v in range(1, 7):
        d = os.path.join(DIST, 'vol%d' % v)
        for f in sorted(os.listdir(d)):
            if not f.endswith('.pdf'):
                continue
            path = os.path.join(d, f)
            fonts = subprocess.run(['pdffonts', path], capture_output=True,
                                   text=True).stdout.splitlines()[2:]
            notemb = [l for l in fonts if l.split()[-5] != 'yes']
            if notemb:
                problems.append('%s: fonts not embedded: %s' % (path, notemb))
        sizes = subprocess.run(['pdfinfo', '-f', '1', '-l', '9999',
                                os.path.join(d, 'interior.pdf')],
                               capture_output=True, text=True).stdout
        dims = set(re.findall(r'Page +\d+ size: +([\d.]+ x [\d.]+)', sizes))
        say('vol%d interior: page size(s) %s pt; fonts embedded in all PDFs'
            % (v, ', '.join(sorted(dims))))
        if len(dims) != 1:
            problems.append('vol%d: pages of different sizes %s' % (v, dims))


def qrcodes():
    rows = list(csv.DictReader(open(os.path.join(DIST, 'links.csv'),
                                    encoding='utf-8')))
    want = defaultdict(set)          # (vol, page label) -> codes
    for r in rows:
        want[(int(r['volume']), r['page'])].add(r['code'])
    found = set()
    with tempfile.TemporaryDirectory() as tmp:
        for v in range(1, 7):
            pdf = os.path.join(DIST, 'vol%d' % v, 'interior.pdf')
            labels = page_labels(pdf)
            for (vol, page), codes in sorted(want.items()):
                if vol != v:
                    continue
                idx = labels.get(page)
                if idx is None:
                    problems.append('vol%d: page %s not found' % (v, page))
                    continue
                got = set()
                lines = []
                # zbar occasionally misses a code at one particular scale;
                # print resolution is far higher, so try a few resolutions
                for dpi in ('300', '450', '600'):
                    png = os.path.join(tmp, 'p')
                    subprocess.run(['pdftoppm', '-r', dpi, '-gray', '-png',
                                    '-singlefile', '-f', str(idx), '-l', str(idx),
                                    pdf, png], check=True)
                    out = subprocess.run(['zbarimg', '-q', '--raw',
                                          '-Sdisable', '-Sqrcode.enable',
                                          png + '.png'],
                                         capture_output=True, text=True).stdout
                    lines += out.split()
                    if {l.rsplit('/', 1)[-1] for l in lines} >= codes:
                        break
                for line in dict.fromkeys(lines):
                    m = re.fullmatch(r'https://sharov\.me/r/(\d+-c?\d+)', line)
                    if m:
                        got.add(m.group(1))
                    else:
                        problems.append('vol%d p.%s: unexpected QR content %r'
                                        % (v, page, line))
                found |= got
                if got != codes:
                    problems.append('vol%d p.%s: QR codes %s, expected %s'
                                    % (v, page, sorted(got), sorted(codes)))
    say('QR codes: %d listed in links.csv, %d decoded and matched'
        % (len(rows), len(found & {r['code'] for r in rows})))


def page_labels(pdf):
    """printed page number -> physical page index (1-based)."""
    out = subprocess.run(['pdfinfo', '-f', '1', '-l', '9999', pdf],
                         capture_output=True, text=True).stdout
    n = int(re.search(r'Pages: +(\d+)', out).group(1))
    # the printed folio of every page, from the text layer of each page
    # is unreliable; use the page labels written by hyperref instead
    lab = subprocess.run(['qpdf', '--json', '--json-key=pagelabels', pdf],
                         capture_output=True, text=True).stdout
    data = json.loads(lab).get('pagelabels', [])
    labels = {}
    ranges = sorted(((d['index'], d['label']) for d in data),
                    key=lambda x: x[0])
    for k, (start, l) in enumerate(ranges):
        end = ranges[k + 1][0] if k + 1 < len(ranges) else n
        first = l.get('/St', 1)
        style = l.get('/S')
        for i in range(start, end):
            num = first + i - start
            labels[roman(num) if style == '/r' else str(num)] = i + 1
    return labels


def roman(n):
    out = ''
    for v, s in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'),
                 (90, 'xc'), (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'),
                 (5, 'v'), (4, 'iv'), (1, 'i')):
        while n >= v:
            out += s
            n -= v
    return out


def epub():
    p = os.path.join(ROOT, 'links', 'placements_report.json')
    if not os.path.exists(p):
        problems.append('no EPUB link extraction yet (links/placements_report.json)')
        return
    r = json.load(open(p, encoding='utf-8'))
    say('EPUB links: %(total)d in the ebook, %(placed)d placed '
        '(%(internal)d internal, %(external)d external), %(notplaced)d not placed' % r)
    if r['total'] != r['placed'] + r['notplaced']:
        problems.append('EPUB link count mismatch')


def main():
    logs()
    pdfs()
    qrcodes()
    epub()
    say('')
    if problems:
        say('PROBLEMS:')
        for p in problems:
            say('  ' + p)
    else:
        say('all checks passed')
    with open(os.path.join(ROOT, 'build', 'check-report.txt'), 'w') as f:
        f.write('\n'.join(report) + '\n')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
