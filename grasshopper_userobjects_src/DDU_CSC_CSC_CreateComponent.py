#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

import json
import uuid

import numpy as np
from scipy.spatial import ConvexHull
from sklearn.decomposition import PCA

import System
import Grasshopper
import Rhino

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "CSC_CreateComponent"
ghenv.Component.NickName = "CSC_CreateComponent"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "3 Component Operations"


class CreateComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """

    def minimum_bounding_rectangle(self, points):
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

    def transformation_matrix(self, rectangle, angle):
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

    def compute_pca_bounding_box(self, points):
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

    def rhino_xform(self, transformation_matrix):
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

    def compute_minimum_bounds(self, geometry: Rhino.Geometry.GeometryBase):
        compute_3d = False
        # HANDLE BREP
        if isinstance(geometry, Rhino.Geometry.Brep):
            points = np.array([[p.Location.X,
                                p.Location.Y,
                                p.Location.Z] for p in Geometry.Vertices])
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
                               f'for geometry of type {type(Geometry)}!')
        # PROCESSING RESULTS FOR OUTPUT
        if compute_3d:
            # compute bbx
            (principal_axes,
             bbox_corners,
             transformation_matrix,
             transformation_matrix_inv) = self.compute_pca_bounding_box(points)
            # get xform
            XForm = self.rhino_xform(transformation_matrix)
            # create bbx and aligned bbx
            AlignedBBX = [Rhino.Geometry.Point3d(p[0], p[1], p[2])
                          for p in bbox_corners]
            # create aligned geometry
            AlignedGeometry = geometry
            AlignedGeometry.Transform(XForm)
        else:
            mbr, angle = self.minimum_bounding_rectangle(points)
            transformation_matrix = self.transformation_matrix(mbr, angle)
            # create rhino xform
            XForm = self.rhino_xform(transformation_matrix)
            # create aligned geometry
            AlignedGeometry = geometry
            AlignedGeometry.Transform(XForm)
            # create bbxes
            AlignedBBX = [Rhino.Geometry.Point3d(p[0], p[1], 0) for p in mbr]
            [pt.Transform(XForm) for pt in AlignedBBX]
        # return results
        return (AlignedBBX, AlignedGeometry)

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

    def RunScript(self,
            ComponentID: str,
            Type: str,
            Material: str,
            Geometry: Rhino.Geometry.GeometryBase,
            MaterialThickness: float,
            Color: System.Drawing.Color):
        
        # GHENV COMPONENT SETTINGS
        ghenv.Component.Name = "CSC_CreateComponent"
        ghenv.Component.NickName = "CSC_CreateComponent"
        ghenv.Component.Category = "DDU_CSC"
        ghenv.Component.SubCategory = "2 Catalogue Interface"
        
        # set up output trees and results tuple
        ComponentData = Grasshopper.DataTree[System.Object]()
        # sanitize input and abort if not present
        if not ComponentID:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input ComponentID failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        elif not self.validate_uuid(ComponentID):
            rml = ghenv.Component.RuntimeMessageLevel.Error
            msg = 'Input ComponentID is not a valid UUID! Aborting...'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        if not Type:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input Type failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        if not Material:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input Material failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        if not Color:
            rml = ghenv.Component.RuntimeMessageLevel.Remark
            msg = ('Input Color failed to collect data.'
                   'Will use Grey as default Color.')
            print(msg)
            ghenv.Component.AddRuntimeMessage(rml, msg)
            Color = System.Drawing.Color.FromArgb(255, 175, 175, 175)
        if not Geometry:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input Geometry failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        elif not Geometry.IsValid:
            rml = ghenv.Component.RuntimeMessageLevel.Error
            msg = 'Input Geometry is invalid!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        # create component data dictionary
        COMPDATA = {
            '_id': ComponentID,
            'type': Type,
            'material': Material,
            'materialthickness': MaterialThickness,
            'geometry': {},
            'color': [Color.R, Color.G, Color.B],
            'validated': False,
            'bbx': {
                'xy': None,
                'xyz': None
            },
            'iframe': {
                'o': [0.0, 0.0, 0.0],
                'x': [1.0, 0.0, 0.0],
                'y': [0.0, 1.0, 0.0],
                'z': [0.0, 0.0, 1.0]
            }
        }
        # TYPE FILTERING
        if Type == 'rubble':
            if not isinstance(Geometry, Rhino.Geometry.Mesh):
                msg = ('The "rubble" type expects a Mesh as '
                    'geometry input! Please ensure and try again.')
                print(msg)
                raise ValueError(msg)
        elif Type == 'sheet':
            if not (isinstance(Geometry, Rhino.Geometry.PolylineCurve) or 
                    isinstance(Geometry, Rhino.Geometry.Polyline)):
                msg = ('The "sheet" type expects a polyline as '
                    'geometry input! Please ensure and try again.')
                print(msg)
                raise ValueError(msg)
            if not MaterialThickness:
                msg = ('The "sheet" type expects a value for '
                       '"MaterialThickness"! Please ensure and try again.')
                print(msg)
                raise ValueError(msg)
        # process geometry input
        # HANDLE POLYLINE AND POLYLINECURVE
        if (isinstance(Geometry, Rhino.Geometry.Polyline) or
            isinstance(Geometry, Rhino.Geometry.PolylineCurve)):
            bbx_xy, aligned_geometry = self.compute_minimum_bounds(Geometry)
            bbxdata = {
                'xy': [[pt.X, pt.Y] for pt in bbx_xy],
            }
            COMPDATA['bbx'].update(bbxdata)
            # create geometry dict
            polyline = [[p.X, p.Y] for p in aligned_geometry.ToPolyline()]
            comp_polyline = {
                'polyline': polyline
            }
            COMPDATA['geometry'].update(comp_polyline)
        # HANDLE MESH
        elif isinstance(Geometry, Rhino.Geometry.Mesh):
            Geometry.Faces.ConvertQuadsToTriangles()
            Geometry.Compact()
            # compute minimum bounding box
            bbx_xyz, aligned_geometry = self.compute_minimum_bounds(Geometry)
            # create bbx dict
            bbxdata = {
                'xyz': [[pt.X, pt.Y, pt.Z] for pt in bbx_xyz]
            }
            COMPDATA['bbx'].update(bbxdata)
            mt = bbx_xyz[0].DistanceTo(bbx_xyz[4])
            COMPDATA['materialthickness'] = mt
            # create geometry dict
            vertices = [[p.X, p.Y, p.Z] for p in aligned_geometry.Vertices]
            faces = [[f[0], f[1], f[2]] for f in aligned_geometry.Faces]
            comp_mesh = {
                'mesh': {
                    'v': vertices,
                    'f': faces
                }
            }
            COMPDATA['geometry'].update(comp_mesh)
        # HANDLE BREP
        elif isinstance(Geometry, Rhino.Geometry.Brep):
            raise RuntimeError('Geometry Processing for geometry of '
                               f'type {type(Geometry)} not implemented yet! '
                               'Please convert to Mesh and try again.')
        elif isinstance(Geometry, Rhino.Geometry.Extrusion):
            raise RuntimeError('Geometry Processing for geometry of '
                               f'type {type(Geometry)} not implemented yet! '
                               'Please convert to Mesh and try again.')
        else:
            raise RuntimeError('Geometry Processing for geometry of '
                               f'type {type(Geometry)} not implemented yet! '
                               'Please convert to Mesh and try again.')
        # create json string
        ComponentData = json.dumps(COMPDATA)
        # return output
        return ComponentData
