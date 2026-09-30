#!/usr/bin/env python3
"""Side-by-side sheets of Morrigan's post-stage scenes: Dreamcast (tools/flycast/stage_end_dc.py) vs the port
(tools/mame/check_stage_end.py demo), one sheet per disc/language and stage, one row per pairing: the distinct frames
of the DC scene (menus, loading and repeats dropped) | the distinct frames of the port scene (GameLoop state 8).
Writes stage_endings_verification/compare/<US|JP>_s<stage>.png and prints frame counts per case.
usage: stage_end_compare.py [--stages 1-6]"""
import os, sys, glob, argparse
import numpy as np
from PIL import Image, ImageDraw
ROOT = os.path.abspath(os.path.dirname(__file__) + '/..')
V = ROOT + '/stage_endings_verification'
PAIRS = ['7-0'] + [f'7-{c}' for c in range(1, 7)] + [f'{c}-7' for c in range(0, 7)]   # 0-7: P2 only
NAMES = {0: 'solo', 1: 'Alucard', 2: 'Marion', 3: 'Valpiro', 4: 'Tavia', 5: 'Hei-Cob', 6: 'Aine', 7: 'Morrigan'}


def distinct(frames, keep):
    out, prev = [], None
    for f in frames:
        a = np.asarray(Image.open(f).convert('RGB').resize((64, 48)), float)
        if not keep(a): prev = None; continue
        if prev is None or np.abs(a - prev).mean() > 4: out.append(f)
        prev = a
    return out


def dc_scene(d):
    fs = sorted(glob.glob(d + '/f*.png'))
    # the DC menu: black with small white text; loading: black; the scene: a full picture
    def keep(a): return a.mean() > 25 and (a > 60).mean() > 0.3
    return distinct(fs, keep)


def port_scene(d):
    st = None; states = {}
    for l in open(d + '.hash'):
        p = l.split(); st = st if st is not None else int(p[0]); states[int(p[0])] = p[5]
    t0 = min(states)
    fs = [f for f in sorted(glob.glob(d + '/f*.png')) if states.get(t0 + int(os.path.basename(f)[1:6]) - 2) == '8'
          or states.get(t0 + int(os.path.basename(f)[1:6])) == '8']
    return distinct(fs, lambda a: a.mean() > 10)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--stages', default='1-6')
    a = ap.parse_args(); s0, s1 = map(int, a.stages.split('-'))
    os.makedirs(V + '/compare', exist_ok=True)
    for reg, lang in (('US', 'EN'), ('JP', 'JP')):
        for s in range(s0, s1 + 1):
            rows = []
            for p in PAIRS:
                dd, pd = f'{V}/dc/{reg}/demo_s{s}_{p}', f'{V}/port/{lang}/demo_s{s}_{p}'
                dc = dc_scene(dd) if os.path.isdir(dd) else []
                pt = port_scene(pd) if os.path.isdir(pd) else []
                rows.append((p, dc, pt))
                print(f'{reg} stage {s} {p:4s}: DC {len(dc):2d} distinct frames, port {len(pt):2d}')
            W1 = max(len(r[1]) for r in rows) * 108 + 8; W2 = max(len(r[2]) for r in rows) * 58
            o = Image.new('RGB', (130 + W1 + W2, 84 * len(rows)), (30, 30, 30)); dr = ImageDraw.Draw(o)
            for y, (p, dc, pt) in enumerate(rows):
                a, b = map(int, p.split('-'))
                dr.text((4, y * 84 + 30), f'1P {NAMES[a] if a else "-"}\n2P {NAMES[b] if b else "-"}', fill='yellow')
                for x, f in enumerate(dc): o.paste(Image.open(f).convert('RGB').resize((106, 80)), (130 + x * 108, y * 84))
                for x, f in enumerate(pt): o.paste(Image.open(f).convert('RGB').resize((56, 80)), (130 + W1 + x * 58, y * 84))
            o.save(f'{V}/compare/{reg}_s{s}.png')
    print('sheets in', V + '/compare')


if __name__ == '__main__':
    main()
