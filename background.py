import sys
from pprint import pprint, pformat
import textwrap
import struct
from operator import itemgetter

from aseprite import parse_file
from aseprite import PaletteChunk, OldPaletteChunk, TilesetChunkInternal, CelChunk_CompressedTilemap

def pprinti(o, i):
    s = pformat(o)
    print(textwrap.indent(s, '    ' * i))

def pack_bgr555(red, green, blue):
    bgr = (
        ((red >> 3) << 0) |
        ((green >> 3) << 5) |
        ((blue >> 3) << 10)
    )
    return struct.pack(">H", bgr)

def pack_index(i):
    return struct.pack(">I", i)

def pack_old_palette_chunk(old_palette_chunk):
    with open("palette.bin", "wb") as f:
        for color in old_palette_chunk.packets[0].colors:
            f.write(pack_bgr555(*color))

def pack_palette_chunk(palette_chunk):
    with open("palette.bin", "wb") as f:
        assert palette_chunk.first_color_index_to_change == 0

        for entry in palette_chunk.entries:
            color = (entry.red, entry.green, entry.blue)
            f.write(pack_bgr555(*color))

        print("palette.bin", f.tell(), file=sys.stderr)

def pack_palette(palette):
    if type(palette) is PaletteChunk:
        pack_palette_chunk(palette)
    elif type(palette) is OldPaletteChunk:
        pack_old_palette_chunk(palette)
    else:
        assert False, type(palette)

def pack_character_2x2(tileset_chunk, offset):
    #tileset_chunk.number_of_tiles,
    #tileset_chunk.tile_width,
    #tileset_chunk.tile_height,

    assert tileset_chunk.tile_width == 16
    assert tileset_chunk.tile_height == 16
    assert type(tileset_chunk.data) == TilesetChunkInternal

    buf = bytearray(16 * 16)

    for cell_ix in range(4):
        for y in range(8):
            for x in range(8):
                tileset_x = 8 * (cell_ix % 2) + x
                tileset_y = 8 * (cell_ix // 2) + y
                px = tileset_chunk.data.pixel[offset + tileset_y * 16 + tileset_x]
                buf[cell_ix * 8 * 8 + y * 8 + x] = px

    return bytes(buf)

def pack_character_1x1(tileset_chunk, offset):
    assert tileset_chunk.tile_width == 8
    assert tileset_chunk.tile_height == 8
    assert type(tileset_chunk.data) == TilesetChunkInternal

    buf = bytearray(8 * 8)

    for y in range(8):
        for x in range(8):
            tileset_x = x
            tileset_y = y
            px = tileset_chunk.data.pixel[offset + tileset_y * 8 + tileset_x]
            buf[y * 8 + x] = px

    return bytes(buf)

def pack_character_patterns(filename, tileset_chunk):
    with open(filename, "wb") as f:
        for i in range(tileset_chunk.number_of_tiles):
            offset = tileset_chunk.tile_width * tileset_chunk.tile_height * i

            if tileset_chunk.tile_width == 8 and tileset_chunk.tile_height == 8:
                buf = pack_character_1x1(tileset_chunk, offset)
            elif tileset_chunk.tile_width == 16 and tileset_chunk.tile_height == 16:
                buf = pack_character_2x2(tileset_chunk, offset)
            else:
                assert False, (tileset_chunk.tile_width, tileset_chunk.tile_height)

            f.write(buf)

        print(filename, f.tell(), file=sys.stderr)

def pack_pattern_name_table(filename, cel_chunk, x_cells, y_cells):
    with open(filename, "wb") as f:
        assert type(cel_chunk.data) == CelChunk_CompressedTilemap
        #assert cel_chunk.data.width_in_number_of_tiles <= 64
        #assert cel_chunk.data.height_in_number_of_tiles <= 64

        tile_width = cel_chunk.data.width_in_number_of_tiles
        tile_height = cel_chunk.data.height_in_number_of_tiles

        print(tile_width, tile_height)

        h_pages = ((tile_width + (x_cells - 1)) & (~(x_cells - 1))) // x_cells
        v_pages = ((tile_height + (y_cells - 1)) & (~(y_cells - 1))) // y_cells

        if h_pages > 2:
            h_pages = 2
        if v_pages > 2:
            v_pages = 2

        print("h_pages, v_pages", h_pages, v_pages)

        for v_page in range(v_pages):
            for h_page in range(h_pages):
                for y in range(y_cells):
                    for x in range(x_cells):
                        tx = (h_page * x_cells) + x
                        ty = (v_page * y_cells) + y
                        if tx >= tile_width or ty >= tile_height:
                            f.write(pack_index(0))
                        else:
                            cel_chunk_ix = ty * tile_width + tx
                            tile_data = cel_chunk.data.tile[cel_chunk_ix]

                            tile_id = tile_data & cel_chunk.data.bitmask_for_tile_id.value
                            x_flip = (tile_data & cel_chunk.data.bitmask_for_x_flip.value) != 0
                            y_flip = (tile_data & cel_chunk.data.bitmask_for_y_flip.value) != 0

                            pattern = (int(y_flip) << 31) | (int(x_flip) << 30) | tile_id

                            f.write(pack_index(pattern))

        print(filename, f.tell(), file=sys.stderr)

with open(sys.argv[1], 'rb') as f:
    buf = f.read()
    mem = memoryview(buf)

tilesets, layers, palette, cel_chunks = parse_file(buf)

pack_palette(palette)

for tileset_index, tileset_chunk in sorted(tilesets.items(), key=itemgetter(0)):
    filename = f"character_pattern__tileset_{tileset_index}.bin"
    pack_character_patterns(filename, tileset_chunk)

for layer_index, cel_chunk in sorted(cel_chunks.items(), key=itemgetter(0)):
    filename = f"pattern_name_table__layer_{layer_index}.bin"
    #layers[layer_index]
    print(f"layer={layer_index} layer_name={layers[layer_index].layer_name} tileset={layers[layer_index].tileset_index}");
    tileset_chunk = tilesets[layers[layer_index].tileset_index]

    x_cells = 64 // (tileset_chunk.tile_width // 8)
    y_cells = 64 // (tileset_chunk.tile_height // 8)

    pack_pattern_name_table(filename, cel_chunk, x_cells, y_cells)

#for layer_index, layer_chunk in enumerate(layers):
#    print(f"layer={layer_index} layer_name={layer_chunk.layer_name} tileset={layer_chunk.tileset_index}");
