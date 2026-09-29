#!/usr/bin/env python3
"""Draw census of the ORIGINAL game (stock gunbird2): does a screen draw pixels with given palette lines?
A line can hold black (never written with a colour, tools/mame/palcensus.py) and still be drawn with - the select
screen's art does - so a line is only free for Morrigan's colours if the game never draws with it while her colours
are loaded.  Method: the same run twice, once clean and once with the lines' entries rewritten to a vivid colour
after every frame (timeline 'palpoison'), comparing a screen hash every frame (timeline 'phash').  Any difference =
the line is drawn.
  select  the select screen and the first seconds of play (regress_select.py cases), each line on its own;
          reported per GameLoop state (9 = select screen, 10 = play)
  game    whole games (regress_game.py cases), all candidate lines at once, reported per GameLoop state
usage: paldraw.py select [--lines 1c-1f,2c-3f]
       paldraw.py game [--lines 30-36[/24-2b...]] [--cases 1P1,...] [--frames 100000] [--set gunbird2m]
          (game: '/' separates line groups, each poisoned in a run of its own against one shared clean run; a group
          'e:200-23f+10+5d-5e' lists palette entries instead of lines)"""
import os, sys, subprocess, tempfile, argparse, shutil, itertools
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regress_select as RS
ROOT = RS.ROOT
POISON = 'FF00FF00'                       # magenta, RGBx


def parse_lines(s):
    out = []
    for part in s.split(','):
        a, _, b = part.partition('-'); out += list(range(int(a, 16), int(b or a, 16) + 1))
    return out


SET = 'gunbird2'                          # --set gunbird2m: the patched build (out/roms)


def run_tl(tl_lines, work, tag, eep):
    """screen hashes of one run (phash lines: frame hash stage 1P 2P GameLoop)"""
    nv = f'{work}/nv_{tag}/{SET}'; shutil.rmtree(os.path.dirname(nv), ignore_errors=True); os.makedirs(nv)
    shutil.copy(eep, nv + '/eeprom')
    open(f'{work}/{tag}.tl', 'w').write('\n'.join(tl_lines) + '\n')
    subprocess.run([ROOT + '/tools/mame/run.sh', RS.ORIG if SET == 'gunbird2' else ROOT + '/out/roms',
                    f'{work}/{tag}.tl'], capture_output=True, env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET=SET))
    return [l.split()[1] for l in open(f'{work}/{tag}.hash')] if os.path.exists(f'{work}/{tag}.hash') else []


def select_case(case, work, lines, eep):
    base = [l for l in RS.timeline(case, work + '/snap').splitlines() if ' snap ' not in l]
    def tl(tag, extra): return base + [f'2 phash 1 {work}/{tag}.hash'] + extra
    clean = run_tl(tl(f'{case}_clean', []), work, f'{case}_clean', eep)
    states = [l.split()[5] for l in open(f'{work}/{case}_clean.hash')]
    drawn = {}                                    # line -> {GameLoop state: frames that differ}
    for l in lines:
        tag = f'{case}_{l:02x}'
        h = run_tl(tl(tag, [f'900 palpoison {16 * l:x} {16 * l + 15:x} {POISON}']), work, tag, eep)
        d = {}
        for x, y, st in zip(clean, h, states):
            if x != y: d[st] = d.get(st, 0) + 1
        if d: drawn[l] = d
    return case, drawn, len(clean)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['select', 'game']); ap.add_argument('--lines')
    ap.add_argument('--cases'); ap.add_argument('--frames', type=int, default=100000)
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--set', default='gunbird2', choices=['gunbird2', 'gunbird2m'])
    a = ap.parse_args()
    global SET
    SET = a.set
    eep = ROOT + '/out/tmp/eeprom_regress.bin'
    work = tempfile.mkdtemp(prefix='paldraw_')
    if a.mode == 'select':
        lines = parse_lines(a.lines or '1c-1f,2c-3f')
        cases = a.cases.split(',') if a.cases else ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'l1', 'q', 'a', 'p2']
        per = {'9': set(), '10': set()}           # GameLoop 9 = select screen, 10 = play (first ~20 s)
        with ThreadPoolExecutor(a.jobs) as ex:
            for case, drawn, n in ex.map(lambda c: select_case(c, work, lines, eep), cases):
                for l, d in drawn.items():
                    for st in d: per.setdefault(st, set()).add(l)
                print(f'{case:3s} {n} frames; drawn on select: ' +
                      (' '.join(f'{l:02x}' for l, d in drawn.items() if '9' in d) or 'none') + '; in play: ' +
                      (' '.join(f'{l:02x}' for l, d in drawn.items() if '10' in d) or 'none'), flush=True)
        for st, name in (('9', 'select screen'), ('10', 'play (first seconds)')):
            print(f'{name}: not drawn: ' + ' '.join(f'{l:02x}' for l in lines if l not in per.get(st, ())))
    else:
        import regress_game as RG
        def entry_ranges(g):                     # -> [(first entry, last entry)]
            if g.startswith('e:'):
                return [(int(x.split('-')[0], 16), int(x.split('-')[-1], 16)) for x in g[2:].split('+')]
            return [(16 * l, 16 * l + 15) for l in parse_lines(g)]
        specs = (a.lines or '30-36').split('/')
        groups = [entry_ranges(g) for g in specs]
        cases = a.cases.split(',') if a.cases else [f'1P{c}' for c in range(1, 7)] + ['2P1-2', '2P3-4', '2P5-6']
        def gname(g): return f'{g[0][0]:03x}-{g[-1][1]:03x}' + (f'+{len(g) - 1}' if len(g) > 1 else '')
        def one(job):
            case, g = job
            ga = argparse.Namespace(frames=a.frames, every=1)
            base = [l for l in RG.timeline(case, ga, f'{work}/{case}').splitlines() if ' phash ' not in l and ' snap ' not in l]
            if g is None:
                return case, None, run_tl(base + [f'2 phash 4 {work}/{case}_c.hash'], work, f'{case}_c', eep)
            tag = f'{case}_{gname(g)}'
            return case, g, run_tl(base + [f'2 phash 4 {work}/{tag}.hash'] +
                                   [f'2 palpoison {e0:x} {e1:x} {POISON}' for e0, e1 in g], work, tag, eep)
        names = {'2': 'attract', '3': 'ending', '4': 'name entry/ranking', '5': 'game start', '8': 'stage demo',
                 '9': 'select/2P join', '10': 'play'}
        res = {}
        with ThreadPoolExecutor(a.jobs) as ex:
            for case, g, h in ex.map(one, [(c, g) for c in cases for g in [None] + groups]):
                res[case, None if g is None else gname(g)] = h
        for g in groups:
            allst = {}
            print(f'lines {gname(g)}:')
            for case in cases:
                clean = res[case, None]; pois = res[case, gname(g)]
                states = [l.split()[5] for l in open(f'{work}/{case}_c.hash')]
                d = {}
                for x, y, st in zip(clean, pois, states):
                    if x != y: d[st] = d.get(st, 0) + 1
                for st, k in d.items(): allst[st] = allst.get(st, 0) + k
                print(f'  {case:6s} {len(clean)} samples; differing samples per state: ' +
                      (', '.join(f'{names.get(st, st)} {k}' for st, k in sorted(d.items())) or 'none'))
            print(f'  lines {gname(g)} drawn in: ' +
                  (', '.join(f'{names.get(st, st)} ({k} samples)' for st, k in sorted(allst.items())) or 'no state'), flush=True)

if __name__ == '__main__':
    main()
