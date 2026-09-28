! @ 06001c14
! Stage Select, 2P Character value: as stagesel_names_1p.s (original 0x06001C14-0x06001C2F, same length).
    mov     #0x78,r0
    mov.l   @(r0,r15),r2
    mov.l   .Lnames,r4
    mov.l   r2,@-r15
    bra     1f
    mov.l   @(0x30,r15),r3      ! delay slot
    .align  2
.Lnames:
    .long   gb2_stage_names
1:  mov.w   @r3,r6
    mov.w   @(2,r3),r0
    shll2   r0
    jsr     @r13
    mov.l   @(r0,r4),r4         ! delay slot: name pointer
    nop
