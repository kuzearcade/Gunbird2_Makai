#!/usr/bin/env python3
"""Dreamcast .CHR sprite texture decoding (ARGB1555, PVR twiddled) + OBJDT entry helpers."""
import numpy as np, functools

@functools.lru_cache(None)
def twiddle_map(n):
    """index i (twiddled) -> (y, x) for an n x n square, PVR order (x from odd bits)"""
    bits = n.bit_length() - 1
    ys = np.zeros(n * n, np.int32); xs = np.zeros(n * n, np.int32)
    for i in range(n * n):
        x = y = 0
        for b in range(bits):
            y |= ((i >> (2 * b)) & 1) << b
            x |= ((i >> (2 * b + 1)) & 1) << b
        ys[i], xs[i] = y, x
    return ys, xs

def untwiddle(v, w, h):
    """PVR twiddled w x h (powers of two; rectangular = square blocks of min(w,h) along the long axis)"""
    s = min(w, h); out = np.zeros((h, w), v.dtype); ys, xs = twiddle_map(s)
    nb = (w * h) // (s * s)
    for b in range(nb):
        blk = v[b * s * s:(b + 1) * s * s]
        by, bx = (b * s, 0) if h > w else (0, b * s)
        out[by + ys, bx + xs] = blk
    return out

def pow2(x):
    p = 1
    while p < x: p <<= 1
    return p

def texdims(wt, ht):
    """texture size in pixels for a sprite of wt x ht 16px tiles"""
    return pow2(wt * 16), pow2(ht * 16)

def entry(words):
    """decode 6-word OBJDT entry -> dict"""
    x, y, s0, s1, at, ix = words
    size = (s0 << 16) | s1
    return dict(x=x, y=y, h=((size >> 24) & 0xF) + 1, w=((size >> 8) & 0xF) + 1, flipy=size >> 31,
                flipx=(size >> 15) & 1, attr=at, idx=ix, size=size)
