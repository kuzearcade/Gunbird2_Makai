#!/usr/bin/env python3
"""Annotated SH-2 disassembly of an arcade RAM-code range: resolves PC-relative literals and jsr targets
(names from re/arcade.sym). usage: annotate_asm.py <start> <end>   (RAM addresses, hex)"""
import sys, re, struct, subprocess, os
ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
r = open(ROOT + '/assets/arcade/ram_init.bin', 'rb').read()
s, e = int(sys.argv[1], 16), int(sys.argv[2], 16)
tmp = ROOT + '/out/obj/ann.bin'
open(tmp, 'wb').write(r[s - 0x06000000:e - 0x06000000])
dis = subprocess.run([ROOT + '/tools/bin/sh-objdump', '-D', '-b', 'binary', '-m', 'sh2', '-EB', f'--adjust-vma=0x{s:x}', tmp],
                     capture_output=True, text=True).stdout
syms = {}
for l in open(ROOT + '/re/arcade.sym'):
    if l.startswith('#') or not l.strip(): continue
    a, n = l.split()[:2]; syms[int(a, 16)] = n
regs = {}
for l in dis.splitlines():
    m = re.match(r'\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} ){2})\s*(.*)', l)
    if not m: continue
    a = int(m.group(1), 16); t = m.group(3).strip()
    note = ''
    mm = re.match(r'mov\.l\s+0x([0-9a-f]+),(r\d+)', t)
    if mm:
        la = int(mm.group(1), 16)
        v = struct.unpack('>I', r[la - 0x06000000:la - 0x06000000 + 4])[0]
        regs[mm.group(2)] = v; note = f'= {v:#x} {syms.get(v, "")}'
    mm = re.match(r'mov\.w\s+0x([0-9a-f]+),(r\d+)', t)
    if mm:
        la = int(mm.group(1), 16)
        v = struct.unpack('>h', r[la - 0x06000000:la - 0x06000000 + 2])[0]; note = f'= {v:#x}'
    mm = re.match(r'(jsr|jmp)\s+@(r\d+)', t)
    if mm and mm.group(2) in regs: note = f'-> {syms.get(regs[mm.group(2)], hex(regs[mm.group(2)]))}'
    mm = re.match(r'(bsr|bra|bt|bf|bt/s|bf/s)\s+0x([0-9a-f]+)', t)
    if mm: note = syms.get(int(mm.group(2), 16), '')
    print(f'{a:08x}  {t:<32} {note}')
