/* Morrigan palette groups.
 * Morrigan's sprites use colr 0xFF with pens >= 16, i.e. palette entries 0x1000+ (lines 0x100-0x13F), which
 * the original game never writes (PltBlockSet masks the line with 0xFF), so a group written once stays until
 * another group (select screen, story screens) replaces it.  Nothing here runs per frame: extra cycles in the
 * in-game main loop change slowdown and with it the game's course (verified: hooking the palette queue made
 * non-Morrigan games diverge from the original). */
#include "arcade.h"
#include "gen_gfx.h"

#define PAL_RAM       ((volatile u32 *)0x24040000)   /* cache-through palette RAM, 32-bit RGBx entries */

/* write a Morrigan palette group into entries 0xFF0+PEN0.. (colr 0xFF window, >= 0x1000) */
void gb2_pal_load_group(const u32 *pal, u16 count)
{
    u16 i;
    for (i = 0; i < count; i++) PAL_RAM[MORRIGAN_COLR * 16 + MORRIGAN_PEN0 + i] = pal[i];
}

/* in-game group: called from PlayerSet for charNo 7 (src/playerset7.s) */
void gb2_morrigan_pal_init(void)
{
    gb2_pal_load_group(pal_game, pal_game_count);
}
