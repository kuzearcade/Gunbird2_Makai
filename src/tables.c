/* Per-character tables extended from 6 to 7 entries (index 6 = Morrigan).
 * Originals live in the arcade SEQUENCE data; the SEQ header fields that point at them are repointed here
 * (see src/patches.txt: sym32 entries). */
#include "arcade.h"

extern const u8 MORRIGAN_CHARDEF[], MORRIGAN_SUBSHOT_TBL[];

/* SEQ header +0x30 (ROM 0x60048): character definition structs (0xB0 bytes each) */
const void *const gb2_chardef_table[7] = {
    (const void *)0x000CB2B4, (const void *)0x000CB364, (const void *)0x000CB414,
    (const void *)0x000CB4C4, (const void *)0x000CB574, (const void *)0x000CB624,
    MORRIGAN_CHARDEF,
};

/* SEQ header +0x34 (ROM 0x6004C): sub-shot parameters per power level (4 x 0x14 bytes) */
const void *const gb2_subshot_table[7] = {
    (const void *)0x000CB818, (const void *)0x000CB868, (const void *)0x000CB8B8,
    (const void *)0x000CB908, (const void *)0x000CB958, (const void *)0x000CB9A8,
    MORRIGAN_SUBSHOT_TBL,
};
