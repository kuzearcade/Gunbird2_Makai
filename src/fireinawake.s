! FireInawake (0x060108F6, draws an OBJDT object as sprites) takes the palette bank from its caller (r7, param_4)
! and ignores the entry's own attr high byte: the life-icon callers (HUD 0x0601063E, ranking 0x060207CE) pass 0x40,
! the bank of the six original icons.  Morrigan's objects use bank 0xFF (high palette lines, see make_gfx.py), so
! an entry whose bank byte (+8) is 0xFF keeps it; every other call is unchanged.  Entered from the hook trampoline
! (hooks.txt, clobbers r0), which overwrote the first five instructions (the r14-r10 pushes): redone here.
        .text
        .align  2
        .global gb2_fireinawake
gb2_fireinawake:
        mov.b   @(8,r4),r0      ! entry bank byte (sign-extended)
        cmp/eq  #-1,r0
        bf      1f
        mov     #-1,r7          ! bank 0xFF (FireInawake uses the low byte)
1:      mov.l   r14,@-r15
        mov.l   r13,@-r15
        mov.l   r12,@-r15
        mov.l   r11,@-r15
        mov.l   r10,@-r15
        mov.l   .Lcont,r0
        jmp     @r0
        nop
        .align  2
.Lcont: .long   0x06010900
