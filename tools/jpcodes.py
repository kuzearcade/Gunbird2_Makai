#!/usr/bin/env python3
"""Unicode <-> arcade Japanese font code (tile 0x150 + code).  The font is JIS X 0208 order with gaps removed:
row 1 from '、' (codes 0-92), row 2 '◆'..'〓' (93-106), digits 107-116, custom 117-121 (♥ ‼ ⁉ ♬ ♭),
A-Z a-z 122-173, hiragana 174-256, katakana 257-342, Greek 343-390, Cyrillic capitals 391-423, kanji level 1
424-3388.  Verified against anchors and the game's own text.  After level 1 the font holds only 44 hand-picked
level-2 kanji (3389-3432, not in JIS order, e.g. 丼 弐 刹 喩 曖 舗 萬), then no more glyphs: codes past 3432 draw
unrelated gfx data (a level-2 character encoded in JIS order showed a coloured block), so encode() refuses anything
beyond level 1 and spells the known missing kanji in kana (MISSING)."""
def _jis(row, col):
    try: return bytes([0xA0 + row, 0xA0 + col]).decode('euc_jp')
    except UnicodeDecodeError: return None

def build():
    seq = []
    seq += [c for c in (_jis(1, k) for k in range(2, 95)) if c]                     # row 1 without '　'
    seq += [c for c in (_jis(2, k) for k in range(1, 15)) if c]                     # ◆..〓
    seq += [c for c in (_jis(3, k) for k in range(16, 26)) if c]                    # 0-9
    seq += ['♥', '‼', '⁉', '♬', '♭']
    seq += [c for c in (_jis(3, k) for k in range(33, 95)) if c]                    # A-Z a-z
    seq += [c for c in (_jis(4, k) for k in range(1, 95)) if c]                     # hiragana
    seq += [c for c in (_jis(5, k) for k in range(1, 95)) if c]                     # katakana
    seq += [c for c in (_jis(6, k) for k in range(1, 95)) if c]                     # Greek
    seq += [c for c in (_jis(7, k) for k in range(1, 34)) if c]                     # Cyrillic capitals
    for row in range(16, 85):
        seq += [c for c in (_jis(row, k) for k in range(1, 95)) if c]
    return seq

SEQ = build()
LEVEL1_END = 3389                       # first code after kanji level 1 (湾碗腕 end it)
CODE = {}
for i, ch in enumerate(SEQ[:LEVEL1_END]): CODE.setdefault(ch, i)
MISSING = {'騙': 'だま'}                # not in the arcade font: 騙した -> だました (Morrigan x Hei-Cob ending)
ALIAS = {'!': '！', '?': '？', ' ': None, '~': '～', '-': 'ー', '…': '…', '・': '・', '!!': '‼'}

def encode(text):
    """unicode (with \\n) -> codes: ' ' / '　' -> 0xFFFD, newline -> 0xFFFE, end 0xFFFF"""
    out = []
    for k, v in MISSING.items(): text = text.replace(k, v)
    for ch in text:
        if ch == '\n': out.append(0xFFFE); continue
        if ch in (' ', '　'): out.append(0xFFFD); continue
        if ch not in CODE and 0x21 <= ord(ch) < 0x7F: ch = chr(ord(ch) + 0xFEE0)     # ASCII -> full width
        if ch not in CODE: ch = {'〜': '～', '♡': '♥'}.get(ch, ch)
        if ch not in CODE: raise KeyError(f'{ch!r} (in {text!r}) is not in the arcade font: add it to MISSING')
        out.append(CODE[ch])
    return out + [0xFFFF]

def decode(codes):
    return ''.join('\n' if c == 0xFFFE else ' ' if c == 0xFFFD else '' if c == 0xFFFF else
                   (SEQ[c] if c < len(SEQ) else f'<{c:x}>') for c in codes)

if __name__ == '__main__':
    for ch, want in (('0', 107), ('A', 122), ('ぁ', 174), ('ァ', 257), ('Α', 343), ('А', 391), ('亜', 424), ('、', 0)):
        print(ch, CODE.get(ch), want)
