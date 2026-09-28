#!/usr/bin/env python3
"""List the Dreamcast Morrigan endings: title task + per-branch picture tasks with their picture / text / wait
sequence (parent work: w0C/w10 = picture composite, w0A = text composite, w07 = task done).
Endings: DC ending table slots 26 (solo, END6), 6, 12, 17, 21, 24 (with characters 1-5, END60-64)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis
from gbres import Space

SLOTS = {26: 'END6.CHR', 6: 'END60.CHR', 12: 'END61.CHR', 17: 'END62.CHR', 21: 'END63.CHR', 24: 'END64.CHR'}

def ops(img, a, stop=None):
    out = []
    for _ in range(400):
        ln, txt, tg, term, op = seqdis.decode(img, a)
        out.append((a, txt, tg, op))
        if term or txt.startswith(('End ', 'Sleep')) or txt.strip() in ('End', 'Sleep'): break
        a += ln
    return out

def task(img, a):
    ev = []
    for ad, txt, tg, op in ops(img, a):
        t = txt.split()
        if t[0] == 'CalcWork' and t[1] in ('0860', '0870') and len(t) >= 5:
            reg = int(t[2], 16); val = img.l(ad + 6)
            if reg in (0x0C, 0x10) and val > 0x8C300000: ev.append(('pic', hex(val)))
            elif reg == 0x0A and val > 0x8C300000: ev.append(('text', hex(val)))
            elif reg == 0x0A and val == 0: ev.append(('clear',))
            elif reg == 0x07: ev.append(('done',))
        elif t[0] == 'Wait': ev.append(('wait', int(t[1])))
        elif t[0] == 'SetNewAct': ev.append(('act', hex(tg[0])))
        elif t[0] in ('Sound', 'Effect'): ev.append((t[0].lower(), t[1]))
        elif t[0] == 'JumpCompare' and 'text' not in [e[0] for e in ev] and t[1] == '0150':
            ev.append(('cmp', ' '.join(t[1:4]), hex(tg[0])))
    return ev

def main():
    D = Space('dc_US'); img = seqdis.Image('dc_US')
    tbl = D.u32(D.u32(D.u32(0x8C30002C) + 8) + 0x10)
    res = {}
    for slot, fn in SLOTS.items():
        a = D.u32(tbl + 4 * slot)
        # main flow: linear SetNewAct/Call list; a choice ending then waits for w6 and branches (w6 = 1 / 2)
        seq, br, x = [], [], a
        for _ in range(200):                      # linear scan (the w6 wait loop jumps back: never follow Jumps)
            ln, txt, tg, term, op = seqdis.decode(img, x)
            w = txt.split()[0]
            if w == 'SetNewAct': seq.append(tg[0])
            if w == 'JumpCompare' and '0170 0006' in txt: br.append(tg[0])
            if w in ('Sleep', 'End') or len(br) == 2: break
            if w == 'Nop' and seq and not any('0006' in seqdis.decode(img, x + ln)[1] for _ in [0]) and \
                    not seqdis.decode(img, x + ln)[1].startswith(('SetNewAct', 'Call', 'JumpCompare')): break
            x += ln
        branches = []
        for b in br:
            bo = ops(img, b)
            branches.append([task(img, tg[0]) for ad, txt, tg, op in bo if txt.startswith('SetNewAct')])
        res[slot] = {'file': fn, 'script': hex(a), 'title_task': hex(seq[0]), 'title': task(img, seq[0]),
                     'tasks': [task(img, t) for t in seq[1:]], 'task_addrs': [hex(t) for t in seq], 'branches': branches}
        title = res[slot]['title']
        print(f'== slot {slot} {fn} {hex(a)}  title {title}')
        for t in res[slot]['tasks']: print('    ', t)
        for i, b in enumerate(branches):
            print(f'   branch {i + 1}: {len(b)} pictures')
            for t in b: print('      ', t)
    json.dump(res, open(os.path.dirname(os.path.abspath(__file__)) + '/../out/stagedemo/endings.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
