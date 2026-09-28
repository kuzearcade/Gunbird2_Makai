! Charge gauge: per-character thresholds are rows of 3 u32 at SEQ hdr+0x14 table +0x20 + (charNo-1)*12, six rows.
! The DC appends Morrigan's row at +0x344 and special-cases charNo 7 (FUN_8C058180, FUN_8C056600, FUN_8C056900,
! FUN_8C04E320); her values (600, 5600, 19000; US and JP) equal Aine's row.  Arcade port: every site that indexes
! the rows (15 x 'mov #0x48,r0; mov.b @(r0,rBase),r1' with rBase = player+0x10) reads a "gauge index" byte at
! player+0x46 instead (alignment padding: never accessed by the game, verified with read/write taps over 1P/2P play),
! which PlayerSet sets to charNo, or 6 for Morrigan.
        .text
        .align  2
        .global gb2_playerset_tail
gb2_playerset_tail:
        mov     r6,r2           ! player offset (p * 0xB0)
        add     r7,r2           ! + 0x06055010 = player+0x10 (valid on every path into the tail)
        mov     #0x48,r0
        mov.b   @(r0,r2),r0     ! charNo
        cmp/eq  #7,r0
        bf      1f
        mov     #6,r0           ! Morrigan -> Aine's row (identical values)
1:      mov     r0,r1
        mov     #0x36,r0
        mov.b   r1,@(r0,r2)     ! player+0x46 = gauge index
        mov     #0,r10          ! --- replayed 0x0601322E-0x06013236
        mov     r10,r1
        mov     r10,r5
        mov     r6,r14
        add     r7,r14
        mov.l   .Lback,r0       ! r0 is reloaded at 0x06013238
        jmp     @r0
        nop
        .align  2
.Lback: .long   0x06013238
