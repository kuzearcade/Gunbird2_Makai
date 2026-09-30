#!/usr/bin/env python3
"""Stage-end / transition sequences with Morrigan on the patched set (gunbird2m), screenshots for review against the
Dreamcast (tools/flycast/stage_end_dc.py).  Two triggers from the maintenance Stage Select:
  demo   PlayMode 'Stage Demo': the post-stage story scene of <stage> for a pairing, directly (G_StageDemo, state 8)
         - stages 1-7 x pairings: 1P Morrigan + 2P NoUse / Jiki0-5, 1P Jiki0-5 + 2P Morrigan; English and Japanese
  flow   PlayMode 'Full Play' (always from stage 1) with the stage frame counter 0x0604C74C kept past 0x5460 (the
         game's own stage-end condition, flag 0x0604C750): every stage ends as it starts, so one run goes through
         all transitions in game order - stage 1 end, scene 1, stage 2, ..., stage 7 end, the ending - per pairing
Screenshots every 20 frames into stage_endings_verification/port/<EN|JP>/<demo|flow>_s<stage>_<p1>-<p2>/ (p = 1-based
charNo, 7 = Morrigan, 0 = NoUse), and per case the scene's frames (the stage-demo state) with a contact sheet.
usage: check_stage_end.py [demo|flow|all] [--lang EN,JP] [--stages 1-7] [--jobs N]"""
import os, sys, re, shutil, argparse, subprocess, itertools
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
OUT = ROOT + '/stage_endings_verification/port'
M = 6
PAIRS = [(M, None)] + [(M, c) for c in range(6)] + [(None, M)] + [(c, M) for c in range(6)]   # (None, M): P2 only
FRAMES = {'demo': 4200, 'flow': 9000}


def tag(kind, stage, p1, p2):
    return f'{kind}_s{stage}_{0 if p1 is None else p1 + 1}-{0 if p2 is None else p2 + 1}'


def run(job):
    lang, kind, stage, p1, p2 = job
    d = f'{OUT}/{lang}/{tag(kind, stage, p1, p2)}'
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    args = [sys.executable, ROOT + '/tools/mame/mkstage.py', str(stage), str(M if p1 is None else p1), '--mode',
            '2' if kind == 'demo' else '1']
    if p1 is None: args += ['--p2', '0']                 # P2 only: 1P Morrigan / 2P Jiki0 first, then on the menu
    elif p2 is not None: args += ['--p2', str(p2)]      # 1P -> NoUse (after Jiki6) and 2P -> Morrigan
    out = subprocess.run(args, capture_output=True, text=True).stdout.splitlines()
    st = int(next(l.split()[-1] for l in out if 'START' in l))
    L = [l for l in out if not l.startswith('#')]
    if p1 is None:
        L = [l for l in L if int(l.split()[0]) < st]
        t = st
        for x in ['Up'] * 4 + ['Right'] + ['Down'] + ['Right'] * 6 + ['Down'] * 3: L.append(f'{t} tap 3 P1 {x}'); t += 10
        L += [f'{t + 10} snap {d}/menu.png', f'{t + 20} tap 5 1 Player Start']; st = t + 20
    if lang == 'JP': L = ['1 field 0 Region', '1200 poke32 06040004 0'] + L
    n = FRAMES[kind]
    L += [f'{st} phash 2 {d}.hash']
    if kind == 'flow':                                   # invincible; every stage ends as it starts
        L += [f'{f} poke8 06040016 01' for f in range(st, st + n, 60)]
        L += [f'{f} poke32 0604c74c 5461' for f in range(st + 300, st + n, 30)]
    L += [f'{st + f} snap {d}/f{f:05d}.png' for f in range(0, n, 20)] + [f'{st + n} exit']
    L = [l for l in L if not l[0].isdigit()] + sorted((l for l in L if l[0].isdigit()), key=lambda l: int(l.split()[0]))
    open(d + '.tl', 'w').write('\n'.join(L) + '\n')
    nv = d + '_nv/gunbird2m'; os.makedirs(nv); shutil.copy(ROOT + '/out/tmp/eeprom_morrigan.bin', nv + '/eeprom')
    subprocess.run([ROOT + '/tools/mame/run.sh', ROOT + '/out/roms', d + '.tl'], capture_output=True,
                   env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2m'))
    shutil.rmtree(d + '_nv', ignore_errors=True)
    # GameLoop state per frame (phash column 6): the scene = state 8 (stage demo), 7 = prize (JP)
    states = {}
    if os.path.exists(d + '.hash'):
        for l in open(d + '.hash'):
            p = l.split(); states[int(p[0]) - st] = p[5]
    seq = []
    for f in sorted(states):
        if not seq or seq[-1][1] != states[f]: seq.append((f, states[f]))
    scene = [f for f in range(0, n, 20) if states.get(f - f % 2) == '8']
    if kind == 'flow':                                   # one sheet per transition (each stretch of state 8)
        runs, prev = [], None
        for f in range(0, n, 20):
            if states.get(f - f % 2) == '8':
                if prev != '8': runs.append([])
                runs[-1].append(f)
            prev = states.get(f - f % 2)
        for k, r in enumerate(runs): sheet(d, r, f'{d}_scene{k + 1}.png')
        return job, seq, len(runs)
    sheet(d, scene or list(range(0, n, 20)), f'{d}_sheet.png')
    return job, seq, len(scene)


def sheet(d, frames, out, w=112, h=160, cols=16):
    fs = [f'{d}/f{f:05d}.png' for f in frames if os.path.exists(f'{d}/f{f:05d}.png')][::2]
    if not fs: return
    o = Image.new('RGB', (cols * w, ((len(fs) + cols - 1) // cols) * h))
    for i, f in enumerate(fs): o.paste(Image.open(f).convert('RGB').resize((w, h)), ((i % cols) * w, (i // cols) * h))
    o.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', nargs='?', default='all', choices=['demo', 'flow', 'all'])
    ap.add_argument('--lang', default='EN,JP'); ap.add_argument('--stages', default='1-7')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    s0, s1 = map(int, a.stages.split('-'))
    jobs = []
    for lang in a.lang.split(','):
        if a.what in ('demo', 'all'): jobs += [(lang, 'demo', s, p1, p2) for s in range(s0, s1 + 1) for p1, p2 in PAIRS]
        if a.what in ('flow', 'all'): jobs += [(lang, 'flow', 1, p1, p2) for p1, p2 in PAIRS]
    bad = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for (lang, kind, stage, p1, p2), seq, nscene in ex.map(run, jobs):
            t = tag(kind, stage, p1, p2)
            ok = (nscene == 6 and '3' in [s for _, s in seq]) if kind == 'flow' else (nscene > 0 or stage == 7)
            bad += not ok
            print(f'{lang} {t:14s} {"OK " if ok else "BAD"} ' + (f'scenes {nscene} (6 + ending expected)' if kind == 'flow'
                  else f'scene frames {nscene * 20:5d}') + '; states '
                  + ' '.join(f'{s}@{f}' for f, s in seq), flush=True)
    print(f'screenshots in {OUT}')
    print('PASS' if not bad else f'FAIL ({bad})')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
