#!/usr/bin/env python3.9
"""
BoxScore computation for mesh shape characterization.

BoxScore measures how well an oriented bounding box abstracts/fits a mesh
by comparing the volume of the oriented bounding box to the volume of the
convex hull.

Formula:
    BoxScore = |(V_box - V_hull) / V_box * factor|

Where:
    - V_box: Volume of the oriented bounding box
    - V_hull: Volume of the convex hull
    - factor: Scaling factor (default 100)

An optimal BoxScore is 0, which occurs when the convex hull volume exactly
matches the oriented bounding box volume (i.e., the object is box-shaped).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import trimesh


# FUNCTION DEFINITIONS --------------------------------------------------------


def compute_boxscore(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> float:
    """
    Compute the BoxScore for a correctly oriented mesh.

    The BoxScore measures how well an oriented bounding box abstracts the mesh
    by comparing the OBB volume to the convex hull volume.

    Args:
        mesh: trimesh.Trimesh object (must be correctly oriented)
        factor: scaling factor for the score (default 100.0, must be >= 100)

    Returns:
        score: BoxScore value (optimal value is 0)

    Raises:
        ValueError: if mesh is invalid or factor < 100
    """
    if factor < 100:
        raise ValueError(f'Factor must be >= 100, got {factor}')

    if len(mesh.vertices) == 0:
        raise ValueError('Mesh has no vertices')
    if len(mesh.faces) == 0:
        raise ValueError('Mesh has no faces')

    # Compute convex hull
    try:
        hull = mesh.convex_hull
    except Exception as e:
        raise ValueError(f'Failed to compute convex hull: {e}')

    # Get hull volume
    vhull = hull.volume

    # Compute oriented bounding box
    try:
        obb = mesh.bounding_box_oriented
    except Exception as e:
        raise ValueError(f'Failed to compute oriented bounding box: {e}')

    # Get OBB volume
    vbox = obb.volume

    # Avoid division by zero
    if vbox == 0:
        raise ValueError('Oriented bounding box has zero volume')

    # Compute BoxScore
    score = abs((vbox - vhull) / vbox * factor)

    return score


def compute_boxscore_with_metadata(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> Dict[str, float]:
    """
    Compute BoxScore with additional metadata.

    Args:
        mesh: trimesh.Trimesh object (must be correctly oriented)
        factor: scaling factor for the score (default 100.0)

    Returns:
        dictionary containing:
            - score: BoxScore value
            - vbox: oriented bounding box volume
            - vhull: convex hull volume
            - factor: scaling factor used

    Raises:
        ValueError: if mesh is invalid or computation fails
    """
    # Compute convex hull and OBB
    hull = mesh.convex_hull
    obb = mesh.bounding_box_oriented

    # Get volumes
    vhull = hull.volume
    vbox = obb.volume

    # Compute score
    score = compute_boxscore(mesh, factor=factor)

    # Return results
    return {
        'score': float(score),
        'vbox': float(vbox),
        'vhull': float(vhull),
        'factor': float(factor)
    }
