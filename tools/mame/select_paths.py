#!/usr/bin/env python3
"""Find select-screen input sequences for every original character (1P) and every ordered 2P pair, for the
whole-game regression (tools/mame/regress_game.py).  The select screen is deterministic with Random()'s idle-time
entropy neutralised, so a sequence found once replays exactly; each is verified by reading the players' charNo
(player block +0x58: 0x06055058 / 0x06055108, 1-based).
1P: cursor starts on character 2; Right: 2 -> 3 -> 4 -> 5 -> '?' -> 1; '?' + Down = Aine (6) with the Aine flag = 2.
2P: P1 decides first (1P mapping), then P2 is searched: n x Right (0-6), optionally + Down.
Writes out/tmp/select_paths.json {"1P1": {"p1": [...], "p2": null}, "2P4-1": {"pre": [P2 taps first], ...}, "2P1-2": {...}, ...} (keys 1-based charNo).
usage: select_paths.py <eeprom>"""
import os, sys, json, subprocess, tempfile, shutil, itertools
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
P1 = {1: ['Left'], 2: [], 3: ['Right'], 4: ['Right'] * 2, 5: ['Right'] * 3, 6: ['Right'] * 4 + ['Down']}


def select_lines(p1, p2, pre=()):
    """timeline lines from boot to both decisions; returns (lines, frame after the last decision)"""
    L = ['60 poke16 06029226 e201', '600 poke16 06029226 e201', '600 tap 5 Coin 1']
    if p2 is not None: L.append('610 tap 5 Coin 1')
    L.append('1000 until 0605ccde ffff 0134 30 1 Player Start')
    t = 1080
    if p2 is not None: L.append('1080 tap 5 2 Players Start'); t = 1140
    for x in pre: L.append(f'{t} tap 3 P2 {x}'); t += 10     # P2 off the slot P1 needs (P1's cursor skips P2's)
    for x in p1: L.append(f'{t} tap 3 P1 {x}'); t += 10
    L.append(f'{t} tap 3 P1 Button 1'); t += 60
    if p2 is not None:
        for x in p2: L.append(f'{t} tap 3 P2 {x}'); t += 10
        L.append(f'{t} tap 3 P2 Button 1'); t += 10
    return L, t


def probe(eep, p1, p2, work, tag, pre=()):
    L, t = select_lines(p1, p2, pre)
    L += [f'{t + 400} peek 06055058 1', f'{t + 401} peek 06055108 1', f'{t + 402} exit']
    nv = f'{work}/nv_{tag}'; shutil.rmtree(nv, ignore_errors=True); os.makedirs(nv + '/gunbird2m')
    shutil.copy(eep, nv + '/gunbird2m/eeprom')
    open(f'{work}/{tag}.tl', 'w').write('\n'.join(L) + '\n')
    out = subprocess.run([ROOT + '/tools/mame/run.sh', ROOT + '/out/roms', f'{work}/{tag}.tl'], capture_output=True,
                         text=True, env=dict(os.environ, GB2_NVRAM=nv, GB2_SET='gunbird2m')).stdout
    v = [int(l.split()[2], 16) for l in out.splitlines() if l.startswith('PEEK')]
    return tuple(v) if len(v) == 2 else None


def main():
    eep = os.path.abspath(sys.argv[1])
    work = tempfile.mkdtemp(prefix='selpath_')
    res = {}
    cands = [['Right'] * n + d for n in range(7) for d in ([], ['Down'])] + [['Left'] * n + d for n in (1, 2) for d in ([], ['Down'])]
    name = lambda c: ''.join(x[0] for x in c) or '0'
    ex = ThreadPoolExecutor(os.cpu_count() or 4)
    # 1P
    for a, got in zip(range(1, 7), ex.map(lambda a: probe(eep, P1[a], None, work, f'1P{a}'), range(1, 7))):
        if got and got[0] == a: res[f'1P{a}'] = {'p1': P1[a], 'p2': None}
        else: print(f'1P{a}: path gave {got}')
    # 2P stage 1: P1 sequence -> P1 character (P2 decides on its start slot)
    p1map = {}
    for c, got in zip(cands, ex.map(lambda c: probe(eep, c, [], work, 'p1_' + name(c)), cands)):
        if got and got[0] not in p1map: p1map[got[0]] = c
    pre = {k: [] for k in p1map}
    left = [a for a in range(1, 7) if a not in p1map]
    if left:                                            # retry with P2 moved one slot first
        for c, got in zip(cands, ex.map(lambda c: probe(eep, c, [], work, 'p1pre_' + name(c), ['Right']), cands)):
            if got and got[0] in left and got[0] not in p1map: p1map[got[0]] = c; pre[got[0]] = ['Right']
    print('2P, P1 paths:', {k: ('P2 R, ' if pre[k] else '') + name(v) for k, v in sorted(p1map.items())})
    # 2P stage 2: P2 sequences per pair
    jobs = [(a, b, c) for a, b in itertools.permutations(range(1, 7), 2) if a in p1map for c in cands]
    for (a, b, c), got in zip(jobs, ex.map(lambda j: probe(eep, p1map[j[0]], j[2], work, f'2P{j[0]}-{j[1]}_{name(j[2])}',
                                                          pre[j[0]]), jobs)):
        key = f'2P{a}-{b}'
        if got and got == (a, b) and key not in res: res[key] = {'pre': pre[a], 'p1': p1map[a], 'p2': c}
    missing = [f'2P{a}-{b}' for a, b in itertools.permutations(range(1, 7), 2) if f'2P{a}-{b}' not in res]
    missing += [f'1P{a}' for a in range(1, 7) if f'1P{a}' not in res]
    json.dump(res, open(ROOT + '/out/tmp/select_paths.json', 'w'), indent=1)
    print(f'{len(res)} paths found; missing: {missing or "none"}')


if __name__ == '__main__':
    main()
