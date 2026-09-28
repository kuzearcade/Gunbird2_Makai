#!/usr/bin/env python3
"""Sound-effect coverage runs: which effect IDs does the game actually play (timeline 'sndlog').
Runs (parallel): attract mode, and Stage Select plays of every stage x character (1P) with shot held (released
periodically for charge attacks), bombs, movement and coin+Start for continues.
usage: sndcov.py <romdir> <eeprom> <outdir> [--set gunbird2] [--chars 0,1,..] [--stages 1,..] [--frames N]
Writes <outdir>/<run>.log and <outdir>/ids.txt (union of played IDs, hex)."""
import os, sys, subprocess, argparse, re
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')


def play_inputs(t0, frames):
    ev, t = [f'{t0} press P1 Button 1'], t0
    moves = ['P1 Left', 'P1 Up', 'P1 Right', 'P1 Down']
    k = 0
    while t < t0 + frames:
        ev.append(f'{t} tap 30 {moves[k % 4]}')
        if k % 5 == 2: ev += [f'{t + 40} release P1 Button 1', f'{t + 90} press P1 Button 1']   # charge attack
        if k % 9 == 4: ev.append(f'{t + 60} tap 4 P1 Button 2')                                 # bomb
        if k % 6 == 0: ev += [f'{t + 10} tap 4 Coin 1', f'{t + 30} tap 4 1 Player Start']       # continue
        t += 120; k += 1
    return ev


def run(args, name, tl):
    d = f'{args.out}/{name}'
    nv = d + '_nv'; os.makedirs(f'{nv}/{args.set}', exist_ok=True)
    subprocess.run(['cp', args.eeprom, f'{nv}/{args.set}/eeprom'])
    open(d + '.tl', 'w').write('\n'.join(tl) + '\n')
    r = subprocess.run([ROOT + '/tools/mame/run.sh', args.romdir, d + '.tl'], capture_output=True, text=True,
                       env=dict(os.environ, GB2_NVRAM=nv, GB2_SET=args.set))
    open(d + '.log', 'w').write(r.stdout + r.stderr)
    return {int(m, 16) for m in re.findall(r'^SND ([0-9a-f]+)', r.stdout, re.M)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('romdir'); ap.add_argument('eeprom'); ap.add_argument('out')
    ap.add_argument('--set', default='gunbird2'); ap.add_argument('--chars', default='0,1,2,3,4,5')
    ap.add_argument('--stages', default='1,2,3,4,5,6,7'); ap.add_argument('--frames', type=int, default=9000)
    ap.add_argument('--attract', type=int, default=40000)
    args = ap.parse_args(); args.eeprom = os.path.abspath(args.eeprom); os.makedirs(args.out, exist_ok=True)
    jobs = []
    if args.attract: jobs.append(('attract', ['600 sndlog', f'{args.attract} exit']))
    for c in map(int, args.chars.split(',')):
        for s in map(int, args.stages.split(',')):
            out = subprocess.run([sys.executable, ROOT + '/tools/mame/mkstage.py', str(s), str(c)],
                                 capture_output=True, text=True).stdout.splitlines()
            start = int(next(l.split()[-1] for l in out if 'START' in l))
            tl = [l for l in out if not l.startswith('#')] + [f'{start} sndlog'] + play_inputs(start + 60, args.frames)
            tl.append(f'{start + 60 + args.frames} exit')
            jobs.append((f'c{c}_s{s}', tl))
    ids = set()
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        for (name, _), got in zip(jobs, ex.map(lambda j: run(args, *j), jobs)):
            print(f'{name}: {len(got)} ids'); ids |= got
    open(args.out + '/ids.txt', 'w').write('\n'.join(f'{i:x}' for i in sorted(ids)) + '\n')
    print('union', len(ids))


if __name__ == '__main__':
    main()
