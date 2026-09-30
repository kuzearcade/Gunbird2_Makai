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
    if v in BD_OBJ: return all_parts(BD_OBJ[v])
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
from dcchr import untwiddle

BLOB_BASE, BLOB_END = 0x06034000, 0x06040000
FILES = {26: 'END6.CHR', 6: 'END60.CHR', 12: 'END61.CHR', 17: 'END62.CHR', 21: 'END63.CHR', 24: 'END64.CHR'}
COMMON_FILE = 'END6.CHR'            # engine/common UI composites (identical cells in every END file)
COMMON_BANK = 0xE0                  # bank 0xF0 is not used (the BG backdrop is a sprite object, see BACKDROP)
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


# The END60 / END61 close-ups (Morrigan "Soul fist!!", Marion "Morrigan! You!!") are transparent pictures over the DC
# engine's backdrop map 0x8C3E5918 (ENDBG speed lines), shown by the tasks 0x8C3E5D90 / 0x8C3E5E30 as a BG layer: it
# covers the previous picture, then the close-up slides in over it.  On the arcade a BG layer's priority against sprites
# differs between MAME and the real PS5 (on the board it covered the pictures) and the arcade map 0x0ACB78 is different
# art, so the backdrop is a sprite object instead: a synthetic composite (BD_OBJ) with the close-up's window geometry,
# drawn with the DC ENDBG pixels.  The backdrop tasks are type 0x0400 (no object of their own), so their BG setup
# (MapSetP .. ShowBg, 28 bytes) becomes SetNewAct 0x0200 of a synthetic task (DeathSyncOn: it ends with the backdrop
# task, where the DC hides the BG; the close-up tasks' object setup, BD_PRIO; PutObj of the backdrop) + Nops.
# Placement, from DC Ending
# Demo captures (a scratch alignment of the picture and the map against the frame): the map pixel under picture-rect
# pixel (y, x) - the picture turned by np.rot90(.., ROT) - is np.rot90(map, MROT)[y - oy, x - ox].
BACKDROP_MAP = 0x8C327770                  # sub-map of 0x8C3E5918: u16 0, 16, W, H, then u32 entries (cell << 16)
BACKDROP = {0x8C38C9B8: (-132, -287), 0x8C38C85C: (-144, -272)}      # close-up composite -> (ox, oy)
ROT, MROT = 1, 3
BD_OBJ = {0x7F000000 | (c & 0xFFFFFF): c for c in BACKDROP}        # synthetic backdrop composite -> its close-up
BD_TASKS = {0x8C3E5D90: 0x8C38C85C, 0x8C3E5E30: 0x8C38C9B8}          # backdrop task -> close-up
BD_SETUP = 28                              # MapSetP 14 + BgPriority 4 + BgCfd 4 + BgFullScreenSet 4 + ShowBg 2
BD_PRIO = 0x0E                             # ObjPriority (higher = on top): over the pictures (0x0C / 0x0D), under
CLOSEUP_PRIO = 0x0F                        # the close-up, which the DC leaves at 0x0A (0x8C3E623C) since its BG hides
CLOSEUP_CALLS = {0x8C3F22B8, 0x8C3F320C}   # the rest; masks 0x1E / 0x1F, text 0x7F.  Their Call 623c -> CLOSEUP_PRIO
OP_RET = 0x06
OP_SLEEP, OP_SETNEWACT, OP_DEATHSYNC, OP_HARDPRIO, OP_PRIO, OP_MOVEPOS, OP_PUTOBJ = 0x02, 0x20, 0x2C, 0x75, 0x74, 0x44, 0x60
# The engine's full-screen white plate: faded with sprite alpha (ChangeShadeObj slot + FncShadeRegSet) over the pictures
# for fades to / from white.  The real PS5 does not alpha-blend 8bpp sprites (the stock game only blends 4bpp ones; on
# the board the plate stayed solid through its fade), so src/ending.c replaces a partly transparent plate by tinting
# the ending's palette banks toward white by the same amount.
WHITE_PLATE = 0x8C38A3D8
_bdmap = []


def backdrop_map():
    """the DC backdrop map as ARGB1555 pixels (0 = no cell), from ENDBG.CHR / ENDBG.PAL"""
    if not _bdmap:
        _, _, W, H = struct.unpack('<4H', D.raw(BACKDROP_MAP, 8))
        ent = struct.unpack(f'<{W * H}I', D.raw(BACKDROP_MAP + 8, 4 * W * H))
        fs = ROOT + '/assets/dc/US/fs/'
        chr_ = np.fromfile(fs + 'ENDBG.CHR', np.uint8); pal = np.fromfile(fs + 'ENDBG.PAL', '<u2').astype(int)
        m = np.zeros((H * 16, W * 16), int)
        for i, e in enumerate(ent):
            if e >> 16 == 0: continue
            c = np.asarray(untwiddle(chr_[(e >> 16) * 256:((e >> 16) + 1) * 256], 16, 16)).reshape(16, 16)
            y, x = divmod(i, W)
            m[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = np.where(c != 0, pal[np.minimum(c, len(pal) - 1)] | 0x8000, 0)
        _bdmap.append(m)
    return _bdmap[0]


def part_cells(v, p, cs):
    """the cells of part p of composite v; a synthetic backdrop composite (BD_OBJ) is the DC backdrop under its
    close-up's window"""
    cells = [cs[p['idx'] + j] for j in range(p['W'] * p['H'])]
    if v not in BD_OBJ: return cells
    W, H = p['W'], p['H']
    K = np.zeros((H * 16, W * 16), int)
    ox, oy = BACKDROP[BD_OBJ[v]]
    kr = np.rot90(K, ROT); h, w = kr.shape
    bd = np.rot90(backdrop_map(), MROT)[-oy:h - oy, -ox:w - ox]
    assert bd.shape == kr.shape and (bd & 0x8000).all(), hex(v)
    kr = np.where(kr & 0x8000, kr, bd)
    K = np.rot90(kr, -ROT)
    shape = np.asarray(cells[0]).shape
    return [K[y * 16:y * 16 + 16, x * 16:x * 16 + 16].reshape(shape).astype(np.asarray(cells[0]).dtype)
            for y in range(H) for x in range(W)]


def build(only=None, tnum_base=None, out=ROOT + '/out/end'):
    """only: iterable of ending slots to include (others keep their arcade scripts) - used while the gfx space for
    all six endings is not available.  tnum_base: first gfx tile (256-byte units)."""
    os.makedirs(out, exist_ok=True)
    only = set(only or ENDINGS)
    insns, refs = crawl(sorted(only))
    own = owners(refs)
    use = {v: e for v, e in own.items() if e is None or e in only}
    use.update({b: use[c] for b, c in BD_OBJ.items() if c in use})
    # ---- tiles + palettes ------------------------------------------------------------------------------------
    groups = collections.defaultdict(list)                   # (ending|None, bank) -> [composite]
    for e in sorted({e for e in use.values()}, key=lambda x: (x is None, x)):
        comps = sorted([v for v, o in use.items() if o == e and v not in BD_OBJ],
                       key=lambda v: -sum(p['W'] * p['H'] for p in all_parts(v)))
        if e is None:
            groups[(None, COMMON_BANK)] = comps; continue
        big = comps[:MAX_OWN_BANKS]; small = comps[MAX_OWN_BANKS:]
        for i, v in enumerate(big): groups[(e, 0x10 + 0x10 * i)].append(v)
        if small: groups[(e, 0x10 + 0x10 * len(big))] += small
    for b, c in BD_OBJ.items():                              # the backdrop shares its close-up's bank
        if b in use: [g.append(b) for g in groups.values() if c in g]
    tiles, tile_of_part, pal_of_group, comp_bank = bytearray(), {}, {}, {}
    part_tiles = {}                                          # content hash -> tnum offset
    for (e, bank), comps in groups.items():
        cfile = {v: FILES[e] if e is not None else common_file(v) for v in comps}
        counts = {}
        for v in comps:
            comp_bank[v] = bank; cs = dcend.cells('US', cfile[v])
            for p in all_parts(v):
                for c in part_cells(v, p, cs):
                    vv = c[(c & 0x8000) != 0] & 0x7FFF
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
                cells = part_cells(v, p, cs)
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
    txt = json.load(open(ROOT + '/out/stagedemo/ending_text.json'))
    pairs = json.load(open(ROOT + '/re/end_text_pairs.json'))
    owner_f = json.load(open(ROOT + '/re/end_text_owner.json'))
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
    # ---- synthetic backdrop tasks (see BACKDROP) -----------------------------------------------------------------
    bd_task = {}
    B.align(); closeup_sub = B.here()                        # 0x8C3E623C with the close-up's priority
    B.u16(OP_DEATHSYNC); B.u16(OP_HARDPRIO); B.u16(0); B.u16(OP_PRIO); B.u16(CLOSEUP_PRIO); B.u16(OP_RET)
    for t, c in BD_TASKS.items():
        b = {c: b for b, c in BD_OBJ.items()}[c]
        if b not in addr: continue
        B.align(); bd_task[t] = B.here()
        B.u16(OP_DEATHSYNC); B.u16(OP_MOVEPOS); B.u16(0); B.u32(0); B.u32(0x70)   # MovePosition 0, 0x70 (as the close-ups)
        B.u16(OP_PUTOBJ); B.u32(addr[b])
        B.u16(OP_HARDPRIO); B.u16(0); B.u16(OP_PRIO); B.u16(BD_PRIO); B.u16(OP_SLEEP)
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
        if any(0 < x - t < BD_SETUP for t in BD_TASKS): continue              # rest of the replaced BG setup
        assert B.here() == newa[x]
        if x in CLOSEUP_CALLS:
            assert DI.l(x + 2) == 0x8C3E623C and ln == 6; B.u16(DI.w(x)); B.u32(closeup_sub); continue
        if x in BD_TASKS:                                    # BG setup -> backdrop object (see BACKDROP)
            assert sum(keep[y][0] for y in keep if x <= y < x + BD_SETUP) == BD_SETUP and DI.w(x + BD_SETUP - 2) == 0x80
            B.u16(OP_SETNEWACT); B.u16(0x0200); B.u32(bd_task[x])
            for _ in range((BD_SETUP - 8) // 2): B.u16(0)
            assert B.here() == newa[x] + BD_SETUP
            continue
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
            'palettes': {str(s): [(b, c) for b, c in v] for s, v in pal_sets.items()}, 'errors': errors,
            'objects': {f'{v:08x}': a for v, a in sorted(addr.items())}}
    json.dump(meta, open(out + '/meta.json', 'w'))
    print(f'blob {len(B.data):#x} bytes, tiles {len(tiles) // 256}, errors {len(errors)}')
    for e in errors[:20]: print('  ', e)
    return meta


def line_positions(img, addr, nlines, reg='US', fn=None):
    """text line origins (hardware = text printer coordinates, relative to the composite origin) in reading order.
    Text runs along hardware x; lines stack along y with the screen's top at the highest y.  A part of W columns
    holds W lines: column W-1 is the first; row r is the 16-pixel cell at x + 16 r.  Blank lines (columns without
    pixels) are skipped, and a line starts at its first non-blank cell (the DC bakes indents into the bitmap, e.g. the
    solo ending's choice 0x8C38C7A8: the two options start 2 cells in, right of the cursor)."""
    cs = dcend.cells(reg, fn) if fn else None
    ls = []
    for p in dcend.parts(img, addr):
        for c in range(p['W']):
            ink = [r for r in range(p['H']) if p['idx'] + r * p['W'] + c < len(cs)
                   and (cs[p['idx'] + r * p['W'] + c] & 0x8000).any()] if cs is not None else [0]
            if not ink: continue
            ls.append((-(p['y'] + 16 * c), p['x'] + 16 * ink[0]))
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
    place = {o: f for o, f in json.load(open(ROOT + '/out/gfx/place.json')).items()
             if f not in ('ending.tiles', 'ending.data')}           # a re-run replaces its own previous placement
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
         f'#define END_WHITE_PLATE 0x{meta["objects"].get(f"{WHITE_PLATE:08x}", 0):08X}   /* src/ending.c palette fade */',
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
