#!/usr/bin/env python3
"""Code-side balance diff between the Dreamcast builds US v1.000 and JP v1.002 (1ST_READ.BIN, Ghidra listings).

Each function's instructions are normalised: branch targets dropped, PC-relative literal loads replaced by the
literal's value unless it is an address (then 'PTR'); immediates are kept.  The function lists (address order) are
aligned with difflib on the normalised bodies; identical functions pair up, the rest are paired inside replaced
blocks by position and diffed instruction-wise.  Reported: every changed immediate / literal value, per function.
US v1.000 contains assert calls (FUN_8C025620(cond, function name, message, 0)) that the JP release lacks, so a
changed value is looked for as a constant the JP function has and the US one does not (--consts, default); US-only
constants are mostly assert conditions.
usage: dc_codediff.py [--all] [--hunks]      (default: game code 0x8C010000-0x8C081500, without the libraries)"""
import os, re, sys, struct, difflib, collections
ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
BASE = 0x8C010000


ASSERT = {'US': 0x8C025620, 'JP': None}                    # assert(cond, function, message, value)


def load(tag):
    tag_ = tag
    img = open(f'{ROOT}/re/1st_read_{tag}.bin', 'rb').read()
    funcs = collections.OrderedDict()
    for line in open(f'{ROOT}/re/export/dc_{tag}.lst'):
        p = line.rstrip('\n').split('\t')
        if len(p) < 4: continue
        if p[3] == '-': continue                                   # not inside a function
        a, name, ins, start = int(p[0], 16), p[1], p[2], int(p[3], 16)
        f = funcs.setdefault(start, {'name': name, 'ins': []})
        f['ins'].append((a, ins))
    def lit(addr, size):
        o = addr - BASE
        if not 0 <= o < len(img) - size: return None
        return struct.unpack('<I' if size == 4 else '<h', img[o:o + size])[0]
    out = collections.OrderedDict()
    for start, f in funcs.items():
        toks = []
        for a, ins in sorted(f['ins']):
            m = re.match(r'_?(\S+)\s*(.*)', ins)
            op, args = m.group(1), m.group(2)
            if op in ('bra', 'bsr', 'bt', 'bf', 'bt/s', 'bf/s'): toks.append((op, 'L')); continue
            pm = re.match(r'(?:@\()?0x([0-9a-f]+)(?:,pc\))?,(r\d+)$', args)   # PC-relative literal load
            if pm and op in ('mov.l', 'mov.w'):
                v = lit(int(pm.group(1), 16), 4 if op == 'mov.l' else 2)
                ptr = v is not None and op == 'mov.l' and 0x8C000000 <= v < 0x8D000000
                tag = ('PTR:assert' if v == ASSERT[tag_] else 'PTR') if ptr else f'={v:#x}' if v is not None else '?'
                toks.append((op, tag + ',' + pm.group(2)))
                continue
            if op == 'mova': toks.append((op, 'PTR')); continue
            toks.append((op, args))
        out[start] = (f['name'], toks)
    return out


def strip_asserts(toks):
    """drop US assert calls: from the load of the 4th argument (r7) up to the jsr through PTR:assert (+ delay slot)"""
    out, i = [], 0
    while i < len(toks):
        if toks[i][1].startswith('PTR:assert'):
            k = len(out) - 1
            while k >= 0 and not re.search(r',r7$', out[k][1]): k -= 1
            if k >= 0: del out[k:]
            i += 3                                                   # load, jsr, delay slot
            continue
        out.append(toks[i]); i += 1
    return out


def consts(toks):
    return [t for t in toks if re.search(r'(#?-?0x[0-9a-f]+|=\-?0x[0-9a-f]+|\b\d+\b)', t[1])]


def main():
    lo, hi = (0, 1 << 32) if '--all' in sys.argv else (0x8C010000, 0x8C081500)
    us, jp = load('US'), load('JP')
    ua = [a for a in us if lo <= a < hi]; ja = [a for a in jp if lo <= a < hi]
    key = lambda d, a: hash(tuple(d[a][1]))
    sm = difflib.SequenceMatcher(None, [key(us, a) for a in ua], [key(jp, a) for a in ja], autojunk=False)
    same = changed = 0; report = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal': same += i2 - i1; continue
        # pair inside the replaced block by similarity (order kept): greedy over the best-scoring pairs
        ops = lambda d, a: [o for o, _ in d[a][1]]
        cand = []
        for x in range(i1, i2):
            for y in range(j1, j2):
                if abs((x - i1) - (y - j1)) > 12: continue
                r = difflib.SequenceMatcher(None, ops(us, ua[x]), ops(jp, ja[y]), autojunk=False).ratio()
                if r > 0.6: cand.append((r, x, y))
        pairs, usedx, usedy = [], set(), set()
        for r, x, y in sorted(cand, reverse=True):
            if x in usedx or y in usedy: continue
            if any((x - px) * (y - py) < 0 for px, py in pairs): continue      # keep order
            pairs.append((x, y)); usedx.add(x); usedy.add(y)
        for x in range(i1, i2):
            if x not in usedx: report.append((ua[x], None, us[ua[x]][0] + ' (only in US)', []))
        for y in range(j1, j2):
            if y not in usedy: report.append((None, ja[y], jp[ja[y]][0] + ' (only in JP)', []))
        for x, y in sorted(pairs):
            u, j = ua[x], ja[y]
            tu, tj = us[u][1], jp[j][1]
            d = []
            for t2, a1, a2, b1, b2 in difflib.SequenceMatcher(None, tu, tj, autojunk=False).get_opcodes():
                if t2 != 'equal': d.append((tu[a1:a2], tj[b1:b2]))
            changed += 1; report.append((u, j, us[u][0], d))
    print(f'functions: US {len(ua)} JP {len(ja)}; identical {same}; differing/unpaired {len(report)}')
    if '--hunks' not in sys.argv:
        num = lambda toks: collections.Counter(m for _, x in toks for m in re.findall(r'(?:#|=)-?0x[0-9a-f]+', x))
        hits = 0
        for u, j, name, d in report:
            if u is None or j is None: continue
            cu, cj = num(us[u][1]), num(jp[j][1])
            added, removed = cj - cu, cu - cj
            if added:
                hits += 1
                print(f'  {name:22s} US {u:08x} JP {j:08x}  JP adds {dict(added)}  US-only {dict(removed)}')
        print(f'functions with constants new in JP: {hits}')
        print('unpaired:', ', '.join(n for u, j, n, _ in report if u is None or j is None))
        return
    for u, j, name, d in report:
        print(f'\n{name}  US {u and hex(u)}  JP {j and hex(j)}  ({len(d)} hunks)')
        for a, b in d[:12]:
            print('   US', ' ; '.join(f'{o} {x}' for o, x in a)[:150])
            print('   JP', ' ; '.join(f'{o} {x}' for o, x in b)[:150])


if __name__ == '__main__':
    main()
