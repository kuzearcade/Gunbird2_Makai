/* Maintenance-code screen and secret flags (arcade 0x0600731C, 0x06022A3E/4E, 0x06022B10) with a sixth code
 * that unlocks Morrigan ("Up" on '?' at character select), mirroring how the arcade gates Aine. */
#include "arcade.h"

s16 gb2_morrigan_enabled;

/* original codes live in the D section at 0x0602E77D (5 x 5 digits); initial digits at 0x0602E796 */
#define ORIG_CODES   ((const s8 *)0x0602E77D)
#define INIT_DIGITS  ((const s16 *)0x0602E796)
static const s8 morrigan_code[5] = { 5, 1, 9, 9, 4 };

/* 0x06022A3E: clear secret block */
void gb2_secret_clear(void)
{
    SECRET_TIME = 0;
    SECRET_PLAYS = 0;
    SECRET_AINE = 0;
    gb2_morrigan_enabled = 0;
}

/* 0x06022A4E: count the credit and save the secret block */
void gb2_secret_save(void)
{
    s16 sum;
    u16 m;
    if (SECRET_COUNTED == 0 && (u32)SECRET_TIME > 0xD2EFF) {
        SECRET_PLAYS = SECRET_PLAYS + 1;
        if (SECRET_PLAYS > 60000) SECRET_PLAYS = 60000;
        SECRET_COUNTED = 1;
        if (SECRET_AINE == 0) {
            if (SECRET_PLAYS > 6) SECRET_AINE = 1;
        } else if (SECRET_AINE == 1 && SECRET_PLAYS > 0x1D) {
            SECRET_AINE = 2;
        }
    }
    sum = (s16)SECRET_TIME + SECRET_PLAYS + SECRET_AINE;
    EepWrite(0x18, (const void *)0x0605CA48, 4);
    EepWrite(0x1C, (const void *)0x0605CA50, 2);
    EepWrite(0x1E, (const void *)0x0605CA54, 2);
    EepWrite(0x2E, &sum, 2);
    m = gb2_morrigan_enabled ? MORRIGAN_MAGIC : 0;
    EepWrite(EEP_MORRIGAN, &m, 2);
}

/* 0x06022B10: load the secret block at boot; returns 1 if the checksum was valid */
int gb2_secret_load(void)
{
    u16 sum, m;
    EepRead(0x18, (void *)0x0605CA48, 4);
    EepRead(0x1C, (void *)0x0605CA50, 2);
    EepRead(0x1E, (void *)0x0605CA54, 2);
    EepRead(0x2E, &sum, 2);
    EepRead(EEP_MORRIGAN, &m, 2);
    gb2_morrigan_enabled = (m == MORRIGAN_MAGIC);
    if (sum != (u16)(SECRET_TIME + SECRET_PLAYS + SECRET_AINE)) {
        SECRET_TIME = 0;
        SECRET_PLAYS = 0;
        SECRET_AINE = 0;
        gb2_morrigan_enabled = 0;
        gb2_secret_save();
        return 0;
    }
    return 1;
}

static int pad(int bits) { return (PAD_TRIG_P1 & bits) || (PAD_TRIG_P2 & bits); }

static void print_line(const char *s, int y)
{
    s16 slot = PrintCentered(s, y);
    TEXT_ATTR(slot) = 0x20;
}

/* one result screen shared by the flag codes: returns 0 to leave the maintenance-code screen */
static int flag_screen(const char *msg, s16 cnt, int sound, void (*apply)(void))
{
    PrintCentered(msg, 0x78);
    if (cnt == 0) PlaySound(sound);
    else if (cnt == 2) apply();
    else if (cnt < 0xB4) { if (pad(8)) return 0; }
    else return 0;
    return 1;
}

static void apply_cancel(void) { gb2_secret_clear(); SECRET_COUNTED = 1; gb2_secret_save(); }
static void apply_flag1(void)  { SECRET_PLAYS = 7; SECRET_AINE = 1; SECRET_COUNTED = 1; gb2_secret_save(); }
static void apply_flag2(void)  { SECRET_PLAYS = 0x1E; SECRET_AINE = 2; SECRET_COUNTED = 1; gb2_secret_save(); }
static void apply_morrigan(void) { gb2_morrigan_enabled = 1; SECRET_COUNTED = 1; gb2_secret_save(); }

void gb2_maintenance_code(void)
{
    s16 digit[5];
    s16 cursor = 0, state = 0, cnt = 0;
    int run = 1, i, c;

    for (i = 0; i < 5; i++) digit[i] = INIT_DIGITS[i];
    while (TASK_BUSY != 0) WaitFrame();
    ScreenClear(0, 4, 0, 6);
    ObjHide(V16(0x0605CB50));

    do {
        WaitFrame();
        TextClear();
        PrintCentered((const char *)0x0602E7A0, 0x11D);
        print_line((const char *)0x0602E7B8, 0x3E);
        print_line((const char *)0x0602E7C8, 0x30);
        print_line((const char *)0x0602E7DC, 0x22);
        print_line((const char *)0x0602E7F0, 0x14);
        for (i = 0; i < 5; i++) {
            PrintNumber(&digit[i], 0x57 + i * 10, 200, 0);
            if (i == cursor) PrintAt((const char *)0x0602E808, 0x57 + i * 10, 0xC4);
        }

        if (state == 0) {
            if (pad(0x80) && ++digit[cursor] > 9) digit[cursor] = 0;
            if (pad(0x40) && --digit[cursor] < 0) digit[cursor] = 9;
            if (pad(0x20) && ++cursor > 4) cursor = 0;
            if (pad(0x10) && --cursor < 0) cursor = 4;
            if (pad(8)) {
                state = 100;
                for (c = 0; c < 6; c++) {
                    const s8 *code = c < 5 ? ORIG_CODES + c * 5 : morrigan_code;
                    for (i = 0; i < 5 && digit[i] == code[i]; i++) ;
                    if (i == 5) { state = c + 1; break; }
                }
            }
            if (pad(1)) run = 0;
            continue;
        }

        switch (state) {
        case 1:                                   /* 5-3-5-7-3 all data initialised */
            PrintCentered((const char *)0x0602E80C, 0x78);
            if (cnt == 1) {
                InitRankingA(); InitCharStats(); gb2_secret_clear(); InitScoresA();
                InitRankingB(); SaveCharStats(); gb2_secret_save(); SaveScores();
            } else if (cnt < 0x96) { if (pad(8)) run = 0; }
            else run = 0;
            break;
        case 2: run = flag_screen((const char *)0x0602E824, cnt, 0x3B, apply_cancel); break;   /* 5-3-1-5-7 */
        case 3: run = flag_screen((const char *)0x0602E838, cnt, 0x38, apply_flag1); break;     /* 5-3-7-6-5 */
        case 4: run = flag_screen((const char *)0x0602E84C, cnt, 0x32, apply_flag2); break;     /* 5-1-0-2-4 */
        case 5: MAINT_MODE_REQ = 0x100; run = 0; break;                                   /* 5-2-0-4-8 */
        case 6: run = flag_screen("Sit a MORRIGAN Flag", cnt, 0x32, apply_morrigan); break; /* 5-1-9-9-4 */
        case 100:
            PrintCentered((const char *)0x0602E860, 0x78);
            if (cnt < 0x78) cnt++;
            else { cnt = 0; Random(5); cursor = Random(5); state = 0; }
            continue;
        }
        cnt++;
    } while (run);
    WaitFrame();
}
