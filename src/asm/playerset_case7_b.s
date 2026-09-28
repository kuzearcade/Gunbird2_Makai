! @ 06013220
! PlayerSet generic case for charNo 6 (Aine) and 7 (Morrigan):
!   r3 = charNo, r1 = chardef_table[charNo-1]; continue in case-5 tail (stores chardef ptr + charNo)
! defsym: ps_case5_tail=0x06013200
    mov     r0,r3
    shll2   r0
    add     #-4,r0
    bra     ps_case5_tail
    mov.l   @(r0,r14),r1
