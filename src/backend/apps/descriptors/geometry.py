#!/usr/bin/env python3.9
"""
Geometry utilities for descriptor computation.

This module provides functions to:
1. Load meshes from primitive format (component.json)
2. Load meshes from OBJ files (with coordinate system conversion)
3. Apply PCA frame transformations to align meshes with principal axes
4. Convert between coordinate systems (Rhino <-> OBJ)

Coordinate Systems:
- Rhino: X=right, Y=back, Z=up
- OBJ (as saved): X=right, Y=up, Z=forward
- Transformation: Rhino(X,Y,Z) -> OBJ(X,Z,-Y)
- Reverse: OBJ(X,Y,Z) -> Rhino(X,-Z,Y)
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Tuple, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import trimesh


# FUNCTION DEFINITIONS --------------------------------------------------------

def load_mesh_from_primitive(
    vertices: List[List[float]],
    faces: List[List[int]]
) -> trimesh.Trimesh:
    """
    Load a mesh from primitive format (component.json format).

    Primitive meshes are stored in Rhino coordinate system and are already
    centered at the origin.

    Args:
        vertices: List of [x, y, z] vertex coordinates in Rhino coordinates
        faces: List of face vertex indices (triangles or quads)

    Returns:
        trimesh.Trimesh object in Rhino coordinate system

    Raises:
        ValueError: if vertices or faces are invalid
    """
    if not vertices or len(vertices) == 0:
        raise ValueError('Vertices list is empty')
    if not faces or len(faces) == 0:
        raise ValueError('Faces list is empty')

    # Convert to numpy arrays
    verts = np.array(vertices, dtype=np.float64)
    faces_array = np.array(faces, dtype=np.int32)

    # Validate vertex dimensions
    if verts.shape[1] != 3:
        raise ValueError(
            f'Vertices must be [x, y, z] triplets, got shape {verts.shape}'
        )

    # Validate face indices
    if not np.all((faces_array >= 0) & (faces_array < len(verts))):
        raise ValueError('Face indices out of bounds')

    # Handle quads by triangulating
    triangulated_faces = []
    for face in faces_array:
        if len(face) == 3:
            # Already a triangle
            triangulated_faces.append(face)
        elif len(face) == 4:
            # Quad - split into two triangles
            triangulated_faces.append([face[0], face[1], face[2]])
            triangulated_faces.append([face[0], face[2], face[3]])
        else:
            raise ValueError(
                f'Faces must be triangles (3 vertices) or '
                f'quads (4 vertices), got {len(face)} vertices'
            )

    triangulated_faces = np.array(triangulated_faces, dtype=np.int32)

    # Create trimesh object
    try:
        mesh = trimesh.Trimesh(vertices=verts, faces=triangulated_faces)
    except Exception as e:
        raise ValueError(f'Failed to create mesh: {e}')

    return mesh


def create_mesh_from_extrusion(
    profile: List[List[float]],
    height: float
) -> trimesh.Trimesh:
    """
    Create a 3D mesh from an extrusion profile.

    Creates a solid mesh by extruding a 2D profile polygon along the Z axis.
    The mesh includes:
    - Bottom face (at Z=0)
    - Top face (at Z=height)
    - Side faces connecting bottom and top

    Args:
        profile: List of [x, y] coordinates defining the profile polygon
        height: Extrusion height (Z direction)

    Returns:
        trimesh.Trimesh object representing the extruded solid

    Raises:
        ValueError: if profile or height are invalid
    """
    if not profile or len(profile) < 3:
        raise ValueError(
            f'Profile must have at least 3 points, got {len(profile)}'
        )
    if height <= 0:
        raise ValueError(f'Height must be positive, got {height}')

    # Convert profile to numpy array
    profile_array = np.array(profile, dtype=np.float64)

    # Validate profile dimensions
    if profile_array.shape[1] != 2:
        raise ValueError(
            f'Profile points must be [x, y] pairs, '
            f'got shape {profile_array.shape}'
        )

    num_points = len(profile_array)

    # Create bottom vertices (Z=-height/2)
    bottom_vertices = np.hstack([
        profile_array,
        np.full((num_points, 1), -height/2)
    ])

    # Create top vertices (Z=height/2)
    top_vertices = np.hstack([
        profile_array,
        np.full((num_points, 1), height/2)
    ])

    # Combine all vertices
    vertices = np.vstack([bottom_vertices, top_vertices])

    # Create faces
    faces = []

    # Side faces (quads split into two triangles)
    for i in range(num_points):
        next_i = (i + 1) % num_points

        # Bottom vertex indices
        bottom_curr = i
        bottom_next = next_i

        # Top vertex indices (offset by num_points)
        top_curr = i + num_points
        top_next = next_i + num_points

        # Create two triangles for this quad
        # Triangle 1: bottom_curr, bottom_next, top_next
        faces.append([bottom_curr, bottom_next, top_next])
        # Triangle 2: bottom_curr, top_next, top_curr
        faces.append([bottom_curr, top_next, top_curr])

    # Bottom face (triangulate the polygon)
    # Use simple fan triangulation from first vertex
    if num_points > 2:
        for i in range(1, num_points - 1):
            faces.append([0, i, i + 1])

    # Top face (triangulate the polygon)
    # Use simple fan triangulation from first vertex (reversed winding)
    if num_points > 2:
        for i in range(1, num_points - 1):
            # Reverse winding for top face (offset by num_points)
            faces.append([
                num_points,
                num_points + i + 1,
                num_points + i
            ])

    faces_array = np.array(faces, dtype=np.int32)

    # Create trimesh object
    try:
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces_array)
    except Exception as e:
        raise ValueError(f'Failed to create mesh from extrusion: {e}')

    return mesh


def load_mesh_from_obj(
    filepath: str,
    use_first_only: bool = False
) -> trimesh.Trimesh:
    """
    Load a mesh from an OBJ file and convert to Rhino coordinate system.

    OBJ files saved by CreateComponent use the transformation:
    Rhino(X,Y,Z) -> OBJ(X,Z,-Y)

    This function reverses that transformation:
    OBJ(X,Y,Z) -> Rhino(X,-Z,Y)

    Args:
        filepath: path to .obj file
        use_first_only: if True and OBJ contains multiple objects,
                        only use the first object. If False, concatenate
                        all objects. Default False (concatenate).

    Returns:
        trimesh.Trimesh object in Rhino coordinate system (centered)

    Raises:
        FileNotFoundError: if file doesn't exist
        ValueError: if file is not a valid mesh
    """
    try:
        # Load mesh using trimesh (handles OBJ format natively)
        loaded = trimesh.load(filepath)
    except FileNotFoundError:
        raise FileNotFoundError(f'OBJ file not found: {filepath}')
    except Exception as e:
        raise ValueError(f'Failed to load OBJ file {filepath}: {e}')

    # Handle Scene (multiple objects) vs single Trimesh
    if isinstance(loaded, trimesh.Scene):
        if use_first_only:
            # Get only the first mesh from the scene
            # NOTE: trimesh loads OBJ objects in REVERSE order, so the last
            # item in the geometry dict is actually the first object saved
            if len(loaded.geometry) == 0:
                raise ValueError(f'OBJ file contains no geometry: {filepath}')
            mesh = list(loaded.geometry.values())[-1]
        else:
            # Concatenate all meshes in the scene
            mesh = loaded.dump(concatenate=True)
    else:
        mesh = loaded

    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(
            f'File {filepath} is not a triangle mesh. '
            f'Got type: {type(mesh)}'
        )

    if len(mesh.vertices) == 0:
        raise ValueError(f'Mesh has no vertices: {filepath}')
    if len(mesh.faces) == 0:
        raise ValueError(f'Mesh has no faces: {filepath}')

    # Convert from OBJ coordinate system to Rhino coordinate system
    # OBJ(X,Y,Z) -> Rhino(X,-Z,Y)
    vertices = mesh.vertices.copy()
    rhino_vertices = np.zeros_like(vertices)
    rhino_vertices[:, 0] = vertices[:, 0]  # X stays the same
    rhino_vertices[:, 1] = -vertices[:, 2]  # -Z becomes Y
    rhino_vertices[:, 2] = vertices[:, 1]   # Y becomes Z

    # Create new mesh in Rhino coordinates
    mesh_rhino = trimesh.Trimesh(
        vertices=rhino_vertices,
        faces=mesh.faces.copy()
    )

    return mesh_rhino


def apply_pca_frame_transform(
    mesh: trimesh.Trimesh,
    pca_frame: Dict[str, List[float]]
) -> trimesh.Trimesh:
    """
    Apply PCA frame transformation to align mesh with principal axes.

    This replicates Rhino's Transform.PlaneToPlane(pca_plane, WorldXY)
    which transforms FROM pca_plane TO WorldXY.

    The transformation works as follows:
    1. Start with mesh in PCA-oriented space (where it was created)
    2. Transform it to world XYZ axes (aligning PCA axes with world axes)

    Result: A centered mesh where PCA principal axes align with world XYZ,
    making the longest dimension align with X, second with Y, shortest with Z.

    Args:
        mesh: trimesh.Trimesh object (should be centered at origin)
        pca_frame: dictionary with keys 'o', 'x', 'y', 'z' containing
                   origin point and axis vectors as [x, y, z] lists

    Returns:
        trimesh.Trimesh object aligned with world axes via PCA orientation

    Raises:
        ValueError: if pca_frame is invalid
    """
    # Validate pca_frame
    required_keys = ['o', 'x', 'y', 'z']
    for key in required_keys:
        if key not in pca_frame:
            raise ValueError(f'pca_frame missing required key: {key}')
        if len(pca_frame[key]) != 3:
            raise ValueError(
                f'pca_frame[{key}] must be [x, y, z], '
                f'got length {len(pca_frame[key])}'
            )
    # Extract frame components
    origin = np.array(pca_frame['o'], dtype=np.float64)
    x_axis = np.array(pca_frame['x'], dtype=np.float64)
    y_axis = np.array(pca_frame['y'], dtype=np.float64)
    z_axis = np.array(pca_frame['z'], dtype=np.float64)
    # Normalize axes (ensure they are unit vectors)
    x_axis_norm = np.linalg.norm(x_axis)
    y_axis_norm = np.linalg.norm(y_axis)
    z_axis_norm = np.linalg.norm(z_axis)
    if x_axis_norm < 1e-10 or y_axis_norm < 1e-10 or z_axis_norm < 1e-10:
        raise ValueError('PCA frame axes must be non-zero')
    x_axis = x_axis / x_axis_norm
    y_axis = y_axis / y_axis_norm
    z_axis = z_axis / z_axis_norm
    # Build the transformation to align mesh with PCA axes
    # We want to rotate the mesh so that PCA axes become world XYZ axes
    #
    # The mesh is currently in world coordinates
    # PCA frame defines axes in world coordinates
    # We want: PCA X -> World X, PCA Y -> World Y, PCA Z -> World Z
    #
    # This means we need to express world points in the PCA basis
    # The transformation is: T = inv(T_pca) where T_pca has PCA axes
    # as columns
    #
    # T_pca = [x_axis | y_axis | z_axis | origin]
    #         [  0       0        0        1    ]
    #
    # Since the axes are orthonormal, inv(T_pca) rotates world coords
    # to align with PCA frame

    # Build PCA frame transformation matrix (world -> PCA frame basis)
    # When PCA axes are orthonormal, rotation part is just the transpose
    pca_rotation = np.column_stack([x_axis, y_axis, z_axis])
    # Full transformation matrix
    pca_transform = np.eye(4)
    pca_transform[:3, :3] = pca_rotation.T  # Transpose for world->PCA
    pca_transform[:3, 3] = -pca_rotation.T @ origin  # Transform origin
    # Apply transformation to mesh
    mesh_transformed = mesh.copy()
    mesh_transformed.apply_transform(pca_transform)
    return mesh_transformed


def center_mesh(mesh: trimesh.Trimesh) -> Tuple[trimesh.Trimesh, np.ndarray]:
    """
    Center a mesh at the origin using its centroid.

    Args:
        mesh: trimesh.Trimesh object

    Returns:
        Tuple of:
        - centered mesh (trimesh.Trimesh)
        - translation vector applied (numpy array [x, y, z])
    """
    # Compute centroid
    centroid = mesh.centroid

    # Create translation vector (negative to move to origin)
    translation = -centroid

    # Apply translation
    mesh_centered = mesh.copy()
    mesh_centered.apply_translation(translation)

    return mesh_centered, translation


def prepare_mesh_for_descriptor(
    mesh: trimesh.Trimesh,
    pca_frame: Optional[Dict[str, List[float]]] = None,
    center: bool = True
) -> trimesh.Trimesh:
    """
    Prepare a mesh for descriptor computation.

    This is a convenience function that:
    1. Centers the mesh (if requested)
    2. Applies PCA frame transformation (if provided)

    Args:
        mesh: trimesh.Trimesh object
        pca_frame: optional PCA frame dictionary to align mesh
        center: if True, center the mesh before applying PCA frame

    Returns:
        trimesh.Trimesh object ready for descriptor computation
    """
    prepared_mesh = mesh.copy()
    if pca_frame is not None:
        prepared_mesh = apply_pca_frame_transform(prepared_mesh, pca_frame)
    if center:
        prepared_mesh, _ = center_mesh(prepared_mesh)
    return prepared_mesh


def load_primitive_mesh_for_descriptor(
    vertices: List[List[float]],
    faces: List[List[int]],
    pca_frame: Optional[Dict[str, List[float]]] = None
) -> trimesh.Trimesh:
    """
    Load and prepare a primitive mesh for descriptor computation.

    Primitive meshes are already centered, so this function:
    1. Loads the mesh from primitive format
    2. Applies PCA frame transformation (if provided)

    Args:
        vertices: List of [x, y, z] vertex coordinates
        faces: List of face vertex indices
        pca_frame: optional PCA frame dictionary to align mesh

    Returns:
        trimesh.Trimesh object ready for descriptor computation
    """
    mesh = load_mesh_from_primitive(vertices, faces)
    if pca_frame is not None:
        mesh = apply_pca_frame_transform(mesh, pca_frame)
    return mesh


def load_obj_mesh_for_descriptor(
    filepath: str,
    pca_frame: Optional[Dict[str, List[float]]] = None,
    is_assembly: bool = True
) -> trimesh.Trimesh:
    """
    Load and prepare an OBJ mesh for descriptor computation.

    OBJ meshes saved by CreateComponent are already centered, so this function:
    1. Loads the mesh from OBJ file
    2. Converts coordinates from OBJ to Rhino
    3. Applies PCA frame transformation (if provided)

    Args:
        filepath: path to .obj file
        pca_frame: optional PCA frame dictionary to align mesh
        is_assembly: if True, concatenate all objects in OBJ. If False,
                     use only the first object. Default True.

    Returns:
        trimesh.Trimesh object ready for descriptor computation
    """
    mesh = load_mesh_from_obj(filepath, use_first_only=not is_assembly)
    if pca_frame is not None:
        mesh = apply_pca_frame_transform(mesh, pca_frame)
    return mesh


def load_extrusion_mesh_for_descriptor(
    profile: List[List[float]],
    height: float,
    pca_frame: Optional[Dict[str, List[float]]] = None
) -> trimesh.Trimesh:
    """
    Load and prepare an extrusion mesh for descriptor computation.

    Extrusions are already centered (created at origin), so this function:
    1. Creates mesh from extrusion profile and height
    2. Applies PCA frame transformation (if provided)

    Args:
        profile: List of [x, y] coordinates defining the profile polygon
        height: Extrusion height (Z direction)
        pca_frame: optional PCA frame dictionary to align mesh

    Returns:
        trimesh.Trimesh object ready for descriptor computation
    """
    mesh = create_mesh_from_extrusion(profile, height)
    if pca_frame is not None:
        mesh = apply_pca_frame_transform(mesh, pca_frame)
    return mesh
