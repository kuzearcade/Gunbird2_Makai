#!/usr/bin/env python3
"""Morrigan's sounds on the patched set (gunbird2m), three checks:

moves  Each game situation with her sounds, set up directly: bomb (chardef +0x78), charged shot at gauge levels 1-3
       (+0x84; the level is the charge gauge player +0x74 against +0x7C/+0x7E/+0x80, not the hold time), button 3
       (+0x80) and its hits (her 0x84), the select screen, a death and a continue.  Pass = every expected ID plays;
       together they cover all 20 of her IDs (DC 0x150-0x162, 0x84 -> arcade 0x16A-0x17D).
play   Every sound-effect start during gameplay with her (timeline 'sndtrace'): a whole game 1P (Stage Select 'stage
       7, round 2, Full Play': both loops, invincible, shot held with releases for charge attacks, bombs, button 3),
       2P with her on either side, and mortal Stage Select plays.  Pass = no ID that belongs to another character
       (DC SE table 0x8C08D57C: player-bank sample, character mask without her bit; the DC resolves those through the
       players' banks, so they never sound for her) is played in a run where only she is a player character.
listen Each of her IDs (and the shared IDs her scripts use) requested one at a time in a silenced game (sound request
       0x06079E04 = id + 1, music channels cleared) with -wavwrite; the recording is cross-correlated with the reference
       sample: the DC's (decoded from MAIN_O.OSB / P6_O.OSB, at the DC's pitch) for her IDs, the original arcade ROM's
       for the shared ones, both below 5 kHz.  Pass = normalised correlation >= 0.85 (content and pitch; an untouched
       original arcade sample scores 0.89-1.00) and her 8-bit waves not clipped (<= 1% of samples at full scale).
usage: check_sound.py [moves|play|listen|all] [--jobs N] [--frames N]"""
import os, sys, re, json, struct, wave, shutil, zipfile, argparse, subprocess, tempfile, collections
from concurrent.futures import ThreadPoolExecutor
import numpy as np
ROOT = os.path.abspath(os.path.dirname(__file__) + '/../..')
sys.path.insert(0, ROOT + '/tools'); sys.path.insert(0, ROOT + '/tools/mame')
from sndcov import play_inputs
MORRIGAN = 6
REMAP = {int(k, 16): v for k, v in json.load(open(ROOT + '/out/snd/remap.json')).items()}
HER = {v: k for k, v in REMAP.items()}                  # arcade id -> DC id
SHARED = [0x0A, 0x0E, 0x0F, 0x12, 0x1B, 0x24, 0x31, 0x3B, 0x59, 0x5A, 0x5B, 0x6C, 0x81]   # Effect ids in her DC scripts
PS5_RATE = 28636363 / 33868800


def dc_table():
    """DC SE table: id -> (bank, index, mask); bank 1 = the players' banks"""
    import port_sound as S
    b = open(ROOT + '/re/1st_read_US.bin', 'rb').read()
    return {i: struct.unpack('<3h', b[S.DC_SE - S.DC_BASE + 6 * i:S.DC_SE - S.DC_BASE + 6 * i + 6]) for i in range(0x200)}


def mame(tl_lines, tag, work, extra=()):
    open(f'{work}/{tag}.tl', 'w').write('\n'.join(tl_lines) + '\n')
    nv = f'{work}/nv_{tag}/gunbird2m'; os.makedirs(nv, exist_ok=True)
    shutil.copy(ROOT + '/out/tmp/eeprom_morrigan.bin', nv + '/eeprom')
    r = subprocess.run([ROOT + '/tools/mame/run.sh', ROOT + '/out/roms', f'{work}/{tag}.tl', *extra],
                       capture_output=True, text=True, env=dict(os.environ, GB2_NVRAM=os.path.dirname(nv), GB2_SET='gunbird2m'))
    open(f'{work}/{tag}.log', 'w').write(r.stdout + r.stderr)
    return r.stdout


# ---- play ------------------------------------------------------------------------------------------------------
def play_timeline(case, frames):
    """case: 'm' (1P whole game), 'm-<c>' / '<c>-m' (2P whole game, c = 1-based partner), 'd<stage>' (1P mortal)"""
    mortal = case.startswith('d')
    if mortal: args = [case[1:], str(MORRIGAN)]
    elif case == 'm': args = ['7', str(MORRIGAN), '2']
    elif case.startswith('m-'): args = ['7', str(MORRIGAN), '2', '--p2', str(int(case[2:]) - 1)]
    else: args = ['7', str(int(case.split('-')[0]) - 1), '2', '--p2', str(MORRIGAN)]
    lines = subprocess.run([sys.executable, ROOT + '/tools/mame/mkstage.py'] + args + ([] if mortal else ['--mode', '1']),
                           capture_output=True, text=True).stdout.splitlines()
    st = int(next(l.split()[-1] for l in lines if 'START' in l))
    L = [l for l in lines if not l.startswith('#')] + [f'{st} sndtrace']
    if mortal:
        frames = min(frames, 9000)
        L += play_inputs(st + 60, frames)                               # shot/charge, bombs, coin + start = continues
    else:                                                               # invincible, enemies weakened (as check_palette)
        L += [f'{st} weaken 0604c8cc 0605cd6a 0605cd68 10000']
        L += [f'{f} poke8 06040016 01' for f in range(st, st + frames, 60)] + \
             [f'{f} poke8 06040018 01' for f in range(st, st + frames, 60)]
        for who, ph in (('P1', 0), ('P2', 4)):
            for f in range(st + 60 + ph, st + frames, 240):            # hold shot 150 frames, release: charge attack
                L += [f'{f} press {who} Button 1', f'{f + 150} release {who} Button 1']
            L += [f'{f} tap 30 {who} {d}' for f, d in zip(range(st + 60 + ph, st + frames, 120),
                                                         ['Left', 'Up', 'Right', 'Down'] * 9999)]
            L += [f'{f} tap 4 {who} Button 2' for f in range(st + 600 + ph, st + frames, 1080)]
            L += [f'{f} tap 4 {who} Button 3' for f in range(st + 900 + ph, st + frames, 700)]
    L.append(f'{st + frames} exit')
    return sorted(set(L), key=lambda l: int(l.split()[0]) if l[0].isdigit() else -1)


def play(a, work):
    cases = ['m', 'm-2', '2-m', 'm-1', '4-m'] + [f'd{s}' for s in range(1, 8)]
    se = dc_table()
    def run(case):
        out = mame(play_timeline(case, a.frames), 'play_' + case, work)
        return case, [tuple(int(x, 16) if i else int(x) for i, x in enumerate(m)) for m in
                      re.findall(r'^SNDT (\d+) ([0-9a-f]+) ([0-9a-f]+)', out, re.M)]
    seen, fails = collections.Counter(), 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for case, starts in ex.map(run, cases):
            ids = collections.Counter(i for _, _, i in starts)
            seen.update(ids)
            partners = set() if case == 'm' or case.startswith('d') else {int(case.replace('m', '').strip('-')) - 1}
            foreign = {i: n for i, n in ids.items() if i < 0x150 and se[i][0] == 1 and se[i][2] & 0xFF
                       and not se[i][2] & (1 << MORRIGAN) and not any(se[i][2] & (1 << p) for p in partners)}
            hers = {i: n for i, n in ids.items() if i in HER}
            print(f'{case:5s} {len(starts):5d} starts, {len(ids):3d} ids; hers: '
                  + ' '.join(f'{i:x}x{n}' for i, n in sorted(hers.items()))
                  + (f'; OTHER CHARACTERS\' SOUNDS: ' + ' '.join(f'{i:x}x{n}' for i, n in sorted(foreign.items())) if foreign else ''),
                  flush=True)
            fails += bool(foreign)
    missing = [i for i in sorted(HER) if not seen[i]]
    print('her IDs not played in these runs (the situations are set up by \'moves\'): '
          + (' '.join(f'{i:x} (DC {HER[i]:x})' for i in missing) if missing else 'none'))
    return fails


# ---- moves -----------------------------------------------------------------------------------------------------
def moves(a, work):
    """each game situation that plays her sounds, set up directly; expected IDs per situation (DC ids in comments)"""
    fails = 0
    # A: Stage Select stage 1, invincible; charge levels by the gauge (player +0x74; thresholds +0x7C/+0x7E/+0x80)
    base = play_timeline('m', 3000)
    st = int([l for l in base if 'sndtrace' in l][0].split()[0])
    L = [l for l in base if not l[0].isdigit() or int(l.split()[0]) <= st or not ('Button' in l or l.endswith('exit'))]
    L += [f'{f} tap 3 P1 Button 1' for f in range(st + 60, st + 1500, 8)]
    t, cases = st + 1600, []
    for name, gauge, button, exp in (                                   # (chardef +0x78 bomb, +0x80 button 3,
            ('bomb', None, 2, {0x173, 0x17A, 0x17B, 0x17C}),                 # +0x84 charged shot by gauge level)
            ('charge level 1', 1000, 1, {0x170, 0x177}),                     # DC 0x159, 0x160-0x162 | 0x156, 0x15D
            ('charge level 2', 7000, 1, {0x171, 0x178}),                     # DC 0x157, 0x15E
            ('charge level 3', 30000, 1, {0x172, 0x179}),                    # DC 0x158, 0x15F
            ('button 3', 1000, 3, {0x16F, 0x175})):                          # DC 0x155, 0x15B
        if gauge is not None: L.append(f'{t - 5} poke16 06055074 {gauge:04x}')   # charge gauge (player +0x74)
        L += [f'{t} press P1 Button {button}', f'{t + (60 if button == 1 else 30)} release P1 Button {button}']
        cases.append((name, t, exp)); t += 1200
    for k in range(40):                                                  # button 3 attacks that hit: her 0x84
        L += [f'{t - 3} poke16 06055074 03e8', f'{t} tap 4 P1 Button 3']; t += 150
    cases.append(('button 3 hits', t - 6000, {0x17D}))                  # DC 0x84 (her bank's sample)
    L.append(f'{t} exit')
    out = mame(sorted(L, key=lambda l: int(l.split()[0]) if l[0].isdigit() else -1), 'moves_a', work)
    ev = [(int(f), int(i, 16)) for f, _, i in re.findall(r'^SNDT (\d+) ([0-9a-f]+) ([0-9a-f]+)', out, re.M)]
    for name, t0, exp in cases:
        got = {i for f, i in ev if t0 <= f < t0 + (6200 if name == 'button 3 hits' else 1100) and i in HER}
        ok = exp <= got; fails += not ok
        print(f'  {name:15s} expected {" ".join(f"{i:x}" for i in sorted(exp))}; played {" ".join(f"{i:x}" for i in sorted(got)) or "-"} '
              f'{"OK" if ok else "MISSING " + " ".join(f"{i:x}" for i in sorted(exp - got))}', flush=True)
    # B: a normal game - select screen (her voice), no input until her life is gone, continue (her voice again);
    # (a player joining mid-game can only pick charNo 1-5, on the DC too, so she has no join voice)
    from regress_select import GATE
    L = ['60 poke16 06029226 e201', '600 poke16 06029226 e201', '600 tap 5 Coin 1', GATE, '1000 sndtrace']
    t = 1080
    for x in ['Right'] * 4: L.append(f'{t} tap 3 P1 {x}'); t += 10
    t += 20; L.append(f'{t} tap 3 P1 Up'); t += 30
    L.append(f'{t} tap 3 P1 Button 1'); sel = t
    L += [f'{t + 1400} tap 5 Coin 1'] + [f'{f} tap 4 1 Player Start' for f in range(t + 1500, t + 6000, 50)]   # continue
    L.append(f'{t + 9500} exit')
    out = mame(L, 'moves_b', work)
    ev = [(int(f), int(i, 16)) for f, _, i in re.findall(r'^SNDT (\d+) ([0-9a-f]+) ([0-9a-f]+)', out, re.M)]
    at_sel = [f for f, i in ev if i == 0x16A and f <= sel + 60]
    later = [f for f, i in ev if i == 0x16A and f > sel + 60]
    death = [f for f, i in ev if i == 0x16B]
    for name, ok in (('select voice', bool(at_sel)), ('death voice', bool(death)), ('continue voice', bool(later))):
        fails += not ok
        print(f'  {name:15s} {"OK" if ok else "NOT PLAYED"}', flush=True)
    return fails


# ---- listen ----------------------------------------------------------------------------------------------------
def pcm(rom, w):
    """a YMF278B wave header's sample data as float"""
    import port_sound as P
    wv = P.parse(rom)[w]; b = rom[wv['start']:wv['start'] + wv['bytes']]
    if wv['fmt'] == 0: return np.frombuffer(b, np.int8).astype(float) * 256
    if wv['fmt'] == 2: return np.frombuffer(b, '>i2').astype(float)
    b = np.frombuffer(b[:len(b) // 3 * 3], np.uint8).reshape(-1, 3).astype(int)   # 12-bit: 2 samples per 3 bytes
    s = np.stack([(b[:, 0] << 4) | (b[:, 2] >> 4), (b[:, 1] << 4) | (b[:, 2] & 15)], 1).ravel()
    return np.where(s >= 2048, s - 4096, s).astype(float) * 16


def lowpass(y, sr, fc=5000):
    """compare below 5 kHz: the YMF278B's interpolation and a linear resampler differ above that (noise-like and
    high-pitched samples would otherwise score low without anything being wrong)"""
    f = np.fft.rfft(y); f[int(fc * len(y) / sr):] = 0
    return np.fft.irfft(f, len(y))


def listen(a, work):
    import dcsnd, port_sound as P
    from sound_levels import dc_params
    snd_new = open(ROOT + '/out/roms/gunbird2m/sound.u9', 'rb').read()
    snd_old = zipfile.ZipFile(ROOT + '/mame_roms/gunbird2.zip').read('sound.u9')
    prog_new = open(ROOT + '/out/prog_be_patched.bin', 'rb').read()
    prog_old = open(ROOT + '/assets/arcade/prog_be.bin', 'rb').read()
    ids = sorted(HER) + SHARED
    # requests while the (silent) maintenance Stage Select screen is up: no music or game sounds underneath
    lines = subprocess.run([sys.executable, ROOT + '/tools/mame/mkstage.py', '1', str(MORRIGAN)],
                           capture_output=True, text=True).stdout.splitlines()
    st = int(next(l.split()[-1] for l in lines if 'START' in l))
    t0, step = st + 120, 150
    L = [l for l in lines if not l.startswith('#') and 'Player Start' not in l]
    L += [f'{t0 + step * k} poke16 06079E04 {i + 1:04x}' for k, i in enumerate(ids)] + [f'{t0 + step * len(ids) + 200} exit']
    mame(sorted(L, key=lambda l: int(l.split()[0])), 'listen', work, ('-wavwrite', f'{work}/listen.wav'))
    w = wave.open(f'{work}/listen.wav'); sr, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
    x = x[:len(x) // ch * ch].reshape(-1, ch).mean(1)
    banks = {0: dcsnd.bank('MAIN_O.OSB'), 1: dcsnd.bank('P6_O.OSB')}
    se = dc_table()
    def rs(y, rate): n = int(len(y) * sr / rate); return np.interp(np.arange(n) * rate / sr, np.arange(len(y)), y)
    fails = 0
    fps = 60.0                                                             # MAME psikyo5 screen
    for k, i in enumerate(ids):
        note_new = prog_new[0x40300 + 6 * i + 5]
        rate = 22050 * PS5_RATE * 2 ** ((note_new - 60) / 12)             # the port's playback rate
        cents = ''
        if i in HER:                                                       # the DC's sample, at the port's rate
            bk, ix, _ = se[HER[i]]; e = banks[bk][ix]
            p0 = dc_params(bk, ix)[0]
            ref = rs(dcsnd.decode(dict(e, n=e['end'])).astype(float), rate)
            cents = f' pitch vs DC {1200 * np.log2(rate / (22050 * 2 ** (p0 / 1200))):+4.0f} cents'
            what = f'DC {HER[i]:03x}'
        else:                                                              # the original arcade sample and pitch
            wn, note = struct.unpack_from('>H', prog_old, 0x40300 + 6 * i)[0], prog_old[0x40300 + 6 * i + 5]
            ref = rs(pcm(snd_old, wn), 22050 * PS5_RATE * 2 ** ((note - 60) / 12))
            what = 'arcade'
        ref = lowpass(ref[:int(0.4 * sr)], sr)
        t = (t0 + step * k) / fps
        seg = lowpass(x[max(0, int((t - 0.4) * sr)):int((t + 1.6) * sr)], sr)
        n = 1 << int(np.ceil(np.log2(len(seg) + len(ref))))
        c = np.fft.irfft(np.fft.rfft(seg, n) * np.conj(np.fft.rfft(ref, n)), n)[:len(seg) - len(ref) + 1]
        j = int(np.argmax(np.abs(c))); win = seg[j:j + len(ref)]
        ncc = abs(c[j]) / np.sqrt((win ** 2).sum() * (ref ** 2).sum() + 1e-9)
        lvl = 20 * np.log10(np.sqrt((win ** 2).mean()) + 1e-9)
        ent = prog_new[0x40300 + 6 * i:0x40306 + 6 * i]
        wn = (ent[0] << 8) | ent[1]
        clip = (np.abs(pcm(snd_new, wn)) >= 127 * 256).mean() if i in HER else 0.0   # 8-bit full scale
        ok = ncc >= 0.85 and clip <= 0.01; fails += not ok
        print(f'  id {i:03x} ({what:6s}) wave {(ent[0] << 8) | ent[1]:03x} vol {ent[2]:02x} note {ent[5]:02x}: '
              f'correlation {ncc:.2f}, clipped {100 * clip:4.1f}% {"OK " if ok else "BAD"} level {lvl:5.1f} dB{cents}',
              flush=True)
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', nargs='?', default='all', choices=['play', 'listen', 'moves', 'all'])
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument('--frames', type=int, default=76000)
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix='checksnd_'); print('work dir', work, flush=True)
    fails = 0
    if a.what in ('listen', 'all'): print('listen:', flush=True); fails += listen(a, work)
    if a.what in ('moves', 'all'): print('moves:', flush=True); fails += moves(a, work)
    if a.what in ('play', 'all'): print('play:', flush=True); fails += play(a, work)
    print('PASS' if not fails else f'FAIL ({fails})')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
