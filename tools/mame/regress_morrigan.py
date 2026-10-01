#!/usr/bin/env python3
"""Whole-game runs with Morrigan (patched set only - the original has no Morrigan to compare with): coin, character
select with her ('?' + Up, Morrigan flag 2), both loops with the story scenes, her ending, all-clear tally, name entry,
ranking, back to attract; the same scripted play as tools/mame/regress_game.py (invincible, infinite bombs, enemy HP
capped, moves / fire / charge / bombs per player).  Pass = the run reaches the last stage (stage counter 0xE) and name
entry (GameLoop state 4), i.e. her ending and the tally ran, and the screen keeps changing to the end of the run.
cases: m (1P) and m-<c> / <c>-m (2P with character c = 1..6 as partner, she on P1 / P2)
EEPROM: out/tmp/eeprom_regress.bin with the Morrigan flag set to 2 ('Mo' at 0x20; Aine flag 2 already, so every partner
is selectable) -> out/tmp/eeprom_morrigan_regress.bin.
--find: search the select-screen input sequences (verified by reading the players' charNo, 0x06055058 / 0x06055108)
and store them in out/tmp/morrigan_paths.json.
usage: regress_morrigan.py [--find] [--cases m,m-1,...] [--frames 100000] [--jobs N]"""
import os, sys, json, shutil, tempfile, argparse, subprocess
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from select_paths import select_lines, probe
import regress_game as RG
ROOT = RG.ROOT
EEP = ROOT + '/out/tmp/eeprom_morrigan_regress.bin'
PATHS = ROOT + '/out/tmp/morrigan_paths.json'
M = 7
CASES = ['m'] + [f'm-{c}' for c in range(1, 7)] + [f'{c}-m' for c in range(1, 7)]
P1MAP = {1: ['Left'], 2: [], 3: ['Right'], 4: ['Right'] * 2, 5: ['Right'] * 3, 6: ['Right'] * 4 + ['Down'],
         M: ['Right'] * 4 + ['Up']}


def eeprom():
    e = bytearray(open(ROOT + '/out/tmp/eeprom_regress.bin', 'rb').read())
    e[0x20:0x22] = b'Mo'                      # not part of the secret-block checksum (0x2E)
    open(EEP, 'wb').write(e)


def want(case):
    if case == 'm': return M, None
    a, b = case.split('-')
    return (M, int(b)) if a == 'm' else (int(a), M)


def find():
    work = tempfile.mkdtemp(prefix='mpath_')
    seqs = [['Right'] * n + d for n in range(7) for d in ([], ['Down'], ['Up'])] + \
           [['Left'] * n + d for n in (1, 2) for d in ([], ['Down'], ['Up'])]
    tag = lambda s: ''.join(x[0] for x in s) or '0'
    res = {}
    with ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        got = probe(EEP, P1MAP[M], None, work, 'm')
        assert got and got[0] == M, f'1P Morrigan path gave {got}'
        res['m'] = {'p1': P1MAP[M], 'p2': None}
        for case in CASES[1:]:
            a, b = want(case)
            pres = [[]] + [['Right'] * n for n in range(1, 6)]
            trials = [(pre, s) for pre in pres for s in seqs]
            found = None
            for (pre, s), g in zip(trials, ex.map(lambda t: probe(EEP, P1MAP[a], t[1], work, f'{case}_{tag(t[0])}_{tag(t[1])}', t[0]), trials)):
                if g == (a, b): found = {'pre': pre, 'p1': P1MAP[a], 'p2': s}; break
            if found: res[case] = found
            else: print(f'{case}: no select path found')
    json.dump(res, open(PATHS, 'w'), indent=1)
    print(f'{len(res)} of {len(CASES)} paths -> {PATHS}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--find', action='store_true'); ap.add_argument('--cases')
    ap.add_argument('--frames', type=int, default=100000); ap.add_argument('--every', type=int, default=4)
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    eeprom()
    if a.find or not os.path.exists(PATHS): find()
    RG.PATHS.clear(); RG.PATHS.update(json.load(open(PATHS)))
    cases = [c for c in (a.cases.split(',') if a.cases else CASES) if c in RG.PATHS]
    work = tempfile.mkdtemp(prefix='regmorr_', dir=os.environ.get('TMPDIR'))
    print(f'{len(cases)} cases, work dir {work}', flush=True)
    bad = 0
    def one(case):
        return case, RG.run(RG.PATCHED, EEP, case, a, work)
    with ThreadPoolExecutor(a.jobs) as ex:
        for case, x in ex.map(one, cases):
            if not x: bad += 1; print(f'{case:5s} no hashes'); continue
            states = []
            for r in x:
                if not states or states[-1] != r[5]: states.append(r[5])
            stage = max(int(r[2], 16) for r in x)
            top = max(max(int(r[3]), int(r[4])) for r in x)
            tail = {r[1] for r in x[-500:]}                  # last ~2000 frames: still animating (no hang)
            ok = stage >= 0xE and '4' in states and len(tail) > 1 and int(x[-1][0]) >= int(x[0][0]) + a.frames - 2 * a.every
            bad += not ok
            print(f'{case:5s} {"OK  " if ok else "FAIL"} {len(x)} hashes up to frame {x[-1][0]}, stage counter up to '
                  f'{stage:#x}, best score {top}, GameLoop states {"-".join(states[:14])}', flush=True)
    print('PASS' if not bad else f'FAIL ({bad} of {len(cases)})')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
