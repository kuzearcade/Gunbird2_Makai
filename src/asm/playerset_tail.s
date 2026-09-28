! @ 0601322e
! PlayerSet common tail (all cases converge here) -> gb2_playerset_tail (src/gauge.s), which records the charge-
! gauge table index before the original tail runs.  Overwrites 0x0601322E-37 (5 instructions, replayed by the stub);
! nothing branches into 0x06013230-37.  r1 is dead here (reloaded at 0x06013230 originally).
    mov.l   .Ltail,r1
    jmp     @r1
    nop
    .align  2
.Ltail:
    .long   gb2_playerset_tail
