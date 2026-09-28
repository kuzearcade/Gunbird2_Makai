#!/usr/bin/env python3
"""Build analysis images from gunbird2.zip into assets/arcade/.
prog_be.bin  : 1 MB program, big-endian as the SH-2 sees it (addr 0x00000000)
pdata_be.bin : 512 KB data ROM, big-endian (addr 0x05000000)
gfx.bin      : 0x3800000 gfx region, same layout as MAME's "gfx" region
sound.bin    : YMF278B ROM"""
import zipfile, sys, os
root = os.path.dirname(os.path.abspath(__file__)) + '/..'
z = zipfile.ZipFile(sys.argv[1] if len(sys.argv) > 1 else root + '/mame_roms/gunbird2.zip')
r = lambda n: z.read(n)
out = root + '/assets/arcade/'
os.makedirs(out, exist_ok=True)
# ROM_LOAD32_WORD_SWAP: h at +0, l at +2, each word byteswapped relative to file => file words are LE
H, L = r('1_prog_h.u17'), r('2_prog_l.u16')
p = bytearray(0x100000)
for i in range(0, 0x80000, 2):
    p[2*i:2*i+2] = H[i+1:i+2] + H[i:i+1]
    p[2*i+2:2*i+4] = L[i+1:i+2] + L[i:i+1]
open(out + 'prog_be.bin', 'wb').write(p)
d = bytearray(r('3_pdata.u1'))
d[0::2], d[1::2] = d[1::2], d[0::2]
open(out + 'pdata_be.bin', 'wb').write(d)
g = bytearray()
for lo, hi in [('0l.u3','0h.u10'),('1l.u4','1h.u11'),('2l.u5','2h.u12'),('3l.u6','3h.u13')]:
    A, B = r(lo), r(hi); o = bytearray(len(A)*2)
    for i in range(0, len(A), 2):
        o[2*i:2*i+2] = A[i:i+2]; o[2*i+2:2*i+4] = B[i:i+2]
    g += o
open(out + 'gfx.bin', 'wb').write(g)
open(out + 'sound.bin', 'wb').write(r('sound.u9'))
print('ok', hex(len(p)), hex(len(d)), hex(len(g)))
