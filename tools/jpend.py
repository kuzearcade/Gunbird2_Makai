#!/usr/bin/env python3
"""Japanese ending texts -> arcade font codes: each JP text composite part is one line of glyph cells (DC JP
END*.CHR); lines ordered by display position (the image is shown rotated 90 degrees CCW), indent -> 0xFFFD."""
import os, sys, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis, dcend, jpfont

def codes(fn, addr, img):
    cs = dcend.cells('JP', fn)
    ps = dcend.parts(img, addr)
    lines = []
    for p in ps:
        # hardware part at (x, y): W columns x H rows, row-major; displayed rotated 90 degrees CCW, so column c is
        # one text line (top = -(x + (c+1)*16)) and rows are its characters (left = y + 16*i)
        for c in range(p['W']):
            top, left = -(p['x'] + (c + 1) * 16), p['y']
            g = []
            for i in range(p['H']):
                k = p['idx'] + i * p['W'] + c
                m = (cs[k] & 0x8000) != 0 if k < len(cs) else np.zeros((16, 16), bool)
                if m.sum() < 3: g.append(None); continue
                (cc, d), = jpfont.match(m, 1)
                g.append((cc, d))
            while g and g[-1] is None: g.pop()
            if g: lines.append((top, left, g))
    lines.sort()
    x0 = min(l[1] for l in lines) if lines else 0
    out, worst = [], 0
    for n, (top, left, g) in enumerate(lines):
        if n: out.append(0xFFFE)
        out += [0xFFFD] * ((left - x0) // 16)
        for x in g:
            out.append(0xFFFD if x is None else x[0]); worst = max(worst, 0 if x is None else x[1])
    return out + [0xFFFF], worst

if __name__ == '__main__':
    ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
    pairs = json.load(open(ROOT + '/re/end_text_pairs.json'))
    owner = json.load(open(ROOT + '/re/end_text_owner.json'))
    img = seqdis.Image('dc_JP')
    res = {}
    for u, j in pairs.items():
        c, w = codes(owner[u], int(j, 16), img)
        res[u] = c
        if w: print(u, 'worst', w)
    json.dump(res, open(ROOT + '/out/stagedemo/end_jp_codes.json', 'w'))
    from jptranscribe import render
    from PIL import Image
    S = ROOT + '/out/tmp/'; os.makedirs(S, exist_ok=True)       # contact sheet of all ending texts (checking)
    ims = [Image.fromarray(render(res[u])) for u in sorted(res)]
    H = sum(i.height + 4 for i in ims); W = max(i.width for i in ims)
    o = Image.new('L', (W, H)); y = 0
    for i in ims: o.paste(i, (0, y)); y += i.height + 4
    o.save(S + 'endjp.png'); print(len(res), o.size)
