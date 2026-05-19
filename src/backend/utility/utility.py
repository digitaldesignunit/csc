#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import datetime
import hashlib
import json
import os
import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, UploadFile

if TYPE_CHECKING:
    from fastapi import Request


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


def get_cors_origins() -> list:
    """
    Read CORS origins from environment variable FASTAPI_CORS_ORIGINS
    (comma-separated list).
    """
    origins_str = os.environ['FASTAPI_CORS_ORIGINS']
    return [o.strip() for o in origins_str.split(',') if o.strip()]


def get_preview_directory() -> str:
    """
    Read preview directory from environment variable PREVIEW_DIR.
    """
    return sanitize_path(os.environ['PREVIEW_DIR'])


def get_snapshot_preview_directory() -> str:
    """Rendered catalog thumbnails keyed by snapshot_id."""
    explicit = os.getenv('SNAPSHOT_PREVIEW_DIR')
    if explicit:
        return sanitize_path(explicit)
    legacy_preview = get_preview_directory()
    return sanitize_path(
        os.path.join(os.path.dirname(legacy_preview), 'snapshot_previews')
    )


def get_snapshot_photos_directory() -> str:
    """User-uploaded photos keyed by snapshot_id / index."""
    explicit = os.getenv('SNAPSHOT_PHOTOS_DIR')
    if explicit:
        return sanitize_path(explicit)
    legacy_preview = get_preview_directory()
    return sanitize_path(
        os.path.join(os.path.dirname(legacy_preview), 'snapshot_photos')
    )


def get_snapshot_meshes_directory() -> str:
    """PLY mesh files: meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply."""
    explicit = os.getenv('SNAPSHOT_MESHES_DIR')
    if explicit:
        return sanitize_path(explicit)
    legacy_preview = get_preview_directory()
    return sanitize_path(
        os.path.join(os.path.dirname(legacy_preview), 'meshes')
    )


def get_snapshot_point_clouds_directory() -> str:
    """PLY point clouds: point_clouds/<snapshot_id>/<index>.ply."""
    explicit = os.getenv('SNAPSHOT_POINT_CLOUDS_DIR')
    if explicit:
        return sanitize_path(explicit)
    legacy_preview = get_preview_directory()
    return sanitize_path(
        os.path.join(os.path.dirname(legacy_preview), 'point_clouds')
    )


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


def get_geometry_directory() -> str:
    """
    Read geometry directory from environment variable GEOMETRY_DIR.
    """
    return sanitize_path(os.environ['GEOMETRY_DIR'])


def get_geometry_archive_directory() -> str:
    """
    Read geometry archive directory from environment variable
    GEOMETRY_ARCHIVE_DIR.
    """
    return sanitize_path(os.environ['GEOMETRY_ARCHIVE_DIR'])


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
    Read GitHub repository token from environment variable
    GITHUB_CSC_GH_TOKEN.
    """
    return os.environ['GITHUB_CSC_GH_TOKEN']


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


def generate_component_etag(component_data: dict) -> str:
    """
    Generate ETag for a component using hybrid hash approach.

    Creates a hash from lastmodified timestamp and key component fields
    (id, type, material, validated) for efficient cache validation.

    Args:
        component_data: Component data dictionary

    Returns:
        ETag string (hex digest of MD5 hash)
    """
    # Extract key fields for ETag generation
    key_fields = {
        'lastmodified': component_data.get('lastmodified', ''),
        'id': component_data.get('_id', component_data.get('id', '')),
        'type': component_data.get('type',
                                   component_data.get('componenttype', '')),
        'material': component_data.get('material', ''),
        'validated': str(component_data.get('validated', False))
    }

    # Create a consistent string representation
    etag_string = json.dumps(key_fields, sort_keys=True,
                             separators=(',', ':'))

    # Generate MD5 hash
    etag_hash = hashlib.md5(etag_string.encode('utf-8')).hexdigest()
    return etag_hash


def generate_geometry_etag(file_path: str, component_id: str) -> str:
    """
    Generate ETag for a geometry file using file stats.

    Args:
        file_path: Path to the geometry file
        component_id: Component ID for uniqueness

    Returns:
        ETag string (MD5 hash of file stats + component_id)
    """
    try:
        if not os.path.exists(file_path):
            return f'geometry-{component_id}-not-found'

        stat = os.stat(file_path)
        # Use modification time and file size for ETag
        etag_data = f'{component_id}-{stat.st_mtime}-{stat.st_size}'
        return hashlib.md5(etag_data.encode('utf-8')).hexdigest()
    except (OSError, IOError):
        return f'geometry-{component_id}-error'


def check_geometry_conditional_request(request: 'Request', etag: str) -> bool:
    """
    Check if request is a conditional request for geometry with If-None-Match.

    Args:
        request: FastAPI request object
        etag: Current ETag of the geometry resource

    Returns:
        True if resource hasn't changed (should return 304), False otherwise
    """
    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return True
    return False


def generate_etag_for_components(components: list) -> str:
    """
    Generate ETag for a list of components using the individual component
    ETag function.

    Args:
        components: List of component dictionaries

    Returns:
        ETag string (MD5 hash of component ETags)
    """

    # Generate ETag for each component and collect them
    component_etags = []
    for comp in components:
        etag = generate_component_etag(comp)
        component_etags.append(etag)

    # Sort for consistent hashing
    component_etags.sort()

    # Create hash of all component ETags
    etag_string = json.dumps(component_etags, separators=(',', ':'))
    etag_hash = hashlib.md5(etag_string.encode('utf-8')).hexdigest()

    return etag_hash


def generate_design_etag(design_data: dict) -> str:
    """
    Generate ETag for a design using hybrid hash approach.

    Creates a hash from lastmodified timestamp and key design fields
    (id, name, creator, components) for efficient cache validation.

    Args:
        design_data: Design data dictionary

    Returns:
        ETag string (hex digest of MD5 hash)
    """
    # Extract key fields for ETag generation
    key_fields = {
        'lastmodified': design_data.get('lastmodified', ''),
        'id': design_data.get('_id', design_data.get('id', '')),
        'name': design_data.get('name', ''),
        'creator': design_data.get('creator', ''),
        'components_count': len(design_data.get('components', [])),
        'additional_geometry_count': len(
            design_data.get('additional_geometry', [])
        ),
        'created': design_data.get('created', '')
    }

    # Create a consistent string representation
    etag_string = json.dumps(key_fields, sort_keys=True,
                             separators=(',', ':'))

    # Generate MD5 hash
    etag_hash = hashlib.md5(etag_string.encode('utf-8')).hexdigest()

    return etag_hash


def generate_etag_for_designs(designs: list) -> str:
    """
    Generate ETag for a list of designs using the individual design
    ETag function.

    Args:
        designs: List of design dictionaries

    Returns:
        ETag string (MD5 hash of design ETags)
    """
    if not designs:
        return hashlib.md5(b'').hexdigest()

    design_etags = []
    for design in designs:
        etag = generate_design_etag(design)
        design_etags.append(etag)

    # Sort for consistent hashing
    design_etags.sort()

    # Create hash of all design ETags
    etag_string = json.dumps(design_etags, separators=(',', ':'))
    etag_hash = hashlib.md5(etag_string.encode('utf-8')).hexdigest()

    return etag_hash


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


def validate_component_id(component_id: str) -> str:
    """Reject non-UUID component IDs before they can be used in file paths."""
    try:
        uuid.UUID(component_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail='Invalid component ID')
    return component_id


def ensure_file(path: str) -> str:
    """Return path if it exists, otherwise raise 404."""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='File not found')
    return path
