#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import time  # NOQA
import json  # NOQA
import base64  # NOQA
import os  # NOQA
import hashlib  # NOQA
import pickle  # NOQA
import math  # NOQA
import struct  # NOQA
from threading import RLock  # NOQA
import uuid  # NOQA
from datetime import datetime, timedelta  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'Session'  # NOQA
ghenv.Component.NickName = 'CSC_Session'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '1 User'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Handles user authentication with the remote API, manages access '
    'tokens, and provides a unified catalog cache (identities and '
    'snapshots stored independently, mesh PLY geometry cached per '
    'snapshot). Stores authentication state in scriptcontext.sticky.'
)

"""
Author: Max Benjamin Eschenbach
License: MIT License
Version: 260609
"""


def _compute_compose_etag(identity_doc, snapshot_doc):
    """Match backend ``_compute_compose_etag`` (identity + snapshot pair)."""
    payload = (
        f"{identity_doc.get('lastmodified', '')}::"
        f"{snapshot_doc.get('etag', '')}"
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _query_cache_key(params):
    """Stable cache key for a GET /identities query parameter dict."""
    if not params:
        return 'query:identities'
    items = sorted((str(k), str(v)) for k, v in params.items())
    payload = '&'.join(f'{k}={v}' for k, v in items)
    return 'query:' + hashlib.md5(payload.encode('utf-8')).hexdigest()


class _CachedResponse(object):
    """Minimal response wrapper for cache hits (status 200 + JSON body)."""

    def __init__(self, data, etag=None, status_code=200):
        self.status_code = status_code
        self._data = data
        self._etag = etag

    def json(self):
        return self._data

    @property
    def headers(self):
        return {'ETag': self._etag} if self._etag else {}


# ComponentCache - Embedded ---------------------------------------------------

class _ComponentCache(object):
    """
    Component cache manager for efficient local storage and retrieval.

    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    def __init__(self, cache_dir=None, ttl_hours=24):
        self.ttl_hours = ttl_hours
        self.cache_dir = cache_dir or self._get_default_cache_dir()
        self.components_dir = os.path.join(self.cache_dir, 'components')
        self.identities_dir = os.path.join(self.cache_dir, 'identities')
        self.snapshots_dir = os.path.join(self.cache_dir, 'snapshots')
        self.designs_dir = os.path.join(self.cache_dir, 'designs')
        self.metadata_dir = os.path.join(self.cache_dir, 'metadata')
        self.geometry_dir = os.path.join(self.cache_dir, 'component_geometry')
        self._lock = RLock()

        # Ensure cache directories exist
        self._ensure_cache_dirs()

    def _get_default_cache_dir(self):
        """Get platform-specific cache directory."""
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA', '')
            return os.path.join(appdata, 'DDU_CSC', 'cache')
        else:  # macOS/Linux
            home = os.path.expanduser('~')
            return os.path.join(
                home, 'Library', 'Application Support', 'DDU_CSC', 'cache'
            )

    def _ensure_cache_dirs(self):
        """Create cache directories if they don't exist."""
        dirs = [
            self.cache_dir, self.components_dir, self.identities_dir,
            self.snapshots_dir, self.designs_dir, self.metadata_dir,
            self.geometry_dir
        ]
        for directory in dirs:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

    def _get_cache_key_hash(self, cache_key):
        """Generate a safe filename from cache key."""
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()

    def _is_expired(self, timestamp_str):
        """Check if cache entry is expired based on TTL."""
        try:
            timestamp = datetime.fromisoformat(
                timestamp_str.replace('Z', '+00:00'))
            expiry = timestamp + timedelta(hours=self.ttl_hours)
            return datetime.now(timestamp.tzinfo) > expiry
        except (ValueError, TypeError):
            return True  # If we can't parse timestamp, consider expired

    def get(self, cache_key, filters=None):
        """
        Get cached data for a cache key.

        Args:
            cache_key: Cache key (e.g., 'all_components', 'component:uuid')
            filters: Optional filter parameters for metadata cache

        Returns:
            Tuple of (data, etag, is_from_cache) or
            (None, None, False) if not found
        """
        # Try binary cache first
        return self.get_binary(cache_key)

    def set(self, cache_key, data, etag=None, filters=None):
        """
        Store data in cache.

        Args:
            cache_key: Cache key
            data: Data to cache
            etag: ETag for the data
            filters: Optional filter parameters
        """
        # Use binary cache
        self.set_binary(cache_key, data, etag, filters)

    def _write_metadata(self, cache_key, metadata):
        metadata_file = os.path.join(
            self.metadata_dir,
            f"{self._get_cache_key_hash(cache_key)}.json"
        )
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def _read_metadata(self, cache_key):
        metadata_file = os.path.join(
            self.metadata_dir,
            f"{self._get_cache_key_hash(cache_key)}.json"
        )
        if not os.path.exists(metadata_file):
            return None
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        if self._is_expired(metadata.get('cached_at', '')):
            return None
        return metadata

    # Identity / snapshot catalog cache (v0.5) -------------------------------

    def set_identity(self, identity_id, identity_doc):
        """Store one identity document (keyed by identity id)."""
        with self._lock:
            try:
                cache_key = f'identity:{identity_id}'
                identity_file = os.path.join(
                    self.identities_dir, f'{identity_id}.pkl'
                )
                with open(identity_file, 'wb') as f:
                    pickle.dump(identity_doc, f)
                self._write_metadata(cache_key, {
                    'cache_key': cache_key,
                    'cached_at': datetime.now().isoformat(),
                    'etag': identity_doc.get('lastmodified'),
                    'type': 'identity',
                    'current_snapshot_id': identity_doc.get(
                        'current_snapshot_id'),
                })
            except (IOError, pickle.PickleError):
                pass

    def get_identity(self, identity_id):
        """Return (identity_doc, etag, is_cached)."""
        with self._lock:
            try:
                cache_key = f'identity:{identity_id}'
                metadata = self._read_metadata(cache_key)
                if metadata is None:
                    return None, None, False
                identity_file = os.path.join(
                    self.identities_dir, f'{identity_id}.pkl'
                )
                if not os.path.exists(identity_file):
                    return None, None, False
                with open(identity_file, 'rb') as f:
                    identity_doc = pickle.load(f)
                return identity_doc, metadata.get('etag'), True
            except (IOError, pickle.PickleError, KeyError):
                return None, None, False

    def set_snapshot(self, snapshot_id, snapshot_doc):
        """Store one snapshot document (keyed by snapshot id)."""
        with self._lock:
            try:
                cache_key = f'snapshot:{snapshot_id}'
                snapshot_file = os.path.join(
                    self.snapshots_dir, f'{snapshot_id}.pkl'
                )
                with open(snapshot_file, 'wb') as f:
                    pickle.dump(snapshot_doc, f)
                self._write_metadata(cache_key, {
                    'cache_key': cache_key,
                    'cached_at': datetime.now().isoformat(),
                    'etag': snapshot_doc.get('etag'),
                    'type': 'snapshot',
                    'identity_id': snapshot_doc.get('identity_id'),
                })
            except (IOError, pickle.PickleError):
                pass

    def get_snapshot(self, snapshot_id):
        """Return (snapshot_doc, etag, is_cached)."""
        with self._lock:
            try:
                cache_key = f'snapshot:{snapshot_id}'
                metadata = self._read_metadata(cache_key)
                if metadata is None:
                    return None, None, False
                snapshot_file = os.path.join(
                    self.snapshots_dir, f'{snapshot_id}.pkl'
                )
                if not os.path.exists(snapshot_file):
                    return None, None, False
                with open(snapshot_file, 'rb') as f:
                    snapshot_doc = pickle.load(f)
                return snapshot_doc, metadata.get('etag'), True
            except (IOError, pickle.PickleError, KeyError):
                return None, None, False

    def ingest_compose_row(self, row):
        """
        Store identity + snapshot from one compose row.

        Returns the identity id when both parts were stored, else None.
        """
        if not isinstance(row, dict):
            return None
        identity = row.get('identity')
        snapshot = row.get('snapshot')
        if not isinstance(identity, dict) or not isinstance(snapshot, dict):
            return None
        identity_id = identity.get('_id') or identity.get('id')
        snapshot_id = snapshot.get('_id') or snapshot.get('id')
        if not identity_id or not snapshot_id:
            return None
        self.set_identity(identity_id, identity)
        self.set_snapshot(snapshot_id, snapshot)
        return identity_id

    def ingest_compose_rows(self, rows):
        """Store many compose rows; return ordered identity ids."""
        identity_ids = []
        for row in rows or []:
            identity_id = self.ingest_compose_row(row)
            if identity_id:
                identity_ids.append(identity_id)
        return identity_ids

    def assemble_compose(self, identity_id):
        """
        Build {identity, snapshot} from independently cached documents.

        Uses identity.current_snapshot_id to pick the snapshot.
        """
        identity_doc, _, identity_ok = self.get_identity(identity_id)
        if not identity_ok or not identity_doc:
            return None
        snapshot_id = identity_doc.get('current_snapshot_id')
        if not snapshot_id:
            return None
        snapshot_doc, _, snapshot_ok = self.get_snapshot(snapshot_id)
        if not snapshot_ok or not snapshot_doc:
            return None
        return {'identity': identity_doc, 'snapshot': snapshot_doc}

    def set_query(self, query_key, identity_ids, etag=None, params=None):
        """Store list-query metadata (identity id index + list ETag)."""
        with self._lock:
            try:
                self._write_metadata(query_key, {
                    'cache_key': query_key,
                    'cached_at': datetime.now().isoformat(),
                    'etag': etag,
                    'type': 'query',
                    'identity_ids': list(identity_ids),
                    'params': params,
                })
            except (IOError, TypeError):
                pass

    def get_query(self, query_key):
        """Return (identity_ids, etag, is_cached) for a list query."""
        with self._lock:
            try:
                metadata = self._read_metadata(query_key)
                if metadata is None:
                    return None, None, False
                return (
                    metadata.get('identity_ids') or [],
                    metadata.get('etag'),
                    True,
                )
            except (IOError, KeyError):
                return None, None, False

    def assemble_compose_list(self, identity_ids):
        """Build compose rows from cached identity/snapshot documents."""
        rows = []
        for identity_id in identity_ids or []:
            compose = self.assemble_compose(identity_id)
            if compose:
                rows.append(compose)
        return rows

    def invalidate(self, pattern=None):
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match cache keys (None = clear all)
        """
        with self._lock:
            try:
                if pattern is None:
                    # Clear all cache
                    for directory in [
                            self.components_dir,
                            self.identities_dir,
                            self.snapshots_dir,
                            self.metadata_dir,
                            self.geometry_dir
                    ]:
                        if os.path.exists(directory):
                            for filename in os.listdir(directory):
                                file_path = os.path.join(directory, filename)
                                if os.path.isfile(file_path):
                                    os.remove(file_path)
                                elif os.path.isdir(file_path):
                                    # Remove subdirectories
                                    # (geometry type folders)
                                    import shutil
                                    shutil.rmtree(
                                        file_path,
                                        ignore_errors=True
                                    )
                else:
                    # Clear specific pattern
                    pattern_hash = self._get_cache_key_hash(pattern)
                    metadata_file = os.path.join(
                        self.metadata_dir, f"{pattern_hash}.json"
                    )
                    if os.path.exists(metadata_file):
                        os.remove(metadata_file)

            except (IOError, OSError):
                pass

    def get_cache_stats(self):
        """Get cache statistics."""
        with self._lock:
            try:
                component_count = len(
                    [f for f in os.listdir(self.components_dir)
                     if f.endswith('.pkl')]
                )
                identity_count = len(
                    [f for f in os.listdir(self.identities_dir)
                     if f.endswith('.pkl')]
                )
                snapshot_count = len(
                    [f for f in os.listdir(self.snapshots_dir)
                     if f.endswith('.pkl')]
                )
                metadata_count = len(
                    [f for f in os.listdir(self.metadata_dir)
                     if f.endswith('.json')]
                )

                # Calculate total cache size
                total_size = 0
                for directory in [
                        self.components_dir, self.identities_dir,
                        self.snapshots_dir, self.metadata_dir
                ]:
                    for filename in os.listdir(directory):
                        file_path = os.path.join(directory, filename)
                        if os.path.isfile(file_path):
                            total_size += os.path.getsize(file_path)

                # Calculate geometry cache stats
                geometry_count = 0
                geometry_size = 0
                if os.path.exists(self.geometry_dir):
                    for root, dirs, files in os.walk(self.geometry_dir):
                        for file in files:
                            if file.endswith('.pkl'):
                                geometry_count += 1
                                file_path = os.path.join(root, file)
                                if os.path.isfile(file_path):
                                    geometry_size += os.path.getsize(file_path)

                # Calculate design cache stats
                design_count = 0
                design_size = 0
                if os.path.exists(self.designs_dir):
                    for filename in os.listdir(self.designs_dir):
                        if filename.endswith('.pkl'):
                            design_count += 1
                            file_path = os.path.join(
                                self.designs_dir, filename)
                            if os.path.isfile(file_path):
                                design_size += os.path.getsize(file_path)

                return {
                    'component_count': component_count,
                    'identity_count': identity_count,
                    'snapshot_count': snapshot_count,
                    'metadata_count': metadata_count,
                    'geometry_count': geometry_count,
                    'design_count': design_count,
                    'total_size_bytes': (total_size + geometry_size +
                                         design_size),
                    'geometry_size_bytes': geometry_size,
                    'design_size_bytes': design_size,
                    'cache_dir': self.cache_dir
                }
            except (IOError, OSError):
                return {
                    'component_count': 0,
                    'identity_count': 0,
                    'snapshot_count': 0,
                    'metadata_count': 0,
                    'geometry_count': 0,
                    'design_count': 0,
                    'total_size_bytes': 0,
                    'geometry_size_bytes': 0,
                    'design_size_bytes': 0,
                    'cache_dir': self.cache_dir
                }

    def get_binary(self, cache_key):
        """
        Get cached data from binary cache.

        Args:
            cache_key: Cache key (e.g., 'component:uuid')

        Returns:
            Tuple of (data, etag, is_from_cache) or
            (None, None, False) if not found
        """
        with self._lock:
            try:
                # Check metadata cache first
                metadata_file = os.path.join(
                    self.metadata_dir,
                    f"{self._get_cache_key_hash(cache_key)}.json"
                )

                if not os.path.exists(metadata_file):
                    return None, None, False

                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                # Check if expired
                if self._is_expired(metadata.get('cached_at', '')):
                    return None, None, False

                # Handle different cache key types
                if cache_key.startswith('component:'):
                    # Individual component
                    component_id = cache_key.split(':', 1)[1]
                    component_file = os.path.join(
                        self.components_dir, f"{component_id}.pkl"
                    )

                    if os.path.exists(component_file):
                        with open(component_file, 'rb') as f:
                            component_data = pickle.load(f)
                        return component_data, metadata.get('etag'), True

                elif cache_key.startswith('design:'):
                    # Individual design
                    design_id = cache_key.split(':', 1)[1]
                    design_file = os.path.join(
                        self.designs_dir, f"{design_id}.pkl"
                    )

                    if os.path.exists(design_file):
                        with open(design_file, 'rb') as f:
                            design_data = pickle.load(f)
                        return design_data, metadata.get('etag'), True

                elif cache_key == 'schema:create_identity':
                    # Schema data is stored directly in metadata
                    return metadata.get('data'), metadata.get('etag'), True

                elif cache_key == 'schema:design':
                    # Schema data is stored directly in metadata
                    return metadata.get('data'), metadata.get('etag'), True

                return None, None, False

            except (IOError, pickle.PickleError, KeyError):
                return None, None, False

    def set_binary(self, cache_key, data, etag=None, filters=None):
        """
        Store data in binary cache.

        Args:
            cache_key: Cache key
            data: Data to cache
            etag: ETag for the data
            filters: Optional filter parameters
        """
        with self._lock:
            try:
                current_time = datetime.now().isoformat()
                # Guards against unhandled cache keys (avoids referencing an
                # unassigned ``metadata`` at the write step below).
                metadata = None

                if cache_key.startswith('component:'):
                    # Individual component
                    component_id = cache_key.split(':', 1)[1]
                    component_file = os.path.join(
                        self.components_dir, f"{component_id}.pkl"
                    )

                    # Store component data as pickle
                    with open(component_file, 'wb') as f:
                        pickle.dump(data, f)

                    # Store metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'component'
                    }

                elif cache_key.startswith('design:'):
                    # Individual design
                    design_id = cache_key.split(':', 1)[1]
                    design_file = os.path.join(
                        self.designs_dir, f"{design_id}.pkl"
                    )

                    # Store design data as pickle
                    with open(design_file, 'wb') as f:
                        pickle.dump(data, f)

                    # Store metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'design'
                    }

                elif cache_key == 'schema:create_identity':
                    # Schema data - store directly in metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'schema',
                        'data': data
                    }

                elif cache_key == 'schema:design':
                    # Schema data - store directly in metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'schema',
                        'data': data
                    }

                # Unhandled cache key: nothing to persist, bail out safely
                if metadata is None:
                    return

                # Write metadata file
                metadata_file = os.path.join(
                    self.metadata_dir,
                    f"{self._get_cache_key_hash(cache_key)}.json"
                )
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

            except (IOError, pickle.PickleError, KeyError):
                # Silently fail cache writes to not break main functionality
                pass

    def get_mesh_binary(self, snapshot_id, primitive_index, resolution):
        """
        Get one cached snapshot-primitive mesh from binary cache.

        Args:
            snapshot_id: Snapshot UUID
            primitive_index: Index into the snapshot geometry.meshes array
            resolution: 'reduced' or 'detailed'

        Returns:
            Tuple of (mesh, etag, is_from_cache) or (None, None, False)
        """
        with self._lock:
            try:
                cache_key = (
                    f'mesh:{resolution}:{snapshot_id}:{primitive_index}'
                )
                metadata_file = os.path.join(
                    self.metadata_dir,
                    f"{self._get_cache_key_hash(cache_key)}.json"
                )

                if not os.path.exists(metadata_file):
                    return None, None, False

                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                # Check if expired
                if self._is_expired(metadata.get('cached_at', '')):
                    return None, None, False

                # Get mesh file path
                mesh_file = os.path.join(
                    self.geometry_dir,
                    resolution,
                    f"{snapshot_id}_{primitive_index}.pkl"
                )

                if os.path.exists(mesh_file):
                    with open(mesh_file, 'rb') as f:
                        mesh_json = pickle.load(f)
                    mesh = Rhino.Geometry.Mesh.FromJSON(mesh_json)
                    if mesh:
                        return mesh, metadata.get('etag'), True

                return None, None, False

            except (IOError, pickle.PickleError, KeyError):
                return None, None, False

    def set_mesh_binary(
            self, snapshot_id, primitive_index, resolution, mesh, etag):
        """
        Cache one snapshot-primitive mesh as binary (mesh ToJSON pickle).

        Args:
            snapshot_id: Snapshot UUID
            primitive_index: Index into the snapshot geometry.meshes array
            resolution: 'reduced' or 'detailed'
            mesh: Rhino.Geometry.Mesh object (already parsed from PLY)
            etag: ETag from server response
        """
        with self._lock:
            try:
                current_time = datetime.now().isoformat()
                cache_key = (
                    f'mesh:{resolution}:{snapshot_id}:{primitive_index}'
                )

                # Create geometry subdirectory
                geometry_subdir = os.path.join(
                    self.geometry_dir, resolution
                )
                os.makedirs(geometry_subdir, exist_ok=True)

                # Convert mesh to JSON string using ToJSON
                options = Rhino.FileIO.SerializationOptions()
                options.WriteUserData = True
                options.WriteRenderMeshes = True
                options.WriteAnalysisMeshes = True
                mesh_json = mesh.ToJSON(options)

                # Store JSON string as pickle
                mesh_file = os.path.join(
                    geometry_subdir,
                    f"{snapshot_id}_{primitive_index}.pkl"
                )
                with open(mesh_file, 'wb') as f:
                    pickle.dump(mesh_json, f)

                # Store metadata
                metadata = {
                    'cache_key': cache_key,
                    'cached_at': current_time,
                    'etag': etag,
                    'type': 'mesh',
                    'resolution': resolution,
                    'snapshot_id': snapshot_id,
                    'primitive_index': primitive_index
                }

                metadata_file = os.path.join(
                    self.metadata_dir,
                    f"{self._get_cache_key_hash(cache_key)}.json"
                )
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

            except (IOError, pickle.PickleError, KeyError):
                # Silently fail cache writes to not break main functionality
                pass


def _parse_ply_binary_to_mesh(ply_bytes):
    """
    Parse a binary_little_endian PLY (CSC canonical, Rhino Z-up) into a
    single Rhino.Geometry.Mesh. Supports float/double vertex coords,
    optional uchar red/green/blue, and a face list (uchar count + int
    indices). No coordinate rotation is applied (PLY is already Z-up).
    Returns the mesh or None on failure.
    """
    try:
        if not ply_bytes:
            return None

        # Locate end of (ascii) header
        marker = b'end_header\n'
        header_end = ply_bytes.find(marker)
        if header_end == -1:
            print('PLY: missing end_header')
            return None
        header_text = ply_bytes[:header_end].decode('ascii', 'ignore')
        body = ply_bytes[header_end + len(marker):]

        if 'binary_little_endian' not in header_text:
            print('PLY: only binary_little_endian supported')
            return None

        # Parse header elements/properties
        _type_fmt = {
            'char': 'b', 'int8': 'b',
            'uchar': 'B', 'uint8': 'B',
            'short': 'h', 'int16': 'h',
            'ushort': 'H', 'uint16': 'H',
            'int': 'i', 'int32': 'i',
            'uint': 'I', 'uint32': 'I',
            'float': 'f', 'float32': 'f',
            'double': 'd', 'float64': 'd',
        }
        _type_size = {
            'b': 1, 'B': 1, 'h': 2, 'H': 2,
            'i': 4, 'I': 4, 'f': 4, 'd': 8,
        }

        vertex_count = 0
        face_count = 0
        vertex_props = []  # list of (fmt_char, name)
        face_list = None  # (count_fmt, index_fmt)
        current = None
        for raw_line in header_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            tok = line.split()
            if tok[0] == 'element':
                current = tok[1]
                if current == 'vertex':
                    vertex_count = int(tok[2])
                elif current == 'face':
                    face_count = int(tok[2])
            elif tok[0] == 'property':
                if tok[1] == 'list':
                    count_fmt = _type_fmt.get(tok[2], 'B')
                    index_fmt = _type_fmt.get(tok[3], 'i')
                    face_list = (count_fmt, index_fmt)
                elif current == 'vertex':
                    fmt = _type_fmt.get(tok[1])
                    if fmt:
                        vertex_props.append((fmt, tok[2]))

        if face_list is None:
            face_list = ('B', 'i')

        # Read vertices
        vertex_struct = struct.Struct(
            '<' + ''.join(f for f, _ in vertex_props)
        )
        names = [n for _, n in vertex_props]
        ix = names.index('x') if 'x' in names else 0
        iy = names.index('y') if 'y' in names else 1
        iz = names.index('z') if 'z' in names else 2
        has_color = ('red' in names and 'green' in names and
                     'blue' in names)
        if has_color:
            ir = names.index('red')
            ig = names.index('green')
            ib = names.index('blue')

        mesh = Rhino.Geometry.Mesh()
        offset = 0
        vsize = vertex_struct.size
        colors = []
        for _ in range(vertex_count):
            vals = vertex_struct.unpack_from(body, offset)
            offset += vsize
            mesh.Vertices.Add(
                float(vals[ix]), float(vals[iy]), float(vals[iz])
            )
            if has_color:
                colors.append(
                    (int(vals[ir]), int(vals[ig]), int(vals[ib]))
                )

        # Read faces
        count_fmt, index_fmt = face_list
        count_struct = struct.Struct('<' + count_fmt)
        count_size = _type_size[count_fmt]
        index_size = _type_size[index_fmt]
        for _ in range(face_count):
            (n,) = count_struct.unpack_from(body, offset)
            offset += count_size
            idx_struct = struct.Struct('<' + index_fmt * n)
            indices = idx_struct.unpack_from(body, offset)
            offset += index_size * n
            if n == 3:
                mesh.Faces.AddFace(indices[0], indices[1], indices[2])
            elif n == 4:
                mesh.Faces.AddFace(
                    indices[0], indices[1], indices[2], indices[3]
                )
            elif n > 4:
                for k in range(1, n - 1):
                    mesh.Faces.AddFace(
                        indices[0], indices[k], indices[k + 1]
                    )

        if has_color and len(colors) == mesh.Vertices.Count:
            for r, g, b in colors:
                mesh.VertexColors.Add(r, g, b)

        mesh.Normals.ComputeNormals()
        mesh.Compact()
        return mesh

    except Exception as e:
        print(f'Error parsing PLY: {str(e)}')
        return None


# AuthCore - Embedded ---------------------------------------------------------

class _AuthCore(object):
    """
    Authorization and cache management tool that gets stored in sticky to be
    used by other CSC Grasshopper Components.

    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    def __init__(self, base_url, leeway=30, disable_cache=False):
        self.base_url = (base_url or 'https://api.ddu.uber.space').rstrip('/')
        self.leeway = int(leeway) if leeway is not None else 30
        self.disable_cache = disable_cache
        self._lock = RLock()
        self._token = None
        self._exp = 0
        self._username = None
        self._cache = None if disable_cache else _ComponentCache()

    @staticmethod
    def _now():
        return int(time.time())

    @staticmethod
    def _b64url_decode(seg):
        rem = len(seg) % 4
        if rem:
            seg += '=' * (4 - rem)
        return base64.urlsafe_b64decode(seg.encode('utf-8'))

    @classmethod
    def _jwt_payload(cls, token):
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            return json.loads(cls._b64url_decode(parts[1]).decode('utf-8'))
        except Exception:
            return {}

    def set_access_token(self, token, username=None):
        payload = self._jwt_payload(token)
        exp = int(payload.get('exp', 0))
        if exp <= 0:
            exp = self._now() + 3600  # 1h fallback if no exp claim
        with self._lock:
            self._token = token
            self._exp = exp
            if username:
                self._username = username

    def clear(self):
        with self._lock:
            self._token = None
            self._exp = 0
            self._username = None

    def is_valid(self):
        with self._lock:
            if not self._token or self._exp <= 0:
                return False
            return (self._now() + self.leeway) < self._exp

    def get_username(self):
        with self._lock:
            return self._username

    def auth_header(self):
        with self._lock:
            return ({'Authorization': 'Bearer ' + self._token}
                    if self._token else {})

    def authorized_get(
            self,
            path,
            params=None,
            extra_headers=None,
            timeout=20):
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        return requests.get(
            self.base_url + path,
            params=params,
            headers=headers,
            timeout=timeout
        )

    def authorized_post(
            self,
            path,
            json_body=None,
            files=None,
            extra_headers=None,
            timeout=60):
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        # Handle file uploads vs JSON requests
        if files is not None:
            # For file uploads, don't set Content-Type header
            # (let requests handle it)
            # and use data instead of json
            return requests.post(
                self.base_url + path,
                files=files,
                headers=headers,
                timeout=timeout
            )
        else:
            # For JSON requests, use json parameter
            return requests.post(
                self.base_url + path,
                json=json_body,
                headers=headers,
                timeout=timeout
            )

    def validate_uuid(self, uuid_to_test: str, version: int = 4):
        """
        Check if uuid_to_test is a valid UUID.
        Returns True if uuid_to_test is a valid UUID, otherwise False.
        """
        try:
            uuid_obj = uuid.UUID(uuid_to_test, version=version)
        except ValueError:
            return False
        return str(uuid_obj) == uuid_to_test

    # Cache Management Methods ------------------------------------------------

    def get_cache(self):
        """Get the cache instance."""
        return self._cache

    def set_cache_enabled(self, enabled):
        """Enable or disable caching."""
        with self._lock:
            self.disable_cache = not enabled
            if enabled and self._cache is None:
                self._cache = _ComponentCache()
            elif not enabled:
                self._cache = None

    def is_cache_enabled(self):
        """Check if caching is enabled."""
        return self._cache is not None

    def sync_cache(self):
        """Force cache synchronization (clear cache)."""
        if self._cache:
            self._cache.invalidate()

    def get_cache_stats(self):
        """Get cache statistics."""
        if self._cache:
            return self._cache.get_cache_stats()
        return {
            'component_count': 0,
            'metadata_count': 0,
            'total_size_bytes': 0,
            'cache_dir': 'Cache disabled'
        }

    def cached_get(
            self,
            path,
            cache_key,
            params=None,
            extra_headers=None,
            timeout=20):
        """
        Make a cached GET request with ETag support.

        Args:
            path: API path
            cache_key: Cache key for this request
            params: Query parameters
            extra_headers: Additional headers
            timeout: Request timeout

        Returns:
            Response object
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        # If cache is disabled, make regular request
        if not self._cache:
            return self.authorized_get(path, params, extra_headers, timeout)

        # Check cache first
        cached_data, cached_etag, is_from_cache = self._cache.get(cache_key)

        # Prepare headers
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)

        # Add conditional request header if we have cached data
        if is_from_cache and cached_etag:
            headers['If-None-Match'] = cached_etag

        # Make request
        response = requests.get(
            self.base_url + path,
            params=params,
            headers=headers,
            timeout=timeout
        )

        # Handle response
        if response.status_code == 304 and is_from_cache:
            return _CachedResponse(cached_data, cached_etag)

        elif response.status_code == 200:
            # Data changed or first request - cache the response.
            # Cache writes must never break the fetch, so swallow any
            # parse/serialise/IO error and just return the live response.
            try:
                data = response.json()
                etag = response.headers.get('ETag')
                self._cache.set(cache_key, data, etag, params)
            except Exception:
                pass

        return response

    def cached_list_identities(
            self,
            params=None,
            extra_headers=None,
            timeout=60):
        """
        Fetch GET /identities with unified identity/snapshot caching.

        List responses store per-identity and per-snapshot documents plus a
        lightweight query index (identity ids + list ETag). A 304 reassembles
        compose rows from the individual caches.
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        params = dict(params or {})
        query_key = _query_cache_key(params)

        if not self._cache:
            return self.authorized_get(
                '/identities', params, extra_headers, timeout)

        identity_ids, query_etag, has_query = self._cache.get_query(
            query_key)

        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        if has_query and query_etag:
            headers['If-None-Match'] = query_etag

        response = requests.get(
            self.base_url + '/identities',
            params=params,
            headers=headers,
            timeout=timeout
        )

        if response.status_code == 304:
            if has_query and identity_ids:
                rows = self._cache.assemble_compose_list(identity_ids)
                if rows:
                    return _CachedResponse(rows, query_etag)
            # Stale query index — refetch without conditional header
            headers = self.auth_header()
            if extra_headers:
                headers.update(extra_headers)
            response = requests.get(
                self.base_url + '/identities',
                params=params,
                headers=headers,
                timeout=timeout
            )

        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    stored_ids = self._cache.ingest_compose_rows(data)
                    list_etag = response.headers.get('ETag')
                    self._cache.set_query(
                        query_key, stored_ids, list_etag, params)
            except Exception:
                pass

        return response

    def cached_get_compose(
            self,
            identity_id,
            extra_headers=None,
            timeout=20):
        """
        Fetch GET /identities/{id}/compose with identity/snapshot caching.

        Compose ETag is derived from cached identity.lastmodified and
        snapshot.etag (same as the backend). A 304 returns the assembled
        pair from cache.
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        path = f'/identities/{identity_id}/compose'

        if not self._cache:
            return self.authorized_get(
                path, None, extra_headers, timeout)

        compose = self._cache.assemble_compose(identity_id)
        compose_etag = None
        if compose:
            compose_etag = _compute_compose_etag(
                compose['identity'], compose['snapshot'])

        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        if compose_etag:
            headers['If-None-Match'] = compose_etag

        response = requests.get(
            self.base_url + path,
            headers=headers,
            timeout=timeout
        )

        if response.status_code == 304:
            if compose:
                return _CachedResponse(compose, compose_etag)
            # Stale identity/snapshot pair — refetch without conditional
            headers = self.auth_header()
            if extra_headers:
                headers.update(extra_headers)
            response = requests.get(
                self.base_url + path,
                headers=headers,
                timeout=timeout
            )

        if response.status_code == 200:
            try:
                data = response.json()
                self._cache.ingest_compose_row(data)
            except Exception:
                pass

        return response

    def cached_get_snapshot_mesh(self, snapshot_id, primitive_index,
                                 resolution, timeout=60):
        """
        Fetch one snapshot-primitive mesh PLY with ETag caching.

        Args:
            snapshot_id: Snapshot UUID
            primitive_index: Index into the snapshot geometry.meshes array
            resolution: 'reduced' or 'detailed'
            timeout: Request timeout

        Returns:
            Tuple of (mesh, etag, is_from_cache). ``mesh`` is None when the
            requested resolution is unavailable (404) or on parse/transport
            error, signalling the caller to fall back to inline geometry.
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        path = (
            f'/snapshots/{snapshot_id}/meshes/'
            f'{primitive_index}/{resolution}'
        )

        # If cache is disabled, fetch + parse without caching
        if not self._cache:
            response = self.authorized_get(path, timeout=timeout)
            if response.status_code == 200:
                mesh = _parse_ply_binary_to_mesh(response.content)
                etag = response.headers.get('ETag')
                return mesh, etag, False
            return None, None, False

        # Check binary cache first
        (cached_mesh,
         cached_etag,
         is_from_cache) = self._cache.get_mesh_binary(
            snapshot_id, primitive_index, resolution)

        # Prepare headers (conditional request when we have cached data)
        headers = self.auth_header()
        if is_from_cache and cached_etag:
            headers['If-None-Match'] = cached_etag

        response = requests.get(
            self.base_url + path,
            headers=headers,
            timeout=timeout
        )

        if response.status_code == 304 and is_from_cache:
            # Not modified - return cached mesh
            return cached_mesh, cached_etag, True

        if response.status_code == 200:
            mesh = _parse_ply_binary_to_mesh(response.content)
            etag = response.headers.get('ETag')
            if mesh is not None:
                try:
                    self._cache.set_mesh_binary(
                        snapshot_id, primitive_index, resolution, mesh, etag
                    )
                except (ValueError, KeyError):
                    pass
            return mesh, etag, False

        # 404 / other -> unavailable; caller falls back to inline geometry
        return None, None, False

    def get_create_identity_schema(self, force_refresh=False):
        """
        Get CreateComponentRequest JSON Schema (POST /identities).

        Args:
            force_refresh: Force refresh of schema even if cached

        Returns:
            Schema dictionary or None if failed
        """
        cache_key = 'schema:create_identity'
        endpoint = '/schema/create-identity'

        if not self.base_url:
            raise RuntimeError(
                'Base URL not configured. Please sign in first.')

        if not self._cache:
            try:
                response = requests.get(f'{self.base_url}{endpoint}')
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception:
                return None

        if not force_refresh:
            cached_schema, cached_etag, is_from_cache = self._cache.get(
                cache_key)
            if is_from_cache:
                return cached_schema

        try:
            headers = {}
            if not force_refresh:
                cached_schema, cached_etag, is_from_cache = self._cache.get(
                    cache_key)
                if is_from_cache and cached_etag:
                    headers['If-None-Match'] = cached_etag

            response = requests.get(
                f'{self.base_url}{endpoint}',
                headers=headers,
            )

            if response.status_code == 304 and not force_refresh:
                cached_schema, _, is_from_cache = self._cache.get(cache_key)
                if is_from_cache:
                    return cached_schema

            elif response.status_code == 200:
                try:
                    data = response.json()
                    etag = response.headers.get('ETag')
                    self._cache.set(cache_key, data, etag)
                    return data
                except (ValueError, KeyError):
                    return None

            return None
        except Exception:
            if not force_refresh:
                cached_schema, _, is_from_cache = self._cache.get(cache_key)
                if is_from_cache:
                    return cached_schema
            return None

    def get_design_schema(self, force_refresh=False):
        """
        Get design schema with caching support.

        Args:
            force_refresh: Force refresh of schema even if cached

        Returns:
            Design schema dictionary or None if failed
        """
        # Schema endpoints are unprotected, so we can access without auth
        # But we still need to check if we have a valid base_url
        if not self.base_url:
            raise RuntimeError(
                'Base URL not configured. Please sign in first.')

        # If cache is disabled, make regular request
        # (schema endpoint is unprotected)
        if not self._cache:
            try:
                response = requests.get(f'{self.base_url}/schema/design')
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception:
                return None

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_schema, cached_etag, is_from_cache = self._cache.get(
                'schema:design')
            if is_from_cache:
                return cached_schema

        # Make request to get schema (unprotected endpoint)
        try:
            # Prepare headers for conditional request
            headers = {}
            if not force_refresh:
                cached_schema, cached_etag, is_from_cache = self._cache.get(
                    'schema:design')
                if is_from_cache and cached_etag:
                    headers['If-None-Match'] = cached_etag

            response = requests.get(f'{self.base_url}/schema/design',
                                    headers=headers)

            if response.status_code == 304 and not force_refresh:
                # Not modified - return cached data
                cached_schema, _, is_from_cache = self._cache.get(
                    'schema:design')
                if is_from_cache:
                    return cached_schema

            elif response.status_code == 200:
                # Data changed or first request - cache the response
                try:
                    data = response.json()
                    etag = response.headers.get('ETag')
                    self._cache.set('schema:design', data, etag)
                    return data
                except (ValueError, KeyError):
                    return None

            return None
        except Exception:
            # If request fails and we have cached schema, return cached version
            if not force_refresh:
                cached_schema, _, is_from_cache = self._cache.get(
                    'schema:design')
                if is_from_cache:
                    return cached_schema
            return None


class CSC_Session(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    # Development setting - do not change!
    __HARD_RESET = False

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = 'Your Username or E-Mail'
        self.InputParams[1].Description = 'Your password'
        self.InputParams[2].Description = (
            'Refresh toggle, press when your token expired'
        )
        self.InputParams[3].Description = (
            'Disable caching (default: False - caching enabled)'
        )
        self.InputParams[4].Description = (
            'Clear cache (default: False)'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Status Message'
        )

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage or create new one."""
        if not self.__HARD_RESET:
            auth_core = sc.sticky.get('CSC_AuthCore')
        else:
            auth_core = None
        if auth_core is None:
            # Create new AuthCore instance with default settings
            auth_core = _AuthCore(
                base_url='https://api.ddu.uber.space'
            )
            sc.sticky['CSC_AuthCore'] = auth_core
        return auth_core

    def RunScript(self,
            Username: str,
            Password: str,
            Refresh: bool,
            DisableCache: bool,
            ClearCache: bool):
        # Initialize status messages list
        status_messages = []

        # Sanitize input parameters (defaults don't work in function signature)
        if DisableCache is None:
            DisableCache = False
        if ClearCache is None:
            ClearCache = False

        # Get or create AuthCore instance
        auth_core = self.get_auth_core_from_sticky()

        # Handle cache management
        if ClearCache:
            auth_core.sync_cache()
            status_messages.append('Cache cleared')
            self.Component.Message = 'Cache cleared'
            # Return status messages
            Status = status_messages
            return (Status,)

        # Set cache enabled/disabled
        auth_core.set_cache_enabled(not DisableCache)

        # Input validation
        if not Username or not Username.strip():
            status_messages.append('Please provide username/email')
            self.Component.Message = 'Please provide username/email'
            Status = status_messages
            return (Status,)

        if not Password or not Password.strip():
            status_messages.append('Please provide password')
            self.Component.Message = 'Please provide password'
            Status = status_messages
            return (Status,)

        username = Username.strip()
        password = Password.strip()

        try:
            if Refresh:
                # Refresh authentication - clear existing token and re-auth
                auth_core.clear()
                self.Component.Message = 'Refreshing authentication...'
            else:
                # Check if we already have a valid token
                if auth_core.is_valid():
                    current_user = auth_core.get_username()
                    self.Component.Message = (
                        f'Already signed in as: {current_user}'
                    )

                    # Fetch and cache create-identity schema
                    try:
                        schema = auth_core.get_create_identity_schema()
                        if schema:
                            status_messages.append(
                                'Create-identity schema cached')
                            self._addRemark(
                                'Create-identity schema cached successfully'
                            )
                        else:
                            status_messages.append('Failed to cache schema')
                            self._addWarning(
                                'Failed to cache create-identity schema'
                            )
                    except Exception as e:
                        status_messages.append(
                            f'Schema caching failed: {str(e)}')
                        self._addWarning(f'Schema cache failed: {str(e)}')

                    # Get cache status for output
                    cache_stats = auth_core.get_cache_stats()
                    cache_enabled = auth_core.is_cache_enabled()
                    comp_count = cache_stats["component_count"]
                    geometry_count = cache_stats["geometry_count"]
                    design_count = cache_stats["design_count"]
                    size_kb = cache_stats["total_size_bytes"] // 1024
                    geometry_size_kb = (
                        cache_stats["geometry_size_bytes"] // 1024
                    )
                    design_size_kb = (
                        cache_stats["design_size_bytes"] // 1024
                    )

                    # Add cache status to messages
                    cache_status = (
                        'Cache: '
                        f'{"Enabled" if cache_enabled else "Disabled"}\n'
                        f' | Components: {comp_count}\n'
                        f' | Geometry: {geometry_count} files\n'
                        f' | Designs: {design_count} files\n'
                        f' | Size: {size_kb} kB\n'
                        f' | Geometry: {geometry_size_kb} kB\n'
                        f' | Designs: {design_size_kb} kB\n')
                    status_messages.append(cache_status)
                    Status = status_messages
                    return (Status,)

                self.Component.Message = 'Signing in...'

            # Prepare login data
            login_data = {
                'username': username,
                'password': password
            }

            # Make login request
            response = requests.post(
                f'{auth_core.base_url}/auth/token',
                data=login_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                timeout=20
            )

            if response.status_code == 200:
                # Login successful
                token_data = response.json()
                access_token = token_data.get('access_token')

                if access_token:
                    # Store token in AuthCore
                    auth_core.set_access_token(access_token, username)

                    # Update sticky storage
                    sc.sticky['CSC_AuthCore'] = auth_core

                    # Fetch and cache create-identity schema
                    try:
                        schema = auth_core.get_create_identity_schema()
                        if schema:
                            status_messages.append(
                                'Create-identity schema cached')
                            self._addRemark(
                                'Create-identity schema cached successfully'
                            )
                        else:
                            status_messages.append('Failed to cache schema')
                            self._addWarning(
                                'Failed to cache create-identity schema'
                            )
                    except Exception as e:
                        status_messages.append(
                            f'Schema caching failed: {str(e)}')
                        self._addWarning(f'Schema cache failed: {str(e)}')

                    # Get cache status for output
                    cache_stats = auth_core.get_cache_stats()
                    cache_enabled = auth_core.is_cache_enabled()
                    comp_count = cache_stats["component_count"]
                    geometry_count = cache_stats["geometry_count"]
                    design_count = cache_stats["design_count"]
                    size_kb = cache_stats["total_size_bytes"] // 1024
                    geometry_size_kb = (
                        cache_stats["geometry_size_bytes"] // 1024
                    )
                    design_size_kb = (
                        cache_stats["design_size_bytes"] // 1024
                    )

                    # Add cache status to messages
                    cache_status = (
                        f'Cache: '
                        f'{"Enabled" if cache_enabled else "Disabled"}\n'
                        f' | Components: {comp_count}\n'
                        f' | Geometry: {geometry_count} files\n'
                        f' | Designs: {design_count} files\n'
                        f' | Size: {size_kb} kB\n'
                        f' | Geometry: {geometry_size_kb} kB\n'
                        f' | Designs: {design_size_kb} kB\n')
                    status_messages.append(cache_status)

                    self.Component.Message = f'Signed in as: {username}'

                    # Return status messages
                    Status = status_messages
                    return (Status,)

                else:
                    msg = 'Login failed: No token received'
                    status_messages.append(msg)
                    self._addWarning(msg)
                    self.Component.Message = msg
                    Status = status_messages
                    return (Status,)

            elif response.status_code == 401:
                msg = 'Invalid username or password'
                status_messages.append(msg)
                self._addError(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

            elif response.status_code == 422:
                msg = 'Invalid input data'
                status_messages.append(msg)
                self._addError(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

            elif response.status_code == 500:
                msg = 'Server error - please try again'
                status_messages.append(msg)
                self._addWarning(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

            else:
                msg = f'Login failed with status code: {response.status_code}'
                status_messages.append(msg)
                self._addError(msg)
                self.Component.Message = msg
                Status = status_messages
                return (Status,)

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server - check URL'
            status_messages.append(msg)
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg
            Status = status_messages
            return (Status,)

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout - server may be slow'
            status_messages.append(msg)
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg
            Status = status_messages
            return (Status,)

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            status_messages.append(msg)
            self._addError(msg)
            self.Component.Message = msg
            Status = status_messages
            return (Status,)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            status_messages.append(msg)
            self.Component.Message = msg
            Status = status_messages
            return (Status,)
