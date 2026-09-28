"""Photo metadata whitelist (design decision 7.13)."""

import io

from PIL import Image

from apps.catalog.api.snapshot_images import (
    compress_and_save_jpeg,
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
