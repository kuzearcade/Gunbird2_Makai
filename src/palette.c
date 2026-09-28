/* Palette upload queue (arcade 0x0602847C) re-implemented so Morrigan's in-game colours are rewritten every
 * time the shared player palette (lines 0x40-0x4F, table 0x260B6428) is loaded.
 * Morrigan's sprites use colr 0xFF with pens >= 16, i.e. palette entries 0x1000+ (lines 0x100-0x13F), which
 * the original game never writes (PltBlockSet masks the line with 0xFF). */
#include "arcade.h"

struct pal_req { void *fn; u32 line; const void *tbl; u32 pad; };
#define PAL_QUEUE_N   VU16(0x0604C21C)
#define PAL_QUEUE     ((volatile struct pal_req *)0x0604C220)
#define PAL_COPY_FN   ((void *)0x060284B0)
#define PAL_RAM       ((volatile u32 *)0x24040000)
#define PLAYER_PAL    0x060B6428u

extern const u32 pal_morrigan_game[];
extern const u16 pal_morrigan_game_first, pal_morrigan_game_count;

static void enqueue(void *fn, u32 line, const void *tbl)
{
    u16 n = PAL_QUEUE_N;
    PAL_QUEUE[n].fn = fn;
    PAL_QUEUE[n].line = line & 0xFF;
    PAL_QUEUE[n].tbl = tbl;
    PAL_QUEUE_N = n + 1;
}

/* queue callback (runs at vblank like the original copy routine) */
void gb2_pal_write_morrigan(u32 line, const void *tbl)
{
    u16 i;
    (void)line; (void)tbl;
    for (i = 0; i < pal_morrigan_game_count; i++)
        PAL_RAM[pal_morrigan_game_first + i] = pal_morrigan_game[i];
}

void gb2_pal_queue(u32 line, const void *tbl)
{
    enqueue(PAL_COPY_FN, line, tbl);
    if ((line & 0xFF) == 0x40 && ((u32)tbl & 0x0FFFFFFF) == PLAYER_PAL)
        enqueue((void *)gb2_pal_write_morrigan, 0, 0);
}
