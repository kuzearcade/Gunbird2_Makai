#!/usr/bin/env python3
"""Dreamcast reference (Flycast, US v1.000, ARCADE mode) vs arcade port (MAME, gunbird2m): Morrigan's speed, hitbox,
damage and time-to-kill from per-frame traces (tools/flycast/timeline.lua / tools/mame/timeline.lua 'trace').

Both runs: stage 1, Morrigan, player invincible (debug flag: DC 0x8C1A8BF2, arcade 0x06040016).
  DC: title -> ARCADE -> GAME START; select: 1P cursor set to Morrigan's slot (the DC only offers her once
      unlocked); fire = A, bomb = B.
  arcade: maintenance Stage Select, 1P Jiki6 (tools/mame/mkstage.py); fire = Button 1, bomb = Button 2.
Trace line: F <frame> <x 16.16> <y 16.16> P <player hit rects> T <task>:<hp 16.16>:<type> ...
Scenarios (the action starts at 'go' = first frame the player's hit rects exist + 60):
  speed   hold Right/Left/Up/Down 40 frames each, then the same with fire held (charging)
  shot    tap fire (3 on / 3 off) for N frames, standing still
  charge  hold fire 150 frames, release, 60 frames, repeated
  bomb    tap bomb every 400 frames, tap fire in between
Report: out/trace_compare/report.md (+ the traces).
usage: trace_compare.py [--scen speed,shot,charge,bomb] [--frames N] [--analyze-only]"""
import os, sys, json, subprocess, argparse, collections, statistics
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.dirname(__file__) + '/..')
OUT = ROOT + '/out/trace_compare'
MAP = {int(k, 16): int(v[0], 16) for k, v in json.load(open(ROOT + '/re/map_dc2arc.json')).items()}
EEP = ROOT + '/out/tmp/eeprom_morrigan.bin'          # Morrigan-enabled arcade EEPROM (maintenance code applied)

DC = dict(px=0x8C27E124, phit=0x8C27E126, objs=0x8C2759E0, lst=0x8C2863DE, cnt=0x8C2863DC, inv=0x8C1A8BF2,
          fire='A', bomb='B', L='Left', R='Right', U='Up', D='Down')
AR = dict(px=0x06055010, phit=0x06055010, objs=0x0604C8CC, lst=0x0605CD6A, cnt=0x0605CD68, inv=0x06040016,
          fire='P1 Button 1', bomb='P1 Button 2', L='P1 Left', R='P1 Right', U='P1 Up', D='P1 Down')
DC_NAV = ['2200 tap 6 Start', '2400 tap 6 Start', '2600 tap 6 Down', '2640 tap 6 Down', '2700 tap 6 Start',
          '2900 tap 6 A',
          # character select: wait for its countdown (u16 on the stack, 900 -> 0; boot/load times vary), then put
          # the 1P cursor (0x8C00F38C) on slot 6 = Morrigan - the DC only offers her once unlocked - and confirm;
          # the select's own exit path then loads JIKI6 and calls PlayerSet(0, 7)
          '2950 timer 8c00f38a 352 384'] + [f'{f} poke16 8c00f38c 6' for f in range(2990, 3011, 2)] + ['3012 tap 6 A']
DC_START = 3250                                        # stage 1 is running (after 'Now Loading'; + gate shift)


def actions(m, scen, t0, n):
    """input lines for scenario scen starting at frame t0 (machine m: DC or AR)"""
    ev, t = [], t0
    if scen == 'speed':
        for held in (False, True):
            if held: ev.append(f'{t} press {m["fire"]}'); t += 20
            for d in 'RLUD':
                ev.append(f'{t} press {m[d]}'); ev.append(f'{t + 40} release {m[d]}'); t += 60
            if held: ev.append(f'{t} release {m["fire"]}'); t += 20
    elif scen == 'shot':
        ev += [f'{f} tap 3 {m["fire"]}' for f in range(t, t + n, 6)]; t += n
    elif scen == 'charge':
        while t < t0 + n:
            ev += [f'{t} press {m["fire"]}', f'{t + 150} release {m["fire"]}']; t += 210
    elif scen == 'bomb':
        k = 0
        while t < t0 + n:
            if k % 67 == 20: ev.append(f'{t} tap 6 {m["bomb"]}')
            else: ev.append(f'{t} tap 3 {m["fire"]}')
            t += 6; k += 1
    return ev, t


def dc_trace_ok(tr, end):
    """the run reached stage 1 as Morrigan: player hit rects from within 400 frames of the trace start, covering the
    scenario (frame numbers include the select gate's shift)"""
    fr = [l.split(None, 2) for l in open(tr)]
    if not fr: return False
    t0 = int(fr[0][1]); have = [int(f[1]) for f in fr if len(f) > 2 and 'P -' in f[2]]
    return bool(have) and have[0] < t0 + 400 and len(have) > (end - DC_START - 400) * 0.9


def run_dc(scen, n):
    tl = f'{OUT}/dc_{scen}.tl'; tr = f'{OUT}/dc_{scen}.txt'
    ev, end = actions(DC, scen, DC_START + 100, n)
    lines = DC_NAV + [f'{DC_START} trace {tr} {DC["px"]:x} {DC["phit"]:x} {DC["objs"]:x} {DC["lst"]:x} {DC["cnt"]:x}']
    lines += [f'{f} poke16 {DC["inv"]:x} 1' for f in range(DC_START, end + 30, 30)] + ev + [f'{end + 30} exit']
    lines += [f'{DC_START + 400} snap {OUT}/dc_{scen}.png']
    open(tl, 'w').write('\n'.join(lines) + '\n')
    for _ in range(3):                                  # Flycast sometimes hangs while the disc boots: retry
        if os.path.exists(tr): os.remove(tr)
        pr = subprocess.Popen([ROOT + '/tools/flycast/run.sh', 'US', tl], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, env=dict(os.environ, GB2_FC_INST=scen), start_new_session=True)
        try: pr.wait(timeout=(end + 600) / 60 * 1.5 + 60)
        except subprocess.TimeoutExpired:
            os.killpg(pr.pid, 9); pr.wait()
        if os.path.exists(tr) and dc_trace_ok(tr, end): return tr
    raise RuntimeError(f'DC run {scen} failed')


def run_ar(scen, n):
    tl = f'{OUT}/ar_{scen}.tl'; tr = f'{OUT}/ar_{scen}.txt'
    out = subprocess.run([sys.executable, ROOT + '/tools/mame/mkstage.py', '1', '6'], capture_output=True,
                         text=True).stdout.splitlines()
    st = int(next(l.split()[-1] for l in out if 'START' in l))
    ev, end = actions(AR, scen, st + 200 + int(os.environ.get('GB2_GO_SHIFT', 0)), n)   # shift: noise estimate
    lines = [l for l in out if not l.startswith('#')]
    lines += [f'{st} trace {tr} {AR["px"]:x} {AR["phit"]:x} {AR["objs"]:x} {AR["lst"]:x} {AR["cnt"]:x}']
    lines += [f'{f} poke16 {AR["inv"]:x} 1' for f in range(st, end + 30, 30)] + ev + [f'{end + 30} exit']
    open(tl, 'w').write('\n'.join(lines) + '\n')
    nv = f'{OUT}/nv_{scen}/gunbird2m'; os.makedirs(nv, exist_ok=True)
    subprocess.run(['cp', EEP, nv + '/eeprom'])
    subprocess.run([ROOT + '/tools/mame/run.sh', ROOT + '/out/roms', tl], capture_output=True,
                   env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2m'))
    return tr


# ---- analysis ------------------------------------------------------------------------------------------------
def parse(fn, dc):
    frames = []
    for line in open(fn):
        t = line.split()
        f = dict(fr=int(t[1]), x=int(t[2]) / 65536, y=int(t[3]) / 65536, rects=[], tasks={},
                 lv=(int(t[5]), int(t[6])) if len(t) > 6 and t[4] == 'L' else None)
        i = t.index('P') + 1
        while i < len(t) and t[i] != 'T': f['rects'].append(t[i]); i += 1
        while i < len(t):
            task, hp, ty = t[i + 1].split(':'); ty = int(ty, 16)
            f['tasks'][task] = (int(hp) / 65536, MAP.get(ty, ty) if dc else ty); i += 2
        frames.append(f)
    start = next(k for k, f in enumerate(frames) if f['rects'])
    return frames[start:]


def speeds(frames):
    """runs of constant per-frame motion: (dx, dy) -> number of frames"""
    c = collections.Counter()
    for a, b in zip(frames, frames[1:]):
        d = (round(b['x'] - a['x'], 4), round(b['y'] - a['y'], 4))
        if d != (0, 0): c[d] += 1
    return c


def damage(frames):
    """per-hit HP decrements, and per-task (type, max HP, frames from first damage to disappearance)"""
    dec, life, prev = collections.Counter(), {}, {}
    for f in frames:
        for task, (hp, ty) in f['tasks'].items():
            L = life.setdefault(task, dict(ty=ty, hp0=hp, first=None, last=f['fr'], seen=f['fr']))
            if task in prev and hp < prev[task]:
                dec[round(prev[task] - hp, 3)] += 1
                if L['first'] is None: L['first'] = f['fr']
            L['last'] = f['fr']; prev[task] = hp
    ttk = [(L['ty'], L['hp0'], L['last'] - L['first'] + 1) for L in life.values() if L['first'] is not None]
    return dec, ttk


def analyze(scens):
    rep = ['# Morrigan: Dreamcast (Flycast, US v1.000 ARCADE mode) vs arcade port (MAME gunbird2m)', '']
    for scen in scens:
        d = parse(f'{OUT}/dc_{scen}.txt', True); a = parse(f'{OUT}/ar_{scen}.txt', False)
        rep += [f'## {scen}', '']
        hb = lambda fr: collections.Counter(' '.join(f['rects']) for f in fr if f['rects'])
        rep.append(f'- hitbox rects (x,y,w,h) DC {dict(hb(d))} | arcade {dict(hb(a))}')
        if scen == 'speed':
            sd, sa = speeds(d), speeds(a)
            keys = sorted(set(sd) | set(sa), key=lambda k: -(sd[k] + sa[k]))[:10]
            rep.append('- movement per frame (dx, dy): frames DC / arcade')
            rep += [f'  - {k}: {sd[k]} / {sa[k]}' for k in keys]
        else:
            dd, td = damage(d); da, ta = damage(a)
            vals = sorted(set(dd) | set(da))
            rep.append(f'- hit events DC {sum(dd.values())} / arcade {sum(da.values())}; total damage DC '
                       f'{sum(k * v for k, v in dd.items()):.1f} / arcade {sum(k * v for k, v in da.items()):.1f}')
            rep.append('- per-hit damage (HP): count DC / arcade')
            rep += [f'  - {v}: {dd[v]} / {da[v]}' for v in vals]
            big = lambda tt: sorted([x for x in tt if x[1] >= 10], key=lambda x: (x[1], x[2]))
            rep.append('- time to kill, enemies with >= 10 HP (type, max HP, frames first hit -> gone): DC | arcade')
            bd, ba = big(td), big(ta)
            for k in range(max(len(bd), len(ba))):
                x = bd[k] if k < len(bd) else None; y = ba[k] if k < len(ba) else None
                f = lambda v: f'{v[0]:x} {v[1]:.0f}HP {v[2]}f' if v else '-'
                rep.append(f'  - {f(x)} | {f(y)}')
        rep.append('')
    open(f'{OUT}/report.md', 'w').write('\n'.join(rep) + '\n')
    print('\n'.join(rep))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scen', default='speed,shot,charge,bomb'); ap.add_argument('--frames', type=int, default=3600)
    ap.add_argument('--analyze-only', action='store_true')
    ap.add_argument('--arcade-only', action='store_true', help='rerun only the arcade side (DC traces kept)')
    a = ap.parse_args(); scens = a.scen.split(','); os.makedirs(OUT, exist_ok=True)
    if not a.analyze_only:
        with ThreadPoolExecutor(8) as ex:              # arcade runs in parallel; DC runs one at a time (a slower
            jobs = [ex.submit(run_ar, s, a.frames) for s in scens]      # boot misses the frame-timed menu inputs)
            if not a.arcade_only:
                for s in scens: run_dc(s, a.frames)
            for j in jobs: j.result()
    analyze(scens)


if __name__ == '__main__':
    main()
