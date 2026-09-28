#!/usr/bin/env python3
"""Match DC script blocks to arcade script blocks by fingerprint: opcode sequence + non-pointer operand words of the
next N instructions (DC-only ops skipped, pointer/immediate-pointer operands ignored).  Arcade side: every
instruction address reachable in the SEQUENCE area (scanned linearly from each arcade script start we know)."""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
import port_morrigan as PM
DI, AI = seqdis.Image('dc_US'), seqdis.Image('arcade')
DC_ONLY = PM.DC_ONLY

def fp(img, a, n=6, dc=False):
    out = []
    for _ in range(40):
        if len(out) >= n: break
        if not img.valid(a): return None
        ln, txt, tg, term, op = seqdis.decode(img, a)
        if op in DC_ONLY: a += ln; continue
        words = [img.w(a + 2 * i) for i in range(ln // 2)]
        if op not in (None, 0):
            t = PM.op_types(img if dc else DI, a, op, (ln - 2) // 2) if dc else None
            if op == 0x0B and len(words) >= 5 and words[1] & 0x0F == 0:
                words = words[:3] + ['imm']                       # CalcWork immediate: value may be a pointer
            elif t:
                words = [words[0]] + [('p' if x == 'p' else '-' if x == '-' else w) for x, w in zip(t, words[1:])]
        out.append(tuple(words) if dc else words)
        if term: break
        a += ln
    return out

def arcade_index(n=6):
    """fingerprint -> [arcade addr] over all arcade script instructions found by the arcade seq map"""
    starts = set()
    for v in json.load(open(os.path.dirname(os.path.abspath(__file__)) + '/../re/map_dc2arc.json')).values():
        if v[1] == 'script': starts.add(int(v[0], 16))
    idx = collections.defaultdict(list); seen = set()
    for s in starts:
        out, _ = seqdis.disasm(AI, s)
        for a in out:
            if a in seen: continue
            seen.add(a)
    return seen

def normalize(img, a, types_img, n=6):
    """opcode+operand words with pointer operands (per DC-learnt types) and CalcWork immediates masked"""
    out = []
    for _ in range(60):
        if len(out) >= n: break
        if not img.valid(a): return None
        ln, txt, tg, term, op = seqdis.decode(img, a)
        if op in DC_ONLY: a += ln; continue
        w = [img.w(a + 2 * i) for i in range(ln // 2)]
        if op not in (None, 0):
            n2 = (ln - 2) // 2
            if op == 0x0B and n2 >= 4 and w[1] & 0x0F == 0: w = w[:3] + ['imm']
            elif op == 0x0A:
                w = w[:-2] + ['p']
            else:
                for i in seqdis.PTRPOS.get(op, []):
                    if i + 1 < n2: w[1 + i] = 'p'; w[2 + i] = 'p'
        out.append(tuple(w))
        if term: break
        a += ln
    return tuple(out)

if __name__ == '__main__':
    arc = arcade_index()
    print(len(arc), 'arcade instructions indexed')

def arcade_roots():
    from gbres import Space
    A = Space('arcade')
    roots = set()
    for v in json.load(open(os.path.dirname(os.path.abspath(__file__)) + '/../re/map_dc2arc.json')).values():
        if v[1] == 'script': roots.add(int(v[0], 16))
    h8 = A.u32(A.u32(0x0608002C) + 8)
    for i in range(0, 0x60, 4):
        v = A.u32(h8 + i)
        if 0x60000 <= v < 0x100000: roots.add(v)
    for t in (A.u32(h8 + 0x10),):
        for i in range(21): roots.add(A.u32(t + 4 * i))
    st = A.u32(h8)
    for s in range(7):
        t = A.u32(st + 4 * s)
        for i in range(21): roots.add(A.u32(t + 4 * i))
    return roots

def build_index(n=6):
    idx = collections.defaultdict(set)
    for r in arcade_roots():
        out, _ = seqdis.disasm(AI, r)
        for a in out:
            f = normalize(AI, a, None, n)
            if f: idx[f].add(a)
    return idx

def match(dc_addrs, n=6):
    idx = build_index(n)
    res = {}
    for a in dc_addrs:
        f = normalize(DI, a, None, n)
        hits = idx.get(f, set()) if f else set()
        res[a] = sorted(hits)
    return res
