#!/usr/bin/env python3.13
"""
Evidence attachment files (data model spec section 3.5; decisions 7.3, 7.13,
8.13; I24): sniffed, never trusted by name or declared type; a PDF stored
byte for byte, an image through the snapshot photo pipeline (EXIF GPS, owner
and serial stripped, re-encoded as JPEG); one copy per record, a hard link
where the file system allows and a copy where not; ``sha256`` over the
stored bytes.

Blocking functions: the routes run them with ``asyncio.to_thread``.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

PDF = 'application/pdf'
JPEG = 'image/jpeg'
EXTENSION: Dict[str, str] = {PDF: 'pdf', JPEG: 'jpg'}
MAX_ATTACHMENTS = 30                  # per record, removed ones included
MAX_NAME = 200
_UNSAFE_NAME = re.compile(r'[\x00-\x1f\x7f/\\]')


class UnsupportedFile(ValueError):
    """The bytes are neither a PDF nor a usable image."""


@dataclass(frozen=True)
class StoredCopy:
    """One processed upload waiting under the temp name."""
    path: str
    media_type: str
    size: int
    sha256: str


def sniff(raw: bytes) -> Optional[str]:
    """``application/pdf`` or ``image`` (png, jpeg, webp) by magic bytes;
    None for anything else. A PDF header may follow a few bytes of junk
    (the spec allows the first 1024)."""
    if b'%PDF-' in raw[:1024]:
        return PDF
    if raw[:3] == b'\xff\xd8\xff' or raw[:8] == b'\x89PNG\r\n\x1a\n' or (
            raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'):
        return 'image'
    return None


def safe_name(name: Optional[str], fallback: str = 'attachment') -> str:
    """The file name as stored in ``attachments[]``: no path, no control
    characters, bounded."""
    base = (name or '').replace('\\', '/').rsplit('/', 1)[-1]
    base = _UNSAFE_NAME.sub('', base).strip().strip('.')
    return (base or fallback)[:MAX_NAME]


def file_path(root: str, record_id: str, index: int, media_type: str) -> str:
    """``<root>/<record id>/<index>.<ext>``; the id is a UUID and the
    extension one of two, so the path cannot leave ``root``."""
    uuid.UUID(record_id)
    if media_type not in EXTENSION:
        raise ValueError(f'unsupported stored type {media_type!r}')
    return os.path.join(root, record_id, f'{int(index)}.{EXTENSION[media_type]}')


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def process_upload(raw: bytes, root: str, *, max_image_bytes: int,
                   max_long_edge_px: int) -> StoredCopy:
    """Turn an upload into the bytes that are stored, under a temp name in
    ``root``. Raises ``UnsupportedFile``."""
    # imported here: the api package imports its routers, which import this
    from apps.catalog.api.snapshot_images import (
        compress_and_save_jpeg,
        open_upload_photo,
    )
    kind = sniff(raw)
    if kind is None:
        raise UnsupportedFile('only PDF documents and JPEG, PNG or WebP '
                              'images can be attached')
    temp_dir = os.path.join(root, '.incoming')
    os.makedirs(temp_dir, exist_ok=True)
    temp = os.path.join(temp_dir, uuid.uuid4().hex)
    if kind == PDF:
        with open(temp, 'wb') as handle:
            handle.write(raw)
        media_type = PDF
    else:
        try:
            image = open_upload_photo(raw)
        except Exception as exc:
            raise UnsupportedFile('not a readable image') from exc
        try:
            compress_and_save_jpeg(image, temp, max_bytes=max_image_bytes,
                                   max_long_edge_px=max_long_edge_px)
        except Exception:
            if os.path.exists(temp):
                os.remove(temp)
            raise
        media_type = JPEG
    return StoredCopy(path=temp, media_type=media_type,
                      size=os.path.getsize(temp), sha256=_sha256(temp))


def place_copy(copy: StoredCopy, root: str, record_id: str, index: int
               ) -> str:
    """The stored file of one record: a hard link to the processed upload,
    else a copy (7.3: every record owns its files, nothing is shared)."""
    dest = file_path(root, record_id, index, copy.media_type)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    try:
        os.link(copy.path, dest)
    except OSError:
        shutil.copy2(copy.path, dest)
    return dest


def discard_temp(copy: StoredCopy) -> None:
    try:
        os.remove(copy.path)
    except OSError:
        pass


def remove_file(root: str, record_id: str, index: int,
                media_type: str) -> bool:
    try:
        path = file_path(root, record_id, index, media_type)
    except ValueError:
        return False
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def remove_record_files(root: str, record_id: str) -> None:
    """Everything of one record (it was deleted or purged)."""
    try:
        uuid.UUID(record_id)
    except ValueError:
        return
    shutil.rmtree(os.path.join(root, record_id), ignore_errors=True)


def next_index(attachments: List[dict]) -> int:
    """Indices are never reused, tombstones included (I24)."""
    return max((a['index'] for a in attachments), default=-1) + 1
