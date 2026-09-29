/* Player state set when a bomb or a charged shot starts: the DC added cases for Morrigan (charNo 7) to both.
 * p = player block + 0x10 (x); p[0x48] = charNo, u16 p+0x50 = flags (0x8000 = player sprite hidden), p+0x68 = charge
 * gauge level.  Replace the arcade functions (src/hooks.txt); charNo 1-6 behave exactly as the originals. */
#include "arcade.h"

#define FLAGS(p) (*(u16 *)((p) + 0x50))
#define W16(p, o) (*(s16 *)((p) + (o)))

/* bomb start: arcade 0x06012CA4 (1, 3 -> 0x8001; 2, 6 -> 0x8041), DC FUN_8C056C80 adds 7 -> 0x8041 */
void gb2_bomb_start(u8 *p)
{
    u8 c = p[0x48];
    if (c == 1 || c == 3) FLAGS(p) |= 0x8001;
    else if (c == 2 || c == 6 || c == 7) FLAGS(p) |= 0x8041;
    else return;
    W16(p, 0x5E) = 1;
}

/* charged shot start: arcade 0x06012CE6, DC FUN_8C056D60 adds 7: hidden, and at gauge level 3 (her full-screen
 * charged attack draws her itself) the same fields as Aine's */
void gb2_charge_start(u8 *p)
{
    u8 c = p[0x48];
    if (c >= 1 && c <= 5) FLAGS(p) |= 0x8000;
    else if (c == 6) {
        FLAGS(p) |= 1;
        W16(p, 0x5E) = 1;
        FLAGS(p) |= 0x8000;
        if (W16(p, 0x68) >= 2) { W16(p, 0x9A) = 0; W16(p, 0xA8) = 1; }
    } else if (c == 7) {
        FLAGS(p) |= 0x8000;
        if (W16(p, 0x68) == 3) { W16(p, 0x9A) = 0; W16(p, 0x5E) = 1; W16(p, 0xA8) = 1; }
    }
}
