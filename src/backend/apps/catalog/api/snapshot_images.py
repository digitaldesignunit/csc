"""Encode and compress snapshot user photos (JPEG on disk)."""

from __future__ import annotations

import io
import os
from typing import Tuple

from PIL import Image

PHOTO_EXTENSION = '.jpg'
PHOTO_MEDIA_TYPE = 'image/jpeg'


def photo_filename(index: int) -> str:
    return f'{index}{PHOTO_EXTENSION}'


def compress_and_save_jpeg(
    image: Image.Image,
    dest_path: str,
    *,
    max_bytes: int,
    max_long_edge_px: int,
) -> Tuple[int, int, int]:
    """
    Write a JPEG at *dest_path* not larger than *max_bytes*.

    Returns (file_size_bytes, width, height).
    """
    if max_bytes < 1:
        raise ValueError('max_bytes must be positive')
    if max_long_edge_px < 1:
        raise ValueError('max_long_edge_px must be positive')

    working = image.convert('RGB')
    if max(working.size) > max_long_edge_px:
        working.thumbnail(
            (max_long_edge_px, max_long_edge_px),
            Image.Resampling.LANCZOS,
        )

    quality = 88
    scale = 1.0
    best_payload: bytes | None = None

    for _ in range(40):
        candidate = working
        if scale < 1.0:
            w, h = working.size
            candidate = working.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )

        buf = io.BytesIO()
        candidate.save(
            buf,
            format='JPEG',
            quality=quality,
            optimize=True,
            progressive=True,
        )
        payload = buf.getvalue()
        best_payload = payload

        if len(payload) <= max_bytes:
            os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
            with open(dest_path, 'wb') as handle:
                handle.write(payload)
            return len(payload), candidate.size[0], candidate.size[1]

        if quality > 42:
            quality -= 8
            continue
        if scale > 0.3:
            scale *= 0.85
            quality = 88
            continue
        break

    if best_payload is None:
        raise RuntimeError('failed to encode JPEG')

    os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
    with open(dest_path, 'wb') as handle:
        handle.write(best_payload)
    w, h = working.size
    if scale < 1.0:
        w = max(1, int(w * scale))
        h = max(1, int(h * scale))
    return len(best_payload), w, h
