#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import os

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

import numpy as np
from PIL import Image
import pyvista as pv


# FUNCTION DEFINITIONS --------------------------------------------------------

def create_extrusion_component_mesh(
        component_data: dict) -> pv.PolyData:
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
        faces.append([4, i, next_i, num_points + next_i, num_points + i])
    # Create faces for the top and bottom
    bottom_face = [num_points] + list(range(num_points))
    top_face = [num_points] + list(range(num_points, 2 * num_points))
    # Combine all faces
    faces = np.hstack(
        [[len(face)] + face for face in faces + [bottom_face, top_face]])
    # Create the mesh as PolyData object
    mesh = pv.PolyData(all_points, faces)
    return mesh


def convert_mesh_component_mesh(
        component_data: dict) -> pv.PolyData:
    # build np arrays from mesh data
    vertices = np.array(component_data['geometry']['mesh']['v'])
    faces = np.hstack(
        [[len(face)] + face
         for face in component_data['geometry']['mesh']['f']]
    )
    mesh = pv.PolyData(vertices, faces)
    return mesh


def create_component_preview(
        component_data: dict,
        output_folder: str,
        output_filename: str,
        image_size: int = 800) -> bool:
    # Create mesh based on component type
    if component_data['type'] == 'sheet':
        component_mesh = create_extrusion_component_mesh(component_data)
    else:
        component_mesh = convert_mesh_component_mesh(component_data)
    # Create plotter and set up scene
    plotter = pv.Plotter(
        off_screen=True,
        window_size=[image_size, image_size],
        line_smoothing=True,
        polygon_smoothing=True
    )
    # Add mesh to plotter
    plotter.add_mesh(
        component_mesh,
        color=component_data['color'],
        show_edges=True
    )
    # Get the bounds of the mesh to adjust the view
    bounds = component_mesh.bounds
    center = component_mesh.center
    max_extent = max(bounds[1] - bounds[0],
                     bounds[3] - bounds[2],
                     bounds[5] - bounds[4])
    padding = max_extent * 0.1
    # Adjust the camera to center the geometry and add some padding
    plotter.view_isometric()
    # Set the camera position and zoom to fit the mesh within the view
    plotter.camera.focal_point = center
    plotter.camera.position = [
        center[0] + max_extent + padding,
        center[1] + max_extent + padding,
        center[2] + max_extent + padding
    ]
    # Zoom out to ensure there is padding around the geometry
    plotter.camera.zoom(0.8)
    # Render the plot and grab the image data
    img_data = plotter.screenshot(transparent_background=False)
    # Convert the image data to a PIL Image
    img = Image.fromarray(img_data)
    # Save to output folder as .webp
    output_path = f'{output_folder}/{output_filename}.webp'
    img.save(output_path, 'webp')

    print(f'[PREVIEWGEN] Preview for {output_filename} saved to {output_path}')

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
    output_folder = os.path.dirname(os.path.abspath(__file__))
    create_component_preview(
        __example_component_data_a,
        output_folder,
        __example_component_data_a['_id'])
    create_component_preview(
        __example_component_data_b,
        output_folder,
        __example_component_data_b['_id'])
