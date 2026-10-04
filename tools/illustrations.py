#!/usr/bin/env python3
"""Download the 26 sequence illustrations of lesswrong.com/rationality and
convert them to grayscale JPEGs for the Part divider pages.

The images are NOT part of the repository (their license is not stated on
the site); they are fetched into build/illus at build time.  If the download
fails, the volumes are built without them.
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'illus')
BASE = 'https://res.cloudinary.com/lesswrong-2-0/image/upload/v1/'
MAX_PX = 1400          # ~ 97 mm at 360 dpi


def main():
    os.makedirs(OUT, exist_ok=True)
    seqs = json.load(open(os.path.join(ROOT, 'links', 'lw_posts.json')))['sequences']
    ok = 0
    for i, s in enumerate(seqs, 1):
        raw = os.path.join(OUT, '%02d.png' % i)
        jpg = os.path.join(OUT, 'part%02d.jpg' % i)
        if os.path.exists(jpg):
            ok += 1
            continue
        if not os.path.exists(raw):
            r = subprocess.run(['curl', '-sSf', '-m', '180', '--retry', '3',
                                '-o', raw, BASE + s['banner']])
            if r.returncode:
                print('illustration %d (%s): download failed' % (i, s['title']),
                      file=sys.stderr)
                continue
        im = Image.open(raw).convert('RGBA')
        bg = Image.new('RGBA', im.size, 'white')
        bg.alpha_composite(im)
        g = ImageOps.grayscale(bg)
        g = ImageOps.autocontrast(g, cutoff=0.5)
        g.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
        g.save(jpg, quality=90, dpi=(360, 360))
        ok += 1
    print('illustrations: %d of %d available' % (ok, len(seqs)))


if __name__ == '__main__':
    main()
