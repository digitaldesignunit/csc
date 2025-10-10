#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import time
import json
import base64
import os
import hashlib
import pickle
import math
from threading import RLock
import uuid
from datetime import datetime, timedelta

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SignIn'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'SignIn'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '1 User'  # type: ignore[reportUnedfinedVariable] # NOQA

"""
Author: Max Benjamin Eschenbach
License: MIT License
Version: 251007
"""


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
            self.cache_dir, self.components_dir, self.metadata_dir,
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
                metadata_count = len(
                    [f for f in os.listdir(self.metadata_dir)
                     if f.endswith('.json')]
                )

                # Calculate total cache size
                total_size = 0
                for directory in [self.components_dir, self.metadata_dir]:
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

                return {
                    'component_count': component_count,
                    'metadata_count': metadata_count,
                    'geometry_count': geometry_count,
                    'total_size_bytes': total_size + geometry_size,
                    'geometry_size_bytes': geometry_size,
                    'cache_dir': self.cache_dir
                }
            except (IOError, OSError):
                return {
                    'component_count': 0,
                    'metadata_count': 0,
                    'geometry_count': 0,
                    'total_size_bytes': 0,
                    'geometry_size_bytes': 0,
                    'cache_dir': self.cache_dir
                }

    def get_geometry(self, component_id, geometry_type):
        """
        Get cached geometry for a component.

        Args:
            component_id: Component ID
            geometry_type: 'reduced' or 'detailed'

        Returns:
            Tuple of (geometry_data, etag, is_from_cache) or
            (None, None, False) if not found
        """
        # Try binary cache first
        return self.get_geometry_binary(component_id, geometry_type)

    def set_geometry(self, component_id, geometry_type, geometry_data, etag):
        """
        Cache geometry data for a component.

        Args:
            component_id: Component ID
            geometry_type: 'reduced' or 'detailed'
            geometry_data: OBJ file content as string
            etag: ETag from server response
        """
        # Convert OBJ string to Rhino meshes and store as binary
        try:
            meshes = self._convert_obj_to_meshes(geometry_data)
            if meshes:  # Only store if conversion succeeded
                self.set_geometry_binary(
                    component_id,
                    geometry_type,
                    meshes,
                    etag
                )
        except Exception as e:
            # Don't cache anything if conversion fails
            self._addError(
                f"Error converting OBJ to meshes: {str(e)}")

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

                elif (cache_key == 'all_components' or
                        cache_key.startswith('filtered:')):
                    # Collection of components
                    components = []
                    for comp_ref in metadata.get('components', []):
                        comp_id = comp_ref.get('id')
                        if comp_id:
                            comp_file = os.path.join(
                                self.components_dir, f"{comp_id}.pkl"
                            )
                            if os.path.exists(comp_file):
                                with open(comp_file, 'rb') as f:
                                    components.append(pickle.load(f))

                    return components, metadata.get('etag'), True

                elif cache_key == 'schema:component':
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

                elif (cache_key == 'all_components' or
                        cache_key.startswith('filtered:')):
                    # Collection of components
                    components = []
                    for component in data:
                        comp_id = component.get('_id') or component.get('id')
                        if comp_id:
                            # Store individual component as pickle
                            comp_file = os.path.join(
                                self.components_dir, f"{comp_id}.pkl"
                            )
                            with open(comp_file, 'wb') as f:
                                pickle.dump(component, f)

                            # Add reference to metadata
                            components.append({
                                'id': comp_id,
                                'etag': component.get('etag'),
                                'lastmodified': component.get('lastmodified')
                            })

                    # Store metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'collection',
                        'components': components,
                        'filters': filters
                    }

                elif cache_key == 'schema:component':
                    # Schema data - store directly in metadata
                    metadata = {
                        'cache_key': cache_key,
                        'cached_at': current_time,
                        'etag': etag,
                        'type': 'schema',
                        'data': data
                    }

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

    def get_geometry_binary(self, component_id, geometry_type):
        """
        Get cached geometry from binary cache.

        Args:
            component_id: Component ID
            geometry_type: 'reduced' or 'detailed'

        Returns:
            Tuple of (meshes, etag, is_from_cache) or
            (None, None, False) if not found
        """
        with self._lock:
            try:
                cache_key = f'geometry:{geometry_type}:{component_id}'
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

                # Get geometry file path
                geometry_file = os.path.join(
                    self.geometry_dir,
                    geometry_type,
                    f"{component_id}.pkl"
                )

                if os.path.exists(geometry_file):
                    with open(geometry_file, 'rb') as f:
                        mesh_json_strings = pickle.load(f)

                    # Reconstruct meshes from JSON using FromJSON
                    meshes = []
                    for json_string in mesh_json_strings:
                        try:
                            mesh = Rhino.Geometry.Mesh.FromJSON(json_string)
                            if mesh:
                                meshes.append(mesh)
                        except Exception as e:
                            # Log error but continue with other meshes
                            self._addError(
                                f"Error reconstructing mesh "
                                f"from JSON: {str(e)}")
                            continue

                    # If no meshes could be reconstructed, return failure
                    if not meshes:
                        return None, None, False

                    return meshes, metadata.get('etag'), True

                return None, None, False

            except (IOError, pickle.PickleError, KeyError):
                return None, None, False

    def set_geometry_binary(self, component_id, geometry_type, meshes, etag):
        """
        Cache geometry data as binary.

        Args:
            component_id: Component ID
            geometry_type: 'reduced' or 'detailed'
            meshes: List of Rhino.Geometry.Mesh objects
            etag: ETag from server response
        """
        with self._lock:
            try:
                current_time = datetime.now().isoformat()
                cache_key = f'geometry:{geometry_type}:{component_id}'

                # Create geometry subdirectory
                geometry_subdir = os.path.join(
                    self.geometry_dir, geometry_type
                )
                os.makedirs(geometry_subdir, exist_ok=True)

                # Convert meshes to JSON strings using ToJSON
                mesh_json_strings = []
                for mesh in meshes:
                    # Use ToJSON with SerializationOptions to include user data
                    options = Rhino.FileIO.SerializationOptions()
                    options.WriteUserData = True
                    options.WriteRenderMeshes = True
                    options.WriteAnalysisMeshes = True

                    json_string = mesh.ToJSON(options)
                    mesh_json_strings.append(json_string)

                # Store JSON strings as pickle
                geometry_file = os.path.join(
                    geometry_subdir, f"{component_id}.pkl"
                )
                with open(geometry_file, 'wb') as f:
                    pickle.dump(mesh_json_strings, f)

                # Store metadata
                metadata = {
                    'cache_key': cache_key,
                    'cached_at': current_time,
                    'etag': etag,
                    'type': 'geometry',
                    'geometry_type': geometry_type,
                    'component_id': component_id
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

    def _convert_obj_to_meshes(self, obj_content):
        """
        Convert OBJ file content to list of Rhino.Geometry.Mesh objects.
        Optimized version with improved performance for large files.
        Supports multiple objects (o object_0, o object_1, etc.) and
        v X Y Z R G B format with RGB integer colors.
        Returns list of mesh objects or empty list if conversion fails.
        """
        try:
            if not obj_content or not obj_content.strip():
                return []

            # Pre-allocate data structures for better performance
            meshes = []
            global_vertices = []
            global_normals = []
            global_vertex_colors = []

            # Current mesh data
            current_mesh_data = {
                'vertices': [],
                'faces': [],
                'normals': [],
                'vertex_colors': [],
                'name': 'default'
            }

            # Parse lines more efficiently
            lines = obj_content.splitlines()

            # Pre-process lines to avoid repeated string operations
            processed_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split()
                    if parts:
                        processed_lines.append(parts)

            # Process lines without excessive logging
            for i, parts in enumerate(processed_lines):
                if parts[0] == 'o':  # object declaration
                    # Save previous mesh if it exists
                    if (current_mesh_data['vertices'] and
                            current_mesh_data['faces']):
                        mesh = self._create_mesh_from_data(current_mesh_data)
                        if mesh:
                            meshes.append(mesh)

                    # Start new mesh
                    current_mesh_data = {
                        'vertices': [],
                        'faces': [],
                        'normals': [],
                        'vertex_colors': [],
                        'name': (parts[1] if len(parts) > 1
                                 else f'object_{len(meshes)}')
                    }

                elif parts[0] == 'v':  # vertex
                    if len(parts) >= 4:
                        # Use tuple instead of Point3d for better performance
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        vertex = (x, y, z)
                        global_vertices.append(vertex)
                        current_mesh_data['vertices'].append(vertex)

                        # Check for vertex colors in v X Y Z R G B format
                        if len(parts) >= 7:
                            # Extract RGB integer values
                            r = int(parts[4])
                            g = int(parts[5])
                            b = int(parts[6])
                            color = (r, g, b)
                            global_vertex_colors.append(color)
                            current_mesh_data['vertex_colors'].append(color)
                        else:
                            # No color data, use default white
                            color = (255, 255, 255)
                            global_vertex_colors.append(color)
                            current_mesh_data['vertex_colors'].append(color)

                elif parts[0] == 'vn':  # vertex normal
                    if len(parts) >= 4:
                        nx = float(parts[1])
                        ny = float(parts[2])
                        nz = float(parts[3])
                        normal = (nx, ny, nz)
                        global_normals.append(normal)
                        current_mesh_data['normals'].append(normal)

                elif parts[0] == 'f':  # face
                    if len(parts) >= 4:
                        # Optimized face processing
                        face_vertices = []
                        for i in range(1, len(parts)):
                            # Handle different OBJ face formats
                            # (v, v/vt, v//vn, v/vt/vn)
                            vertex_part = parts[i].split('/')[0]
                            if vertex_part:
                                # OBJ is 1-indexed, convert to 0-indexed
                                vertex_index = int(vertex_part) - 1
                                if 0 <= vertex_index < len(global_vertices):
                                    # Use direct local index calculation
                                    vertices_len = len(
                                        current_mesh_data['vertices']
                                    )
                                    local_index = (
                                        vertex_index -
                                        (len(global_vertices) - vertices_len)
                                    )
                                    if (0 <= local_index < len(
                                            current_mesh_data['vertices'])):
                                        face_vertices.append(local_index)
                        if len(face_vertices) >= 3:
                            current_mesh_data['faces'].append(face_vertices)

            # Handle the last mesh
            if (current_mesh_data['vertices'] and
                    current_mesh_data['faces']):
                mesh = self._create_mesh_from_data(current_mesh_data)
                if mesh:
                    meshes.append(mesh)

            # If no objects were found, treat as single mesh
            # (backward compatibility)
            if not meshes and global_vertices:
                # Collect all faces from the global context
                global_faces = []
                for line in lines:
                    line = line.strip()
                    if (not line or line.startswith('#') or
                            line.startswith('o')):
                        continue
                    parts = line.split()
                    if not parts or parts[0] != 'f':
                        continue
                    if len(parts) >= 4:
                        face_vertices = []
                        for i in range(1, len(parts)):
                            vertex_part = parts[i].split('/')[0]
                            if vertex_part:
                                vertex_index = int(vertex_part) - 1
                                if 0 <= vertex_index < len(global_vertices):
                                    face_vertices.append(vertex_index)
                        if len(face_vertices) >= 3:
                            global_faces.append(face_vertices)

                if global_faces:
                    single_mesh = Rhino.Geometry.Mesh()
                    self._finalize_mesh(single_mesh, global_vertices,
                                        global_faces, global_normals,
                                        global_vertex_colors)
                    meshes.append(single_mesh)

            if not meshes:
                return []

            return meshes

        except Exception as e:
            self._addError(
                f"Error converting OBJ to meshes: {str(e)}")
            return []

    def _create_mesh_from_data(self, mesh_data):
        """
        Optimized method to create a Rhino mesh from pre-processed data.
        Uses bulk operations for better performance.
        """
        try:
            vertices = mesh_data['vertices']
            faces = mesh_data['faces']
            normals = mesh_data['normals']
            vertex_colors = mesh_data['vertex_colors']

            if not vertices or not faces:
                return None

            # Create mesh
            mesh = Rhino.Geometry.Mesh()

            # Convert tuples to Point3d objects in bulk
            point3d_vertices = []
            for x, y, z in vertices:
                point3d_vertices.append(Rhino.Geometry.Point3d(x, y, z))

            # Add vertices in bulk
            mesh.Vertices.AddVertices(point3d_vertices)

            # Add faces efficiently
            for face in faces:
                if len(face) == 3:
                    mesh.Faces.AddFace(face[0], face[1], face[2])
                elif len(face) == 4:
                    mesh.Faces.AddFace(face[0], face[1], face[2], face[3])
                else:
                    # Triangulate polygon faces
                    for i in range(1, len(face) - 1):
                        mesh.Faces.AddFace(face[0], face[i], face[i + 1])

            # Add normals if available
            if normals and len(normals) == len(vertices):
                mesh.Normals.Clear()
                for nx, ny, nz in normals:
                    mesh.Normals.Add(Rhino.Geometry.Vector3d(nx, ny, nz))
                mesh.Normals.ComputeNormals()
            else:
                mesh.Normals.ComputeNormals()

            # Add vertex colors if available
            if vertex_colors and len(vertex_colors) == len(vertices):
                for r, g, b in vertex_colors:
                    mesh.VertexColors.Add(r, g, b)

            # Apply coordinate system transformation
            mesh.Rotate(
                (math.pi / 2),
                Rhino.Geometry.Plane.WorldXY.XAxis,
                Rhino.Geometry.Point3d(0, 0, 0)
            )

            # Set mesh name
            mesh.UserDictionary.Set('Name', mesh_data['name'])

            # Compute mesh properties
            mesh.Compact()

            return mesh

        except Exception as e:
            self._addError(
                f"Error creating mesh from data: {str(e)}")
            return None

    def _finalize_mesh(self, mesh, vertices, faces, normals, vertex_colors):
        """
        Helper method to finalize a mesh with vertices, faces, normals,
        and colors.
        """
        try:
            # Add vertices
            for vertex in vertices:
                mesh.Vertices.Add(vertex)

            # Add faces
            for face in faces:
                if len(face) == 3:
                    mesh.Faces.AddFace(face[0], face[1], face[2])
                elif len(face) == 4:
                    mesh.Faces.AddFace(face[0], face[1], face[2], face[3])
                else:
                    # Triangulate polygon faces
                    for i in range(1, len(face) - 1):
                        mesh.Faces.AddFace(face[0], face[i], face[i + 1])

            # Add normals if available
            if normals and len(normals) == len(vertices):
                mesh.Normals.Clear()
                for normal in normals:
                    mesh.Normals.Add(normal)
                mesh.Normals.ComputeNormals()
            else:
                mesh.Normals.ComputeNormals()

            # Add vertex colors if available
            if vertex_colors and len(vertex_colors) == len(vertices):
                for color in vertex_colors:
                    r, g, b = color
                    mesh.VertexColors.Add(r, g, b)

            # rotate around x-axis to normalize for Rhino
            mesh.Rotate(
                (math.pi / 2),
                Rhino.Geometry.Plane.WorldXY.XAxis,
                Rhino.Geometry.Point3d(0, 0, 0)
            )
            # Compute mesh properties
            mesh.Compact()

        except Exception as e:
            self._addError(
                f"Error finalizing mesh: {str(e)}")
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
            # Not modified - return cached data
            # Create a mock response with cached data
            class MockResponse:
                def __init__(self, data, etag):
                    self.status_code = 200
                    self._data = data
                    self._etag = etag

                def json(self):
                    return self._data

                @property
                def headers(self):
                    return {'ETag': self._etag} if self._etag else {}

            return MockResponse(cached_data, cached_etag)

        elif response.status_code == 200:
            # Data changed or first request - cache the response
            try:
                data = response.json()
                etag = response.headers.get('ETag')
                self._cache.set(cache_key, data, etag, params)
            except (ValueError, KeyError):
                # If we can't parse JSON or cache, just return response
                pass

        return response

    def cached_get_geometry(self, component_id, geometry_type, timeout=60):
        """
        Make a cached GET request for geometry with ETag support.

        Args:
            component_id: Component ID
            geometry_type: 'reduced' or 'detailed'
            timeout: Request timeout

        Returns:
            Response object with geometry data
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        # If cache is disabled, make regular request
        if not self._cache:
            path = f'/components/{component_id}/geometry_{geometry_type}'
            return self.authorized_get(path, timeout=timeout)

        # Check binary cache first
        (cached_meshes,
         cached_etag,
         is_from_binary_cache) = self._cache.get_geometry_binary(
            component_id, geometry_type)

        # Prepare headers
        headers = self.auth_header()

        # Add conditional request header if we have cached data
        if is_from_binary_cache and cached_etag:
            headers['If-None-Match'] = cached_etag

        # Make request
        path = f'/components/{component_id}/geometry_{geometry_type}'
        response = requests.get(
            self.base_url + path,
            headers=headers,
            timeout=timeout
        )

        # Handle response
        if response.status_code == 304 and is_from_binary_cache:
            # Not modified - return cached data as OBJ text
            # Convert cached meshes back to OBJ for compatibility
            try:
                obj_text = self._convert_meshes_to_obj(cached_meshes)
            except Exception:
                # Fallback: return empty OBJ
                obj_text = "# No geometry data available"

            class MockResponse:
                def __init__(self, data, etag):
                    self.status_code = 200
                    self._data = data
                    self._etag = etag

                @property
                def text(self):
                    return self._data

                @property
                def headers(self):
                    return {'ETag': self._etag} if self._etag else {}

            return MockResponse(obj_text, cached_etag)

        elif response.status_code == 200:
            # Data changed or first request - cache the response
            try:
                geometry_data = response.text
                etag = response.headers.get('ETag')
                # Use the updated set_geometry method which converts to binary
                self._cache.set_geometry(
                    component_id, geometry_type, geometry_data, etag
                )
            except (ValueError, KeyError):
                # If we can't cache, just return response
                pass

        return response

    def get_component_schema(self, force_refresh=False):
        """
        Get component schema with caching support.

        Args:
            force_refresh: Force refresh of schema even if cached

        Returns:
            Component schema dictionary or None if failed
        """
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )

        # If cache is disabled, make regular request
        # (schema endpoint is unprotected)
        if not self._cache:
            try:
                response = requests.get(f'{self.base_url}/schema/component')
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception:
                return None

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_schema, cached_etag, is_from_cache = self._cache.get(
                'schema:component')
            if is_from_cache:
                return cached_schema

        # Make request to get schema (unprotected endpoint)
        try:
            # Prepare headers for conditional request
            headers = {}
            if not force_refresh:
                cached_schema, cached_etag, is_from_cache = self._cache.get(
                    'schema:component')
                if is_from_cache and cached_etag:
                    headers['If-None-Match'] = cached_etag

            response = requests.get(f'{self.base_url}/schema/component',
                                    headers=headers)

            if response.status_code == 304 and not force_refresh:
                # Not modified - return cached data
                cached_schema, _, is_from_cache = self._cache.get(
                    'schema:component')
                if is_from_cache:
                    return cached_schema

            elif response.status_code == 200:
                # Data changed or first request - cache the response
                try:
                    data = response.json()
                    etag = response.headers.get('ETag')
                    self._cache.set('schema:component', data, etag)
                    return data
                except (ValueError, KeyError):
                    return None

            return None
        except Exception:
            # If request fails and we have cached schema, return cached version
            if not force_refresh:
                cached_schema, _, is_from_cache = self._cache.get(
                    'schema:component')
                if is_from_cache:
                    return cached_schema
            return None

    def _convert_meshes_to_obj(self, meshes):
        """
        Convert Rhino.Geometry.Mesh objects to OBJ file content.
        This is used for compatibility when returning cached binary data
        as OBJ text.
        """
        try:
            if not meshes:
                return "# No geometry data available"

            obj_lines = []
            vertex_offset = 0

            for mesh_idx, mesh in enumerate(meshes):
                # Add object declaration
                obj_lines.append(f"o object_{mesh_idx}")

                # Add vertices
                for i in range(mesh.Vertices.Count):
                    vertex = mesh.Vertices[i]
                    obj_lines.append(f"v {vertex.X} {vertex.Y} {vertex.Z}")

                # Add vertex colors if available
                if mesh.VertexColors.Count > 0:
                    for i in range(mesh.Vertices.Count):
                        if i < mesh.VertexColors.Count:
                            color = mesh.VertexColors[i]
                            obj_lines.append(
                                f"v {mesh.Vertices[i].X} "
                                f"{mesh.Vertices[i].Y} "
                                f"{mesh.Vertices[i].Z} "
                                f"{color.R} {color.G} {color.B}"
                            )
                        else:
                            vertex = mesh.Vertices[i]
                            obj_lines.append(
                                f"v {vertex.X} {vertex.Y} {vertex.Z}"
                            )

                # Add faces (adjust indices for OBJ format)
                for i in range(mesh.Faces.Count):
                    face = mesh.Faces[i]
                    if face.IsTriangle:
                        obj_lines.append(
                            f"f {face.A + vertex_offset + 1} "
                            f"{face.B + vertex_offset + 1} "
                            f"{face.C + vertex_offset + 1}"
                        )
                    elif face.IsQuad:
                        obj_lines.append(
                            f"f {face.A + vertex_offset + 1} "
                            f"{face.B + vertex_offset + 1} "
                            f"{face.C + vertex_offset + 1} "
                            f"{face.D + vertex_offset + 1}"
                        )

                vertex_offset += mesh.Vertices.Count

            return "\n".join(obj_lines)

        except Exception as e:
            return f"# Error converting meshes to OBJ: {str(e)}"


# SignIn Grasshopper Component ------------------------------------------------

class CSC_SignIn(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    """

    # Development setting - do not change!
    __HARD_RESET = False

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

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
            DisableCache,
            ClearCache):
        # Initialize param descriptions (this has to be done in RunScript)
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

                    # Fetch and cache component schema
                    try:
                        schema = auth_core.get_component_schema()
                        if schema:
                            status_messages.append(
                                'Schema cached successfully')
                            self._addRemark('Schema cached successfully')
                        else:
                            status_messages.append('Failed to cache schema')
                            self._addWarning('Failed to cache schema')
                    except Exception as e:
                        status_messages.append(
                            f'Schema caching failed: {str(e)}')
                        self._addWarning(f'Schema cache failed: {str(e)}')

                    # Get cache status for output
                    cache_stats = auth_core.get_cache_stats()
                    cache_enabled = auth_core.is_cache_enabled()
                    comp_count = cache_stats["component_count"]
                    geometry_count = cache_stats["geometry_count"]
                    size_kb = cache_stats["total_size_bytes"] // 1024
                    geometry_size_kb = (
                        cache_stats["geometry_size_bytes"] // 1024
                    )

                    # Add cache status to messages
                    cache_status = (
                        f'Cache: {"Enabled" if cache_enabled else "Disabled"}\n'
                        f' | Components: {comp_count}\n'
                        f' | Geometry: {geometry_count} files\n'
                        f' | Size: {size_kb} kB\n'
                        f' | Geometry: {geometry_size_kb} kB\n')
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

                    # Fetch and cache component schema
                    try:
                        schema = auth_core.get_component_schema()
                        if schema:
                            status_messages.append(
                                'Schema cached successfully')
                            self._addRemark('Schema cached successfully')
                        else:
                            status_messages.append('Failed to cache schema')
                            self._addWarning('Failed to cache schema')
                    except Exception as e:
                        status_messages.append(
                            f'Schema caching failed: {str(e)}')
                        self._addWarning(f'Schema cache failed: {str(e)}')

                    # Get cache status for output
                    cache_stats = auth_core.get_cache_stats()
                    cache_enabled = auth_core.is_cache_enabled()
                    comp_count = cache_stats["component_count"]
                    geometry_count = cache_stats["geometry_count"]
                    size_kb = cache_stats["total_size_bytes"] // 1024
                    geometry_size_kb = (
                        cache_stats["geometry_size_bytes"] // 1024
                    )

                    # Add cache status to messages
                    cache_status = (
                        f'Cache: {"Enabled" if cache_enabled else "Disabled"}\n'
                        f' | Components: {comp_count}\n'
                        f' | Geometry: {geometry_count} files\n'
                        f' | Size: {size_kb} kB\n'
                        f' | Geometry: {geometry_size_kb} kB\n')
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
