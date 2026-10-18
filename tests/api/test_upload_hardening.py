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
