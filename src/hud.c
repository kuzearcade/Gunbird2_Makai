/* HUD: remaining-lives icons. The arcade draws charNo*12 + list - 12 from global resource table entry 109
 * (SEQ hdr+0x1C table, offset 0x1B4). DC's list has 7 entries; entry 7 = Morrigan (SYSTEM.CHR cell 0x16D). */
#include "arcade.h"
#include "gen_gfx.h"

const u16 gb2_life_icons[7][6] = {
    { 0x03F8, 0x07F8, 0, 0, 0x4080, 0x1C92 },
    { 0x03F8, 0x07F8, 0, 0, 0x4080, 0x1C93 },
    { 0x03F9, 0x07F8, 0, 0, 0x4080, 0x1C94 },
    { 0x03F8, 0x07F8, 0, 0, 0x4080, 0x1C95 },
    { 0x03F9, 0x07F8, 0, 0, 0x4080, 0x1C96 },
    { 0x03F8, 0x07F8, 0, 0, 0x4080, 0x1C97 },
    { 0x03F8, 0x07F8, 0, 0, (COLR_LIFE_ICON << 8) | 0x80 | (TNUM_LIFE_ICON >> 16), TNUM_LIFE_ICON & 0xFFFF },
};
