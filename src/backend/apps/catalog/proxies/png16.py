#!/usr/bin/env python3.13
"""
16-bit RGB PNG, written and read without an imaging library.

Pillow cannot write a three-channel 16-bit PNG, and the deviation maps need
one (spec appendix B: distance, normal deviation, occupancy). The format is
small enough to write by hand: signature, IHDR (colour type 2, depth 16),
one zlib-compressed IDAT with filter type 0, IEND.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import struct
import zlib

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np

_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))


def encode_rgb16(image: np.ndarray) -> bytes:
    """``(height, width, 3)`` uint16 array -> PNG bytes."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f'need (h, w, 3), got {image.shape}')
    height, width, _ = image.shape
    big_endian = np.ascontiguousarray(image.astype('>u2'))
    rows = big_endian.reshape(height, width * 3)
    raw = b''.join(b'\x00' + rows[i].tobytes() for i in range(height))
    header = struct.pack('>IIBBBBB', width, height, 16, 2, 0, 0, 0)
    return (_SIGNATURE + _chunk(b'IHDR', header)
            + _chunk(b'IDAT', zlib.compress(raw, 6)) + _chunk(b'IEND', b''))


def decode_rgb16(data: bytes) -> np.ndarray:
    """PNG bytes written by ``encode_rgb16`` -> ``(h, w, 3)`` uint16."""
    if data[:8] != _SIGNATURE:
        raise ValueError('not a PNG')
    position, header, idat = 8, None, b''
    while position < len(data):
        length, = struct.unpack('>I', data[position:position + 4])
        kind = data[position + 4:position + 8]
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            idat += body
    if header is None or header[2:] != (16, 2, 0, 0, 0):
        raise ValueError('only 16-bit RGB PNGs without interlace')
    width, height = header[0], header[1]
    raw = zlib.decompress(idat)
    stride = width * 6 + 1
    rows = []
    for i in range(height):
        line = raw[i * stride:(i + 1) * stride]
        if line[0] != 0:
            raise ValueError('only filter type 0')
        rows.append(np.frombuffer(line[1:], dtype='>u2').reshape(width, 3))
    return np.stack(rows).astype(np.uint16)
