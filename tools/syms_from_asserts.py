#!/usr/bin/env python3
"""Derive function names from assert strings 'file.c  Func()' in a strrefs.tsv"""
import sys, re, collections
names = collections.defaultdict(set)
for l in open(sys.argv[1]):
    fn, a, v, s = l.rstrip('\n').split('\t')
    m = re.match(r'^\s*\w+\.c\s+(\w+)\s*\(\)', s)
    if m and fn.startswith('FUN_'): names[fn[4:]].add(m.group(1))
out = {a: list(ns)[0] for a, ns in names.items() if len(ns) == 1}
used = collections.Counter(out.values())
print('# auto: from assert strings')
for a in sorted(out):
    n = out[a]; print(a, n if used[n] == 1 else n + '_' + a)
