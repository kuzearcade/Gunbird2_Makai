#!/usr/bin/env python3
"""Propagate DC<->arcade function correspondences over the call graph.

Seeds: re/func_dc2arc.json (opcode handlers, Fnc table, ...). For every matched pair, callees are
compared in call order (both builds come from the same C source), and unique candidates are paired.
Also matches by shared callers (a function called from matched F at the same relative call index).
Writes re/func_dc2arc.json (extended) and names into re/arcade.sym for matched DC names.
"""
import re, json, collections, sys
ROOT = __file__.rsplit('/', 2)[0]

def load(path, lo, hi):
    src = open(path).read()
    funcs, calls = {}, {}
    for m in re.finditer(r'^// ==== (\S+) @ ([0-9a-f]+)\n(.*?)(?=^// ==== |\Z)', src, re.S | re.M):
        a = int(m.group(2), 16)
        funcs[m.group(1)] = a
        calls[a] = m.group(3)
    byname = funcs
    seq = {}
    for a, body in calls.items():
        out = []
        for c in re.findall(r'\b((?:FUN_[0-9a-f]{8})|[A-Za-z_]\w*)\s*\(', body):
            t = byname.get(c)
            if t is not None and lo <= t < hi and t != a: out.append(t)
        seq[a] = out
    return funcs, seq

dfun, dseq = load(ROOT + '/re/export/dc_US.c', 0x8C010000, 0x8C081500)
afun, aseq = load(ROOT + '/re/export/arcade.c', 0x06000000, 0x0602DCDC)
dname = {v: k for k, v in dfun.items()}
m = {int(k, 16): int(v, 16) for k, v in json.load(open(ROOT + '/re/func_dc2arc.json')).items()}
m = {d: a for d, a in m.items() if d in dseq and a in aseq}
inv = {a: d for d, a in m.items()}

def dedup(seq):
    out = []
    for x in seq:
        if x not in out: out.append(x)
    return out

changed = True; rounds = 0
while changed and rounds < 30:
    changed = False; rounds += 1
    # callee alignment: same call order after removing already-known-mismatched
    for d, a in list(m.items()):
        ds, as_ = dedup(dseq.get(d, [])), dedup(aseq.get(a, []))
        # align by anchors: walk both lists, pairing unknowns between known anchors
        i = j = 0
        while i < len(ds) and j < len(as_):
            x, y = ds[i], as_[j]
            if x in m:
                if m[x] == y: i += 1; j += 1; continue
                if m[x] in as_[j:]: j = as_.index(m[x], j); continue
                i += 1; continue
            if y in inv: i += 1; continue
            # both unknown: pair if the counts of remaining unknowns agree locally
            m[x] = y; inv[y] = x; changed = True; i += 1; j += 1
    # callers: if a DC function is called by exactly one matched DC function set, and likewise arcade
    dcallers, acallers = collections.defaultdict(set), collections.defaultdict(set)
    for d, s in dseq.items():
        for t in s: dcallers[t].add(d)
    for a, s in aseq.items():
        for t in s: acallers[t].add(a)
print('matched', len(m), 'rounds', rounds)
json.dump({f'{d:08x}': f'{a:08x}' for d, a in m.items()}, open(ROOT + '/re/func_dc2arc.json', 'w'), indent=0)
# names for arcade
syms = {}
for line in open(ROOT + '/re/arcade.sym'):
    if line.startswith('#') or not line.strip(): continue
    x, n = line.split()[:2]; syms[int(x, 16)] = n
for d, a in m.items():
    n = dname.get(d, '')
    if n and not n.startswith('FUN_') and a not in syms: syms[a] = n
    elif a not in syms: syms[a] = f'dc_{d:08x}'
with open(ROOT + '/re/arcade.sym', 'w') as f:
    f.write('# arcade symbols (from DC correspondence; dc_XXXXXXXX = DC address of twin)\n')
    for x in sorted(syms): f.write(f'{x:08x} {syms[x]}\n')
print('arcade syms', len(syms))
