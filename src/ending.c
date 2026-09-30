/* Morrigan endings (DC ending engine ported by tools/port_endings.py).
 *
 * - gb2_seq_putobjwork: native handler for seq opcode 0x67 PutObjWork (DC-only on the arcade): show the composite
 *   whose pointer is in work register A at (work X, work Y).  A pointer to a text descriptor ('TXT1') prints its
 *   lines with the arcade text printers instead (EN or JP by region), replacing the DC's pre-rendered text images.
 * - gb2_end_slot: G_Ending scene slot for 7 characters (as gb2_demo_slot); for one of Morrigan's endings it loads
 *   the ending data (scripts/composites/text, linked for RAM 0x06034000) and its palette banks from the gfx ROM,
 *   read through the PS6406B ROM-test window (0x04060000, 128 KB bank selected by video register 4). */
#include "arcade.h"
#include "gen_endings.h"

#define TASK            V32(0x0604005C)
#define WORK(t, r)      V32((t) + 0x80 + (r) * 4)
#define REGION_JP       (V32(0x06040004) == 0)
#define TEXT_MAGIC      0x54585431
#define PAL_RAM         ((volatile u32 *)0x24040000)
#define GFX_WIN         0x24060000
#define VIDREG4         V32(0x2405FFF0)
#define SEQ_GLOBAL(i)   V32(0x0605CAE0 + 4 * (i))   /* seq VM global work (JumpCompare / CalcWork kind 5) */
#define PrintJP         FN(s16, 0x06029352, (const void *, int, int))
#define PrintEN         FN(s16, 0x06029288, (const char *, int, int))

extern int gb2_demo_slot(int count, int last);
extern void gb2_pal_save_ending(void);

struct text_line { s16 x, y; const void *s; };
struct text_desc { u32 magic; u16 n_en, n_jp; struct text_line l[1]; };

/* arcade text objects live for one frame (freed by the frame routine), so text is printed on every call, as the
 * arcade's own ending scripts do with KanjiPrint inside per-frame loops */
static void text_show(const struct text_desc *d, int ox, int oy)
{
    int i, n0 = REGION_JP ? d->n_en : 0, n = REGION_JP ? d->n_jp : d->n_en;
    for (i = 0; i < n; i++) {
        const struct text_line *l = &d->l[n0 + i];
        int hx = ox + l->x, hy = oy + l->y;
        s16 slot = REGION_JP ? PrintJP(l->s, TXT_X(hx, hy), TXT_Y(hx, hy))
                             : PrintEN((const char *)l->s, TXT_X(hx, hy), TXT_Y(hx, hy));
        TEXT_TYPE_ATTR(slot);
    }
}

void gb2_seq_putobjwork(void)
{
    s32 t = TASK, ctx = V32(t + 0x20);
    u16 *pc = (u16 *)V32(ctx + 0x10);
    int ra = pc[0], rx = pc[1], ry = pc[2];
    s32 obj;
    s16 x, y;
    V32(ctx + 0x10) = (s32)(pc + 3);
    obj = WORK(t, ra);
    V32(t + 0x3C) = obj;
    x = (s16)WORK(t, rx); y = (s16)WORK(t, ry);
    if (obj && V32(obj) == TEXT_MAGIC) {
        text_show((const struct text_desc *)obj, x, y);
        ObjHide(V16(t + 0x48));
        return;
    }
    if (!obj) { ObjHide(V16(t + 0x48)); return; }
    /* position bookkeeping as the DC handler (integer parts at ctx+0x1C/+0x20 on the big-endian arcade) */
    V16(t + 0x34) += x - V16(ctx + 0x1C);
    V16(t + 0x36) += y - V16(ctx + 0x20);
    V16(t + 0x30) = x; V16(ctx + 0x1C) = x;
    V16(t + 0x32) = y; V16(ctx + 0x20) = y;
    V16(ctx + 0x1E) = 0; V16(ctx + 0x22) = 0;
    ObjSet(V16(t + 0x48), x, y, (const void *)obj);
    ObjShow(V16(t + 0x48));
}

/* ---- loading ------------------------------------------------------------------------------------------------ */
static void gfx_copy(void *dst, u32 gfx_off, u32 bytes)
{
    u32 save = VIDREG4, *d = dst;
    while (bytes) {
        u32 bank = gfx_off >> 17, off = gfx_off & 0x1FFFF, n = 0x20000 - off;
        if (n > bytes) n = bytes;
        VIDREG4 = (save & ~0xFFF) | bank;
        {
            volatile u32 *s = (volatile u32 *)(GFX_WIN + off);
            u32 i;
            for (i = 0; i < n / 4; i++) *d++ = s[i];
        }
        gfx_off += n; bytes -= n;
    }
    VIDREG4 = save;
}

static void load_ending(int slot)
{
    const struct end_pal *p;
    gfx_copy((void *)END_BLOB_BASE, END_BLOB_GFX, END_BLOB_SIZE);
    gb2_pal_save_ending();                          /* lines 0x10-0x3F, put back after the ending (palette.c) */
    /* global 0x0E: the DC sets it to 1 at game start and in Stage Select (0x8C03DB48, 0x8C073900); the solo ending's
     * choice ("The medicine." / "None.") picks its text layout and cursor step from it.  The arcade clears the globals
     * at game start and never uses 0x0E, so it read 0 here: 32-pixel lines instead of the DC's 16 */
    SEQ_GLOBAL(0x0E) = 1;
    for (p = end_pals; p->slot >= 0; p++) {
        if (p->slot != slot) continue;
        gfx_copy((void *)p->pal, p->gfx, 256 * 4);
    }
}

int gb2_end_slot(int count, int last)
{
    int slot = gb2_demo_slot(count, last), i;
    for (i = 0; i < END_N; i++) if (end_slots[i] == slot) { load_ending(slot); break; }
    return slot;
}
