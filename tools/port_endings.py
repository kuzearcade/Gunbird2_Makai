#!/usr/bin/env python3
"""Translate Morrigan's six Dreamcast endings (and the DC ending engine they run on) for the arcade.

Stage 1 (this file, 'inventory'): crawl the closure of the 6 ending scripts and classify every referenced object.
Pointers can appear as normal pointer operands (PutObj/AnimObj/MapSetP/PltBlockSet/...) and as 32-bit CalcWork
immediates written to work registers (w0A = text composite, w0C/w10/w14 = picture composite).
"""
import os, sys, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from gbres import Space, ROOT
import port_morrigan as PM

D, DI = PM.D, PM.DI
TBL = D.u32(D.u32(D.u32(0x8C30002C) + 8) + 0x10)
ENDINGS = {26: 'END6.CHR', 6: 'END60.CHR', 12: 'END61.CHR', 17: 'END62.CHR', 21: 'END63.CHR', 24: 'END64.CHR'}
OBJ_OPS = {0x60, 0x61, 0x63, 0x6B, 0x6C, 0x6F, 0x73}      # ops whose pointer operand is a composite (as port_morrigan)
WREG_KIND = {0x0A: 'text', 0x0C: 'pic', 0x10: 'pic', 0x14: 'pic'}


def is_res(v): return 0x8C300000 <= v < 0x8C300000 + len(D.res)


def crawl():
    """-> insns {addr: (len, op, text)}, refs {obj addr: {(kind, where)}}"""
    insns, refs, todo = {}, collections.defaultdict(set), [D.u32(TBL + 4 * s) for s in ENDINGS]
    seen = set(todo)
    while todo:
        out, _ = seqdis.disasm(DI, todo.pop(), follow=True)
        for x, (ln, txt, op) in out.items():
            insns[x] = (ln, op, txt)
            if op in (None, 0): continue
            n = (ln - 2) // 2
            name = txt.split()[0]
            if op == 0x0B and n >= 4 and DI.w(x + 2) & 0x0F == 0:          # CalcWork desc, reg, imm32
                v = DI.l(x + 6)
                if is_res(v): refs[v].add((WREG_KIND.get(DI.w(x + 4), f'w{DI.w(x + 4):02x}'), x))
                continue
            for i, t in enumerate(PM.op_types(DI, x, op, n)):
                if t != 'p': continue
                v = DI.l(x + 2 + 2 * i)
                if not is_res(v): continue
                if op in seqdis.CODE_PTR_OPS or op == 0x0A:
                    if v not in seen and v not in insns: seen.add(v); todo.append(v)
                else:
                    refs[v].add(('obj' if op in OBJ_OPS else name, x))
    return insns, refs


def ending_of(x):
    """which ending's own code an instruction belongs to (None = shared engine)"""
    starts = sorted((D.u32(TBL + 4 * s), s) for s in ENDINGS)
    own_end = 0x8C3F4B80
    for i, (a, s) in enumerate(starts):
        b = starts[i + 1][0] if i + 1 < len(starts) else own_end
        if a <= x < b: return s
    return None


def main():
    insns, refs = crawl()
    print(len(insns), 'instructions,', sum(v[0] for v in insns.values()), 'bytes')
    cnt = collections.Counter()
    for v, rs in sorted(refs.items()):
        kinds = sorted({k for k, _ in rs}); ends = sorted({str(ending_of(x)) for _, x in rs})
        attr = DI.w(v + 8)
        cnt[(tuple(kinds), 'src%d' % (attr & 0x7F) if kinds[0] in ('obj', 'pic', 'text') else '-', tuple(ends) if len(ends) > 1 else 'one')] += 1
    for k, c in sorted(cnt.items(), key=lambda x: -x[1]): print(f'{c:4d}', k)


if __name__ == '__main__':
    main()
