/* Morrigan's sub-shot (port of DC shot.c NewSubShot_Jiki6 @ 0x8C06B7A0).
 * Unlike the six arcade characters (C-coded sub-shots), Morrigan's sub-shot spawns seq tasks running the
 * script at chardef+0x7C; count / limit per power level come from the SEQ hdr+0x34 table (0x0605D27C). */
#include "arcade.h"

#define PLAYER(p)         (0x06055000 + (p) * 0xB0)
#define P_X(p)            V16(PLAYER(p) + 0x10)
#define P_Y(p)            V16(PLAYER(p) + 0x14)
#define P_CHARDEF(p)      V32(PLAYER(p) + 0x34)
#define P_SUB_ROT(p)      VU16(PLAYER(p) + 0x4A)
#define P_SUB_ACTIVE(p)   V16(PLAYER(p) + 0x4E)
#define P_CHARNO(p)       V8(PLAYER(p) + 0x58)
#define P_SHOTLV(p)       V8(PLAYER(p) + 0x59)
#define P_POWER(p)        V16(PLAYER(p) + 0x5A)
#define SUBSHOT_TABLE     V32(0x0605D27C)

#define CreateTask        FN(s32, 0x0600C25E, (int, s32))   /* dc_8c059c20: (type, script) -> task */

int gb2_newsubshot_jiki6(s16 p)
{
    s32 entry = V32(SUBSHOT_TABLE + (P_CHARNO(p) - 1) * 4) + P_POWER(p) * 0x14;
    s16 count = V16(entry + 0xE);
    int i;

    if (V16(entry + 0xC) < P_SUB_ACTIVE(p) + count) return 0;
    for (i = 0; i < count; i++) {
        s32 task, seq;
        if (count <= (s16)P_SUB_ROT(p)) P_SUB_ROT(p) = 0;
        task = CreateTask(3, V32(P_CHARDEF(p) + 0x7C));
        seq = V32(task + 0x20);
        V32(seq + 0x1C) = (s32)P_X(p) << 16;
        V32(seq + 0x20) = (s32)P_Y(p) << 16;
        V16(task + 0x30) = P_X(p);
        V16(task + 0x32) = P_Y(p);
        V32(task + 0x80) = P_SHOTLV(p);
        V32(task + 0x84) = P_SUB_ROT(p);
        V32(task + 0x88) = p;
        P_SUB_ROT(p) = P_SUB_ROT(p) + 1;
        P_SUB_ACTIVE(p) = P_SUB_ACTIVE(p) + 1;
    }
    PlaySound(0x15A);
    return 1;
}

/* NewSubShot dispatch (arcade 0x0601A342 jumps through the literal at 0x0601A398) */
const void *const gb2_subshot_dispatch[7] = {
    (const void *)0x0601970C, (const void *)0x060198CC, (const void *)0x06019B3C,
    (const void *)0x06019DB0, (const void *)0x06019FA8, (const void *)0x0601A19C,
    (const void *)gb2_newsubshot_jiki6,
};
