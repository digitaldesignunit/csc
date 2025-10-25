#! python3
# venv: DDU_CSC
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2
# VERSION: 250115

import os
import json
import glob


import numpy as np
from scipy.spatial import ConvexHull
from sklearn.decomposition import PCA


import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc


def transformation_matrix(rectangle, angle):
    # Compute the centroid of the rectangle
    centroid = np.mean(rectangle, axis=0)
    # Calculate translation to the origin
    translate_to_origin = np.eye(4)
    translate_to_origin[0, 3] = -centroid[0]
    translate_to_origin[1, 3] = -centroid[1]
    # Calculate rotation to align the long side with the x-axis
    rotate = np.eye(4)
    cos_angle = np.cos(-angle)
    sin_angle = np.sin(-angle)
    rotate[0, 0] = cos_angle
    rotate[0, 1] = -sin_angle
    rotate[1, 0] = sin_angle
    rotate[1, 1] = cos_angle
    # Combine transformations
    transformation = np.dot(rotate, translate_to_origin)
    return transformation


def rhino_xform(transformation_matrix):
    XForm = Rhino.Geometry.Transform.Identity
    XForm.M00 = transformation_matrix[0][0]
    XForm.M01 = transformation_matrix[0][1]
    XForm.M02 = transformation_matrix[0][2]
    XForm.M03 = transformation_matrix[0][3]
    XForm.M10 = transformation_matrix[1][0]
    XForm.M11 = transformation_matrix[1][1]
    XForm.M12 = transformation_matrix[1][2]
    XForm.M13 = transformation_matrix[1][3]
    XForm.M20 = transformation_matrix[2][0]
    XForm.M21 = transformation_matrix[2][1]
    XForm.M22 = transformation_matrix[2][2]
    XForm.M23 = transformation_matrix[2][3]
    return XForm


def minimum_bounding_rectangle(points):
    # Compute the convex hull of the points
    hull = ConvexHull(points)
    hull_points = points[hull.vertices]
    # Initialize variables to keep track of the best rectangle
    min_area = float('inf')
    best_rectangle = None
    best_angle = 0
    # Loop through each edge of the convex hull
    for i in range(len(hull_points)):
        # Determine the points forming the current edge
        p1 = hull_points[i]
        p2 = hull_points[(i + 1) % len(hull_points)]
        # Calculate edge vector
        edge_vec = p2 - p1
        # Rotate the points to align this edge with the x-axis
        angle = np.arctan2(edge_vec[1], edge_vec[0])
        cos_angle = np.cos(-angle)
        sin_angle = np.sin(-angle)
        rot_matrix = np.array([[cos_angle, -sin_angle],
                               [sin_angle, cos_angle]])
        rotated_points = np.dot(points, rot_matrix.T)
        # Compute the min/max x/y in the rotated points
        min_x = np.min(rotated_points[:, 0])
        max_x = np.max(rotated_points[:, 0])
        min_y = np.min(rotated_points[:, 1])
        max_y = np.max(rotated_points[:, 1])
        # Calculate area of the bounding rectangle
        area = (max_x - min_x) * (max_y - min_y)
        if area < min_area:
            min_area = area
            best_angle = angle
            # Create the rectangle in the rotated space
            # and then rotate it back
            best_rectangle = np.array([
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y]
            ])
            inv_rot_matrix = np.array([[cos_angle, sin_angle],
                                       [-sin_angle, cos_angle]])
            best_rectangle = np.dot(best_rectangle, inv_rot_matrix.T)
    # return results
    return best_rectangle, best_angle


def compute_pca_bounding_box(points):
    # normalize the data by subtracting the mean
    mean = np.mean(points, axis=0)
    centered_points = points - mean
    # apply PCA to find the principal axes
    pca = PCA(n_components=3)
    pca.fit(centered_points)
    # project the normalized points onto the PCA axes
    transformed_points = pca.transform(centered_points)
    # find the bounds along the principal axes
    min_bounds = np.min(transformed_points, axis=0)
    max_bounds = np.max(transformed_points, axis=0)
    # define the 8 corners of the bounding box in the PCA coordinate system
    corners = np.array([
        [min_bounds[0], min_bounds[1], min_bounds[2]],
        [max_bounds[0], min_bounds[1], min_bounds[2]],
        [max_bounds[0], max_bounds[1], min_bounds[2]],
        [min_bounds[0], max_bounds[1], min_bounds[2]],
        [min_bounds[0], min_bounds[1], max_bounds[2]],
        [max_bounds[0], min_bounds[1], max_bounds[2]],
        [max_bounds[0], max_bounds[1], max_bounds[2]],
        [min_bounds[0], max_bounds[1], max_bounds[2]]
    ])
    # calculate the transformation matrix to align
    # the PCA bounding box with the world axes
    extents = max_bounds - min_bounds
    sorted_indices = np.argsort(-extents)
    sorted_components = pca.components_[sorted_indices]
    # transformation matrix: Rotate back to align
    # with original axes, then translate to origin
    rotation_matrix = sorted_components
    transformation_matrix = np.eye(4)
    transformation_matrix[:3, :3] = rotation_matrix
    transformed_mean = rotation_matrix.dot(mean)
    transformation_matrix[:3, 3] = -transformed_mean
    transformation_matrix_inv = np.linalg.inv(transformation_matrix)
    # return results
    return (sorted_components,
            corners,
            transformation_matrix,
            transformation_matrix_inv)


def compute_minimum_bounds(geometry: Rhino.Geometry.GeometryBase):
    compute_3d = False
    # HANDLE BREP
    if isinstance(geometry, Rhino.Geometry.Brep):
        points = np.array([[p.Location.X,
                            p.Location.Y,
                            p.Location.Z] for p in geometry.Vertices])
        compute_3d = True
    # HANDLE EXTRUSIONS
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        brep = geometry.ToBrep()
        points = np.array([[p.Location.X,
                            p.Location.Y,
                            p.Location.Z] for p in brep.Vertices])
        compute_3d = True
    # HANDLE MESH
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        # get points
        points = np.array([[p.X, p.Y, p.Z] for p in geometry.Vertices])
        compute_3d = True
    # HANDLE POLYLINECURVE
    elif isinstance(geometry, Rhino.Geometry.PolylineCurve):
        pl = geometry.ToPolyline()
        atol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        angtol = Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians
        pl.RemoveNearlyEqualSubsequentPoints(atol)
        pl.MergeColinearSegments(angtol, True)
        pl.ReduceSegments(atol)
        points = np.array([[p.X, p.Y] for p in pl])
        compute_3d = False
    else:
        raise RuntimeError('Minimum BBX not implemented '
                           f'for geometry of type {type(geometry)}!')
    # PROCESSING RESULTS FOR OUTPUT
    if compute_3d:
        # compute bbx
        (principal_axes,
            bbox_corners,
            transformation_matrix,
            transformation_matrix_inv) = compute_pca_bounding_box(points)
        # get xform
        XForm = rhino_xform(transformation_matrix)
        # create bbx and aligned bbx
        AlignedBBX = [Rhino.Geometry.Point3d(p[0], p[1], p[2])
                      for p in bbox_corners]
        # create aligned geometry
        AlignedGeometry = geometry
        AlignedGeometry.Transform(XForm)
    else:
        mbr, angle = minimum_bounding_rectangle(points)
        transformation_matrix = transformation_matrix(mbr, angle)
        # create rhino xform
        XForm = rhino_xform(transformation_matrix)
        # create aligned geometry
        AlignedGeometry = geometry
        AlignedGeometry.Transform(XForm)
        # create bbxes
        AlignedBBX = [Rhino.Geometry.Point3d(p[0], p[1], 0) for p in mbr]
        [pt.Transform(XForm) for pt in AlignedBBX]
    # return results
    return (AlignedBBX, AlignedGeometry, XForm)


def reduce_mesh(mesh_id, target_face_count=100):
    # Reduce the mesh using Rhino's MeshReduce function
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    mesh = rs.coercemesh(mesh_id)
    if not mesh:
        print('Failed to get mesh geometry.')
        return None

    # Perform the mesh reduction
    primitive_mesh = mesh.Duplicate()
    primitive_mesh.Reduce(target_face_count, True, 5, False, True)
    primitive_mesh.Faces.ConvertQuadsToTriangles()
    primitive_mesh.Compact()

    # Replace the original mesh with the reduced one
    rs.DeleteObject(mesh_id)

    primitive_mesh_id = sc.doc.Objects.AddMesh(primitive_mesh)
    return primitive_mesh, primitive_mesh_id


def save_files(
        primitive_mesh,
        bbx_data, uid,
        json_source_dir,
        json_target_dir):
    # Get vertices
    vertices = [[v.X, v.Y, v.Z] for v in primitive_mesh.Vertices]

    # Get faces
    faces = []
    for i in range(primitive_mesh.Faces.Count):
        face = primitive_mesh.Faces[i]
        if face.IsQuad:
            raise RuntimeError('QUAD DETECTED!')
        else:
            faces.append([face.A, face.B, face.C])

    # Get vertex colors
    colors = []
    if primitive_mesh.VertexColors.Count == primitive_mesh.Vertices.Count:
        colors = [[c.R, c.G, c.B] for c in primitive_mesh.VertexColors]
    else:
        # Default color if no vertex colors are assigned
        colors = None

    # in json source dir, open file with uid
    input_file = os.path.join(json_source_dir, uid + '.json')
    with open(input_file, 'r', encoding='utf-8') as infile:
        jsondata = json.load(infile)

    # Modify geometry data, bbx, mt and lastmodified
    jsondata['bbx'] = bbx_data
    jsondata['geometry']['mesh']['v'] = vertices
    jsondata['geometry']['mesh']['f'] = faces
    jsondata['geometry']['mesh']['c'] = colors
    jsondata['lastmodified'] = '250115-151700'

    # Save the updated JSON to the output location
    output_file = os.path.join(json_target_dir, uid + '.json')
    with open(output_file, 'w', encoding='utf-8') as outfile:
        json.dump(jsondata, outfile, indent=4)

    print(f'    JSON updated and saved to: {output_file}')


def process_mesh(
        mesh_file,
        mesh_reduced_file,
        primitive_mesh_3dm_file,
        target_geometry_dir,
        uid,
        json_source_dir,
        json_target_dir):
    # PROCESS ORIGINAL MESH
    print('    Processing ORIGINAL Mesh...')
    # Clear the current document and open a new empty one
    rs.DocumentModified(False)
    rs.Command('!-_New _None', echo=False)
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    # Import the mesh
    rs.Command(f'!_-Open "{mesh_file}"')
    rs.Command('!_-ZE')
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    # Get all meshes in the document
    mesh_ids = rs.ObjectsByType(rs.filter.mesh)
    if not mesh_ids:
        print(f'    No mesh found in {mesh_file}')
        return
    # Assume we are working with the first mesh
    mesh_id = mesh_ids[0]
    # --> Apply PCA and obtain XFORM for reduced mesh
    # compute minimum bounding box
    original_mesh = rs.coercemesh(mesh_id)
    if not original_mesh:
        print('    Failed to get mesh geometry.')
        return
    bbx_xyz, aligned_geometry, xform = compute_minimum_bounds(original_mesh)
    # create bbx data (maximum points)
    bbx_list = [[pt.X, pt.Y, pt.Z] for pt in bbx_xyz]
    bbx_min = [bbx_list[0][0],
               bbx_list[0][1],
               bbx_list[0][2]]
    bbx_max = [bbx_list[6][0],
               bbx_list[6][1],
               bbx_list[6][2]]
    bbx_data = [bbx_min, bbx_max]
    # transform original mesh using xform
    rs.TransformObject(mesh_id, xform)
    # Export the mesh as OBJ with texture and MTL
    head, tail = os.path.split(mesh_file)
    obj_dir = os.path.join(target_geometry_dir, uid)
    if not os.path.exists(obj_dir):
        os.makedirs(obj_dir)
    obj_name = tail.split('.')[0]
    obj_name += '.obj'
    obj_file = os.path.join(obj_dir, obj_name)
    print('    Exporting ORIGINAL OBJ...')
    export_mesh_as_obj(mesh_id, obj_file)

    # OBTAIN PRIMITIVE MESH FROM ORIGINAL MESH AND SAVE 3DM
    print('    Creating PRIMITIVE Mesh...')
    # Reduce the mesh to obtain a primitive representation
    primitive_mesh, primitive_mesh_id = reduce_mesh(mesh_id,
                                                    target_face_count=300)
    if not primitive_mesh_id:
        print('    Mesh reduction failed!')
        return
    # Save the primitive mesh to a new file
    if not rs.SelectObject(primitive_mesh_id):
        print('    Failed to select reduced mesh for saving...')
        return
    os.makedirs(os.path.split(primitive_mesh_3dm_file)[0], exist_ok=True)
    if os.path.isfile(primitive_mesh_3dm_file):
        os.remove(primitive_mesh_3dm_file)
    if not rs.Command(f'!-_SaveAs \"{primitive_mesh_3dm_file}\"', echo=False):
        print('    Failed to save reduced mesh to '
              f'{primitive_mesh_3dm_file}...')
        return

    # PROCESS REDUCED MESH
    # Clear the current document and open a new empty one
    print('    Processing REDUCED Mesh...')
    rs.DocumentModified(False)
    rs.Command('!-_New _None', echo=False)
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    # Import the mesh
    rs.Command(f'!_-Open "{mesh_reduced_file}"')
    rs.Command('!_-ZE')
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    # Get all meshes in the document
    mesh_ids = rs.ObjectsByType(rs.filter.mesh)
    if not mesh_ids:
        print(f'    No mesh found in {mesh_reduced_file}')
        return
    # Assume we are working with the first mesh
    mesh_id = mesh_ids[0]
    # transform reduced mesh using xform
    rs.TransformObject(mesh_id, xform)
    # Export the mesh as OBJ with texture and MTL
    head, tail = os.path.split(mesh_reduced_file)
    obj_name = tail.split('.')[0]
    obj_name = obj_name + '.obj'
    obj_file = os.path.join(obj_dir, obj_name)
    print('    Exporting REDUCED OBJ...')
    export_mesh_as_obj(mesh_id, obj_file)

    # Save mesh data as JSON
    save_files(primitive_mesh, bbx_data, uid, json_source_dir, json_target_dir)


def export_mesh_as_obj(mesh_id, obj_file):
    # Select the mesh for export
    rs.SelectObject(mesh_id)

    # Export the mesh as an OBJ file
    export_command = f'!_-Export "{obj_file}" _Enter'
    if not rs.Command(export_command, echo=False):
        print(f'    Failed to export mesh to {obj_file}')
        return

    # extract obj filename without ext
    obj_name = os.path.splitext(os.path.basename(obj_file))[0]

    # rename jpg file
    all_jpgs = glob.glob(os.path.join(os.path.split(obj_file)[0], '*.jpg'))
    texture_fp = all_jpgs[0]
    texture_file = os.path.basename(texture_fp)
    old_texture_name = os.path.splitext(texture_file)[0]
    new_texture_name = 'texture'
    head, tail = os.path.split(texture_fp)
    ext = os.path.splitext(texture_fp)[1]
    new_texture_fp = os.path.join(head, new_texture_name + ext)
    try:
        os.rename(texture_fp, new_texture_fp)
    except FileExistsError:
        print('    Texture file already renamed, deleting second one...')
        os.remove(texture_fp)

    # Check if the mtl file exists
    mtl_filename = obj_name + '.mtl'
    mtl_file_path = os.path.join(os.path.split(obj_file)[0], mtl_filename)
    if not os.path.exists(mtl_file_path):
        print(f'    File not found: {mtl_file_path}')
        return

    # Read the content of the .mtl file
    with open(mtl_file_path, 'r') as file:
        lines = file.readlines()

    # Replace the texture filename
    updated_lines = []
    for line in lines:
        if line.strip().startswith('map_Kd') and old_texture_name in line:
            # Replace the old texture name with the new one
            updated_line = line.replace(old_texture_name, new_texture_name)
            updated_lines.append(updated_line)
        else:
            updated_lines.append(line)

    # Write the updated content back to the file
    with open(mtl_file_path, 'w') as file:
        file.writelines(updated_lines)

    print(f'    Mesh exported to {obj_file}')


def sas_processing(
        source_geometry_dir,
        target_geometry_dir,
        json_source_dir,
        json_target_dir):
    # List all subfolders in the specified folder
    subfolders = [f.path for f in
                  os.scandir(source_geometry_dir) if f.is_dir()]
    total = len(subfolders)

    for i, subfolder in enumerate(subfolders):
        uid = os.path.basename(subfolder)
        mesh_file = os.path.join(subfolder, 'mesh.3dm')
        mesh_reduced_file = os.path.join(subfolder, 'mesh_reduced.3dm')
        primitive_mesh_3dm_file = os.path.join(subfolder, 'mesh_primitive.3dm')
        print('--------------------------------------------')
        print(f'Processing ({i+1}/{total}) {uid}...')

        if os.path.exists(mesh_file):
            process_mesh(
                mesh_file,
                mesh_reduced_file,
                primitive_mesh_3dm_file,
                target_geometry_dir,
                uid,
                json_source_dir,
                json_target_dir)
        else:
            print(f'mesh_reduced.3dm not found in {subfolder}')

    # Clear the current document and open a new empty one
    rs.DocumentModified(False)
    rs.Command('!-_New _None', echo=False)
    sc.doc = Rhino.RhinoDoc.ActiveDoc


if __name__ == '__main__':
    source_geometry_dir = r'C:\Users\EFESTWIN\Documents\07_tu_darmstadt_ddu\05_Promotion\07_Source\240404_SAS_Debris_Files'  # NOQA
    target_geometry_dir = r'C:\Users\EFESTWIN\source\repos\csc\component_geometry\250115'  # NOQA
    json_source_dir = r'C:\Users\EFESTWIN\source\repos\csc\mongodb_backup\250115_0825'  # NOQA
    json_target_dir = r'C:\Users\EFESTWIN\source\repos\csc\mongodb_backup\SAS_NEW'  # NOQA
    sas_processing(
        source_geometry_dir,
        target_geometry_dir,
        json_source_dir,
        json_target_dir)
