#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import datetime
import os
from fastapi import HTTPException, UploadFile


# FUNCTION DEFINITIONS --------------------------------------------------------

def sanitize_path(fp: str = '') -> str:
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


def mm_to_inches(mm):
    """Convert millimeters to inches."""
    return mm / 25.4


# CONFIG LOADING --------------------------------------------------------------

def get_db_connectionstring() -> str:
    """
    Read MongoDB connection string from environment variable MONGODB_URI.
    """
    return os.environ['MONGODB_URI']


def get_database_name() -> str:
    """The MongoDB database (MONGODB_DB, default ``csc``)."""
    return os.environ.get('MONGODB_DB') or 'csc'


def get_cors_origins() -> list:
    """
    Read CORS origins from environment variable FASTAPI_CORS_ORIGINS
    (comma-separated list).
    """
    origins_str = os.environ['FASTAPI_CORS_ORIGINS']
    return [o.strip() for o in origins_str.split(',') if o.strip()]


def get_snapshot_preview_directory() -> str:
    """Rendered catalog thumbnails keyed by snapshot_id."""
    return sanitize_path(os.environ['SNAPSHOT_PREVIEW_DIR'])


def get_snapshot_photos_directory() -> str:
    """User-uploaded photos keyed by snapshot_id / index."""
    return sanitize_path(os.environ['SNAPSHOT_PHOTOS_DIR'])


def get_snapshot_meshes_directory() -> str:
    """
    PLY mesh files:
        meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply.
    """
    return sanitize_path(os.environ['SNAPSHOT_MESHES_DIR'])


def get_snapshot_point_clouds_directory() -> str:
    """PLY point clouds: point_clouds/<snapshot_id>/<index>.ply."""
    return sanitize_path(os.environ['SNAPSHOT_POINT_CLOUDS_DIR'])


def get_snapshot_proxies_directory() -> str:
    """Deviation maps: proxies/<snapshot_id>/<proxy_index>/<face_id>.png."""
    return sanitize_path(os.environ['SNAPSHOT_PROXIES_DIR'])


def get_snapshot_capture_directory() -> str:
    """Capture fixtures: capture/<snapshot_id>/fixtures/<i>.ply."""
    return sanitize_path(os.environ['SNAPSHOT_CAPTURE_DIR'])


def get_evidence_attachments_directory() -> str:
    """Evidence attachments: evidence/<evidence_id>/<index>.<ext>."""
    return sanitize_path(os.environ['EVIDENCE_ATTACHMENTS_DIR'])


EVIDENCE_UPLOAD_MAX_MB = 25


def get_evidence_upload_limit_bytes() -> int:
    """Largest evidence attachment accepted: 25 MB (decision 8.82); the
    environment (EVIDENCE_UPLOAD_LIMIT_MB) may only lower it."""
    mb = int(os.getenv('EVIDENCE_UPLOAD_LIMIT_MB',
                       str(EVIDENCE_UPLOAD_MAX_MB)))
    if not 1 <= mb <= EVIDENCE_UPLOAD_MAX_MB:
        raise ValueError(
            f'EVIDENCE_UPLOAD_LIMIT_MB must be 1 to {EVIDENCE_UPLOAD_MAX_MB}')
    return mb * 1024 * 1024


def get_snapshot_photo_upload_limit_bytes() -> int:
    mb = int(os.getenv('SNAPSHOT_PHOTO_UPLOAD_LIMIT_MB', '10'))
    return mb * 1024 * 1024


def get_snapshot_photo_max_output_bytes() -> int:
    mb = int(os.getenv('SNAPSHOT_PHOTO_MAX_OUTPUT_MB', '2'))
    return mb * 1024 * 1024


def get_snapshot_photo_max_long_edge_px() -> int:
    px = int(os.getenv('SNAPSHOT_PHOTO_MAX_LONG_EDGE_PX', '4096'))
    if px < 1:
        raise ValueError('SNAPSHOT_PHOTO_MAX_LONG_EDGE_PX must be >= 1')
    return px


def get_gh_xml_cache_directory() -> str:
    """
    Read GH XML cache directory from environment variable GH_XML_CACHE_DIR.
    """
    return sanitize_path(os.environ['GH_XML_CACHE_DIR'])


def get_github_repo_url() -> str:
    """
    Read GitHub repository URL from environment variable GITHUB_REPO_URL.
    """
    return os.environ['GITHUB_REPO_URL']


def get_github_repo_token() -> str:
    """
    Optional GitHub token from GITHUB_CSC_GH_TOKEN.

    Public repos do not require a token. A token is only useful to increase
    GitHub API rate limits for CSC_Update.
    """
    return os.getenv('GITHUB_CSC_GH_TOKEN', '')


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
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def get_geometry_upload_limit_bytes() -> int:
    """
    Read max geometry upload size from environment variable
    GEOMETRY_UPLOAD_LIMIT_MB (default: 250 MB).
    """
    mb = int(os.getenv('GEOMETRY_UPLOAD_LIMIT_MB', '250'))
    return mb * 1024 * 1024


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
