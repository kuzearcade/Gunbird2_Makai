! @ 06001bf4
! Stage Select, 1P Character value: print gb2_stage_names[index] (8 entries) instead of the 7-entry stack copy
! (index 7 = Morrigan read past it).  Same length as the original 0x06001BF4-0x06001C0D; the original loaded
! @(4,r15) twice, which leaves room for the literal.  r5 = x (set before), r6 = y, r2 is dead afterwards.
    mov.l   @(0x3c,r15),r1
    mov.l   .Lnames,r4
    bra     1f
    mov.l   r1,@-r15            ! delay slot: push as the original
    .align  2
.Lnames:
    .long   gb2_stage_names
1:  mov.l   @(4,r15),r3
    mov.w   @r3,r6
    mov.w   @(2,r3),r0
    shll2   r0
    jsr     @r13
    mov.l   @(r0,r4),r4         ! delay slot: name pointer
    nop
    mov     r11,r5              ! original instruction at 0x06001C0E (the section is padded to 4 bytes)
