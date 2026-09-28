#!/usr/bin/env python3
"""Translate Morrigan's Dreamcast resources (RESOURCE.BIN objects reachable from her character data) into
arcade-format blobs placed in free program ROM.

Object kinds and how they are translated:
  script   - seq bytecode: opcodes copied, operands typed via re/seq_types.json (+ rules), pointers relocated,
             DC-only asset ops dropped.
  objdt    - sprite frame lists (12-byte entries): x,y,size copied; attr/idx rewritten to the converted tiles.
  typed    - data structs: field widths learnt from the same data path for characters 0-5 (paired DC/arcade
             instances), pointers relocated.
Pointers to objects that also exist on the arcade are mapped through re/map_dc2arc.json.

Outputs out/res/morrigan.json: {"blobs": [[addr, hex], ...], "symbols": {...}, "errors": [...]}
"""
import sys, os, json, struct, bisect, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from gbres import Space, ROOT, field_kinds
from dcchr import entry

D, A = Space('dc_US'), Space('arcade')
DI, AI = seqdis.Image('dc_US'), seqdis.Image('arcade')
DC_ONLY = {o['op'] for o in seqdis.OPS.values() if o.get('tag') == 'DC-ONLY'}
TYPES = json.load(open(ROOT + '/re/seq_types.json'))
MAP = {int(k, 16): int(v[0], 16) for k, v in json.load(open(ROOT + '/re/map_dc2arc.json')).items()}
if os.path.exists(ROOT + '/re/map_extra.json'):
    MAP.update({int(k, 16): int(v, 16) for k, v in json.load(open(ROOT + '/re/map_extra.json')).items()})
CFG = json.load(open(ROOT + '/src/morrigan_layout.json'))

DC_CHARTBL, ARC_CHARTBL = 0x8C40F7F0, 0xCB298
DC_SUBTBL, ARC_SUBTBL = 0x8C40FE20, 0xCB800
M = 6                                                          # Morrigan's 0-based character index

# ---- DC object boundaries (any pointer target) ------------------------------------------------------
def dc_bounds():
    b = set(MAP)
    res = D.res
    for o in range(0, len(res) - 4, 2):
        v = struct.unpack('<I', res[o:o + 4])[0]
        if 0x8C300000 <= v < 0x8C300000 + len(res): b.add(v)
    return sorted(b)
BOUNDS = dc_bounds()
def dc_size(a, cap=0x2000):
    i = bisect.bisect_right(BOUNDS, a)
    return min(BOUNDS[i] - a, cap) if i < len(BOUNDS) else cap

# ---- script helpers --------------------------------------------------------------------------------
def op_types(img, a, op, n):
    """per-operand-word type list for the instruction at a (DC image)"""
    if op == 0x0A:
        d = img.w(a + 2); t = ['w']
        t += ['l', '-'] if d & 0xF0 == 0 else ['w']
        t += ['l', '-'] if d & 0x0F == 0 else ['w']
        return t + ['p', '-']
    if op == 0x0B:
        d = img.w(a + 2)
        return ['w', 'w'] + (['l', '-'] if d & 0x0F == 0 else ['w'])
    t = TYPES.get(str(op))
    if t and len(t) == n: return t
    if t is None:
        # no paired evidence: pointers from learnt positions, rest u16
        t = ['w'] * n
        for i in seqdis.PTRPOS.get(op, []):
            if i + 1 < n: t[i], t[i + 1] = 'p', '-'
        return t
    return (t + ['w'] * n)[:n]

class Porter:
    def __init__(self):
        self.objs = {}            # dc addr -> kind/path
        self.new = {}             # dc addr -> arcade addr (object bases and every script instruction)
        self.blobs = []           # (arcade addr, bytes, [(offset, dc_target)] fixups)
        self.errors = []
        self.syms = {}
        self.script_insns = {}    # dc instr addr -> (len, op)

    # ---- discovery ---------------------------------------------------------------------------------
    def add(self, a, kind):
        if a in MAP or a in self.objs: return
        self.objs[a] = kind
        self.todo.append((a, kind))

    def discover(self, roots):
        self.todo = collections.deque()
        for a, k in roots: self.add(a, k)
        while self.todo:
            a, kind = self.todo.popleft()
            if kind == 'script':
                out, _ = seqdis.disasm(DI, a, follow=True)
                for x, (ln, txt, op) in out.items():
                    self.script_insns[x] = (ln, op)
                    if op in (None, 0): continue
                    n = (ln - 2) // 2
                    for i, t in enumerate(op_types(DI, x, op, n)):
                        if t != 'p': continue
                        v = DI.l(x + 2 + 2 * i)
                        if not D.is_ptr(v): continue
                        if op in seqdis.CODE_PTR_OPS or op == 0x0A:
                            if v not in self.script_insns and v not in MAP: self.add(v, 'script')
                        elif op in (0x60, 0x61, 0x63, 0x6B, 0x6C, 0x6F, 0x73):
                            self.add(v, 'objdt')
                        else:
                            self.add(v, f'op{op:02x}.{i}')
            elif kind == 'chardef':
                for off, k in CFG['chardef_ptrs'].items():
                    v = D.u32(a + int(off, 16))
                    if D.is_ptr(v): self.add(v, k)
            elif kind in CFG['typed']:
                spec = CFG['typed'][kind]
                size = spec.get('size') or dc_size(a)
                ftypes = spec.get('fields', {})
                for off in range(0, size - 3, 2):
                    v = D.u32(a + off)
                    if ftypes and hex(off) in ftypes and ftypes[hex(off)] != 'p': continue
                    if off % 2 == 0 and D.is_ptr(v) and D.section(v) != '?':
                        sub = spec.get('ptr_kinds', {}).get(hex(off), spec.get('default_ptr_kind', 'unknown'))
                        if sub in ('objdt_or_rect', 'unknown'):
                            sub = {'OBJDT': 'objdt', 'RECTDT': 'rectdt'}.get(D.section(v), sub)
                        self.add(v, sub)

    # ---- layout ------------------------------------------------------------------------------------
    def layout(self):
        # merge script instructions into contiguous regions
        regs, cur = [], None
        for x in sorted(self.script_insns):
            ln, op = self.script_insns[x]
            if x in MAP and x not in self.objs: continue      # shared script: leave on arcade
            if cur and x == cur[1]: cur[1] = x + ln; cur[2].append(x)
            else:
                cur = [x, x + ln, [x]]; regs.append(cur)
        self.script_regions = regs
        placement = []
        for s, e, insns in regs:
            size = sum(self.script_insns[x][0] for x in insns if self.script_insns[x][1] not in DC_ONLY)
            placement.append(('script', s, size, insns))
        for a, k in sorted(self.objs.items()):
            if k == 'script': continue
            if k == 'objdt': placement.append(('objdt', a, dc_size(a), None))
            elif k in CFG['typed']: placement.append((k, a, CFG['typed'][k].get('size') or dc_size(a), None))
            else: self.errors.append(f'untyped object {D.name(a)} kind {k} size {dc_size(a):#x}')
        # allocate: objdt -> OBJ area, others -> DATA area
        pos = {'objdt': CFG['objdt_area'][0], 'data': CFG['data_area'][0]}
        lim = {'objdt': CFG['objdt_area'][1], 'data': CFG['data_area'][1]}
        self.place = []
        for kind, a, size, insns in placement:
            area = 'objdt' if kind == 'objdt' else 'data'
            p = (pos[area] + 3) & ~3
            if p + size > lim[area]: self.errors.append(f'area {area} full at {D.name(a)}'); continue
            pos[area] = p + size
            self.place.append((kind, a, size, insns, p))
            self.new[a] = p
            if kind == 'script':
                q = p
                for x in insns:
                    self.new[x] = q
                    if self.script_insns[x][1] not in DC_ONLY: q += self.script_insns[x][0]
        self.used = pos

    # ---- translation -------------------------------------------------------------------------------
    def reloc(self, v, where):
        if v == 0: return 0
        if v in self.new: return self.new[v]
        if v in MAP: return MAP[v]
        # pointer into the middle of an object
        i = bisect.bisect_right(sorted(self.new), v) - 1
        keys = sorted(self.new)
        if i >= 0 and keys[i] in self.objs and v - keys[i] < dc_size(keys[i]):
            return self.new[keys[i]] + (v - keys[i])
        mk = sorted(MAP); j = bisect.bisect_right(mk, v) - 1
        if j >= 0 and v - mk[j] < 0x100 and v - mk[j] < dc_size(mk[j]):
            return MAP[mk[j]] + (v - mk[j])
        self.errors.append(f'unmapped pointer {D.name(v)} from {where}')
        return 0

    def tr_script(self, insns):
        out = bytearray()
        for x in insns:
            ln, op = self.script_insns[x]
            if op in DC_ONLY: continue
            out += struct.pack('>H', DI.w(x))
            if op in (None, 0): continue
            n = (ln - 2) // 2
            t = op_types(DI, x, op, n)
            i = 0
            while i < n:
                y = x + 2 + 2 * i
                if t[i] == 'p': out += struct.pack('>I', self.reloc(DI.l(y), D.name(x))); i += 2
                elif t[i] == 'l': out += struct.pack('>I', DI.l(y)); i += 2
                elif t[i] in ('b4',): out += D.raw(y, 4); i += 2
                elif t[i] == 'b2': out += D.raw(y, 2); i += 1
                else: out += struct.pack('>H', DI.w(y)); i += 1
        return bytes(out)

    def tr_objdt(self, a, size):
        out = bytearray()
        g = CFG['gfx']
        for k in range(size // 12):
            e = entry([D.u16(a + 12 * k + 2 * j) for j in range(6)])
            src = e['attr'] & 0x7F
            if src != 1: self.errors.append(f'objdt {D.name(a)}[{k}] attr {e["attr"]:#x} not JIKI6')
            tnum = g['tnum_base'] + e['idx']
            attr = (g['colr'] << 8) | 0x80 | ((tnum >> 16) & 7)
            out += struct.pack('>6H', e['x'], e['y'], D.u16(a + 12 * k + 4), D.u16(a + 12 * k + 6), attr, tnum & 0xFFFF)
        return bytes(out)

    def tr_typed(self, kind, a, size):
        spec = CFG['typed'][kind]
        fields = {int(o, 16): t for o, t in spec.get('fields', {}).items()}
        # value remaps for 16-bit fields: {"0x2": {"13": 9}} (DC-only enum values -> arcade equivalents)
        remap = {int(o, 16): {int(k): v for k, v in m.items() if not k.startswith('_')}
                 for o, m in spec.get('remap', {}).items()}
        out = bytearray(); off = 0
        while off < size:
            t = fields.get(off)
            v4 = D.raw(a + off, 4) if off + 4 <= size else None
            if t is None and v4 and D.is_ptr(struct.unpack('<I', v4)[0]) and off % 2 == 0: t = 'p'
            t = t or spec.get('default', 'w')
            if t == 'p': out += struct.pack('>I', self.reloc(D.u32(a + off), f'{kind}@{D.name(a)}+{off:x}')); off += 4
            elif t == 'l': out += struct.pack('>I', D.u32(a + off)); off += 4
            elif t == 'b': out += D.raw(a + off, 1); off += 1
            else: out += struct.pack('>H', remap.get(off, {}).get(D.u16(a + off), D.u16(a + off))); off += 2
        return bytes(out)

    def translate(self):
        for kind, a, size, insns, p in self.place:
            if kind == 'script': b = self.tr_script(insns)
            elif kind == 'objdt': b = self.tr_objdt(a, size)
            else: b = self.tr_typed(kind, a, size)
            self.blobs.append((p, b, kind, D.name(a)))

def main():
    P = Porter()
    m7 = D.u32(DC_CHARTBL + 4 * M)
    roots = [(m7, 'chardef'), (D.u32(DC_SUBTBL + 4 * M), 'subshot_tbl')]
    P.discover(roots)
    P.layout()
    P.translate()
    P.syms['MORRIGAN_CHARDEF'] = P.new.get(m7, 0)
    P.syms['MORRIGAN_SUBSHOT_TBL'] = P.new.get(D.u32(DC_SUBTBL + 4 * M), 0)
    os.makedirs(ROOT + '/out/res', exist_ok=True)
    json.dump({'blobs': [[f'{p:08x}', b.hex(), k, n] for p, b, k, n in P.blobs],
               'symbols': {k: f'{v:08x}' for k, v in P.syms.items()},
               'errors': P.errors, 'used': {k: f'{v:08x}' for k, v in P.used.items()}},
              open(ROOT + '/out/res/morrigan.json', 'w'), indent=0)
    kinds = collections.Counter(k for k in P.objs.values())
    print('objects', dict(kinds), 'script regions', len(P.script_regions))
    print('area use', {k: hex(v) for k, v in P.used.items()})
    print('errors', len(P.errors))
    for e in P.errors[:40]: print('  ', e)

if __name__ == '__main__':
    main()
