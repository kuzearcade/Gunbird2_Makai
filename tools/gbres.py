#!/usr/bin/env python3
"""Shared helpers for Gunbird 2 resource analysis: address spaces of the arcade and DC builds,
pointer classification, and endian-aware field access."""
import os, struct

ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'


class Space:
    """An address space holding resource data (scripts + tables)."""
    def __init__(self, kind):
        self.kind = kind
        if kind == 'arcade':
            self.e = '>'
            self.prog = open(ROOT + '/assets/arcade/prog_be.bin', 'rb').read()
            self.data = open(ROOT + '/assets/arcade/pdata_be.bin', 'rb').read()
        else:
            self.e = '<'
            reg = kind.split('_')[1] if '_' in kind else 'US'
            self.res = open(ROOT + f'/assets/dc/{reg}/fs/RESOURCE.BIN', 'rb').read()

    # --- address handling -------------------------------------------------------------------
    def canon(self, a):
        if self.kind == 'arcade':
            if (a & 0xF0000000) == 0x20000000: a &= 0x0FFFFFFF          # cache-through mirror
            if 0x05000000 <= a < 0x05080000: a = a - 0x05000000 + 0x06080000
        return a

    def is_ptr(self, v):
        """plausible pointer into resource data (not code)"""
        if self.kind == 'arcade':
            v = self.canon(v)
            return 0x40000 <= v < 0x100000 or 0x06080000 <= v < 0x06100000
        return 0x8C300000 <= v < 0x8C300000 + len(self.res)

    def raw(self, a, n):
        a = self.canon(a)
        if self.kind == 'arcade':
            if 0 <= a < 0x100000: b = self.prog[a:a+n]
            elif 0x06080000 <= a < 0x06100000: b = self.data[a-0x06080000:a-0x06080000+n]
            else: return None
        else:
            if not (0x8C300000 <= a < 0x8C300000 + len(self.res)): return None
            b = self.res[a-0x8C300000:a-0x8C300000+n]
        return b if len(b) == n else None

    def u8(self, a): return self.raw(a, 1)[0]
    def u16(self, a): return struct.unpack(self.e + 'H', self.raw(a, 2))[0]
    def u32(self, a): return struct.unpack(self.e + 'I', self.raw(a, 4))[0]

    def name(self, a):
        a = self.canon(a)
        if self.kind == 'arcade':
            return f"rom+{a:05x}" if a < 0x100000 else f"pd+{a-0x06080000:05x}"
        return f"res+{a-0x8C300000:06x}"

    def section(self, a):
        """which resource section an address belongs to"""
        a = self.canon(a)
        if self.kind == 'arcade':
            if a < 0x100000: return 'SEQ' if a >= 0x60000 else 'ROM'
            o = a - 0x06080000
            for lo, hi, n in ((0x80, 0x15F48, 'PALETTE'), (0x15F48, 0x37EB8, 'BGMAP'),
                              (0x37EB8, 0x72E57, 'OBJDT'), (0x72E57, 0x78978, 'RECTDT'), (0x78978, 0x80000, 'CHECKSUM')):
                if lo <= o < hi: return n
            return 'PD?'
        o = a - 0x8C300000
        for lo, hi, n in ((0x80, 0x28CF0, 'BGMAP'), (0x28CF0, 0x92220, 'OBJDT'), (0x92220, 0x979E0, 'RECTDT'),
                          (0x979E0, 0x97A28, 'CHECKSUM'), (0x97A28, 1 << 30, 'SEQ')):
            if lo <= o < hi: return n
        return '?'


def field_kinds(pairs_d, pairs_a, dsp, asp, size):
    """Given matched instances (lists of DC and arcade base addresses) of one struct type, infer per-offset
    field kinds: 'ptr', 'u32', 'u16', 'u8', 'zero', '?'. Returns list of (offset, kind)."""
    out, k = [], 0
    while k < size:
        votes = {}
        for d, a in zip(pairs_d, pairs_a):
            dv4, av4 = dsp.raw(d + k, 4), asp.raw(a + k, 4)
            dv2, av2 = dsp.raw(d + k, 2), asp.raw(a + k, 2)
            if dv4 and av4:
                D, A = struct.unpack('<I', dv4)[0], struct.unpack('>I', av4)[0]
                if dsp.is_ptr(D) and asp.is_ptr(A): votes['ptr'] = votes.get('ptr', 0) + 1; continue
                if D == A and D != 0 and (D >> 16) != (D & 0xFFFF) and (D >> 16) != 0:
                    votes['u32'] = votes.get('u32', 0) + 1; continue
            if dv2 and av2:
                D, A = struct.unpack('<H', dv2)[0], struct.unpack('>H', av2)[0]
                if D == A:
                    votes['zero' if D == 0 else ('u16' if (D >> 8) != (D & 0xFF) else 'u16/u8')] = \
                        votes.get('zero' if D == 0 else ('u16' if (D >> 8) != (D & 0xFF) else 'u16/u8'), 0) + 1
                    continue
                if dv2 == av2: votes['u8'] = votes.get('u8', 0) + 1; continue
            votes['?'] = votes.get('?', 0) + 1
        best = max(votes, key=lambda x: (x not in ('zero', 'u16/u8'), votes[x])) if votes else '?'
        if best in ('ptr', 'u32'):
            out.append((k, best)); k += 4
        else:
            out.append((k, best if best != 'u16/u8' else 'u16')); k += 2
    return out
