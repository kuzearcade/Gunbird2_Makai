#!/usr/bin/env python3
"""Build patched Gunbird 2 ROMs.

  1. compile src/*.c (sh2-cc) and src/*.s (sh-as), link with src/gb2.ld into ROM free space
  2. apply trampolines (src/hooks.txt: '<arcade RAM function addr> <symbol>') and raw patches
     (src/patches.txt: '<addr> <hex bytes>' ; addr may be RAM-code 0x06xxxxxx or ROM 0x000xxxxx or data 0x0508xxxx/0x0608xxxx)
  3. merge extra resource blobs (out/res/*.bin with .json placement) - later milestones
  4. split into chip images (same names as MAME set) under out/roms/<set>/ and fix nothing else yet

usage: build.py [--set gunbird2] [--no-compile]
"""
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


def split_and_write(img, setname):
    d = OUT + '/roms/' + setname
    os.makedirs(d, exist_ok=True)
    p = img.prog
    H, L = bytearray(0x80000), bytearray(0x80000)
    for i in range(0, 0x80000, 2):
        H[i:i + 2] = p[2 * i:2 * i + 2][::-1]
        L[i:i + 2] = p[2 * i + 2:2 * i + 4][::-1]
    dd = bytearray(img.data); dd[0::2], dd[1::2] = dd[1::2], dd[0::2]
    files = {'1_prog_h.u17': bytes(H), '2_prog_l.u16': bytes(L), '3_pdata.u1': bytes(dd)}
    z = zipfile.ZipFile(ROOT + '/mame_roms/gunbird2.zip')
    for n in z.namelist():
        if n not in files: files[n] = z.read(n)
    for extra in glob.glob(OUT + '/gfx/*.u*') + glob.glob(OUT + '/snd/*.u*'):
        files[os.path.basename(extra)] = open(extra, 'rb').read()
    for n, b in files.items():
        open(f'{d}/{n}', 'wb').write(b)
    return {n: (f'{zlib.crc32(b):08x}', hashlib.sha1(b).hexdigest(), len(b)) for n, b in files.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', default='gunbird2')
    a = ap.parse_args()
    img = Image()
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
    pat = SRC + '/patches.txt'
    if os.path.exists(pat):
        for line in open(pat):
            line = line.split('#')[0].strip()
            if not line: continue
            addr, hexb = line.split(None, 1)
            b = bytes.fromhex(hexb.replace(' ', ''))
            img.write(int(addr, 16), b, 'patch')
    crcs = split_and_write(img, a.set)
    json.dump(crcs, open(OUT + f'/roms/{a.set}.crc.json', 'w'), indent=1)
    open(OUT + '/prog_be_patched.bin', 'wb').write(img.prog)
    open(OUT + '/pdata_be_patched.bin', 'wb').write(img.data)
    print('wrote', OUT + '/roms/' + a.set)


if __name__ == '__main__':
    main()
