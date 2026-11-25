"""
S5 and S6 (decision 8.144): blocking work stays off the event loop, mesh
downloads are rate limited and the OBJ conversion has a size cap; uploaded
images are sniffed, decoded by the three expected decoders only, and refused
above a pixel cap before anything is decoded.
"""

from __future__ import annotations

import asyncio
import io
import struct
import zlib

import pytest
from PIL import Image

from apps.catalog.api import snapshot_common
from apps.catalog.api import snapshot_media
from apps.catalog.api import snapshot_meshes
from apps.catalog.api import snapshot_proxies
from apps.catalog.api.snapshot_images import (
    MAX_UPLOAD_PIXELS,
    ImageTooLarge,
    UnreadableImage,
    open_upload_photo,
)
from apps.catalog.evidence import files as evidence_files
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import seed_05_catalog, sid

PLY = (b'ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\n'
       b'property float y\nproperty float z\nelement face 1\n'
       b'property list uchar int vertex_indices\nend_header\n'
       b'0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n')
DRAFT = 'b8f2d6a4-0c1e-4b6f-9a2d-3e5f7a9c1b2d'
GIF = b'GIF89a\x01\x00\x01\x00\x00\x00\x00;'


def _jpeg(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, (20, 120, 200)).save(buf, 'JPEG')
    return buf.getvalue()


def _png_header_only(width: int, height: int) -> bytes:
    """A PNG that declares a canvas and carries no pixel data: decoding it
    would fail late, and a loader that allocates first would pay the memory."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack(
            '>I', zlib.crc32(body) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IEND', b'')


# THE DECODER -----------------------------------------------------------------
def test_a_real_image_opens():
    image = open_upload_photo(_jpeg())
    assert image.size == (64, 48)


@pytest.mark.parametrize('name,raw', [
    ('gif', GIF),
    ('bmp', b'BM' + b'\x00' * 60),
    ('tiff', b'II*\x00' + b'\x00' * 60),
    ('pdf', b'%PDF-1.7\n'),
    ('text', b'not an image'),
    ('empty', b''),
])
def test_only_jpeg_png_and_webp_are_decoded(name, raw):
    with pytest.raises(UnreadableImage):
        open_upload_photo(raw)


def test_a_large_canvas_is_refused_before_it_is_decoded():
    side = int(MAX_UPLOAD_PIXELS ** 0.5) + 1
    with pytest.raises(ImageTooLarge):
        open_upload_photo(_png_header_only(side, side))
    # under the cap the size check passes (the missing pixel data then makes
    # the decoder fail, which is a plain unreadable image)
    with pytest.raises(UnreadableImage) as info:
        open_upload_photo(_png_header_only(1000, 1000))
    assert not isinstance(info.value, ImageTooLarge)


# THE ROUTES ------------------------------------------------------------------
@pytest.fixture
def world(api, db, auth_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    beam_v1 = db['component_snapshots'].find_one({'_id': sid('beam', 1)})
    db['component_snapshots'].insert_one({
        **beam_v1, '_id': DRAFT, 'version': 2, 'status': 'draft',
        'supersedes': None, 'superseded_by': None})
    return {'api': api, 'admin': auth_headers('admin')}


def test_the_photo_route_refuses_what_is_not_a_jpeg_png_or_webp(world):
    api, admin = world['api'], world['admin']
    url = f'/snapshots/{DRAFT}/photos/0'
    gif = api.put(url, headers=admin, files={
        'photo': ('p.jpg', GIF, 'image/jpeg')})
    assert gif.status_code == 400
    side = int(MAX_UPLOAD_PIXELS ** 0.5) + 1
    big = api.put(url, headers=admin, files={
        'photo': ('p.png', _png_header_only(side, side), 'image/png')})
    assert big.status_code == 413
    assert 'megapixels' in big.json()['detail']
    ok = api.put(url, headers=admin, files={
        'photo': ('p.jpg', _jpeg(), 'image/jpeg')})
    assert ok.status_code == 200, ok.text


def _off_the_loop(record):
    """Wrap a function: note whether it ran inside a running event loop."""
    def wrap(function):
        def run_it(*args, **kwargs):
            try:
                asyncio.get_running_loop()
                record.append('loop')
            except RuntimeError:
                record.append('thread')
            return function(*args, **kwargs)
        return run_it
    return wrap


def test_photo_decoding_and_encoding_run_off_the_event_loop(world, monkeypatch):
    seen = []
    wrap = _off_the_loop(seen)
    monkeypatch.setattr(snapshot_media, 'open_upload_photo',
                        wrap(snapshot_media.open_upload_photo))
    monkeypatch.setattr(snapshot_media, 'compress_and_save_jpeg',
                        wrap(snapshot_media.compress_and_save_jpeg))
    response = world['api'].put(
        f'/snapshots/{DRAFT}/photos/0', headers=world['admin'],
        files={'photo': ('p.jpg', _jpeg(), 'image/jpeg')})
    assert response.status_code == 200, response.text
    assert seen == ['thread', 'thread']


def _upload_mesh(world):
    response = world['api'].put(
        f'/snapshots/{DRAFT}/meshes/0/reduced', headers=world['admin'],
        files={'mesh_file': ('m.ply', PLY)})
    assert response.status_code == 200, response.text


def test_the_obj_conversion_runs_off_the_event_loop(world, monkeypatch):
    _upload_mesh(world)
    seen = []
    monkeypatch.setattr(
        snapshot_meshes, 'export_mesh_file',
        _off_the_loop(seen)(snapshot_meshes.export_mesh_file))
    response = world['api'].get(
        f'/snapshots/{DRAFT}/meshes/0/reduced?format=obj',
        headers=world['admin'])
    assert response.status_code == 200, response.text
    assert b'\nv ' in response.content
    assert seen == ['thread']


def test_the_proxy_export_runs_off_the_event_loop(world, monkeypatch):
    seen = []
    monkeypatch.setattr(
        snapshot_proxies, '_proxy_mesh_bytes',
        _off_the_loop(seen)(snapshot_proxies._proxy_mesh_bytes))
    response = world['api'].get(
        f'/snapshots/{sid("panel")}/proxies/0/mesh?format=obj',
        headers=world['admin'])
    assert response.status_code == 200, response.text
    assert seen == ['thread']


def test_a_mesh_above_the_cap_is_not_converted_to_obj(world, monkeypatch):
    _upload_mesh(world)
    url = f'/snapshots/{DRAFT}/meshes/0/reduced'
    monkeypatch.setattr(snapshot_meshes, 'OBJ_CONVERSION_MAX_BYTES',
                        len(PLY) - 1)
    refused = world['api'].get(f'{url}?format=obj', headers=world['admin'])
    assert refused.status_code == 413
    assert 'PLY' in refused.json()['detail']
    # the PLY itself is still served
    assert world['api'].get(url, headers=world['admin']).status_code == 200


def test_the_mesh_routes_are_rate_limited(world):
    from limiter import local_limiter
    _upload_mesh(world)
    url = f'/snapshots/{DRAFT}/meshes/0/reduced'
    local_limiter.reset()
    local_limiter.enabled = True              # the fixtures switch it off
    try:
        codes = [world['api'].get(url, headers=world['admin']).status_code
                 for _ in range(snapshot_common.MESH_LIMIT_PER_MINUTE + 1)]
        assert set(codes[:-1]) == {200} and codes[-1] == 429
    finally:
        local_limiter.enabled = False
        local_limiter.reset()


# RAW BYTES BEFORE PILLOW (8.197) ---------------------------------------------
def _apng_declaring(width: int, height: int) -> bytes:
    """An animated PNG of two 1 x 1 frames (the first disposed to the
    background) on a canvas of the given size: under 200 bytes."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack(
            '>I', zlib.crc32(body) & 0xFFFFFFFF)

    def fctl(seq: int) -> bytes:
        return chunk(b'fcTL', struct.pack(
            '>IIIIIHHBB', seq, 1, 1, 0, 0, 1, 10, 1, 0))
    pixel = zlib.compress(b'\x00\x00\x00\x00\x00')
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height,
                                         8, 6, 0, 0, 0))
            + chunk(b'acTL', struct.pack('>II', 2, 0))
            + fctl(0) + chunk(b'IDAT', pixel) + fctl(1)
            + chunk(b'fdAT', struct.pack('>I', 2) + pixel)
            + chunk(b'IEND', b''))


def _jpeg_with_exif_segments() -> bytes:
    """10 APP1 segments of repeated ``Exif`` plus two zero bytes: 630 KB."""
    payload = b'Exif\x00\x00' * 10_500
    segment = b'\xff\xe1' + (len(payload) + 2).to_bytes(2, 'big') + payload
    base = _jpeg()
    return base[:2] + segment * 10 + base[2:]


@pytest.fixture
def pillow_is_not_called(monkeypatch):
    calls = []

    def refuse(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Image.open was called')
    monkeypatch.setattr(Image, 'open', refuse)
    return calls


def test_the_photo_route_refuses_a_declared_canvas_and_much_exif_unopened(
        world, pillow_is_not_called):
    api, admin = world['api'], world['admin']
    url = f'/snapshots/{DRAFT}/photos/0'
    big = api.put(url, headers=admin, files={
        'photo': ('p.png', _apng_declaring(9000, 9000), 'image/png')})
    assert big.status_code == 413
    assert 'megapixels' in big.json()['detail']
    heavy = api.put(url, headers=admin, files={
        'photo': ('p.jpg', _jpeg_with_exif_segments(), 'image/jpeg')})
    assert heavy.status_code == 400
    assert pillow_is_not_called == []


def test_the_photo_route_stores_a_png_with_a_normal_exif_chunk(world):
    exif = Image.Exif()
    exif[0x010F] = 'Apple'
    buf = io.BytesIO()
    Image.new('RGB', (32, 24), (1, 2, 3)).save(buf, 'PNG', exif=exif)
    api, admin = world['api'], world['admin']
    url = f'/snapshots/{DRAFT}/photos/0'
    ok = api.put(url, headers=admin, files={
        'photo': ('p.png', buf.getvalue(), 'image/png')})
    assert ok.status_code == 200, ok.text
    stored = api.get(url, headers=admin)
    assert stored.status_code == 200
    kept = Image.open(io.BytesIO(stored.content)).getexif()
    assert kept.get(0x010F) == 'Apple'


def test_the_photo_route_stores_no_jpeg_comment(world):
    raw = _jpeg()
    comment = b'\xff\xfe' + (2 + 9).to_bytes(2, 'big') + b'my diary!'
    raw = raw[:2] + comment + raw[2:]
    api, admin = world['api'], world['admin']
    url = f'/snapshots/{DRAFT}/photos/0'
    assert api.put(url, headers=admin, files={
        'photo': ('p.jpg', raw, 'image/jpeg')}).status_code == 200
    stored = api.get(url, headers=admin)
    assert stored.status_code == 200
    assert b'my diary!' not in stored.content


def test_an_attachment_image_is_checked_the_same_way(
        tmp_path, pillow_is_not_called):
    with pytest.raises(evidence_files.UnsupportedFile) as big:
        evidence_files.process_upload(
            _apng_declaring(9000, 9000), str(tmp_path),
            max_image_bytes=1_000_000, max_long_edge_px=4096)
    assert 'megapixels' in str(big.value)
    with pytest.raises(evidence_files.UnsupportedFile):
        evidence_files.process_upload(
            _jpeg_with_exif_segments(), str(tmp_path),
            max_image_bytes=1_000_000, max_long_edge_px=4096)
    assert pillow_is_not_called == []


# T5 (8.197 f): the refusals reach the user, the preview has no comment -------
def _jpeg_with_scans(count: int) -> bytes:
    sos = b'\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34'
    base = _jpeg()
    return base[:-2] + sos * (count - 1) + b'\xff\xd9'


def _webp_declaring(width: int, height: int) -> bytes:
    frames = [Image.new('RGB', (16, 12), (255, 0, 0)),
              Image.new('RGB', (16, 12), (0, 255, 0))]
    buf = io.BytesIO()
    frames[0].save(buf, 'WEBP', save_all=True, append_images=frames[1:],
                   duration=100, lossless=True)
    raw = bytearray(buf.getvalue())
    assert raw[12:16] == b'VP8X'
    raw[24:27] = (width - 1).to_bytes(3, 'little')
    raw[27:30] = (height - 1).to_bytes(3, 'little')
    return bytes(raw)


def test_the_photo_route_says_why_an_image_is_refused(
        world, pillow_is_not_called):
    api, admin = world['api'], world['admin']
    url = f'/snapshots/{DRAFT}/photos/0'
    exif = api.put(url, headers=admin, files={
        'photo': ('p.jpg', _jpeg_with_exif_segments(), 'image/jpeg')})
    assert exif.status_code == 400
    assert 'EXIF metadata' in exif.json()['detail']
    assert 'image' in exif.json()['detail']
    scans = api.put(url, headers=admin, files={
        'photo': ('p.jpg', _jpeg_with_scans(65), 'image/jpeg')})
    assert scans.status_code == 400
    assert 'scans' in scans.json()['detail'] and '64' in scans.json()['detail']
    webp = api.put(url, headers=admin, files={
        'photo': ('p.webp', _webp_declaring(5000, 5000), 'image/webp')})
    assert webp.status_code == 413, webp.text
    assert 'WebP' in webp.json()['detail'] and '16' in webp.json()['detail']
    gif = api.put(url, headers=admin, files={
        'photo': ('p.jpg', GIF, 'image/jpeg')})
    assert gif.status_code == 400
    assert gif.json()['detail']                     # a text, whatever it says
    assert pillow_is_not_called == []


def test_the_attachment_path_says_why_an_image_is_refused(
        tmp_path, pillow_is_not_called):
    for raw, word in [(_jpeg_with_exif_segments(), 'EXIF metadata'),
                      (_jpeg_with_scans(65), 'scans')]:
        with pytest.raises(evidence_files.UnsupportedFile) as refused:
            evidence_files.process_upload(
                raw, str(tmp_path), max_image_bytes=1_000_000,
                max_long_edge_px=4096)
        assert word in str(refused.value)
    assert pillow_is_not_called == []


def test_the_pdf_preview_of_an_old_photo_carries_no_comment(tmp_path):
    from apps.catalog.api import exports
    comment = b'\xff\xfe' + (2 + 9).to_bytes(2, 'big') + b'my diary!'
    raw = _jpeg()
    path = tmp_path / '0.jpg'
    path.write_bytes(raw[:2] + comment + raw[2:])
    assert b'my diary!' in path.read_bytes()
    preview = exports._preview_bytes(str(path))
    assert preview and b'my diary!' not in preview


def _gray_png_with_text(key: bytes, value: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack(
            '>I', zlib.crc32(body) & 0xFFFFFFFF)
    buf = io.BytesIO()
    Image.new('L', (16, 12), 90).save(buf, 'PNG')
    base = buf.getvalue()
    at = base.index(b'IDAT') - 4
    return base[:at] + chunk(b'tEXt', key + b'\x00' + value) + base[at:]


def test_a_failing_image_step_is_a_400_on_the_photo_route(world):
    raw = _gray_png_with_text(b'transparency', b'zzz')
    response = world['api'].put(
        f'/snapshots/{DRAFT}/photos/0', headers=world['admin'],
        files={'photo': ('p.png', raw, 'image/png')})
    assert response.status_code == 400, response.text
    assert 'image' in response.json()['detail']


def test_a_failing_image_step_is_a_refusal_of_the_attachment_path(tmp_path):
    raw = _gray_png_with_text(b'transparency', b'zzz')
    with pytest.raises(evidence_files.UnsupportedFile):
        evidence_files.process_upload(
            raw, str(tmp_path), max_image_bytes=1_000_000,
            max_long_edge_px=4096)
    assert not list((tmp_path / '.incoming').glob('*'))     # no half file


def test_a_failing_image_step_leaves_a_line_in_the_log(world, caplog):
    import logging
    raw = _gray_png_with_text(b'transparency', b'zzz')
    with caplog.at_level(logging.WARNING):
        response = world['api'].put(
            f'/snapshots/{DRAFT}/photos/0', headers=world['admin'],
            files={'photo': ('p.png', raw, 'image/png')})
    assert response.status_code == 400
    assert 'image step' in caplog.text
