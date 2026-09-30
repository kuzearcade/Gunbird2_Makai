#!/usr/bin/env python3
"""Morrigan's sounds for the arcade sound ROM (YMF278B, 4 MB, full on the original board).

Space: the waves listed in re/sound_audit.json (tools/sound_audit.py: never played, dropped by the DC port) are
removed and the remaining sample data is compacted (headers keep their wave numbers; only start addresses move;
removed waves point at a short silence).  Morrigan's samples (DC P6_O.OSB #62-#77 and MAIN_O.OSB #152, AICA ADPCM
22050 Hz) are decoded, scaled to the arcade's 8-bit level (DC/64, measured on the samples both versions share; a
sample whose peak would clip at that scale - her voices, recorded hotter on the DC - is scaled down to fit and its SE
volume raised by the same amount) and appended as new waves 0xDA+ (note 0x3F = 22171 Hz on the PS5 clock, see
docs/NOTES.md "Sound").

IDs: the DC gives Morrigan IDs 0x150-0x162 (arcade IDs with other samples) and her own 0x84 (shared with Marion on the
DC via per-player banks); they become free arcade IDs 0x16A+ (SE table ROM 0x40300 + 6*id: wave, volume, 0, group,
note).  Outputs:
  out/snd/sound.u9                  new sound ROM (build.py uses it)
  out/snd/remap.json                DC id -> arcade id (port_morrigan.py remaps Effect operands)
  src/gen_sound.[ch], src/gen_sound_patches.txt   SE entries, Morrigan's voice-table entries (build.py)"""
import os, sys, json, struct, zipfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dcsnd
from gbres import ROOT

HDR_END, ROM_SIZE, FIRST_NEW_WAVE, FIRST_NEW_ID = 0x1800, 0x400000, 0xDA, 0x16A
ENV = bytes.fromhex('00ff100600')                       # LFO/VIB, AR/D1R, DL/D2R, RC/RR, AM of every arcade SE wave
# pitch: octave = note/12 - 5, F-number row 0x10 = equal temperament; the PS5 clocks the YMF278B at 28.636 MHz
# (not 33.8688), so note 0x3C plays at 22050 * 0.8455 = 18643 Hz.  Morrigan's 22050 Hz samples: note 0x3F = 22171 Hz
NOTE = 0x3F
TL_STEP_DB = 0.375                                      # YMF278B total level: 0.375 dB per step (volume = 127 - TL)
DC_SE, DC_GRP, DC_BASE = 0x8C08D57C, 0x8C08E974, 0x8C010000
# DC IDs Morrigan uses (Effect ops in her scripts, voice/shot/item tables) -> (bank file, sample index)
M_IDS = list(range(0x150, 0x163)) + [0x84]
# level: the DC's per-sample level p1 mapped through the DC->arcade mix fit of tools/sound_levels.py
# (re/sound_levels.json); pitch: the DC's per-sample pitch p0 (cents) added to NOTE, rounded to a semitone
LEVELS = json.load(open(ROOT + '/re/sound_levels.json'))


def level_and_note(bank, idx, grp):
    from sound_levels import dc_params
    p0, p1, _ = dc_params(bank, idx)
    k = LEVELS['k_voice'] if grp in (0, 1) else LEVELS['k_sfx']
    tl = (-k - LEVELS["u"] * p1) / TL_STEP_DB
    return max(0, min(127, round(127 - tl))), NOTE + round(p0 / 100)
# arcade channel groups (FUN_0602BE6C: channels 0x0E-0x17 = 5,5,3,3,3,2,2,2,0,0); the player waits forever for a free
# channel of the entry's group, so every entry must use one of them.  DC group 1 (a second voice group) -> 0 (voices)
GROUP = {0: 0, 1: 0, 2: 2, 3: 3, 5: 5}


def parse(rom):
    w = []
    for i in range(384):
        h = rom[12 * i:12 * i + 12]
        start = ((h[0] & 0x3F) << 16) | (h[1] << 8) | h[2]
        n = (((h[5] << 8) | h[6]) ^ 0xFFFF) + 1
        if start == 0 and n == 0x10000: break
        w.append({'fmt': h[0] >> 6, 'start': start, 'n': n, 'h': bytearray(h),
                  'bytes': n * {0: 8, 1: 12, 2: 16}[h[0] >> 6] // 8})
    return w


def header(fmt, start, n, loop, env=ENV):
    end = (n - 1) ^ 0xFFFF
    return bytes([(fmt << 6) | (start >> 16), (start >> 8) & 0xFF, start & 0xFF, loop >> 8, loop & 0xFF,
                  end >> 8, end & 0xFF]) + env


def dc_entry(i):
    b = open(ROOT + '/re/1st_read_US.bin', 'rb').read()
    bk, ix, mask = struct.unpack('<3h', b[DC_SE - DC_BASE + 6 * i:DC_SE - DC_BASE + 6 * i + 6])
    return bk, ix, b[DC_GRP - DC_BASE + i]


def main():
    rom = bytearray(zipfile.ZipFile(ROOT + '/mame_roms/gunbird2.zip').read('sound.u9'))
    waves = parse(rom)
    remove = set(json.load(open(ROOT + '/re/sound_audit.json'))['remove'])
    # ---- compact the kept sample data (clusters of overlapping waves move together) -----------------------
    # the chip reads past a wave's last sample (interpolation / loop wrap), so each wave keeps the bytes that
    # followed it in the original ROM (up to the next wave, at most 16)
    starts = sorted({w['start'] for w in waves})
    def extent(w):
        e = w['start'] + w['bytes']
        nxt = next((s for s in starts if s >= e), ROM_SIZE)
        return e + min(nxt - e, 16)
    kept = sorted((w['start'], extent(w), i) for i, w in enumerate(waves) if i not in remove)
    clusters = []
    for s, e, i in kept:
        if clusters and s < clusters[-1][1]: clusters[-1][1] = max(e, clusters[-1][1]); clusters[-1][2].append(i)
        else: clusters.append([s, e, [i]])
    out = bytearray(rom[:HDR_END]); pos = HDR_END
    for s, e, ids in clusters:
        out += rom[s:e]
        for i in ids:
            w = waves[i]; w['start'] += pos - s
            out[12 * i:12 * i + 3] = bytes([(w['fmt'] << 6) | (w['start'] >> 16), (w['start'] >> 8) & 0xFF,
                                            w['start'] & 0xFF])
        pos += e - s
    silence = pos; out += bytes(4); pos += 4
    for i in remove:
        out[12 * i:12 * i + 12] = header(0, silence, 4, 2)
    freed = ROM_SIZE - pos
    # ---- Morrigan's samples -----------------------------------------------------------------------------
    banks = {0: dcsnd.bank('MAIN_O.OSB'), 1: dcsnd.bank('P6_O.OSB')}
    wave_of, new_waves, gain_of = {}, [], {}
    for dcid in M_IDS:
        bk, ix, grp = dc_entry(dcid)
        e = banks[bk][ix]
        key = (bk, e['start'], e['end'])                 # 0x160-0x162 reuse 0x15A's data (count at +0xA)
        if key not in wave_of:
            assert dcsnd.rate(e['pitch']) == 22050, (hex(dcid), dcsnd.rate(e['pitch']))
            pcm = dcsnd.decode(dict(e, n=e['end'])) / 64.0
            g = min(1.0, 127.0 / max(1.0, np.abs(pcm).max()))  # fit 8 bits; the SE volume makes up for g
            s8 = np.clip(np.round(pcm * g), -128, 127).astype(np.int8).tobytes() + bytes(2)
            wn = FIRST_NEW_WAVE + len(new_waves)
            out[12 * wn:12 * wn + 12] = header(0, pos, len(s8), len(s8) - 2)
            out += s8; pos += len(s8)
            wave_of[key] = wn; new_waves.append((wn, hex(dcid), len(s8))); gain_of[wn] = g
    assert pos <= ROM_SIZE, f'sound ROM overflow by {pos - ROM_SIZE} bytes'
    out += bytes(ROM_SIZE - pos)
    os.makedirs(ROOT + '/out/snd', exist_ok=True)
    open(ROOT + '/out/snd/sound.u9', 'wb').write(out)
    # ---- SE entries + ID remap ------------------------------------------------------------------------------
    remap, pat = {}, ['# generated by tools/port_sound.py - do not edit',
                      '# SE table (ROM 0x40300 + 6*id: wave, volume, 0, group, note) - Morrigan (DC id -> arcade id)']
    for k, dcid in enumerate(M_IDS):
        bk, ix, grp = dc_entry(dcid)
        e = banks[bk][ix]
        aid = FIRST_NEW_ID + k; remap[dcid] = aid
        wn = wave_of[(bk, e['start'], e['end'])]
        vol, note = level_and_note(bk, ix, grp)
        up = round(-20 * np.log10(gain_of[wn]) / TL_STEP_DB)          # the sample was scaled down by gain_of[wn]
        assert vol + up <= 127, (hex(dcid), vol, up)
        vol += up
        ent = struct.pack('>HBBBB', wn, vol, 0, GROUP[grp], note)
        pat.append(f'{0x40300 + 6 * aid:08X} {ent.hex().upper()}      # id {aid:#05x} = DC {dcid:#05x} (wave {wn:#04x}, '
                   f'volume {vol:#04x}, note {note:#04x})')
    pat += ['# voice tables, 1-based charNo (DC 8C087E9C/EAC/EBC have 7 entries; the arcade ones 6, followed by the',
            '# next table: [7] of the first two falls on the unused [0] of the next one, the third is redirected)',
            '06031FAE 005B                      # item voice A tbl 0x06031FA0[7] (DC 0x5B)',
            f'06031FBC {remap[0x152]:04X}                      # item voice B tbl 0x06031FAE[7] (DC 0x152)',
            'sym32 0601760C gb2_voice_item_c    # HitActI literal: item voice C tbl 0x06031FBC -> 8 entries',
            f'06032066 {remap[0x15C]:04X}                      # main-shot sound table 0x06032058[7] (DC 0x15C)',
            f'06032116 {remap[0x150]:04X}                      # select/stage-clear voice 0x0603210A[6] (DC 0x150); was',
            '                                   #   the original select\'s initial P1 slot (select is src/select.c)']
    open(ROOT + '/src/gen_sound_patches.txt', 'w').write('\n'.join(pat) + '\n')
    c = ['/* generated by tools/port_sound.py - do not edit */', '#include "arcade.h"', '',
         '/* HitActI item voice C by charNo (arcade 0x06031FBC[1..6] + Morrigan, DC 8C087EBC) */',
         'const u16 gb2_voice_item_c[8] = {0x0000, 0x0011, 0x0009, 0x001A, 0x0023, 0x0030, 0x003C, '
         f'0x{remap[0x153]:04X}}};']
    open(ROOT + '/src/gen_sound.c', 'w').write('\n'.join(c) + '\n')
    h = ['/* generated by tools/port_sound.py - do not edit */', '#ifndef GEN_SOUND_H', '#define GEN_SOUND_H',
         '/* Morrigan\'s sound-effect IDs: SND_M(dc id) (the DC numbers, remapped to free arcade IDs) */']
    h += [f'#define SND_M_{dcid:03X} 0x{aid:03X}' for dcid, aid in remap.items()]
    h += ['#define SND_M(x) SND_M_##x', '#endif']
    open(ROOT + '/src/gen_sound.h', 'w').write('\n'.join(h) + '\n')
    json.dump({f'{k:#x}': v for k, v in remap.items()}, open(ROOT + '/out/snd/remap.json', 'w'), indent=0)
    used = sum(n for _, _, n in new_waves)
    print(f'removed {len(remove)} waves, freed {freed} bytes; Morrigan {len(new_waves)} waves {used} bytes; '
          f'{ROM_SIZE - pos} bytes free')


if __name__ == '__main__':
    main()
