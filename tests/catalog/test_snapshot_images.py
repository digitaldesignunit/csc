"""Photo metadata whitelist (design decision 7.13) and the checks of the raw
bytes of an upload (8.197)."""

import io
import random
import struct
import time
import zlib

import pytest
from PIL import Image, ImageFile

from apps.catalog.api import snapshot_images
from apps.catalog.api.snapshot_images import (
    ImageTooLarge,
    UnreadableImage,
    compress_and_save_jpeg,
    open_upload_photo,
    sanitized_exif,
    strip_jpeg_metadata,
)

GPS_IFD = 0x8825
EXIF_IFD = 0x8769


def _phone_photo() -> bytes:
    """A JPEG carrying everything a phone writes, wanted or not."""
    exif = Image.Exif()
    exif[0x0112] = 6                      # Orientation
    exif[0x010F] = 'Apple'                # Make
    exif[0x0110] = 'iPhone 15'            # Model
    exif[0x013B] = 'Jane Doe'             # Artist
    exif[0x8298] = '(c) Jane Doe'         # Copyright
    exif.get_ifd(EXIF_IFD).update({
        0x9003: '2026:05:19 10:00:00',    # DateTimeOriginal
        0x9011: '+02:00',                 # OffsetTimeOriginal
        0xA430: 'Jane Doe',               # CameraOwnerName
        0xA431: 'SERIAL123',              # BodySerialNumber
    })
    exif.get_ifd(GPS_IFD).update({
        1: 'N', 2: (49.0, 51.0, 40.0), 3: 'E', 4: (8.0, 40.0, 1.0),
    })
    buf = io.BytesIO()
    Image.new('RGB', (64, 48), (200, 30, 30)).save(
        buf, 'JPEG', exif=exif, quality=90)
    return buf.getvalue()


def _assert_whitelisted(exif: Image.Exif):
    assert dict(exif.get_ifd(GPS_IFD)) == {}
    assert exif.get(0x0112) == 6
    assert exif.get(0x010F) == 'Apple'
    assert exif.get(0x0110) == 'iPhone 15'
    assert 0x013B not in exif and 0x8298 not in exif
    sub = exif.get_ifd(EXIF_IFD)
    assert sub.get(0x9003) == '2026:05:19 10:00:00'
    assert sub.get(0x9011) == '+02:00'
    assert 0xA430 not in sub and 0xA431 not in sub


def test_sanitized_exif_keeps_only_the_whitelist():
    _assert_whitelisted(sanitized_exif(Image.open(io.BytesIO(_phone_photo()))))


def test_sanitized_exif_is_none_without_metadata():
    buf = io.BytesIO()
    Image.new('RGB', (8, 8)).save(buf, 'JPEG')
    assert sanitized_exif(Image.open(buf)) is None


def test_upload_pipeline_writes_no_gps(tmp_path):
    dest = tmp_path / 'photo.jpg'
    compress_and_save_jpeg(
        Image.open(io.BytesIO(_phone_photo())), str(dest),
        max_bytes=1_000_000, max_long_edge_px=4096,
    )
    _assert_whitelisted(Image.open(dest).getexif())


def test_stored_photo_rewrite_is_lossless_and_idempotent():
    raw = _phone_photo()
    original = Image.open(io.BytesIO(raw))
    cleaned = strip_jpeg_metadata(raw, sanitized_exif(original))

    reopened = Image.open(io.BytesIO(cleaned))
    assert reopened.tobytes() == original.tobytes()   # pixels untouched
    _assert_whitelisted(reopened.getexif())

    again = strip_jpeg_metadata(cleaned, sanitized_exif(reopened))
    assert again == cleaned


# --- crafted bytes, built here and never stored (8.197) ----------------------
JUNK = b'Exif\x00\x00'          # what the measured files repeat
CAP = 256 * 1024                # MAX_UPLOAD_EXIF_BYTES
SIDE = 9000                     # declared canvas of the crafted files: 81 MP


def _segment(marker: int, payload: bytes) -> bytes:
    return b'\xff' + bytes([marker]) + (len(payload) + 2).to_bytes(
        2, 'big') + payload


def _jpeg(size=(64, 48), **save) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, (20, 120, 200)).save(buf, 'JPEG', **save)
    return buf.getvalue()


def _jpeg_with_segments(*segments: bytes) -> bytes:
    base = _jpeg()
    return base[:2] + b''.join(segments) + base[2:]


def _jpeg_with_exif_segments(count: int, payload_size: int) -> bytes:
    """A JPEG with *count* APP1 segments of repeated ``Exif\\0\\0``."""
    payload = (JUNK * (payload_size // 6 + 1))[:payload_size]
    return _jpeg_with_segments(*[_segment(0xE1, payload)] * count)


def _jpeg_declaring(width: int, height: int) -> bytes:
    base = _jpeg()
    at = base.index(b'\xff\xc0\x00\x11\x08') + 5      # SOF0: height, width
    return base[:at] + struct.pack('>HH', height, width) + base[at + 4:]


def _mpo() -> bytes:
    """A two-picture JPEG as a phone writes it (APP2 MPF)."""
    first = Image.new('RGB', (64, 48), (200, 30, 30))
    second = Image.new('RGB', (32, 24), (30, 200, 30))
    buf = io.BytesIO()
    first.save(buf, 'MPO', save_all=True, append_images=[second])
    return buf.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack(
        '>I', zlib.crc32(body) & 0xFFFFFFFF)


def _png(size=(16, 12), **save) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, (20, 120, 200)).save(buf, 'PNG', **save)
    return buf.getvalue()


def _png_with_chunks(*chunks: bytes) -> bytes:
    base = _png()
    at = base.index(b'IDAT') - 4
    return base[:at] + b''.join(chunks) + base[at:]


def _apng_declaring(width: int, height: int) -> bytes:
    """An animated PNG of two 1 x 1 frames on a canvas of the given size
    (frame 1 disposed to the background): a few hundred bytes."""
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    fctl = lambda seq, w, h: _png_chunk(                   # noqa: E731
        b'fcTL', struct.pack('>IIIIIHHBB', seq, w, h, 0, 0, 1, 10, 1, 0))
    pixel = zlib.compress(b'\x00\x00\x00\x00\x00')
    return (b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR', ihdr)
            + _png_chunk(b'acTL', struct.pack('>II', 2, 0))
            + fctl(0, 1, 1) + _png_chunk(b'IDAT', pixel)
            + fctl(1, 1, 1)
            + _png_chunk(b'fdAT', struct.pack('>I', 2) + pixel)
            + _png_chunk(b'IEND', b''))


def _webp(size=(16, 12), **save) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, (20, 120, 200)).save(buf, 'WEBP', **save)
    return buf.getvalue()


def _animated_webp(**save) -> bytes:
    frames = [Image.new('RGB', (16, 12), (255, 0, 0)),
              Image.new('RGB', (16, 12), (0, 255, 0))]
    buf = io.BytesIO()
    frames[0].save(buf, 'WEBP', save_all=True, append_images=frames[1:],
                   duration=100, lossless=True, **save)
    return buf.getvalue()


def _webp_declaring(width: int, height: int) -> bytes:
    """An animated WebP whose VP8X canvas is *width* x *height* (24 bit,
    minus one) around its small frames: about 140 bytes."""
    raw = bytearray(_animated_webp())
    assert raw[12:16] == b'VP8X'
    raw[24:27] = (width - 1).to_bytes(3, 'little')
    raw[27:30] = (height - 1).to_bytes(3, 'little')
    return bytes(raw)


def _tiny_samples() -> dict:
    return {
        'jpeg': _jpeg(),
        'jpeg_exif': _phone_photo(),
        'mpo': _mpo(),
        'png': _png(),
        'png_exif': _png(exif=_exif_bytes()),
        'apng': _apng_declaring(40, 30),
        'webp': _webp(),
        'webp_exif': _webp(exif=_exif_bytes()),
        'webp_animated': _animated_webp(),
    }


def _exif_bytes() -> bytes:
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = 'Apple'
    exif[0x0110] = 'iPhone 15'
    exif[0x013B] = 'Jane Doe'
    exif.get_ifd(EXIF_IFD).update({0x9003: '2026:05:19 10:00:00'})
    exif.get_ifd(GPS_IFD).update({1: 'N', 2: (49.0, 51.0, 40.0)})
    return exif.tobytes()


@pytest.fixture
def pillow_is_not_called(monkeypatch):
    """The list of calls of ``Image.open``; a call fails the test."""
    calls = []

    def refuse(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Image.open was called')
    monkeypatch.setattr(Image, 'open', refuse)
    return calls


# --- a declared canvas is refused before Pillow opens the file ---------------
def _png_declaring(width: int, height: int) -> bytes:
    base = bytearray(_png())
    base[16:24] = struct.pack('>II', width, height)
    base[29:33] = struct.pack('>I', zlib.crc32(bytes(base[12:29])) & 0xFFFFFFFF)
    return bytes(base)


CANVASES = {
    'apng': lambda: _apng_declaring(SIDE, SIDE),
    'webp_animated': lambda: _webp_declaring(SIDE, SIDE),
    'png': lambda: _png_declaring(SIDE, SIDE),
    'jpeg': lambda: _jpeg_declaring(SIDE, SIDE),
}


@pytest.mark.parametrize('name', sorted(CANVASES))
def test_a_declared_canvas_is_refused_before_pillow_opens_it(
        name, pillow_is_not_called):
    raw = CANVASES[name]()
    assert len(raw) < 20_000          # the cost is the declaration, not bytes
    with pytest.raises(ImageTooLarge):
        open_upload_photo(raw)
    assert pillow_is_not_called == []


def test_the_canvas_limit_is_in_pixels_not_per_side(pillow_is_not_called):
    # 7000 x 5000 = 35 MP is under the limit and goes on to Pillow (spied
    # here, so it ends as unreadable); 9000 x 5000 = 45 MP is over it
    with pytest.raises(UnreadableImage) as info:
        open_upload_photo(_jpeg_declaring(7000, 5000))
    assert not isinstance(info.value, ImageTooLarge)
    assert len(pillow_is_not_called) == 1
    with pytest.raises(ImageTooLarge):
        open_upload_photo(_jpeg_declaring(9000, 5000))
    assert len(pillow_is_not_called) == 1


# --- EXIF over the limit is refused before Pillow opens the file -------------
OVERSIZED_EXIF = {
    # the measured JPEG: 10 APP1 segments, 639 KB of repeated Exif
    'jpeg': lambda: _jpeg_with_exif_segments(10, 63_000),
    'png': lambda: _png(exif=JUNK * 100_000),                    # 586 KB
    'webp': lambda: _webp(exif=JUNK * 100_000),                  # 586 KB
    # the key Pillow reads as EXIF when there is no eXIf chunk
    'png_text_exif': lambda: _png_with_chunks(
        _png_chunk(b'tEXt', b'exif\x00' + JUNK * 50_000)),
}


@pytest.mark.parametrize('name', sorted(OVERSIZED_EXIF))
def test_exif_over_the_limit_is_refused_before_pillow_opens_it(
        name, pillow_is_not_called):
    raw = OVERSIZED_EXIF[name]()
    with pytest.raises(UnreadableImage, match='EXIF') as info:
        open_upload_photo(raw)
    assert not isinstance(info.value, ImageTooLarge)
    assert pillow_is_not_called == []


def test_the_exif_limit_is_exact():
    assert snapshot_images.MAX_UPLOAD_EXIF_BYTES == CAP
    ok = _png_with_chunks(_png_chunk(b'eXIf', b'\x00' * CAP))
    assert open_upload_photo(ok).size == (16, 12)
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_png_with_chunks(
            _png_chunk(b'eXIf', b'\x00' * (CAP + 1))))
    # the EXIF of a JPEG is the sum of its APP1 segments (Pillow joins them)
    raw = _jpeg_with_segments(*[_segment(0xE1, JUNK + b'\x00' * 1018)] * 256)
    assert snapshot_images.read_raw_image_info(raw).exif_bytes == CAP
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_segments(
            *[_segment(0xE1, JUNK + b'\x00' * 1018)] * 257))


def test_a_png_text_key_does_not_carry_exif_past_the_limit(monkeypatch):
    """1 KB of file, 480 KB of hex text once inflated: the file check cannot
    see it, so the key is taken out before ``getexif`` reads it."""
    hexed = (JUNK * 40_000).hex()                       # 480 KB of text
    text = f'\nexif\n{len(JUNK) * 40_000:8d}\n{hexed}\n'.encode('latin-1')
    raw = _png_with_chunks(_png_chunk(
        b'zTXt', b'Raw profile type exif\x00\x00' + zlib.compress(text)))
    assert len(raw) < 3_000

    loaded = []
    original = Image.Exif.load

    def spy(self, data):
        loaded.append(len(data))
        return original(self, data)
    monkeypatch.setattr(Image.Exif, 'load', spy)

    image = open_upload_photo(raw)
    assert 'Raw profile type exif' in image.info      # the decoder keeps it
    assert sanitized_exif(image) is None
    assert 'Raw profile type exif' not in image.info
    assert loaded == []                               # and nothing parsed it


def test_a_png_key_behind_the_image_data_is_dropped_on_an_unloaded_image(
        monkeypatch):
    """``getexif`` of a PNG loads it, which reads the text chunks behind
    IDAT: the key must be gone before that."""
    text = f'\nexif\n{len(JUNK) * 40_000:8d}\n{(JUNK * 40_000).hex()}\n'
    base = _png()
    end = base.index(b'IEND') - 4
    raw = base[:end] + _png_chunk(
        b'zTXt', b'Raw profile type exif\x00\x00'
        + zlib.compress(text.encode('latin-1'))) + base[end:]
    image = Image.open(io.BytesIO(raw))          # not loaded
    assert 'Raw profile type exif' not in image.info
    loaded = []
    original = Image.Exif.load

    def spy(self, data):
        loaded.append(len(data))
        return original(self, data)
    monkeypatch.setattr(Image.Exif, 'load', spy)
    assert sanitized_exif(image) is None
    assert 'Raw profile type exif' not in image.info
    assert loaded == []


def test_the_exif_message_rounds_the_size_up():
    raw = _png_with_chunks(_png_chunk(b'eXIf', b'\x00' * (CAP + 1)))
    with pytest.raises(UnreadableImage) as info:
        open_upload_photo(raw)
    assert '257 KB' in str(info.value) and 'limit is 256 KB' in str(info.value)


def test_exif_over_the_limit_in_info_is_not_parsed(monkeypatch):
    image = Image.open(io.BytesIO(_png()))
    image.info['exif'] = JUNK * 100_000
    loaded = []
    monkeypatch.setattr(Image.Exif, 'load',
                        lambda self, data: loaded.append(len(data)))
    assert sanitized_exif(image) is None
    assert loaded == []


# --- what is still accepted, with the whitelisted tags as before -------------
ACCEPTED = {
    'phone jpeg': _phone_photo,
    'progressive jpeg': lambda: _jpeg(progressive=True),
    'mpo': _mpo,
    'png': _png,
    'png with a normal eXIf': lambda: _png(exif=_exif_bytes()),
    'static webp': _webp,
    'static webp with exif': lambda: _webp(exif=_exif_bytes()),
    'animated webp': _animated_webp,
    'animated webp with exif': lambda: _animated_webp(exif=_exif_bytes()),
}


@pytest.mark.parametrize('name', sorted(ACCEPTED))
def test_normal_uploads_are_still_accepted(name, tmp_path):
    image = open_upload_photo(ACCEPTED[name]())
    dest = tmp_path / 'photo.jpg'
    compress_and_save_jpeg(image, str(dest), max_bytes=1_000_000,
                           max_long_edge_px=4096)
    stored = Image.open(dest)
    assert stored.format == 'JPEG'
    if 'exif' in name or name == 'phone jpeg':
        exif = stored.getexif()
        assert dict(exif.get_ifd(GPS_IFD)) == {}
        assert exif.get(0x0112) == 6
        assert exif.get(0x010F) == 'Apple'
        assert exif.get(0x0110) == 'iPhone 15'
        assert 0x013B not in exif
        assert exif.get_ifd(EXIF_IFD).get(0x9003) == '2026:05:19 10:00:00'


def test_the_raw_header_agrees_with_pillow_on_normal_files():
    for name, make in ACCEPTED.items():
        raw = make()
        info = snapshot_images.read_raw_image_info(raw)
        image = Image.open(io.BytesIO(raw))
        assert (info.width, info.height) == image.size, name


def test_the_raw_header_counts_exif_per_format():
    exif = _exif_bytes()
    jpeg = snapshot_images.read_raw_image_info(_phone_photo())
    assert 0 < jpeg.exif_bytes < 2_000
    assert snapshot_images.read_raw_image_info(_png()).exif_bytes == 0
    assert snapshot_images.read_raw_image_info(
        _png(exif=exif)).exif_bytes == len(exif) - len(JUNK)
    assert snapshot_images.read_raw_image_info(_webp()).exif_bytes == 0
    assert snapshot_images.read_raw_image_info(
        _webp(exif=exif)).exif_bytes >= len(exif) - len(JUNK)
    assert snapshot_images.read_raw_image_info(
        _png_with_chunks(_png_chunk(b'eXIf', b'a' * 10),
                         _png_chunk(b'eXIf', b'b' * 5))).exif_bytes == 15


def test_the_frames_of_an_animation_lie_inside_the_canvas():
    """The canvas is enough: Pillow itself refuses a frame outside it, before
    it allocates (a PNG in its header pass, a WebP in the decoder)."""
    ihdr = struct.pack('>IIBBBBB', 10, 10, 8, 6, 0, 0, 0)
    pixel = zlib.compress(b'\x00\x00\x00\x00\x00')
    apng = (b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR', ihdr)
            + _png_chunk(b'acTL', struct.pack('>II', 1, 0))
            + _png_chunk(b'fcTL', struct.pack(
                '>IIIIIHHBB', 0, 5000, 5000, 0, 0, 1, 10, 0, 0))
            + _png_chunk(b'IDAT', pixel) + _png_chunk(b'IEND', b''))
    with pytest.raises(Exception):
        Image.open(io.BytesIO(apng), formats=['PNG'])
    with pytest.raises(Exception):
        Image.open(io.BytesIO(_webp_declaring(3, 3)), formats=['WEBP'])
    assert snapshot_images.read_raw_image_info(apng).width == 10


# --- decoder failures end as our own errors ----------------------------------
def test_a_decompression_bomb_or_a_memory_error_is_not_a_server_error(
        monkeypatch):
    def bomb(*args, **kwargs):
        raise Image.DecompressionBombError('too many pixels')

    def memory(*args, **kwargs):
        raise MemoryError()
    monkeypatch.setattr(Image, 'open', bomb)
    with pytest.raises(ImageTooLarge):
        open_upload_photo(_jpeg())
    monkeypatch.setattr(Image, 'open', memory)
    with pytest.raises(UnreadableImage):
        open_upload_photo(_jpeg())


def test_a_memory_error_while_decoding_is_not_a_server_error(monkeypatch):
    raw = _jpeg()                    # saving a file calls load() as well

    def memory(self):
        raise MemoryError()
    monkeypatch.setattr(ImageFile.ImageFile, 'load', memory)
    with pytest.raises(UnreadableImage):
        open_upload_photo(raw)


# --- truncated and damaged bytes ---------------------------------------------
def test_truncated_files_raise_nothing_but_unreadable_image():
    for name, raw in _tiny_samples().items():
        for cut in range(len(raw)):
            _only_unreadable(raw[:cut], f'{name} cut at {cut}')


def test_damaged_and_random_files_raise_nothing_but_unreadable_image():
    rng = random.Random(20261125)
    for name, raw in _tiny_samples().items():
        for _ in range(150):
            damaged = bytearray(raw)
            for _ in range(rng.randint(1, 4)):
                damaged[rng.randrange(len(damaged))] = rng.randrange(256)
            _only_unreadable(bytes(damaged), f'{name} damaged')
        for _ in range(50):
            junk = raw[:rng.randint(4, 16)] + bytes(
                rng.randrange(256) for _ in range(rng.randint(0, 200)))
            _only_unreadable(junk, f'{name} head and noise')


def _only_unreadable(raw: bytes, label: str) -> None:
    try:
        snapshot_images.read_raw_image_info(raw)
    except UnreadableImage:
        pass
    except Exception as exc:                       # pragma: no cover
        raise AssertionError(
            f'{label}: raw header raised {type(exc).__name__}') from exc
    try:
        open_upload_photo(raw)
    except UnreadableImage:
        pass
    except Exception as exc:                       # pragma: no cover
        raise AssertionError(
            f'{label}: open_upload_photo raised {type(exc).__name__}') from exc


# --- the walk of the bytes is bounded ----------------------------------------
FLOODS = {
    'png': lambda: _png_with_chunks(*[_png_chunk(b'tEXt', b'')] * 60_000),
    'jpeg': lambda: _jpeg_with_segments(*[_segment(0xFE, b'')] * 11_000),
    'webp': lambda: _webp()[:12] + b'JUNK\x00\x00\x00\x00' * 60_000
    + _webp()[12:],
}


@pytest.mark.parametrize('name', sorted(FLOODS))
def test_a_flood_of_empty_chunks_is_refused_unopened(
        name, pillow_is_not_called):
    with pytest.raises(UnreadableImage):
        open_upload_photo(FLOODS[name]())
    assert pillow_is_not_called == []


def test_filler_between_jpeg_segments_is_walked_as_pillow_walks_it():
    # fill bytes, escaped 0xFF and stray bytes between the segments: Pillow
    # opens the file, so the check must read the same size from it
    filler = b'\xff' * 1_000_000 + b'\xff\x00' * 500_000 + b'\x00junk\x00'
    raw = _jpeg_with_segments(filler, _segment(0xE0, b'JFIF\x00' * 3), filler)
    assert Image.open(io.BytesIO(raw)).size == (64, 48)
    started = time.perf_counter()
    info = snapshot_images.read_raw_image_info(raw)
    assert (info.width, info.height) == (64, 48)
    assert time.perf_counter() - started < 3          # linear, not per byte


def test_the_walk_without_its_safety_net_raises_only_unreadable_image():
    rng = random.Random(8197)
    for name, raw in _tiny_samples().items():
        for _ in range(300):
            damaged = bytearray(raw)
            for _ in range(rng.randint(1, 6)):
                damaged[rng.randrange(len(damaged))] = rng.randrange(256)
            try:
                snapshot_images._scan_raw(bytes(damaged))
            except UnreadableImage:
                pass


def test_a_second_ihdr_replaces_the_first_in_pillow_and_counts_here(
        pillow_is_not_called):
    """Pillow lets a later IHDR override the first one: a small canvas, then
    a declaration of 9000 x 9000 with animation chunks (under 400 bytes)."""
    base = _apng_declaring(8, 8)
    again = _png_chunk(b'IHDR', struct.pack(
        '>IIBBBBB', SIDE, SIDE, 8, 6, 0, 0, 0))
    at = base.index(b'acTL') - 4
    raw = base[:at] + again + base[at:]
    assert len(raw) < 400
    with pytest.raises(ImageTooLarge):
        open_upload_photo(raw)
    # and one behind the image data is read as well
    end = base.index(b'IEND') - 4
    with pytest.raises(ImageTooLarge):
        open_upload_photo(base[:end] + again + base[end:])
    assert pillow_is_not_called == []


def test_the_walk_skips_eoi_and_reserved_markers_like_pillow(
        pillow_is_not_called):
    # EOI (D9), a JPG0 (F0) and a stray 0xFF 0x00 in front of the EXIF must
    # not end the walk: the EXIF behind them is still counted
    exif = _segment(0xE1, JUNK * 10_000)
    raw = _jpeg_with_segments(
        b'\xff\xd9', b'\xff\xf0', b'\xff\x00', *[exif] * 5)
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(raw)
    assert pillow_is_not_called == []
    assert snapshot_images.read_raw_image_info(raw).exif_bytes == 5 * 60_000


def test_a_png_text_comment_does_not_reach_the_stored_jpeg(tmp_path):
    raw = _png_with_chunks(_png_chunk(b'tEXt', b'comment\x00written at home'))
    image = open_upload_photo(raw)
    assert image.info.get('comment') == 'written at home'
    dest = tmp_path / 'photo.jpg'
    compress_and_save_jpeg(image, str(dest), max_bytes=1_000_000,
                           max_long_edge_px=4096)
    assert b'written at home' not in dest.read_bytes()


# --- the JPEG comment is dropped (7.13, 8.197 b) ------------------------------
def _comment_segment(text: bytes = b'shot by someone, at home') -> bytes:
    return _segment(0xFE, text)


def _has_marker(jpeg: bytes, marker: int) -> bool:
    """Walk the segments up to SOS."""
    i = 2
    while i < len(jpeg) - 1 and jpeg[i] == 0xFF:
        kind = jpeg[i + 1]
        if kind == marker:
            return True
        if kind == 0xDA:
            return False
        i += 2 + int.from_bytes(jpeg[i + 2:i + 4], 'big')
    return False


def test_the_stored_photo_carries_no_comment(tmp_path):
    raw = _jpeg_with_segments(_comment_segment())
    image = open_upload_photo(raw)
    assert image.info['comment'] == b'shot by someone, at home'
    for scale_down in (False, True):          # the resize path too
        dest = tmp_path / f'photo{scale_down}.jpg'
        compress_and_save_jpeg(image, str(dest), max_bytes=1_000_000,
                               max_long_edge_px=32 if scale_down else 4096)
        stored = dest.read_bytes()
        assert not _has_marker(stored, 0xFE)
        assert b'shot by someone' not in stored
        assert 'comment' not in Image.open(dest).info


def test_the_upload_of_an_attachment_stores_no_comment(tmp_path):
    from apps.catalog.evidence.files import process_upload
    copy = process_upload(_jpeg_with_segments(_comment_segment()),
                          str(tmp_path), max_image_bytes=1_000_000,
                          max_long_edge_px=4096)
    assert b'shot by someone' not in open(copy.path, 'rb').read()


def test_the_rewrite_of_a_stored_photo_drops_the_comment():
    raw = _jpeg_with_segments(_comment_segment(), _comment_segment(b'two'))
    assert _has_marker(raw, 0xFE)
    cleaned = strip_jpeg_metadata(raw, None)
    assert not _has_marker(cleaned, 0xFE)
    assert Image.open(io.BytesIO(cleaned)).tobytes() == Image.open(
        io.BytesIO(raw)).tobytes()
    assert strip_jpeg_metadata(cleaned, None) == cleaned      # idempotent
    # a photo without a comment is left as it is
    plain = _jpeg()
    assert strip_jpeg_metadata(plain, None) == plain


# --- T5 (8.197 f): TIFF directories, WebP pixels, JPEG scans, kept text -------
TIFF_UNIT = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
             11: 4, 12: 8, 13: 4, 16: 8}
EXIF_POINTER = 0x8769


def _tiff(entries0, entries_exif=None, *, order='<', next_ifd=0,
          shared=None) -> bytes:
    """A TIFF stream as EXIF carries it (with the ``Exif`` marker).

    *entries0* / *entries_exif*: lists of ``(tag, type, count, value)``; the
    value is bytes (put in the data area when over 4 bytes), or ``('at',
    offset)`` to point at a place of the data area, or an int that is stored
    as it is (a pointer). ``shared`` is the one block of the data area that
    ``('at', 0)`` entries all point at.
    """
    pack = lambda fmt, *a: struct.pack(order + fmt, *a)       # noqa: E731
    count0 = len(entries0) + (1 if entries_exif is not None else 0)
    ifd0_size = 2 + 12 * count0 + 4
    exif_size = 0 if entries_exif is None else 2 + 12 * len(entries_exif) + 4
    data_at = 8 + ifd0_size + exif_size
    data = bytearray(shared or b'')

    def directory(entries, extra, link):
        out = pack('H', len(entries) + len(extra))
        rows = []
        for tag, typ, count, value in list(entries) + list(extra):
            if isinstance(value, tuple):                    # ('at', offset)
                field = pack('L', data_at + value[1])
            elif isinstance(value, int):
                field = pack('L', value)
            elif len(value) > 4:
                field = pack('L', data_at + len(data))
                data.extend(value)
            else:
                field = value.ljust(4, b'\x00')
            rows.append((tag, typ, count, field))
        for tag, typ, count, field in sorted(rows, key=lambda r: r[0]):
            out += pack('HHL', tag, typ, count) + field
        return out + pack('L', link)

    extra0 = []
    if entries_exif is not None:
        extra0 = [(EXIF_POINTER, 4, 1, 8 + ifd0_size)]
    ifd0 = directory(entries0, extra0, next_ifd)
    exif_ifd = b'' if entries_exif is None else directory(entries_exif, [], 0)
    head = (b'II*\x00' if order == '<' else b'MM\x00*') + pack('L', 8)
    return b'Exif\x00\x00' + head + ifd0 + exif_ifd + bytes(data)


def _shared_value_exif(n, typ, count, *, where='exif') -> bytes:
    """*n* entries that all point at one value of ``count`` items."""
    shared = b'\x01' * (count * TIFF_UNIT[typ])
    rows = [(0x9100 + i, typ, count, ('at', 0)) for i in range(n)]
    if where == 'exif':
        return _tiff([], rows, shared=shared)
    return _tiff(rows, None, shared=shared)


def _jpeg_with_exif(blob: bytes) -> bytes:
    """The blob in APP1 segments of at most 60 000 bytes, which Pillow
    joins (the later ones start with their own marker, which it cuts)."""
    segments = [_segment(0xE1, blob[:60_000])]
    rest = blob[60_000:]
    while rest:
        segments.append(_segment(0xE1, b'Exif\x00\x00' + rest[:60_000]))
        rest = rest[60_000:]
    return _jpeg_with_segments(*segments)


def _png_with_exif(blob: bytes) -> bytes:
    return _png_with_chunks(_png_chunk(b'eXIf', blob))


def _webp_with_exif(blob: bytes) -> bytes:
    return _webp(exif=blob)


WRAP = {'jpeg': _jpeg_with_exif, 'png': _png_with_exif,
        'webp': _webp_with_exif}


def _phone_exif(maker_note=60_000) -> bytes:
    """What a phone writes: IFD0 with make, model, orientation, a pointer
    to the Exif directory with the capture time and a big maker note, and a
    thumbnail directory (IFD1) behind it."""
    ifd0 = [(0x010F, 2, 6, b'Apple\x00'), (0x0110, 2, 10, b'iPhone 15\x00'),
            (0x0112, 3, 1, b'\x06\x00'), (0x0131, 2, 4, b'1.0\x00')]
    exif = [(0x9003, 2, 20, b'2026:05:19 10:00:00\x00'),
            (0x9011, 2, 7, b'+02:00\x00'),
            (0x927C, 7, maker_note, b'\x07' * maker_note),
            (0xA002, 4, 1, struct.pack('<L', 4032))]
    return _tiff(ifd0, exif, next_ifd=0)


def _mpf_jpeg(entries: int, value_bytes: int) -> bytes:
    """A JPEG with an APP2 MPF segment of *entries* entries that all point
    at one block of *value_bytes* bytes."""
    shared = b'\x00' * value_bytes
    rows = [(0xB100 + i, 7, value_bytes, ('at', 0)) for i in range(entries)]
    tiff = _tiff(rows, None, shared=shared)[6:]        # no Exif marker
    return _jpeg_with_segments(_segment(0xE2, b'MPF\x00' + tiff))


@pytest.fixture
def directories_read(monkeypatch):
    """The directories Pillow decodes: (entries, bytes of values) per load."""
    from PIL import TiffImagePlugin
    seen = []
    original = TiffImagePlugin.ImageFileDirectory_v2.load

    def spy(self, fp):
        original(self, fp)
        seen.append((len(self._tagdata),
                     sum(len(v) for v in self._tagdata.values())))
    monkeypatch.setattr(TiffImagePlugin.ImageFileDirectory_v2, 'load', spy)
    return seen


# --- 1. TIFF directories ------------------------------------------------------
@pytest.mark.parametrize('where', ['exif', 'ifd0'])
@pytest.mark.parametrize('wrap', sorted(WRAP))
def test_entries_that_share_one_value_are_refused_unopened(
        wrap, where, pillow_is_not_called):
    # 500 entries, each RATIONAL x 1000 (8 KB) or BYTE x 1000, all on the same
    # bytes: the file is about 14 KB and Pillow's reader copies 4 MB of
    # values (a second per KB of file, growing with the square)
    typ, count = (5, 1000) if where == 'exif' else (1, 1000)
    raw = WRAP[wrap](_shared_value_exif(500, typ, count, where=where))
    assert len(raw) < 20_000
    with pytest.raises(UnreadableImage, match='EXIF') as info:
        open_upload_photo(raw)
    assert not isinstance(info.value, ImageTooLarge)
    assert pillow_is_not_called == []


def test_too_many_entries_in_one_directory_are_refused(pillow_is_not_called):
    rows = [(0x9100 + i, 3, 1, b'\x01\x00') for i in range(513)]
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_exif(_tiff([], rows)))
    rows = rows[:512]
    snapshot_images.read_raw_image_info(_jpeg_with_exif(_tiff([], rows)))
    assert pillow_is_not_called == []


def test_the_value_bytes_of_a_directory_are_limited_by_the_cap(
        pillow_is_not_called):
    # one block of 4 KB that every entry points at: 60 entries read 240 KB,
    # 70 entries 280 KB, from a file of 5 KB
    ok = _shared_value_exif(60, 7, 4096)
    assert len(ok) < 5_000
    snapshot_images.read_raw_image_info(_jpeg_with_exif(ok))
    raw = _png_with_exif(_shared_value_exif(70, 7, 4096))
    assert len(raw) < 10_000                 # 280 KB of values to read
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(raw)
    assert pillow_is_not_called == []


def test_the_mpf_directory_of_a_jpeg_is_limited(pillow_is_not_called):
    with pytest.raises(UnreadableImage, match='multi-picture') as info:
        open_upload_photo(_mpf_jpeg(500, 1000))               # 500 KB read
    assert not isinstance(info.value, ImageTooLarge)
    with pytest.raises(UnreadableImage, match='multi-picture'):
        open_upload_photo(_mpf_jpeg(10, 600))                 # 6 KB read
    assert pillow_is_not_called == []
    snapshot_images.read_raw_image_info(_mpf_jpeg(10, 300))   # 3 KB: passes


def test_the_pointer_to_the_exif_directory_must_be_one_long_or_short(
        pillow_is_not_called):
    for typ, count, value in [(5, 1, b'\x01' * 8), (4, 2, b'\x00' * 8),
                              (2, 4, b'abc\x00'), (1, 4, b'\x08\x00\x00\x00')]:
        blob = _tiff([(EXIF_POINTER, typ, count, value)])
        with pytest.raises(UnreadableImage, match='EXIF'):
            open_upload_photo(_jpeg_with_exif(blob))
    assert pillow_is_not_called == []
    # one SHORT is a pointer Pillow follows, so it is read and accepted
    blob = _tiff([(EXIF_POINTER, 3, 1, b'\x20\x00')])
    snapshot_images.read_raw_image_info(_jpeg_with_exif(blob))


def test_a_pointer_of_type_ifd_is_read_like_a_long(pillow_is_not_called):
    rows = [(0x9100 + i, 7, 1000, ('at', 0)) for i in range(500)]
    blob = _tiff([], rows, shared=b'\x01' * 1000)    # 500 KB behind the pointer
    as_ifd = blob.replace(struct.pack('<HHL', EXIF_POINTER, 4, 1),
                          struct.pack('<HHL', EXIF_POINTER, 13, 1), 1)
    assert as_ifd != blob
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_exif(as_ifd))
    assert pillow_is_not_called == []
    small = _tiff([], [(0x9003, 2, 2, b'x\x00')]).replace(
        struct.pack('<HHL', EXIF_POINTER, 4, 1),
        struct.pack('<HHL', EXIF_POINTER, 13, 1), 1)
    snapshot_images.read_raw_image_info(_jpeg_with_exif(small))


def test_every_pointer_entry_is_followed_not_only_the_last(
        pillow_is_not_called):
    # two pointers: Pillow takes the last, the first leads to the big one
    rows = [(0x9100 + i, 7, 1000, ('at', 0)) for i in range(500)]
    blob = _tiff([(EXIF_POINTER, 4, 1, 0)], rows, shared=b'\x01' * 1000)
    # the first pointer is rewritten to name the directory of the second
    pointers = [m for m in range(len(blob))
                if blob[m:m + 4] == struct.pack('<HH', EXIF_POINTER, 4)]
    assert len(pointers) == 2
    first, second = pointers
    target = blob[second + 8:second + 12]
    blob = blob[:first + 8] + target + blob[first + 12:]
    blob = (blob[:second + 8] + struct.pack('<L', 0) + blob[second + 12:])
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_exif(blob))
    assert pillow_is_not_called == []


def test_the_value_bytes_of_all_the_directories_of_a_file_add_up(
        pillow_is_not_called):
    # IFD0 and the Exif directory each declare 160 KB (40 x 4 KB shared):
    # under the cap alone, over it together
    rows0 = [(0x9100 + i, 7, 4096, ('at', 0)) for i in range(40)]
    rows1 = [(0x9200 + i, 7, 4096, ('at', 0)) for i in range(40)]
    one = _tiff(rows0, None, shared=b'\x01' * 4096)
    both = _tiff(rows0, rows1, shared=b'\x01' * 4096)
    snapshot_images.read_raw_image_info(_jpeg_with_exif(one))
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_exif(both))
    # duplicate tags count each time, though Pillow keeps the last one
    dup = _tiff([(0x9100, 7, 4096, ('at', 0)) for _ in range(70)],
                shared=b'\x01' * 4096)
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_exif(dup))
    assert pillow_is_not_called == []


def test_the_entries_that_lie_in_the_data_are_counted_not_the_declared():
    blob = bytearray(_tiff([(0x0112, 3, 1, b'\x01\x00'),
                            (0x010F, 2, 6, b'Apple\x00')]))
    at = 6 + 8                                  # the entry count of IFD0
    blob[at:at + 2] = struct.pack('<H', 60_000)
    for wrap in WRAP.values():
        open_upload_photo(wrap(bytes(blob)))


def test_a_phone_exif_with_a_big_maker_note_is_accepted(tmp_path):
    blob = _phone_exif(maker_note=60_000)
    assert len(blob) > 60_000
    for wrap in WRAP.values():
        image = open_upload_photo(wrap(blob))
        dest = tmp_path / 'photo.jpg'
        compress_and_save_jpeg(image, str(dest), max_bytes=1_000_000,
                               max_long_edge_px=4096)
        exif = Image.open(dest).getexif()
        assert exif.get(0x010F) == 'Apple' and exif.get(0x0110) == 'iPhone 15'
        assert exif.get(0x0112) == 6
        assert exif.get_ifd(EXIF_IFD).get(0x9003) == '2026:05:19 10:00:00'
        assert 0x0131 not in exif                      # software: dropped


def test_a_broken_but_harmless_exif_is_not_refused():
    # an entry that points behind the data: Pillow stops reading there
    far = _tiff([(0x010F, 2, 50, ('at', 100_000)), (0x0110, 2, 4, b'abc\x00')])
    # a directory count over what the data holds, a bad header, a BigTIFF
    short = _tiff([(0x0112, 3, 1, b'\x01\x00')])[:-10]
    bad_head = b'Exif\x00\x00XX*\x00' + b'\x00' * 20
    bigtiff = b'Exif\x00\x00II+\x00\x08\x00\x00\x00' + b'\x00' * 20
    for blob in (far, short, bad_head, bigtiff, b'Exif\x00\x00', b'', b'II'):
        for wrap in WRAP.values():
            open_upload_photo(wrap(blob) if blob else _png())


def test_the_exif_header_markers_are_stripped_as_pillow_strips_them():
    # many leading markers, then a directory that is over the limit
    bad = _shared_value_exif(500, 1, 1000)
    blob = b'Exif\x00\x00' * 5 + bad
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_png_with_exif(blob))
    # the PNG text key `exif` holds the same bytes
    raw = _png_with_chunks(_png_chunk(b'tEXt', b'exif\x00' + bad))
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(raw)


def test_every_exif_chunk_of_a_png_or_webp_is_checked():
    good, bad = _phone_exif(1000), _shared_value_exif(500, 1, 1000)
    raw = _png_with_chunks(_png_chunk(b'eXIf', bad), _png_chunk(b'eXIf', good))
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(raw)


def test_a_joined_jpeg_exif_is_checked_as_pillow_joins_it():
    # the second segment continues the first one (its marker is cut)
    blob = _shared_value_exif(500, 1, 1000)
    first, rest = blob[:3000], blob[3000:]
    raw = _jpeg_with_segments(_segment(0xE1, first),
                              _segment(0xE1, b'Exif\x00\x00' + rest))
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(raw)


def test_the_check_reads_exactly_the_directories_pillow_reads(
        directories_read):
    """IFD0 and the Exif directory (for a PNG or WebP through
    ``sanitized_exif``); the thumbnail directory (IFD1) that IFD0 links to
    is never read: 600 entries there are no reason to refuse the file."""
    rows0, rows1 = [(0x010F, 2, 6, b'Apple\x00')], [(0x9003, 2, 2, b'x\x00')]
    length = len(_tiff(rows0, rows1)) - 6
    base = _tiff(rows0, rows1, next_ifd=length)
    rows = b''.join(struct.pack('<HHL', 0x9100 + i, 3, 1) + b'\x01\x00\x00\x00'
                    for i in range(600))
    blob = base + struct.pack('<H', 600) + rows + struct.pack('<L', 0)
    image = open_upload_photo(_png_with_exif(blob))
    directories_read.clear()
    sanitized_exif(image)
    assert len(directories_read) == 2
    assert max(entries for entries, _ in directories_read) < 10


def test_exif_bytes_are_read_like_pillow_in_a_seeded_fuzz(directories_read):
    """The bounds the check computes are never below what Pillow decodes."""
    rng = random.Random(8197)
    types = list(range(0, 18))
    for round_ in range(1500):
        order = rng.choice('<>')
        rows0, rows1 = [], []
        size = rng.choice([40, 200, 2000])
        for rows in (rows0, rows1):
            for _ in range(rng.randint(0, 25)):
                typ = rng.choice(types)
                count = rng.choice([0, 1, 2, 4, 20, 300, rng.randint(0, 5000)])
                value = rng.choice([
                    ('at', rng.randint(0, size)), rng.randint(0, 2 ** 32 - 1)])
                rows.append((rng.randint(0, 65535), typ, count, value))
        if rng.random() < 0.7:
            for _ in range(rng.choice([1, 1, 1, 2])):
                rows0.append((EXIF_POINTER, rng.choice([3, 4, 4, 4, 13, 5]),
                              rng.choice([1, 1, 1, 2]), rng.randint(0, 600)))
        blob = _tiff(rows0, rows1 if rng.random() < 0.5 else None,
                     order=order,
                     shared=bytes(rng.randrange(256) for _ in range(size)))
        if rng.random() < 0.3:
            blob = blob[:rng.randint(0, len(blob))]
        if rng.random() < 0.1:
            blob = b'Exif\x00\x00' * rng.randint(1, 3) + blob
        directories_read.clear()
        try:
            exif = Image.Exif()
            exif.load(blob)
            exif.get_ifd(EXIF_IFD)
        except Exception:
            pass
        # the same two steps that ``sanitized_exif`` takes: what did they read?
        pillow = list(directories_read)
        try:
            counted = snapshot_images._exif_directory_stats(blob)
        except UnreadableImage:
            continue                       # refused: the file is not read
        assert len(counted) >= len(pillow), (round_, counted, pillow)
        if pillow:                                   # IFD0
            assert (counted[0][0] >= pillow[0][0]
                    and counted[0][1] >= pillow[0][1]), (round_, counted, pillow)
        if len(pillow) > 1:                          # the directory it led to
            assert any(ours[0] >= pillow[1][0] and ours[1] >= pillow[1][1]
                       for ours in counted[1:]), (round_, counted, pillow)


# --- 2. WebP pixels -----------------------------------------------------------
def test_a_webp_above_sixteen_megapixels_is_refused_unopened(
        pillow_is_not_called):
    assert snapshot_images.MAX_UPLOAD_WEBP_PIXELS == 16_000_000
    with pytest.raises(ImageTooLarge) as info:
        open_upload_photo(_webp_declaring(4001, 4000))        # 16.004 MP
    assert 'WebP' in str(info.value) and 'is 16' in str(info.value)
    with pytest.raises(ImageTooLarge):
        open_upload_photo(_webp_declaring(6300, 6300))       # the 39.7 MP row
    assert pillow_is_not_called == []
    # up to 16 MP the file goes on to Pillow (spied here), a phone photo
    # of 12.5 MP among them
    for size in ((4000, 4000), (4080, 3072)):
        with pytest.raises(UnreadableImage) as ok:
            open_upload_photo(_webp_declaring(*size))
        assert not isinstance(ok.value, ImageTooLarge)
    assert len(pillow_is_not_called) == 2


def test_the_webp_limit_does_not_touch_other_formats(pillow_is_not_called):
    # 20 MP PNG and JPEG are under their own limit of 40 MP
    for raw in (_png_declaring(5000, 4000), _jpeg_declaring(5000, 4000)):
        with pytest.raises(UnreadableImage) as info:
            open_upload_photo(raw)
        assert not isinstance(info.value, ImageTooLarge)
    assert len(pillow_is_not_called) == 2


def test_a_plain_webp_within_the_limit_is_still_accepted():
    assert open_upload_photo(_webp((3000, 2000))).size == (3000, 2000)
    assert open_upload_photo(_animated_webp()).n_frames == 2


# --- 3. JPEG scans ------------------------------------------------------------
SOS = b'\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00'      # one component


def _jpeg_with_scans(count: int, entropy: bytes = b'\x12\x34') -> bytes:
    """A baseline JPEG followed by more scans (headers only, as far as the
    walk is concerned): *count* in all, before the EOI."""
    base = _jpeg()
    assert base[-2:] == b'\xff\xd9'
    return base[:-2] + (SOS + entropy) * (count - 1) + b'\xff\xd9'


def test_more_than_64_scans_are_refused_unopened(pillow_is_not_called):
    raw = _jpeg_with_scans(65)
    assert len(raw) < 2_000
    with pytest.raises(UnreadableImage, match='scans') as info:
        open_upload_photo(raw)
    assert not isinstance(info.value, ImageTooLarge)
    assert pillow_is_not_called == []
    snapshot_images.read_raw_image_info(_jpeg_with_scans(64))


def test_what_is_not_a_scan_is_not_counted():
    # escaped 0xFF, restart markers, fill bytes and a long entropy run
    entropy = (b'\xff\x00' * 30 + b'\xff\xd0' + b'\xff\xd7' + b'\xff\xff\x00'
               + b'\xff\xff\xff\xff\x00' + b'\x12' * 4000) * 20
    raw = _jpeg_with_scans(3, entropy)
    snapshot_images.read_raw_image_info(raw)
    # 64 scans between the same noise are still 64
    snapshot_images.read_raw_image_info(_jpeg_with_scans(64, entropy))
    with pytest.raises(UnreadableImage, match='scans'):
        snapshot_images.read_raw_image_info(_jpeg_with_scans(65, entropy))


def test_only_the_scans_of_the_first_picture_are_counted():
    # libjpeg stops at the first EOI: the second picture of an MPO and the
    # video of a motion photo behind it are not decoded
    second = _jpeg_with_scans(100)
    snapshot_images.read_raw_image_info(_jpeg_with_scans(10) + second)
    rng = random.Random(8197)
    video = bytes(rng.randrange(256) for _ in range(2_000_000))
    assert video.count(b'\xff\xda') > 10                    # random "scans"
    info = snapshot_images.read_raw_image_info(_jpeg_with_scans(3) + video)
    assert (info.width, info.height) == (64, 48)
    # the end of the first picture is the first EOI after the first SOS: an
    # EOI before it (Pillow walks on) does not end the header
    base = _jpeg()
    early = base[:2] + b'\xff\xd9' + base[2:-2] + SOS * 70 + b'\xff\xd9'
    with pytest.raises(UnreadableImage, match='scans'):
        snapshot_images.read_raw_image_info(early)


def test_phone_and_progressive_jpegs_and_an_mpo_pass_the_scan_limit():
    big = Image.effect_noise((256, 256), 80).convert('RGB')
    buf = io.BytesIO()
    big.save(buf, 'JPEG', progressive=True)
    info = snapshot_images.read_raw_image_info(buf.getvalue())
    assert (info.width, info.height) == (256, 256)
    first = Image.new('RGB', (64, 48), (200, 30, 30))
    both = io.BytesIO()
    first.save(both, 'MPO', save_all=True, progressive=True,
               append_images=[Image.new('RGB', (32, 24))])
    open_upload_photo(both.getvalue())
    open_upload_photo(_phone_photo())


# --- 4. kept EXIF text --------------------------------------------------------
def _exif_with(**tags) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = tags.get('make', 'Apple')
    exif[0x0110] = tags.get('model', 'iPhone 15')
    exif[0x0112] = tags.get('orientation', 6)
    sub = exif.get_ifd(EXIF_IFD)
    sub[0x9003] = tags.get('taken', '2026:05:19 10:00:00')
    sub[0x9011] = tags.get('offset', '+02:00')
    return exif


def _sanitized_of(exif: Image.Exif):
    image = Image.open(io.BytesIO(_jpeg(exif=exif)))
    return sanitized_exif(image)


def test_kept_text_is_at_most_64_characters_and_dropped_not_cut():
    kept = _sanitized_of(_exif_with(make='M' * 64, model='x' * 64,
                                    taken='t' * 64, offset='o' * 64))
    assert kept.get(0x010F) == 'M' * 64 and kept.get(0x0110) == 'x' * 64
    sub = kept.get_ifd(EXIF_IFD)
    assert sub.get(0x9003) == 't' * 64 and sub.get(0x9011) == 'o' * 64
    long = _sanitized_of(_exif_with(make='M' * 65, model='x' * 65,
                                    taken='t' * 65, offset='o' * 65))
    assert long is None or (0x010F not in long and 0x0110 not in long)
    if long is not None:
        sub = long.get_ifd(EXIF_IFD)
        assert 0x9003 not in sub and 0x9011 not in sub
        assert long.get(0x0112) == 6                 # the rest is kept


def test_the_length_of_kept_text_is_measured_without_nul_and_spaces():
    padded = _sanitized_of(_exif_with(make='Apple' + ' ' * 200,
                                      model='x' * 64 + ' \x00' * 30))
    assert padded.get(0x010F) == 'Apple'            # stored without padding
    assert padded.get(0x0110) == 'x' * 64
    over = _sanitized_of(_exif_with(model='x' * 65 + ' ' * 30))
    assert 0x0110 not in over


def test_the_orientation_is_kept_only_from_1_to_8():
    for value in range(1, 9):
        assert _sanitized_of(_exif_with(orientation=value)).get(0x0112) == value
    for value in (0, 9, 255, 60_000):
        kept = _sanitized_of(_exif_with(orientation=value))
        assert 0x0112 not in kept


def test_a_kept_tag_that_is_not_text_is_dropped():
    # make as a SHORT, model as a RATIONAL: not text, so not kept
    blob = _tiff([(0x010F, 3, 1, b'\x05\x00'),
                  (0x0110, 5, 1, struct.pack('<LL', 1, 2)),
                  (0x0112, 3, 1, b'\x01\x00')])
    kept = sanitized_exif(open_upload_photo(_jpeg_with_exif(blob)))
    assert 0x010F not in kept and 0x0110 not in kept
    assert kept.get(0x0112) == 1


def test_an_oversized_tag_does_not_end_in_a_server_error(tmp_path):
    # Make of 70 000 bytes: over the size of one JPEG segment, so saving it
    # raised "EXIF data is too long"
    blob = _tiff([(0x010F, 2, 70_000, b'A' * 70_000),
                  (0x0110, 2, 6, b'Pixel\x00'),
                  (0x0112, 3, 1, b'\x01\x00')])
    for wrap in WRAP.values():
        image = open_upload_photo(wrap(blob))
        dest = tmp_path / 'photo.jpg'
        compress_and_save_jpeg(image, str(dest), max_bytes=1_000_000,
                               max_long_edge_px=4096)
        stored = Image.open(dest).getexif()
        assert 0x010F not in stored and stored.get(0x0110) == 'Pixel'


# --- an error of an image step is the fault of the file (T5 item 5) -----------
def _gray_png_with_text(key: bytes, value: bytes) -> bytes:
    buf = io.BytesIO()
    Image.new('L', (16, 12), 90).save(buf, 'PNG')
    base = buf.getvalue()
    at = base.index(b'IDAT') - 4
    return base[:at] + _png_chunk(b'tEXt', key + b'\x00' + value) + base[at:]


def test_a_png_text_key_transparency_is_a_refusal_not_a_server_error(tmp_path):
    raw = _gray_png_with_text(b'transparency', b'zzz')
    image = open_upload_photo(raw)                  # opens: the key is a str
    dest = tmp_path / 'photo.jpg'
    with pytest.raises(UnreadableImage) as info:
        compress_and_save_jpeg(image, str(dest), max_bytes=1_000_000,
                               max_long_edge_px=4096)
    assert 'image' in str(info.value)
    assert not dest.exists()


def test_an_error_of_the_disk_is_not_turned_into_a_refusal(tmp_path):
    blocker = tmp_path / 'file'
    blocker.write_bytes(b'x')
    image = open_upload_photo(_png())
    with pytest.raises(OSError):                     # the directory is a file
        compress_and_save_jpeg(image, str(blocker / 'sub' / 'photo.jpg'),
                               max_bytes=1_000_000, max_long_edge_px=4096)
    assert not issubclass(OSError, UnreadableImage)


# --- round 3: the walk after the first SOS, the entry budget ------------------
def _progressive_units():
    """A Pillow progressive JPEG as (header, units): a unit is what comes
    before a scan (its tables), the SOS header and the entropy data."""
    # the same picture every time (``effect_noise`` is random, and some
    # random entropy data does not survive the junk that is put into it)
    rng = random.Random(8197)
    noise = Image.frombytes(
        'RGB', (128, 128), bytes(rng.randrange(256) for _ in range(128 * 128 * 3)))
    buf = io.BytesIO()
    noise.save(buf, 'JPEG', progressive=True, quality=85)
    jpeg = buf.getvalue()
    pos, marks = 2, []
    while pos < len(jpeg):
        marker = jpeg[pos + 1]
        if marker == 0xD9:
            break
        end = pos + 2 + int.from_bytes(jpeg[pos + 2:pos + 4], 'big')
        if marker == 0xDA:
            while True:          # the entropy data, up to the next marker
                nxt = jpeg.index(b'\xff', end)
                if jpeg[nxt + 1] == 0 or 0xD0 <= jpeg[nxt + 1] <= 0xD7:
                    end = nxt + 2
                    continue
                end = nxt
                break
        marks.append((marker, pos, end))
        pos = end
    sof = next(m for m in marks if m[0] == 0xC2)
    units, boundary = [], sof[2]
    for marker, start, end in marks:
        if marker == 0xDA:
            units.append((jpeg[boundary:end], start - boundary))
            boundary = end
    return jpeg[:sof[2]], units


def _with_restart_and_junk(order, header, junk: bytes) -> bytes:
    """Header + a restart interval of 1 + the units, with *junk* in the
    entropy data of the first scan (right behind its SOS header)."""
    parts = []
    for i, (data, sos_at) in enumerate(order):
        if i == 0:
            cut = sos_at + 2 + int.from_bytes(
                data[sos_at + 2:sos_at + 4], 'big')
            data = data[:cut] + junk + data[cut:]
        parts.append(data)
    return (header + b'\xff\xdd\x00\x04\x00\x01' + b''.join(parts)
            + b'\xff\xd9')


# a marker below 0xC0, alone and followed by fill bytes and another one; what
# comes behind the junk is the entropy data again. (A marker of 0xC0 and up
# in there, such as `FF E1`, is read by its length, by libjpeg too: the
# bytes after the junk then decide how far it jumps, so it is not used.)
JUNK_MARKERS = [b'\xff\x02', b'\xff\xbf', b'\xff\xbf\xff\xff\xff\x02']


def _bypass_files(junk: bytes):
    """66 scans, the DC scan last, junk in the first one; and the same
    without the last scan."""
    header, units = _progressive_units()
    dc, ac = units[0], units[1:]
    many = ac[:-1] * 8 + [ac[-1]]
    return (_with_restart_and_junk(many + [dc], header, junk),
            _with_restart_and_junk(many, header, junk))


@pytest.mark.parametrize('junk', JUNK_MARKERS)
def test_pillow_decodes_the_scans_behind_a_marker_below_c0(junk):
    """With a restart interval libjpeg skips such a marker in the entropy
    data and goes on: the pixels depend on the DC scan at the very end."""
    raw, without_last = _bypass_files(junk)

    def pixels(data):
        image = Image.open(io.BytesIO(data))
        image.load()
        return image.convert('RGB').tobytes()
    assert pixels(raw) != pixels(without_last)


@pytest.mark.parametrize('junk', JUNK_MARKERS)
def test_a_marker_below_c0_in_the_entropy_data_does_not_end_the_scan_walk(
        junk, pillow_is_not_called):
    raw, _ = _bypass_files(junk)
    with pytest.raises(UnreadableImage, match='scans'):
        open_upload_photo(raw)
    assert pillow_is_not_called == []


def _unknown_entries(count: int) -> bytes:
    """EXIF whose IFD0 has *count* entries of a type Pillow skips."""
    return _tiff([(0x9100 + i, 20, 1, b'\x00\x00\x00\x00')
                  for i in range(count)])


def test_entries_of_unknown_types_are_counted_per_file(pillow_is_not_called):
    one = _unknown_entries(512)                      # costs no value bytes
    snapshot_images.read_raw_image_info(_png_with_exif(one))
    chunks = [_png_chunk(b'eXIf', one)] * 12         # 222 KB, 6144 entries
    raw = _png_with_chunks(*chunks)
    started = time.perf_counter()
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(raw)
    assert time.perf_counter() - started < 1.0       # it was 2 to 3 s
    assert pillow_is_not_called == []
    # the same entries as Exif directories of one JPEG: IFD0 + two pointers
    rows = [(0x9100 + i, 20, 1, b'\x00\x00\x00\x00') for i in range(500)]
    assert snapshot_images.MAX_FILE_ENTRIES == 2048
    snapshot_images.read_raw_image_info(_jpeg_with_exif(_tiff(rows, rows)))


def test_more_than_two_pointers_to_the_exif_directory_are_refused(
        pillow_is_not_called):
    def pointers(count):
        return _tiff([(EXIF_POINTER, 4, 1, 8) for _ in range(count)])
    snapshot_images.read_raw_image_info(_jpeg_with_exif(pointers(2)))
    with pytest.raises(UnreadableImage, match='EXIF'):
        open_upload_photo(_jpeg_with_exif(pointers(3)))
    assert pillow_is_not_called == []


def test_the_multi_picture_segments_share_the_entry_budget(
        pillow_is_not_called):
    rows = [(0xB100 + i, 20, 1, b'\x00\x00\x00\x00') for i in range(512)]
    segment = _segment(0xE2, b'MPF\x00' + _tiff(rows)[6:])
    snapshot_images.read_raw_image_info(_jpeg_with_segments(segment))
    with pytest.raises(UnreadableImage, match='metadata'):
        open_upload_photo(_jpeg_with_segments(*[segment] * 5))
    assert pillow_is_not_called == []
