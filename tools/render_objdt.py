#!/usr/bin/env python3
"""Render OBJDT frames to PNG for visual checks.
  render_objdt.py dc <objdt addr> <chr file> out.png [nframes]      (DC: ARGB1555 cells)
  render_objdt.py arc <objdt addr> <gfx file> <palette dump|-> out.png [nframes]"""
import sys, struct, numpy as np
from PIL import Image
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from gbres import Space
from dcchr import untwiddle, entry
mode = sys.argv[1]
def s16(v): return v - 0x10000 if v & 0x8000 else v
def frames(sp, addr, n):
    out = []
    for i in range(n):
        e = entry([sp.u16(addr + 12 * i + 2 * k) for k in range(6)])
        if e['w'] > 8 or e['h'] > 8: break
        out.append(e)
    return out
if mode == 'dc':
    sp = Space('dc_US'); addr = int(sys.argv[2], 16); chr_ = np.fromfile(sys.argv[3], dtype='<u2'); outp = sys.argv[4]
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    fr = frames(sp, addr, n)
    imgs = []
    for e in fr:
        im = np.zeros((e['h'] * 16, e['w'] * 16, 4), np.uint8)
        for j in range(e['w'] * e['h']):
            c = untwiddle(chr_[(e['idx'] + j) * 256:(e['idx'] + j + 1) * 256], 16, 16)
            x, y = (j % e['w']) * 16, (j // e['w']) * 16
            r = ((c >> 10) & 31) << 3; g = ((c >> 5) & 31) << 3; b = (c & 31) << 3; a = np.where(c & 0x8000, 255, 0)
            im[y:y + 16, x:x + 16] = np.stack([r, g, b, a], -1)
        imgs.append(Image.fromarray(im, 'RGBA'))
else:
    sp = Space('arcade'); addr = int(sys.argv[2], 16); g = np.fromfile(sys.argv[3], dtype=np.uint8)
    pal = np.fromfile(sys.argv[4], dtype='>u4') if sys.argv[4] != '-' else None
    outp = sys.argv[5]; n = int(sys.argv[6]) if len(sys.argv) > 6 else 8
    fr = frames(sp, addr, n); imgs = []
    for e in fr:
        t = ((e['attr'] & 7) << 16) | e['idx']; colr = e['attr'] >> 8
        im = np.zeros((e['h'] * 16, e['w'] * 16, 4), np.uint8)
        for j in range(e['w'] * e['h']):
            px = g[(t + j) * 256:(t + j + 1) * 256].reshape(16, 16).astype(int)
            x, y = (j % e['w']) * 16, (j // e['w']) * 16
            ent = colr * 16 + px
            col = pal[ent] if pal is not None else (px * 0x01010100)
            im[y:y + 16, x:x + 16] = np.stack([(col >> 24) & 255, (col >> 16) & 255, (col >> 8) & 255,
                                               np.where(px != 0, 255, 0)], -1)
        imgs.append(Image.fromarray(im.astype(np.uint8), 'RGBA'))
W = sum(i.width for i in imgs) + 4 * len(imgs); H = max(i.height for i in imgs)
sheet = Image.new('RGBA', (W, H), (40, 40, 60, 255)); x = 0
for i in imgs: sheet.paste(i, (x, 0), i); x += i.width + 4
sheet = sheet.resize((W * 3, H * 3), Image.NEAREST); sheet.save(outp)
print(len(imgs), 'frames', [(e['w'], e['h'], hex(e['attr']), e['idx']) for e in fr])
