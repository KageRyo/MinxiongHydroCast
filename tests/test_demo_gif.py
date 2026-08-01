from pathlib import Path


def _read_subblocks(payload: bytes, offset: int) -> tuple[bytes, int]:
    blocks = bytearray()
    while payload[offset]:
        length = payload[offset]
        offset += 1
        blocks.extend(payload[offset : offset + length])
        offset += length
    return bytes(blocks), offset + 1


def _decode_lzw(payload: bytes, minimum_code_size: int) -> bytes:
    clear_code = 1 << minimum_code_size
    end_code = clear_code + 1
    code_width = minimum_code_size + 1
    next_code = end_code + 1
    table = {code: bytes((code,)) for code in range(clear_code)}
    bit_offset = 0
    output = bytearray()
    previous: bytes | None = None

    while bit_offset + code_width <= len(payload) * 8:
        byte_offset = bit_offset // 8
        shift = bit_offset % 8
        available = int.from_bytes(payload[byte_offset : byte_offset + 3], "little")
        code = (available >> shift) & ((1 << code_width) - 1)
        bit_offset += code_width
        if code == clear_code:
            table = {value: bytes((value,)) for value in range(clear_code)}
            code_width = minimum_code_size + 1
            next_code = end_code + 1
            previous = None
            continue
        if code == end_code:
            return bytes(output)
        if code in table:
            entry = table[code]
        elif previous is not None and code == next_code:
            entry = previous + previous[:1]
        else:
            raise ValueError(f"invalid GIF LZW code: {code}")
        output.extend(entry)
        if previous is not None and next_code < 4096:
            table[next_code] = previous + entry[:1]
            next_code += 1
            if next_code == (1 << code_width) and code_width < 12:
                code_width += 1
        previous = entry
    raise ValueError("GIF image data ended before the LZW end code")


def test_demo_walkthrough_is_decodable_animated_gif():
    path = Path(__file__).parents[1] / "docs" / "assets" / "demo-walkthrough.gif"
    payload = path.read_bytes()

    assert payload[:6] == b"GIF89a"
    width = int.from_bytes(payload[6:8], "little")
    height = int.from_bytes(payload[8:10], "little")
    packed = payload[10]
    offset = 13
    if packed & 0x80:
        offset += 3 * (1 << ((packed & 0x07) + 1))

    frame_count = 0
    while payload[offset] != 0x3B:
        marker = payload[offset]
        offset += 1
        if marker == 0x21:
            offset += 1
            _extension, offset = _read_subblocks(payload, offset)
            continue
        assert marker == 0x2C
        descriptor = payload[offset : offset + 9]
        offset += 9
        frame_width = int.from_bytes(descriptor[4:6], "little")
        frame_height = int.from_bytes(descriptor[6:8], "little")
        image_packed = descriptor[8]
        if image_packed & 0x80:
            offset += 3 * (1 << ((image_packed & 0x07) + 1))
        minimum_code_size = payload[offset]
        image_data, offset = _read_subblocks(payload, offset + 1)
        indexes = _decode_lzw(image_data, minimum_code_size)
        assert (frame_width, frame_height) == (width, height)
        assert len(indexes) == width * height
        frame_count += 1

    assert (width, height) == (640, 360)
    assert frame_count == 30
