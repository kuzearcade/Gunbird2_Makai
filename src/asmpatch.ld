OUTPUT_FORMAT("elf32-shbig-linux")
INCLUDE res_syms.ld
SECTIONS { .text : { *(.text) } /DISCARD/ : { *(*) } }
