#!/usr/bin/env python3
"""Generate Morrigan graphics artefacts (tiles in the gfx ROM, palettes and OBJDT frame lists in program ROM).

Palette mode 'high': Morrigan's sprites use colr 0xFF with pens >= 16, i.e. palette entries 0x1000-0x10EF
(lines 0x100-0x10E), which exist in palette RAM (0x5000 bytes) but are never written by the original game.
Each *group* (in-game, select screen, ...) owns that whole range while its screen is active, so groups never
coexist: the in-game group is (re)written with the player palette at stage start, the select group when the
select screen opens.

Outputs:
  out/gfx/<group>.tiles + out/gfx/place.json     gfx ROM placements
  src/gen_gfx.c / src/gen_gfx.h                  palettes, OBJDT lists for converted DC objects, tile numbers
"""
import os, sys, json
import numpy as np
ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
sys.path.insert(0, ROOT + '/tools')
import gfxconv
from dcchr import entry
from gbres import Space

CFG = json.load(open(ROOT + '/src/morrigan_layout.json'))['gfx']
FS = ROOT + '/assets/dc/US/fs/'
D = Space('dc_US')
os.makedirs(ROOT + '/out/gfx', exist_ok=True)
COLR = CFG['colr']
PEN0 = CFG['index_start']


def quantize(counts, n):
    """reduce {c555: pixelcount} to <= n colours (weighted k-means in RGB); returns {c555: representative c555}"""
    cols = list(counts)
    if len(cols) <= n: return {c: c for c in cols}
    X = np.array([[(c >> 10) & 31, (c >> 5) & 31, c & 31] for c in cols], float)
    W = np.array([counts[c] for c in cols], float)
    order = np.argsort(-W); C = X[order[:n]].copy()
    for _ in range(25):
        d = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1); lab = d.argmin(1)
        for k in range(n):
            m = lab == k
            if m.any(): C[k] = (X[m] * W[m, None]).sum(0) / W[m].sum()
    C = np.clip(np.round(C), 0, 31).astype(int)
    d = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1); lab = d.argmin(1)
    rep = {}
    for c, k in zip(cols, lab):
        r, g, b = C[k]; rep[c] = (r << 10) | (g << 5) | b
    return rep


def load_sheet(chrf, face=None):
    """cells of a DC CHR, or of one face record of a STGDEMO.0nn portrait texture (u32 header length, then
    records {u16 idx base, u16 cells, u32 byte offset of the next record}; the first record starts at the header end)"""
    if face is None: return gfxconv.load_cells(FS + chrf)
    import struct
    d = open(FS + chrf, 'rb').read(); hl = struct.unpack('<I', d[:4])[0]
    w = struct.unpack('<%dH' % ((hl - 4) // 2), d[4:hl])
    off = hl
    for k in range(0, len(w), 4):
        base, n, nxt = w[k], w[k + 1], w[k + 2] | (w[k + 3] << 16)
        if k // 4 == face:
            raw = np.frombuffer(d[off:off + n * 512], '<u2')
            from dcchr import untwiddle
            return base, [untwiddle(raw[i * 256:(i + 1) * 256], 16, 16) for i in range(n)]
        off = nxt
    raise ValueError(face)


def load_trans_cells(fname='JIKI6.001'):
    """streamed-animation cells (seq op AnimTrans): u32 offset, u16 dest cell, u16 cell count x 40 images, then
    512-byte cells like a CHR; all images back to back, in file order"""
    import struct
    from dcchr import untwiddle
    d = open(FS + fname, 'rb').read()
    ent = [struct.unpack('<IHH', d[8 * i:8 * i + 8]) for i in range(struct.unpack('<I', d[:4])[0] // 8)]
    cells = []
    for off, _, n in ent:                      # cells row-major per image, as OBJDT frames use them
        raw = np.frombuffer(d[off:off + n * 512], '<u2')
        cells += [untwiddle(raw[j * 256:(j + 1) * 256], 16, 16) for j in range(n)]
    return cells


def obj_frames(addr, count):
    return [entry([D.u16(addr + 12 * i + 2 * k) for k in range(6)]) for i in range(count)]


def build_group(name, sheet_cells, objects, tnum_base, extra_cells=(), max_cols=240, pen0=None):
    """sheet_cells: list of all cells of the main sheet (converted 1:1) or None;
    objects: {objname: (dc addr, frame count, chr file[, face])} converted with cells gathered on demand
    (frame count 0 = a composite: the part count from the first entry, y >> 10)."""
    pen0 = PEN0 if pen0 is None else pen0
    cells, remap = [], {}
    if sheet_cells is not None: cells = list(sheet_cells)
    sheets = {}
    frames_out = {}
    for oname, spec in objects.items():
        addr, count, chrf = spec[:3]; face = spec[3] if len(spec) > 3 else None
        sk = (chrf, face)
        if sk not in sheets:
            sheets[sk] = (0, load_sheet(chrf)) if face is None else load_sheet(chrf, face)
        base, sheet = sheets[sk]
        if count == 0: count = D.u16(addr + 2) >> 10
        fr = obj_frames(addr, count); lst = []
        for e in fr:
            i0 = e['idx'] - base
            key = (sk, i0, e['w'] * e['h'])
            if key not in remap:
                remap[key] = len(cells)
                cells.extend(sheet[i0:i0 + e['w'] * e['h']])
            lst.append((e, remap[key]))
        frames_out[oname] = lst
    extras = []
    for chrf, idx, ename in extra_cells:
        if chrf not in sheets: sheets[chrf] = gfxconv.load_cells(FS + chrf)
        extras.append((ename, len(cells))); cells.append(sheets[chrf][idx])
    counts = {}
    for c in cells:
        v = c[(c & 0x8000) != 0] & 0x7FFF
        u, n = np.unique(v, return_counts=True)
        for a, b in zip(u.tolist(), n.tolist()): counts[a] = counts.get(a, 0) + b
    rep = quantize(counts, max_cols)
    reps = sorted(set(rep.values()), key=lambda r: -sum(counts[c] for c in rep if rep[c] == r))
    pen = {r: pen0 + i for i, r in enumerate(reps)}
    pal = {c: pen[rep[c]] for c in rep}
    tiles = gfxconv.cells_to_tiles(cells, pal)
    open(ROOT + f'/out/gfx/{name}.tiles', 'wb').write(tiles)
    cols = [0] * len(reps)
    for r, p in pen.items(): cols[p - pen0] = gfxconv.rgb888(r)
    print(f'{name}: {len(cells)} tiles @ tnum {tnum_base:#x}, {len(counts)} colours -> {len(reps)} pens')
    return dict(tiles=len(cells), cols=cols, frames=frames_out, extras=extras, base=tnum_base, pen0=pen0)


def attr_idx(t, colr=None):
    return ((COLR if colr is None else colr) << 8) | 0x80 | ((t >> 16) & 7), t & 0xFFFF


def main():
    groups = []
    base = CFG['tnum_base']
    # in-game: whole JIKI6.CHR 1:1 (OBJDT idx == cell index), then the JIKI6.001 streamed-animation images (her
    # charged-shot / bomb AnimTrans, tools/port_morrigan.py), then extra icons
    chr_cells = gfxconv.load_cells(FS + 'JIKI6.CHR')
    g_game = build_group('game', chr_cells + load_trans_cells(), {}, base,
                         extra_cells=[tuple(x) for x in CFG.get('extra_cells', [])], max_cols=0xBF - PEN0 + 1)
    groups.append(('game', g_game))
    base += g_game['tiles']
    # select screen
    sel_objs = {k: tuple(v) for k, v in CFG.get('select_objects', {}).items()}
    for k, v in sel_objs.items(): sel_objs[k] = (int(v[0], 16), v[1], v[2])
    g_sel = build_group('select', None, sel_objs, base)
    groups.append(('select', g_sel))
    base += g_sel['tiles']
    # stage-demo portraits (background layer: palette index must stay below 0x1000, so a normal 256-colour bank,
    # loaded by the scene script; one frame list per bank variant)
    dp = CFG.get('demo_portraits')
    if dp:
        objs = {k: (int(v[0], 16), 0, v[1], v[2]) for k, v in dp['objects'].items()}
        g_demo = build_group('demo', None, objs, base, max_cols=255, pen0=1)
        g_demo['colrs'] = [int(x, 16) for x in dp['colrs']]
        groups.append(('demo', g_demo))
        base += g_demo['tiles']

    # high-score ranking animation (palette bank of its own, loaded by the ranking script branch)
    rk = CFG.get('ranking')
    if rk:
        objs = {k: (int(v[0], 16), v[1], v[2]) for k, v in rk['objects'].items()}
        g_rank = build_group('ranking', None, objs, base, max_cols=255, pen0=1)
        g_rank['colrs'] = [int(rk['colr'], 16)]
        groups.append(('ranking', g_rank))
        base += g_rank['tiles']

    place, c, h = {}, ['/* generated by tools/make_gfx.py - do not edit */', '#include "arcade.h"',
                       '#include "gen_gfx.h"', ''], \
        ['/* generated by tools/make_gfx.py - do not edit */', '#ifndef GEN_GFX_H', '#define GEN_GFX_H',
         f'#define MORRIGAN_COLR 0x{COLR:02X}', f'#define MORRIGAN_PEN0 {PEN0}',
         f'#define MORRIGAN_TNUM_BASE 0x{CFG["tnum_base"]:X}',
         f'#define MORRIGAN_TRANS_CELL0 {len(chr_cells)}   /* first JIKI6.001 cell in the game group */']
    for gname, g in groups:
        place[f'{g["base"] * 256:08x}'] = f'{gname}.tiles'
        c.append(f'const u32 pal_{gname}[{len(g["cols"])}] = {{' + ', '.join(f'0x{v:08X}' for v in g['cols']) + '};')
        c.append(f'const u16 pal_{gname}_count = {len(g["cols"])};')
        h.append(f'extern const u32 pal_{gname}[]; extern const u16 pal_{gname}_count;')
        for ename, k in g['extras']:
            h.append(f'#define TNUM_{ename.upper()} 0x{g["base"] + k:X}')
        for oname, lst in g['frames'].items():
            for colr in g.get('colrs', [None]):
                rows = []
                for e, k in lst:
                    a, i = attr_idx(g['base'] + k, colr)
                    rows.append(f'{{0x{e["x"]:04X},0x{e["y"]:04X},0x{e["size"] >> 16:04X},0x{e["size"] & 0xFFFF:04X},0x{a:04X},0x{i:04X}}}')
                on = oname if colr is None else f'{oname}_{colr:02x}'
                c.append(f'const u16 obj_{on}[{len(lst)}][6] = {{' + ', '.join(rows) + '};')
                h.append(f'extern const u16 obj_{on}[][6];   /* {len(lst)} frames */')
        if g.get('pen0') == 1:
            # full 256-colour bank for PltBlockSet: 16 lines of 16 colours + line pointer table (0-terminated)
            bank = [0] + g['cols'] + [0] * (255 - len(g['cols']))
            c.append(f'const u32 pal_{gname}_bank[256] = {{' + ', '.join(f'0x{v:08X}' for v in bank) + '};')
            c.append(f'const u32 *const pal_{gname}_lines[17] = {{' + ', '.join(f'pal_{gname}_bank + {16 * i}' for i in range(16)) + ', 0};')
            h.append(f'extern const u32 pal_{gname}_bank[]; extern const u32 *const pal_{gname}_lines[];')
    h.append('#endif')
    json.dump(place, open(ROOT + '/out/gfx/place.json', 'w'), indent=0)
    open(ROOT + '/src/gen_gfx.c', 'w').write('\n'.join(c) + '\n')
    open(ROOT + '/src/gen_gfx.h', 'w').write('\n'.join(h) + '\n')


if __name__ == '__main__':
    main()
