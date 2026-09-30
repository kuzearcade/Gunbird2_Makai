#!/usr/bin/env python3
"""Build patched Gunbird 2 ROMs.

  1. compile src/*.c (sh2-cc) and src/*.s (sh-as), link with src/gb2.ld into ROM free space
  2. apply trampolines (src/hooks.txt: '<arcade RAM function addr> <symbol>') and raw patches
     (src/patches.txt: '<addr> <hex bytes>' ; addr may be RAM-code 0x06xxxxxx or ROM 0x000xxxxx or data 0x0508xxxx/0x0608xxxx)
  3. merge extra resource blobs (out/res/*.bin with .json placement) - later milestones
  4. split into chip images (same names as MAME set) under out/roms/<set>/ and fix nothing else yet

usage: build.py [--set gunbird2] [--no-compile]
"""
import numpy as np
import os, sys, struct, subprocess, glob, json, zipfile, hashlib, zlib, argparse

ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
BIN = ROOT + '/tools/bin'
SRC = ROOT + '/src'
OUT = ROOT + '/out'
P_BASE_ROM, P_BASE_RAM, P_LEN = 0x780, 0x06000000, 0x2DCDC
D_BASE_ROM, D_BASE_RAM, D_LEN = 0x2E47C, 0x0602DCDC, 0x4A61


def ram2rom(a):
    if P_BASE_RAM <= a < P_BASE_RAM + P_LEN: return a - P_BASE_RAM + P_BASE_ROM
    if D_BASE_RAM <= a < D_BASE_RAM + D_LEN: return a - D_BASE_RAM + D_BASE_ROM
    raise ValueError(f'{a:08x} is not in a ROM-backed RAM section')


class Image:
    def __init__(self):
        self.prog = bytearray(open(ROOT + '/assets/arcade/prog_be.bin', 'rb').read())
        self.data = bytearray(open(ROOT + '/assets/arcade/pdata_be.bin', 'rb').read())
        self.touched = []

    def write(self, a, b, what=''):
        """write bytes at a CPU address (RAM code/data copy, ROM, or data ROM)"""
        if a < 0x100000:
            buf, o = self.prog, a
        elif 0x05000000 <= a < 0x05080000:
            buf, o = self.data, a - 0x05000000
        elif 0x06080000 <= a < 0x06100000 or 0x26080000 <= a < 0x26100000:
            buf, o = self.data, (a & 0x0FFFFFFF) - 0x06080000
        else:
            buf, o = self.prog, ram2rom(a)
        buf[o:o + len(b)] = b
        self.touched.append((a, len(b), what))


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr); sys.exit(f'failed: {cmd}')
    return r.stdout


def compile_and_link():
    os.makedirs(OUT + '/obj', exist_ok=True)
    objs = []
    for c in sorted(glob.glob(SRC + '/*.c')):
        o = OUT + '/obj/' + os.path.basename(c)[:-2] + '.o'
        run(f'{BIN}/sh2-cc {c} -o {o} -I{SRC}')
        objs.append(o)
    for s in sorted(glob.glob(SRC + '/*.s')):
        o = OUT + '/obj/' + os.path.basename(s)[:-2] + '.S.o'
        run(f'{BIN}/sh-as -big --isa=sh2 {s} -o {o}')
        objs.append(o)
    if not objs: return None, {}
    elf = OUT + '/obj/patch.elf'
    run(f'{BIN}/sh-ld -EB -L {SRC} -T {SRC}/gb2.ld -Map {OUT}/obj/patch.map -o {elf} ' + ' '.join(objs))
    syms = {}
    for line in run(f'{BIN}/sh-nm {elf}').splitlines():
        p = line.split()
        if len(p) == 3: syms[p[2]] = int(p[0], 16)
    return elf, syms


def load_sections(img, elf):
    """copy allocated sections into the image at their load addresses"""
    out = run(f'{BIN}/sh-objdump -h {elf}')
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 7 and p[0].isdigit():
            name, size, vma, lma = p[1], int(p[2], 16), int(p[3], 16), int(p[4], 16)
            if size == 0 or name.startswith('.bss') or name.startswith('.comment'): continue
            run(f'{BIN}/sh-objcopy -O binary --only-section={name} {elf} {OUT}/obj/sec.bin')
            b = open(OUT + '/obj/sec.bin', 'rb').read()
            img.write(lma, b, name)
            print(f'  section {name:10} lma {lma:08x} size {size:#x}')


def trampoline(a, target):
    """jump from arcade function entry a to target (clobbers r0)"""
    if a % 4 == 0:
        return bytes.fromhex('d001402b00090009') + struct.pack('>I', target)
    return bytes.fromhex('d001402b0009') + struct.pack('>I', target)


def gfx_image(setname='gunbird2'):
    """the whole gfx ROM image (MAME region order) with out/gfx/place.json applied, padded to the set's size"""
    limit = 0x4000000 if setname == 'gunbird2m' else 0x3800000
    g = bytearray(open(ROOT + '/assets/arcade/gfx.bin', 'rb').read())
    pj = OUT + '/gfx/place.json'
    for off, f in (json.load(open(pj)).items() if os.path.exists(pj) else ()):
        b = open(OUT + '/gfx/' + f, 'rb').read(); o = int(off, 16)
        if o + len(b) > limit: sys.exit(f'gfx {f} @ {o:#x} exceeds the {setname} gfx space ({limit:#x})')
        if o + len(b) > len(g): g += b'\0' * (o + len(b) - len(g))
        g[o:o + len(b)] = b
        print(f'  gfx {f} @ {o:#x} ({len(b):#x} bytes)')
    if len(g) < limit: g += b'\0' * (limit - len(g))
    return g


def rom_checksums(img, g, snd, setname):
    """ROM test (0x0602D370, results 0x0602D558 'CHARn' / 'SOUND'): records at data-ROM header[12] (CHECKSUM
    section), 8 bytes each: {u16 count, u16 lo, u16 hi, u16 lo + hi}; count = 128 KB gfx banks read through the
    0x24060000 window (the CPU sees each gfx u32 byte-reversed: sums of the low / high halfwords of the little-endian
    u32s), 0x8000 = sound ROM (byte sum via the YMF278B, only the last word checked), 0 = end.  Stock: CHAR0-2 0x80
    banks, CHAR3 0x40 (56 MB); gunbird2m: CHAR3 0x80 (64M EPROM pair).  Verified: reproduces the stock values."""
    a = struct.unpack('>I', bytes(img.data[0x40:0x44]))[0] - 0x26080000
    off = 0
    for i in range(16):
        r = a + 8 * i
        cnt = struct.unpack('>H', bytes(img.data[r:r + 2]))[0]
        if cnt == 0: break
        if cnt & 0x8000:
            s = int(np.frombuffer(snd, np.uint8).sum(dtype=np.uint64)) & 0xFFFF
            img.data[r + 2:r + 8] = struct.pack('>3H', 0, 0, s)
            print(f'  ROM test SOUND sum {s:04x}')
            continue
        if i == 3: cnt = (len(g) - off) // 0x20000                # last gfx record: to the end of the set's gfx
        w = np.frombuffer(bytes(g[off:off + cnt * 0x20000]), '<u4')
        lo = int((w & 0xFFFF).sum(dtype=np.uint64)) & 0xFFFF; hi = int((w >> 16).sum(dtype=np.uint64)) & 0xFFFF
        img.data[r:r + 8] = struct.pack('>4H', cnt, lo, hi, (lo + hi) & 0xFFFF)
        print(f'  ROM test CHAR{i} {cnt:#x} banks: {lo:04x} {hi:04x} {(lo + hi) & 0xFFFF:04x}')
        off += cnt * 0x20000


def gfx_chips(setname='gunbird2', g=None):
    """apply out/gfx/place.json to the gfx image and return modified chip files.
    gunbird2: stock layout (0x3800000, bank 3 = 2 x 32M).  gunbird2m: bank 3 = 2 x 64M EPROMs (U6/U13), gfx up to
    0x4000000 - same PS5 board, the sockets take 64M parts (see docs/MORRIGAN_BACKPORT_PLAN.md 0.1)."""
    if g is None: g = gfx_image(setname)
    chips = {}
    names = [('0l.u3', '0h.u10'), ('1l.u4', '1h.u11'), ('2l.u5', '2h.u12'), ('3l.u6', '3h.u13')]
    for bank, (lo, hi) in enumerate(names):
        seg = g[bank * 0x1000000:(bank + 1) * 0x1000000]
        w = np.frombuffer(bytes(seg), dtype='>u2')
        chips[lo], chips[hi] = w[0::2].tobytes(), w[1::2].tobytes()
    return chips


def split_and_write(img, setname):
    d = OUT + '/roms/' + setname
    os.makedirs(d, exist_ok=True)
    g = gfx_image(setname)
    z = zipfile.ZipFile(ROOT + '/mame_roms/gunbird2.zip')
    sndf = OUT + '/snd/sound.u9'                             # tools/port_sound.py (Morrigan's samples)
    snd = open(sndf, 'rb').read() if os.path.exists(sndf) else z.read('sound.u9')
    rom_checksums(img, g, snd, setname)                      # before the data ROM is split
    p = img.prog
    H, L = bytearray(0x80000), bytearray(0x80000)
    for i in range(0, 0x80000, 2):
        H[i:i + 2] = p[2 * i:2 * i + 2][::-1]
        L[i:i + 2] = p[2 * i + 2:2 * i + 4][::-1]
    dd = bytearray(img.data); dd[0::2], dd[1::2] = dd[1::2], dd[0::2]
    files = {'1_prog_h.u17': bytes(H), '2_prog_l.u16': bytes(L), '3_pdata.u1': bytes(dd)}
    for n in z.namelist():
        if n not in files: files[n] = z.read(n)
    if setname == 'gunbird2m':
        for n in ('3l.u6', '3h.u13'): files.pop(n, None)
    files['sound.u9'] = snd
    files.update(gfx_chips(setname, g))
    for n, b in files.items():
        open(f'{d}/{n}', 'wb').write(b)
    return {n: (f'{zlib.crc32(b):08x}', hashlib.sha1(b).hexdigest(), len(b)) for n, b in files.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', default='gunbird2')
    a = ap.parse_args()
    img = Image()
    # resource blobs (ported DC data) and their symbols for the C code
    ldsyms = ['/* generated by build.py from out/res/*.json */']
    for rj in sorted(glob.glob(OUT + '/res/*.json')):
        r = json.load(open(rj))
        if r.get('errors'): sys.exit(f'{rj}: unresolved errors, run the porter first')
        for addr, hexb, kind, name in r['blobs']:
            img.write(int(addr, 16), bytes.fromhex(hexb), f'res:{kind}:{name}')
        for k, v in r['symbols'].items(): ldsyms.append(f'PROVIDE({k} = 0x{v});')
        print(f'  resources {os.path.basename(rj)}: {len(r["blobs"])} blobs')
    open(SRC + '/res_syms.ld', 'w').write('\n'.join(ldsyms) + '\n')
    elf, syms = compile_and_link()
    if elf: load_sections(img, elf)
    hooks = SRC + '/hooks.txt'
    if os.path.exists(hooks):
        for line in open(hooks):
            line = line.split('#')[0].strip()
            if not line: continue
            addr, sym = line.split()[:2]
            t = syms[sym] if sym in syms else int(sym, 16)
            img.write(int(addr, 16), trampoline(int(addr, 16), t), f'hook->{sym}')
            print(f'  hook {addr} -> {sym} ({t:08x})')
    for pat in (SRC + '/patches.txt', SRC + '/gen_sound_patches.txt'):
        if not os.path.exists(pat): continue
        for line in open(pat):
            line = line.split('#')[0].strip()
            if not line: continue
            if line.startswith('sym32'):
                _, addr, sym = line.split()[:3]
                img.write(int(addr, 16), struct.pack('>I', syms[sym]), f'sym32 {sym}')
                continue
            addr, hexb = line.split(None, 1)
            b = bytes.fromhex(hexb.replace(' ', ''))
            img.write(int(addr, 16), b, 'patch')
    # absolute-address assembly patches: first line '! @ <hex address>', optional '! defsym: name=0xaddr ...'
    # Branch targets are defined relative to a __base label so the assembler resolves short displacements.
    # The section is linked at the 4-aligned address below the patch with '.skip' padding (then dropped), so
    # '.align' in a patch refers to real addresses (SH .text sections are 4-aligned by the assembler).
    for asm in sorted(glob.glob(SRC + '/asm/*.s')):
        text = open(asm).read()
        addr = int(text.splitlines()[0].split('@')[1].strip(), 16)
        pad = addr & 3
        pre = ['    .text', f'    .skip {pad}', '__base:']
        for l in text.splitlines():
            if l.startswith('! defsym:'):
                for d in l.split(':', 1)[1].split():
                    n, v = d.split('=')
                    pre.append(f'    .set {n}, __base + ({int(v, 16)} - {addr})')
        tmp = OUT + '/obj/' + os.path.basename(asm)
        open(tmp, 'w').write('\n'.join(pre) + '\n' + text)
        o = tmp + '.o'; e = tmp + '.elf'
        run(f'{BIN}/sh-as -big --isa=sh2 {tmp} -o {o}')
        run(f'{BIN}/sh-ld -EB -Ttext=0x{addr - pad:x} -e 0x{addr - pad:x} -L {SRC} -T {SRC}/asmpatch.ld --just-symbols={OUT}/obj/patch.elf -o {e} {o}')
        run(f'{BIN}/sh-objcopy -O binary --only-section=.text {e} {OUT}/obj/asm.bin')
        b = open(OUT + '/obj/asm.bin', 'rb').read()[pad:]
        img.write(addr, b, f'asm {os.path.basename(asm)}')
        print(f'  asm {os.path.basename(asm)} @ {addr:08x} ({len(b)} bytes)')
    crcs = split_and_write(img, a.set)
    json.dump(crcs, open(OUT + f'/roms/{a.set}.crc.json', 'w'), indent=1)
    open(OUT + '/prog_be_patched.bin', 'wb').write(img.prog)
    open(OUT + '/pdata_be_patched.bin', 'wb').write(img.data)
    print('wrote', OUT + '/roms/' + a.set)
    if a.set == 'gunbird2m':                                  # last step: MiSTer MRA + out/roms/gunbird2m.zip
        print(run(f'{sys.executable} {ROOT}/tools/make_mra.py').strip())


if __name__ == '__main__':
    main()
