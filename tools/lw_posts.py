#!/usr/bin/env python3
"""Map every essay to its LessWrong post (for the "discussion" QR codes)
and record the sequence illustrations of the Rationality: A-Z collection.

Needs network.  Output: links/lw_posts.json (committed, so that the build
itself works offline).  Run tools/prepare.py first (it writes
build/essays.json).
"""
import json
import os
import re
import subprocess
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = 'https://www.lesswrong.com/graphql'
COLLECTION = 'oneQyj4pw77ynzwAF'      # lesswrong.com/rationality
POST_FIELDS = '_id slug title pageUrl commentCount postedAt user { displayName }'
# Essays whose LessWrong title differs from the 2015 book title
ALIASES = {
    'e1': 'what-do-we-mean-by-rationality-1',
    'e3': 'why-truth',
    'e4': 'what-s-a-bias',
    'e10': 'the-lens-that-sees-its-flaws',
    'e140': 'an-especially-elegant-evpsych-experiment',
    'e201': 'savanna-poets',
    'interlude-the-twelve-virtues-of-rationality':
        'twelve-virtues-of-rationality',
    'e316': '3-levels-of-rationality-verification',
}


def gql(query):
    body = json.dumps({'query': query})
    for attempt in range(5):
        r = subprocess.run(['curl', '-sS', '-m', '60',
                            '-H', 'content-type: application/json',
                            '--data', body, API],
                           capture_output=True, text=True)
        if r.returncode == 0:
            break
        time.sleep(2 ** attempt)
    else:
        raise RuntimeError('LessWrong API unreachable: ' + r.stderr)
    out = r.stdout
    d = json.loads(out)
    if 'errors' in d:
        raise RuntimeError(d['errors'][0]['message'])
    return d['data']


def norm(t):
    t = re.sub(r'\\-', '', t)
    t = re.sub(r'\\ldots', '...', t)
    t = re.sub(r'\\[a-zA-Z]+', '', t)
    t = unicodedata.normalize('NFKD', t)
    t = re.sub(r"``|''|[`'’“”{}]", '', t)
    t = re.sub(r'^interlude:\s*', '', t.lower())
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def lw_slug(t):
    return norm(t).replace(' ', '-')


def main():
    ess = json.load(open(os.path.join(ROOT, 'build', 'essays.json')))
    col = gql('{ collection(input:{selector:{documentId:"%s"}}){ result {'
              ' books { number title sequences { _id title gridImageId'
              ' bannerImageId chapters { posts { %s } } } } } } }'
              % (COLLECTION, POST_FIELDS))['collection']['result']
    by_title = {}
    sequences = []
    for b in col['books']:
        for s in b['sequences']:
            sequences.append({'book': b['number'], 'title': s['title'],
                              'id': s['_id'],
                              'grid': s['gridImageId'],
                              'banner': s['bannerImageId']})
            for c in s['chapters']:
                for p in c['posts']:
                    by_title.setdefault(norm(p['title']), p)
    posts = {}
    unresolved = []
    for eid, e in ess.items():
        p = None if eid in ALIASES else by_title.get(norm(e['title']))
        if p is None:
            slug = ALIASES.get(eid) or lw_slug(e['title'])
            res = gql('{ posts(input:{terms:{view:"slugPost", slug:"%s"}})'
                      '{ results { %s } } }'
                      % (slug, POST_FIELDS))['posts']['results']
            p = res[0] if res else None
        if p is None:
            unresolved.append(eid)
            continue
        posts[eid] = {'title': p['title'], 'url': p['pageUrl'],
                      'comments': p['commentCount'],
                      'author': (p.get('user') or {}).get('displayName')}
    out = {'posts': posts, 'unresolved': unresolved, 'sequences': sequences}
    with open(os.path.join(ROOT, 'links', 'lw_posts.json'), 'w') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print('essays %d, resolved %d, unresolved %s'
          % (len(ess), len(posts), unresolved))


if __name__ == '__main__':
    main()
