/* Maintenance Stage Select (arcade dc_8c073900 @ 0x06001780): character names for the 1P/2P rows.
 * The original copies a 7-entry name list (NoUse, Jiki0-Jiki5) to the stack, so Morrigan's value 7 read the
 * following min-limit table as a string pointer (blank name).  src/asm/stagesel_names_1p.s / _2p.s read this
 * 8-entry table instead; slot 7 uses the DC's name for her ("Jiki6", as the other characters' JikiN). */
#include "arcade.h"

const char *const gb2_stage_names[8] = {
    (const char *)0x0602E86C, (const char *)0x0602E874, (const char *)0x0602E87C, (const char *)0x0602E884,
    (const char *)0x0602E88C, (const char *)0x0602E894, (const char *)0x0602E89C, "Jiki6",
};
