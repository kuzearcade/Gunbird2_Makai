#!/usr/bin/env python3
"""Sound regression: the same Stage Select play (stage, character, scripted inputs incl. continues) on the original
set and on the patched set.  Pass = the YMF278B register write sequence (timeline 'ymflog') is identical; the
-wavwrite recordings are compared for information only: any change in executed CPU cycles (patched code, or even a
different menu path on the unmodified ROM) moves the phase of the 9-cycle vblank wait loop (0x06028918), so the
same writes land up to 8 cycles earlier/later and MAME's YMF278B output differs slightly at some note onsets
(see re/NOTES.md "Sound").  Random()'s idle-time entropy is neutralised as in regress_select.py.
usage: regress_sound.py <eeprom> [--set gunbird2m] [--chars 0,1,2,3,4,5] [--stage 1] [--frames 3000]"""
import os, sys, subprocess, argparse, wave, tempfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sndcov import play_inputs
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')


def run(romdir, setname, eep, c, a, work):
    tag = f'{setname}_c{c}'
    out = subprocess.run([sys.executable, ROOT + '/tools/mame/mkstage.py', str(a.stage), str(c)],
                         capture_output=True, text=True).stdout.splitlines()
    start = int(next(l.split()[-1] for l in out if 'START' in l))
    tl = ['60 poke16 06029226 e201', '600 poke16 06029226 e201', f'{start} sndtrace', f'{start} ymflog {work}/{tag}.ymf'] + \
         [l for l in out if not l.startswith('#')]
    tl += play_inputs(start + 60, a.frames) + [f'{start + 60 + a.frames} exit']
    open(f'{work}/{tag}.tl', 'w').write('\n'.join(tl) + '\n')
    nv = f'{work}/{tag}_nv'; os.makedirs(f'{nv}/{setname}', exist_ok=True)
    subprocess.run(['cp', eep, f'{nv}/{setname}/eeprom'])
    r = subprocess.run([ROOT + '/tools/mame/run.sh', romdir, f'{work}/{tag}.tl', '-wavwrite', f'{work}/{tag}.wav'],
                       capture_output=True, text=True, env=dict(os.environ, GB2_NVRAM=nv, GB2_SET=setname))
    open(f'{work}/{tag}.log', 'w').write(r.stdout)
    w = wave.open(f'{work}/{tag}.wav')
    ymf = [l.split() for l in open(f'{work}/{tag}.ymf')]
    return np.frombuffer(w.readframes(w.getnframes()), np.int16), ymf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('eeprom'); ap.add_argument('--set', default='gunbird2m')
    ap.add_argument('--chars', default='0,1,2,3,4,5'); ap.add_argument('--stage', type=int, default=1)
    ap.add_argument('--frames', type=int, default=3000)
    ap.add_argument('--patched', default=ROOT + '/out/roms', help='rom directory of the patched set')
    a = ap.parse_args(); eep = os.path.abspath(a.eeprom)
    work = tempfile.mkdtemp(prefix='regsnd_', dir=os.environ.get('TMPDIR'))
    chars = [int(c) for c in a.chars.split(',')]
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        res = list(ex.map(lambda c: (run(ROOT + '/mame_roms', 'gunbird2', eep, c, a, work),
                                     run(a.patched, a.set, eep, c, a, work)), chars))
    bad = 0
    for c, ((x, ya), (y, yb)) in zip(chars, res):
        same = len(ya) == len(yb) and all(p[2:] == q[2:] for p, q in zip(ya, yb))
        cyc = sorted({round((float(q[1]) - float(p[1])) * 28.636363) for p, q in zip(ya, yb)})
        n = min(len(x), len(y)); d = int(np.count_nonzero(x[:n] != y[:n]))
        print(f'char {c}: {len(ya)} register writes ' + ('identical' if same else 'DIFFER') +
              f' (timing offsets {cyc} CPU cycles); audio {d} of {n} samples differ')
        bad += not same
    print('work dir', work)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
