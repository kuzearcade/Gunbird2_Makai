#!/usr/bin/env python3
"""Render Dreamcast stage-demo messages to PNG.

The DC draws a stage-demo message as a PutObj composite (OBJDT) chosen by the script subroutine 0x8C3FFE60 from
work vars w15 (stage), w12 (pair index, 0..26) and w13 (message number); the OBJDT's cells come from the scene's
text texture STG<stage>DEMOMSG.<pair+1:03> (u16 flags, u16 cell count, 28 bytes pad, N twiddled 16x16 ARGB1555
cells).  usage: dcmsg.py <US|JP> <stage 1-6> <pair 0-26> [out_dir]   -> msg_<reg>_s<stage>_p<pair>_m<n>.png"""
import os, sys, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from dcchr import untwiddle

ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
SUB = {'US': 0x8C3FFE60, 'JP': 0x8C3FF530}    # message subroutine (script) per disc


def sx(v, bits=10):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def find_objdt(img, work, sub):
    """walk the dispatch tree (CalcWork/JumpCompare(==)/Jump/PutObj) and return the PutObj data address"""
    a = sub
    for _ in range(400):
        ln, txt, tg, term, op = seqdis.decode(img, a)
        if op == 0x0A:                                  # JumpCompare desc, work, imm32, target
            idx = img.w(a + 4); val = img.l(a + 6)
            if work.get(idx, 0) == val: a = tg[0]; continue
        elif op == 0x08:
            a = tg[0]; continue
        elif txt.startswith('PutObj'):
            return img.l(a + 2)
        elif term:
            return None
        a += ln
    return None


def render(reg, rec, cells, img):
    """rec = 6-word record {x, y, s0, s1, attr, idx}: one message = (s1>>8)+1 columns x (s0>>8)+1 rows of cells,
    row-major from idx-0x1000, stored rotated: the displayed text is the image turned 90 degrees counter-clockwise"""
    s0, s1, idx = img.w(rec + 4), img.w(rec + 6), img.w(rec + 10) - 0x1000
    W, H = ((s1 >> 8) & 15) + 1, ((s0 >> 8) & 15) + 1
    im = np.zeros((H * 16, W * 16, 3), np.uint8)
    for j in range(W * H):
        if idx + j >= len(cells): break
        c = cells[idx + j]; cx, cy = j % W, j // W
        on = (c & 0x8000) != 0
        rgb = np.stack([((c >> 10) & 31) << 3, ((c >> 5) & 31) << 3, (c & 31) << 3], -1).astype(np.uint8)
        im[cy * 16:cy * 16 + 16, cx * 16:cx * 16 + 16][on] = rgb[on]
    return Image.fromarray(im).rotate(90, expand=True)


def load_cells(reg, stage, pair):
    d = open(f'{ROOT}/assets/dc/{reg}/fs/STG{stage}DEMOMSG.{pair + 1:03d}', 'rb').read()
    n = int.from_bytes(d[2:4], 'little')
    raw = np.frombuffer(d[32:32 + n * 512], '<u2')
    return [untwiddle(raw[k * 256:(k + 1) * 256], 16, 16).astype(int) for k in range(n)]


def messages(reg, stage, pair, maxmsg=4, file_no=None):
    img = seqdis.Image('dc_' + reg)
    cells = load_cells(reg, stage, pair if file_no is None else file_no - 1)
    out = []
    for m in range(maxmsg):
        o = find_objdt(img, {0x15: stage, 0x12: pair, 0x13: m}, SUB[reg])
        if o is None: break
        if any(o == x[0] for x in out): break
        out.append((o, render(reg, o, cells, img)))
    return out


if __name__ == '__main__':
    reg, stage, pair = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    od = sys.argv[4] if len(sys.argv) > 4 else '.'
    for m, (o, im) in enumerate(messages(reg, stage, pair)):
        p = f'{od}/msg_{reg}_s{stage}_p{pair}_m{m}.png'
        if im: im.save(p)
        print(p, hex(o))
