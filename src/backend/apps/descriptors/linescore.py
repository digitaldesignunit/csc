"""
Linescore descriptor computation for meshes.

The linescore measures how well a line abstracts an object by comparing
the two smallest dimensions to the largest dimension of the oriented
bounding box.
"""
import trimesh
from typing import Dict


def compute_linescore(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> float:
    """
    Compute the linescore for a mesh.

    The linescore is calculated based on the oriented bounding box dimensions:
    - height: smallest dimension
    - width: middle dimension
    - length: largest dimension

    ratio_a = height / length
    ratio_b = width / length
    score = max(ratio_a, ratio_b) * factor

    Args:
        mesh: trimesh.Trimesh object (should be properly oriented)
        factor: scaling factor for the score (default: 100.0)

    Returns:
        float: linescore value

    Raises:
        ValueError: if mesh has no volume or invalid bounding box
    """
    if len(mesh.vertices) == 0:
        raise ValueError('Mesh has no vertices')
    if len(mesh.faces) == 0:
        raise ValueError('Mesh has no faces')

    # Get oriented bounding box
    obb = mesh.bounding_box_oriented

    # Get the extents (dimensions) of the bounding box
    extents = obb.primitive.extents  # [x, y, z] dimensions

    # Sort to get height (smallest), width (middle), length (largest)
    sorted_extents = sorted(extents)
    height = sorted_extents[0]
    width = sorted_extents[1]
    length = sorted_extents[2]

    # Avoid division by zero
    if length == 0:
        raise ValueError('Bounding box has zero dimension')

    # Calculate ratios
    ratio_a = height / length
    ratio_b = width / length

    # Compute score
    if ratio_a > ratio_b:
        score = ratio_a * factor
    else:
        score = ratio_b * factor

    return score


def compute_linescore_with_metadata(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> Dict[str, float]:
    """
    Compute the linescore with additional metadata.

    Returns the score along with the bounding box dimensions and ratios.

    Args:
        mesh: trimesh.Trimesh object (should be properly oriented)
        factor: scaling factor for the score (default: 100.0)

    Returns:
        dict: {
            'score': linescore value,
            'height': smallest bounding box dimension,
            'width': middle bounding box dimension,
            'length': largest bounding box dimension,
            'ratio_a': height / length,
            'ratio_b': width / length,
            'factor': scaling factor used
        }

    Raises:
        ValueError: if mesh has no volume or invalid bounding box
    """
    if len(mesh.vertices) == 0:
        raise ValueError('Mesh has no vertices')
    if len(mesh.faces) == 0:
        raise ValueError('Mesh has no faces')

    # Get oriented bounding box
    obb = mesh.bounding_box_oriented

    # Get the extents (dimensions) of the bounding box
    extents = obb.primitive.extents

    # Sort to get height (smallest), width (middle), length (largest)
    sorted_extents = sorted(extents)
    height = sorted_extents[0]
    width = sorted_extents[1]
    length = sorted_extents[2]

    # Avoid division by zero
    if length == 0:
        raise ValueError('Bounding box has zero dimension')

    # Calculate ratios
    ratio_a = height / length
    ratio_b = width / length

    # Compute score
    score = compute_linescore(mesh, factor=factor)

    return {
        'score': float(score),
        'height': float(height),
        'width': float(width),
        'length': float(length),
        'ratio_a': float(ratio_a),
        'ratio_b': float(ratio_b),
        'factor': float(factor)
    }
