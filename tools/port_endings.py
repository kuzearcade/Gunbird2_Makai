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


FRAMES = {}                                                  # composite -> animation frame count


def all_parts(v):
    """parts of every animation frame of composite v (frames are stored back to back)"""
    out, a = [], v
    for _ in range(FRAMES.get(v, 1)):
        ps = dcend.parts(DI, a); out += ps; a += 12 * len(ps)
    return out


def is_res(v): return 0x8C300000 <= v < 0x8C300000 + len(D.res)


def linear(a):
    """instructions from a up to a terminator; Sleep ends a block too (code after a Sleep is only entered through an
    explicit target), so the crawl does not run into neighbouring tasks / the DC staff roll"""
    out = {}
    for _ in range(4000):
        if not DI.valid(a) or a in out: break
        ln, txt, tg, term, op = seqdis.decode(DI, a)
        out[a] = (ln, txt, op)
        if term or txt.split()[0] in ('Sleep', 'End', 'Ret', 'AllSleep'): break
        a += ln
    return out


def crawl(slots=None):
    """-> insns {addr: (len, op, text)}, refs {obj addr: {(kind, where)}}"""
    insns, refs, todo = {}, collections.defaultdict(set), [D.u32(TBL + 4 * s) for s in (slots or ENDINGS)]
    seen = set(todo)
    while todo:
        out = linear(todo.pop())
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
                    if op == 0x61: FRAMES[v] = max(FRAMES.get(v, 1), DI.w(x + 6))   # AnimObj ptr, frames, delay, flags
    return insns, refs


def ending_of(x):
    """which ending's own code an instruction belongs to (None = shared engine)"""
    starts = sorted((D.u32(TBL + 4 * s), s) for s in ENDINGS)
    own_end = 0x8C3F4DA4                                   # END64 code runs up to the DC staff roll
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




# ==================================================================================================================
# Stage 2: build.  Output: out/end/blob.bin (RAM image for BLOB_BASE), out/end/tiles.bin + palettes, out/end/meta.json
# ==================================================================================================================
import numpy as np, hashlib
import dcend, gfxconv, jpcodes
from make_gfx import quantize

BLOB_BASE, BLOB_END = 0x06034000, 0x06040000
FILES = {26: 'END6.CHR', 6: 'END60.CHR', 12: 'END61.CHR', 17: 'END62.CHR', 21: 'END63.CHR', 24: 'END64.CHR'}
COMMON_FILE = 'END6.CHR'            # engine/common UI composites (identical cells in every END file)
COMMON_BANK = 0xE0                  # bank 0xF0 stays free: the DC engine's BG map 0x8C3E5918 (arcade 0x0ACB78, used by
                                    # END60/END61) draws with palette bank 0xF0 as loaded by the arcade
MAX_OWN_BANKS = 12                  # per ending: 12 own banks 0x10-0xC0 + 1 shared bank 0xD0 for the smaller composites
TEXT_MAGIC = 0x54585431             # 'TXT1'
DC_PUTOBJWORK = 0x67


class Blob:
    def __init__(self, base): self.base, self.data, self.fix = base, bytearray(), []
    def here(self): return self.base + len(self.data)
    def align(self, n=4):
        while len(self.data) % n: self.data.append(0)
    def put(self, b): a = self.here(); self.data += b; return a
    def u16(self, v): self.data += struct.pack('>H', v & 0xFFFF)
    def u32(self, v): self.data += struct.pack('>I', v & 0xFFFFFFFF)
    def ref(self, key): self.fix.append((len(self.data), key)); self.data += b'\0\0\0\0'


_users = {}


def common_file(v):
    """END file to take a common composite's cells from: common code (e.g. the sparkle task 0x8C3E5EF4) is shared,
    but its cells only exist in the END files of the endings that run it (END61/END64 for the sparkle; END6 has
    Morrigan picture cells at those indices)"""
    if not _users:
        for s in ENDINGS: _users[s] = set(crawl([s])[1])
    fs = [FILES[s] for s in ENDINGS if v in _users[s]] or [COMMON_FILE]
    idx = [p['idx'] + j for p in all_parts(v) for j in range(p['W'] * p['H'])]
    for f in fs[1:]:
        assert all(np.array_equal(dcend.cells('US', fs[0])[k], dcend.cells('US', f)[k]) for k in idx), (hex(v), fs)
    return fs[0]


def owners(refs):
    own = {}
    for v, rs in refs.items():
        ks = {k for k, _ in rs}
        if ks & {'pic', 'obj'}:
            es = {ending_of(x) for _, x in rs}
            own[v] = list(es)[0] if len(es) == 1 else None
    return own


def build(only=None, tnum_base=None, out=ROOT + '/out/end'):
    """only: iterable of ending slots to include (others keep their arcade scripts) - used while the gfx space for
    all six endings is not available.  tnum_base: first gfx tile (256-byte units)."""
    os.makedirs(out, exist_ok=True)
    only = set(only or ENDINGS)
    insns, refs = crawl(sorted(only))
    own = owners(refs)
    use = {v: e for v, e in own.items() if e is None or e in only}
    # ---- tiles + palettes ------------------------------------------------------------------------------------
    groups = collections.defaultdict(list)                   # (ending|None, bank) -> [composite]
    for e in sorted({e for e in use.values()}, key=lambda x: (x is None, x)):
        comps = sorted([v for v, o in use.items() if o == e],
                       key=lambda v: -sum(p['W'] * p['H'] for p in all_parts(v)))
        if e is None:
            groups[(None, COMMON_BANK)] = comps; continue
        big = comps[:MAX_OWN_BANKS]; small = comps[MAX_OWN_BANKS:]
        for i, v in enumerate(big): groups[(e, 0x10 + 0x10 * i)].append(v)
        if small: groups[(e, 0x10 + 0x10 * len(big))] += small
    tiles, tile_of_part, pal_of_group, comp_bank = bytearray(), {}, {}, {}
    part_tiles = {}                                          # content hash -> tnum offset
    for (e, bank), comps in groups.items():
        cfile = {v: FILES[e] if e is not None else common_file(v) for v in comps}
        counts = {}
        for v in comps:
            comp_bank[v] = bank; cs = dcend.cells('US', cfile[v])
            for p in all_parts(v):
                for j in range(p['W'] * p['H']):
                    c = cs[p['idx'] + j]; vv = c[(c & 0x8000) != 0] & 0x7FFF
                    u, n = np.unique(vv, return_counts=True)
                    for a, b in zip(u.tolist(), n.tolist()): counts[a] = counts.get(a, 0) + b
        rep = quantize(counts, 191)            # pens 1-0xBF: 0xC0-0xFF are per-pen alpha when a layer uses alphamap
        reps = sorted(set(rep.values()), key=lambda r: -sum(counts[c] for c in rep if rep[c] == r))
        pen = {r: 1 + i for i, r in enumerate(reps)}
        pal = {c: pen[rep[c]] for c in rep}
        cols = [0] * 256
        for r, p in pen.items(): cols[p] = int(gfxconv.rgb888(int(r)))
        pal_of_group[(e, bank)] = cols
        for v in comps:
            cs = dcend.cells('US', cfile[v])
            for p in all_parts(v):
                cells = [cs[p['idx'] + j] for j in range(p['W'] * p['H'])]
                t = gfxconv.cells_to_tiles(cells, pal)
                k = (bank, e, hashlib.md5(t).hexdigest())
                if k not in part_tiles:
                    part_tiles[k] = len(tiles) // 256; tiles += t
                tile_of_part[(v, p['idx'], e)] = part_tiles[k]
    open(out + '/tiles.bin', 'wb').write(tiles)
    # ---- blob: objdt composites -------------------------------------------------------------------------------
    B = Blob(BLOB_BASE); addr = {}
    for v, e in sorted(use.items()):
        B.align(); addr[v] = B.here()
        for p in all_parts(v):
            w = p['raw']; t = tnum_base + tile_of_part[(v, p['idx'], e)]
            B.u16(w[0]); B.u16(w[1]); B.u16(w[2]); B.u16(w[3])
            B.u16((comp_bank[v] << 8) | 0x80 | ((t >> 16) & 7)); B.u16(t & 0xFFFF)
    # ---- text descriptors -------------------------------------------------------------------------------------
    txt = json.load(open(ROOT + '/src/story/ending_text.json'))
    pairs = json.load(open(ROOT + '/out/stagedemo/end_text_pairs.json'))
    owner_f = json.load(open(ROOT + '/out/stagedemo/end_text_owner.json'))
    fslot = {f: s for s, f in FILES.items()}
    textowner = {k: fslot[f] for k, f in owner_f.items()}
    JI = seqdis.Image('dc_JP')
    texts = [v for v, rs in refs.items() if any(k == 'text' for k, _ in rs)]
    strings = []
    for v in sorted(texts):
        key = hex(v)
        en, jp = txt['en'][key], txt['jp'][key]
        fn = FILES.get(textowner[key], COMMON_FILE)
        lu = line_positions(DI, v, len(en), 'US', fn)
        lj = line_positions(JI, int(pairs[key], 16), len(jp), 'JP', fn)
        B.align(); addr[v] = B.here()
        B.u32(TEXT_MAGIC); B.u16(len(en)); B.u16(len(jp))
        for (x, y), s in zip(lu, en):
            B.u16(x); B.u16(y); B.ref(('str', len(strings))); strings.append(s.encode('ascii') + b'\0')
        for (x, y), s in zip(lj, jp):
            B.u16(x); B.u16(y); B.ref(('str', len(strings)))
            strings.append(b''.join(struct.pack('>H', c) for c in jpcodes.encode(s)))
    # ---- scripts ----------------------------------------------------------------------------------------------
    MAPx = PM.MAP
    keep = {x: v for x, v in insns.items() if x not in MAPx}
    newa, B2 = {}, None
    B.align()
    order = sorted(keep)
    pos = B.here()
    for x in order:                                          # instruction addresses (DC-only ops dropped)
        ln, op, t = keep[x]
        newa[x] = pos
        if op in PM.DC_ONLY and op != DC_PUTOBJWORK: continue
        pos += ln
    def reloc(val, where):
        if val == 0: return 0
        if val in newa: return newa[val]
        if val in addr: return addr[val]
        if val in MAPx: return MAPx[val]
        raise KeyError(f'unmapped {val:08x} from {where:08x}')
    errors = []
    for x in order:
        ln, op, t = keep[x]
        if op in PM.DC_ONLY and op != DC_PUTOBJWORK: continue
        assert B.here() == newa[x]
        B.u16(DI.w(x))
        if op in (None, 0): continue
        n = (ln - 2) // 2
        if op == 0x0B and n >= 4 and DI.w(x + 2) & 0x0F == 0:
            B.u16(DI.w(x + 2)); B.u16(DI.w(x + 4))
            v = DI.l(x + 6)
            if is_res(v):
                try: v = reloc(v, x)
                except KeyError as ex: errors.append(str(ex)); v = 0
            B.u32(v)
            for i in range(4, n): B.u16(DI.w(x + 2 + 2 * i))
            continue
        ty = ['w'] * n if op == DC_PUTOBJWORK else PM.op_types(DI, x, op, n)
        i = 0
        while i < n:
            y = x + 2 + 2 * i
            if ty[i] == 'p':
                v = DI.l(y)
                try: B.u32(reloc(v, x))
                except KeyError as ex: errors.append(str(ex)); B.u32(0)
                i += 2
            elif ty[i] == 'l': B.u32(DI.l(y)); i += 2
            elif ty[i] == 'b4': B.data += D.raw(y, 4); i += 2
            elif ty[i] == 'b2': B.data += D.raw(y, 2); i += 1
            else: B.u16(DI.w(y)); i += 1
    # ---- strings + fixups ---------------------------------------------------------------------------------------
    B.align(2)
    saddr = []
    for s in strings:
        B.align(2); saddr.append(B.here()); B.data += s
    for off, key in B.fix:
        struct.pack_into('>I', B.data, off, saddr[key[1]])
    assert B.here() <= BLOB_END, f'blob too big: {B.here() - BLOB_BASE:#x}'
    open(out + '/blob.bin', 'wb').write(bytes(B.data))
    scripts = {s: newa[D.u32(TBL + 4 * s)] for s in only}
    pal_sets = collections.defaultdict(list)
    for (e, bank), cols in pal_of_group.items():
        for s in (only if e is None else [e]): pal_sets[s].append((bank, cols))
    meta = {'blob_base': BLOB_BASE, 'blob_size': len(B.data), 'tiles': len(tiles) // 256, 'tnum_base': tnum_base,
            'scripts': {str(s): a for s, a in scripts.items()},
            'palettes': {str(s): [(b, c) for b, c in v] for s, v in pal_sets.items()}, 'errors': errors}
    json.dump(meta, open(out + '/meta.json', 'w'))
    print(f'blob {len(B.data):#x} bytes, tiles {len(tiles) // 256}, errors {len(errors)}')
    for e in errors[:20]: print('  ', e)
    return meta


def line_positions(img, addr, nlines, reg='US', fn=None):
    """text line origins (hardware = text printer coordinates, relative to the composite origin) in reading order.
    Text runs along hardware x; lines stack along y with the screen's top at the highest y.  A part of W columns
    holds W lines: column W-1 is the first.  Blank lines (columns without pixels) are skipped."""
    cs = dcend.cells(reg, fn) if fn else None
    ls = []
    for p in dcend.parts(img, addr):
        for c in range(p['W']):
            if cs is not None and not any((cs[p['idx'] + r * p['W'] + c] & 0x8000).any()
                                          for r in range(p['H']) if p['idx'] + r * p['W'] + c < len(cs)):
                continue
            ls.append((-(p['y'] + 16 * c), p['x']))
    ls.sort()
    out = [(x, -ny) for ny, x in ls]
    if len(out) != nlines:
        x, y = out[0] if out else (0, 0)
        out = [(x, y - 16 * i) for i in range(nlines)]
    return out


# ==================================================================================================================
# Stage 3: generate src/gen_endings.[ch] and the gfx data (tiles, blob and palettes pre-reversed for the window)
# ==================================================================================================================
T6 = [0, 6, 11, 15, 18, 20]
T7 = [0, 7, 13, 18, 22, 25, 26]
TXT_DX, TXT_DY = 0, 0                           # text printer coordinates = sprite (hardware) coordinates


def rev32(b):
    b = bytes(b) + b'\0' * (-len(b) % 4)
    return b''.join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


def generate(only):
    place = json.load(open(ROOT + '/out/gfx/place.json'))
    end_off = max(int(o, 16) + os.path.getsize(ROOT + '/out/gfx/' + f) for o, f in place.items())
    tnum_base = (end_off + 255) // 256
    meta = build(only, tnum_base)
    out = ROOT + '/out/end'
    tiles = open(out + '/tiles.bin', 'rb').read()
    data_off = tnum_base * 256 + len(tiles)
    data_off = (data_off + 0xFFF) & ~0xFFF
    blob = open(out + '/blob.bin', 'rb').read()
    data = bytearray(rev32(blob))
    pals = []
    for slot, lst in meta['palettes'].items():
        for bank, cols in lst:
            pals.append((int(slot), bank, data_off + len(data)))
            data += rev32(b''.join(struct.pack('>I', c) for c in cols))
    assert data_off + len(data) <= 0x4000000, f'gfx overflow {data_off + len(data):#x}'   # gunbird2m (bank 3 = 64M)
    open(ROOT + '/out/gfx/ending.tiles', 'wb').write(tiles)
    open(ROOT + '/out/gfx/ending.data', 'wb').write(bytes(data))
    place[f'{tnum_base * 256:08x}'] = 'ending.tiles'
    place[f'{data_off:08x}'] = 'ending.data'
    json.dump(place, open(ROOT + '/out/gfx/place.json', 'w'), indent=0)
    # ending table: arcade scenes moved to their 7-character slots, Morrigan slots -> her endings (RAM)
    A = Space('arcade')
    old = A.u32(A.u32(A.u32(0x0608002C) + 8) + 0x10)
    slots = ['0'] * 27
    for a in range(1, 7):
        for b in range(a, 7):
            slots[T7[a - 1] + b - a] = f'0x{A.u32(old + 4 * (T6[a - 1] + b - a)):08X}'
    solo = meta['scripts'].get('26')
    for s in (26, 6, 12, 17, 21, 24):
        a = meta['scripts'].get(str(s), solo)
        slots[s] = f'0x{a:08X}'
    h = ['/* generated by tools/port_endings.py - do not edit */', '#ifndef GEN_ENDINGS_H', '#define GEN_ENDINGS_H',
         f'#define END_BLOB_BASE 0x{BLOB_BASE:08X}', f'#define END_BLOB_GFX 0x{data_off:08X}',
         f'#define END_BLOB_SIZE 0x{(len(blob) + 3) & ~3:X}', f'#define END_N {len(only)}',
         f'#define TXT_X(hx, hy) ((hx) + ({TXT_DX}))', f'#define TXT_Y(hx, hy) ((hy) + ({TXT_DY}))',
         '#define TEXT_TYPE_ATTR(s) (VU8(0x06040074 + (s) * 0x24) = 2)',
         'struct end_pal { s16 slot; s16 bank; u32 gfx; u32 pal; };   /* pal: palette RAM address of the bank */',
         'extern const struct end_pal end_pals[]; extern const s16 end_slots[];',
         'extern const void *const gb2_end_table[27];', '#endif']
    c = ['/* generated by tools/port_endings.py - do not edit */', '#include "arcade.h"', '#include "gen_endings.h"',
         'const struct end_pal end_pals[] = {' + ', '.join(f'{{{s}, 0x{b:02X}, 0x{g:08X}, 0x{0x24040000 + b * 64:08X}}}' for s, b, g in pals) + ', {-1, 0, 0, 0}};',
         'const s16 end_slots[] = {' + ', '.join(str(s) for s in sorted(only)) + '};',
         'const void *const gb2_end_table[27] = {' + ', '.join(f'(const void *){x}' for x in slots) + '};']
    open(ROOT + '/src/gen_endings.h', 'w').write('\n'.join(h) + '\n')
    open(ROOT + '/src/gen_endings.c', 'w').write('\n'.join(c) + '\n')
    print(f'ending tiles @ tnum {tnum_base:#x} ({len(tiles) // 256}), data @ gfx {data_off:#x} ({len(data):#x})')


if __name__ == '__main__':
    only = [int(x) for x in sys.argv[1:]] or list(ENDINGS)
    generate(only)
