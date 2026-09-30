/* Morrigan endings (DC ending engine ported by tools/port_endings.py).
 *
 * - gb2_seq_putobjwork: native handler for seq opcode 0x67 PutObjWork (DC-only on the arcade): show the composite
 *   whose pointer is in work register A at (work X, work Y).  A pointer to a text descriptor ('TXT1') prints its
 *   lines with the arcade text printers instead (EN or JP by region), replacing the DC's pre-rendered text images.
 * - gb2_end_slot: G_Ending scene slot for 7 characters (as gb2_demo_slot); for one of Morrigan's endings it loads
 *   the ending data (scripts/composites/text, linked for RAM 0x06034000) and its palette banks from the gfx ROM,
 *   read through the PS6406B ROM-test window (0x04060000, 128 KB bank selected by video register 4).  Her solo
 *   ending (also Morrigan + Aine) has a choice whose cursor task reads the pad of the player in the ending task's
 *   w0; G_Ending puts the last active player there (2 whenever two play; the DC's Ending Demo uses 1), so it is set
 *   to Morrigan's player instead. */
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

/* ---- white fades as palette fades ------------------------------------------------------------------------------
 * The ending engine fades a full-screen white plate (END_WHITE_PLATE) in and out with sprite alpha (the picture slot
 * tasks: ChangeShadeObj slot, FncShadeRegSet(slot, w0F), PutObjWork).  The real PS5 does not alpha-blend 8bpp sprites
 * (the stock game only ever blends 4bpp ones; on the board the plate stayed solid for its whole fade-out), so while the
 * plate is partly transparent it is hidden and the ending's palette banks are tinted toward white by the plate's
 * opacity instead - the same picture, as the plate is plain white over opaque pictures.  Bank 0xE0 (common composites:
 * the letterbox masks, the plate itself) is left alone. */
#define OBJ_SHADE(o)    ((VU8(0x06040079 + (o) * 0x24) >> 4) & 7)   /* alpha slot set by ChangeShadeObj */
static int cur_slot;                            /* the loaded ending slot (0 = none: no ending uses slot 0) */
static u32 tint_amt;
static s32 tint_task;

/* a: 0 = the ending's colours .. 252 = (nearly) white.  The original colours are read back from the gfx ROM (no RAM
 * left for a copy), a 1 KB bank at a time through the ROM-test window. */
static void pal_tint(u32 a)
{
    const struct end_pal *p;
    u32 save = VIDREG4, i;
    for (p = end_pals; p->slot >= 0; p++) {
        volatile u32 *d = (volatile u32 *)p->pal;
        if (p->slot != cur_slot || p->bank >= 0xE0) continue;
        for (i = 0; i < 256; i++) {
            u32 off = p->gfx + i * 4, c, r, g, b;
            VIDREG4 = (save & ~0xFFF) | (off >> 17);
            c = V32(GFX_WIN + (off & 0x1FFFF));
            r = c >> 24; g = (c >> 16) & 0xFF; b = (c >> 8) & 0xFF;
            r += ((255 - r) * a) >> 8; g += ((255 - g) * a) >> 8; b += ((255 - b) * a) >> 8;   /* SH-2: no shld */
            d[i] = (r << 24) | (g << 16) | (b << 8) | (c & 0xFF);
        }
    }
    VIDREG4 = save;
}

/* returns 1 when the plate is drawn as a palette tint this frame (the object stays hidden) */
static int white_fade(s32 t, s32 obj)
{
    int v;
    u32 a;
    if (obj != END_WHITE_PLATE && t != tint_task) return 0;
    v = (obj == END_WHITE_PLATE && OBJ_SHADE(V16(t + 0x48))) ? WORK(t, 0x0F) & 0x3F : 0;
    if (obj == END_WHITE_PLATE && v) {
        a = (0x3F - v) << 2;                    /* opacity 0..252 (alpha table: 0 opaque .. 0x3F transparent) */
        if (t != tint_task || a != tint_amt) { pal_tint(a); tint_amt = a; tint_task = t; }
        ObjHide(V16(t + 0x48));
        return 1;
    }
    if (t == tint_task) { pal_tint(0); tint_task = 0; tint_amt = 0; }
    return 0;
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
    if (white_fade(t, obj)) return;
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
    cur_slot = slot; tint_task = 0; tint_amt = 0;
    for (p = end_pals; p->slot >= 0; p++) {
        if (p->slot != slot) continue;
        gfx_copy((void *)p->pal, p->gfx, 256 * 4);
    }
}

#define SOLO_SLOT       26                          /* T[6] in src/story.c: Morrigan alone or with Aine */
#define P1_CHAR         V8(0x06055058)
#define CHAR_MORRIGAN   7

/* player: G_Ending's player number for the ending task's w0 (stack @(0x14,r15)) */
int gb2_end_slot(int count, int last, s16 *player)
{
    int slot = gb2_demo_slot(count, last), i;
    for (i = 0; i < END_N; i++) if (end_slots[i] == slot) { load_ending(slot); break; }
    if (slot == SOLO_SLOT && count == 2) *player = P1_CHAR == CHAR_MORRIGAN ? 1 : 2;
    return slot;
}
