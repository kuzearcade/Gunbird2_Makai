#!/usr/bin/env python3
"""Gunbird 2 sequence-script (seqcode VM) disassembler for arcade (SH-2 BE) and Dreamcast (SH-4 LE) builds.

Opcode word: low byte = opcode, negative word = wait(-w) frames, 0x0000 = NOP (skip).
Operand lengths come from re/seq_opcodes.json (nargs, verified by MAME trace) with special cases
for the variable-length ops below.

Address spaces
  arcade: program ROM 0x00000000-0x000FFFFF, data ROM copy 0x06080000 (also cache-through 0x26080000),
          RAM image 0x06000000 (code/const copy)
  dc    : RESOURCE.BIN at 0x8C300000
"""
import json, os, struct, sys

ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
OPS = {o['op']: o for o in json.load(open(ROOT + '/re/seq_opcodes.json'))}
FIX = {0x05: 2, 0x08: 2, 0xF1: 3}          # Call ptr, Jump ptr, ExDefense 3 words
TERMINATORS = {0x01, 0x06, 0x08}            # End, Ret, Jump
PTRPOS = {int(k): v for k, v in json.load(open(ROOT + '/re/seq_ptrpos.json')).items()}
CODE_PTR_OPS = {0x05, 0x08, 0x0A, 0x11, 0x20, 0x21, 0x22}   # pointer operands that are script code


class Image:
    def __init__(self, kind):
        self.kind = kind
        if kind == 'arcade':
            self.prog = open(ROOT + '/assets/arcade/prog_be.bin', 'rb').read()
            self.data = open(ROOT + '/assets/arcade/pdata_be.bin', 'rb').read()
            self.ram = open(ROOT + '/assets/arcade/ram_init.bin', 'rb').read()
            self.e = '>'
        else:
            self.res = open(ROOT + f'/assets/dc/{kind[3:] or "US"}/fs/RESOURCE.BIN', 'rb').read()
            self.e = '<'

    def canon(self, a):
        if self.kind == 'arcade' and (a & 0xF0000000) == 0x20000000:
            a &= 0x0FFFFFFF                     # SH-2 cache-through mirror
        return a

    def raw(self, a, n):
        a = self.canon(a)
        if self.kind == 'arcade':
            if a < 0x100000: return self.prog[a:a+n]
            if 0x06080000 <= a < 0x06100000: return self.data[a-0x06080000:a-0x06080000+n]
            if 0x06000000 <= a < 0x06080000: return self.ram[a-0x06000000:a-0x06000000+n]
            if 0x05000000 <= a < 0x05080000: return self.data[a-0x05000000:a-0x05000000+n]
        else:
            if 0x8C300000 <= a < 0x8C300000 + len(self.res): return self.res[a-0x8C300000:a-0x8C300000+n]
        return None

    def valid(self, a):
        return self.raw(a, 2) not in (None, b'', b'\0') and len(self.raw(a, 2)) == 2

    def w(self, a):
        return struct.unpack(self.e + 'H', self.raw(a, 2))[0]

    def l(self, a):
        """32-bit operand as the VM reads it: two consecutive words (DC: lo,hi LE == u32 LE; arcade: hi,lo BE)."""
        b = self.raw(a, 4)
        return struct.unpack(self.e + 'I', b)[0]


def oplen(img, a, op):
    """number of operand words following the opcode word at a"""
    if op == 0x0A:                              # JumpCompare desc, A, B, target32
        d = img.w(a + 2)
        return 1 + (2 if d & 0xF0 == 0 else 1) + (2 if d & 0x0F == 0 else 1) + 2
    if op == 0x0B:                              # CalcWork desc, dst, src
        d = img.w(a + 2)
        return 2 + (2 if d & 0x0F == 0 else 1)
    if op in FIX: return FIX[op]
    return OPS[op].get('nargs_dc', OPS[op]['nargs'])


def decode(img, a):
    """-> (length_in_bytes, text, targets, is_terminator, op)"""
    ow = img.w(a)
    if ow & 0x8000:
        return 2, f"Wait {0x10000 - ow}", [], False, None
    if ow == 0:
        return 2, "Nop", [], False, 0
    op = ow & 0xFF
    n = oplen(img, a, op)
    args = [img.w(a + 2 + 2*i) for i in range(n)]
    name = OPS[op]['name'] if OPS[op]['name'] not in ('', '-') else f"op{op:02x}"
    tg, dp = [], []
    if op == 0x0A:
        tg.append(img.l(a + 2 + 2*(n - 2)))
    else:
        for i in PTRPOS.get(op, []):
            if i + 1 < n:
                (tg if op in CODE_PTR_OPS else dp).append(img.l(a + 2 + 2*i))
    txt = f"{name:<16} " + ' '.join(f"{x:04x}" for x in args)
    if ow & 0xFF00: txt += f"   [hi={ow>>8:02x}]"
    if tg: txt += '   -> ' + ' '.join(f"{t:08x}" for t in tg)
    if dp: txt += '   data ' + ' '.join(f"{t:08x}" for t in dp)
    return 2 + 2*n, txt, tg, op in TERMINATORS, op


def disasm(img, start, maxn=4000, follow=True):
    """Recursive traversal. Returns {addr: (len,text)} and set of block starts."""
    out, todo, starts = {}, [start], set([img.canon(start)])
    while todo:
        a = img.canon(todo.pop())
        n = 0
        while n < maxn and img.valid(a) and a not in out:
            ln, txt, tg, term, op = decode(img, a)
            out[a] = (ln, txt, op)
            for t in tg:
                t = img.canon(t)
                if follow and img.valid(t) and t not in starts:
                    starts.add(t); todo.append(t)
            if term: break
            a += ln; n += 1
    return out, starts


def dump(img, start):
    out, starts = disasm(img, start)
    for a in sorted(out):
        if a in starts: print(f"\nL_{a:08x}:")
        print(f"  {a:08x}  {out[a][1]}")


if __name__ == '__main__':
    kind = sys.argv[1]            # arcade | dc_US | dc_JP
    img = Image(kind)
    for s in sys.argv[2:]:
        dump(img, int(s, 16))
