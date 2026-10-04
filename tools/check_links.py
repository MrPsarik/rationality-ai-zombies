#!/usr/bin/env python3
"""Check every external URL of the edition and record its status.

For each original URL:
  ok          reachable (HTTP 2xx) at the same address
  redirected  reachable after redirects; the final address is used
  archived    dead (error, 4xx/5xx, soft 404, or redirected to a site's home
              page); the Wayback Machine snapshot closest to 2015 is used
  unchecked   could not be checked and no snapshot was found; the original
              address is kept

Plain http:// cannot go through this environment's proxy, so http URLs are
checked over https:// first (and over http:// where that is possible).
Results are cached in links/url_status.json (committed); `--refresh` checks
everything again, otherwise only new URLs are checked.

Input: build/links_registry.json and build/discussions.json (run
tools/prepare.py and tools/bibliography.py first).
"""
import concurrent.futures as cf
import datetime
import html
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(ROOT, 'links', 'url_status.json')
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
      ' Chrome/124.0 Safari/537.36')
WAYBACK_API = 'https://archive.org/wayback/available'
TIMEOUT = 40


def https_variant(url):
    p = urlsplit(url)
    if p.scheme == 'http':
        return urlunsplit(('https',) + tuple(p)[1:])
    return url


def norm(url):
    p = urlsplit(url)
    host = p.netloc.lower()
    host = host[4:] if host.startswith('www.') else host
    return host + p.path.rstrip('/') + ('?' + p.query if p.query else '')


def title_of(text):
    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.S | re.I)
    if not m:
        return ''
    t = html.unescape(' '.join(m.group(1).split()))
    t = re.sub(r'\s+[-|—–]\s+(LessWrong|Less Wrong).*$', '', t)
    return t[:120]


SOFT404 = re.compile(r'page not found|404 not found|not found \||'
                     r'page (does not|doesn.t) exist|no longer available|'
                     r'domain (is )?for sale|this domain', re.I)


def fetch(url):
    s = requests.Session()
    s.headers['User-Agent'] = UA
    r = s.get(url, timeout=TIMEOUT, allow_redirects=True)
    return r


def is_home(url):
    return urlsplit(url).path in ('', '/') and not urlsplit(url).query


STOP = {'www', 'html', 'htm', 'php', 'index', 'archives', 'archive', 'files',
        'blog', 'pdf', 'articles', 'article', 'papers', 'wiki', 'posts'}


def tokens(path):
    return {t for t in re.findall(r'[a-z0-9]+', path.lower())
            if len(t) >= 3 and t not in STOP and not t.isdigit()}


def unrelated(orig, final):
    """A redirect to a shallow page that shares nothing with the original
    path (e.g. an old blog post now redirected to a department page)."""
    po, pf = urlsplit(orig).path, urlsplit(final).path
    to, tf = tokens(po), tokens(pf)
    if not to:
        return False
    shared = any(a in b or b in a for a in to for b in tf)
    depth = len([x for x in pf.split('/') if x])
    return not shared and depth <= 2


def candidates(url):
    """Addresses to try, best first."""
    c = []
    p = urlsplit(url)
    # old LessWrong comment anchors (#3tm) are path components today
    if 'lesswrong.com' in p.netloc and p.path.startswith('/lw/') and p.fragment:
        c.append(https_variant(urlunsplit(p._replace(
            path=p.path.rstrip('/') + '/' + p.fragment, fragment=''))))
    # "%5C_" (an escaped backslash before "_") is an artefact of the 2015 text
    if '%5C' in url:
        c.append(https_variant(url.replace('%5C', '')))
    c += [https_variant(url), url]
    return list(dict.fromkeys(c))


BLOCKED = (401, 403, 429)       # bot protection: says nothing about the page


WAYBACK_LOCK = __import__('threading').Lock()


def wayback(url):
    with WAYBACK_LOCK:          # the API rate-limits; one request at a time
        time.sleep(1.5)
        return _wayback(url)


def _wayback(url):
    for attempt in range(6):
        try:
            r = requests.get(WAYBACK_API, params={'url': url,
                                                  'timestamp': '20150301'},
                             timeout=TIMEOUT)
            if r.status_code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            snap = r.json().get('archived_snapshots', {}).get('closest')
            if snap and snap.get('available') and \
                    str(snap.get('status', '200')).startswith(('2', '3')):
                return snap['url'].replace('http://', 'https://', 1), \
                    snap['timestamp']
            return None, None
        except (requests.RequestException, ValueError):
            time.sleep(3 * (attempt + 1))
    return None, None


def check_special(url):
    """Sites that block bots but can be verified another way."""
    p = urlsplit(url)
    host = p.netloc.lower()
    if host in ('doi.org', 'dx.doi.org'):
        # a registered DOI answers with a redirect to the publisher
        doi = p.path.lstrip('/')
        canon = 'https://doi.org/' + doi
        try:
            r = requests.get(canon, allow_redirects=False, timeout=TIMEOUT,
                             headers={'User-Agent': UA})
        except requests.RequestException:
            return None
        if r.status_code in (301, 302, 303, 307, 308):
            return {'status': 'ok' if canon == url else 'redirected',
                    'final': canon, 'http': r.status_code, 'title': '',
                    'note': 'DOI resolves to ' + r.headers.get('location', '')[:120]}
        if r.status_code == 404:
            return None
    if host.endswith('youtube.com') and 'watch' in p.path:
        try:
            r = requests.get('https://www.youtube.com/oembed',
                             params={'url': url, 'format': 'json'},
                             timeout=TIMEOUT, headers={'User-Agent': UA})
        except requests.RequestException:
            return None
        if r.status_code == 200:
            final = https_variant(url).replace('://youtube.com', '://www.youtube.com')
            return {'status': 'ok' if final == url else 'redirected',
                    'final': final, 'http': 200,
                    'title': r.json().get('title', '')[:120],
                    'note': 'verified via YouTube oEmbed'}
        if r.status_code in (400, 404):
            return {'dead': True}
    return None


def check(url):
    res = {'url': url, 'checked': datetime.date.today().isoformat()}
    if 'web.archive.org/web/' in url:
        res.update(status='archived', final=url.replace('http://', 'https://', 1),
                   note='already an archive link in the 2015 text')
        return res
    special = check_special(url)
    if special and special.get('dead'):
        res.update(note='video no longer available', dead=True)
        return archive(res)
    if special:
        res.update(special)
        return res
    tried = []
    dead = False
    for cand in candidates(url):
        r = None
        for attempt in range(3):
            try:
                r = fetch(cand)
                break
            except requests.RequestException as e:
                err = type(e).__name__
                time.sleep(2 * (attempt + 1))
        if r is None:
            tried.append('%s: %s' % (cand, err))
            continue
        res['http'] = r.status_code
        if r.status_code in BLOCKED:
            tried.append('%s: HTTP %s (bot protection)' % (cand, r.status_code))
            continue
        frag = urlsplit(url).fragment
        final = r.url
        if frag and '#' not in final and frag not in final:
            final += '#' + frag
        text = r.text[:200000] if 'html' in r.headers.get('content-type', '') else ''
        res['title'] = title_of(text)
        bad = r.status_code >= 400
        if not bad and is_home(r.url) and not is_home(url):
            bad, res['note'] = True, 'redirected to the home page'
        if not bad and unrelated(url, r.url):
            bad, res['note'] = True, 'redirected to an unrelated page: ' + r.url
        if not bad and SOFT404.search(res['title'] or ''):
            bad, res['note'] = True, 'soft 404: ' + res['title']
        if not bad:
            res['final'] = final
            res['status'] = 'ok' if norm(final) == norm(url) else 'redirected'
            if cand not in (https_variant(url), url):
                res['note'] = 'checked as ' + cand
            return res
        tried.append('%s: HTTP %s' % (cand, r.status_code))
        dead = True
        break
    if not res.get('note'):
        res['note'] = '; '.join(tried)
    if not dead:
        # unreachable from here (bot protection, TLS, proxy): keep it
        res.update(status='unchecked', final=url, title='')
        return res
    res['dead'] = True
    return archive(res)


def archive(res):
    """Dead link: use the Wayback snapshot closest to 2015."""
    snap, ts = wayback(res['url'])
    if snap:
        res.update(status='archived', final=snap, snapshot=ts, title='')
    else:
        res.update(status='unchecked', final=res['url'],
                   note=res.get('note', '') + '; dead, no snapshot found yet')
    return res


def main():
    refresh = '--refresh' in sys.argv
    status = {}
    if os.path.exists(STATUS_FILE) and not refresh:
        status = json.load(open(STATUS_FILE, encoding='utf-8'))
    reg = json.load(open(os.path.join(ROOT, 'build', 'links_registry.json')))
    disc = json.load(open(os.path.join(ROOT, 'build', 'discussions.json')))
    urls = [l['url'] for l in reg['links']] + [d['url'] for d in disc.values()]
    recheck = '--recheck' in sys.argv
    todo = [u for u in dict.fromkeys(urls) if u not in status
            or status[u].get('status') == 'unchecked'
            or (recheck and status[u].get('status') != 'ok')]
    # dead links still waiting for a snapshot: only ask the Wayback Machine
    for u in [u for u in todo if status.get(u, {}).get('dead')]:
        todo.remove(u)
        r = status[u]
        r['note'] = r.get('note', '').replace('; dead, no snapshot found yet', '')
        status[u] = archive(r)
        print('  wayback %s: %s' % (u, status[u]['status']))
    print('%d URLs, %d to check' % (len(set(urls)), len(todo)))
    with cf.ThreadPoolExecutor(6) as ex:
        for i, res in enumerate(ex.map(check, todo), 1):
            status[res['url']] = res
            if i % 25 == 0:
                print('  %d/%d' % (i, len(todo)))
                json.dump(status, open(STATUS_FILE, 'w', encoding='utf-8'),
                          indent=1, ensure_ascii=False, sort_keys=True)
    json.dump(status, open(STATUS_FILE, 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False, sort_keys=True)
    from collections import Counter
    print(Counter(status[u]['status'] for u in set(urls)))


if __name__ == '__main__':
    main()
