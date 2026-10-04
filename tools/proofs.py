#!/usr/bin/env python3
"""Render representative pages of every volume to PNG for inspection:
title page, license page, a plain body page, a page with QR footnotes, the
first Part divider, and the front cover.  Output: build/proofs/volN-*.png and
build/proofs/volN-sheet.png (all side by side).
"""
import csv
import os
import subprocess

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'proofs')
DPI = os.environ.get('DPI', '110')


def texts(pdf):
    t = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True,
                       text=True).stdout
    return t.split('\f')


def render(pdf, page, name):
    base = os.path.join(OUT, name)
    subprocess.run(['pdftoppm', '-r', DPI, '-png', '-singlefile', '-f',
                    str(page), '-l', str(page), pdf, base], check=True)
    return base + '.png'


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'dist', 'links.csv'))))
    for v in range(1, 7):
        pdf = os.path.join(ROOT, 'dist', 'vol%d' % v, 'interior.pdf')
        pages = texts(pdf)
        title = 3       # half title, series page, title page
        lic = next(i for i, p in enumerate(pages) if 'CC BY-NC-SA 3.0' in p) + 1
        part = next(i for i, p in enumerate(pages) if p.strip().startswith('pa r t')
                    or p.strip().lower().startswith('part')) + 1
        # body page: a full text page without footnotes or QR codes
        body = next(i for i, p in enumerate(pages) if i > part + 3 and
                    len(p.splitlines()) > 35 and 'sharov.me' not in p and
                    not any(l.strip()[:3].rstrip('.').isdigit() and len(l) > 40 and
                            l.startswith('   ') for l in p.splitlines()[-3:])) + 1
        qr = next(i for i, p in enumerate(pages) if i > part and
                  'sharov.me/r/%d-' % v in p.replace('\n', '') and
                  'discussion' not in p) + 1
        files = [render(pdf, p, 'vol%d-%s' % (v, n)) for p, n in
                 ((title, 'title'), (lic, 'license'), (part, 'part'),
                  (body, 'body'), (qr, 'qr'))]
        files.append(render(os.path.join(ROOT, 'dist', 'vol%d' % v,
                                         'cover-front.pdf'), 1,
                            'vol%d-cover' % v))
        ims = [Image.open(f) for f in files]
        h = max(i.height for i in ims)
        ims = [i.resize((int(i.width * h / i.height), h)) for i in ims]
        sheet = Image.new('RGB', (sum(i.width for i in ims) + 12 * len(ims), h),
                          (128, 128, 128))
        x = 0
        for i in ims:
            sheet.paste(i, (x, 0))
            x += i.width + 12
        sheet.save(os.path.join(OUT, 'vol%d-sheet.png' % v))
        print('vol%d: title p%d, license p%d, part p%d, body p%d, QR p%d'
              % (v, title, lic, part, body, qr))


if __name__ == '__main__':
    main()
