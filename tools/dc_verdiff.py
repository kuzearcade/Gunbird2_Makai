#!/usr/bin/env python3
"""Balance diff between the Dreamcast builds US v1.000 and JP v1.002 (RESOURCE.BIN objects).

The two resource images have different layouts, so objects are paired by a lockstep crawl from matching roots
(character table SEQ hdr+0x30 per character, sub-shot table +0x34, the other SEQ header fields):
  - scripts: decoded instruction by instruction; opcodes must match, non-pointer operands are compared, pointer
    operands pair their targets (code-pointer ops -> scripts, others -> data);
  - data objects (from a pointer to the next pointer target): compared as 32-bit words; words that are pointers in
    both images pair their targets, other differing words are reported.
Everything reachable from a character's chardef is attributed to that character (first reached wins).
usage: dc_verdiff.py [--char N] [--all]     (default: Morrigan = 6, plus a per-character summary)"""
import os, sys, struct, bisect, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from gbres import Space

U, J = Space('dc_US'), Space('dc_JP')
UI, JI = seqdis.Image('dc_US'), seqdis.Image('dc_JP')
BASE = 0x8C300000
CHARDEF_PTRS = {0x40: 'data', 0x44: 'data', 0x78: 'script', 0x7C: 'data', 0x80: 'script', 0x84: 'script',
                0x88: 'script', 0x8C: 'data', 0x90: 'data', 0x94: 'data', 0x98: 'data', 0x9C: 'data',
                0xA0: 'data', 0xA4: 'data', 0xA8: 'data', 0xAC: 'data'}
NAMES = ['Marion', 'Valnus', 'Tavia', 'Hei-Cob', 'Alucard', 'Aine', 'Morrigan']


def is_res(S, v): return BASE <= v < BASE + len(S.res)


def bounds(S):
    b = set()
    for o in range(0, len(S.res) - 3, 2):
        v = struct.unpack('<I', S.res[o:o + 4])[0]
        if is_res(S, v): b.add(v)
    return sorted(b)


class Crawl:
    def __init__(self):
        self.bu, self.bj = bounds(U), bounds(J)
        self.pair, self.owner, self.todo = {}, {}, collections.deque()
        self.diffs = collections.defaultdict(list)          # owner -> [(kind, us addr, jp addr, text)]
        self.conflicts = []

    def add(self, u, j, kind, owner, via):
        if not (is_res(U, u) and is_res(J, j)): return
        if u in self.pair:
            if self.pair[u][0] != j: self.conflicts.append((hex(u), hex(j), hex(self.pair[u][0]), via))
            return
        self.pair[u] = (j, kind); self.owner[u] = owner
        self.todo.append((u, j, kind, owner))

    def end(self, b, a):
        i = bisect.bisect_right(b, a)
        return b[i] if i < len(b) else a + 0x400

    def script(self, u, j, owner):
        for _ in range(4000):
            if not UI.valid(u) or not JI.valid(j): return
            lu, tu, _, termu, opu = seqdis.decode(UI, u)
            lj, tj, _, termj, opj = seqdis.decode(JI, j)
            if opu != opj or lu != lj:
                self.diffs[owner].append(('script-diverges', u, j, f'US {tu}  |  JP {tj}')); return
            if opu is None:
                if UI.w(u) != JI.w(j): self.diffs[owner].append(('script', u, j, f'US {tu}  |  JP {tj}'))
            elif opu:
                n = (lu - 2) // 2
                ptrs = {n - 2} if opu == 0x0A else {i for i in seqdis.PTRPOS.get(opu, []) if i + 1 < n}
                i, differ = 0, False
                while i < n:
                    if i in ptrs:
                        vu, vj = UI.l(u + 2 + 2 * i), JI.l(j + 2 + 2 * i)
                        if is_res(U, vu) and is_res(J, vj):
                            self.add(vu, vj, 'script' if opu in seqdis.CODE_PTR_OPS or opu == 0x0A else 'data', owner,
                                     f'{u:x}')
                        elif vu != vj: differ = True
                        i += 2
                    else:
                        vu, vj = (UI.l(u + 2 + 2 * i), JI.l(j + 2 + 2 * i)) if i + 1 < n else (0, 0)
                        if is_res(U, vu) and is_res(J, vj):          # untyped pointer operand
                            self.add(vu, vj, 'data', owner, f'{u:x}'); i += 2; continue
                        differ |= UI.w(u + 2 + 2 * i) != JI.w(j + 2 + 2 * i); i += 1
                if differ: self.diffs[owner].append(('script', u, j, f'US {tu}  |  JP {tj}'))
            if termu: return
            u += lu; j += lj

    def data(self, u, j, owner, kind):
        nu = min(self.end(self.bu, u), BASE + len(U.res)) - u
        nj = min(self.end(self.bj, j), BASE + len(J.res)) - j
        if nu != nj: self.diffs[owner].append(('size', u, j, f'object size US {nu:#x} JP {nj:#x}'))
        k = 0
        while k + 2 <= min(nu, nj, 0x2000):
            if k + 4 <= min(nu, nj):                     # pointers may sit at any even offset
                vu, vj = U.u32(u + k), J.u32(j + k)
                if is_res(U, vu) and is_res(J, vj):
                    sub = CHARDEF_PTRS.get(k, 'data') if kind == 'chardef' else 'data'
                    self.add(vu, vj, sub, owner, f'{u:x}+{k:x}'); k += 4; continue
            hu, hj = U.u16(u + k), J.u16(j + k)
            if hu != hj:
                sx = lambda h: struct.unpack('<h', struct.pack('<H', h))[0]
                self.diffs[owner].append(('data', u + k, j + k, f'+{k:#x}: US {hu:04x} JP {hj:04x} '
                                          f'(s16 {sx(hu)} -> {sx(hj)})'))
            k += 2

    def run(self):
        hu, hj = U.u32(BASE + 0x2C), J.u32(BASE + 0x2C)
        cu, cj = U.u32(hu + 0x30), J.u32(hj + 0x30)
        for c in range(7):
            self.add(U.u32(cu + 4 * c), J.u32(cj + 4 * c), 'chardef', c, 'chartbl')
        su, sj = U.u32(hu + 0x34), J.u32(hj + 0x34)
        for c in range(7):
            self.add(U.u32(su + 4 * c), J.u32(sj + 4 * c), 'data', c, 'subshot')
        for i in range(12):
            self.add(U.u32(hu + 4 * i), J.u32(hj + 4 * i), 'data', f'hdr{i}', f'seqhdr[{i}]')
        while self.todo:
            u, j, kind, owner = self.todo.popleft()
            if kind == 'script': self.script(u, j, owner)
            else: self.data(u, j, owner, kind)


def main():
    c = Crawl(); c.run()
    per = collections.Counter(c.owner.values())
    print('paired objects:', len(c.pair), ' conflicts:', len(c.conflicts))
    for o in list(range(7)) + [f'hdr{i}' for i in range(12)]:
        name = NAMES[o] if isinstance(o, int) else o
        print(f'  {name:9s} objects {per[o]:5d}  differences {len(c.diffs[o])}')
    show = [int(sys.argv[sys.argv.index('--char') + 1])] if '--char' in sys.argv else \
        (list(range(7)) + [f'hdr{i}' for i in range(12)] if '--all' in sys.argv else [6])
    for o in show:
        print(f'\n== {NAMES[o] if isinstance(o, int) else o}')
        for kind, u, j, t in c.diffs[o]:
            print(f'  {kind:15s} US {u:08x} JP {j:08x}  {t}')


if __name__ == '__main__':
    main()
