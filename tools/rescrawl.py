#!/usr/bin/env python3
"""Parallel crawl of DC (RESOURCE.BIN) and arcade (SEQUENCE + data ROM) resource graphs.

Builds a DC->arcade address correspondence from matched roots (characters 0-5, SEQ header ...), then
computes Morrigan's (character 6) closure and splits it into objects already present on the arcade
(shared, mapped) and DC-only objects that must be translated.

Outputs re/map_dc2arc.json and re/morrigan_closure.json
"""
import json, struct, sys, collections
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from gbres import Space, ROOT
import seqdis

D, A = Space('dc_US'), Space('arcade')
DI, AI = seqdis.Image('dc_US'), seqdis.Image('arcade')
DC_ONLY = {o['op'] for o in seqdis.OPS.values() if o.get('tag') == 'DC-ONLY'}

mapping = {}                      # dc addr -> (arc addr, kind)
conflicts = []
todo = collections.deque()


def pair(d, a, kind, via):
    a = A.canon(a)
    if d in mapping:
        if mapping[d][0] != a: conflicts.append((d, a, mapping[d], via))
        return
    mapping[d] = (a, kind, via)
    todo.append((d, a, kind))


def dlen(img, x):
    return seqdis.decode(img, x)[0]


def walk_script(d, a):
    """lockstep over two scripts"""
    for _ in range(5000):
        if not DI.valid(d) or not AI.valid(a): return
        dl, dt, dtg, dterm, dop = seqdis.decode(DI, d)
        al, at, atg, aterm, aop = seqdis.decode(AI, a)
        if dop != aop:
            if dop in DC_ONLY: d += dl; continue          # DC asset op, arcade has nothing
            if aop is not None and aop not in DC_ONLY and dop not in (None,):
                # arcade-specific op (e.g. PltBlockSet preamble) - skip arcade side
                if aop in (0xA0, 0xA1, 0x70, 0x71): a += al; continue
            return                                         # diverged
        if dop is None:                                    # Wait: must match
            if DI.w(d) != AI.w(a): return
        elif dop is not None and dop != 0:
            n = (dl - 2) // 2
            ptrs = set()
            if dop == 0x0A: ptrs = {n - 2}
            else: ptrs = set(i for i in seqdis.PTRPOS.get(dop, []) if i + 1 < n)
            for i in sorted(ptrs):
                dv, av = DI.l(d + 2 + 2 * i), AI.l(a + 2 + 2 * i)
                if D.is_ptr(dv) and A.is_ptr(av):
                    code = dop in seqdis.CODE_PTR_OPS
                    pair(dv, av, 'script' if code else f'data:{dop:02x}.{i}', f'{D.name(d)} op{dop:02x}')
        if dterm: return
        d += dl; a += al


def walk_data(d, a, kind, limit=0x400):
    """generic paired walk over a data object; pairs pointers, stops at first unexplained mismatch"""
    k = 0
    while k < limit:
        d4, a4 = D.raw(d + k, 4), A.raw(a + k, 4)
        if d4 is None or a4 is None: return
        dv, av = struct.unpack('<I', d4)[0], struct.unpack('>I', a4)[0]
        if D.is_ptr(dv) and A.is_ptr(av):
            pair(dv, av, 'data', f'{kind}@{D.name(d)}+{k:x}'); k += 4; continue
        d2, a2 = D.raw(d + k, 2), A.raw(a + k, 2)
        if struct.unpack('<H', d2)[0] == struct.unpack('>H', a2)[0] or d2 == a2: k += 2; continue
        if dv == av: k += 4; continue
        return


CHARDEF_PTRS = {0x40: 'objdt', 0x44: 'rectdt', 0x78: 'script', 0x7C: 'data:shotdef', 0x80: 'script', 0x84: 'script',
                0x88: 'script', 0x8C: 'objdt', 0x90: 'objdt', 0x94: 'objdt', 0x98: 'objdt', 0x9C: 'objdt',
                0xA0: 'objdt', 0xA4: 'objdt', 0xA8: 'objdt', 0xAC: 'rectdt'}


def walk_chardef(d, a):
    for off, kind in CHARDEF_PTRS.items():
        pair(D.u32(d + off), A.u32(a + off), kind, f'chardef+{off:x}')


def run():
    # roots
    dct = [D.u32(0x8C40F7F0 + 4 * i) for i in range(7)]
    art = [A.u32(0xCB298 + 4 * i) for i in range(6)]
    for c in range(6):
        pair(dct[c], art[c], 'chardef', f'chartbl[{c}]')
    # SEQ header (DC res+0x97A40 <-> arcade rom 0x60018), first 12 fields align
    for i in range(12):
        dv, av = D.u32(0x8C397A40 + 4 * i), A.u32(0x60018 + 4 * i)
        if D.is_ptr(dv) and A.is_ptr(av): pair(dv, av, 'seqhdr', f'seqhdr[{i}]')
    while todo:
        d, a, kind = todo.popleft()
        if kind == 'script': walk_script(d, a)
        elif kind == 'chardef': walk_chardef(d, a)


ARC_ONLY_SKIP = {0xA0, 0xA1, 0x70, 0x71}


def fingerprint(img, sp, a, maxn=400):
    """canonical instruction sequence of one straight-line block"""
    fp = []
    for _ in range(maxn):
        if not img.valid(a): return None
        ln, txt, tg, term, op = seqdis.decode(img, a)
        if op is None: fp.append(('W', img.w(a)))
        elif op in DC_ONLY or op in ARC_ONLY_SKIP: pass
        else:
            n = (ln - 2) // 2
            ptrs = {n - 2} if op == 0x0A else set(i for i in seqdis.PTRPOS.get(op, []) if i + 1 < n)
            ops, i = [op], 0
            while i < n:
                if i in ptrs: ops.append('P'); i += 2
                else: ops.append(img.w(a + 2 + 2 * i)); i += 1
            fp.append(tuple(ops))
        if term: break
        a += ln
    return tuple(fp) if len(fp) >= 3 else None


def script_roots(sp, img, lo, hi, step):
    roots = set()
    buf = sp.res if sp.kind != 'arcade' else sp.prog
    base = 0x8C300000 if sp.kind != 'arcade' else 0
    for o in range(lo, hi - 4, step):
        v = struct.unpack(sp.e + 'I', buf[o:o + 4])[0]
        if sp.kind == 'arcade':
            if 0x60000 <= v < 0x100000 and v % 2 == 0: roots.add(v)
        elif 0x8C397A28 <= v < 0x8C300000 + len(buf): roots.add(v)
    return roots


def fp_match():
    dr = script_roots(D, DI, 0x97A28, len(D.res), 2)
    ar = script_roots(A, AI, 0x60000, 0x100000, 2)
    ar |= set(v for v in (struct.unpack('>I', A.data[o:o+4])[0] for o in range(0, len(A.data) - 4, 2))
              if 0x60000 <= v < 0x100000 and v % 2 == 0)
    dfp, afp = collections.defaultdict(list), collections.defaultdict(list)
    for r in dr:
        f = fingerprint(DI, D, r)
        if f: dfp[f].append(r)
    for r in ar:
        f = fingerprint(AI, A, r)
        if f: afp[f].append(r)
    n = 0
    for f, ds in dfp.items():
        if f in afp and len(ds) == 1 and len(afp[f]) == 1:
            if ds[0] not in mapping: pair(ds[0], afp[f][0], 'script', 'fingerprint'); n += 1
    return n, len(dfp), len(afp)


def closure(roots):
    """DC-side traversal from roots; returns {addr: kind}"""
    seen, q = {}, collections.deque(roots)
    while q:
        x, kind = q.popleft()
        if x in seen: continue
        seen[x] = kind
        if x in mapping: continue                      # shared object: don't descend
        if kind == 'script':
            out, _ = seqdis.disasm(DI, x, follow=True)
            for ia, (ln, txt, op) in out.items():
                if op in (None, 0): continue
                n = (ln - 2) // 2
                ptrs = {n - 2} if op == 0x0A else set(i for i in seqdis.PTRPOS.get(op, []) if i + 1 < n)
                for i in ptrs:
                    v = DI.l(ia + 2 + 2 * i)
                    if D.is_ptr(v):
                        q.append((v, 'script' if op in seqdis.CODE_PTR_OPS else f'data:{op:02x}.{i}'))
        elif kind == 'chardef':
            for off, k in CHARDEF_PTRS.items():
                q.append((D.u32(x + off), k))
    return seen


if __name__ == '__main__':
    run()
    for it in range(4):
        n, nd, na = fp_match()
        while todo:
            d, a, kind = todo.popleft()
            if kind == 'script': walk_script(d, a)
            elif kind == 'chardef': walk_chardef(d, a)
        print(f'fingerprint pass {it}: +{n} (dc blocks {nd}, arc blocks {na}) mapped {len(mapping)}')
        if n == 0: break
    print('mapped', len(mapping), 'conflicts', len(conflicts))
    for c in conflicts[:20]: print('  conflict', D.name(c[0]), A.name(c[1]), A.name(c[2][0]), c[3])
    json.dump({f'{d:08x}': [f'{a:08x}', k, v] for d, (a, k, v) in mapping.items()},
              open(ROOT + '/re/map_dc2arc.json', 'w'), indent=0)
    m7 = D.u32(0x8C40F7F0 + 24)
    cl = closure([(m7, 'chardef')])
    shared = {x: k for x, k in cl.items() if x in mapping}
    uniq = {x: k for x, k in cl.items() if x not in mapping}
    print('Morrigan closure', len(cl), 'shared', len(shared), 'unique', len(uniq))
    bysec = collections.Counter((D.section(x), k.split(':')[0]) for x, k in uniq.items())
    for (s, k), n in sorted(bysec.items()): print(f'  unique {s:8} {k:8} {n}')
    json.dump({'shared': {f'{x:08x}': [f'{mapping[x][0]:08x}', k] for x, k in shared.items()},
               'unique': {f'{x:08x}': k for x, k in uniq.items()}},
              open(ROOT + '/re/morrigan_closure.json', 'w'), indent=0)
