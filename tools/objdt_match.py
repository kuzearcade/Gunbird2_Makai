#!/usr/bin/env python3
"""Match DC and arcade OBJDT sprite lists by geometry (x, y, size of each frame) and align the SEQ hdr +0x1C
global resource tables. Writes re/globaltbl_align.json: list of [dc_index, dc_addr, [arc_indices], method]."""
import sys, json, struct, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gbres import Space, ROOT
D, A = Space('dc_US'), Space('arcade')
M = {int(k, 16): int(v[0], 16) for k, v in json.load(open(ROOT + '/re/map_dc2arc.json')).items()}
M.update({int(k, 16): int(v, 16) for k, v in json.load(open(ROOT + '/re/map_extra.json')).items()})

def geo(sp, a, n=6):
    """geometry signature of up to n frames (stops at an implausible entry)"""
    out = []
    for i in range(n):
        raw = sp.raw(a + 12 * i, 12)
        if raw is None: break
        w = struct.unpack(sp.e + '6H', raw)
        if (w[2] & 0xF0FF) not in range(0, 0x3100) or (w[3] & 0x00FF) or (w[4] & 0x70):
            break
        out.append(w[:4])
    return tuple(out) if len(out) >= 1 else None

def table(sp, a, n=260): return [sp.u32(a + 4 * i) for i in range(n)]

def main():
    dt, at = table(D, 0x8C397B5C), table(A, 0x60278)
    ageo = {}
    for j, v in enumerate(at):
        if v and A.is_ptr(v):
            g = geo(A, v)
            if g: ageo.setdefault(g, []).append(j)
    aptr = {}
    for j, v in enumerate(at):
        if v: aptr.setdefault(A.canon(v), []).append(j)
    align = []
    for i, v in enumerate(dt):
        if v == 0: align.append((i, '0', [], 'null')); continue
        if not D.is_ptr(v): align.append((i, hex(v), [], 'value')); continue
        if v in M and A.canon(M[v]) in aptr: align.append((i, D.name(v), aptr[A.canon(M[v])], 'map')); continue
        g = geo(D, v)
        if g and g in ageo: align.append((i, D.name(v), ageo[g], 'geo')); continue
        align.append((i, D.name(v), [], '??'))
    json.dump(align, open(ROOT + '/re/globaltbl_align.json', 'w'))
    # summarize index shifts using unique matches
    prev = None
    for i, n, js, how in align:
        if len(js) == 1:
            d = js[0] - i
            if d != prev: print(f'dc[{i}] -> arc[{js[0]}]  (shift {d:+d})'); prev = d
    print('unmatched:', [(i, n) for i, n, js, how in align if how == '??'])

if __name__ == '__main__':
    main()
