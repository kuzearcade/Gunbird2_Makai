! @ 060131c0
! PlayerSet: "param not 1..5 and not 6 -> skip" becomes "param >= 6 -> generic case"
! defsym: ps_generic=0x06013220 ps_tail=0x0601322e
    mov     #6,r1
    cmp/ge  r1,r0            ! T = charNo >= 6
    bt      ps_generic       ! -> generic case 6/7
    bra     ps_tail          ! (delay slot = original 'mov.l @r14,r3' of case 1: harmless)
