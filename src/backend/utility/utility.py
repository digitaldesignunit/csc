#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import datetime
import os
from fastapi import HTTPException, UploadFile

from settings import EVIDENCE_UPLOAD_MAX_MB, get_settings  # noqa: F401


# FUNCTION DEFINITIONS --------------------------------------------------------

def sanitize_path(fp: str = '') -> str:
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


def mm_to_inches(mm):
    """Convert millimeters to inches."""
    return mm / 25.4


# CONFIG LOADING --------------------------------------------------------------

# The values come from settings.py (decision 8.156); these functions keep the
# names the callers use.
def get_db_connectionstring() -> str:
    """MongoDB connection string (MONGODB_URI)."""
    return get_settings().need('MONGODB_URI')


def get_database_name() -> str:
    """The MongoDB database (MONGODB_DB, default ``csc``)."""
    return get_settings().mongodb_db


def get_cors_origins() -> list:
    """CORS origins (FASTAPI_CORS_ORIGINS, comma-separated list)."""
    get_settings().require('FASTAPI_CORS_ORIGINS')
    return get_settings().cors_origins


def get_snapshot_preview_directory() -> str:
    """Rendered catalog thumbnails keyed by snapshot_id."""
    return get_settings().need('SNAPSHOT_PREVIEW_DIR')


def get_snapshot_photos_directory() -> str:
    """User-uploaded photos keyed by snapshot_id / index."""
    return get_settings().need('SNAPSHOT_PHOTOS_DIR')


def get_snapshot_meshes_directory() -> str:
    """
    PLY mesh files:
        meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply.
    """
    return get_settings().need('SNAPSHOT_MESHES_DIR')


def get_snapshot_point_clouds_directory() -> str:
    """PLY point clouds: point_clouds/<snapshot_id>/<index>.ply."""
    return get_settings().need('SNAPSHOT_POINT_CLOUDS_DIR')


def get_snapshot_proxies_directory() -> str:
    """Deviation maps: proxies/<snapshot_id>/<proxy_index>/<face_id>.png."""
    return get_settings().need('SNAPSHOT_PROXIES_DIR')


def get_snapshot_capture_directory() -> str:
    """Capture fixtures: capture/<snapshot_id>/fixtures/<i>.ply."""
    return get_settings().need('SNAPSHOT_CAPTURE_DIR')


def get_evidence_attachments_directory() -> str:
    """Evidence attachments: evidence/<evidence_id>/<index>.<ext>."""
    return get_settings().need('EVIDENCE_ATTACHMENTS_DIR')


def get_evidence_upload_limit_bytes() -> int:
    """Largest evidence attachment accepted: 25 MB (decision 8.82); the
    environment (EVIDENCE_UPLOAD_LIMIT_MB) may only lower it."""
    return get_settings().evidence_upload_limit_mb * 1024 * 1024


def get_snapshot_photo_upload_limit_bytes() -> int:
    return get_settings().snapshot_photo_upload_limit_mb * 1024 * 1024


def get_snapshot_photo_max_output_bytes() -> int:
    return get_settings().snapshot_photo_max_output_mb * 1024 * 1024


def get_snapshot_photo_max_long_edge_px() -> int:
    return get_settings().snapshot_photo_max_long_edge_px


def get_gh_xml_cache_directory() -> str:
    """Cache folder of the UserObject XML (GH_XML_CACHE_DIR)."""
    return get_settings().need('GH_XML_CACHE_DIR')


def get_github_repo_url() -> str:
    """GitHub repository URL (GITHUB_REPO_URL)."""
    return get_settings().need('GITHUB_REPO_URL')


def get_github_repo_token() -> str:
    """
    Optional GitHub token from GITHUB_CSC_GH_TOKEN.

    Public repos do not require a token. A token is only useful to increase
    GitHub API rate limits for CSC_Update.
    """
    return get_settings().github_csc_gh_token.get_secret_value()


def create_logging_timestamp():
    """
    Creates a timestamp in YY:MM:DD-HH:MM:SS format.
    """
    timestamp = datetime.datetime.today().strftime('%y:%m:%d-%H:%M:%S')
    return timestamp


def get_current_timestamp_z() -> str:
    """
    Return current UTC time as ISO 8601 string with 'Z', no offset, no
    subseconds.

    Example: '2024-06-21T09:31:39Z'
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(microsecond=0, tzinfo=None).isoformat() + 'Z'


def get_geometry_upload_limit_bytes() -> int:
    """Max geometry upload size (GEOMETRY_UPLOAD_LIMIT_MB, default 250 MB)."""
    return get_settings().geometry_upload_limit_mb * 1024 * 1024


async def read_upload_limited(upload: UploadFile, limit_bytes: int) -> bytes:
    """
    Read an uploaded file into memory, raising 413 if it exceeds limit_bytes.
    Reads in 64 KB chunks to avoid buffering the entire file before
    checking size.
    """
    chunks = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    'File too large '
                    f'(limit: {limit_bytes // (1024 * 1024)} MB)'
                    ),
            )
        chunks.append(chunk)
    return b''.join(chunks)


def ensure_file(path: str) -> str:
    """Return path if it exists, otherwise raise 404."""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='File not found')
    return path
