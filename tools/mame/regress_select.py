#!/usr/bin/env python3
"""Select-screen regression: run identical input timelines on the original and the patched ROM set from the
same EEPROM image and compare screenshots pixel by pixel (select screen, decision, first seconds of play).
With an EEPROM whose Morrigan flag is clear the patched game must be indistinguishable from the original.
Random() (0x06029200) mixes in 0x0604000C, a count of idle-loop spins in the last frame, i.e. spare CPU time: any
cycle difference anywhere (even on the select screen) changes it by +-1 and, hundreds of frames later, the game's
course.  Both runs therefore get the same test-only RAM patch that replaces that load with a constant
(0x06029226 'mov.l @r3,r2' -> 'mov #1,r2'), so what is compared is behaviour, not CPU load.
usage: regress_select.py <eeprom image> [case ...]      cases: r0..r5 (1P, n x Right), l1, p2 (2 players), q (on '?'), a / m ('?' + Down / Up)"""
import os, sys, subprocess, shutil, tempfile
import numpy as np
from PIL import Image
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
ORIG, PATCHED = ROOT + '/mame_roms', ROOT + '/out/roms'
GATE = '1000 until 0605ccde ffff 0134 30 1 Player Start'   # coin inserted at 600; start until select is up


def timeline(case, snapdir):
    L = ['60 poke16 06029226 e201', '600 poke16 06029226 e201', '600 tap 5 Coin 1']
    if case.startswith('p2'): L.append('610 tap 5 Coin 1')
    L.append(GATE)
    t = 1080
    def tap(n, who='P1'):
        nonlocal t
        L.append(f'{t} tap 3 {who} {n}'); t += 10
    if case.startswith('r'):
        for _ in range(int(case[1:])): tap('Right')
    elif case == 'l1': tap('Left')
    elif case in ('q', 'a', 'm'):                       # on '?'; a = Down (Aine), m = Up (Morrigan)
        for _ in range(4): tap('Right')
        if case != 'q': t += 20; tap({'a': 'Down', 'm': 'Up'}[case])
    elif case == 'p2':
        L.append(f'{t} tap 5 2 Players Start'); t += 20
        tap('Right', 'P2'); tap('Right', 'P2'); tap('Right')
    elif case == 'p2m':                                 # P1 to '?' (1 -> 2 -> 4 -> 5, skipping P2 on 3) + Up
        L.append(f'{t} tap 5 2 Players Start'); t += 20
        for _ in range(3): tap('Right')
        t += 20; tap('Up')
    for k in range(6):                                  # watch the cursor / '?' rotation
        L.append(f'{t + 3 * k} snap {snapdir}/sel{k}.png')
    t += 20
    tap('Button 1')
    if case.startswith('p2'): tap('Button 1', 'P2')
    for k, d in enumerate((5, 30, 120, 400, 900, 1300)):
        L.append(f'{t + d} snap {snapdir}/post{k}.png')
    L.append(f'{t + d + 1} exit')
    return '\n'.join(L) + '\n'


def run(romdir, eep, case, work):
    snap = f'{work}/{os.path.basename(romdir)}_{case}'
    if romdir == ORIG:                                  # original runs never change: cache per EEPROM + case
        import hashlib
        key = hashlib.sha1(open(eep, 'rb').read() + timeline(case, '').encode()).hexdigest()[:16]
        cache = f'{ROOT}/out/tmp/regress_cache/{key}'
        if os.path.isdir(cache): return cache
        snap = cache
    os.makedirs(snap, exist_ok=True)
    nvroot = f'{work}/nv_{os.path.basename(romdir)}_{case}'
    setname = 'gunbird2' if romdir == ORIG else 'gunbird2m'
    nv = f'{nvroot}/{setname}'
    shutil.rmtree(nvroot, ignore_errors=True); os.makedirs(nv)
    shutil.copy(eep, nv + '/eeprom')
    tl = f'{work}/{os.path.basename(romdir)}_{case}.tl'
    open(tl, 'w').write(timeline(case, snap))
    out = subprocess.run([ROOT + '/tools/mame/run.sh', romdir, tl], capture_output=True, text=True,
                         env=dict(os.environ, GB2_NVRAM=nvroot, GB2_SET=setname)).stdout
    if 'UNTIL met' not in out: print(f'  {case}: select screen never reached ({romdir})')
    return snap


def main():
    eep = os.path.abspath(sys.argv[1])
    cases = sys.argv[2:] or ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'l1', 'q', 'p2']
    work = tempfile.mkdtemp(prefix='regsel_', dir=os.environ.get('TMPDIR'))
    bad = 0
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(os.cpu_count() or 2) as ex:
        res = list(ex.map(lambda c: (run(ORIG, eep, c, work), run(PATCHED, eep, c, work)), cases))
    for c, (a, b) in zip(cases, res):
        diffs = []
        for f in sorted(os.listdir(a)):
            x = np.asarray(Image.open(f'{a}/{f}').convert('RGB'), int)
            y = np.asarray(Image.open(f'{b}/{f}').convert('RGB'), int)
            n = int((np.abs(x - y).sum(-1) > 0).sum())
            if n: diffs.append(f'{f[:-4]}:{n}px')
        bad += bool(diffs)
        print(f'{c:3s} ' + ('identical' if not diffs else 'DIFF ' + ' '.join(diffs)))
    print(f'snapshots in {work}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
