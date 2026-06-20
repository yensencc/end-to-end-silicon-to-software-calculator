MEMORY
{
  FLASH (rx) : ORIGIN = 0x00000000, LENGTH = 256K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 64K
}

SECTIONS
{
  .vector_table ORIGIN(FLASH) :
  {
    __vector_table = .;
    KEEP(*(.vector_table));
  } > FLASH

  .text : ALIGN(4)
  {
    *(.text .text.*);
  } > FLASH

  .rodata : ALIGN(4)
  {
    *(.rodata .rodata.*);
  } > FLASH

  .bss (NOLOAD) : ALIGN(4)
  {
    __sbss = .;
    *(.bss .bss.*);
    *(COMMON);
    __ebss = .;
  } > RAM

  /DISCARD/ :
  {
    *(.ARM.exidx);
    *(.ARM.exidx.*);
    *(.ARM.extab.*);
  }
}
