#!/usr/bin/env python3
"""Score-based DC<->arcade function matcher (Jaccard over matched callees/callers + constant features)."""
import re, json, collections
ROOT = __file__.rsplit('/', 2)[0]

def load(path, lo, hi):
    src = open(path).read()
    names, body = {}, {}
    for m in re.finditer(r'^// ==== (\S+) @ ([0-9a-f]+)\n(.*?)(?=^// ==== |\Z)', src, re.S | re.M):
        a = int(m.group(2), 16)
        if lo <= a < hi: names[m.group(1)] = a; body[a] = m.group(3)
    callees = {}
    for a, b in body.items():
        cs = set()
        for c in re.findall(r'\b((?:FUN_[0-9a-f]{8})|[A-Za-z_]\w*)\s*\(', b):
            t = names.get(c)
            if t is not None and t != a: cs.add(t)
        callees[a] = cs
    callers = collections.defaultdict(set)
    for a, cs in callees.items():
        for t in cs: callers[t].add(a)
    consts = {a: set(int(x, 16) for x in re.findall(r'\b0x([0-9a-f]{2,4})\b', b)) - {0xff, 0xffff} for a, b in body.items()}
    return names, body, callees, callers, consts

dn, db, dce, dcr, dk = load(ROOT + '/re/export/dc_US.c', 0x8C010000, 0x8C081500)
an, ab, ace, acr, ak = load(ROOT + '/re/export/arcade.c', 0x06000000, 0x0602DCDC)
m = {int(k, 16): int(v, 16) for k, v in json.load(open(ROOT + '/re/func_dc2arc.seed.json')).items()}
m = {d: a for d, a in m.items() if d in db and a in ab}
inv = {a: d for d, a in m.items()}

def score(d, a):
    md = {m[x] for x in dce[d] if x in m}; ma = {x for x in ace[a] if x in inv}
    cd = {m[x] for x in dcr[d] if x in m}; ca = {x for x in acr[a] if x in inv}
    s1 = len(md & ma) / max(1, len(md | ma)) if (md or ma) else 0
    s2 = len(cd & ca) / max(1, len(cd | ca)) if (cd or ca) else 0
    s3 = len(dk[d] & ak[a]) / max(1, len(dk[d] | ak[a]))
    n = len(md & ma) + len(cd & ca)
    return (s1 + s2) + 0.5 * s3, n

for rnd in range(40):
    added = 0
    # candidate arcade funcs: neighbours of matched pairs
    for d in list(db):
        if d in m: continue
        cand = set()
        for x in dce[d] | dcr[d]:
            if x in m:
                cand |= acr[m[x]] | ace[m[x]]
        cand = {a for a in cand if a not in inv}
        if not cand: continue
        sc = sorted(((score(d, a), a) for a in cand), reverse=True)
        (s, n), a = sc[0]
        s2 = sc[1][0][0] if len(sc) > 1 else 0
        if n >= 2 and s >= 0.6 and s - s2 >= 0.25:
            # mutual best check
            back = sorted(((score(x, a), x) for x in {y for z in ace[a] | acr[a] if z in inv for y in dce[inv[z]] | dcr[inv[z]]} if x not in m), reverse=True)
            if back and back[0][1] != d: continue
            m[d] = a; inv[a] = d; added += 1
    if not added: break
print('matched', len(m), 'rounds', rnd + 1)
json.dump({f'{d:08x}': f'{a:08x}' for d, a in m.items()}, open(ROOT + '/re/func_dc2arc.json', 'w'), indent=0)
dname = {v: k for k, v in dn.items()}
syms = {}
for d, a in m.items():
    n = dname.get(d, '')
    syms[a] = n if n and not n.startswith('FUN_') else f'dc_{d:08x}'
old = {}
for line in open(ROOT + '/re/arcade.sym'):
    if line.startswith('#') or not line.strip(): continue
    x, n = line.split()[:2]
    if not n.startswith('dc_'): old[int(x, 16)] = n
syms.update(old)
with open(ROOT + '/re/arcade.sym', 'w') as f:
    f.write('# arcade symbols (dc_XXXXXXXX = DC twin address)\n')
    for x in sorted(syms): f.write(f'{x:08x} {syms[x]}\n')
