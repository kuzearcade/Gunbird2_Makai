#!/usr/bin/env python3
"""Dreamcast reference for tools/mame/check_stage_end.py: Morrigan's post-stage story scenes (Stage Select, PlayMode
'Stage Demo') for stages 1-7 and every pairing, all in one Flycast session per disc (a scene returns to Stage Select
with the cursor on PlayMode, so the next one is set up from there).
Test Mode: US - hold Start at boot; JP - idol mode 0x8C27E75E = 5 during the attract and the full menu 0x8C283050 =
0x100 (what maintenance code 5-2-0-4-8 sets).  Menu rows: 1P, 2P (NoUse + the others), Round, Stage, PlayMode.
Order: 1P Morrigan with 2P NoUse, Jiki0-5, then 1P NoUse (the 1P list has NoUse after Morrigan: a P2-only game) and
Jiki0-5 with 2P Morrigan.
Screenshots every 20 frames (and the menu before each start) into
stage_endings_verification/dc/<US|JP>/demo_s<stage>_<p1>-<p2>/ (1-based charNo, 7 = Morrigan, 0 = NoUse).
usage: stage_end_dc.py <US|JP> [--window N] [--stages 1-7]"""
import os, sys, subprocess, argparse
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
M = 6
PAIRS = [(M, None)] + [(M, c) for c in range(6)] + [(None, M)] + [(c, M) for c in range(6)]   # (None, M): P2 only
# frames from Start to the return to the menu: DC loading (~180) + the scene (port lengths) + margin
WINDOW = {1: 1000, 2: 1000, 3: 1000, 4: 1000, 5: 1000, 6: 1000, 7: 4400}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reg', choices=['US', 'JP']); ap.add_argument('--stages', default='1-7')
    ap.add_argument('--window', type=int, default=0); ap.add_argument('--pairs', default='')
    a = ap.parse_args()
    s0, s1 = map(int, a.stages.split('-'))
    out = f'{ROOT}/stage_endings_verification/dc/{a.reg}'
    os.makedirs(out, exist_ok=True)
    if a.reg == 'US':
        L = ['5 press Start', '2600 release Start', '2700 tap 6 A']; t = 2800
    else:
        L = [f'{f} poke16 8c27e75e 5' for f in range(1300, 1700)]
        L += [f'{f} poke16 8c283050 100' for f in range(1700, 1780)] + ['1800 tap 6 A']; t = 1900
    def tap(b, n=1):
        nonlocal t
        for _ in range(n): L.append(f'{t} tap 4 {b}'); t += 12
    # from the fresh menu (cursor on 1P, 1P Alucard, 2P NoUse, stage 1) to PlayMode = Stage Demo
    tap('Right', M); tap('Down', 4); tap('Right', 2)                # cursor now on PlayMode
    cur1, cur2, stage = M, None, 1
    pairs = PAIRS if not a.pairs else [PAIRS[int(i)] for i in a.pairs.split(',')]
    def opts(p1): return [None] + [c for c in range(7) if c != p1]
    for p1, p2 in pairs:
        if (p1, p2) != (cur1, cur2):
            tap('Up', 4)                                             # PlayMode -> 1P
            if p1 is None and cur2 is None:                          # 1P NoUse needs a 2P first: 2P -> Jiki0
                tap('Down'); tap('Right'); tap('Up'); cur2 = 0
            o1 = [c for c in list(range(7)) + [None] if c != cur2]   # 1P: Jiki0-6, then NoUse (a P2-only game),
                                                                     # without 2P's current value
            d = (o1.index(p1) - o1.index(cur1)) % len(o1); tap('Right', d); cur1 = p1
            tap('Down')                                              # -> 2P
            o = opts(cur1)
            if cur2 not in o: cur2 = None                            # (never happens with this order)
            d = (o.index(p2) - o.index(cur2)) % len(o); tap('Right', d); cur2 = p2
            tap('Down', 3)                                           # -> PlayMode
        for s in range(s0, s1 + 1):
            if s != stage:
                tap('Up'); tap('Right' if s > stage else 'Left', abs(s - stage)); tap('Down'); stage = s
            d = f'{out}/demo_s{s}_{0 if p1 is None else p1 + 1}-{0 if p2 is None else p2 + 1}'
            os.makedirs(d, exist_ok=True)
            L.append(f'{t + 10} snap {d}/menu.png'); t += 20
            L.append(f'{t} tap 6 Start')
            w = a.window or WINDOW[s]
            L += [f'{t + f} snap {d}/f{f:05d}.png' for f in range(0, w, 20)]
            t += w
    L.append(f'{t + 30} exit')
    open(out + '/t.tl', 'w').write('\n'.join(L) + '\n')
    print(f'{len(pairs) * (s1 - s0 + 1)} scenes, {t} frames')
    lim = max(3600, t // 20 + 600)                                   # Flycast runs at >= ~20 fps here
    r = subprocess.run(['timeout', str(lim + 60), ROOT + '/tools/flycast/run.sh', a.reg, out + '/t.tl'],
                       capture_output=True, text=True,
                       env=dict(os.environ, GB2_FC_INST='80' if a.reg == 'US' else '81', GB2_FC_TIMEOUT=str(lim)))
    open(out + '/log.txt', 'w').write(r.stdout + r.stderr)
    print('flycast exit', r.returncode)


if __name__ == '__main__':
    main()
