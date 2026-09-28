#!/usr/bin/env python3
"""Transcribe DC Japanese stage-demo messages (glyph cells) into arcade font codes by glyph matching.
Line k of a message = stored column W-1-k, character i = stored row i (see dcmsg.render).  Empty cells = space."""
import os, sys, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqdis, dcmsg, jpfont

def message_codes(stage, w12, file_no, m):
    img = seqdis.Image('dc_JP')
    cells = dcmsg.load_cells('JP', stage, file_no - 1)
    rec = dcmsg.find_objdt(img, {0x15: stage, 0x12: w12, 0x13: m}, dcmsg.SUB['JP'])
    s0, s1, idx = img.w(rec + 4), img.w(rec + 6), img.w(rec + 10) - 0x1000
    W, H = ((s1 >> 8) & 15) + 1, ((s0 >> 8) & 15) + 1
    lines, worst = [], 0
    for k in range(W):
        line = []
        for i in range(H):
            j = idx + i * W + (W - 1 - k)
            if j >= len(cells): line.append(None); continue
            mask = (cells[j] & 0x8000) != 0
            if mask.sum() < 3: line.append(None); continue
            (c, d), = jpfont.match(mask, 1)
            worst = max(worst, d); line.append((c, d))
        while line and line[-1] is None: line.pop()
        lines.append(line)
    while lines and not lines[-1]: lines.pop()
    return lines, worst

def encode(lines):
    out = []
    for n, l in enumerate(lines):
        if n: out.append(0xFFFE)
        out += [0xFFFD if x is None else x[0] for x in l]
    return out + [0xFFFF]

def render(codes):
    rows, cur = [], []
    for c in codes:
        if c in (0xFFFE, 0xFFFF): rows.append(cur); cur = []
        else: cur.append(c)
    Wd = max(len(r) for r in rows) * 16
    im = np.zeros((len(rows) * 16, Wd), np.uint8)
    for r, row in enumerate(rows):
        for i, c in enumerate(row):
            if c == 0xFFFD: continue
            g = jpfont.glyph(c)
            # glyphs are stored rotated (hardware orientation): rotate to reading orientation
            im[r * 16:r * 16 + 16, i * 16:i * 16 + 16] = np.rot90(np.where(g > 0, 255, 0), 1)
    return im

if __name__ == '__main__':
    from PIL import Image
    ROOT = os.path.dirname(os.path.abspath(__file__)) + '/..'
    sc = json.load(open(ROOT + '/out/stagedemo/scenes.json'))
    res = {}
    for s in sc:
        for e in s['events']:
            if 'msg' not in e: continue
            lines, worst = message_codes(s['stage'], s['w12'], s['file'], e['msg'])
            codes = encode(lines)
            key = f"s{s['stage']}_w{s['w12']}_m{e['msg']}"
            res[key] = codes
            Image.fromarray(render(codes)).save(f"{ROOT}/out/stagedemo/img/{key}_JParc.png")
            print(key, 'worst', worst, 'len', len(codes))
    json.dump(res, open(ROOT + '/out/stagedemo/jp_codes.json', 'w'), indent=0)
