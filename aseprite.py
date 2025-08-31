import struct
import sys
from dataclasses import dataclass
from pprint import pprint, pformat
import textwrap
from typing import Union, Optional
import zlib
from operator import itemgetter

class CustomInt:
    value: int

    def __init__(self, value):
        self.value = value

    def __int__(self):
        return self.value

    def __eq__(self, other):
        return self.value == other

    def __eq__(self, other):
        return self.value == other

class HexInt(CustomInt):
    def __repr__(self):
        return hex(self.value)

class BinInt(CustomInt):
    def __repr__(self):
        return bin(self.value)

@dataclass
class Header:
    file_size: int
    magic_number: HexInt
    frames: int
    width_in_pixels: int
    height_in_pixels: int
    color_depth: int
    flags: HexInt
    speed: int
    transparent_palette_index: int
    number_of_colors: int
    pixel_width: int
    pixel_height: int
    x_position_of_grid: int
    y_position_of_grid: int
    grid_width: int
    grid_height: int

def dword(mem):
    return struct.unpack("<I", mem[0:4])[0], mem[4:]

def word(mem):
    return struct.unpack("<H", mem[0:2])[0], mem[2:]

def short(mem):
    return struct.unpack("<h", mem[0:2])[0], mem[2:]

def byte(mem):
    return struct.unpack("<B", mem[0:1])[0], mem[1:]

def skip(mem, i):
    return mem[i:]

def uuid(mem):
    return bytes(mem[0:16]), mem[16:]

def string(mem):
    string_length, mem = word(mem)
    byte = bytes(mem[0:string_length])
    return byte, mem[string_length:]

def parse_header(mem):
    file_size, mem = dword(mem)
    magic_number, mem = word(mem)
    frames, mem = word(mem)
    width_in_pixels, mem = word(mem)
    height_in_pixels, mem = word(mem)
    color_depth, mem = word(mem)
    flags, mem = dword(mem)
    speed, mem = word(mem)
    mem = skip(mem, 8)
    transparent_palette_index, mem = byte(mem)
    mem = skip(mem, 3)
    number_of_colors, mem = word(mem)
    pixel_width, mem = byte(mem)
    pixel_height, mem = byte(mem)
    x_position_of_grid, mem = short(mem)
    y_position_of_grid, mem = short(mem)
    grid_width, mem = word(mem)
    grid_height, mem = word(mem)
    mem = skip(mem, 84)

    assert magic_number == 0xa5e0, magic_number

    header = Header(
        file_size = file_size,
        magic_number = HexInt(magic_number),
        frames = frames,
        width_in_pixels = width_in_pixels,
        height_in_pixels = height_in_pixels,
        color_depth = color_depth,
        flags = flags,
        speed = speed,
        transparent_palette_index = transparent_palette_index,
        number_of_colors = number_of_colors,
        pixel_width = pixel_width,
        pixel_height = pixel_height,
        x_position_of_grid = x_position_of_grid,
        y_position_of_grid = y_position_of_grid,
        grid_width = grid_width,
        grid_height = grid_height,
    )

    return header, mem

@dataclass
class FrameHeader:
    bytes_in_this_frame: int
    magic_number: HexInt
    number_of_chunks: int
    frame_duration: int

def parse_frame_header(mem):
    bytes_in_this_frame, mem = dword(mem)
    magic_number, mem = word(mem)
    old_number_of_chunks, mem = word(mem)
    frame_duration, mem = word(mem)
    mem = skip(mem, 2)
    new_number_of_chunks, mem = dword(mem)

    assert magic_number == 0xf1fa, magic_number
    assert (
        old_number_of_chunks == new_number_of_chunks or
        (old_number_of_chunks == 0xffff and new_number_of_chunks != 0) or
        (old_number_of_chunks < 0xffff and new_number_of_chunks == 0)
    )
    number_of_chunks = new_number_of_chunks if new_number_of_chunks != 0 else old_number_of_chunks

    frame_header = FrameHeader(
        bytes_in_this_frame = bytes_in_this_frame,
        magic_number = HexInt(magic_number),
        number_of_chunks = number_of_chunks,
        frame_duration = frame_duration,
    )

    return frame_header, mem

@dataclass
class Chunk:
    chunk_size: int
    chunk_type: HexInt
    data: memoryview

def parse_chunk(mem):
    chunk_size, mem = dword(mem)
    chunk_type, mem = word(mem)
    assert chunk_size >= 6, chunk_size
    data = mem[0:chunk_size - 6]
    mem = skip(mem, chunk_size - 6)
    chunk = Chunk(
        chunk_size = chunk_size,
        chunk_type = HexInt(chunk_type),
        data = data
    )
    return chunk, mem

@dataclass
class PaletteChunkPacket:
    entries_to_skip: int
    number_of_colors: int
    colors: list[tuple[int, int, int]]

@dataclass
class OldPaletteChunk:
    number_of_packets: int
    packets: list[PaletteChunkPacket]

def parse_old_palette_chunk(mem):
    number_of_packets, mem = word(mem)
    packets = []
    for _ in range(number_of_packets):
        entries_to_skip, mem = byte(mem)
        number_of_colors, mem = byte(mem)

        assert entries_to_skip == 0, entries_to_skip

        colors = []
        for _ in range(number_of_colors):
            red, mem = byte(mem)
            green, mem = byte(mem)
            blue, mem = byte(mem)
            colors.append((red, green, blue))

        packets.append(PaletteChunkPacket(
            entries_to_skip = entries_to_skip,
            number_of_colors = number_of_colors,
            colors = colors,
        ))

    old_palette_chunk = OldPaletteChunk(
        number_of_packets = number_of_packets,
        packets = packets
    )

    return old_palette_chunk, mem

@dataclass
class PaletteChunkEntry:
    red: int
    green: int
    blue: int
    alpha: int
    color_name: str

def parse_palette_chunk_entry(mem):
    flag, mem = word(mem)
    red, mem = byte(mem)
    green, mem = byte(mem)
    blue, mem = byte(mem)
    alpha, mem = byte(mem)
    color_name = None
    if flag & (1 << 0):
        color_name, mem = string(mem)
    palette_chunk_entry = PaletteChunkEntry(
        red = red,
        green = green,
        blue = blue,
        alpha = alpha,
        color_name = color_name
    )
    return palette_chunk_entry, mem

@dataclass
class PaletteChunk:
    new_palette_size: int
    first_color_index_to_change: int
    last_color_index_to_change: int
    entries: list[PaletteChunkEntry]

def parse_palette_chunk(mem):
    new_palette_size, mem = dword(mem)
    first_color_index_to_change, mem = dword(mem)
    last_color_index_to_change, mem = dword(mem)
    mem = skip(mem, 8)
    length = last_color_index_to_change - first_color_index_to_change
    assert length > 0, length

    entries = []

    for _ in range(length + 1):
        palette_chunk_entry, mem = parse_palette_chunk_entry(mem)
        entries.append(palette_chunk_entry)

    palette_chunk = PaletteChunk(
        new_palette_size = new_palette_size,
        first_color_index_to_change = first_color_index_to_change,
        last_color_index_to_change = last_color_index_to_change,
        entries = entries
    )
    return palette_chunk, mem

@dataclass
class TilesetChunkExternal:
    id_of_external_file: int
    tileset_id_in_external_file: int

@dataclass
class TilesetChunkInternal:
    data_length: int
    pixel: memoryview

@dataclass
class TilesetChunk:
    tileset_id: int
    tileset_flags: HexInt
    number_of_tiles: int
    tile_width: int
    tile_height: int
    base_index: int
    name_of_tileset: str
    data: Union[TilesetChunkExternal, TilesetChunkInternal]

def parse_tileset_chunk(mem):
    _link_to_external_file = (1 << 0)
    _tiles_inside_this_file = (1 << 1)

    tileset_id, mem = dword(mem)
    tileset_flags, mem = dword(mem)
    number_of_tiles, mem = dword(mem)
    tile_width, mem = word(mem)
    tile_height, mem = word(mem)
    base_index, mem = short(mem)
    mem = skip(mem, 14)
    name_of_tileset, mem = string(mem)

    assert (tileset_flags & 0b11) != 0, tileset_flags

    data = None
    if tileset_flags & _link_to_external_file:
        id_of_external_file, mem = dword(mem)
        tileset_id_in_external_file, mem = dword(mem)
        data = TilesetChunkExternal(
            id_of_external_file,
            tileset_id_in_external_file,
        )
    elif tileset_flags & _tiles_inside_this_file:
        data_length, mem = dword(mem)
        pixel = mem[0:data_length]

        mem = skip(mem, data_length)
        data = TilesetChunkInternal(
            data_length,
            zlib.decompress(pixel),
        )

    tileset_chunk = TilesetChunk(
        tileset_id = tileset_id,
        tileset_flags = HexInt(tileset_flags),
        number_of_tiles = number_of_tiles,
        tile_width = tile_width,
        tile_height = tile_height,
        base_index = base_index,
        name_of_tileset = name_of_tileset,
        data = data,
    )

    return tileset_chunk, mem

@dataclass
class LayerChunk:
    flags: int
    layer_type: int
    layer_child_level: int
    default_layer_width_in_pixels: int
    default_layer_height_in_pixels: int
    blend_mode: int
    opacity: int
    layer_name: str
    tileset_index: Optional[int]
    layer_uuid: Optional[bytes]

def parse_layer_chunk(mem, header_flags):
    flags, mem = word(mem)
    layer_type, mem = word(mem)
    layer_child_level, mem = word(mem)
    default_layer_width_in_pixels, mem = word(mem)
    default_layer_height_in_pixels, mem = word(mem)
    blend_mode, mem = word(mem)
    opacity, mem = byte(mem)
    mem = skip(mem, 3)
    layer_name, mem = string(mem)
    tileset_index = None
    if layer_type == 2:
        tileset_index, mem = dword(mem)
    layer_uuid = None
    if header_flags & (1 << 3):
        layer_uuid, mem = uuid(mem)

    layer_chunk = LayerChunk(
        flags = flags,
        layer_type = layer_type,
        layer_child_level = layer_child_level,
        default_layer_width_in_pixels = default_layer_width_in_pixels,
        default_layer_height_in_pixels = default_layer_height_in_pixels,
        blend_mode = blend_mode,
        opacity = opacity,
        layer_name = layer_name,
        tileset_index = tileset_index,
        layer_uuid = layer_uuid,
    )

    return layer_chunk, mem

@dataclass
class CelChunk_RawImageData:
    width_in_pixels: int
    height_in_pixes: int
    pixel: memoryview

@dataclass
class CelChunk_LinkedCell:
    frame_position: int

@dataclass
class CelChunk_CompressedImage:
    width_in_pixels: int
    height_in_pixels: int
    pixel: memoryview

@dataclass
class CelChunk_CompressedTilemap:
    width_in_number_of_tiles: int
    height_in_number_of_tiles: int
    bits_per_tile: int
    bitmask_for_tile_id: int
    bitmask_for_x_flip: int
    bitmask_for_y_flip: int
    bitmask_for_diagonal_flip: int
    tile: memoryview

@dataclass
class CelChunk:
    layer_index: int
    x_position: int
    y_position: int
    opacity_level: int
    cel_type: int
    z_index: int

    data: Union[CelChunk_RawImageData,
                CelChunk_LinkedCell,
                CelChunk_CompressedImage,
                CelChunk_CompressedTilemap]

def parse_cel_chunk(mem):
    layer_index, mem = word(mem)
    x_position, mem = short(mem)
    y_position, mem = short(mem)
    opacity_level, mem = byte(mem)
    cel_type, mem = word(mem)
    z_index, mem = short(mem)
    mem = skip(mem, 5)

    assert cel_type in {0, 1, 2, 3}, cel_type

    data = None
    if cel_type == 0:
        width_in_pixels, mem = word(mem)
        height_in_pixels, mem = word(mem)
        pixel = mem
        data = CelChunk_RawImageData(
            width_in_pixels,
            height_in_pixels,
            pixel,
        )
    if cel_type == 1:
        frame_position, mem = word(mem)
        data = CelChunk_LinkedCell(frame_position)
    if cel_type == 2:
        width_in_pixels, mem = word(mem)
        height_in_pixels, mem = word(mem)
        pixel = memoryview(zlib.decompress(mem))
        data = CelChunk_CompressedImage(
            width_in_pixels,
            height_in_pixels,
            pixel,
        )
    if cel_type == 3:
        width_in_number_of_tiles, mem = word(mem)
        height_in_number_of_tiles, mem = word(mem)
        bits_per_tile, mem = word(mem)
        bitmask_for_tile_id, mem = dword(mem)
        bitmask_for_x_flip, mem = dword(mem)
        bitmask_for_y_flip, mem = dword(mem)
        bitmask_for_diagonal_flip, mem = dword(mem)
        mem = skip(mem, 10)
        tile_mem = memoryview(zlib.decompress(mem))
        assert len(tile_mem) % 4 == 0
        tile = [
            struct.unpack("<I", tile_mem[i*4:i*4+4])[0]
            for i in range(len(tile_mem) // 4)
        ]
        data = CelChunk_CompressedTilemap(
            width_in_number_of_tiles = width_in_number_of_tiles,
            height_in_number_of_tiles = height_in_number_of_tiles,
            bits_per_tile = bits_per_tile,
            bitmask_for_tile_id = HexInt(bitmask_for_tile_id),
            bitmask_for_x_flip = HexInt(bitmask_for_x_flip),
            bitmask_for_y_flip = HexInt(bitmask_for_y_flip),
            bitmask_for_diagonal_flip = HexInt(bitmask_for_diagonal_flip),
            tile = tile,
        )

    cel_chunk = CelChunk(
        layer_index = layer_index,
        x_position = x_position,
        y_position = y_position,
        opacity_level = opacity_level,
        cel_type = cel_type,
        z_index = z_index,
        data = data,
    )

    return cel_chunk, mem

with open(sys.argv[1], 'rb') as f:
    buf = f.read()
    mem = memoryview(buf)

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

def pack_character_patterns_2x2(filename, tileset_chunk):
    with open(filename, "wb") as f:
        for i in range(tileset_chunk.number_of_tiles):
            offset = tileset_chunk.tile_width * tileset_chunk.tile_height * i
            buf = pack_character_2x2(tileset_chunk, offset)
            f.write(buf)

        print(filename, f.tell(), file=sys.stderr)

def pack_pattern_name_table_2x2(filename, cel_chunk):
    with open(filename, "wb") as f:
        assert type(cel_chunk.data) == CelChunk_CompressedTilemap
        assert cel_chunk.data.width_in_number_of_tiles <= 64
        assert cel_chunk.data.height_in_number_of_tiles <= 64

        tile_width = cel_chunk.data.width_in_number_of_tiles
        tile_height = cel_chunk.data.height_in_number_of_tiles

        h_pages = ((tile_width + 31) & (~31)) // 32
        v_pages = ((tile_height + 31) & (~31)) // 32

        for v_page in range(v_pages):
            for h_page in range(h_pages):
                for y in range(32):
                    for x in range(32):
                        tx = (h_page * 32) + x
                        ty = (v_page * 32) + y
                        if tx >= tile_width or ty >= tile_height:
                            f.write(pack_index(0))
                        else:
                            cel_chunk_ix = ty * tile_width + tx
                            tile_data = cel_chunk.data.tile[cel_chunk_ix]

                            tile_id = tile_data & cel_chunk.data.bitmask_for_tile_id.value
                            x_flip = (tile_data & cel_chunk.data.bitmask_for_x_flip.value) != 0
                            y_flip = (tile_data & cel_chunk.data.bitmask_for_y_flip.value) != 0

                            pattern = (int(y_flip) << 31) | (int(x_flip) << 30) | tile_id
                            if x_flip or y_flip:
                                print("HERE", x_flip, y_flip, hex(pattern))

                            f.write(pack_index(pattern))

        print(filename, f.tell(), file=sys.stderr)

header, mem = parse_header(mem)
#pprint(header)
assert header.color_depth == 8, header.color_depth

frame_header, mem = parse_frame_header(mem)
#pprint(frame_header)

tilesets = dict() # by tileset id
layers = []
palette = None
cel_chunks = dict() # by layer index

for _ in range(frame_header.number_of_chunks):
    chunk, mem = parse_chunk(mem)
    #pprinti(chunk, 1)
    if chunk.chunk_type == 0x4:
        old_palette_chunk, _ = parse_old_palette_chunk(chunk.data)
        #pprinti(old_palette_chunk, 2)
        assert palette is None
        palette = old_palette_chunk
    elif chunk.chunk_type == 0x2019:
        palette_chunk, _ = parse_palette_chunk(chunk.data)
        #pprinti(palette_chunk, 2)
        assert palette is None
        palette = palette_chunk
    elif chunk.chunk_type == 0x2023:
        tileset_chunk, _ = parse_tileset_chunk(chunk.data)
        assert tileset_chunk.tileset_id not in tilesets
        tilesets[tileset_chunk.tileset_id] = tileset_chunk
        #pprinti(tileset_chunk, 2)
    elif chunk.chunk_type == 0x2004:
        layer_chunk, _ = parse_layer_chunk(chunk.data, header.flags)
        assert layer_chunk.layer_type == 2
        layers.append(layer_chunk)
        #pprinti(layer_chunk, 2)
    elif chunk.chunk_type == 0x2005:
        cel_chunk, _ = parse_cel_chunk(chunk.data)
        #pprinti(cel_chunk, 2)
        assert cel_chunk.layer_index not in cel_chunks
        cel_chunks[cel_chunk.layer_index] = cel_chunk
    elif chunk.chunk_type == 0x2020:
        # user data
        pass
    else:
        print("unhandled chunk: ")
        pprinti(chunk, 1)

assert palette is not None

pack_palette(palette)

for tileset_index, tileset_chunk in sorted(tilesets.items(), key=itemgetter(0)):
    filename = f"character_pattern__tileset_{tileset_index}.bin"
    pack_character_patterns_2x2(filename, tileset_chunk)

for layer_index, cel_chunk in sorted(cel_chunks.items(), key=itemgetter(0)):
    filename = f"pattern_name_table__layer_{layer_index}.bin"
    pack_pattern_name_table_2x2(filename, cel_chunk)

for layer_index, layer_chunk in enumerate(layers):
    print(f"layer={layer_index} tileset={layer_chunk.tileset_index}");
