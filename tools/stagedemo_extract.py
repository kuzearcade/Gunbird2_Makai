#!/usr/bin/env python3
"""Extract the Dreamcast stage-demo scenes that involve Morrigan (6 per stage: solo + pairs with characters 1-6).

For each stage 1-6 and DC pair slot (26 solo, 6, 12, 17, 21, 24 = with characters 1..5? see PAIR_SLOTS), walk the
DC scene script and record the event list (portrait = w0F character / w0E face, message = w13 number), the message
id (w12) and MSG file, and render every message in English (US disc) and Japanese (JP disc).
Output: out/stagedemo/scenes.json + out/stagedemo/img/s<stage>_w<w12>_m<n>_<US|JP>.png + contact sheets."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis, dcmsg
from gbres import Space, ROOT
from PIL import Image

PAIR_SLOTS = [26, 6, 12, 17, 21, 24]     # DC slots: Morrigan solo, (1,7), (2,7), (3,7), (4,7), (5,7); (6,7) -> 26
OUT = ROOT + '/out/stagedemo'


def scene(reg, stage, slot):
    D = Space('dc_' + reg); img = seqdis.Image('dc_' + reg)
    t = D.u32(D.u32(D.u32(D.u32(0x8C30002C) + 8)) + 4 * (stage - 1))
    a = D.u32(t + 4 * slot)
    work, ev, meta = {}, [], {}
    while True:
        ln, txt, tg, term, op = seqdis.decode(img, a)
        name = txt.split()[0]
        if name == 'MesFileRead': meta['file'] = img.w(a + 2)
        elif name == 'CalcWork' and img.w(a + 2) == 0x0840:
            work[img.w(a + 4)] = img.l(a + 6)
        elif name == 'Call':
            if not ev and 'start' not in meta: meta['start'] = tg[0]
            elif work.get(0x13) is not None and 'fe60' in txt or '530' in txt and 'Call' in txt:
                pass
        if name == 'Call' and 'start' in meta and tg[0] != meta['start']:
            kind = 'msg' if tg[0] == dcmsg.SUB[reg] else 'port'
            if kind == 'port': ev.append({'port': [work.get(0x0F), work.get(0x0E)]})
            else: ev.append({'msg': work.get(0x13), 'dur': work.get(0x0C)})
        if name == 'CalcWork' and img.w(a + 4) == 0x12 and img.w(a + 2) == 0x0840: meta['w12'] = work[0x12]
        if name in ('Sleep', 'End') or term: break
        a += ln
    return meta, ev


def main():
    os.makedirs(OUT + '/img', exist_ok=True)
    res = []
    for stage in range(1, 7):
        for slot in PAIR_SLOTS:
            meta, ev = scene('US', stage, slot)
            mj, evj = scene('JP', stage, slot)
            assert [e.get('port', e.get('msg')) for e in ev] == [e.get('port', e.get('msg')) for e in evj], (stage, slot)
            nmsg = len([e for e in ev if 'msg' in e])
            for reg in ('US', 'JP'):
                ms = dcmsg.messages(reg, stage, meta['w12'], maxmsg=nmsg, file_no=meta['file'])
                for m, (o, im) in enumerate(ms):
                    im.save(f"{OUT}/img/s{stage}_w{meta['w12']}_m{m}_{reg}.png")
            res.append({'stage': stage, 'slot': slot, 'w12': meta['w12'], 'file': meta['file'],
                        'start': hex(meta['start']), 'events': ev})
            print(stage, slot, meta, ev)
    json.dump(res, open(OUT + '/scenes.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
