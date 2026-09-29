#!/usr/bin/env python3
"""Check that Morrigan's sprite colours stay intact through whole games on the patched set (gunbird2m).

Her in-game colours are two sets, pal_game0 / pal_game1 on colr MORRIGAN_COLR0 / 1 at the pens pal_game<k>_pens
(lines 0x20-0x23 and free text-line entries; see tools/make_gfx.py and src/palette.c): the real PS5 does not reach
the entries 0x1000+ MAME emulates.  Each run plays
the whole game with her (Stage Select Full Play: both loops from stage 1, stage demos, endings, the all-clear tally),
invincible, enemy HP capped, and every 60 frames reads palette lines 0x00-0x3F and the game state.  Pass = whenever
she is in play (GameLoop in game / stage demo / 2P join) both sets are exactly as gb2_morrigan_pal_init writes them
(src/gen_gfx.c), and the rest of lines 0x10-0x3F (the original's flash / shadow banks, which the original game never
changes during play) is the same in every in-play sample - her select art and endings cover them only in between.
cases: m (1P) and m-<c> / <c>-m (2P with character c = 1..6 as partner, she on P1 / P2)
usage: check_palette.py [--cases m,m-1,...] [--frames 76000] [--jobs N]"""
import os, sys, re, json, struct, subprocess, tempfile, argparse, shutil
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
PLAY = {'8', '9', '10'}                   # stage demo, 2P join, in game


def expected():
    """{palette entry: RGBx} of her in-game colour sets"""
    src, h = open(ROOT + '/src/gen_gfx.c').read(), open(ROOT + '/src/gen_gfx.h').read()
    exp = {}
    for k, colr in re.findall(r'MORRIGAN_COLR(\d) (0x[0-9A-F]+)', h):
        vals = [int(x, 16) for x in re.search(rf'pal_game{k}\[\d+\] = \{{([^}}]*)\}}', src).group(1).split(',')]
        pens = [int(x) for x in re.search(rf'pal_game{k}_pens\[\d+\] = \{{([^}}]*)\}}', src).group(1).split(',')]
        exp.update({int(colr, 16) * 16 + p: v for p, v in zip(pens, vals)})
    return exp


def timeline(case, a, out):
    # Stage Select 'stage 7, round 2, Full Play' plays both loops from stage 1 (endings at ~65000 frames)
    if case == 'm': args = ['7', '6', '2']
    elif case.startswith('m-'): args = ['7', '6', '2', '--p2', str(int(case[2:]) - 1)]
    else: args = ['7', str(int(case.split('-')[0]) - 1), '2', '--p2', '6']
    lines = subprocess.run([sys.executable, ROOT + '/tools/mame/mkstage.py'] + args + ['--mode', '1'],
                           capture_output=True, text=True).stdout.splitlines()
    st = int(next(l.split()[-1] for l in lines if 'START' in l)); end = st + a.frames
    L = [l for l in lines if not l.startswith('#')]
    L += [f'{st} phash 4 {out}.hash', f'{st} weaken 0604c8cc 0605cd6a 0605cd68 10000']
    L += [f'{f} poke8 06040016 01' for f in range(st, end, 60)] + [f'{f} poke8 06040018 01' for f in range(st, end, 60)]
    for who, ph in (('P1', 0), ('P2', 4)):
        L += [f'{f} tap 3 {who} Button 1' for f in range(st + 60 + ph, end, 8)]
        L += [f'{f} tap 30 {who} {d}' for f, d in zip(range(st + 60 + ph, end, 120), ['Left', 'Up', 'Right', 'Down'] * 9999)]
        L += [f'{f} tap 4 {who} Button 2' for f in range(st + 600 + ph, end, 1080)]
    L += [f'{f} dumpmem 04040000 1000 {out}_pal/{f}.bin' for f in range(st + 60, end, 60)] + [f'{end} exit']
    return '\n'.join(L) + '\n', st


def run(case, a, work, exp):
    out = f'{work}/{case}'; os.makedirs(out + '_pal', exist_ok=True)
    tl, st = timeline(case, a, out)
    open(out + '.tl', 'w').write(tl)
    nv = f'{work}/nv_{case}/gunbird2m'; os.makedirs(nv, exist_ok=True)
    shutil.copy(ROOT + '/out/tmp/eeprom_morrigan.bin', nv + '/eeprom')
    subprocess.run([ROOT + '/tools/mame/run.sh', ROOT + '/out/roms', out + '.tl'], capture_output=True,
                   env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2m'))
    states = {int(l.split()[0]): (l.split()[5], l.split()[2]) for l in open(out + '.hash')}
    checked = bad = 0; first_bad = None; stage = 0; ref = None
    others = [e for e in range(0x100, 0x400) if e not in exp]
    for f in sorted(int(x[:-4]) for x in os.listdir(out + '_pal')):
        s = states.get(f - f % 4)                      # phash logs on multiples of 4
        if not s: continue
        stage = max(stage, int(s[1], 16))
        if s[0] not in PLAY: continue
        d = open(f'{out}_pal/{f}.bin', 'rb').read()
        nbad = sum(struct.unpack_from('>I', d, 4 * e)[0] != v for e, v in exp.items())
        rest = [struct.unpack_from('>I', d, 4 * e)[0] for e in others]
        if ref is None: ref = rest
        nbad += sum(x != y for x, y in zip(rest, ref))
        checked += 1
        if nbad:
            bad += 1
            if first_bad is None: first_bad = (f, s[0], s[1], nbad)
    return case, checked, bad, first_bad, stage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases'); ap.add_argument('--frames', type=int, default=76000)
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    cases = a.cases.split(',') if a.cases else ['m'] + [f'm-{c}' for c in range(1, 7)] + [f'{c}-m' for c in range(1, 7)]
    exp = expected()
    work = tempfile.mkdtemp(prefix='checkpal_')
    print(f'{len(cases)} runs, {len(exp)} palette entries, work dir {work}', flush=True)
    fails = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for case, checked, bad, first_bad, stage in ex.map(lambda c: run(c, a, work, exp), cases):
            ok = checked > 0 and bad == 0 and stage >= 0xE
            fails += not ok
            print(f'{case:5s} {"OK " if ok else "BAD"} {checked} in-play samples, {bad} with wrong colours, '
                  f'stage counter up to {stage:#x}' + (f'; first bad at frame {first_bad[0]} (state {first_bad[1]}, '
                  f'stage {first_bad[2]}, {first_bad[3]} entries differ)' if first_bad else ''), flush=True)
    print('PASS' if not fails else f'FAIL ({fails})')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
