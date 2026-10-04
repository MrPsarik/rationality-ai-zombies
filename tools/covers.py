#!/usr/bin/env python3
"""Build the covers of all volumes from the finished interiors.

spine width = number of sheets x paper thickness
            = ceil(pages / 2) x SHEET_MM   (default 0.1 mm, 80 g/m2)

Writes dist/volN/cover.pdf (back + spine + front), cover-front.pdf and
cover-back.pdf, all with 3 mm bleed, and dist/volumes.csv with the page
counts and spine widths.
"""
import csv
import math
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.environ.get('PAPER', 'royal')
SHEET_MM = float(os.environ.get('SHEET_MM', '0.1'))
OUT = os.path.join(ROOT, 'build', 'cover')


def pages(pdf):
    info = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True,
                          check=True).stdout
    return int(next(l.split()[1] for l in info.splitlines()
                    if l.startswith('Pages:')))


def main():
    os.makedirs(OUT, exist_ok=True)
    env = dict(os.environ, TEXINPUTS='.:print//:')
    rows = []
    for v in range(1, 7):
        interior = os.path.join(ROOT, 'dist', 'vol%d' % v, 'interior.pdf')
        n = pages(interior)
        sheets = math.ceil(n / 2)
        spine = round(sheets * SHEET_MM, 2)
        rows.append({'volume': v, 'pages': n, 'sheets': sheets,
                     'sheet_mm': SHEET_MM, 'spine_mm': spine,
                     'paper': PAPER})
        for part, name in (('spread', 'cover'), ('front', 'cover-front'),
                           ('back', 'cover-back')):
            job = 'cover%d-%s' % (v, part)
            tex = ('\\def\\PaperName{%s}\\def\\VolNum{%d}\\def\\SpineW{%.2fmm}'
                   '\\def\\CoverPart{%s}\\input{print/cover.tex}'
                   % (PAPER, v, spine, part))
            r = subprocess.run(['lualatex', '-interaction=nonstopmode',
                                '-halt-on-error', '-output-directory=' + OUT,
                                '-jobname=' + job, tex],
                               cwd=ROOT, env=env, capture_output=True, text=True)
            if r.returncode:
                sys.exit('cover %s failed:\n%s' % (job, r.stdout[-2000:]))
            shutil.copy(os.path.join(OUT, job + '.pdf'),
                        os.path.join(ROOT, 'dist', 'vol%d' % v, name + '.pdf'))
        print('vol%d: %d pages, %d sheets, spine %.2f mm' % (v, n, sheets, spine))
    with open(os.path.join(ROOT, 'dist', 'volumes.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == '__main__':
    main()
