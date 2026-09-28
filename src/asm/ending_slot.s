! @ 0601fc7a
! G_Ending: ending slot for the (up to two) players, 7-character layout -> gb2_end_slot(count, last char), which also
! loads Morrigan's ending data.  Replaces the 6-character arithmetic 0x0601FC7A-0x0601FCCF; @(8,r15) = players
! counted, @(4,r15) = charNo of the last player found; result in r8 as the original code left it.
! defsym: done=0x0601fcd0
    mov.w   @(8,r15),r0
    mov     r0,r4
    mov.w   @(4,r15),r0
    mov     r0,r5
    mov.l   .Lslot,r1
    jsr     @r1
    nop
    mov     r0,r8
    bra     done
    nop
    .align  2
.Lslot:
    .long   gb2_end_slot
