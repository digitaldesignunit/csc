"""Encode and compress snapshot user photos (JPEG on disk)."""

from __future__ import annotations

import io
import os
import re
import struct
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from PIL import Image

PHOTO_EXTENSION = '.jpg'
PHOTO_MEDIA_TYPE = 'image/jpeg'

# EXIF kept on stored photos (design decision 7.13): orientation, capture
# time and camera make / model. Everything else is dropped --- GPS position,
# artist, copyright, owner and serial numbers, maker notes, the JPEG comment,
# and any tag not listed here. Photos are served to anonymous readers of
# public components. A kept tag has to be small (8.197 f): the orientation a
# number from 1 to 8, the others text of at most ``MAX_KEPT_TEXT`` characters;
# a tag that is not is dropped, not cut.
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
_ORIENTATION = 0x0112
MAX_KEPT_TEXT = 64


def photo_filename(index: int) -> str:
    return f'{index}{PHOTO_EXTENSION}'


# decoded size above which an upload is refused before any pixel is decoded
# (S6, 8.144): a small file can hold a very large canvas
MAX_UPLOAD_PIXELS = 40_000_000
# Pillow holds four canvases of a WebP (a 40 MP file costs 730 MB, a 16 MP one
# 330 MB; a 40 MP PNG 410 MB), so a WebP gets a lower limit (8.197 f). A phone
# photo has 12.2 to 12.5 MP.
MAX_UPLOAD_WEBP_PIXELS = 16_000_000
# EXIF above this size is refused (8.197): Pillow's EXIF reader is quadratic in
# repeated markers, so a few hundred KB of them cost seconds. A phone writes
# 10 to 50 KB, with a maker note of up to about 60 KB.
MAX_UPLOAD_EXIF_BYTES = 256 * 1024
# The TIFF directories Pillow reads (8.197 f): its reader lets every entry
# point at the same bytes, so n entries of m bytes cost n x m. A directory has
# at most this many entries; the value bytes the directories of a file declare
# add up (duplicate tags and a directory that two pointers lead to count each
# time) to at most the cap (the multi-picture directories of a JPEG: 4 KB).
MAX_TIFF_ENTRIES = 512
MAX_MPF_BYTES = 4 * 1024
# The entries all the directories of a file may have in the data, read or
# skipped (an entry of an unknown type costs no value bytes but a turn of the
# loop): about the entries of a phone photo, 30 times over. At most two
# pointers to the Exif directory per block.
MAX_FILE_ENTRIES = 2048
MAX_EXIF_POINTERS = 2
# more scans than this in a JPEG are refused: libjpeg decodes every scan of a
# progressive file over all its pixels (a normal file has about 10)
MAX_JPEG_SCANS = 64
UPLOAD_FORMATS = ['JPEG', 'PNG', 'WEBP']
# chunks (PNG, WebP) or segments and fill runs (JPEG) the check of the raw
# bytes walks: a real file has a few dozen, a flood of empty ones costs a loop
_MAX_CHUNKS = 50_000
_MAX_JPEG_STEPS = 10_000
# a PNG text chunk of this key is read by Pillow as EXIF (hex text); its
# inflated size is not visible in the raw bytes
_PNG_RAW_EXIF_KEY = 'Raw profile type exif'
_EXIF_REFUSED = ('the image carries EXIF metadata with too many entries '
                 'or too much data')
_MPF_REFUSED = ('the image carries multi-picture metadata with too many '
                'entries or too much data')


class UnreadableImage(ValueError):
    """The bytes are not a JPEG, PNG or WebP image the server will decode."""


class ImageTooLarge(UnreadableImage):
    """The image declares more pixels than the limit of its format."""


class RawImageInfo(NamedTuple):
    """What the bytes of an image file declare, read without decoding."""
    width: int
    height: int
    exif_bytes: int
    format: str = ''


def _unreadable() -> UnreadableImage:
    return UnreadableImage('not a readable image')


# --- the TIFF directories of an EXIF block ------------------------------------
# value sizes of the TIFF types Pillow decodes (TiffImagePlugin); an entry of
# another type is skipped by it
_TIFF_UNIT = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
              11: 4, 12: 8, 13: 4, 16: 8}
# the headers ``ImageFileDirectory_v2`` accepts (PREFIXES)
_TIFF_HEADERS = (b'MM\x00\x2a', b'II\x2a\x00', b'MM\x2a\x00', b'II\x00\x2a',
                 b'MM\x00\x2b', b'II\x2b\x00')
_EXIF_MARKER = b'Exif\x00\x00'


def _tiff_start(blob: bytes, skip_marker: bool) -> Optional[Tuple[int, str, int]]:
    """Where the TIFF stream of *blob* starts, its byte order and the offset
    of its first directory, as Pillow reads them; None when Pillow cannot
    read the header (it then reads nothing and the block is harmless)."""
    pos = 0
    while skip_marker and blob.startswith(_EXIF_MARKER, pos):
        pos += len(_EXIF_MARKER)       # Pillow strips every leading marker
    head = blob[pos:pos + 8]
    # byte 2 of an 'II+' header: Pillow takes it for BigTIFF and then fails
    if len(head) < 8 or head[:4] not in _TIFF_HEADERS or head[2] == 0x2B:
        return None
    order = '>' if head[:2] == b'MM' else '<'
    return pos, order, struct.unpack(order + 'L', head[4:8])[0]


class _Budget:
    """What the directories of ONE file may cost altogether: value bytes of
    the EXIF directories, value bytes of the multi-picture directories, and
    entries looked at (all of them, whatever their type)."""

    def __init__(self) -> None:
        self.value_bytes = MAX_UPLOAD_EXIF_BYTES
        self.mpf_bytes = MAX_MPF_BYTES
        self.entries = MAX_FILE_ENTRIES

    def look(self, count: int, message: str) -> None:
        self.entries -= count
        if self.entries < 0:
            raise UnreadableImage(message)


def _read_directory(blob: bytes, base: int, offset: int, order: str,
                    limit: int, cache: dict, message: str, budget: _Budget
                    ) -> Tuple[list, Tuple[int, int]]:
    """The entries ``ImageFileDirectory_v2.load`` keeps from the directory at
    *offset* of the TIFF stream that starts at *base*, and (entries, value
    bytes). Pillow stops at the first value that lies behind the data, and so
    does this; over the limits: ``UnreadableImage``. A directory is parsed once
    (a second pointer to it is charged the entries again, not parsed)."""
    if offset in cache:
        entries, stats, looked = cache[offset]
        budget.look(looked, message)
        return entries, stats
    end = len(blob)
    at = base + offset
    entries: list = []
    total = 0
    looked = 0
    if at + 2 <= end:
        declared = struct.unpack_from(order + 'H', blob, at)[0]
        at += 2
        for seen in range(declared):
            if at + 12 > end:
                break
            if seen >= MAX_TIFF_ENTRIES:
                raise UnreadableImage(message)
            budget.look(1, message)
            looked += 1
            tag, typ, count = struct.unpack_from(order + 'HHL', blob, at)
            field = blob[at + 8:at + 12]
            at += 12
            unit = _TIFF_UNIT.get(typ)
            if unit is None:
                continue
            size = count * unit
            if size > 4 and base + struct.unpack(order + 'L', field)[0] + size > end:
                break
            if size == 0:
                continue
            total += size
            if total > limit:
                raise UnreadableImage(message)
            entries.append((tag, typ, count, field))
    result = (entries, (len(entries), total))
    cache[offset] = (entries, result[1], looked)
    return result


def _charge(budget: _Budget, stats: Tuple[int, int], message: str) -> None:
    budget.value_bytes -= stats[1]
    if budget.value_bytes < 0:
        raise UnreadableImage(message)


def _exif_directory_stats(blob: bytes, budget: Optional[_Budget] = None
                          ) -> List[Tuple[int, int]]:
    """Check the directories that ``Image.open``, ``getexif`` and
    ``get_ifd(0x8769)`` decode from an EXIF block (IFD0 and the Exif
    directory its pointer leads to) and return (entries, value bytes) of each,
    as Pillow reads them. Pillow follows the last pointer entry; every one is
    followed here. The thumbnail directory (IFD1) is linked from IFD0 and
    never read, so it is not looked at. *budget* is what is left of the work
    of the file (value bytes and entries). ``UnreadableImage`` over the
    limits, for more than ``MAX_EXIF_POINTERS`` pointers or for an Exif
    pointer that is not one SHORT, LONG or IFD value."""
    start = _tiff_start(blob, True)
    if start is None:
        return []
    if budget is None:
        budget = _Budget()
    base, order, first = start
    cache: dict = {}
    entries, stats = _read_directory(
        blob, base, first, order, MAX_UPLOAD_EXIF_BYTES, cache, _EXIF_REFUSED,
        budget)
    _charge(budget, stats, _EXIF_REFUSED)
    result = [stats]
    pointers = [entry for entry in entries if entry[0] == _EXIF_IFD]
    if len(pointers) > MAX_EXIF_POINTERS:
        raise UnreadableImage(_EXIF_REFUSED)
    for tag, typ, count, field in pointers:
        if count != 1 or typ not in (3, 4, 13):
            raise UnreadableImage(_EXIF_REFUSED)
        pointer = struct.unpack(
            order + ('H' if typ == 3 else 'L'), field[:2 if typ == 3 else 4])[0]
        stats = _read_directory(
            blob, base, pointer, order, MAX_UPLOAD_EXIF_BYTES, cache,
            _EXIF_REFUSED, budget)[1]
        _charge(budget, stats, _EXIF_REFUSED)
        result.append(stats)
    return result


def _check_exif_blob(blob: bytes, budget: Optional[_Budget] = None) -> None:
    _exif_directory_stats(blob, budget)


def _check_mpf(payload: bytes, budget: _Budget) -> None:
    """The multi-picture directory of a JPEG (APP2 ``MPF\\0``, after those four
    bytes): Pillow reads its first directory in ``Image.open``."""
    start = _tiff_start(payload, False)
    if start is not None:
        stats = _read_directory(payload, start[0], start[2], start[1],
                                MAX_MPF_BYTES, {}, _MPF_REFUSED, budget)[1]
        budget.mpf_bytes -= stats[1]
        if budget.mpf_bytes < 0:
            raise UnreadableImage(_MPF_REFUSED)


# --- the walk of the file ------------------------------------------------------
def _scan_png(raw: bytes) -> RawImageInfo:
    # Pillow takes the size from IHDR, and a later IHDR replaces an earlier
    # one, so the largest of them counts; the frames of an animated PNG (fcTL)
    # must lie inside the canvas, or Pillow refuses the file before it
    # allocates anything. The eXIf chunk may come after the image data, so
    # every chunk up to IEND is read. Pillow keeps the last of the eXIf chunks
    # and the tEXt chunks keyed `exif`; every one of them is checked.
    size = None
    exif = 0
    blobs = []
    pos = 8
    end_of_file = len(raw)
    for _ in range(_MAX_CHUNKS):
        if pos + 12 > end_of_file:
            break
        length = int.from_bytes(raw[pos:pos + 4], 'big')
        kind = raw[pos + 4:pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > end_of_file:        # a truncated chunk: Pillow fails
            break
        if size is None and kind != b'IHDR':
            raise _unreadable()          # the first chunk is IHDR
        if kind == b'IHDR':
            if length < 8:
                raise _unreadable()
            found = struct.unpack('>II', raw[start:start + 8])
            if size is None or found[0] * found[1] > size[0] * size[1]:
                size = found
        elif kind == b'IEND':
            break
        elif kind == b'eXIf':
            exif += length
            blobs.append((start, end))
        elif kind in (b'tEXt', b'zTXt', b'iTXt'):
            key = raw[start:min(end, start + 22)].split(b'\x00', 1)[0]
            if key in (b'exif', _PNG_RAW_EXIF_KEY.encode('ascii')):
                exif += length
                if kind == b'tEXt' and key == b'exif':
                    blobs.append((start + len(key) + 1, end))
        pos = end + 4
    else:
        raise _unreadable()              # more chunks than a real file has
    if size is None:
        raise _unreadable()
    if exif <= MAX_UPLOAD_EXIF_BYTES:
        budget = _Budget()
        for start, end in blobs:
            _check_exif_blob(raw[start:end], budget)
    return RawImageInfo(size[0], size[1], exif, 'PNG')


def _scan_webp(raw: bytes) -> RawImageInfo:
    # a still image declares its size in VP8 or VP8L, an extended file
    # (animation, EXIF, ICC) in the VP8X canvas, which is what the animation
    # decoder allocates: libwebp refuses a frame outside the canvas. The
    # largest declaration counts.
    best = None
    exif = 0
    blobs = []
    pos = 12
    end_of_file = len(raw)
    for _ in range(_MAX_CHUNKS):
        if pos + 8 > end_of_file:
            break
        kind = raw[pos:pos + 4]
        length = int.from_bytes(raw[pos + 4:pos + 8], 'little')
        start = pos + 8
        end = start + length
        head = raw[start:start + 10]
        size = None
        if kind == b'VP8X' and len(head) >= 10:
            size = (1 + int.from_bytes(head[4:7], 'little'),
                    1 + int.from_bytes(head[7:10], 'little'))
        elif (kind == b'VP8 ' and len(head) >= 10
              and head[3:6] == b'\x9d\x01\x2a'):
            size = (int.from_bytes(head[6:8], 'little') & 0x3FFF,
                    int.from_bytes(head[8:10], 'little') & 0x3FFF)
        elif kind == b'VP8L' and len(head) >= 5 and head[0] == 0x2F:
            bits = int.from_bytes(head[1:5], 'little')
            size = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        elif kind == b'EXIF':
            exif += min(length, end_of_file - start)
            blobs.append((start, min(end, end_of_file)))
        if size is not None and (best is None
                                 or size[0] * size[1] > best[0] * best[1]):
            best = size
        if end > end_of_file:
            break
        pos = end + (length & 1)         # chunks are padded to even length
    else:
        raise _unreadable()
    if best is None:
        raise _unreadable()
    if exif <= MAX_UPLOAD_EXIF_BYTES:
        budget = _Budget()
        for start, end in blobs:
            _check_exif_blob(raw[start:end], budget)
    return RawImageInfo(best[0], best[1], exif, 'WEBP')


# in a JPEG every marker has a length except these; Pillow (JpegImagePlugin)
# refuses the file at any other marker byte, and so do we
_JPEG_NO_LENGTH = frozenset(
    [0xC8, *range(0xD0, 0xDA), *range(0xF0, 0xFE)])
_JPEG_WITH_LENGTH = frozenset(
    [*range(0xC0, 0xC8), *range(0xC9, 0xD0), *range(0xDA, 0xF0), 0xFE])
_JPEG_SOF = frozenset(
    [*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC),
     *range(0xCD, 0xD0), 0xDE])
# Pillow skips any byte that is not 0xFF between segments, and 0xFF 0x00; the
# entropy-coded data of a scan is made of the same, and of restart markers
_JPEG_FILLER = re.compile(rb'(?:[^\xff]++|\xff\x00|\xff[\xd0-\xd7])*+')
_JPEG_FF_RUN = re.compile(rb'\xff+')


def _scan_jpeg(raw: bytes) -> RawImageInfo:
    # Walks the segments as Pillow does up to the first SOS (the same junk,
    # fill and length rules), at the speed of the regular expressions for
    # the filler. It then goes on through the scans, by the length of their
    # marker segments and over the entropy data, up to the first EOI, only to
    # count the SOS headers: what follows the EOI (the second picture of an
    # MPO, the video of a motion photo) is not decoded and not walked. A
    # marker segment (0xC0 and up) whose length runs over the end ends the
    # walk: libjpeg cannot pass it either.
    best = None
    exif = 0
    exif_parts = []
    mpf_parts = []
    scans = 0
    pos = 2
    end_of_file = len(raw)
    for _ in range(_MAX_JPEG_STEPS):
        pos = _JPEG_FILLER.match(raw, pos).end()
        if pos + 1 >= end_of_file:
            break
        marker = raw[pos + 1]
        if marker == 0xFF:               # fill: the marker is the last 0xFF
            pos = _JPEG_FF_RUN.match(raw, pos).end() - 1
            continue
        if marker == 0xD9 and scans:     # the end of the first picture
            break
        # a marker below 0xC0 after the first SOS has no length here: with a
        # restart interval libjpeg skips it (jpeg_resync_to_restart) and goes
        # on, so only the end of the data or the EOI ends the walk
        if marker in _JPEG_NO_LENGTH or (scans and marker < 0xC0):
            pos += 2
            continue
        if marker not in _JPEG_WITH_LENGTH or pos + 4 > end_of_file:
            if scans:
                break
            raise _unreadable()
        length = int.from_bytes(raw[pos + 2:pos + 4], 'big')
        start = pos + 4
        end = start + max(length - 2, 0)
        if end > end_of_file:            # a truncated segment: Pillow fails
            if scans:
                break
            raise _unreadable()
        if marker == 0xDA:
            if not scans and best is None:
                raise _unreadable()
            scans += 1
            if scans > MAX_JPEG_SCANS:
                raise UnreadableImage(
                    f'the image has more than {MAX_JPEG_SCANS} scans; '
                    f'the limit is {MAX_JPEG_SCANS}')
        elif not scans and marker in _JPEG_SOF:   # precision, height, width
            if end - start < 6:
                raise _unreadable()
            size = (int.from_bytes(raw[start + 3:start + 5], 'big'),
                    int.from_bytes(raw[start + 1:start + 3], 'big'))
            if best is None or size[0] * size[1] > best[0] * best[1]:
                best = size
        elif not scans and marker == 0xE1 and raw.startswith(
                _EXIF_MARKER, start, end):
            exif += end - start          # Pillow joins these segments
            exif_parts.append((start, end))
        elif not scans and marker == 0xE2 and raw.startswith(
                b'MPF\x00', start, end):
            mpf_parts.append((start + 4, end))
        pos = end
    else:
        raise _unreadable()
    if not scans:
        raise _unreadable()
    budget = _Budget()
    if exif and exif <= MAX_UPLOAD_EXIF_BYTES:
        first, *rest = exif_parts
        # the first segment whole, the next ones without their marker
        _check_exif_blob(raw[first[0]:first[1]] + b''.join(
            raw[s + len(_EXIF_MARKER):e] for s, e in rest), budget)
    for start, end in mpf_parts:
        _check_mpf(raw[start:end], budget)
    return RawImageInfo(best[0], best[1], exif, 'JPEG')


def _scan_raw(raw: bytes) -> RawImageInfo:
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return _scan_png(raw)
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return _scan_webp(raw)
    if raw[:3] == b'\xff\xd8\xff':
        return _scan_jpeg(raw)
    raise UnreadableImage('not a JPEG, PNG or WebP image')


def read_raw_image_info(raw: bytes) -> RawImageInfo:
    """
    The declared width and height and the total size of the EXIF data of a
    JPEG, PNG or WebP file, read from the bytes themselves (8.197); also
    refuses (``UnreadableImage``) EXIF whose TIFF directories are over the
    limits, a multi-picture directory over its limit and a JPEG of more than
    ``MAX_JPEG_SCANS`` scans.

    Nothing is decoded or inflated and Pillow is not used: a few hundred
    bytes can declare a canvas of hundreds of megabytes (an animated PNG or
    WebP, which Pillow allocates while it opens the file) and a few hundred
    KB of repeated markers cost seconds in Pillow's EXIF reader. The work is
    linear in the size of the file and stays inside it. Raises
    ``UnreadableImage`` when the size cannot be found.
    """
    try:
        return _scan_raw(raw)
    except UnreadableImage:
        raise
    except (IndexError, ValueError, OverflowError, struct.error) as exc:
        raise _unreadable() from exc


def _too_large(pixels: int, limit: int, kind: str = '') -> str:
    megapixels = -(-pixels // 1_000_000)
    if kind:
        return (f'{kind} image of {megapixels} megapixels; '
                f'the limit for {kind} is {limit // 1_000_000}')
    return (f'image of {megapixels} megapixels; '
            f'the limit is {limit // 1_000_000}')


def _pixel_limit(image_format: str) -> Tuple[int, str]:
    if image_format == 'WEBP':
        return MAX_UPLOAD_WEBP_PIXELS, 'WebP'
    return MAX_UPLOAD_PIXELS, ''


def open_upload_photo(raw: bytes) -> Image.Image:
    """
    Load uploaded image bytes without applying EXIF orientation transforms.

    Pixel data is kept as stored in the file; orientation metadata (if any)
    survives :func:`compress_and_save_jpeg`, which keeps only the EXIF tags
    listed above.

    The bytes are sniffed (magic numbers, not the declared type) and their
    declared size, EXIF and scans are read from the raw bytes (8.197) before
    Pillow sees them: Pillow allocates the canvas of an animated PNG or WebP
    and parses a JPEG's EXIF inside ``Image.open``. Only JPEG, PNG and WebP
    decoders are tried, and the size in the header is checked once more
    against the limit of its format before ``load()`` decodes anything.
    Raises ``UnreadableImage`` (``ImageTooLarge`` for a big canvas; too much
    EXIF or too many scans are an ``UnreadableImage`` with a message that
    says so).
    """
    # imported here: the evidence package imports this module
    from apps.catalog.evidence.files import sniff
    if sniff(raw) != 'image':
        raise UnreadableImage('not a JPEG, PNG or WebP image')
    declared = read_raw_image_info(raw)
    limit, kind = _pixel_limit(declared.format)
    if declared.width * declared.height > limit:
        raise ImageTooLarge(_too_large(
            declared.width * declared.height, limit, kind))
    if declared.exif_bytes > MAX_UPLOAD_EXIF_BYTES:
        raise UnreadableImage(
            f'the image carries {-(-declared.exif_bytes // 1024)} KB of EXIF '
            f'metadata; the limit is {MAX_UPLOAD_EXIF_BYTES // 1024} KB')
    try:
        image = Image.open(io.BytesIO(raw), formats=UPLOAD_FORMATS)
    except Image.DecompressionBombError as exc:
        raise ImageTooLarge('image too large') from exc
    except Exception as exc:             # includes MemoryError
        raise UnreadableImage('not a readable image') from exc
    width, height = image.size
    limit, kind = _pixel_limit(image.format)
    if width * height > limit:
        image.close()
        raise ImageTooLarge(_too_large(width * height, limit, kind))
    try:
        image.load()
    except Image.DecompressionBombError as exc:
        raise ImageTooLarge('image too large') from exc
    except Exception as exc:
        raise UnreadableImage('not a readable image') from exc
    return image


def _kept_text(value: Any) -> Optional[str]:
    """The text without the NUL bytes and spaces it may be padded with, or
    None when it is not text or still longer than ``MAX_KEPT_TEXT``."""
    if not isinstance(value, str):
        return None
    value = value.rstrip('\x00 ')
    return value if len(value) <= MAX_KEPT_TEXT else None


def _kept_orientation(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and 1 <= value <= 8)


def sanitized_exif(image: Image.Image) -> Optional[Image.Exif]:
    """
    Return a new Exif holding only the kept tags, or None if none remain.

    The EXIF is limited before ``getexif`` parses it (8.197): EXIF over
    ``MAX_UPLOAD_EXIF_BYTES``, or with TIFF directories over the limits of
    the raw check, is not read, and the PNG text key
    ``Raw profile type exif``, whose hex text is inflated from a few bytes,
    is taken out of ``image.info``. A kept tag is dropped, not cut, when it is
    not small (see the top of this module).
    """
    try:
        # a PNG reads the text chunks behind the image data only when it is
        # loaded: load first, so that the key is popped for good
        image.load()
    except Exception:
        return None
    image.info.pop(_PNG_RAW_EXIF_KEY, None)
    present = image.info.get('exif')
    if present is not None:
        if (not isinstance(present, (bytes, bytearray))
                or len(present) > MAX_UPLOAD_EXIF_BYTES):
            return None
        try:
            _check_exif_blob(bytes(present))
        except UnreadableImage:
            return None
    try:
        source = image.getexif()
    except Exception:
        return None
    kept = Image.Exif()
    for tag in _KEEP_IFD0_TAGS:
        if tag in source:
            value = source[tag]
            if tag == _ORIENTATION:
                if _kept_orientation(value):
                    kept[tag] = value
            elif _kept_text(value) is not None:
                kept[tag] = _kept_text(value)
    try:
        exif_ifd = source.get_ifd(_EXIF_IFD)
    except Exception:
        exif_ifd = {}
    kept_sub = {t: _kept_text(exif_ifd[t]) for t in _KEEP_EXIF_IFD_TAGS
                if t in exif_ifd and _kept_text(exif_ifd[t]) is not None}
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

    Drops every EXIF and XMP (APP1), IPTC (APP13) and comment (COM) segment
    and inserts *exif* (if any) as the only APP1 segment after SOI / APP0.
    The scan data is copied byte for byte, so repeated runs never lose
    quality.
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
        # APP1 = EXIF / XMP, APP13 = IPTC, COM = comment
        if marker not in (0xE1, 0xED, 0xFE):
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


def _encode_jpeg(
    image: Image.Image,
    exif_kwargs: Dict[str, Any],
    max_bytes: int,
    max_long_edge_px: int,
) -> Tuple[bytes, int, int]:
    """The image steps of :func:`compress_and_save_jpeg`: convert, resize,
    encode. Returns (payload, width, height)."""
    # convert first, then thumbnail the converted copy: never ``draft()`` a
    # JpegImageFile (GHSA-8g5g-8vmr-9782 is not reachable while this order
    # stands; the Pillow pin stays, 8.197)
    working = image.convert('RGB')
    # ``save`` takes the comment from ``info`` on its own (the only key of
    # ``info`` it reads); a comment is not in the whitelist of 7.13
    working.info.pop('comment', None)
    if max(working.size) > max_long_edge_px:
        working.thumbnail(
            (max_long_edge_px, max_long_edge_px),
            Image.Resampling.LANCZOS,
        )

    quality = 88
    scale = 1.0
    best_payload: bytes | None = None
    best_size = working.size

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
        best_size = candidate.size

        if len(payload) <= max_bytes:
            break

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
    return best_payload, best_size[0], best_size[1]


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
    (orientation, capture time, make / model) when present. A JPEG comment
    is not carried over.

    An exception of the image steps (convert, resize, encode: for example a
    PNG text key ``transparency`` that ``convert`` cannot use) is an
    ``UnreadableImage``, the fault of the file; one of the disk (the
    directory, the write) is left as it is, a fault of the server.

    Returns (file_size_bytes, width, height).
    """
    if max_bytes < 1:
        raise ValueError('max_bytes must be positive')
    if max_long_edge_px < 1:
        raise ValueError('max_long_edge_px must be positive')

    try:
        payload, width, height = _encode_jpeg(
            image, _jpeg_exif_save_kwargs(image), max_bytes, max_long_edge_px)
    except UnreadableImage:
        raise
    except Exception as exc:             # includes MemoryError
        raise UnreadableImage('the image could not be processed') from exc

    os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
    with open(dest_path, 'wb') as handle:
        handle.write(payload)
    return len(payload), width, height
