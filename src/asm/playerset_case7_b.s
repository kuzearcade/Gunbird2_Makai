! @ 06013220
! PlayerSet generic case for charNo 6 (Aine) / 7 (Morrigan): jump to the stub in dead RAM code at 0x06022B20.
! Only 0x06013220-0x06013229 is free (case 3 branches to 0x0601322A), so the literal follows the jmp directly:
! its high half 0x0602 executes in the delay slot as 'stc sr,r6' (legal, harmless: the stub recomputes r6).
    mov.l   .Lgen,r1
    jmp     @r1
.Lgen:
    .long   0x06022B20
