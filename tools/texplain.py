"""Plain-text projection of LaTeX source with an offset map.

plain_with_map(tex) -> (text, offs) where text[i] came from tex[offs[i]].
Both the projection and ebook text go through norm_chars(), so that quotes,
dashes, ellipses and spacing compare equal.
"""
import re
import unicodedata

SKIP_ARG = {'comment', 'label', 'begin', 'end', 'RAZoldlabel', 'pageref', 'ref', 'url',
            'footback', 'setcounter', 'addtocounter', 'mygraphics',
            'includegraphics', 'myfigure', 'hspace', 'vspace'}
SYMBOLS = {'ldots': '...', 'dots': '...', 'textgreater': '>', 'textless': '<',
           'texttimes': 'x', 'times': 'x', 'textbar': '|', 'degree': 'deg',
           'supercomma': ',', 'newline': ' ', 'par': ' ', 'bigskip': ' ',
           'textlnot': '~', 'lnot': '~', 'pounds': 'L', 'copyright': '(c)',
           'textregistered': '(r)', 'uparrow': '\u2191', 'texttrademark': '(tm)', 'textpm': '+-'}


def norm_chars(s):
    s = unicodedata.normalize('NFKC', s)
    s = s.replace('\u2026', '...')
    s = re.sub(r'\.\s\.\s\.', '...', s)
    s = re.sub(r'[\u2018\u2019\u201a\u201b\u2032`]', "'", s)
    s = re.sub(r'[\u201c\u201d\u201e\u201f\u2033]', '"', s)
    s = re.sub(r'[\u2010-\u2015\u2212]', '-', s)
    s = s.replace('\u00a0', ' ').replace('\u200b', '').replace('\u00ad', '')
    return s


def plain_with_map(tex, skip_notes=False):
    skip = SKIP_ARG | ({'footnote', 'footnotetext'} if skip_notes else set())
    out, offs = [], []
    i, n = 0, len(tex)

    def emit(s, at):
        for ch in s:
            out.append(ch)
            offs.append(at)
    while i < n:
        c = tex[i]
        if c == '%' and (i == 0 or tex[i - 1] != '\\'):
            j = tex.find('\n', i)
            i = n if j < 0 else j + 1
            continue
        if c == '\\':
            m = re.match(r'\\([a-zA-Z]+)\*?', tex[i:])
            if m:
                name = m.group(1)
                j = i + m.end()
                if name in skip:
                    # skip optional [..] and one {...} argument (two for figures)
                    nargs = 3 if name == 'myfigure' else 1
                    while j < n and tex[j] in ' [':
                        if tex[j] == '[':
                            j = tex.find(']', j) + 1
                        else:
                            j += 1
                    for _ in range(nargs):
                        if j < n and tex[j] == '{':
                            depth, j = 1, j + 1
                            while j < n and depth:
                                if tex[j] == '\\':
                                    j += 2
                                    continue
                                depth += {'{': 1, '}': -1}.get(tex[j], 0)
                                j += 1
                    i = j
                    continue
                if name in SYMBOLS:
                    emit(SYMBOLS[name], i)
                elif name in ('footnote', 'footnotetext'):
                    emit(' ', i)
                i = j
                # a control word eats following spaces
                continue
            # control symbol
            if i + 1 < n:
                d = tex[i + 1]
                if d in '%&#_$~{}':
                    emit(d, i + 1)
                elif d in ' \n,;:!' or d == '\\':
                    emit(' ', i)
                elif d == '-':
                    pass                      # discretionary hyphen
                elif d in '\'"`^.=':
                    pass                      # accent: base letter follows
                elif d == '/':
                    pass
            i += 2
            continue
        if c in '{}$':
            i += 1
            continue
        if tex.startswith('---', i):
            emit('\u2014', i); i += 3; continue
        if tex.startswith('--', i):
            emit('\u2013', i); i += 2; continue
        if tex.startswith('``', i):
            emit('\u201c', i); i += 2; continue
        if tex.startswith("''", i):
            emit('\u201d', i); i += 2; continue
        if c == '~':
            emit(' ', i); i += 1; continue
        emit(c, i)
        i += 1
    # normalise characters and collapse whitespace, keeping the map
    text, omap = [], []
    prev_space = True
    for ch, o in zip(out, offs):
        ch = norm_chars(ch)
        for k in ch:
            if k.isspace():
                if prev_space:
                    continue
                k = ' '
                prev_space = True
            else:
                prev_space = False
            text.append(k)
            omap.append(o)
    return ''.join(text), omap


def norm_text(s):
    return ' '.join(norm_chars(s).split())
