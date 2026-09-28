#!/usr/bin/env python3
"""Stage-demo checks via maintenance Stage Select (PlayMode 'Stage Demo').
  morrigan  : every Morrigan scene (stages 1-6, P2 none/0..5) -> contact sheets out/tmp/sdcheck/m_s<stage>.png
  regress   : original scenes (solo 0..5, some pairs) on original vs patched ROMs, pixel compare
usage: check_stagedemo.py <morrigan|regress> <eeprom> [--jp]"""
import os, sys, subprocess, shutil, tempfile, itertools
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
SNAPS = list(range(1700, 3000, 50))


def run(romdir, eep, stage, p1, p2, jp, tag, work):
    d = f'{work}/{tag}'; os.makedirs(d, exist_ok=True)
    args = [sys.executable, ROOT + '/tools/mame/mkstage.py', str(stage), str(p1), '--mode', '2']
    if p2 is not None: args += ['--p2', str(p2)]
    tl = [l for l in subprocess.run(args, capture_output=True, text=True).stdout.splitlines() if not l.startswith('#')]
    if jp: tl = ['1 field 0 Region', '1200 poke32 06040004 0'] + tl
    tl += [f'{f} snap {d}/f{f}.png' for f in SNAPS] + [f'{SNAPS[-1] + 1} exit']
    open(d + '.tl', 'w').write('\n'.join(tl) + '\n')
    nv = d + '_nv'; shutil.rmtree(nv, ignore_errors=True); os.makedirs(nv + '/gunbird2')
    shutil.copy(eep, nv + '/gunbird2/eeprom')
    subprocess.run([ROOT + '/tools/mame/run.sh', romdir, d + '.tl'], capture_output=True, env=dict(os.environ, GB2_NVRAM=nv))
    return d


def sheet(dirs, out, every=3):
    rows = []
    for d in dirs:
        fs = sorted(os.listdir(d), key=lambda s: int(s[1:-4]))[::every]
        rows.append([Image.open(f'{d}/{f}').resize((112, 160)) for f in fs])
    W = max(len(r) for r in rows) * 114; H = len(rows) * 162
    o = Image.new('RGB', (W, H))
    for y, r in enumerate(rows):
        for x, im in enumerate(r): o.paste(im, (x * 114, y * 162))
    o.save(out)


def main():
    mode, eep = sys.argv[1], os.path.abspath(sys.argv[2]); jp = '--jp' in sys.argv
    work = ROOT + '/out/tmp/sdcheck'; os.makedirs(work, exist_ok=True)
    pat = ROOT + '/out/roms'; org = ROOT + '/mame_roms'
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        if mode == 'morrigan':
            jobs = [(s, p2) for s in range(1, 7) for p2 in [None, 0, 1, 2, 3, 4, 5]]
            res = list(ex.map(lambda j: run(pat, eep, j[0], 6, j[1], jp, f"m{'j' if jp else ''}_s{j[0]}_p{j[1]}", work), jobs))
            for s in range(1, 7):
                sheet([r for r, j in zip(res, jobs) if j[0] == s], f"{work}/m{'j' if jp else ''}_s{s}.png")
        else:
            jobs = [(s, c, None) for s in (1, 4, 6) for c in range(6)] + [(2, 0, 5), (3, 2, 3), (5, 1, 4), (6, 4, 0)]
            res = list(ex.map(lambda j: (run(org, eep, *j, jp, f'o_{j[0]}_{j[1]}_{j[2]}', work),
                                          run(pat, eep, *j, jp, f'p_{j[0]}_{j[1]}_{j[2]}', work)), jobs))
            bad = 0
            for (a, b), j in zip(res, jobs):
                diff = []
                for f in sorted(os.listdir(a)):
                    x = np.asarray(Image.open(f'{a}/{f}').convert('RGB'), int); y = np.asarray(Image.open(f'{b}/{f}').convert('RGB'), int)
                    n = int((np.abs(x - y).sum(-1) > 0).sum())
                    if n: diff.append(f'{f[:-4]}:{n}')
                bad += bool(diff)
                print(j, 'identical' if not diff else 'DIFF ' + ' '.join(diff[:6]))
            sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
