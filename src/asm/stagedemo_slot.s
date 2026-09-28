! @ 0601eda8
! G_StageDemo: scene slot for the (up to two) players, 7-character layout -> gb2_demo_slot(count, last char).
! Replaces the 6-character triangle arithmetic (0x0601EDA8-0x0601EDF7); @(4,r15) = players counted,
! r8 = charNo of the last player found, result stored at @r15 as the original code did.
! defsym: done=0x0601edf8
    mov.w   @(4,r15),r0
    mov     r0,r4
    mov     r8,r5
    mov.l   .Lslot,r1
    jsr     @r1
    nop
    mov.w   r0,@r15
    bra     done
    nop
    .align  2
.Lslot:
    .long   gb2_demo_slot
