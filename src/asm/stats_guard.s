! @ 06023448
! Save per-character stats (0x0602342C -> 0x060229DC): the records are 6 x 0x16 bytes at EEPROM 0x30 with the
! checksum at 0xB4, and the RAM copies (0x0605C9D0, 6 x 0x14) are followed by the secret block.  The update routine
! (0x060231C4) already ignores charNo > 6, but this save did not: for Morrigan it wrote the secret block over the
! checksum and 0xB6-0xC7.  Now skipped for charNo > 6 as well as 0xFF (no player).  Morrigan stats are not kept
! (the operator bookkeeping screen lists the six original characters).
! defsym: exit=0x06023456 save=0x060229dc
    mov     #6,r3
    cmp/hi  r3,r0           ! unsigned: 0xFF..(-1) and 7 -> skip
    bt      exit
    mov     r0,r4           ! charNo (sign-extended byte, as the original mov.b)
    lds.l   @r15+,macl
    bra     save
    mov.l   @r15+,r14
