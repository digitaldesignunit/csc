#!/usr/bin/env python3
"""
Strip location and personal metadata from stored snapshot photos.

Design decision 7.13 / data model spec §8.1 step 14. Every JPEG under the
snapshot photos directory is rewritten to keep only orientation, capture time
and camera make / model (the same whitelist as the upload pipeline,
``apps.catalog.api.snapshot_images``). The pixels are not re-encoded — only
the metadata segments change — so the script is safe to run repeatedly.

Files only; the database is not touched.

Usage:
    python migrate_strip_photo_gps.py [--photos-dir DIR] [--dry-run]

``--photos-dir`` defaults to $SNAPSHOT_PHOTOS_DIR. The backend code is taken
from $CSC_BACKEND_DIR (on the server: ~/csc/backend), else from this
repository's src/backend.
"""

import argparse
import io
import os
import sys

_BACKEND = os.getenv('CSC_BACKEND_DIR') or os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src', 'backend'))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from PIL import Image  # noqa: E402

from apps.catalog.api.snapshot_images import (  # noqa: E402
    sanitized_exif,
    strip_jpeg_metadata,
)

_GPS_IFD = 0x8825


def _has_gps(image: Image.Image) -> bool:
    try:
        return len(image.getexif().get_ifd(_GPS_IFD)) > 0
    except Exception:
        return False


def process(path: str, dry_run: bool) -> tuple:
    """Return (changed, had_gps) for one file."""
    with open(path, 'rb') as handle:
        raw = handle.read()
    image = Image.open(io.BytesIO(raw))
    had_gps = _has_gps(image)
    cleaned = strip_jpeg_metadata(raw, sanitized_exif(image))
    if cleaned == raw:
        return False, had_gps
    # the result must decode to exactly the same pixels
    if Image.open(io.BytesIO(cleaned)).tobytes() != image.tobytes():
        raise RuntimeError('pixel data changed; file left untouched')
    if not dry_run:
        tmp = path + '.tmp'
        with open(tmp, 'wb') as handle:
            handle.write(cleaned)
        os.replace(tmp, path)
    return True, had_gps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--photos-dir', default=os.getenv('SNAPSHOT_PHOTOS_DIR'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.photos_dir or not os.path.isdir(args.photos_dir):
        print('photos directory not found; pass --photos-dir or set '
              'SNAPSHOT_PHOTOS_DIR', file=sys.stderr)
        return 1

    total = changed = with_gps = failed = 0
    for dirpath, _, filenames in os.walk(args.photos_dir):
        for name in sorted(filenames):
            if not name.lower().endswith(('.jpg', '.jpeg')):
                continue
            path = os.path.join(dirpath, name)
            total += 1
            try:
                was_changed, had_gps = process(path, args.dry_run)
            except Exception as exc:  # keep going; report at the end
                failed += 1
                print(f'FAILED {path}: {exc}', file=sys.stderr)
                continue
            changed += was_changed
            with_gps += had_gps
            if was_changed:
                print(f'{"would clean" if args.dry_run else "cleaned"} '
                      f'{path}{"  (had GPS)" if had_gps else ""}')

    mode = 'DRY RUN — nothing written. ' if args.dry_run else ''
    print(f'{mode}{total} photos, {with_gps} with GPS, {changed} '
          f'{"to clean" if args.dry_run else "cleaned"}, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
