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
 * the letterbox masks, the plate itself) is left alone.
 * Board findings (PCB video 2026-09-30, reproduced in MAME frame by frame): the sprite list is shown a frame after it
 * is built, palette writes at once.  Restoring the colours when the plate turned opaque showed the old picture in full
 * colour for one frame (the list on screen still had the plate hidden), so under an opaque plate the tint is undone
 * two frames later by gb2_end_frame (G_Ending's per-frame call), once the plate is surely on screen.  Reading the
 * original colours back through the gfx ROM-test window every frame made random pixels shimmer on the board (the
 * window shares the gfx ROM with the sprite engine), so load_ending keeps a RAM copy (END_PAL_CACHE, after the blob). */
#define OBJ_SHADE(o)    ((VU8(0x06040079 + (o) * 0x24) >> 4) & 7)   /* alpha slot set by ChangeShadeObj */
#define PAL_CACHE       ((const u32 *)END_PAL_CACHE)
#define VBL_COUNT       0x0604C21C              /* vblank job queue: u16 count, {fn, a, b, c} x 32 */
#define VBL_JOBS        0x0604C220
static int cur_slot;                            /* the loaded ending slot (0 = none: no ending uses slot 0) */
static u32 tint_amt;
static s32 tint_task;
static int tint_hold;                           /* frames until the tint under an opaque plate is undone */
static int end_active;                          /* in G_Ending's frame call with one of her endings (gb2_objlist) */

/* a: 0 = the ending's colours .. 252 = (nearly) white, for one bank from its RAM copy s */
static void tint_bank(volatile u32 *d, const u32 *s, u32 a)
{
    u32 i;
    if (!a) { for (i = 0; i < 256; i++) d[i] = s[i]; return; }
    for (i = 0; i < 256; i++) {
        u32 c = s[i], r = c >> 24, g = (c >> 16) & 0xFF, b = (c >> 8) & 0xFF;
        r += ((255 - r) * a) >> 8; g += ((255 - g) * a) >> 8; b += ((255 - b) * a) >> 8;   /* SH-2: no shld */
        d[i] = (r << 24) | (g << 16) | (b << 8) | (c & 0xFF);
    }
}

static void pal_vblank(void);

/* returns 1 when the plate is drawn as a palette tint this frame (the object stays hidden) */
static int white_fade(s32 t, s32 obj)
{
    int v;
    u32 a;
    if (obj != END_WHITE_PLATE && t != tint_task) return 0;
    v = (obj == END_WHITE_PLATE && OBJ_SHADE(V16(t + 0x48))) ? WORK(t, 0x0F) & 0x3F : 0;
    if (obj == END_WHITE_PLATE && v) {
        a = (0x3F - v) << 2;                    /* opacity 0..252 (alpha table: 0 opaque .. 0x3F transparent) */
        tint_amt = a; tint_task = t;            /* written in vblank (pal_vblank) */
        tint_hold = 0;
        ObjHide(V16(t + 0x48));
        return 1;
    }
    if (obj == END_WHITE_PLATE) {               /* opaque plate: drawn; the tint goes once it is on screen */
        if (tint_task && !tint_hold) tint_hold = 2; /* armed once: some tasks re-put the plate every frame */
        return 0;
    }
    if (t == tint_task) { tint_task = 0; tint_amt = 0; tint_hold = 0; }
    return 0;
}

/* G_Ending's frame call (its WaitFrame literal 0x0601FB24 points here, src/patches.txt) */
int gb2_end_frame(void)
{
    int r;
    end_active = cur_slot != 0;
    if (cur_slot && V16(VBL_COUNT) < 32) {          /* palette writes in vblank: engine job queue (FUN_06027868) */
        u16 n = V16(VBL_COUNT);
        V16(VBL_COUNT) = n + 1;
        V32(VBL_JOBS + n * 16) = (u32)pal_vblank;
    }
    r = WaitFrameR();
    end_active = 0;
    if (tint_hold && --tint_hold == 0) { tint_task = 0; tint_amt = 0; }
    return r;
}

/* ---- picture cross-fades ----------------------------------------------------------------------------------------
 * The picture task w0C fades a new picture in over the old one (shade slot, w0F 0x3F -> 0), which the PS5 cannot do
 * with 8bpp sprites.  For the long ones (end_dissolves, tools/port_endings.py DISSOLVES) the build pre-blends
 * END_DISSOLVE_STEPS - 1 pictures; the one for the current alpha is drawn opaque instead of the new picture (its
 * own palette bank, loaded with the ending: no palette change during the fade).  The shade register is set opaque
 * too, so MAME shows the same as the board.  Returns the composite to draw, or 0 while nothing of the new picture
 * shows yet. */
static s32 dissolve(s32 t, s32 obj)
{
    const struct end_dissolve *d;
    int o = V16(t + 0x48), slot = OBJ_SHADE(o), v, k;
    if (!slot) return obj;
    for (d = end_dissolves; d->slot >= 0; d++) if (d->slot == cur_slot && d->pic == (u32)obj) break;
    if (d->slot < 0) return obj;
    v = WORK(t, 0x0F) & 0x3F;
    k = (((0x3F - v) * END_DISSOLVE_STEPS + 0x1F) * 0x410) >> 16;     /* round(opacity * steps); SH-2: no divide */
    VU8(0x2405FFE0 + slot) = 0;
    if (k >= END_DISSOLVE_STEPS) return obj;
    return k <= 0 ? 0 : (s32)(d->first + (k - 1) * d->stride);
}

/* ---- sprite load ------------------------------------------------------------------------------------------------
 * PCB video (2026-09-30, IMG_2404): stray pixels at the picture edges and in the text, i.e. where the letterbox masks
 * cover the pictures' overhang.  Her endings asked the sprite engine for 2-3 times the 8bpp data per scanline of the
 * stock endings (MAME sprite lists: stock <= 536 bytes per line, hers up to 1550), and the board evidently drops
 * pixels then; MAME does not model the limit.  Two kinds of sprites nobody can see are left out of the sprite list:
 *  - duplicates: after every picture fade the engine keeps the picture in both w0C and w10, the same composite at the
 *    same place;
 *  - pictures under an opaque picture that covers the whole letterbox window while the masks show: the base picture
 *    layer (HardObjPriority 2) stays under the close-ups, their backdrops and the next scene's pictures.
 * gb2_objlist runs in place of the sprite-list build of WaitFrame (its literal 0x060289F8, src/patches.txt), after all
 * tasks of the frame: it marks those objects hidden, builds the list and clears the marks again, so the scripts never
 * see a change.  Only while G_Ending runs one of her endings (gb2_end_frame); elsewhere it is one test.  Levels:
 * vidreg 0x08 maps HardObjPriority 0/1/2/3 to sprite levels 2/3/1/7; within a level the higher ObjPriority is on top.
 * (The masks are 4bpp too, tools/port_endings.py MASK_COMP.) */
#define OBJ_N           48
#define OBJ_COMP(o)     V32(0x0604006C + (o) * 0x24)
#define OBJ_X(o)        ((s16)V16(0x06040070 + (o) * 0x24))
#define OBJ_Y(o)        ((s16)V16(0x06040072 + (o) * 0x24))
#define OBJ_XY(o)       V32(0x06040070 + (o) * 0x24)
#define OBJ_LEVEL(o)    (VU8(0x06040074 + (o) * 0x24) & 3)
#define OBJ_PRIO(o)     VU8(0x06040077 + (o) * 0x24)
#define OBJ_FLAGS(o)    V16(0x0604007C + (o) * 0x24)
#define OBJ_HIDDEN(o)   (OBJ_FLAGS(o) & 0x8000)
#define IN_BLOB(c)      ((u32)(c) - END_BLOB_BASE < 0x0C000)
#define WIN_X0 0                                /* letterbox window: object x/y + composite x/y (hardware y/x) */
#define WIN_X1 224
#define WIN_Y0 112
#define WIN_Y1 272
#define ObjListBuild    FN(void, 0x06023FFC, (void))

static int above(int j, int o)
{
    static const u8 level[4] = { 2, 3, 1, 7 };
    int lj = level[OBJ_LEVEL(j)], lo = level[OBJ_LEVEL(o)];
    return lj > lo || (lj == lo && OBJ_PRIO(j) > OBJ_PRIO(o));
}

static int covered(int o)
{
    const struct end_opaque *r;
    int j;
    for (j = 0; j < OBJ_N; j++) {
        if (j == o || OBJ_HIDDEN(j) || OBJ_SHADE(j) || !above(j, o)) continue;
        for (r = end_opaque; r->comp; r++) if (r->comp == (u32)OBJ_COMP(j)) break;
        if (r->comp && OBJ_X(j) + r->x0 <= WIN_X0 && OBJ_X(j) + r->x1 >= WIN_X1
                    && OBJ_Y(j) + r->y0 <= WIN_Y0 && OBJ_Y(j) + r->y1 >= WIN_Y1) return 1;
    }
    return 0;
}

/* The list builder can draw objects twice: it splits its list 0x06042BEC at two boundaries (0x06043602, 0x06043606:
 * prefix counts of priority bands) and FUN_06024778 sends [0, first) and later [second, end) to the sprite engine;
 * with her close-up priorities (0x0C-0x0F) the second boundary can come out below the first, so the entries between
 * go out twice (the close-up scene's bokeh backdrop in Jiki6 + Jiki1: 4 full-width 8bpp sprites instead of 2). */
#define LIST_SPLIT1     V16(0x06043602)
#define LIST_SPLIT2     V16(0x06043606)

/* vblank job (queued by gb2_end_frame): the white-fade tint for the banks of the pictures on screen, from the RAM
 * copy, only where the amount changed; when the fade is over every bank goes back (a plain copy).  PCB video
 * IMG_2435/2436: rewriting all the ending's banks (up to 13 x 256 colours) every frame during the display made
 * pixels shimmer while the castle (Jiki6 + Jiki2) and Marion's slide-up (Jiki6 + Jiki1) faded in from white - the
 * game itself changes colours only in vblank (FUN_06028564).  Being in vblank, the change also lands exactly between
 * the frame whose sprite list it belongs to and the next. */
static u8 bank_amt[16];                         /* tint applied per bank (bank >> 4) */

static void pal_vblank(void)
{
    const struct end_pal *p;
    const u32 *s = PAL_CACHE;
    u8 vis[16];
    int o, i;
    for (i = 0; i < 16; i++) vis[i] = 0;
    if (tint_amt)
        for (o = 0; o < OBJ_N; o++) {
            s32 c = OBJ_COMP(o);
            int n;
            if (OBJ_HIDDEN(o) || !IN_BLOB(c)) continue;
            n = ((V16(c + 2) >> 8) >> 2) & 0x3F;      /* SH-2 shifts: 1, 2, 8, 16 */
            if (!n) n = 1;
            for (i = 0; i < n; i++) vis[(VU8(c + 12 * i + 8) >> 2) >> 2] = 1;
        }
    for (p = end_pals; p->slot >= 0; p++) {
        int k = ((u16)p->bank >> 2) >> 2;
        u32 want;
        if (p->slot != cur_slot || p->bank >= 0xE0) continue;
        want = vis[k] ? tint_amt : tint_amt ? bank_amt[k] : 0;
        if (want != bank_amt[k]) { tint_bank((volatile u32 *)p->pal, s, want); bank_amt[k] = want; }
        s += 256;
    }
}

/* Sprites entirely under a letterbox mask (hardware x < 112 or >= 272) and below the masks' level (HardObjPriority 0
 * or 2 - the masks are 1) cannot be seen: the pictures' overhang, e.g. the second part of a close-up sliding in.
 * They are moved below the screen after the list build.  Sprite entries: w0 = y << 16 | x (10 bits each, x wraps
 * at 1024), w1 bits 8-11 width - 1 (cells), 12-13 HardObjPriority; indices in 0x06042BEC [0, count 0x060435EC). */
#define SPR(i)          ((volatile u32 *)(0x24000000 + ((i) & 0x3FF) * 16))
#define SPR_LIST        ((volatile u16 *)0x06042BEC)
#define SPR_TOTAL       V16(0x060435EC)

static void cull_masked(void)
{
    int i, n = SPR_TOTAL;
    if (n > 0x300) return;
    for (i = 0; i < n; i++) {
        volatile u32 *s = SPR(SPR_LIST[i]);
        u32 w0 = s[0], w1 = s[1];
        int x = w0 & 0x3FF, w = (((w1 >> 8) & 15) + 1) * 16, pri = ((w1 >> 8) >> 2) >> 2 & 3;   /* SH-2 shifts: 1, 2, 8, 16 */
        if (pri == 1 || pri == 3) continue;                       /* the masks' level and above */
        if (x >= 512) x -= 1024;
        if (x + w <= WIN_Y0 || x >= WIN_Y1) s[0] = (w0 & 0xFFFF) | 0x03000000;
    }
}

void gb2_objlist(void)
{
    u8 cut[OBJ_N];
    int n = 0, o, j, masks = 0;
    if (end_active) {
        for (o = 0; o < OBJ_N; o++) if (!OBJ_HIDDEN(o) && OBJ_COMP(o) == END_MASK) masks = 1;
        for (o = 0; o < OBJ_N; o++) {
            s32 c = OBJ_COMP(o);
            int dup = 0;
            if (OBJ_HIDDEN(o) || !IN_BLOB(c) || c == END_MASK) continue;
            /* of two copies the one without a shade slot stays: the alpha register acts at once while the list goes
             * out a frame later, so on the first frame of a fade the w0C copy would already be see-through */
            for (j = 0; j < OBJ_N; j++)
                if (j != o && !OBJ_HIDDEN(j) && OBJ_COMP(j) == c && OBJ_XY(j) == OBJ_XY(o)
                    && (OBJ_SHADE(o) && !OBJ_SHADE(j) || !OBJ_SHADE(o) == !OBJ_SHADE(j) && j < o)) dup = 1;
            if (dup || (masks && covered(o))) { OBJ_FLAGS(o) |= 0x8000; cut[n++] = o; }
        }
    }
    ObjListBuild();
    while (n) { o = cut[--n]; OBJ_FLAGS(o) &= 0x7FFF; }
    if (end_active && (s16)LIST_SPLIT2 < (s16)LIST_SPLIT1) LIST_SPLIT2 = LIST_SPLIT1;
    if (end_active && masks) cull_masked();
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
    if (obj && V32(obj) != TEXT_MAGIC && !(obj = dissolve(t, obj))) { ObjHide(V16(t + 0x48)); return; }
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
    cur_slot = slot; tint_task = 0; tint_amt = 0; tint_hold = 0;
    { int k; for (k = 0; k < 16; k++) bank_amt[k] = 0; }
    {
        u32 *c = (u32 *)END_PAL_CACHE;
        for (p = end_pals; p->slot >= 0; p++) {
            if (p->slot != slot) continue;
            gfx_copy((void *)p->pal, p->gfx, 256 * 4);
            if (p->bank < 0xE0) { gfx_copy(c, p->gfx, 256 * 4); c += 256; }   /* pal_tint's originals */
        }
    }
}

#define SOLO_SLOT       26                          /* T[6] in src/story.c: Morrigan alone or with Aine */
#define P1_CHAR         V8(0x06055058)
#define CHAR_MORRIGAN   7

/* player: G_Ending's player number for the ending task's w0 (stack @(0x14,r15)) */
int gb2_end_slot(int count, int last, s16 *player)
{
    int slot = gb2_demo_slot(count, last), i;
    cur_slot = 0;                                   /* a stock ending: no palette fade, no sprite culling */
    for (i = 0; i < END_N; i++) if (end_slots[i] == slot) { load_ending(slot); break; }
    if (slot == SOLO_SLOT && count == 2) *player = P1_CHAR == CHAR_MORRIGAN ? 1 : 2;
    return slot;
}
