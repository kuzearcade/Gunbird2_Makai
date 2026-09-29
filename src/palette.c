/* Morrigan palette groups.
 * Her sprite colours must stay on palette lines <= 0xFF: the real PS5 does not render sprite colours from the
 * entries 0x1000+ (lines 0x100+) that MAME emulates and her sprites used before.  The original game draws with nearly
 * every line <= 0xFF somewhere (tools/mame/paldraw.py, even lines it keeps black, e.g. the select screen's icon
 * shadows with bank 0x30), so each group gets lines the original does not draw while that group is shown:
 *  - in-game sprites: two colour sets, pal_game0 on colr 0x1C and pal_game1 on colr 0x2C, pens 1-63 each (lines
 *    0x1C-0x1F, 0x2C-0x2F).  Lines 0x10-0x3F are the original's damage-flash (white 0x10, red 0x20) and shadow
 *    (black 0x30) banks, drawn with any sprite's own pens; lines 0x1C-0x1F / 0x2C-0x2F are their black tails, reached
 *    only by pens 0xC0-0xFF and in play almost never drawn (tools/mame/sprlog.py: 0x1C / 0x2C never, 0x1D-0x1F /
 *    0x2D-0x2F on a few hundred frames in nine whole games, where a flashing enemy's darkest pixels would show her
 *    colours instead of black).  Her pens stay below 0x40, so her own shadow and flash stay right.  The select screen
 *    and every game start write these lines (PltBlockSet(0x20, 0x260B6318)), so the sets are (re)loaded whenever
 *    play (GameLoop state 10) starts, and at G_Ranking.
 *  - select-screen art (pal_select): colr 0x10, lines 0x10-0x1F.  Not drawn on the select screen, but lines
 *    0x10-0x1B hold colours the select screen loads for later (drawn in play), so they are saved before the art is
 *    loaded and restored after it (src/select.c).
 * Her endings load banks 0x10-0xE0 over lines the original keeps (0x30-0x3F: the black shadow bank): see below.
 * Nothing here runs per frame: extra cycles in the in-game main loop change slowdown and with it the game's course
 * (verified: hooking the palette queue made non-Morrigan games diverge from the original). */
#include "arcade.h"
#include "gen_gfx.h"

#define PAL_RAM       ((volatile u32 *)0x24040000)   /* cache-through palette RAM, 32-bit RGBx entries */

/* copy count palette entries (the PS5's 32-bit RGBx) */
void gb2_pal_copy(volatile u32 *dst, const volatile u32 *src, u16 count)
{
    u16 i;
    for (i = 0; i < count; i++) dst[i] = src[i];
}

/* write a Morrigan palette group to pens MORRIGAN_PEN0.. of bank colr */
void gb2_pal_load_group(const u32 *pal, u16 count, u16 colr)
{
    gb2_pal_copy(PAL_RAM + colr * 16 + MORRIGAN_PEN0, pal, count);
}

/* One save buffer for the two things that cover lines the original game needs later (never both at once):
 *  - the select screen puts her art on lines 0x10-0x1F: saved before, restored on the way out (src/select.c);
 *  - her endings load banks 0x10-0xE0 (the original endings leave 0x10-0x3F alone): lines 0x10-0x3F are saved when
 *    the first ending scene loads (src/ending.c) and restored at the next entry into play (loop 2) or G_Ranking.
 * (In .bss, which must end below the ending data at 0x06034000: src/gb2.ld.) */
#define ENDING_SAVED  0x4D4F5247                     /* 'MORG' */
static u32 saved[0x300];
static u32 ending_saved;

void gb2_pal_save(void)
{
    ending_saved = 0;
    gb2_pal_copy(saved, PAL_RAM + 0x100, 0x100);
}

void gb2_pal_restore_select(void)   { gb2_pal_copy(PAL_RAM + 0x100, saved, 0x100); }

void gb2_pal_save_ending(void)
{
    if (ending_saved == ENDING_SAVED) return;       /* a later scene of the same ending */
    gb2_pal_copy(saved, PAL_RAM + 0x100, 0x300);
    ending_saved = ENDING_SAVED;
}

static void restore_ending(void)
{
    if (ending_saved != ENDING_SAVED) return;
    gb2_pal_copy(PAL_RAM + 0x100, saved, 0x300);
    ending_saved = 0;
}

/* in-game group: called from PlayerSet for charNo 7 (src/asm/playerset_generic.s), G_Ranking and at every entry
 * into the in-game state (gb2_play_wrap) */
void gb2_morrigan_pal_init(void)
{
    gb2_pal_load_group(pal_game0, pal_game0_count, MORRIGAN_COLR0);
    gb2_pal_load_group(pal_game1, pal_game1_count, MORRIGAN_COLR1);
}

/* G_Ranking entry (src/ranking_entry.s): after her last ending, and her life icon in the ranking list even when she
 * has not been played since the select screen covered her lines */
void gb2_ranking_pal(void)
{
    restore_ending();
    gb2_morrigan_pal_init();
}

#define G_Play      FN(int, 0x0601EFA2, (void))
#define CHARNO(p)   VU8(0x06055058 + (p) * 0xB0)

/* GameLoop's in-game state (state 10, handler 0x0601EFA2 via literal 0x0601CDCC, src/patches.txt), entered once per
 * stage: game start rewrites lines 0x20-0x2F after PlayerSet, and her endings (after loop 1) load their own banks,
 * so the lines under her ending are put back and her sprite colours (re)loaded here; nothing else writes those
 * lines during play (tools/mame/check_palette.py) */
int gb2_play_wrap(void)
{
    restore_ending();
    if (CHARNO(0) == 7 || CHARNO(1) == 7) gb2_morrigan_pal_init();
    return G_Play();
}
