#!/usr/bin/env python3
"""Build a dependency-free animated GIF from a Playwright WebM capture.

The Playwright-bundled FFmpeg is deliberately minimal and cannot encode GIF directly. This script
uses it only to decode scaled PNG frames, then writes a fixed 3-3-2 palette GIF with the Python
standard library. It keeps image tooling out of the runtime package.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def read_rgb_png(path: Path) -> tuple[int, int, bytes]:
    payload = path.read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError(f"not a PNG file: {path}")
    offset = len(PNG_SIGNATURE)
    width = height = 0
    compressed = bytearray()
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        data = payload[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", data)
            )
            if (bit_depth, color_type, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError(
                    "expected a non-interlaced 8-bit RGB PNG, got "
                    f"depth={bit_depth} type={color_type} interlace={interlace}"
                )
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    if width <= 0 or height <= 0:
        raise ValueError(f"PNG is missing a valid IHDR: {path}")

    encoded = zlib.decompress(bytes(compressed))
    stride = width * 3
    expected = height * (stride + 1)
    if len(encoded) != expected:
        raise ValueError(f"unexpected PNG payload size: {len(encoded)} != {expected}")
    decoded = bytearray(height * stride)
    source = 0
    for row_index in range(height):
        filter_kind = encoded[source]
        source += 1
        row = bytearray(encoded[source : source + stride])
        source += stride
        prior_start = (row_index - 1) * stride
        for index, value in enumerate(row):
            left = row[index - 3] if index >= 3 else 0
            above = decoded[prior_start + index] if row_index else 0
            upper_left = (
                decoded[prior_start + index - 3]
                if row_index and index >= 3
                else 0
            )
            if filter_kind == 0:
                restored = value
            elif filter_kind == 1:
                restored = value + left
            elif filter_kind == 2:
                restored = value + above
            elif filter_kind == 3:
                restored = value + ((left + above) // 2)
            elif filter_kind == 4:
                restored = value + _paeth(left, above, upper_left)
            else:
                raise ValueError(f"unsupported PNG row filter: {filter_kind}")
            row[index] = restored & 0xFF
        start = row_index * stride
        decoded[start : start + stride] = row
    return width, height, bytes(decoded)


def quantize_332(rgb: bytes) -> bytes:
    output = bytearray(len(rgb) // 3)
    for index in range(0, len(rgb), 3):
        red, green, blue = rgb[index : index + 3]
        output[index // 3] = (red & 0xE0) | ((green & 0xE0) >> 3) | (blue >> 6)
    return bytes(output)


def palette_332() -> bytes:
    palette = bytearray()
    for index in range(256):
        red = ((index >> 5) & 0x07) * 255 // 7
        green = ((index >> 2) & 0x07) * 255 // 7
        blue = (index & 0x03) * 255 // 3
        palette.extend((red, green, blue))
    return bytes(palette)


def lzw_encode(indexes: bytes) -> bytes:
    clear_code = 256
    end_code = 257
    table = {bytes((value,)): value for value in range(256)}
    next_code = 258
    code_width = 9
    output = bytearray()
    bit_buffer = 0
    bit_count = 0

    def emit(code: int) -> None:
        nonlocal bit_buffer, bit_count
        bit_buffer |= code << bit_count
        bit_count += code_width
        while bit_count >= 8:
            output.append(bit_buffer & 0xFF)
            bit_buffer >>= 8
            bit_count -= 8

    emit(clear_code)
    current = bytes((indexes[0],))
    for value in indexes[1:]:
        combined = current + bytes((value,))
        if combined in table:
            current = combined
            continue
        emit(table[current])
        if next_code < 4096:
            table[combined] = next_code
            next_code += 1
            # The encoder creates a dictionary entry one emitted code before the decoder can
            # create the same entry. Defer the width increase until the following insertion so
            # both sides switch widths before the same code.
            if next_code > (1 << code_width) and code_width < 12:
                code_width += 1
        else:
            emit(clear_code)
            table = {bytes((item,)): item for item in range(256)}
            next_code = 258
            code_width = 9
        current = bytes((value,))
    emit(table[current])
    emit(end_code)
    if bit_count:
        output.append(bit_buffer & 0xFF)
    return bytes(output)


def _subblocks(payload: bytes) -> bytes:
    blocks = bytearray()
    for offset in range(0, len(payload), 255):
        block = payload[offset : offset + 255]
        blocks.append(len(block))
        blocks.extend(block)
    blocks.append(0)
    return bytes(blocks)


def write_gif(
    frames: list[tuple[int, int, bytes]],
    output: Path,
    *,
    delay_centiseconds: int,
) -> None:
    if not frames:
        raise ValueError("at least one frame is required")
    width, height, _indexes = frames[0]
    if any((frame_width, frame_height) != (width, height) for frame_width, frame_height, _ in frames):
        raise ValueError("all GIF frames must use the same dimensions")
    payload = bytearray(b"GIF89a")
    payload.extend(struct.pack("<HH", width, height))
    payload.extend((0xF7, 0, 0))
    payload.extend(palette_332())
    payload.extend(b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
    for _frame_width, _frame_height, indexes in frames:
        payload.extend(b"\x21\xf9\x04\x00")
        payload.extend(struct.pack("<H", delay_centiseconds))
        payload.extend(b"\x00\x00")
        payload.extend(b"\x2c\x00\x00\x00\x00")
        payload.extend(struct.pack("<HH", width, height))
        payload.append(0)
        payload.append(8)
        payload.extend(_subblocks(lzw_encode(indexes)))
    payload.append(0x3B)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)


def extract_frames(
    ffmpeg: Path,
    source: Path,
    *,
    start_seconds: float,
    duration_seconds: int,
    interval_seconds: int,
    width: int,
) -> list[tuple[int, int, bytes]]:
    frames: list[tuple[int, int, bytes]] = []
    with tempfile.TemporaryDirectory(prefix="mhc-demo-gif-") as temporary:
        root = Path(temporary)
        for frame_index, second in enumerate(
            range(0, duration_seconds, interval_seconds)
        ):
            frame_path = root / f"frame-{frame_index:03d}.png"
            subprocess.run(
                [
                    str(ffmpeg),
                    "-ss",
                    str(start_seconds + second),
                    "-i",
                    str(source),
                    "-vf",
                    f"scale={width}:-2",
                    "-frames:v",
                    "1",
                    "-y",
                    str(frame_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            frame_width, frame_height, rgb = read_rgb_png(frame_path)
            frames.append((frame_width, frame_height, quantize_332(rgb)))
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-seconds", type=float, default=60)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=int, default=2)
    parser.add_argument("--width", type=int, default=640)
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.interval_seconds <= 0 or args.width <= 0:
        raise SystemExit("duration, interval, and width must be positive")
    frames = extract_frames(
        args.ffmpeg,
        args.input,
        start_seconds=args.start_seconds,
        duration_seconds=args.duration_seconds,
        interval_seconds=args.interval_seconds,
        width=args.width,
    )
    write_gif(
        frames,
        args.output,
        delay_centiseconds=args.interval_seconds * 100,
    )
    print(
        f"[OK] Wrote {len(frames)} frames / {args.duration_seconds}s to {args.output}"
    )


if __name__ == "__main__":
    main()
