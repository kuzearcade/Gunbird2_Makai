/* Gunbird 2 Morrigan backport - patch code layout (real PS5 limits: everything inside the 1 MB program ROM) */
OUTPUT_FORMAT("elf32-shbig-linux")
OUTPUT_ARCH(sh)
INCLUDE arcade_syms.ld
INCLUDE res_syms.ld
MEMORY
{
    ROMFREE1 (rx) : ORIGIN = 0x00033000, LENGTH = 0x00005000   /* patch code (0x38000-0x3FFFF = Morrigan OBJDT) */
    ROMFREE2 (r)  : ORIGIN = 0x00057E00, LENGTH = 0x00003200   /* Morrigan scripts/data (tools/port_morrigan.py) */
    ROMSTORY (r)  : ORIGIN = 0x0005B000, LENGTH = 0x00005000   /* story scenes/text (tools/port_stagedemo.py, .story) */
    RAMFREE  (rw) : ORIGIN = 0x06033000, LENGTH = 0x0000D000   /* unused RAM between D and BSS sections */
}
SECTIONS
{
    .text   : { *(.text.hooks) *(.text) *(.text.*) } > ROMFREE1
    .rodata : { *(.rodata) *(.rodata.*) *(.rdata) } > ROMFREE1
    .story  : { *(.story) } > ROMSTORY
    .data   : { *(.data) *(.data.*) } > ROMFREE1   /* must stay empty: no writable initialised data */
    .bss (NOLOAD) : { __bss_start = .; *(.bss) *(.bss.*) *(COMMON) __bss_end = .; } > RAMFREE
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame) }
}
ASSERT(SIZEOF(.data) == 0, "no writable initialised data allowed")
