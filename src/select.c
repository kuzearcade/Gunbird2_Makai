/* Character select screen - C port of arcade 0x0601CDFC (DC twin FUN_8C039CC0) with the Dreamcast's Morrigan
 * secret added: with the cursor on '?' (slot 5), Up picks Morrigan (character 7) once she is unlocked
 * (maintenance code 5-1-9-9-4), just as Down picks Aine when the Aine flag is 2.
 *
 * Everything not Morrigan-related follows the arcade code (re/port/select_arcade.c / .ann); the Morrigan parts
 * follow the DC code (re/port/select_dc.c):
 *  - '?' shows character rot/3, rot advancing every frame; a matched secret pins rot to 0xF (Aine) / 0x12
 *    (Morrigan); matching one secret cancels the other
 *  - rot range: /3 <= 4 without the Aine flag, 5 with it, 6 with Aine flag + Morrigan; in 2P, when rot hits the
 *    other player's character it skips 3 ahead, wrapping at /3 > 5 (> 6 with Morrigan)
 *  - initial rot: Random(0x12) with Morrigan unlocked, else Random(0xF)
 * Slot values: bits 0-3 slot, 0x10 = decided.  Objects: see enum. */
#include "arcade.h"
#include "gen_gfx.h"

#define PlayerSet       FN(void, 0x06013188, (int, int))
#define GameStartSetup  FN(void, 0x06023D7E, (void))
#define SlotIcon        FN(void, 0x0601EA38, (int, int, int, int))
#define CreditCheck     FN(int,  0x0602AEA0, (int, int))
#define CreditUse       FN(void, 0x0602AF22, (int, int))

#define SEQHDR          V32(0x2608002C)
#define PLAYERS         VU16(0x0604C8C8)
#define IN_TRIG(p)      VU8(0x0604C628 + (p))
#define IN_HELD(p)      VU8(0x0604C624 + (p))
#define OBJ_ATTR(o)     VU8(0x06040079 + (s16)((o) * 0x24))
#define SND_SELECT(i)   V16(0x0603210A + (i) * 2)
#define PORT_ANIM(i)    ((const s16 *)(0x060320A8 + (i) * 4))                     /* {frames, delay} */
#define REC(p, i)       ((const s16 *)((p ? 0x060320E4 : 0x060320C0) + (i) * 6))  /* {prio, x, y} */
#define AINE_CODE       VU8(0x06032108)   /* 0x40 = Down */
#define MORRIGAN_CODE   0x80              /* Up (DC 0x8C087C9F) */
#define MORRIGAN_VOICE  0x150             /* DC select voice table [6] */
#define ROT_AINE        0xF
#define ROT_MORRIGAN    0x12
#define BIT(p)          ((p) ? 2 : 1)       /* no dynamic shifts on SH-2 */

enum { O_ICON0, O_CUR1, O_CUR2, O_PORT1, O_PORT2, O_TIMEBG, O_TIMEDIG, O_ICON1, O_ICON2, O_ICON3, O_ICON4,
       O_QMARK, O_SHAD0, O_QSHAD = 17 };

extern void gb2_pal_load_group(const u32 *pal, u16 count);

/* Morrigan entries of the per-character tables (DC: 7th entries) */
static const s16 anim_morrigan[2] = { 1, 4 };
static const s16 rec_morrigan[2][3] = { { 7, 0, 0 }, { 8, 0, 0 } };

/* small unsigned quotient without a divide: the SH-4 cc1 lowers constant divisions to SH-3+ shad */
static int udiv(int x, int d) { int q = 0; while (x >= d) { x -= d; q++; } return q; }
#define ROT3(r) udiv(r, 3)

static s32 gt;                                  /* global object table (SEQ hdr +0x1C) */
#define GT(off) ((const void *)V32(gt + (off)))

static int voice(int c) { return c == 6 ? MORRIGAN_VOICE : SND_SELECT(c); }
static const s16 *port_anim(int c) { return c == 6 ? anim_morrigan : PORT_ANIM(c); }
static const s16 *rec(int p, int c) { return c == 6 ? rec_morrigan[p] : REC(p, c); }
static const void *icon(int c) { return c == 6 ? (const void *)obj_sel_icon : GT(0x198 + c * 4); }
/* 1P-mode portrait (gt+0x150 set) */
static const void *portrait(int c) { return c == 6 ? (const void *)obj_sel_portrait : GT(0x150 + c * 4); }
/* 2P-mode half portraits (gt+0x168 left / gt+0x180 right) */
static const void *side(int p, int c)
{
    if (c == 6) return p ? (const void *)obj_sel_side_2p : (const void *)obj_sel_side_1p;
    return GT((p ? 0x180 : 0x168) + c * 4);
}
static void slot_icon(int o, int c, int x, int y)
{
    if (c == 6) { ObjSetAnim(o, x, y, obj_sel_icon, 6, 4, 0x200); ObjShow(o); }   /* DC SlotIcon case 6 */
    else SlotIcon(o, c, x, y);
}
static void portrait_anim(int o, int c, int x, int y)
{
    const s16 *an = port_anim(c);
    ObjSetAnim(o, x, y, portrait(c), an[0], an[1], 0x200);
}

/* rot advance for a '?' cursor that is not decided; other = the other player's slot (-1 in 1P) */
static s16 rot_next(s16 rot, int other)
{
    int max = SECRET_AINE == 0 ? 4 : (gb2_morrigan_enabled ? 6 : 5);
    rot++;
    if (ROT3(rot) > max) rot = 0;
    if (other >= 0 && (other & 0xF) == ROT3(rot)) {
        rot += 3;
        if (ROT3(rot) > (gb2_morrigan_enabled ? 6 : 5)) rot = 0;
    }
    return rot;
}

/* Left (d = -1) / Right (d = 1): move, skipping the other player's slot and the character the other
 * player's decided '?' stands for */
static u16 move(u16 s, int d, u16 other, s16 rot)
{
    do {
        s += d;
        if ((s16)s < 0) s = 5;
        if ((s16)s > 5) s = 0;
    } while (PLAYERS == 3 && ((other & 0xF) == (s & 0xF) || (other == 0x15 && ROT3(rot) == (s16)s)));
    return s;
}

int gb2_select(void)
{
    s16 o[18];
    u16 slot[2], refresh[2], wason[2];
    s16 run = 1, timer = 900, delay = 0x1E, rot, bufi = 0, i, p;
    u8 buf[1];
    int a_hit = 0, a_draw = 1, m_hit = 0, m_draw = 1;
    s32 hdr8;
    static const s16 ix[6] = { 0x1A, 0x3C, 0x5E, 0x80, 0xA2, 0xC4 };
    static const s16 ioff[6] = { 0x198, 0x19C, 0x1A0, 0x1A4, 0x1A8, 0x1C0 };
    static const s16 ifr[6][2] = { { 6, 4 }, { 4, 4 }, { 4, 2 }, { 4, 2 }, { 8, 4 }, { 36, 2 } };
    static const s8 iobj[6] = { O_ICON0, O_ICON1, O_ICON2, O_ICON3, O_ICON4, O_QMARK };

    gt = V32(SEQHDR + 0x1C);
    hdr8 = V32(SEQHDR + 8);
    slot[0] = VU16(0x06032116); slot[1] = VU16(0x06032118);
    refresh[0] = VU16(0x0603211A); refresh[1] = VU16(0x0603211C);
    wason[0] = VU16(0x0603211E); wason[1] = VU16(0x06032120);
    V16(0x0604C750) = 0;
    V16(0x0605CCDE) = 0x134;
    SndInit1(); SndInit2(); SndInit3(7);
    V16(0x06060CAC) = 0; V16(0x06060CAE) = 0;
    for (i = 0; i < 18; i++) o[i] = ObjAlloc();
    buf[0] = 0;
    Random(gb2_morrigan_enabled ? ROT_MORRIGAN : 0xF);
    rot = Random(gb2_morrigan_enabled ? ROT_MORRIGAN : 0xF);
    CreateTask(2, V32(gt + 0x1BC));
    for (i = 0; i < 5; i++) if (WaitFrameR()) return 7;
    ScreenClear(0, 0x14, 0, 6);
    CreateTask(4, V32(hdr8 + 0x4C));
    V16(0x06040016) = 0; V16(0x06040018) = 0; V16(0x060799F4) = 0;
    V16(0x06040014) = 0; V32(0x0604001C) = 0; V16(0x06043600) = 0;
    if (gb2_morrigan_enabled) gb2_pal_load_group(pal_select, pal_select_count);

    for (i = 0; i < 6; i++) {
        ObjSetAnim(o[iobj[i]], ix[i], 0x30, GT(ioff[i]), ifr[i][0], ifr[i][1], 0x200);
        ObjShow(o[iobj[i]]);
    }
    for (i = 0; i < 6; i++) {
        ObjSetAnim(o[O_SHAD0 + i], ix[i] + 2, 0x2E, GT(ioff[i]), ifr[i][0], ifr[i][1], 0x200);
        ObjShade(o[O_SHAD0 + i], 0x30);
        ObjShow(o[O_SHAD0 + i]);
    }
    ObjSet(o[O_TIMEBG], 0x56, 0x14, GT(0x3C)); ObjShow(o[O_TIMEBG]);
    ObjSet(o[O_TIMEDIG], 0x76, 0x14, (const u8 *)GT(0x40) + udiv(timer, 90) * 0xC); ObjShow(o[O_TIMEDIG]);
    AnmPrtSet(o[O_ICON0], 0x14); AnmPrtSet(o[O_ICON1], 0x14); AnmPrtSet(o[O_ICON2], 0x14); AnmPrtSet(o[O_ICON3], 0x14);
    AnmPrtSet(o[O_ICON4], 0x13); AnmPrtSet(o[O_QMARK], 0x13);
    for (i = 0; i < 6; i++) AnmPrtSet(o[O_SHAD0 + i], 0x13);
    AnmPrtSet(o[O_CUR1], 0x16); AnmPrtSet(o[O_CUR2], 0x16);
    AnmPrtSet(o[O_PORT1], 6); AnmPrtSet(o[O_PORT2], 5);
    AnmPrtSet(o[O_TIMEBG], 0x19); AnmPrtSet(o[O_TIMEDIG], 0x1A);
    ObjFlag(o[O_PORT1], 0); ObjFlag(o[O_PORT2], 0);
    MusicSet(0);

    for (;;) {
        if (run == 0) {
            ObjHide(o[O_TIMEBG]); ObjHide(o[O_TIMEDIG]);
            for (i = 0; i < 0x28; i++) if (WaitFrameR()) return 7;
            SndInit2();
            ScreenClear(2, 10, 0, 6);
            for (i = 0; i < 10; i++) if (WaitFrameR()) return 7;
            if ((slot[0] & 0xF) == 5) slot[0] = ROT3(rot);
            if ((slot[1] & 0xF) == 5) slot[1] = ROT3(rot);
            if (PLAYERS & 1) PlayerSet(0, (slot[0] & 0xF) + 1);
            if (PLAYERS & 2) PlayerSet(1, (slot[1] & 0xF) + 1);
            V32(0x06055174) = PLAYERS == 3;
            GameStartSetup();
            return 1;
        }
        if (WaitFrameR()) return 7;
        if (timer) timer--;
        if (delay) delay--;
        if (timer == 0) {                                   /* time up: decide for everyone */
            for (p = 0; p < 2; p++) {
                if (!(PLAYERS & BIT(p))) continue;
                if (!(slot[p] & 0x10)) PlaySound(voice((slot[p] & 0xF) == 5 ? ROT3(rot) : slot[p] & 0xF));
                if ((slot[p] & 0xF) == 5) refresh[p] = 1;
                slot[p] |= 0x10;
            }
            run = 0;
        }

        for (p = 0; p < 2; p++) {                           /* cursor movement, code input on '?' */
            if ((s16)slot[p] >= 10) continue;
            if ((IN_TRIG(p) & 0x10) && (PLAYERS & BIT(p))) {
                refresh[p] = 1; slot[p] = move(slot[p], -1, slot[p ^ 1], rot); PlaySound(0x54);
            }
            if ((IN_TRIG(p) & 0x20) && (PLAYERS & BIT(p))) {
                refresh[p] = 1; slot[p] = move(slot[p], 1, slot[p ^ 1], rot); PlaySound(0x54);
            }
            if ((slot[p] & 0xF) == 5 && (PLAYERS & BIT(p)) && (IN_TRIG(p) & 0xC0)) {
                buf[bufi] = IN_TRIG(p);
                if (++bufi > 0) bufi = 0;
            }
        }

        /* secrets (DC order: Aine, then Morrigan; a match cancels the other) */
        for (i = 0; i < 2; i++) {
            int on_q = (slot[0] & 0xF) == 5 || (slot[1] & 0xF) == 5;
            int *hit = i ? &m_hit : &a_hit, *draw = i ? &m_draw : &a_draw;
            int c = i ? 6 : 5;
            if (i == 0 ? SECRET_AINE != 2 : !gb2_morrigan_enabled) continue;
            if (!on_q) { *hit = 0; continue; }
            if (*hit) continue;
            *hit = buf[bufi] == (i ? MORRIGAN_CODE : AINE_CODE);
            if (!*hit) { *draw = 1; continue; }
            if (*draw) {
                int q1 = (slot[0] & 0xF) == 5;
                slot_icon(o[O_QMARK], c, 0xC4, 0x30);
                slot_icon(o[O_QSHAD], c, 0xC6, 0x2E);
                portrait_anim(o[q1 ? O_PORT1 : O_PORT2], c, 0, 0);
                portrait_anim(o[q1 ? O_PORT2 : O_PORT1], c, 8, -8);
                ObjShow(o[O_PORT2]); ObjShow(o[O_PORT1]);
                *draw = 0;
            }
            if (i) { a_hit = 0; a_draw = 1; } else { m_hit = 0; m_draw = 1; }
        }

        for (p = 0; p < 2; p++) {                           /* decide / join */
            int bit = BIT(p), other = BIT(p ^ 1);
            u8 in = IN_TRIG(p);
            int dec = 0;
            if (!(in & 1)) dec = (in & 0xE) && (PLAYERS & bit) && delay < 1;
            else if (!(PLAYERS & bit)) {
                if (CreditCheck(p, 0)) {
                    CreditUse(p, 0);
                    PLAYERS = PLAYERS | bit;
                    timer = 900;
                    slot[p] = p ? 3 : 1;
                    while ((slot[p ^ 1] & 0xF) == (slot[p] & 0xF) ||
                           ((slot[p ^ 1] & 0xF) == 5 && ROT3(rot) == (s16)slot[p]))
                        if ((s16)++slot[p] > 5) slot[p] = 0;
                }
            } else dec = delay < 1;
            if (!dec) continue;
            if ((s16)slot[p] < 0x10) {
                PlaySound(voice((slot[p] & 0xF) == 5 ? ROT3(rot) : slot[p] & 0xF));
                if ((in & 1) && (IN_HELD(p) & 0x80)) V16(p ? 0x06060CAE : 0x06060CAC) = 1;
            }
            if ((slot[p] & 0xF) == 5) refresh[p] = 1;
            slot[p] |= 0x10;
            if (!(PLAYERS & other) || (s16)slot[p ^ 1] > 0xF) {
                timer = 1;
                ObjHide(o[O_TIMEBG]); ObjHide(o[O_TIMEDIG]);
            }
        }

        if (PLAYERS == 3) {
            for (p = 0; p < 2; p++) {
                if ((slot[p] & 0xF) == 5) {
                    if (!(slot[p] & 0x10)) {
                        if (a_hit) rot = ROT_AINE;
                        else if (m_hit) rot = ROT_MORRIGAN;
                        else {
                            rot = rot_next(rot, slot[(p + 1) % 2]);
                            ObjSet(o[O_QMARK], 0xC4, 0x30, icon(ROT3(rot)));
                            ObjSet(o[O_QSHAD], 0xC6, 0x2E, icon(ROT3(rot)));
                        }
                    } else if (refresh[p]) {
                        slot_icon(o[O_QMARK], ROT3(rot), 0xC4, 0x30);
                        slot_icon(o[O_QSHAD], ROT3(rot), 0xC6, 0x2E);
                        refresh[p] = 0;
                    }
                    wason[p] = 1;
                } else if (wason[p] == 1) {
                    buf[0] = 0;
                    wason[p] = 0;
                    ObjSetAnim(o[O_QMARK], 0xC4, 0x30, GT(0x1C0), 36, 2, 0x200); ObjShow(o[O_QMARK]);
                    ObjSetAnim(o[O_QSHAD], 0xC6, 0x2E, GT(0x1C0), 36, 2, 0x200); ObjShow(o[O_QSHAD]);
                }
            }
            ObjSet(o[O_CUR1], (slot[0] & 0xF) * 0x22 + 0x1A, 0x30, GT(0x148)); ObjShow(o[O_CUR1]);
            ObjSet(o[O_CUR2], (slot[1] & 0xF) * 0x22 + 0x1A, 0x30, GT(0x14C)); ObjShow(o[O_CUR2]);
            ObjShade(o[O_PORT1], 0);
            for (p = 0; p < 2; p++) {
                s16 ob = o[O_PORT1 + p];
                int c = (slot[p] & 0xF) == 5 ? ROT3(rot) : slot[p] & 0xF;
                const s16 *r = rec(p, c);
                ObjSet(ob, r[1], r[2], side(p, c));
                AnmPrtSet(ob, r[0]);
                if (p) ObjShade(ob, 0);
                OBJ_ATTR(ob) &= 0x8F;
                ObjShow(ob);
            }
            V16(0x06055054) = 8;
            V16(0x06055104) = 8;
        } else {
            s16 port, shad;
            p = (PLAYERS & 1) ? 0 : 1;
            port = o[p ? O_PORT2 : O_PORT1];
            shad = o[p ? O_PORT1 : O_PORT2];
            if ((slot[p] & 0xF) == 5) {
                if (!(slot[p] & 0x10)) {
                    if (a_hit) rot = ROT_AINE;
                    else if (m_hit) rot = ROT_MORRIGAN;
                    else {
                        rot = rot_next(rot, -1);
                        ObjSet(o[O_QMARK], 0xC4, 0x30, icon(ROT3(rot)));
                        ObjSet(o[O_QSHAD], 0xC6, 0x2E, icon(ROT3(rot)));
                    }
                }
                wason[p] = 1;
            } else if (wason[p]) {
                buf[0] = 0;
                wason[p] = 0;
                ObjSetAnim(o[O_QMARK], 0xC4, 0x30, GT(0x1C0), 36, 2, 0x200); ObjShow(o[O_QMARK]);
                ObjSetAnim(o[O_QSHAD], 0xC6, 0x2E, GT(0x1C0), 36, 2, 0x200); ObjShow(o[O_QSHAD]);
            }
            ObjSet(o[O_CUR1 + p], (slot[p] & 0xF) * 0x22 + 0x1A, 0x30, GT(p ? 0x14C : 0x148));
            ObjShow(o[O_CUR1 + p]);
            if ((slot[p] & 0xF) == 5) {
                if (!(slot[p] & 0x10)) {
                    if (!a_hit && !m_hit) {
                        ObjSet(port, 0, 0, portrait(ROT3(rot)));
                        ObjSet(shad, 8, -8, portrait(ROT3(rot)));
                    }
                } else if (refresh[p]) {
                    slot_icon(o[O_QMARK], ROT3(rot), 0xC4, 0x30);
                    slot_icon(o[O_QSHAD], ROT3(rot), 0xC6, 0x2E);
                    portrait_anim(port, ROT3(rot), 0, 0);
                    portrait_anim(shad, ROT3(rot), 8, -8);
                    refresh[p] = 0;
                }
            } else if (refresh[p]) {
                portrait_anim(port, slot[p] & 0xF, 0, 0);
                portrait_anim(shad, slot[p] & 0xF, 8, -8);
                refresh[p] = 0;
            }
            AnmPrtSet(port, 6); ObjShade(port, 0); OBJ_ATTR(port) = 0; ObjShow(port);
            AnmPrtSet(shad, 5); ObjShade(shad, 0x30);
            /* original quirk: the P2-only shadow copies its attribute byte from shadow icon 0 */
            OBJ_ATTR(shad) = (OBJ_ATTR(p ? o[O_SHAD0] : shad) & 0x8F) | 0x20;
            ObjShow(shad);
            V16(p ? 0x06055104 : 0x06055054) = 8;
        }
        ObjSet(o[O_TIMEDIG], 0x76, 0x14, (const u8 *)GT(0x40) + udiv(timer, 90) * 0xC);
    }
}
