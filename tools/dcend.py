#!/usr/bin/env python3
"""Dreamcast ending resources.
END*.CHR = u16 0, u16 cell count, 28 bytes pad, N twiddled 16x16 ARGB1555 cells (art and text).
A composite (OBJDT-like 12-byte entries, part count = y>>10) is drawn in hardware orientation: part at
(x, y & 0x3FF), (s1>>8)+1 columns x (s0>>8)+1 rows, row-major; the displayed picture is that image turned
90 degrees counter-clockwise (vertical monitor).
usage: dcend.py <US|JP> <file.CHR> <composite addr> out.png"""
import os, sys, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from dcchr import untwiddle

ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
_cache = {}


def cells(reg, fn):
    k = (reg, fn)
    if k not in _cache:
        d = open(f'{ROOT}/assets/dc/{reg}/fs/{fn}', 'rb').read()
        n = int.from_bytes(d[2:4], 'little')
        raw = np.frombuffer(d[32:32 + n * 512], '<u2')
        _cache[k] = [untwiddle(raw[i * 256:(i + 1) * 256], 16, 16).astype(int) for i in range(n)]
    return _cache[k]


def parts(img, addr):
    n = max(1, img.w(addr + 2) >> 10)
    out = []
    for i in range(n):
        w = [img.w(addr + 12 * i + 2 * k) for k in range(6)]
        sx = lambda v: (v & 0x3FF) - 0x400 if v & 0x200 else v & 0x3FF
        out.append(dict(x=sx(w[0]), y=sx(w[1]), W=((w[3] >> 8) & 15) + 1, H=((w[2] >> 8) & 15) + 1,
                        attr=w[4], idx=w[5], raw=w))
    return out


def render(reg, fn, addr, img=None, rotate=True):
    img = img or seqdis.Image('dc_' + reg)
    cs = cells(reg, fn)
    ps = parts(img, addr)
    x0 = min(p['x'] for p in ps); y0 = min(p['y'] for p in ps)
    for p in ps: p['x'] -= x0; p['y'] -= y0
    X = max(p['x'] + p['W'] * 16 for p in ps); Y = max(p['y'] + p['H'] * 16 for p in ps)
    cv = np.zeros((Y, X, 3), np.uint8)
    for p in reversed(ps):
        for j in range(p['W'] * p['H']):
            k = p['idx'] + j
            if k >= len(cs): continue
            c = cs[k]; on = (c & 0x8000) != 0
            rgb = np.stack([((c >> 10) & 31) << 3, ((c >> 5) & 31) << 3, (c & 31) << 3], -1).astype(np.uint8)
            x, y = p['x'] + (j % p['W']) * 16, p['y'] + (j // p['W']) * 16
            cv[y:y + 16, x:x + 16][on] = rgb[on]
    im = Image.fromarray(cv)
    return im.rotate(90, expand=True) if rotate else im


if __name__ == '__main__':
    render(sys.argv[1], sys.argv[2], int(sys.argv[3], 16)).save(sys.argv[4])
