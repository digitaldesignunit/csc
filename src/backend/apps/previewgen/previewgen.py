#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from io import BytesIO
import os
from typing import List, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image, ImageOps

# LOCAL MODULE IMPORTS --------------------------------------------------------
try:
    from utility import create_logging_timestamp as logts
except ImportError:
    print('Import Error: utility module not found, '
          'continuing without logging...')


# FUNCTION DEFINITIONS --------------------------------------------------------

def create_extrusion_mesh(extrusion: dict) -> Tuple[np.ndarray, list]:
    """Create a 3D mesh from one snapshot extrusion primitive."""
    points = np.array(extrusion['profile'])
    height = extrusion['height']
    num_points = len(points)
    points_3d_bottom = np.hstack([points, np.zeros((num_points, 1))])
    points_3d_top = points_3d_bottom.copy()
    points_3d_top[:, 2] = height
    all_points = np.vstack([points_3d_bottom, points_3d_top])
    faces = []
    for i in range(num_points):
        next_i = (i + 1) % num_points
        faces.append([
            points_3d_bottom[i],
            points_3d_bottom[next_i],
            points_3d_top[next_i],
            points_3d_top[i],
        ])
    faces.append(points_3d_bottom.tolist())
    faces.append(points_3d_top.tolist())
    return all_points, faces


def combine_snapshot_meshes(meshes: List[dict]):
    """Merge snapshot mesh primitives into arrays for rendering."""
    all_vertices = []
    all_faces = []
    all_vertex_colors = []
    all_faces_idx = []
    vertex_offset = 0

    for mesh_data in meshes:
        vertices = np.array(mesh_data['vertices'])
        vertex_colors = None
        if mesh_data.get('colors'):
            vertex_colors = np.array(mesh_data['colors'])

        faces_idx = mesh_data['faces']
        adjusted_faces_idx = [
            [idx + vertex_offset for idx in face] for face in faces_idx
        ]

        all_vertices.extend(vertices)
        all_faces.extend([
            [vertices[idx] for idx in face] for face in faces_idx
        ])
        all_faces_idx.extend(adjusted_faces_idx)

        if vertex_colors is not None:
            all_vertex_colors.extend(vertex_colors)

        vertex_offset += len(vertices)

    combined_vertices = np.array(all_vertices)
    combined_vertex_colors = (
        np.array(all_vertex_colors) if all_vertex_colors else None
    )
    return (
        combined_vertices,
        all_faces,
        combined_vertex_colors,
        all_faces_idx,
    )


def combine_extrusion_meshes(
    extrusions: List[dict],
) -> Tuple[np.ndarray, list]:
    """Combine multiple snapshot extrusion primitives into one renderable mesh."""
    all_vertices = []
    all_faces = []
    for extrusion in extrusions:
        vertices, faces = create_extrusion_mesh(extrusion)
        all_vertices.append(vertices)
        all_faces.extend(faces)
    combined_vertices = (
        np.vstack(all_vertices) if all_vertices else np.array([])
    )
    return combined_vertices, all_faces


def create_snapshot_preview_image(
        snapshot_data: dict,
        size: int = 800,
        dpi: int = 300) -> Image:

    geometry = snapshot_data.get('geometry', {})
    meshes = geometry.get('meshes') or []
    extrusions = geometry.get('extrusions') or []

    if meshes:
        (vertices, faces,
         vertex_colors,
         faces_idx) = combine_snapshot_meshes(meshes)
    elif extrusions:
        vertices, faces = combine_extrusion_meshes(extrusions)
        vertex_colors = None
        faces_idx = None
    else:
        raise ValueError(
            f'Snapshot {snapshot_data.get("_id")!r} has no supported '
            f'geometry for preview (expected meshes or extrusions, got keys: '
            f'{list(geometry.keys())})'
        )

    # If vertex colors are present, compute face colors by
    # averaging vertex colors per face
    if vertex_colors is not None and faces_idx is not None:
        face_colors = []
        for face in faces_idx:
            # Extract the vertex colors for this face
            fc = vertex_colors[face]
            # Average the vertex colors to get a single face color
            avg_color = np.mean(fc, axis=0)
            face_colors.append(avg_color)
        face_colors = np.array(face_colors) / 255.0
    else:
        # No vertex colors, use snapshot rendering color
        color = snapshot_data.get('color') or [110, 110, 110]
        face_colors = np.array(color) / 255.0

    # Calculate figsize based on image_size and dpi
    figsize = size / dpi
    # Create figure and 3D axis
    fig = plt.figure(
        figsize=(figsize, figsize),
        dpi=dpi,
        constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')

    # Create Poly3DCollection from faces
    # If we have multiple face colors, pass them as facecolors
    # Otherwise, it's just a single color for all faces
    if vertex_colors is not None and faces_idx is not None:
        # Multiple face colors
        poly3d = Poly3DCollection(faces, facecolors=face_colors,
                                  edgecolor='k', linewidths=0.2)
    else:
        # Single color for all faces
        poly3d = Poly3DCollection(
            faces,
            alpha=1.0,
            facecolor=face_colors,
            edgecolor='k',
            linewidths=0.2
        )
    ax.add_collection3d(poly3d)

    # Auto scale to the mesh size
    scale = vertices.flatten()
    ax.auto_scale_xyz(scale, scale, scale)
    ax.autoscale_view(tight=True)

    # Set plot parameters
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')

    # Set the camera view
    ax.view_init(elev=30., azim=45)

    # Adjust camera zoom
    ax.set_box_aspect(None, zoom=1)

    # Render the plot
    plt.axis('off')
    plt.grid(b=None)

    # Save to a BytesIO object
    buf = BytesIO()
    plt.savefig(
        buf,
        format='webp',
        bbox_inches='tight',
        pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    image = Image.open(buf)
    return image


def crop_preview_whitespace(image: Image, padding: int = 10) -> Image:
    """
    Crop the whitespace around an image.

    Args:
        image (PIL.Image.Image): The input image.
        padding (int, optional): The amount of padding to add to the bounding
        box. Defaults to 10.

    Returns:
        PIL.Image.Image: The cropped image.
    """
    # Convert image to grayscale and invert it
    gray_image = ImageOps.grayscale(image)
    inverted_image = ImageOps.invert(gray_image)

    # Get the bounding box of the non-white areas
    bbox = inverted_image.getbbox()
    if bbox:
        # Add padding to the bounding box
        bbox = (
            max(bbox[0] - padding, 0),
            max(bbox[1] - padding, 0),
            min(bbox[2] + padding, image.width),
            min(bbox[3] + padding, image.height)
        )
        return image.crop(bbox)
    return image


def save_preview_image(image: Image, folder: str, filename: str) -> bool:
    # Ensure the folder exists
    os.makedirs(folder, exist_ok=True)
    # Construct the full file path with .webp extension
    if not filename.lower().endswith('.webp'):
        filename += '.webp'
    file_path = os.path.join(folder, filename)
    # Save the image in .webp format
    image.save(file_path, format='webp')
    try:
        ts = logts()
        print(f'[PREVIEWGEN] {ts} Preview for {filename} saved to {folder}')
    except NameError:
        print(f'[PREVIEWGEN] Preview for {filename} saved to {folder}')
    return True


# TESTS -----------------------------------------------------------------------

__example_snapshot_extrusion = {
    '_id': '0026b86f-2b7c-4441-a42b-c135401601f9',
    'color': [209, 208, 205],
    'geometry': {
        'extrusions': [{
            'height': 12.0,
            'profile': [
                [-236.5281668056187, 135.9138446188233],
                [-235.98666438856054, 136.43043673849218],
                [-187.81222509575286, 136.619636378187],
                [236.19128468854456, 136.69496037267368],
                [236.7078768082133, 136.15345795561552],
                [236.95223496355607, 22.86883920802336],
                [235.7850096001714, 7.0161038801627456],
                [236.75591809603554, 3.2878627042294966],
                [236.92702811500726, -0.6862193828435466],
                [235.66342362481873, -9.390589013450608],
                [236.98900730732123, -20.537947095166373],
                [236.91902123370357, -135.93252734186524],
                [235.57772033975323, -136.69496037267368],
                [-236.59400116300475, -136.69496037267356],
                [-236.98900730732095, -119.74676506200217],
                [-236.5281668056187, 135.9138446188233],
            ],
        }],
    },
}

__example_snapshot_mesh = {
    '_id': 'a99b2619-0d97-495f-98c4-a6b02db206a3',
    'color': [207, 194, 126],
    'geometry': {
        'meshes': [{
            'vertices': [
                [510, 33.5, 26.5],
                [510, -33.5, 26.5],
                [-510, 33.5, 26.5],
                [0, 0, 0],
            ],
            'faces': [
                [0, 1, 2],
                [0, 2, 3],
                [1, 0, 3],
            ],
            'colors': [
                [207, 194, 126],
                [207, 194, 126],
                [207, 194, 126],
                [207, 194, 126],
            ],
        }],
    },
}

__example_snapshot_assembly = {
    '_id': 'c99b2619-0d97-495f-98c4-a6b02db206a4',
    'color': [100, 100, 100],
    'geometry': {
        'meshes': [
            {
                'vertices': [
                    [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
                    [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10],
                ],
                'faces': [
                    [0, 1, 2], [0, 2, 3], [4, 7, 6], [4, 6, 5],
                    [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
                    [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
                ],
                'colors': [[255, 0, 0]] * 8,
            },
            {
                'vertices': [
                    [20, 0, 0], [30, 0, 0], [30, 10, 0], [20, 10, 0],
                    [20, 0, 10], [30, 0, 10], [30, 10, 10], [20, 10, 10],
                ],
                'faces': [
                    [0, 1, 2], [0, 2, 3], [4, 7, 6], [4, 6, 5],
                    [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
                    [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
                ],
                'colors': [[0, 255, 0]] * 8,
            },
        ],
    },
}


if __name__ == '__main__':
    out_dir = os.path.dirname(os.path.abspath(__file__))
    for example in (
        __example_snapshot_extrusion,
        __example_snapshot_mesh,
        __example_snapshot_assembly,
    ):
        save_preview_image(
            crop_preview_whitespace(
                create_snapshot_preview_image(snapshot_data=example),
                padding=10,
            ),
            folder=out_dir,
            filename=example['_id'],
        )
