#!/usr/bin/env python3
"""Fit the Dreamcast sound mix to the arcade one, for setting the arcade volume of DC-only (Morrigan) sounds.

DC per-sample parameters (0x8C08E1F4 + idx*6 + bank*0x3C0): p0 = pitch (Katana command 0x18, cents, +-6399),
p1 = level (command 0x15, steps), p2 = priority.  Arcade: level register TL = 127 - volume, 0.375 dB/step.
For every effect ID both versions play (DC sample decoded, /64 = arcade 8-bit scale) loudness is the RMS of the
loudest 100 ms.  k = arcade dB - DC dB, with DC dB = sample dB + u*p1; u is chosen where k varies least over the
effects (same samples on both machines), and k is taken per class (voices = group 0: the DC re-recorded them, so
only the class median is meaningful; effects = other groups).  A DC-only sound then gets
    TL = (-k - u*p1) / 0.375   (its arcade sample = DC sample / 64, so the sample terms cancel).
Writes re/sound_levels.json {u, k_voice, k_sfx, spread_sfx, n}.
usage: sound_levels.py"""
import os, sys, json, struct
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dcsnd, sound_audit as S
from gbres import ROOT

DC_PRM, DC_BASE = 0x8C08E1F4, 0x8C010000
CHAR_BANK = {1: 'P0_O.OSB', 2: 'P1_O.OSB', 4: 'P2_O.OSB', 8: 'P3_O.OSB', 16: 'P4_O.OSB', 32: 'P5_O.OSB'}
_B = None


def dc_params(bank, idx):
    global _B
    _B = _B or open(ROOT + '/re/1st_read_US.bin', 'rb').read()
    a = DC_PRM + idx * 6 + bank * 0x3C0 - DC_BASE
    return struct.unpack('<3h', _B[a:a + 6])


def loud_db(x):
    n = max(1, min(len(x), 2205))
    return 10 * np.log10(np.convolve(x * x, np.ones(n) / n, 'valid').max() + 1e-9)


def rows():
    used = set(json.load(open(ROOT + '/re/sound_audit.json'))['used_ids'])
    b = open(ROOT + '/re/1st_read_US.bin', 'rb').read()
    banks, out = {}, []
    for i in range(1, 0x150):
        bk, ix, m = struct.unpack('<3h', b[S.DC_SE - DC_BASE + 6 * i:S.DC_SE - DC_BASE + 6 * i + 6])
        fn = 'MAIN_O.OSB' if bk == 0 else CHAR_BANK.get(m) if bk == 1 else None
        if i not in used or not fn: continue
        bank = banks.setdefault(fn, dcsnd.bank(fn))
        if ix >= len(bank) or bank[ix]['fmt'] != 1: continue
        e, a = bank[ix], S.se(i)
        w = S.wave(a['wave'])
        if w['fmt'] != 0: continue
        dc = dcsnd.decode(dict(e, n=e['end'])).astype(float) / 64
        arc = np.frombuffer(S.SND[w['start']:w['start'] + w['n']], np.int8).astype(float)
        out.append(dict(id=i, grp=a['grp'], vol=a['vol'], p1=dc_params(bk, ix)[1], dc=loud_db(dc), arc=loud_db(arc)))
    return out


def main():
    r = rows()
    k = lambda u, sel: np.array([x['arc'] - 0.375 * (127 - x['vol']) - (x['dc'] + u * x['p1']) for x in r if sel(x)])
    sfx, voice = (lambda x: x['grp'] != 0), (lambda x: x['grp'] == 0)
    u = float(min(np.arange(0.5, 1.31, 0.05), key=lambda u: np.std(k(u, sfx))))
    res = dict(u=round(u, 2), k_voice=round(float(np.median(k(u, voice))), 2), k_sfx=round(float(np.median(k(u, sfx))), 2),
               spread_sfx=round(float(np.std(k(u, sfx))), 2), n=len(r))
    json.dump(res, open(ROOT + '/re/sound_levels.json', 'w'), indent=0)
    print(res)


if __name__ == '__main__':
    main()
