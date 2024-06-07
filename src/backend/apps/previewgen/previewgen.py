#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from io import BytesIO
import os

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image, ImageOps

# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import create_logging_timestamp as logts


# FUNCTION DEFINITIONS --------------------------------------------------------

def create_extrusion_component_mesh(component_data: dict):
    # Convert polyline to numpy array and add z-coordinate (0)
    points = np.array(component_data['geometry']['polyline'])
    num_points = len(points)
    points_3d_bottom = np.hstack([points, np.zeros((num_points, 1))])
    # Create the top points by adding the material thickness in the z-direction
    points_3d_top = points_3d_bottom.copy()
    points_3d_top[:, 2] = component_data['materialthickness']
    # Combine bottom and top points
    all_points = np.vstack([points_3d_bottom, points_3d_top])
    # Create faces for the sides
    faces = []
    for i in range(num_points):
        next_i = (i + 1) % num_points
        face = [
            points_3d_bottom[i],
            points_3d_bottom[next_i],
            points_3d_top[next_i],
            points_3d_top[i]
        ]
        faces.append(face)
    # Create faces for the top and bottom
    faces.append(points_3d_bottom.tolist())
    faces.append(points_3d_top.tolist())
    return all_points, faces


def convert_mesh_component_mesh(component_data: dict):
    # Build np arrays from mesh data
    vertices = np.array(component_data['geometry']['mesh']['v'])
    faces = [[vertices[idx] for idx in face]
             for face in component_data['geometry']['mesh']['f']]
    return vertices, faces


def create_component_preview_image(
        component_data: dict,
        size: int = 800,
        dpi: int = 300) -> Image:
    # Create mesh based on component type
    if component_data['type'] == 'sheet':
        vertices, faces = create_extrusion_component_mesh(component_data)
    else:
        vertices, faces = convert_mesh_component_mesh(component_data)
    # Calculate figsize based on image_size and dpi
    figsize = size / dpi
    # Create figure and 3D axis
    fig = plt.figure(
        figsize=(figsize, figsize),
        dpi=dpi,
        constrained_layout=True)
    ax = fig.add_subplot(111, projection='3d')
    # Create Poly3DCollection from faces
    poly3d = Poly3DCollection(
        faces, alpha=1.0,  # Set alpha to 1.0 for opaque mesh
        facecolor=np.array(component_data['color']) / 255.0,
        edgecolor='k',
        linewidths=0.2)
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
    ts = logts()
    print(f'[PREVIEWGEN] {ts} Preview for {filename} saved to {folder}')
    return True


# TESTS -----------------------------------------------------------------------

__example_component_data_a = {
        '_id': '0026b86f-2b7c-4441-a42b-c135401601f9',
        'created': '240522-000248',
        'lastmodified': '240522-000248',
        'type': 'sheet',
        'material': 'corian',
        'materialthickness': 12,
        'geometry': {
            'polyline': [
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
                [-236.5281668056187, 135.9138446188233]
            ]
        },
        'complexity': 1,
        'fragment': True,
        'assembly': False,
        'color': [209, 208, 205],
        'bbx': {
            'xy': [
                [-236.98900730732106, -136.69496037267368],
                [236.98900730732112, -136.69496037267368],
                [236.98900730732112, 136.69496037267368],
                [-236.98900730732106, 136.69496037267368]
            ],
            'xyz': None
        },
        'descriptors': {},
        'indicators': {
            'eco2e': {
                'value': 7850,
                'unit': 'kgCO2e/m3',
                'source': 'DuPoint Corian Solid Surface EPD 2017'
            }
        },
        'validated': True,
        'iframe': {
            'o': [0, 0, 0],
            'x': [1, 0, 0],
            'y': [0, 1, 0],
            'z': [0, 0, 1]
        }
    }

__example_component_data_b = {
        '_id': 'a99b2619-0d97-495f-98c4-a6b02db206a3',
        'created': '240522-083157',
        'lastmodified': '240522-083157',
        'type': 'beam',
        'material': 'timber',
        'materialthickness': 53.00000000000001,
        'geometry': {
            'mesh': {
                'v': [
                    [510, 33.5, 26.5],
                    [510, -33.5, 26.5],
                    [-510, 33.5, 26.5],
                    [-510, -33.5, 26.5],
                    [-510, -33.5, 26.5],
                    [-510, 33.5, 26.5],
                    [-510, 36.5, 23.5],
                    [-510, 36.5, -23.5],
                    [-510, 33.5, -26.5],
                    [-510, -33.5, -26.5],
                    [-510, -36.5, -23.5],
                    [-510, -36.5, 23.5],
                    [-510, 33.5, -26.5],
                    [-510, -33.5, -26.5],
                    [510, 33.5, -26.5],
                    [510, -33.5, -26.5],
                    [510, 33.5, 26.5],
                    [510, -33.5, 26.5],
                    [510, -33.5, -26.5],
                    [510, 33.5, -26.5],
                    [510, 36.5, -23.5],
                    [510, 36.5, 23.5],
                    [510, -36.5, 23.5],
                    [510, -36.5, -23.5],
                    [510, 36.5, 23.5],
                    [-510, 36.5, -23.5],
                    [-510, 36.5, 23.5],
                    [510, 36.5, -23.5],
                    [510, -36.5, 23.5],
                    [510, -36.5, -23.5],
                    [-510, -36.5, 23.5],
                    [-510, -36.5, -23.5],
                    [510, 33.5, 26.5],
                    [-510, 33.5, 26.5],
                    [-510, 36.5, 23.5],
                    [510, 36.5, 23.5],
                    [510, -33.5, 26.5],
                    [-510, -33.5, 26.5],
                    [-510, -36.5, 23.5],
                    [510, -36.5, 23.5],
                    [-510, 33.5, -26.5],
                    [510, 33.5, -26.5],
                    [510, 36.5, -23.5],
                    [-510, 36.5, -23.5],
                    [-510, -33.5, -26.5],
                    [510, -33.5, -26.5],
                    [510, -36.5, -23.5],
                    [-510, -36.5, -23.5]
                ],
                'f': [
                    [1, 0, 2],
                    [6, 11, 4],
                    [11, 6, 7],
                    [10, 7, 8],
                    [13, 12, 14],
                    [18, 19, 20],
                    [23, 20, 21],
                    [22, 21, 16],
                    [27, 25, 26],
                    [29, 28, 30],
                    [35, 34, 33],
                    [39, 36, 37],
                    [43, 42, 41],
                    [47, 44, 45],
                    [1, 2, 3],
                    [6, 4, 5],
                    [11, 7, 10],
                    [10, 8, 9],
                    [13, 14, 15],
                    [18, 20, 23],
                    [23, 21, 22],
                    [22, 16, 17],
                    [27, 26, 24],
                    [29, 30, 31],
                    [35, 33, 32],
                    [39, 37, 38],
                    [43, 41, 40],
                    [47, 45, 46]
                ]
            }
        },
        'complexity': 1,
        'fragment': True,
        'assembly': False,
        'color': [207, 194, 126],
        'bbx': {
            'xy': None,
            'xyz': [
                [-510, -36.500000000000014, -26.500000000000004],
                [510, -36.500000000000014, -26.500000000000004],
                [510, 36.500000000000014, -26.500000000000004],
                [-510, 36.500000000000014, -26.500000000000004],
                [-510, -36.500000000000014, 26.500000000000004],
                [510, -36.500000000000014, 26.500000000000004],
                [510, 36.500000000000014, 26.500000000000004],
                [-510, 36.500000000000014, 26.500000000000004]
            ]
        },
        'descriptors': {},
        'indicators': {},
        'validated': True,
        'iframe': {
            'o': [0, 0, 0],
            'x': [1, 0, 0],
            'y': [0, 1, 0],
            'z': [0, 0, 1]
        }
    }


if __name__ == '__main__':
    out_dir = os.path.dirname(os.path.abspath(__file__))
    # Create preview images for example component data
    save_preview_image(
        crop_preview_whitespace(
            create_component_preview_image(
                component_data=__example_component_data_a
            ),
            padding=10
        ),
        folder=out_dir,
        filename=__example_component_data_a['_id']
    )
    save_preview_image(
        crop_preview_whitespace(
            create_component_preview_image(
                component_data=__example_component_data_b
            ),
            padding=10
        ),
        folder=out_dir,
        filename=__example_component_data_b['_id']
    )
