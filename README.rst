===============
saturn-aseprite
===============

This is a humble conversion utility from ``.aseprite`` files to Sega Saturn VDP2
palette/character/pattern name table formats.

Python >= 3.7 is required.

Usage/example:

.. code::

   python aseprite.py rustboro.aseprite

In the case of ``rustboro.aseprite`` (an Aseprite file with two tilesets and two
layers), the following files will be generated (also printed on stderr):

.. code::

   palette.bin
   character_pattern__tileset_0.bin
   character_pattern__tileset_1.bin
   pattern_name_table__layer_0.bin
   pattern_name_table__layer_1.bin

The ``palette.bin`` and ``character_pattern__tileset_*.bin`` files can be
directly copied to VDP2 CRAM and VRAM
respectively. ``pattern_name_table__layer_*.bin`` need to be trivially modified
to point to the correct character addresses, as in:

.. code:: c

  extern uint32_t size;
  extern uint32_t * buf;
  for (uint32_t i = 0; i < size / 4; i++) {
    uint32_t data = buf[i];
    uint32_t character_number = (data & 0x7fff) * 8 + character_offset;
    uint32_t flags = data & 0xf0000000;
    vdp2.vram.u32[(vram_offset / 4) + i] = flags | character_number;
  }
