#!/usr/bin/env python3
"""Sound ROM audit (arcade gunbird2): which sound-effect IDs can the game play, which YMF278B waves do they and the
music use, and which waves are left over (candidates to reclaim for Morrigan's samples).

Sources of effect IDs (player dc_8c01bce0 @ 0x0602B39A, table ROM 0x40300 + 6*id {u16 wave, vol, ?, group, ?}):
  - seq op 0x34 Effect <id> over every script reachable from any pointer into the SEQ section
  - C code: constant arguments + the ID tables in initialised RAM (listed in C_TABLES) - from re/export/arcade.c
  - --trace <ids.txt>: IDs logged at run time (tools/mame sound trace), merged in
Music waves: see music_waves().
A wave is reclaimable when none of its IDs is referenced (static or traced), none of its IDs below 0x150 exists on the
Dreamcast (the DC port dropped every sound it never plays; DC IDs 0x150+ are Morrigan's and say nothing about the
arcade), it is not a music instrument/drum wave (tables at ROM 0x40000 / 0x40100) and not wave 0x3D (ID 0 is played
by dc_8c01bce0(0)).  --write stores the verdict in re/sound_audit.json for tools/port_sound.py.
usage: sound_audit.py [--trace file ...] [--write]"""
import sys, re, struct, collections, zipfile
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from gbres import Space, ROOT
import seqdis

A = Space('arcade'); AI = seqdis.Image('arcade')
SND = zipfile.ZipFile(ROOT + '/mame_roms/gunbird2.zip').read('sound.u9')        # the original sound ROM
SE_TBL, N_SE = 0x40300, 0x200
BITS = {0: 8, 1: 12, 2: 16}


def ram16(a):
    o = a - 0x0602DCDC + 0x2E47C
    return (A.prog[o] << 8) | A.prog[o + 1]


# (RAM address, entries) of u16 sound-ID tables read by the C code (see arcade.c callers of dc_8c01bce0)
C_TABLES = [(0x06031FA0, 7), (0x06031FAE, 7), (0x06031FBC, 7), (0x06032008, 4), (0x06032058, 7), (0x0603210A, 7)]


def se(i):
    b = A.raw(SE_TBL + 6 * i, 6)
    return {'wave': (b[0] << 8) | b[1], 'vol': b[2], 'b3': b[3], 'grp': b[4] & 7, 'b5': b[5]}


def wave(i):
    h = SND[12 * i:12 * i + 12]
    f = h[0] >> 6; start = ((h[0] & 0x3F) << 16) | (h[1] << 8) | h[2]
    n = (((h[5] << 8) | h[6]) ^ 0xFFFF) + 1
    return {'fmt': f, 'start': start, 'n': n, 'bytes': n * BITS[f] // 8, 'loop': (h[3] << 8) | h[4]}


def n_waves():
    n = 0
    while n < 384 and not (wave(n)['start'] == 0 and wave(n)['n'] == 0x10000): n += 1
    return n


def seq_ids():
    """Effect / Sound operands in all scripts reachable from pointers into SEQ"""
    roots = set()
    for buf in (A.prog,):
        for o in range(0, len(buf) - 3, 2):
            v = struct.unpack('>I', buf[o:o + 4])[0]
            if 0x60000 <= v < 0x100000 and not v & 1: roots.add(v)
    eff, snd, seen = collections.defaultdict(set), set(), set()
    for r in sorted(roots):
        if r in seen: continue
        try: out, _ = seqdis.disasm(AI, r, maxn=3000)
        except Exception: continue
        for a, (ln, txt, op) in out.items():
            seen.add(a)
            if op == 0x34: eff[AI.w(a + 2)].add(a)
            elif op == 0x33: snd.add(AI.w(a + 2))
    return eff, snd


# constants reaching dc_8c01bce0 through a variable: HitActI (0x116, 0x56), MaintenanceCode (0x38, 0x3B), name entry /
# ranking (0x5C, 0x77)
C_VAR_IDS = {0x116, 0x56, 0x38, 0x3B, 0x5C, 0x77}


def c_ids():
    src = open(ROOT + '/re/export/arcade.c').read()
    ids = {int(m, 16) for m in re.findall(r'dc_8c01bce0\((0x[0-9a-f]+)\)', src)}
    ids |= {int(m) for m in re.findall(r'dc_8c01bce0\((\d+)\)', src)}
    ids |= C_VAR_IDS
    for a, n in C_TABLES:
        ids |= {ram16(a + 2 * i) for i in range(n)}
    return {i for i in ids if 0 < i < N_SE}


DC_SE, DC_BASE = 0x8C08D57C, 0x8C010000


def dc_has(i):
    b = open(ROOT + '/re/1st_read_US.bin', 'rb').read()
    return struct.unpack('<h', b[DC_SE - DC_BASE + 6 * i:DC_SE - DC_BASE + 6 * i + 2])[0] >= 0


def music_waves():
    ins = {A.u16(0x40000 + 2 * i) for i in range(0x80)}
    drums = {A.u16(0x40100 + 4 * i) for i in range(0x80)}
    return {w for w in ins | drums if w not in (0, 0xFFFF)}


def verdict(used):
    by_wave = collections.defaultdict(set)
    for i in range(N_SE): by_wave[se(i)['wave']].add(i)
    music, rem = music_waves(), []
    for w in range(n_waves()):
        ids = by_wave.get(w, set())
        if w in music or w == 0x3D or ids & used: continue
        if any(dc_has(i) for i in ids if 0 < i < 0x150): continue
        rem.append(w)
    return rem, by_wave


def main():
    trace = set()
    args = [a for a in sys.argv[1:] if a != '--write']
    for fn in args[args.index('--trace') + 1:] if '--trace' in args else []:
        trace |= {int(x, 16) for x in open(fn).read().split()}
    eff, snd = seq_ids(); cids = c_ids()
    used = set(eff) | cids | trace
    used = {i for i in used if 0 < i < N_SE}
    nw = n_waves()
    by_wave = collections.defaultdict(set)
    for i in range(N_SE): by_wave[se(i)['wave']].add(i)
    print(f'waves {nw}, SE ids referenced: seq {len(eff)}, C {len(cids)}, trace {len(trace)}, union {len(used)}')
    print('music ids (Sound op):', sorted(hex(x) for x in snd))
    free = []
    for w in range(nw):
        ids = by_wave.get(w, set())
        if not ids & used:
            free.append(w)
    tot = 0
    for w in free:
        x = wave(w); tot += x['bytes']
        print(f"  wave {w:#04x} fmt {x['fmt']} start {x['start']:#08x} bytes {x['bytes']:6d}  ids {sorted(hex(i) for i in by_wave.get(w, []))[:8]}")
    print(f'unreferenced waves: {len(free)}, {tot} bytes ({tot / 1024:.0f} KB)')
    rem, _ = verdict(used)
    print('reclaimable (also absent on the DC):', [hex(w) for w in rem])
    if '--write' in sys.argv:
        import json
        json.dump({'remove': rem, 'used_ids': sorted(used), 'traced': sorted(trace),
                   'note': 'generated by tools/sound_audit.py'}, open(ROOT + '/re/sound_audit.json', 'w'), indent=0)


if __name__ == '__main__':
    main()
