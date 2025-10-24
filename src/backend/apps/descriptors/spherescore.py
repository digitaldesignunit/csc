#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import trimesh


# FUNCTION DEFINITIONS --------------------------------------------------------


def compute_spherescore(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> float:
    """
    Compute the SphereScore for a correctly oriented mesh.

    Args:
        mesh: trimesh.Trimesh object (must be correctly oriented)
        factor: scaling factor for the score (default 100.0, must be >= 100)

    Returns:
        score: SphereScore value (optimal value is 0)

    Raises:
        ValueError: if mesh is invalid or factor < 100
    """
    spherescore_data = compute_spherescore_with_metadata(mesh, factor)
    return spherescore_data['score']


def compute_spherescore_with_metadata(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> Dict[str, float]:
    """
    Compute SphereScore with additional metadata.

    Args:
        mesh: trimesh.Trimesh object (must be correctly oriented)
        factor: scaling factor for the score (default 100.0)

    Returns:
        dictionary containing:
            - score: SphereScore value
            - vsphere: minimum n-sphere volume
            - vhull: convex hull volume
            - factor: scaling factor used

    Raises:
        ValueError: if mesh is invalid or computation fails
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
    vhull = hull.volume
    # Compute sphere
    try:
        sphere = trimesh.nsphere.minimum_nsphere(mesh.vertices)
    except Exception as e:
        raise ValueError(f'Failed to compute minimum n-sphere: {e}')
    vsphere = sphere.volume
    if (vhull > vsphere):
        vhull = 0
    # Compute SphereScore
    score = abs((vsphere - vhull) / vsphere * factor)
    # Return results
    return {
        'score': float(score),
        'vsphere': float(vsphere),
        'vhull': float(vhull),
        'factor': float(factor)
    }
