/* Gunbird 2 (arcade, PS5) - addresses of original game routines and variables used by the Morrigan patch.
 * Calling convention: Hitachi SHC (r4-r7 args, r0 result, r8-r14/MACH/MACL callee-saved) == gcc -mhitachi.
 * Names dc_XXXXXXXX are arcade routines whose Dreamcast twin lives at 0xXXXXXXXX (see re/arcade.sym). */
#ifndef ARCADE_H
#define ARCADE_H

typedef signed char s8;   typedef unsigned char u8;
typedef short s16;        typedef unsigned short u16;
typedef int s32;          typedef unsigned int u32;

#define V8(a)  (*(volatile s8  *)(a))
#define VU8(a) (*(volatile u8  *)(a))
#define V16(a) (*(volatile s16 *)(a))
#define VU16(a) (*(volatile u16 *)(a))
#define V32(a) (*(volatile s32 *)(a))
#define FN(ret, addr, args) ((ret (*) args)(addr))

/* ---- system ---------------------------------------------------------------------------------- */
#define WaitFrame          FN(void, 0x0602883C, (void))            /* dc_8c01f760 */
#define ScreenClear        FN(void, 0x0602763E, (int, int, int, int)) /* dc_8c021220 */
/* object (sprite/text slot) list at 0x06040060, 0x24 bytes each; +0x1C bit15 = hidden */
#define ObjAlloc           FN(s16,  0x060249D4, (void))             /* dc_8c0145e0 */
#define ObjSet             FN(void, 0x06024AFC, (int, int, int, const void *)) /* dc_8c014a60: static frame 0 */
#define ObjSetAnim         FN(void, 0x06024B6E, (int, int, int, const void *, int, int, int)) /* dc_8c014ec0: frames, delay, flags */
#define ObjShow            FN(void, 0x06024C8E, (int))              /* dc_8c015660 */
#define ObjHide            FN(void, 0x06024CA8, (int))              /* dc_8c0156c0 */
#define ObjShade           FN(void, 0x06024D10, (int, int))         /* dc_8c0157e0 */
#define AnmPrtSet          FN(void, 0x06024D42, (int, int))         /* priority */
#define ObjFlag            FN(void, 0x06024D54, (int, int))         /* dc_8c015940 */
#define CreateTask         FN(s32,  0x0600C25E, (int, s32))         /* dc_8c059c20 */
#define MusicSet           FN(void, 0x0602B292, (int))              /* dc_8c01bc60 */
#define SndInit1           FN(void, 0x0602B8D4, (void))             /* dc_8c01c8b2 */
#define SndInit2           FN(void, 0x0602B8FC, (void))             /* dc_8c01c920 */
#define SndInit3           FN(void, 0x0602BA56, (int))              /* dc_8c01cc40 */
#define WaitFrameR         FN(int,  0x0602883C, (void))             /* WaitFrame: nonzero = abort to attract */
#define TextClear          FN(void, 0x06000FEC, (void))             /* dc_8c072c20 */
#define PrintCentered      FN(s16,  0x0602A1EC, (const char *, int)) /* dc_8c026500: returns text slot */
#define PrintNumber        FN(void, 0x06029938, (s16 *, int, int, int)) /* dc_8c024ec6 */
#define PrintAt            FN(void, 0x06029288, (const char *, int, int)) /* dc_8c0239e0 */
#define PlaySound          FN(void, 0x0602B39A, (int))              /* dc_8c01bce0 */
#define Random             FN(s16,  0x06029200, (int))              /* dc_8c0238ac */
#define TEXT_ATTR(slot)    VU8(0x06040079 + (slot) * 0x24)
#define TASK_BUSY          V32(0x0604C620)

/* input: edge-triggered buttons, bit7 up, bit6 down, bit5 right, bit4 left, bit3 button1, bit0 start */
#define PAD_TRIG_P1        VU8(0x0605CB58)
#define PAD_TRIG_P2        VU8(0x0605CB59)
#define MAINT_MODE_REQ     V32(0x0605CB5C)

/* ---- EEPROM (93C56, 256 bytes) ---------------------------------------------------------------- */
#define EepRead            FN(void, 0x0602D184, (int, void *, int))
#define EepWrite           FN(u32,  0x0602D32C, (int, const void *, int))

/* secret block (EEPROM 0x18-0x1F, checksum 0x2E) */
#define SECRET_TIME        V32(0x0605CA48)   /* play time counter (frames) */
#define SECRET_PLAYS       V16(0x0605CA50)   /* credits played, 60000 max */
#define SECRET_COUNTED     V16(0x0605CA52)   /* this credit already counted */
#define SECRET_AINE        V16(0x0605CA54)   /* 0 none, 1 random may pick Aine, 2 Down on '?' */

/* routines called by "All data initialised" */
#define InitRankingA       FN(void, 0x0600341A, (void))
#define InitCharStats      FN(void, 0x060228CA, (void))
#define InitScoresA        FN(void, 0x06022BE4, (void))
#define InitRankingB       FN(void, 0x06003436, (void))
#define SaveCharStats      FN(void, 0x060228F4, (void))
#define SaveScores         FN(void, 0x06022CCC, (void))

/* ---- Morrigan patch state (lives in free RAM, see gb2.ld) -------------------------------------- */
#define EEP_MORRIGAN       0x20              /* 2 bytes, unused by the original game */
#define MORRIGAN_MAGIC     0x4D6F            /* 'Mo' = enabled */
extern s16 gb2_morrigan_enabled;

#endif
