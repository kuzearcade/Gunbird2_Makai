#!/usr/bin/env python3
"""Palette-line census of the ORIGINAL game (stock gunbird2): which palette lines (16 entries each, palette RAM
0x04040000-0x04044FFF = lines 0x00-0x13F) are written in which game states, over whole games.  Finds lines that are
free for Morrigan's colours on real hardware (sprite colours must stay on lines <= 0xFF: the PS5 does not reach
the 0x1000+ entries MAME emulates).
Runs (all from boot, with the Random() entropy patch like the regressions):
  1P1..1P6, 2Pa-b   whole games as tools/mame/regress_game.py (select, both loops, endings, name entry, ranking,
                    attract), invincible, enemy HP capped
  d1..d6, d2p       1P (and one 2P) play without invincibility: deaths, continue screens, game over
A line counts as used in a state if the game wrote a non-zero value to it (clearing to black is ignored) while GameLoop (0x0604C744) was in that state; the select
screen is reported as its own state 'select' (frames before the first in-game frame of the run).
Writes out/tmp/palcensus.json {'c'|'w': {line: {state: [runs]}}} (c = given a colour, w = any write, black
included) and prints the lines per state and the lines never written.
usage: palcensus.py [--cases 1P1,d1,...] [--jobs N] [--analyze-only]"""
import os, sys, json, subprocess, tempfile, argparse, itertools, shutil, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regress_game as RG
from select_paths import select_lines
ROOT = RG.ROOT
OUT = ROOT + '/out/tmp/palcensus.json'


def timeline(case, work, frames):
    out = f'{work}/{case}'
    if case.startswith('d'):                        # deaths and continues, no invincibility
        key = '2P1-6' if case == 'd2p' else f'1P{case[1:]}'
        p = RG.PATHS[key]
        L, st = select_lines(p['p1'], p['p2'], p.get('pre', ()))
        L += RG.inputs('P1', st + 60, 12000, 0)
        if p['p2'] is not None: L += RG.inputs('P2', st + 60, 12000, 60)
        for f in range(st + 400, st + 12000, 400):   # continue whenever offered
            L += [f'{f} tap 4 Coin 1', f'{f + 20} tap 4 1 Player Start']
            if p['p2'] is not None: L += [f'{f + 40} tap 4 Coin 1', f'{f + 60} tap 4 2 Players Start']
        L.append(f'{st + 12000} exit')
    else:
        a = argparse.Namespace(frames=frames, every=4)
        L = [l for l in RG.timeline(case, a, out).splitlines() if ' phash ' not in l and ' snap ' not in l]
    L += [f'2 phash 4 {out}.hash', f'2 palcensus {out}.pal']
    return '\n'.join(L) + '\n'


def run(case, work, frames):
    nv = f'{work}/nv_{case}/gunbird2'; os.makedirs(nv, exist_ok=True)
    shutil.copy(ROOT + '/out/tmp/eeprom_regress.bin', nv + '/eeprom')
    open(f'{work}/{case}.tl', 'w').write(timeline(case, work, frames))
    subprocess.run([ROOT + '/tools/mame/run.sh', RG.ORIG, f'{work}/{case}.tl'], capture_output=True,
                   env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2'))
    states = {}
    for l in open(f'{work}/{case}.hash'):
        f, _, _, _, _, s = l.split(); states[int(f)] = s
    first_game = min((f for f, s in states.items() if s in ('8', '9', '10')), default=None)
    res = {'c': collections.defaultdict(set), 'w': collections.defaultdict(set)}
    for l in open(f'{work}/{case}.pal'):
        kind, line, ranges = l.split()
        for r in ranges.split(','):
            a, b = map(int, r.split('-'))
            for f in range(a, b + 1):
                st = 'select' if first_game is not None and f < first_game and f > 1000 else \
                    states.get(f - f % 4, states.get(f - f % 4 - 4, '?'))
                res[kind][int(line)].add(st)
    return case, {k: {l: sorted(s) for l, s in v.items()} for k, v in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases'); ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--frames', type=int, default=100000); ap.add_argument('--analyze-only', action='store_true')
    a = ap.parse_args()
    if not a.analyze_only:
        cases = a.cases.split(',') if a.cases else \
            [f'1P{c}' for c in range(1, 7)] + [f'2P{p}-{q}' for p, q in itertools.permutations(range(1, 7), 2)] + \
            [f'd{c}' for c in range(1, 7)] + ['d2p']
        work = tempfile.mkdtemp(prefix='palcensus_')
        print(f'{len(cases)} runs, work dir {work}', flush=True)
        total = {k: collections.defaultdict(lambda: collections.defaultdict(list)) for k in ('c', 'w')}
        with ThreadPoolExecutor(a.jobs) as ex:
            for case, res in ex.map(lambda c: run(c, work, a.frames), cases):
                for k in ('c', 'w'):
                    for l, sts in res[k].items():
                        for st in sts: total[k][l][st].append(case)
                print(f'  {case}: {len(res["w"])} lines written, {len(res["c"])} given a colour', flush=True)
        json.dump({k: {l: dict(v) for l, v in sorted(t.items())} for k, t in total.items()}, open(OUT, 'w'), indent=0)
    total = {k: {int(l): v for l, v in t.items()} for k, t in json.load(open(OUT)).items()}
    names = {'0': 'boot (RAM test)', '2': 'attract/title', '3': 'ending', '4': 'name entry/ranking', '8': 'stage demo',
             '9': '2P join', '10': 'in game', 'select': 'select screen'}
    def ranges(ls):
        rs, cur = [], None
        for l in sorted(ls):
            if cur and l == cur[1] + 1: cur[1] = l
            else: cur = [l, l]; rs.append(cur)
        return ' '.join(f'{x:02x}' if x == y else f'{x:02x}-{y:02x}' for x, y in rs) or '-'
    for k, title in (('c', 'given a colour'), ('w', 'written at all (black included)')):
        print(f'lines {title}, per state:')
        for st in sorted({s for v in total[k].values() for s in v}):
            print(f'  {st:7s} {names.get(st, ""):20s} ' + ranges(l for l, v in total[k].items() if st in v))
    for k, title in (('c', 'never given a colour'), ('w', 'never written at all')):
        free = [l for l in range(0x100) if not (set(total[k].get(l, {})) - {'0'})]   # state 0 = boot RAM test
        print(f'lines 0x00-0xFF {title} in any run (boot RAM test excluded): {ranges(free)}')


if __name__ == '__main__':
    main()
