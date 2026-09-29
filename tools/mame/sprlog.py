#!/usr/bin/env python3
"""Sprite palette census of the ORIGINAL game (stock gunbird2): which palette lines its sprites draw with, per
GameLoop state.  Exact where tools/mame/paldraw.py samples: every frame the timeline op 'sprlog' records each distinct
sprite (colr, tile number, 8bpp, cells) on the sprite list with a colr in the given range; the pixels of its tiles in
the gfx ROM then give the palette entries it can draw (colr * 16 + pen, pen 0 transparent).  Sprites only: background
tilemaps are covered by paldraw.py.
Runs whole games (tools/mame/regress_game.py cases) and the select screen (tools/mame/regress_select.py cases).
usage: sprlog.py [--colr 10-3f] [--cases 1P1,...,s:r0,...] [--frames 100000]"""
import os, sys, argparse, subprocess, tempfile, shutil
import numpy as np
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regress_game as RG, regress_select as RS
ROOT = RS.ROOT
NAMES = {0: 'boot', 2: 'attract', 3: 'ending', 4: 'name entry/ranking', 5: 'game start', 8: 'stage demo',
         9: 'select/2P join', 10: 'play'}


def run(case, a, work, eep):
    lo, hi = a.colr.split('-')
    if case.startswith('s:'):
        base = [l for l in RS.timeline(case[2:], work + '/snap').splitlines() if ' snap ' not in l]
    else:
        ga = argparse.Namespace(frames=a.frames, every=1)
        base = [l for l in RG.timeline(case, ga, f'{work}/{case}').splitlines() if ' phash ' not in l and ' snap ' not in l]
    tag = case.replace(':', '_')
    open(f'{work}/{tag}.tl', 'w').write('\n'.join([f'2 sprlog {lo} {hi} {work}/{tag}.spr'] + base) + '\n')
    nv = f'{work}/nv_{tag}/gunbird2'; os.makedirs(nv); shutil.copy(eep, nv + '/eeprom')
    subprocess.run([ROOT + '/tools/mame/run.sh', RS.ORIG, f'{work}/{tag}.tl'], capture_output=True,
                   env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2'))
    return case, [l.split() for l in open(f'{work}/{tag}.spr')] if os.path.exists(f'{work}/{tag}.spr') else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--colr', default='10-3f'); ap.add_argument('--cases'); ap.add_argument('--frames', type=int, default=100000)
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    cases = a.cases.split(',') if a.cases else \
        [f'1P{c}' for c in range(1, 7)] + ['2P1-2', '2P3-4', '2P5-6'] + [f's:{c}' for c in ('r0', 'r3', 'q', 'p2')]
    g = np.fromfile(ROOT + '/assets/arcade/gfx.bin', dtype=np.uint8)
    eep = ROOT + '/out/tmp/eeprom_regress.bin'
    work = tempfile.mkdtemp(prefix='sprlog_')
    lines = {}                                    # GameLoop state -> {palette line: [(case, colr, tnum)]}
    with ThreadPoolExecutor(a.jobs) as ex:
        for case, recs in ex.map(lambda c: run(c, a, work, eep), cases):
            if recs is None: print(f'{case}: no log'); continue
            print(f'{case}: {len(recs)} distinct sprites', flush=True)
            for colr, tnum, d8, cells, first, n, states in recs:
                colr, tnum, d8, cells = int(colr, 16), int(tnum, 16), int(d8), int(cells)
                pens = set()
                for j in range(cells):
                    if d8: px = g[(tnum + j) * 256:(tnum + j + 1) * 256]
                    else:
                        b = g[(tnum + j) * 128:(tnum + j + 1) * 128]; px = np.concatenate([b >> 4, b & 15])
                    pens |= set(np.unique(px[px != 0]).tolist())
                for st in states.split(','):
                    for p in pens:
                        lines.setdefault(int(st), {}).setdefault((colr * 16 + p) >> 4, []).append((case, colr, tnum))
    for st in sorted(lines):
        ls = sorted(lines[st])
        print(f'{st:2d} {NAMES.get(st, ""):20s} lines drawn by sprites: ' + ' '.join(f'{l:02x}' for l in ls))
        for l in ls:
            src = sorted({(c, f'colr {co:02x} tile {t:05x}') for c, co, t in lines[st][l]})
            print(f'     {l:02x}: ' + ', '.join(f'{c} {s}' for c, s in src[:4]) + (f' (+{len(src) - 4})' if len(src) > 4 else ''))
    print(f'work dir {work}')


if __name__ == '__main__':
    main()
