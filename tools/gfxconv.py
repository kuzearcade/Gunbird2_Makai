#!/usr/bin/env python3
"""Convert Dreamcast 16-bit (ARGB1555, PVR-twiddled 16x16 cells) sprite sheets into arcade 8bpp tiles + palette.

A "sheet" is one DC .CHR file whose cells are referenced by OBJDT entries (cell index = entry idx).
Each DC cell becomes one arcade 8bpp 16x16 tile (256 bytes, tile number in 256-byte units), in the same
order, so an OBJDT entry's tile number is simply base + DC cell index.

Palette: all opaque colours of the sheet(s) sharing one palette group are collected; index 0 = transparent.
DC colours are the arcade RGB888 palette truncated to 5 bits per channel, so they expand back with
(v << 3) | (v >> 2) (exact to within the lost low bits).
"""
import numpy as np, struct, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dcchr import untwiddle

def load_cells(path):
    raw = np.fromfile(path, dtype='<u2')
    n = len(raw) // 256
    return [untwiddle(raw[k * 256:(k + 1) * 256], 16, 16) for k in range(n)]

def expand5(v):
    return (v << 3) | (v >> 2)

def rgb888(c555):
    r, g, b = (c555 >> 10) & 31, (c555 >> 5) & 31, c555 & 31
    return (expand5(r) << 24) | (expand5(g) << 16) | (expand5(b) << 8)

def build_palette(cells_list, reserve=None, max_colours=255, start=1):
    """cells_list: list of lists of 16x16 uint16 cells. reserve: dict c555->index to keep."""
    counts = {}
    for cells in cells_list:
        for c in cells:
            v = c[(c & 0x8000) != 0] & 0x7FFF
            for x in np.unique(v).tolist(): counts[x] = counts.get(x, 0) + 1
    pal = dict(reserve or {})
    nxt = max(max(pal.values(), default=0) + 1, start)
    for c555 in sorted(counts, key=lambda x: -counts[x]):
        if c555 in pal: continue
        if nxt > max_colours: raise ValueError(f'too many colours ({len(counts)})')
        pal[c555] = nxt; nxt += 1
    return pal

def cells_to_tiles(cells, pal):
    lut = np.zeros(0x8000, np.uint8)
    for c555, i in pal.items(): lut[c555] = i
    out = bytearray()
    for c in cells:
        t = np.where((c & 0x8000) != 0, lut[c & 0x7FFF], 0).astype(np.uint8)
        out += t.tobytes()
    return bytes(out)

def palette_blocks(pal, ncolours=None):
    """palette as list of 16-colour blocks (bytes, RGBx888 big-endian), entry 0 black"""
    n = (max(pal.values()) + 1) if ncolours is None else ncolours
    n = (n + 15) & ~15
    arr = [0] * n
    for c555, i in pal.items(): arr[i] = rgb888(c555)
    return [b''.join(struct.pack('>I', v) for v in arr[k:k + 16]) for k in range(0, n, 16)]

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('chr'); ap.add_argument('out_prefix')
    a = ap.parse_args()
    cells = load_cells(a.chr)
    pal = build_palette([cells])
    tiles = cells_to_tiles(cells, pal)
    open(a.out_prefix + '.tiles', 'wb').write(tiles)
    blocks = palette_blocks(pal)
    open(a.out_prefix + '.pal', 'wb').write(b''.join(blocks))
    json.dump({'cells': len(cells), 'colours': len(pal), 'blocks': len(blocks)},
              open(a.out_prefix + '.json', 'w'))
    print(f'{len(cells)} cells, {len(pal)} colours, {len(blocks)} palette blocks')
