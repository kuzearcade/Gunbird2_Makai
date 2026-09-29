#!/usr/bin/env python3
"""Whole-game regression: the same whole game (coin, character select, both loops with the story scenes, ending,
all-clear tally, name entry, ranking, back to attract) on the original set (gunbird2) and on the patched set
(gunbird2m) from the same EEPROM, compared by a hash of the screen every few frames (timeline 'phash').
Pass = every hash identical up to the end of the run.  EEPROM: Aine unlocked (secret flag 2), Morrigan locked
(out/tmp/eeprom_regress.bin) - with Morrigan unlocked the '?' slot draws Random(0x12) instead of Random(0xF), so the
patched game legitimately differs.  Select-screen inputs: out/tmp/select_paths.json (tools/mame/select_paths.py).
Both runs: Random()'s idle-time entropy neutralised (as regress_select.py), players invincible (debug flag
0x06040016), infinite bombs (0x06040018), enemy HP capped ('weaken') so a run clears the game in ~70000 frames;
per active player: moves, fire held (charge attacks on release) and bombs, so the patched bomb / charged-shot
start (src/playerstate.c) and every original character's ending run.
cases: 1Pc (c = charNo 1..6: Marion, Valnus, Tavia, Hei-Cob, Alucard, Aine) and 2Pa-b (all ordered pairs, a != b).
usage: regress_game.py <eeprom> [--one] [--two] [--cases 1P1,2P1-3] [--frames 100000] [--every 4] [--jobs N]"""
import os, sys, subprocess, argparse, tempfile, shutil, itertools, json
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
ORIG, PATCHED = ROOT + '/mame_roms', ROOT + '/out/roms'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from select_paths import select_lines
if not os.path.exists(ROOT + '/out/tmp/select_paths.json'):
    sys.exit('out/tmp/select_paths.json missing: run tools/mame/regress_setup.py')
PATHS = json.load(open(ROOT + '/out/tmp/select_paths.json'))


def inputs(who, t0, frames, phase):
    ev, t = [f'{t0} press {who} Button 1'], t0 + phase
    moves = [f'{who} Left', f'{who} Up', f'{who} Right', f'{who} Down']
    k = 0
    while t < t0 + frames:
        ev.append(f'{t} tap 30 {moves[k % 4]}')
        if k % 5 == 2: ev += [f'{t + 40} release {who} Button 1', f'{t + 90} press {who} Button 1']   # charge
        if k % 9 == 4: ev.append(f'{t + 60} tap 4 {who} Button 2')                                     # bomb
        t += 120; k += 1
    return ev


def timeline(case, a, out):
    p = PATHS[case]
    L, st = select_lines(p['p1'], p['p2'], p.get('pre', ()))
    two = p['p2'] is not None
    end = st + a.frames
    L += [f'{st} phash {a.every} {out}.hash', f'{st} weaken 0604c8cc 0605cd6a 0605cd68 10000']
    L += [f'{f} poke8 06040016 01' for f in range(st, end, 60)] + [f'{f} poke8 06040018 01' for f in range(st, end, 60)]
    L += inputs('P1', st + 60, a.frames - 60, 0)
    if two: L += inputs('P2', st + 60, a.frames - 60, 60)
    L += [f'{f} snap {out}_snap/s{f}.png' for f in range(st, end, 3000)] + [f'{end} exit']
    return '\n'.join(L) + '\n'


def run(romdir, eep, case, a, work):
    setname = 'gunbird2' if romdir == ORIG else 'gunbird2m'
    out = f'{work}/{setname}_{case}'
    os.makedirs(out + '_snap', exist_ok=True)
    nvroot = f'{work}/nv_{setname}_{case}'
    shutil.rmtree(nvroot, ignore_errors=True); os.makedirs(f'{nvroot}/{setname}')
    shutil.copy(eep, f'{nvroot}/{setname}/eeprom')
    open(out + '.tl', 'w').write(timeline(case, a, out))
    subprocess.run([ROOT + '/tools/mame/run.sh', romdir, out + '.tl'], capture_output=True, text=True,
                   env=dict(os.environ, GB2_NVRAM=nvroot, GB2_SET=setname))
    return [l.split() for l in open(out + '.hash')] if os.path.exists(out + '.hash') else []


def compare(case, x, y):
    n = min(len(x), len(y))
    for i in range(n):
        if x[i][1] != y[i][1]:
            return False, (f'{case:7s} DIFF at frame {x[i][0]} (stage counter {x[i][2]}, GameLoop {x[i][5]}, scores orig '
                           f'{x[i][3]}/{x[i][4]} patched {y[i][3]}/{y[i][4]}); {i} of {n} hashes equal')
    if not n: return False, f'{case:7s} no hashes'
    states = []
    for r in x:
        if not states or states[-1] != r[5]: states.append(r[5])
    stage = max(int(r[2], 16) for r in x)
    top = max(max(int(r[3]), int(r[4])) for r in x)
    ok = len(x) == len(y) and stage >= 0xE and '4' in states      # ending reached, name entry ran
    return ok, (f'{case:7s} {"identical" if len(x) == len(y) else "LENGTH"}: {n} hashes up to frame {x[-1][0]}, '
                f'stage counter up to {stage:#x}, best score {top}, GameLoop states {"-".join(states[:12])}'
                + ('' if ok else '  (INCOMPLETE: ending / name entry not reached)'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('eeprom'); ap.add_argument('--one', action='store_true'); ap.add_argument('--two', action='store_true')
    ap.add_argument('--cases'); ap.add_argument('--frames', type=int, default=100000); ap.add_argument('--every', type=int, default=4)
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    cases = a.cases.split(',') if a.cases else []
    if a.one or not (a.one or a.two or cases): cases += [f'1P{c}' for c in range(1, 7)]
    if a.two: cases += [f'2P{p}-{q}' for p, q in itertools.permutations(range(1, 7), 2)]
    eep = os.path.abspath(a.eeprom)
    work = tempfile.mkdtemp(prefix='reggame_', dir=os.environ.get('TMPDIR'))
    print(f'{len(cases)} cases, work dir {work}', flush=True)
    bad = 0
    def one(case):
        return case, run(ORIG, eep, case, a, work), run(PATCHED, eep, case, a, work)
    with ThreadPoolExecutor(a.jobs) as ex:
        for case, x, y in ex.map(one, cases):
            ok, msg = compare(case, x, y); bad += not ok
            print(msg, flush=True)
    print('PASS' if not bad else f'FAIL ({bad} of {len(cases)})')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
