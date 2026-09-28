#!/usr/bin/env python3
"""Arcade Japanese font: glyph code c = 4bpp 16x16 tile 0x150 + c in the gfx ROM (SEQ hdr+0x38 OBJDT entry).
match(cell) finds the arcade code whose glyph best matches a DC 16x16 glyph cell (binary Hamming distance)."""
import os, numpy as np
ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
BASE, N = 0x150, 0x1000
_g = np.memmap(ROOT + '/assets/arcade/gfx.bin', dtype=np.uint8, mode='r')

def glyph(c):
    b = np.asarray(_g[(BASE + c) * 128:(BASE + c + 1) * 128])
    return np.stack([b >> 4, b & 15], -1).reshape(16, 16)

_BIN = None
def bins():
    global _BIN
    if _BIN is None: _BIN = np.stack([glyph(c) != 0 for c in range(N)])
    return _BIN

def match(mask, top=3):
    """mask: 16x16 bool (glyph pixels).  returns [(code, distance)] best first; tries +-1 px shifts"""
    B = bins(); best = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            m = np.roll(np.roll(mask, dy, 0), dx, 1)
            d = (B != m).reshape(N, -1).sum(1)
            best += list(zip(range(N), d.tolist()))
    r = {}
    for c, d in best: r[c] = min(d, r.get(c, 999))
    return sorted(r.items(), key=lambda x: x[1])[:top]
