/* Stage demo scene selection for 7 characters (DC G_StageDemo 8C03D168).
 * The per-stage scene tables have 27 slots (src/gen_story.c): slot = T[a-1] + b - a for characters a <= b (1-based),
 * T = {0,7,13,18,22,25,26}; a single player uses T[c-1].  Aine + Morrigan (6,7) gives 26 = Morrigan's solo scene,
 * as on the DC.  Called from the patched G_StageDemo (src/asm/stagedemo_slot.s). */
#include "arcade.h"

int gb2_demo_slot(int count, int last)
{
    static const s8 T[7] = { 0, 7, 13, 18, 22, 25, 26 };
    int p1 = V8(0x06055058);                      /* player 1 charNo */
    if (count == 2) {
        int a = p1 < last ? p1 : last, b = p1 < last ? last : p1;
        return T[a - 1] + b - a;
    }
    return T[last - 1];
}
