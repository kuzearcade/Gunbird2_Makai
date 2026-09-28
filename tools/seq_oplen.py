#!/usr/bin/env python3
"""Estimate operand word counts for each seq opcode from DC decompiled handlers (dc_US.c).
Counts FUN_8c05cc00(1) (=2 words) and 'script ptr = p + 1' increments (=1 word), following direct calls one level."""
import re, json, sys
src = open('re/export/dc_US.c').read()
funcs = {}
for m in re.finditer(r'^// ==== (\S+) @ ([0-9a-f]+)\n(.*?)(?=^// ==== |\Z)', src, re.S | re.M):
    funcs[int(m.group(2), 16)] = (m.group(1), m.group(3))
byname = {v[0]: k for k, v in funcs.items()}
inc1 = re.compile(r'\+ 0x10\) = \w+ \+ 1;')
inc2 = re.compile(r'\+ 0x10\) = \w+ \+ 2;')
incn = re.compile(r'\+ 0x10\) =\s*\*\(int \*\)\(\*\(int \*\)\(_DAT_8c1a8c58 \+ 0x20\) \+ 0x10\) \+ (\d+);')
def count(addr, depth=0, seen=None):
    seen = seen or set()
    if addr in seen or addr not in funcs: return 0, []
    seen.add(addr)
    name, body = funcs[addr]
    n = 2 * body.count('FUN_8c05cc00(1)') + len(inc1.findall(body)) + 2 * len(inc2.findall(body))
    n += sum(int(x) // 2 for x in incn.findall(body))
    notes = []
    if depth < 2:
        for callee in set(re.findall(r'\b(FUN_[0-9a-f]{8}|[A-Z]\w+)\(', body)):
            if callee in ('FUN_8c05cc00', 'FUN_8c025620') or callee not in byname: continue
            c, _ = count(byname[callee], depth + 1, seen)
            if c: n += c; notes.append(f"{callee}+{c}")
    if 'switch' in body or 'JumpCompare(' in body: notes.append('VAR?')
    return n, notes
ops = json.load(open('re/seq_opcodes.json'))
for o in ops:
    h = int(o['dc'], 16)
    n, notes = count(h)
    o['len_est'] = n; o['len_notes'] = notes
json.dump(ops, open('re/seq_opcodes.json', 'w'), indent=1)
for o in ops:
    if o['name'] not in ('-', ''): print(o['op'], hex(o['op']), o['name'], 'tbl', o['nargs'], 'est', o['len_est'], ' '.join(o['len_notes']))
