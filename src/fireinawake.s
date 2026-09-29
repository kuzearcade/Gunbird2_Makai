! FireInawake (0x060108F6, draws an OBJDT object as sprites) takes the palette bank from its caller (r7, param_4)
! and ignores the entry's own attr high byte: the life-icon callers (HUD 0x0601063E, ranking 0x060207CE) pass 0x40,
! the bank of the six original icons.  Morrigan's objects carry their own banks (0x1C / 0x2C, make_gfx.py), so an entry
! whose tiles lie beyond the original graphics (tile number >= 0x35467, the end of the stock gfx ROM data at
! 0x3546700) keeps its own bank; no original entry can point there, so every original call is unchanged.
! Entered from the hook trampoline (hooks.txt, clobbers r0), which overwrote the first five instructions (the
! r14-r10 pushes): redone here.  r1/r2 are caller-saved scratch at function entry.
        .text
        .align  2
        .global gb2_fireinawake
gb2_fireinawake:
        mov.w   @(8,r4),r0      ! attr = bank << 8 | 0x80 (8bpp) | tile number bits 16-18
        mov     r0,r2
        and     #7,r0           ! tile number bits 16-18
        mov     #3,r1
        cmp/gt  r1,r0
        bt      2f              ! >= 0x40000: added graphics
        cmp/eq  r1,r0
        bf      1f              ! < 0x30000: original
        mov.w   @(10,r4),r0     ! tile number bits 0-15
        extu.w  r0,r0
        mov.l   .Lend,r1
        cmp/hs  r1,r0
        bf      1f              ! < 0x35467: original
2:      shlr8   r2
        extu.b  r2,r7           ! the entry's own bank
1:      mov.l   r14,@-r15
        mov.l   r13,@-r15
        mov.l   r12,@-r15
        mov.l   r11,@-r15
        mov.l   r10,@-r15
        mov.l   .Lcont,r0
        jmp     @r0
        nop
        .align  2
.Lend:  .long   0x5467
.Lcont: .long   0x06010900
