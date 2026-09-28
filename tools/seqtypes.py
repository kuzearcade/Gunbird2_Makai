#!/usr/bin/env python3
"""Classify every sequence-script operand position as u16 / u32 / bytes / ptr by comparing the raw bytes of
paired DC and arcade instructions (from re/map_dc2arc.json). Writes re/seq_types.json:
  { "op" or "op:descLowByte": ["w"|"l"|"b2"|"b4"|"p", ...] }  (one entry per operand word; l/b4/p cover 2 words)
Fallback for unseen positions: handler read order (re/seq_readorder.json).
"""
import sys, json, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from gbres import Space, ROOT

D, A = Space('dc_US'), Space('arcade')
DI, AI = seqdis.Image('dc_US'), seqdis.Image('arcade')
DC_ONLY = {o['op'] for o in seqdis.OPS.values() if o.get('tag') == 'DC-ONLY'}

def key_of(img, a, op):
    return f"{op}:{img.w(a + 2) & 0xFF}" if op in (0x0A, 0x0B) else str(op)

def classify_pairs():
    m = {int(k, 16): (int(v[0], 16), v[1]) for k, v in json.load(open(ROOT + '/re/map_dc2arc.json')).items()}
    votes = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    lens = {}
    seen = set()
    for d, (a, k) in m.items():
        if k != 'script': continue
        x, y = d, a
        for _ in range(3000):
            if (x, y) in seen or not DI.valid(x) or not AI.valid(y): break
            seen.add((x, y))
            dl, _, _, dterm, dop = seqdis.decode(DI, x)
            al, _, _, aterm, aop = seqdis.decode(AI, y)
            if dop != aop:
                if dop in DC_ONLY: x += dl; continue
                if aop in (0xA0, 0xA1, 0x70, 0x71): y += al; continue
                break
            if dop not in (None, 0) and dl == al:
                n = (dl - 2) // 2
                kk = key_of(DI, x, dop); lens[kk] = n
                ptrs = {n - 2} if dop == 0x0A else set(i for i in seqdis.PTRPOS.get(dop, []) if i + 1 < n)
                i = 0
                while i < n:
                    db2, ab2 = D.raw(x + 2 + 2 * i, 2), A.raw(y + 2 + 2 * i, 2)
                    db4, ab4 = D.raw(x + 2 + 2 * i, 4), A.raw(y + 2 + 2 * i, 4)
                    if i in ptrs: votes[kk][i]['p'] += 1; i += 2; continue
                    if i + 1 < n and db4 and ab4 and db4 != ab4 and db4 == ab4[::-1] and db4[:2] != db4[2:]:
                        votes[kk][i]['l'] += 1
                    elif i + 1 < n and db4 and ab4 and db4 == ab4 and db4[:2] != db4[1::-1] + b'' and db4 != db4[::-1] \
                            and db4[0:2] != db4[1::-1]:
                        votes[kk][i]['b4'] += 1
                    if db2 == ab2[::-1] and db2 != ab2: votes[kk][i]['w'] += 1
                    elif db2 == ab2 and db2 != db2[::-1]: votes[kk][i]['b2'] += 1
                    i += 1
            if dterm: break
            x += dl; y += al
    return votes, lens

def resolve(votes, lens):
    order = {int(k): v for k, v in json.load(open(ROOT + '/re/seq_readorder.json')).items()} \
        if os.path.exists(ROOT + '/re/seq_readorder.json') else {}
    out = {}
    for kk, n in lens.items():
        op = int(kk.split(':')[0])
        types, i = [], 0
        while i < n:
            v = votes[kk][i]
            if v['p']: types += ['p', '-']; i += 2; continue
            if v['l'] > max(v['w'], v['b2']) or (v['l'] and not v['w']): types += ['l', '-']; i += 2; continue
            if v['b4'] and not v['w'] and not v['l']: types += ['b4', '-']; i += 2; continue
            if v['b2'] and not v['w']: types.append('b2'); i += 1; continue
            types.append('w'); i += 1
        out[kk] = types[:n]
    return out

if __name__ == '__main__':
    votes, lens = classify_pairs()
    out = resolve(votes, lens)
    json.dump(out, open(ROOT + '/re/seq_types.json', 'w'), indent=0)
    for k in sorted(out, key=lambda s: (int(s.split(':')[0]), s)):
        t = out[k]
        if any(x not in ('w',) for x in t):
            print(k, seqdis.OPS[int(k.split(':')[0])]['name'], t)
