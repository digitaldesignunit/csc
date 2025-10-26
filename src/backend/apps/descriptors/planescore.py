"""
Planescore descriptor computation for meshes.

The planescore measures how well a plane abstracts an object by comparing
the smallest dimension to the other dimensions of the oriented bounding box.
"""
import trimesh
from typing import Dict


def compute_planescore(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> float:
    """
    Compute the planescore for a mesh.

    The planescore is calculated based on the oriented bounding box dimensions:
    - height: smallest dimension
    - length: largest dimension
    - width: middle dimension

    ratio_a = height / length
    ratio_b = height / width
    score = max(ratio_a, ratio_b) * factor

    Args:
        mesh: trimesh.Trimesh object (should be properly oriented)
        factor: scaling factor for the score (default: 100.0)

    Returns:
        float: planescore value

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
    if length == 0 or width == 0:
        raise ValueError('Bounding box has zero dimension')

    # Calculate ratios
    ratio_a = height / length
    ratio_b = height / width

    # Compute score
    if ratio_a > ratio_b:
        score = ratio_a * factor
    else:
        score = ratio_b * factor

    return score


def compute_planescore_with_metadata(
    mesh: trimesh.Trimesh,
    factor: float = 100.0
) -> Dict[str, float]:
    """
    Compute the planescore with additional metadata.

    Returns the score along with the bounding box dimensions and ratios.

    Args:
        mesh: trimesh.Trimesh object (should be properly oriented)
        factor: scaling factor for the score (default: 100.0)

    Returns:
        dict: {
            'score': planescore value,
            'height': smallest bounding box dimension,
            'width': middle bounding box dimension,
            'length': largest bounding box dimension,
            'ratio_a': height / length,
            'ratio_b': height / width,
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
    if length == 0 or width == 0:
        raise ValueError('Bounding box has zero dimension')

    # Calculate ratios
    ratio_a = height / length
    ratio_b = height / width

    # Compute score
    score = compute_planescore(mesh, factor=factor)

    return {
        'score': float(score),
        'height': float(height),
        'width': float(width),
        'length': float(length),
        'ratio_a': float(ratio_a),
        'ratio_b': float(ratio_b),
        'factor': float(factor)
    }
