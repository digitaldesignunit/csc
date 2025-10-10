#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import datetime
import hashlib
import json
import os
from typing import TYPE_CHECKING

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

def get_db_connectionstring(config_file: str) -> str:
    """
    Read MongoDB connection string from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


def get_cors_origins(config_file: str):
    """
    Read CORS origins from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        origins = dbconfig['origins']
    return origins


def get_preview_directory(config_file: str) -> str:
    """
    Read preview directory from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        preview_dir = sanitize_path(dbconfig['preview_dir'])
    return preview_dir


def get_geometry_directory(config_file: str) -> str:
    """
    Read geometry directory from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        geometry_dir = sanitize_path(dbconfig['geometry_dir'])
    return geometry_dir


def get_github_repo_url(config_file: str) -> str:
    """
    Read GitHub repository URL from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        repo_url = dbconfig['github_repo_url']
    return repo_url


def get_github_repo_token(config_file: str) -> str:
    """
    Read GitHub repository token from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        token = dbconfig['github_repo_token']
    return token


def create_logging_timestamp():
    """
    Creates a timestamp in YY:MM:DD-HH:MM:SS format.
    """
    timestamp = datetime.datetime.today().strftime('%y:%m:%d-%H:%M:%S')
    return timestamp


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