#!/usr/bin/env python3
"""Render a composite OBJDT list (all entries drawn at their x/y) for visual comparison.
 dc  <addr> <CHR> out.png [n]            arc <addr> <palette dump> out.png [n]
x = entry x (sign-extended 10 bits), y = entry y & 0x3FF (sign-extended)"""
import os, sys, numpy as np
from PIL import Image
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from gbres import Space
from dcchr import untwiddle, entry
def sx(v, bits=10):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v & (1 << (bits - 1)) else v
mode = sys.argv[1]; addr = int(sys.argv[2], 16)
sp = Space('dc_US' if mode == 'dc' else 'arcade')
if mode == 'dc': chr_ = np.fromfile(sys.argv[3], dtype='<u2')
else:
    g = np.fromfile(os.path.dirname(os.path.abspath(__file__)) + '/../assets/arcade/gfx.bin', dtype=np.uint8)
    pal = np.fromfile(sys.argv[3], dtype='>u4')
outp = sys.argv[4]; n = int(sys.argv[5]) if len(sys.argv) > 5 else 16
MORTON = len(sys.argv) > 6 and sys.argv[6] == 'morton'
def cellpos(j, w, h):
    if not MORTON or w != h or w & (w - 1): return j % w, j // w
    x = y = 0
    for b in range(4):
        y |= ((j >> (2 * b)) & 1) << b; x |= ((j >> (2 * b + 1)) & 1) << b
    return x, y
canvas = np.zeros((512, 512, 4), np.uint8)
ents = []
for i in range(n):
    e = entry([sp.u16(addr + 12 * i + 2 * k) for k in range(6)])
    if e['w'] > 16 or e['h'] > 16 or (e['size'] & 0x00FF00FF): break
    ents.append(e)
for e in reversed(ents):
    if len(sys.argv) > 7 and sys.argv[7] == 'swap': e['w'], e['h'] = e['h'], e['w']
    x0, y0 = sx(e['x']) + 128, sx(e['y']) + 128
    for j in range(e['w'] * e['h']):
        cx, cy = cellpos(j, e['w'], e['h'])
        x, y = x0 + cx * 16, y0 + cy * 16
        if not (0 <= x < 496 and 0 <= y < 496): continue
        if mode == 'dc':
            c = untwiddle(chr_[(e['idx'] + j) * 256:(e['idx'] + j + 1) * 256], 16, 16).astype(int)
            rgba = np.stack([((c >> 10) & 31) << 3, ((c >> 5) & 31) << 3, (c & 31) << 3, np.where(c & 0x8000, 255, 0)], -1)
        else:
            t = ((e['attr'] & 7) << 16) | e['idx']; colr = e['attr'] >> 8
            if e['attr'] & 0x80: px = g[(t + j) * 256:(t + j + 1) * 256].reshape(16, 16).astype(int)
            else:
                b = g[(t + j) * 128:(t + j + 1) * 128]; px = np.stack([b >> 4, b & 15], -1).reshape(16, 16).astype(int)
            col = pal[(colr * 16 + px) % len(pal)]
            rgba = np.stack([(col >> 24) & 255, (col >> 16) & 255, (col >> 8) & 255, np.where(px != 0, 255, 0)], -1)
        m = rgba[..., 3] > 0
        canvas[y:y + 16, x:x + 16][m] = rgba[m]
Image.fromarray(canvas, 'RGBA').save(outp)
print('ok')
