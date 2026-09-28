OUTPUT_FORMAT("elf32-shbig-linux")
INCLUDE arcade_syms.ld
INCLUDE res_syms.ld
SECTIONS { .text : { *(.text) } /DISCARD/ : { *(*) } }
