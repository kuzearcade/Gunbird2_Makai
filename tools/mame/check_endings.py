#!/usr/bin/env python3
"""Run Morrigan's six endings on the patched set (gunbird2m) through the maintenance Stage Select, PlayMode 'Ending
Demo' (1P Jiki6, 2P NoUse = solo / Jiki0-Jiki4 = the pair endings; Aine + Morrigan uses the solo one), in English
and Japanese.  Pass per run:
  - the ending plays (GameLoop state 3) and finishes (the state leaves 3 again) within the frame budget;
  - no background layer is ever on (video register 0x1C, tilemap 0 enabled): the DC backdrop of the END60 / END61
    close-ups is baked into those pictures (tools/port_endings.py BACKDROP), since the BG-vs-sprite priority of the
    real PS5 differs from MAME's (on the board the BG layer covered the pictures);
  - a contact sheet (a frame every 30) is written to out/tmp/endings/<run>.png for a visual check.
usage: check_endings.py [--runs solo,0,1,2,3,4] [--lang en,jp] [--frames 3000] [--jobs N]"""
import os, sys, struct, subprocess, shutil, tempfile, argparse, glob
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')


def run(case, lang, a, work):
    tag = f'{case}_{lang}'; d = f'{work}/{tag}'; os.makedirs(d)
    args = [sys.executable, ROOT + '/tools/mame/mkstage.py', '1', '6', '--mode', '4']
    if case != 'solo': args += ['--p2', case]
    out = subprocess.run(args, capture_output=True, text=True).stdout.splitlines()
    st = int([l for l in out if 'START' in l][0].split()[-1])
    L = [l for l in out if not l.startswith('#')]
    if lang == 'jp': L = ['1 field 0 Region', '1200 poke32 06040004 0'] + L
    L += [f'{st} phash 2 {d}/h.hash']
    L += [f'{st + f} snap {d}/f{f:05d}.png' for f in range(0, a.frames, 30)]
    L += [f'{st + f} dumpmem 0405ffe0 20 {d}/v{f:05d}.bin' for f in range(0, a.frames, 10)]
    L += [f'{st + a.frames} exit']
    L = [l for l in L if not l[0].isdigit()] + sorted((l for l in L if l[0].isdigit()), key=lambda l: int(l.split()[0]))
    open(d + '.tl', 'w').write('\n'.join(L) + '\n')
    nv = f'{d}_nv/gunbird2m'; os.makedirs(nv); shutil.copy(ROOT + '/out/tmp/eeprom_morrigan.bin', nv + '/eeprom')
    subprocess.run([ROOT + '/tools/mame/run.sh', ROOT + '/out/roms', d + '.tl'], capture_output=True,
                   env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2m'))
    return tag, d


def verdict(tag, d):
    states = [int(l.split()[5]) for l in open(d + '/h.hash')] if os.path.exists(d + '/h.hash') else []
    played = 3 in states
    finished = played and states.index(3) + states[states.index(3):].index(3) < len(states) and \
        any(s != 3 for s in states[states.index(3):])
    frames = 2 * sum(1 for s in states if s == 3)
    bg = sum(1 for v in glob.glob(d + '/v*.bin') if struct.unpack_from('>I', open(v, 'rb').read(), 0x1C)[0] & 0x8000)
    sheet(d, f'{ROOT}/out/tmp/endings/{tag}.png')
    ok = played and finished and bg == 0
    return ok, (f'{tag:8s} {"OK " if ok else "BAD"} ending {"played" if played else "NOT PLAYED"}'
                f'{", finished" if finished else ", did not finish"} ({frames} frames); background on in {bg} '
                f'samples')


def sheet(d, out):
    from PIL import Image
    fs = sorted(glob.glob(d + '/f*.png'))
    if not fs: return
    ims = [Image.open(f).convert('RGB') for f in fs]
    w, h = ims[0].width // 2, ims[0].height // 2
    cols = 12; rows = (len(ims) + cols - 1) // cols
    o = Image.new('RGB', (cols * w, rows * h))
    for i, im in enumerate(ims): o.paste(im.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    os.makedirs(os.path.dirname(out), exist_ok=True); o.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', default='solo,0,1,2,3,4'); ap.add_argument('--lang', default='en,jp')
    ap.add_argument('--frames', type=int, default=3000); ap.add_argument('--jobs', type=int, default=6)
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix='endings_')
    jobs = [(c, l) for c in a.runs.split(',') for l in a.lang.split(',')]
    fails = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for tag, d in ex.map(lambda j: run(*j, a, work), jobs):
            ok, msg = verdict(tag, d); fails += not ok; print(msg, flush=True)
    print(f'contact sheets in {ROOT}/out/tmp/endings/; work dir {work}')
    print('PASS' if not fails else f'FAIL ({fails})')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
