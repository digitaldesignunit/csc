"""Encode and compress snapshot user photos (JPEG on disk)."""

from __future__ import annotations

import io
import os
from typing import Any, Dict, Optional, Tuple

from PIL import Image

PHOTO_EXTENSION = '.jpg'
PHOTO_MEDIA_TYPE = 'image/jpeg'

# EXIF kept on stored photos (design decision 7.13): orientation, capture
# time and camera make / model. Everything else is dropped --- GPS position,
# artist, copyright, owner and serial numbers, maker notes, and any tag not
# listed here. Photos are served to anonymous readers of public components.
_KEEP_IFD0_TAGS = (
    0x0112,  # Orientation
    0x010F,  # Make
    0x0110,  # Model
)
_EXIF_IFD = 0x8769
_KEEP_EXIF_IFD_TAGS = (
    0x9003,  # DateTimeOriginal
    0x9011,  # OffsetTimeOriginal
)


def photo_filename(index: int) -> str:
    return f'{index}{PHOTO_EXTENSION}'


def open_upload_photo(raw: bytes) -> Image.Image:
    """
    Load uploaded image bytes without applying EXIF orientation transforms.

    Pixel data is kept as stored in the file; orientation metadata (if any)
    survives :func:`compress_and_save_jpeg`, which keeps only the EXIF tags
    listed above.
    """
    image = Image.open(io.BytesIO(raw))
    image.load()
    return image


def sanitized_exif(image: Image.Image) -> Optional[Image.Exif]:
    """Return a new Exif holding only the kept tags, or None if none remain."""
    try:
        source = image.getexif()
    except Exception:
        return None
    kept = Image.Exif()
    for tag in _KEEP_IFD0_TAGS:
        if tag in source:
            kept[tag] = source[tag]
    try:
        exif_ifd = source.get_ifd(_EXIF_IFD)
    except Exception:
        exif_ifd = {}
    kept_sub = {t: exif_ifd[t] for t in _KEEP_EXIF_IFD_TAGS if t in exif_ifd}
    if kept_sub:
        kept.get_ifd(_EXIF_IFD).update(kept_sub)
    if len(kept) == 0 and not kept_sub:
        return None
    return kept


def _jpeg_exif_save_kwargs(image: Image.Image) -> Dict[str, Any]:
    """Keep orientation, capture time and camera; drop everything else."""
    exif = sanitized_exif(image)
    return {'exif': exif} if exif is not None else {}


def strip_jpeg_metadata(jpeg: bytes, exif: Optional[Image.Exif]) -> bytes:
    """
    Rewrite a stored JPEG's metadata without re-encoding its pixels.

    Drops every EXIF and XMP (APP1) and IPTC (APP13) segment and inserts
    *exif* (if any) as the only APP1 segment after SOI / APP0. The scan data
    is copied byte for byte, so repeated runs never lose quality.
    """
    if jpeg[:2] != b'\xff\xd8':
        raise ValueError('not a JPEG')
    kept_segments = []
    i = 2
    scan_data = b''
    while i < len(jpeg):
        if jpeg[i] != 0xFF:
            raise ValueError(f'bad JPEG marker at byte {i}')
        marker = jpeg[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA or marker == 0xD9:  # start of scan / end of image
            scan_data = jpeg[i:]
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # no length field
            kept_segments.append(jpeg[i:i + 2])
            i += 2
            continue
        length = int.from_bytes(jpeg[i + 2:i + 4], 'big')
        segment = jpeg[i:i + 2 + length]
        if marker not in (0xE1, 0xED):  # APP1 = EXIF / XMP, APP13 = IPTC
            kept_segments.append(segment)
        i += 2 + length

    insert_at = 0
    while (insert_at < len(kept_segments)
           and kept_segments[insert_at][1] == 0xE0):  # after APP0 (JFIF)
        insert_at += 1
    if exif is not None:
        payload = exif.tobytes()  # starts with b'Exif\x00\x00'
        app1 = b'\xff\xe1' + (len(payload) + 2).to_bytes(2, 'big') + payload
        kept_segments.insert(insert_at, app1)
    return b'\xff\xd8' + b''.join(kept_segments) + scan_data


def compress_and_save_jpeg(
    image: Image.Image,
    dest_path: str,
    *,
    max_bytes: int,
    max_long_edge_px: int,
) -> Tuple[int, int, int]:
    """
    Write a JPEG at *dest_path* not larger than *max_bytes*.

    Does not rotate or ``exif_transpose``; embeds the sanitized EXIF
    (orientation, capture time, make / model) when present.

    Returns (file_size_bytes, width, height).
    """
    if max_bytes < 1:
        raise ValueError('max_bytes must be positive')
    if max_long_edge_px < 1:
        raise ValueError('max_long_edge_px must be positive')

    exif_kwargs = _jpeg_exif_save_kwargs(image)
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
            **exif_kwargs,
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
