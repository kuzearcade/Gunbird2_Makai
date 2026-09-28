#!/usr/bin/env python3
"""List instructions that load a given 32-bit literal value (PC-relative) - i.e. xrefs to an address/constant.
usage: lst_litrefs.py image base le|be export.lst value[,value...]"""
import sys, struct, re
img = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 16); fmt = '<' if sys.argv[3] == 'le' else '>'
want = {int(v, 16) for v in sys.argv[5].split(',')}
pat = re.compile(r'mov\.l (?:@\()?(0x[0-9a-f]+)(?:,pc\))?,(r\d+)$')
for line in open(sys.argv[4]):
    a, fn, ins, ent = (line.rstrip('\n').split('\t') + ['-'])[:4]
    m = pat.search(ins)
    if not m: continue
    o = int(m.group(1), 16) - base
    if 0 <= o <= len(img) - 4:
        v = struct.unpack(fmt + 'I', img[o:o+4])[0]
        if v in want: print(f"{fn}\t{a}\t{v:08x}\t{m.group(2)}")
