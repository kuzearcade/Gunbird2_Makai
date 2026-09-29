! G_Ranking (0x06020230) entry: put back the palette lines under her last ending and load her in-game palette
! (gb2_ranking_pal, palette.c) so her life icon in the ranking list has its colours also when she has not been
! played since power-on / the select screen replaced those lines.  The hook trampoline (12 bytes, clobbers r0)
! overwrote the first six instructions: redone here (the PC-relative literal load through its address), then back
! to 0x0602023C.
        .text
        .align  2
        .global gb2_ranking_entry
gb2_ranking_entry:
        sts.l   pr,@-r15
        mov.l   .Linit,r0
        jsr     @r0
        nop
        lds.l   @r15+,pr
        mov.l   r14,@-r15       ! 0x06020230
        mov.l   .Llit,r2        ! 0x06020234: mov.l @(0x06020348,pc),r2
        mov.l   @r2,r2
        mov.l   r13,@-r15       ! 0x06020236
        mov.l   r12,@-r15       ! 0x06020238
        mov.l   .Lcont,r13
        mov     #0x3c,r0        ! 0x06020232
        jmp     @r13
        mov     #0,r13          ! 0x0602023A (delay slot; the jump target was read before)
        .align  2
.Linit: .long   gb2_ranking_pal
.Llit:  .long   0x06020348
.Lcont: .long   0x0602023C
