#!/usr/bin/env python3
"""From a Ghidra export .lst + raw image, list per function the strings it loads via mov.l @(lit,pc).
usage: lst_strrefs.py image base le|be export.lst > refs.tsv   (func_addr func_name insn_addr string)"""
import sys, struct, re
img = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 16); fmt = '<' if sys.argv[3] == 'le' else '>'
def rd32(a):
    o = a - base
    return struct.unpack(fmt + 'I', img[o:o+4])[0] if 0 <= o <= len(img) - 4 else None
def cstr(a):
    o = a - base
    if not (0 <= o < len(img)): return None
    e = img.find(b'\0', o, o + 200)
    if e < 0 or e - o < 4: return None
    s = img[o:e]
    if all(32 <= c < 127 for c in s): return s.decode()
    return None
pat = re.compile(r'mov\.l (?:@\()?(0x[0-9a-f]+)(?:,pc\))?,r\d+$')
mova = re.compile(r'mova (?:@\()?(0x[0-9a-f]+)')
for line in open(sys.argv[4]):
    a, fn, ins, ent = (line.rstrip('\n').split('\t') + ['-'])[:4]
    m = pat.search(ins); mv = mova.search(ins)
    if m: v = rd32(int(m.group(1), 16))
    elif mv: v = int(mv.group(1), 16)
    else: continue
    if v is None: continue
    s = cstr(v)
    if s: print(f"{fn}\t{a}\t{v:08x}\t{s}\t{ent}")
