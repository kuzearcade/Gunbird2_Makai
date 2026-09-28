#!/usr/bin/env python3
"""Dreamcast sound banks (SOSB .OSB): 'SOSB', u32 1, u32 size, u32 count, u32 offsets[count] -> 0x38-byte 'SOSP'
entries: +4 u8 start bits 16-23, +5 u8 format (1 = AICA ADPCM), +6 u16 start bits 0-15 (file offset of the data),
+8 u16 loop start, +10 u16 loop end, +0x10 u16 AICA pitch (OCT 14-11 signed, FNS 9-0), +0x30 u32 sample count.
usage: dcsnd.py <file.OSB> <index> out.wav"""
import os, struct, sys, wave
import numpy as np
ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
STEP = [0x0E6, 0x0E6, 0x0E6, 0x0E6, 0x133, 0x199, 0x200, 0x266]


def bank(fn, reg='US'):
    x = open(f'{ROOT}/assets/dc/{reg}/fs/{fn}', 'rb').read()
    n = struct.unpack('<I', x[12:16])[0]
    offs = struct.unpack(f'<{n}I', x[16:16 + 4 * n])
    out = []
    for o in offs:
        e = x[o:o + 0x38]
        start = (e[4] << 16) | struct.unpack('<H', e[6:8])[0]
        pitch = struct.unpack('<H', e[0x10:0x12])[0]
        out.append(dict(start=start, fmt=e[5], loop=struct.unpack('<H', e[8:10])[0],
                        end=struct.unpack('<H', e[10:12])[0], pitch=pitch, n=struct.unpack('<I', e[0x30:0x34])[0],
                        file=x))
    return out


def rate(pitch):
    oct_ = (pitch >> 11) & 15
    if oct_ & 8: oct_ -= 16
    return 44100 * 2.0 ** oct_ * (1 + (pitch & 0x3FF) / 1024)


def decode(e):
    """AICA ADPCM (low nibble first) -> int16 array"""
    d, n = e['file'][e['start']:], e['n']
    out = np.empty(n, np.int32); s, step = 0, 0x7F
    for i in range(n):
        b = d[i >> 1]; q = (b >> 4) if i & 1 else (b & 15)
        diff = (((q & 7) * 2 + 1) * step) >> 3
        s = s - diff if q & 8 else s + diff
        s = max(-32768, min(32767, s))
        step = max(0x7F, min(0x6000, (step * STEP[q & 7]) >> 8))
        out[i] = s
    return out.astype(np.int16)


if __name__ == '__main__':
    e = bank(sys.argv[1])[int(sys.argv[2])]
    pcm = decode(e)
    w = wave.open(sys.argv[3], 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(rate(e['pitch'])))
    w.writeframes(pcm.tobytes()); w.close()
