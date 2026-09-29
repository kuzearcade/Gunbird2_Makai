! @ 06022b20
! Stub for PlayerSet charNo >= 6 (entered from 0x06013220), placed in the dead body of the original secret-load
! routine 0x06022B10 (hooked -> gb2_secret_load; its trampoline ends at 0x06022B1C).
!   in:  r0 = charNo, r4 = player, r14 = chardef table, r7 = player base; r6 clobbered by the jump's delay slot
!   out: r3 = charNo, r1 = chardef_table[charNo-1], r6 = (s16)(player * 0xB0) -> original case-5 tail
! For Morrigan it first loads her in-game palette (lines 0x1C-0x1F, 0x2C-0x2F, src/palette.c): once per
! game start, nothing added to per-frame paths.
    mov     r0,r3
    shll2   r0
    add     #-4,r0
    mov.l   @(r0,r14),r1
    mov.w   .Lsize,r6
    muls.w  r6,r4
    sts     macl,r6
    exts.w  r6,r6
    mov     r3,r0
    cmp/eq  #7,r0
    bf      1f
    sts.l   pr,@-r15
    mov.l   r1,@-r15
    mov.l   r3,@-r15
    mov.l   r6,@-r15
    mov.l   r7,@-r15
    mov.l   .Lpal,r0
    jsr     @r0
    nop
    mov.l   @r15+,r7
    mov.l   @r15+,r6
    mov.l   @r15+,r3
    mov.l   @r15+,r1
    lds.l   @r15+,pr
1:  mov.l   .Ltail,r0
    jmp     @r0
    nop
    .align  2
.Lpal:  .long   gb2_morrigan_pal_init
.Ltail: .long   0x06013200          ! case-5 tail: stores chardef ptr + charNo
.Lsize: .word   0xB0                ! player struct size
