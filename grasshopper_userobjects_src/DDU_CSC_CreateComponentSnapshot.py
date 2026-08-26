#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA
import struct  # NOQA
import uuid  # NOQA
import os  # NOQA
import platform  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np  # NOQA
from scipy.spatial import ConvexHull  # NOQA
from sklearn.decomposition import PCA  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# One PCA sample per this many mm of triangle area (3D mesh path).
REFERENCE_FACE_AREA_MM2 = 100.0

# Inline JSON preview cap; full cloud staged as PLY above this count.
POINT_CLOUD_INLINE_MAX = 5000
POINT_CLOUD_STAGING_THRESHOLD = 5000

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateComponentSnapshot'  # NOQA
ghenv.Component.NickName = 'CreateComponentSnapshot'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds a POST /identities/{id}/snapshots payload (CreateSnapshotRequest) '
    'from Rhino geometry for an existing identity. Computes PCA orientation, '
    'mesh reduction, stages mesh PLY under '
    'pending_snapshot_assets/{snapshot_id}/meshes/<i>/ and point cloud PLY '
    'under .../point_clouds/<i>.ply.'
)


class CSC_CreateComponentSnapshot(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260826
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'If True, clears pending_snapshot_assets staging '
            '(does not affect Session API cache)'
        )
        self.InputParams[1].Description = (
            'Existing identity UUID to attach the new snapshot to'
        )
        self.InputParams[2].Description = (
            'New snapshot UUID (optional; auto-generated when empty)'
        )
        self.InputParams[3].Description = (
            'Snapshot display name (optional; '
            'inherits current name when empty)'
        )
        self.InputParams[4].Description = (
            'Complexity level '
            '(0=simple, 1=normal, 2=complex, 3=very complex)'
        )
        self.InputParams[5].Description = (
            'Fragment status (True for fragments, False for complete)'
        )
        self.InputParams[6].Description = (
            'Assembly status (True for assemblies, False for individual)'
        )
        self.InputParams[7].Description = (
            'Component color (System.Drawing.Color)'
        )
        self.InputParams[8].Description = (
            'Location as Vector3d (X=latitude, Y=longitude, Z ignored)'
        )
        self.InputParams[9].Description = (
            'Rhino geometry — single Mesh, Extrusion, or PointCloud, or a '
            'list of Meshes and/or PointClouds. Extrusion is single-object '
            'only.'
        )
        self.InputParams[10].Description = (
            'Marker points as list of Point3d objects'
        )
        self.InputParams[11].Description = (
            'Optional condition grade. Integer in {0, 1, 2, 3}. '
            'Leave unconnected for unknown.'
        )
        self.InputParams[12].Description = (
            'Optional free-text notes for the new snapshot (max 5000)'
        )
        self.InputParams[13].Description = (
            'Count of identical physical items (integer >= 1, default 1)'
        )
        self.InputParams[14].Description = (
            'Virtual snapshot flag (True = proposal/hypothetical state)'
        )
        if len(self.InputParams) > 15:
            self.InputParams[15].Description = (
                'Optional reinforcement JSON strings from CreateReinforcement '
                '(one or many; merged into geometry.reinforcements)'
            )
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'CreateSnapshotRequest JSON plus identity_id for '
            'POST /identities/{id}/snapshots'
        )

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            self._addWarning(
                'No authentication found. Using hardcoded snapshot schema.'
            )
            return None
        return auth_core

    def get_snapshot_payload_schema(self):
        """Get CreateSnapshotRequest schema from Session cache or fallback."""
        auth_core = self.get_auth_core_from_sticky()
        if auth_core and hasattr(auth_core, 'get_create_snapshot_schema'):
            try:
                schema = auth_core.get_create_snapshot_schema()
                if schema:
                    self._addRemark('Using cached create-snapshot schema')
                    return schema
            except Exception as e:
                self._addWarning(
                    f'Error fetching create-snapshot schema: {e}; '
                    'using hardcoded fallback'
                )

        self._addRemark('Using hardcoded create-snapshot schema')
        return self.get_hardcoded_snapshot_schema()

    def get_hardcoded_snapshot_schema(self):
        """Minimal CreateSnapshotRequest schema when Session is unavailable."""
        return {
            'type': 'object',
            'required': [
                'complexity', 'fragment', 'assembly', 'geometry', 'bbx',
                'bbx_origin', 'iframe', 'pca_frame',
            ],
            'properties': {
                '_id': {'type': 'string'},
                'identity_id': {'type': 'string'},
                'name': {'type': 'string'},
                'complexity': {'type': 'integer'},
                'fragment': {'type': 'boolean'},
                'assembly': {'type': 'boolean'},
                'virtual': {'type': 'boolean'},
                'geometry': {'type': 'object'},
                'color': {'type': 'array'},
                'bbx': {'type': 'array'},
                'bbx_origin': {'type': 'array'},
                'location': {'type': 'object'},
                'iframe': {'type': 'object'},
                'pca_frame': {'type': 'object'},
                'validated': {'type': 'boolean'},
                'marker_points': {'type': 'array'},
                'notes': {'type': 'string'},
                'quantity': {'type': 'integer'},
            },
        }

    def validate_snapshot_payload(self, payload, schema):
        """Validate snapshot payload against schema required fields."""
        try:
            required_fields = schema.get('required', [])
            missing_fields = [
                field for field in required_fields if field not in payload
            ]
            if missing_fields:
                self._addError(
                    f'Missing required fields: {", ".join(missing_fields)}'
                )
                return False

            if not payload.get('identity_id'):
                self._addError('identity_id must be present')
                return False
            if not self.validate_uuid(payload.get('identity_id', '')):
                self._addError('identity_id must be a valid UUID')
                return False
            if payload.get('_id') and not self.validate_uuid(payload['_id']):
                self._addError('_id must be a valid snapshot UUID')
                return False

            if not isinstance(payload.get('complexity'), int):
                self._addError('complexity must be an integer')
                return False
            if not isinstance(payload.get('fragment'), bool):
                self._addError('fragment must be a boolean')
                return False
            if not isinstance(payload.get('assembly'), bool):
                self._addError('assembly must be a boolean')
                return False

            color = payload.get('color', [])
            if color and (not isinstance(color, list) or len(color) != 3):
                self._addError('color must be a list of 3 integers [R, G, B]')
                return False

            if not isinstance(payload.get('iframe'), dict):
                self._addError('iframe must be a frame object')
                return False
            if not isinstance(payload.get('pca_frame'), dict):
                self._addError('pca_frame must be a frame object')
                return False

            geometry = payload.get('geometry') or {}
            if not (
                geometry.get('meshes')
                or geometry.get('extrusions')
                or geometry.get('point_clouds')
            ):
                self._addError(
                    'geometry must include meshes, extrusions, or point_clouds'
                )
                return False

            return True

        except Exception as e:
            self._addError(f'Validation error: {str(e)}')
            return False

    def normalize_reinforcement_json_input(self, reinforcements_input):
        """Flatten optional reinforcement JSON input to a list of strings."""
        entries = []
        if reinforcements_input is None:
            return entries

        if isinstance(reinforcements_input, str):
            raw = reinforcements_input.strip()
            if raw:
                entries.append(raw)
            return entries

        if isinstance(
            reinforcements_input,
            Grasshopper.Kernel.Data.GH_Structure
        ):
            for obj in reinforcements_input.AllData(True):
                if obj is None:
                    continue
                raw = str(obj).strip()
                if raw:
                    entries.append(raw)
            return entries

        try:
            for item in reinforcements_input:
                if item is None:
                    continue
                raw = str(item).strip()
                if raw:
                    entries.append(raw)
        except TypeError:
            raw = str(reinforcements_input).strip()
            if raw:
                entries.append(raw)
        return entries

    def build_centered_reinforcements(
            self,
            reinforcements_input,
            translation_vector):
        """Parse reinforcement JSON strings and apply centering translation."""
        json_entries = self.normalize_reinforcement_json_input(
            reinforcements_input)
        if not json_entries:
            return []

        tx = float(translation_vector[0])
        ty = float(translation_vector[1])
        tz = float(translation_vector[2])
        centered = []

        for idx, raw in enumerate(json_entries):
            try:
                data = json.loads(raw)
            except (TypeError, ValueError) as exc:
                self._addWarning(
                    f'Reinforcement {idx}: invalid JSON ({exc})'
                )
                continue
            if not isinstance(data, dict):
                self._addWarning(
                    f'Reinforcement {idx}: expected JSON object'
                )
                continue

            spec = str(data.get('spec', '')).strip()
            diameter = data.get('diameter')
            points = data.get('points')
            if not spec:
                self._addWarning(f'Reinforcement {idx}: spec is required')
                continue
            try:
                diameter = float(diameter)
            except (TypeError, ValueError):
                self._addWarning(
                    f'Reinforcement {idx}: diameter must be a number'
                )
                continue
            if diameter <= 0:
                self._addWarning(
                    f'Reinforcement {idx}: diameter must be > 0'
                )
                continue
            if not isinstance(points, list) or len(points) < 2:
                self._addWarning(
                    f'Reinforcement {idx}: at least 2 points required'
                )
                continue

            centered_points = []
            valid = True
            for pt in points:
                if (not isinstance(pt, (list, tuple))
                        or len(pt) != 3):
                    self._addWarning(
                        f'Reinforcement {idx}: invalid point {pt}'
                    )
                    valid = False
                    break
                centered_points.append([
                    float(pt[0]) + tx,
                    float(pt[1]) + ty,
                    float(pt[2]) + tz,
                ])
            if not valid:
                continue

            centered.append({
                'spec': spec,
                'diameter': diameter,
                'points': centered_points,
            })

        return centered

    def build_snapshot_payload(
            self,
            snapshot_id: str,
            identity_id: str,
            name: str,
            complexity: int,
            fragment: bool,
            assembly: bool,
            color,
            dimensions,
            location_data,
            principal_components,
            condition,
            notes,
            quantity,
            virtual: bool):
        """
        Build POST /identities/{{id}}/snapshots JSON
        (CreateSnapshotRequest).
        """
        payload = {
            '_id': snapshot_id,
            'identity_id': identity_id,
            'complexity': int(complexity),
            'fragment': bool(fragment),
            'assembly': bool(assembly),
            'virtual': bool(virtual),
            'geometry': {},
            'color': [color.R, color.G, color.B],
            'bbx': dimensions,
            'bbx_origin': [0.0, 0.0, 0.0],
            'location': location_data or {'lat': 0.0, 'lon': 0.0},
            'descriptors': {},
            'processes': {},
            'iframe': {
                'o': [0.0, 0.0, 0.0],
                'x': [1.0, 0.0, 0.0],
                'y': [0.0, 1.0, 0.0],
                'z': [0.0, 0.0, 1.0],
            },
            'pca_frame': {
                'o': [0.0, 0.0, 0.0],
                'x': principal_components[0].tolist(),
                'y': principal_components[1].tolist(),
                'z': principal_components[2].tolist(),
            },
            'validated': False,
        }

        trimmed_name = (name or '').strip()
        if trimmed_name:
            payload['name'] = trimmed_name

        if condition is not None:
            payload['condition'] = condition

        trimmed_notes = (notes or '').strip()
        if trimmed_notes:
            payload['notes'] = trimmed_notes[:5000]

        try:
            qty = int(quantity) if quantity is not None else 1
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, min(999_999, qty))
        if qty != 1:
            payload['quantity'] = qty

        return payload

    def mesh_to_inline_primitive(self, mesh, default_rgb):
        """SnapshotMesh dict (vertices/faces/colors, Rhino Z-up)."""
        vertices = [[p.X, p.Y, p.Z] for p in mesh.Vertices]
        faces = []
        for face in mesh.Faces:
            if face.IsTriangle:
                faces.append([face.A, face.B, face.C])
            elif face.IsQuad:
                faces.append([face.A, face.B, face.C])
                faces.append([face.A, face.C, face.D])

        if mesh.VertexColors.Count > 0:
            colors = [
                [mesh.VertexColors[i].R, mesh.VertexColors[i].G,
                 mesh.VertexColors[i].B]
                for i in range(mesh.Vertices.Count)
            ]
        else:
            colors = [list(default_rgb)] * len(vertices)

        return {
            'vertices': vertices,
            'faces': faces,
            'colors': colors,
        }

    def save_rhino_mesh_as_ply_binary(self, mesh, file_path, default_rgb):
        """Write binary little-endian PLY (Rhino Z-up) with per-vertex RGB."""
        vertices = []
        colors = []
        has_vc = mesh.VertexColors.Count > 0
        for i in range(mesh.Vertices.Count):
            v = mesh.Vertices[i]
            vertices.append((v.X, v.Y, v.Z))
            if has_vc and i < mesh.VertexColors.Count:
                c = mesh.VertexColors[i]
                colors.append((c.R, c.G, c.B))
            else:
                colors.append(default_rgb)

        faces = []
        for face in mesh.Faces:
            if face.IsTriangle:
                faces.append((face.A, face.B, face.C))
            elif face.IsQuad:
                faces.append((face.A, face.B, face.C))
                faces.append((face.A, face.C, face.D))

        header = (
            'ply\n'
            'format binary_little_endian 1.0\n'
            f'element vertex {len(vertices)}\n'
            'property float x\n'
            'property float y\n'
            'property float z\n'
            'property uchar red\n'
            'property uchar green\n'
            'property uchar blue\n'
            f'element face {len(faces)}\n'
            'property list uchar int vertex_indices\n'
            'end_header\n'
        )

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as handle:
            handle.write(header.encode('ascii'))
            for (x, y, z), (r, g, b) in zip(vertices, colors):
                handle.write(struct.pack('<fffBBB', x, y, z, r, g, b))
            for tri in faces:
                handle.write(struct.pack('<Biii', 3, tri[0], tri[1], tri[2]))

    def point_cloud_to_inline_primitive(
            self,
            cloud,
            max_points: int = POINT_CLOUD_INLINE_MAX):
        """Build inline point_cloud primitive with optional subsampling."""
        count = cloud.Count
        if count == 0:
            raise RuntimeError('Point cloud is empty')

        if count > max_points:
            step = count / float(max_points)
            indices = [
                min(int(round(i * step)), count - 1)
                for i in range(max_points)
            ]
        else:
            indices = list(range(count))

        points = []
        colors = []
        has_colors = False
        for i in indices:
            item = cloud[i]
            loc = item.Location
            points.append([loc.X, loc.Y, loc.Z])
            color = item.Color
            if color.IsEmpty:
                colors.append([128, 128, 128])
            else:
                has_colors = True
                colors.append([color.R, color.G, color.B])

        result = {'points': points}
        if has_colors:
            result['colors'] = colors
        return result

    def save_rhino_point_cloud_as_ply_binary(self, cloud, file_path):
        """Write binary little-endian PLY (vertices only) from a PointCloud."""
        vertices = []
        colors = []
        for i in range(cloud.Count):
            item = cloud[i]
            loc = item.Location
            vertices.append((loc.X, loc.Y, loc.Z))
            color = item.Color
            if color.IsEmpty:
                colors.append((128, 128, 128))
            else:
                colors.append((color.R, color.G, color.B))

        header = (
            'ply\n'
            'format binary_little_endian 1.0\n'
            f'element vertex {len(vertices)}\n'
            'property float x\n'
            'property float y\n'
            'property float z\n'
            'property uchar red\n'
            'property uchar green\n'
            'property uchar blue\n'
            'end_header\n'
        )

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as handle:
            handle.write(header.encode('ascii'))
            for (x, y, z), (r, g, b) in zip(vertices, colors):
                handle.write(struct.pack('<fffBBB', x, y, z, r, g, b))

    def center_geometry_at_origin(self, geometry):
        """
        Center geometry at its centroid.
        Returns centered geometry and translation vector.
        """
        if isinstance(geometry, Rhino.Geometry.PointCloud):
            if geometry.Count == 0:
                raise RuntimeError('Point cloud is empty')
            bbox = geometry.GetBoundingBox(True)
            volume_centroid = bbox.Center
        else:
            # Get the volume centroid of the geometry
            vmp = Rhino.Geometry.VolumeMassProperties.Compute(geometry)
            volume_centroid = vmp.Centroid
            if volume_centroid is None:
                # Fallback to bounding box centroid if volume centroid fails
                bbox = geometry.GetBoundingBox(True)
                volume_centroid = bbox.Center
        # Create translation vector to center
        translation_vector = -np.array([
            volume_centroid.X, volume_centroid.Y, volume_centroid.Z
        ])
        # Create centered extrusion
        centered_geometry = geometry.Duplicate()
        translation_xform = Rhino.Geometry.Transform.Translation(
            translation_vector[0], translation_vector[1], translation_vector[2]
        )
        centered_geometry.Transform(translation_xform)
        return centered_geometry, translation_vector

    def _triangle_area(self, v0, v1, v2):
        return float(0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0)))

    def sample_points_area_weighted_from_mesh(
            self,
            mesh,
            reference_face_area=REFERENCE_FACE_AREA_MM2,
            min_samples_per_face=1):
        """
        Build a PCA point cloud by repeating face centroids weighted by area.
        """
        vertices = np.array(
            [[v.X, v.Y, v.Z] for v in mesh.Vertices],
            dtype=np.float64,
        )
        if mesh.Faces.Count == 0:
            return vertices

        samples = []
        ref_area = max(reference_face_area, 1e-6)
        for face_idx in range(mesh.Faces.Count):
            face = mesh.Faces[face_idx]
            if face.IsTriangle:
                triangles = [[face.A, face.B, face.C]]
            elif face.IsQuad:
                triangles = [
                    [face.A, face.B, face.C],
                    [face.A, face.C, face.D],
                ]
            else:
                continue

            for tri in triangles:
                v0, v1, v2 = (
                    vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
                )
                area = self._triangle_area(v0, v1, v2)
                count = max(
                    min_samples_per_face,
                    int(round(area / ref_area)),
                )
                centroid = (v0 + v1 + v2) / 3.0
                samples.extend([centroid] * count)

        if not samples:
            return vertices
        return np.vstack(samples)

    def sample_points_for_pca_3d(self, geometry):
        """
        Collect area-weighted PCA samples from mesh or brep geometry.
        NOTE: CUrrently not used due to long runtime
        """
        if isinstance(geometry, Rhino.Geometry.Mesh):
            return self.sample_points_area_weighted_from_mesh(geometry)

        if isinstance(geometry, Rhino.Geometry.Brep):
            mp = Rhino.Geometry.MeshingParameters.Default
            brep_meshes = Rhino.Geometry.Mesh.CreateFromBrep(geometry, mp)
            if brep_meshes:
                chunks = [
                    self.sample_points_area_weighted_from_mesh(m)
                    for m in brep_meshes
                ]
                return np.vstack(chunks)

            return np.array(
                [[p.Location.X, p.Location.Y, p.Location.Z]
                 for p in geometry.Vertices],
                dtype=np.float64,
            )

        raise RuntimeError(
            'Area-weighted 3D sampling not implemented for geometry of type '
            f'{type(geometry)}!'
        )

    def compute_obb_3d(self, points):
        """
        Compute object oriented bounding box for 3D points using PCA.
        Returns unsorted dimensions and bounding box origin.
        """
        # Apply PCA to find principal axes
        pca = PCA(n_components=3)
        pca.fit(points)

        # Get principal components (eigenvectors)
        principal_components = pca.components_

        # Ensure right-handed coordinate system
        # Check if determinant is positive (right-handed)
        det = np.linalg.det(principal_components)
        if det < 0:
            # Flip the third component to ensure right-handedness
            principal_components[2] = -principal_components[2]

        # Transform points to PCA space using original component order
        pca_points = np.dot(points, principal_components.T)

        # Find bounds in PCA space
        min_bounds = np.min(pca_points, axis=0)
        max_bounds = np.max(pca_points, axis=0)

        # Compute unsorted dimensions (keep original PCA axis order)
        dimensions = max_bounds - min_bounds

        # Find bounding box center in PCA space
        # Since component is centered at origin, bbx_origin is just the
        # bounding box center in PCA space
        bbx_origin = (min_bounds + max_bounds) / 2.0

        return dimensions.tolist(), principal_components, bbx_origin.tolist()

    def minimum_bounding_rectangle(self, points):
        """
        Compute minimum bounding rectangle for 2D points.
        Returns rectangle corners and angle.
        """
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

                # Create the rectangle in the rotated space and then rotate it
                # back
                best_rectangle = np.array([
                    [min_x, min_y],
                    [max_x, min_y],
                    [max_x, max_y],
                    [min_x, max_y]
                ])

                inv_rot_matrix = np.array([
                    [cos_angle, sin_angle],
                    [-sin_angle, cos_angle]
                ])
                best_rectangle = np.dot(best_rectangle, inv_rot_matrix.T)

        return best_rectangle, best_angle

    def compute_obb_2d(self, points, height):
        """
        Compute object oriented bounding box for extrusions using the
        minimum bounding rectangle method to find optimal 2D orientation.
        Returns unsorted dimensions and bounding box origin.
        """
        # Extract only X and Y coordinates for 2D analysis
        points_2d = points[:, :2]

        # Use the minimum bounding rectangle method to find optimal orientation
        mbr, optimal_angle = self.minimum_bounding_rectangle(points_2d)

        # The optimal_angle is the angle of the edge vector that gives
        # minimum area. To align this edge with the x-axis, we need to
        # rotate by -optimal_angle. This matches the logic in
        # minimum_bounding_rectangle
        cos_angle = np.cos(-optimal_angle)
        sin_angle = np.sin(-optimal_angle)

        # Rotate points to the optimal orientation
        rot_matrix = np.array([
            [cos_angle, -sin_angle],
            [sin_angle, cos_angle]
        ])
        rotated_points = np.dot(points_2d, rot_matrix.T)

        # Compute dimensions in the rotated coordinate system
        min_x = np.min(rotated_points[:, 0])
        max_x = np.max(rotated_points[:, 0])
        min_y = np.min(rotated_points[:, 1])
        max_y = np.max(rotated_points[:, 1])

        x_dim = max_x - min_x
        y_dim = max_y - min_y

        # Find bounding box center in rotated 2D space
        bbx_center_2d = [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0]

        # Find Z center (since component is centered, this should be near 0)
        min_z = np.min(points[:, 2])
        max_z = np.max(points[:, 2])
        z_center = (min_z + max_z) / 2.0

        # Since component is centered at origin, bbx_origin is the bounding
        # box center in rotated 2D space + Z center
        bbx_origin_2d = [bbx_center_2d[0], bbx_center_2d[1], z_center]

        # Ensure X is the longest dimension for consistency
        if x_dim >= y_dim:
            dimensions = [x_dim, y_dim, height]
            # PCA frame aligns with the optimal orientation
            principal_components = np.array([
                [cos_angle, -sin_angle, 0],  # X axis = long axis
                [sin_angle, cos_angle, 0],   # Y axis = short axis
                [0, 0, 1]                    # Z axis stays vertical
            ])
        else:
            # Swap dimensions - the longer dimension should be X
            dimensions = [y_dim, x_dim, height]
            # Rotate by 90 degrees to make Y the X axis
            cos_angle_90 = np.cos(-optimal_angle + np.pi / 2)
            sin_angle_90 = np.sin(-optimal_angle + np.pi / 2)
            principal_components = np.array([
                [cos_angle_90, -sin_angle_90, 0],  # X axis = long axis
                [sin_angle_90, cos_angle_90, 0],   # Y axis = short axis
                [0, 0, 1]                          # Z axis stays vertical
            ])

        return dimensions, principal_components, bbx_origin_2d

    def rhino_xform(self, transformation_matrix) -> Rhino.Geometry.Transform:
        """
        Convert numpy transformation matrix to Rhino Transform.
        """
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

    def process_geometry(self, geometry: Rhino.Geometry.GeometryBase):
        """
        Process geometry to extract points and determine if 3D.
        Returns points array and boolean indicating if 3D.
        """
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
            compute_3d = False
        # HANDLE MESH
        elif isinstance(geometry, Rhino.Geometry.Mesh):
            points = np.array([[p.X, p.Y, p.Z] for p in geometry.Vertices])
            compute_3d = True
        # HANDLE POINT CLOUD
        elif isinstance(geometry, Rhino.Geometry.PointCloud):
            points = np.array([
                [geometry[i].Location.X,
                 geometry[i].Location.Y,
                 geometry[i].Location.Z]
                for i in range(geometry.Count)
            ])
            compute_3d = True
        # IF NOT ONE OF THESE GEOMETRY TYPES
        else:
            raise RuntimeError('Geometry processing not implemented '
                               f'for geometry of type {type(geometry)}!')
        # return results
        return points, compute_3d

    def validate_uuid(self, uuid_to_test: str, version: int = 4) -> bool:
        """
        Check if uuid_to_test is a valid UUID.
        Returns True if uuid_to_test is a valid UUID, otherwise False.
        """
        try:
            uuid_obj = uuid.UUID(uuid_to_test, version=version)
        except ValueError:
            return False
        return str(uuid_obj) == uuid_to_test

    def get_pending_assets_root(self) -> str:
        """Root directory for staged identity mesh PLY files."""
        if platform.system() == 'Windows':
            base_path = os.path.expandvars('%APPDATA%')
            return os.path.join(
                base_path,
                'DDU_CSC',
                'pending_snapshot_assets'
            )
        base_path = os.path.expanduser('~')
        return os.path.join(
            base_path, 'Library', 'Application Support', 'DDU_CSC',
            'pending_snapshot_assets',
        )

    def get_snapshot_assets_dir(self, snapshot_id: str) -> str:
        return os.path.join(self.get_pending_assets_root(), snapshot_id)

    def get_mesh_primitive_dir(
            self,
            snapshot_id: str,
            primitive_index: int
    ) -> str:
        return os.path.join(
            self.get_snapshot_assets_dir(snapshot_id),
            'meshes',
            str(primitive_index),
        )

    def get_point_cloud_staged_path(
            self,
            snapshot_id: str,
            primitive_index: int) -> str:
        return os.path.join(
            self.get_snapshot_assets_dir(snapshot_id),
            'point_clouds',
            f'{primitive_index}.ply',
        )

    def write_staging_manifest(
            self,
            identity_id: str,
            snapshot_id: str,
            mesh_primitives: dict = None,
            point_cloud_primitives: dict = None):
        """Write manifest.json for AddComponentSnapshot upload handoff."""
        manifest = {
            'identity_id': identity_id,
            'snapshot_id': snapshot_id,
            'coordinate_frame': 'rhino_z_up',
        }
        if mesh_primitives:
            manifest['mesh_primitives'] = mesh_primitives
        if point_cloud_primitives:
            manifest['point_cloud_primitives'] = point_cloud_primitives
        assets_dir = self.get_snapshot_assets_dir(snapshot_id)
        os.makedirs(assets_dir, exist_ok=True)
        manifest_path = os.path.join(assets_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as handle:
            json.dump(manifest, handle, indent=2)

    def clear_pending_snapshot_assets_directory(self):
        """Clear all staged pending_snapshot_assets (not Session cache)."""
        try:
            assets_dir = self.get_pending_assets_root()
            if os.path.exists(assets_dir):
                import shutil
                shutil.rmtree(assets_dir, ignore_errors=True)
                os.makedirs(assets_dir, exist_ok=True)
                self._addRemark(
                    f'Cleared pending_snapshot_assets: {assets_dir}'
                )
                return True
            self._addRemark('pending_snapshot_assets does not exist yet')
            return True
        except Exception as e:
            self._addWarning(
                f'Failed to clear pending_snapshot_assets: {str(e)}'
            )
            return False

    def reduce_mesh(
        self, mesh: Rhino.Geometry.Mesh, target_face_count: int
    ) -> Rhino.Geometry.Mesh:
        """
        Reduce a mesh to a target face count using Rhino's mesh reduction.
        Returns the reduced mesh.
        """
        reduced_mesh = mesh.Duplicate()
        reduced_mesh.Reduce(target_face_count, True, 5, False, True)
        reduced_mesh.Faces.ConvertQuadsToTriangles()
        reduced_mesh.Compact()
        return reduced_mesh

    def _stage_mesh_ply_files(
            self,
            snapshot_id: str,
            primitive_index: int,
            detailed_mesh,
            reduced_mesh,
            default_rgb,
            mesh_primitive_threshold: int,
            mesh_reduced_threshold: int,
            mesh_reduced_target: int,
            mesh_primitive_target: int):
        """
        Reduce meshes if needed and write detailed.ply / reduced.ply for one
        primitive index. Returns (primitive_mesh, resolutions_on_disk).
        """
        if detailed_mesh is None:
            return None, []

        face_count = detailed_mesh.Faces.Count
        reduced = None
        primitive = detailed_mesh
        resolutions = []

        primitive_dir = self.get_mesh_primitive_dir(
            snapshot_id, primitive_index)
        detailed_path = os.path.join(primitive_dir, 'detailed.ply')
        reduced_path = os.path.join(primitive_dir, 'reduced.ply')

        if os.path.exists(detailed_path) or os.path.exists(reduced_path):
            self._addWarning(
                f'PLY files already exist for snapshot {snapshot_id} '
                f'primitive {primitive_index}; skipping overwrite.'
            )
            if face_count > mesh_reduced_threshold:
                primitive = self.reduce_mesh(
                    detailed_mesh, mesh_primitive_target)
            elif face_count > mesh_primitive_threshold:
                primitive = self.reduce_mesh(
                    detailed_mesh, mesh_primitive_target)
            return primitive, []

        save_detailed = face_count > mesh_primitive_target
        save_reduced = face_count > mesh_reduced_threshold

        if face_count > mesh_reduced_threshold:
            reduced = self.reduce_mesh(detailed_mesh, mesh_reduced_target)
            primitive = self.reduce_mesh(detailed_mesh, mesh_primitive_target)
        elif face_count > mesh_primitive_threshold:
            primitive = self.reduce_mesh(detailed_mesh, mesh_primitive_target)

        try:
            if save_detailed:
                self.save_rhino_mesh_as_ply_binary(
                    detailed_mesh, detailed_path, default_rgb)
                resolutions.append('detailed')
            if save_reduced and reduced is not None:
                self.save_rhino_mesh_as_ply_binary(
                    reduced, reduced_path, default_rgb)
                resolutions.append('reduced')
            if resolutions:
                self._addRemark(
                    f'Staged PLY for primitive {primitive_index}: '
                    f'{", ".join(resolutions)}'
                )
        except Exception as e:
            self._addWarning(f'Failed to stage PLY files: {str(e)}')
            resolutions = []

        return primitive, resolutions

    def process_mesh_geometry(
        self,
        geometry: Rhino.Geometry.Mesh,
        snapshot_id: str,
        default_rgb,
        mesh_primitive_threshold: int = 8000,
        mesh_reduced_threshold: int = 15000,
        mesh_reduced_target: int = 10000,
        mesh_primitive_target: int = 500,
    ) -> tuple:
        """
        Returns (original, reduced, primitive_mesh, mesh_primitives dict).
        """
        primitive_mesh, resolutions = self._stage_mesh_ply_files(
            snapshot_id,
            0,
            geometry,
            None,
            default_rgb,
            mesh_primitive_threshold,
            mesh_reduced_threshold,
            mesh_reduced_target,
            mesh_primitive_target,
        )
        mesh_primitives = {}
        if resolutions:
            mesh_primitives['0'] = resolutions
        reduced_mesh = None
        if geometry.Faces.Count > mesh_reduced_threshold:
            reduced_mesh = self.reduce_mesh(geometry, mesh_reduced_target)
        return geometry, reduced_mesh, primitive_mesh, mesh_primitives

    def process_multiple_meshes_geometry(
            self,
            meshes,
            snapshot_id,
            default_rgb,
            mesh_primitive_threshold: int = 8000,
            mesh_reduced_threshold: int = 15000,
            mesh_reduced_target: int = 10000,
            mesh_primitive_target: int = 500):
        """Returns (primitive_meshes, mesh_primitives dict)."""
        if not meshes:
            return [], {}

        primitive_meshes = []
        mesh_primitives = {}

        for index, mesh in enumerate(meshes):
            if mesh is None:
                primitive_meshes.append(None)
                continue
            primitive_mesh, resolutions = self._stage_mesh_ply_files(
                snapshot_id,
                index,
                mesh,
                None,
                default_rgb,
                mesh_primitive_threshold,
                mesh_reduced_threshold,
                mesh_reduced_target,
                mesh_primitive_target,
            )
            primitive_meshes.append(primitive_mesh)
            if resolutions:
                mesh_primitives[str(index)] = resolutions

        return primitive_meshes, mesh_primitives

    def _stage_point_cloud_ply(
            self,
            snapshot_id: str,
            primitive_index: int,
            cloud,
            staging_threshold: int = POINT_CLOUD_STAGING_THRESHOLD):
        """Stage full PLY when point count exceeds inline preview cap."""
        if cloud is None or cloud.Count == 0:
            return {}

        if cloud.Count <= staging_threshold:
            return {}

        ply_path = self.get_point_cloud_staged_path(
            snapshot_id, primitive_index)
        if os.path.exists(ply_path):
            self._addWarning(
                f'Point cloud PLY already exists for snapshot {snapshot_id} '
                f'primitive {primitive_index}; skipping overwrite.'
            )
            return {}

        try:
            self.save_rhino_point_cloud_as_ply_binary(cloud, ply_path)
            self._addRemark(
                f'Staged point cloud PLY for primitive {primitive_index}'
            )
            return {str(primitive_index): ['ply']}
        except Exception as e:
            self._addWarning(f'Failed to stage point cloud PLY: {str(e)}')
            return {}

    def process_point_cloud_geometry(
            self,
            cloud: Rhino.Geometry.PointCloud,
            snapshot_id: str,
            staging_threshold: int = POINT_CLOUD_STAGING_THRESHOLD):
        """Returns (original, inline_cloud, point_cloud_primitives dict)."""
        staged = self._stage_point_cloud_ply(
            snapshot_id, 0, cloud, staging_threshold)
        return cloud, cloud, staged

    def process_multiple_point_clouds_geometry(
            self,
            clouds,
            snapshot_id: str,
            staging_threshold: int = POINT_CLOUD_STAGING_THRESHOLD):
        """Returns (clouds, point_cloud_primitives dict)."""
        if not clouds:
            return [], {}

        point_cloud_primitives = {}
        for index, cloud in enumerate(clouds):
            if cloud is None:
                continue
            staged = self._stage_point_cloud_ply(
                snapshot_id, index, cloud, staging_threshold)
            point_cloud_primitives.update(staged)

        return clouds, point_cloud_primitives

    def compute_pca_for_multiple_point_clouds(self, clouds):
        """
        Compute PCA for multiple point clouds as a whole assembly.
        Returns dimensions, principal components, translation vector,
        and bbx_origin.
        """
        if not clouds or len(clouds) == 0:
            return None, None, None, None

        all_points = []
        for cloud in clouds:
            if cloud is None:
                continue
            for i in range(cloud.Count):
                loc = cloud[i].Location
                all_points.append([loc.X, loc.Y, loc.Z])

        if not all_points:
            return None, None, None, None

        points_array = np.array(all_points)
        centroid = np.mean(points_array, axis=0)
        translation_vector = -centroid
        centered_points = points_array + translation_vector
        dimensions, principal_components, bbx_origin = (
            self.compute_obb_3d(centered_points)
        )
        return dimensions, principal_components, translation_vector, bbx_origin

    def compute_pca_for_multiple_meshes(self, meshes):
        """
        Compute PCA for multiple meshes as a whole assembly.
        Centers the assembly at origin before computing PCA.
        Returns dimensions, principal components, translation vector,
        and bbx_origin.
        """
        if not meshes or len(meshes) == 0:
            return None, None, None, None

        all_points = []
        for mesh in meshes:
            if mesh is None:
                continue
            for vertex in mesh.Vertices:
                all_points.append([vertex.X, vertex.Y, vertex.Z])

        if not all_points:
            return None, None, None, None

        points_array = np.array(all_points)

        # Center the assembly at origin (like single meshes)
        # Compute centroid of all points
        centroid = np.mean(points_array, axis=0)
        translation_vector = -centroid

        # Center the points
        centered_points = points_array + translation_vector

        # Compute PCA for the centered combined geometry
        dimensions, principal_components, bbx_origin = (
            self.compute_obb_3d(centered_points)
        )

        return dimensions, principal_components, translation_vector, bbx_origin

    def compute_pca_for_first_geometry_only(self, geometries):
        """
        Compute PCA from geometry at index 0 (Mesh or PointCloud).
        The same translation is applied to every item in the list.
        """
        first_geom = geometries[0]
        if first_geom is None:
            raise ValueError(
                'Geometry at index 0 must be set for multiple inputs '
                'when Assembly=False.'
            )
        centered_geom, translation_vector = (
            self.center_geometry_at_origin(first_geom)
        )
        centered_points, _ = self.process_geometry(centered_geom)
        dimensions, principal_components, bbx_origin = (
            self.compute_obb_3d(centered_points)
        )
        return dimensions, principal_components, translation_vector, bbx_origin

    def compute_pca_for_mixed_geometry(self, geometries):
        """
        Compute PCA from combined mesh vertices and point-cloud points.
        Used when Assembly=True and the geometry list mixes types.
        """
        all_points = []
        for geom in geometries:
            if geom is None:
                continue
            if isinstance(geom, Rhino.Geometry.Mesh):
                for vertex in geom.Vertices:
                    all_points.append([vertex.X, vertex.Y, vertex.Z])
            elif isinstance(geom, Rhino.Geometry.PointCloud):
                for i in range(geom.Count):
                    loc = geom[i].Location
                    all_points.append([loc.X, loc.Y, loc.Z])

        if not all_points:
            return None, None, None, None

        points_array = np.array(all_points)
        centroid = np.mean(points_array, axis=0)
        translation_vector = -centroid
        centered_points = points_array + translation_vector
        dimensions, principal_components, bbx_origin = (
            self.compute_obb_3d(centered_points)
        )
        return dimensions, principal_components, translation_vector, bbx_origin

    def process_mixed_geometry_list(
            self,
            geometries,
            snapshot_id: str,
            default_rgb,
            translation_vector,
            mesh_primitive_threshold: int,
            mesh_reduced_threshold: int,
            mesh_reduced_target: int,
            mesh_primitive_target: int,
            point_cloud_staging_threshold: int = POINT_CLOUD_STAGING_THRESHOLD):  # NOQA
        """
        Center, stage, and build inline primitives for a multi-item geometry
        list that may contain Meshes and/or PointClouds.
        """
        mesh_primitives = {}
        point_cloud_primitives = {}
        meshes_data = []
        point_clouds_data = []
        mesh_index = 0
        point_cloud_index = 0

        translation_xform = Rhino.Geometry.Transform.Translation(
            translation_vector[0],
            translation_vector[1],
            translation_vector[2],
        )

        for geom in geometries:
            if geom is None:
                continue

            centered = geom.Duplicate()
            centered.Transform(translation_xform)

            if isinstance(geom, Rhino.Geometry.Mesh):
                primitive_mesh, resolutions = self._stage_mesh_ply_files(
                    snapshot_id,
                    mesh_index,
                    centered,
                    None,
                    default_rgb,
                    mesh_primitive_threshold,
                    mesh_reduced_threshold,
                    mesh_reduced_target,
                    mesh_primitive_target,
                )
                if resolutions:
                    mesh_primitives[str(mesh_index)] = resolutions
                meshes_data.append(
                    self.mesh_to_inline_primitive(
                        primitive_mesh or centered,
                        default_rgb,
                    )
                )
                mesh_index += 1
            elif isinstance(geom, Rhino.Geometry.PointCloud):
                staged = self._stage_point_cloud_ply(
                    snapshot_id,
                    point_cloud_index,
                    centered,
                    point_cloud_staging_threshold,
                )
                point_cloud_primitives.update(staged)
                point_clouds_data.append(
                    self.point_cloud_to_inline_primitive(
                        centered,
                        max_points=POINT_CLOUD_INLINE_MAX,
                    )
                )
                point_cloud_index += 1
            else:
                raise RuntimeError(
                    'Mixed geometry lists support Mesh and PointCloud only; '
                    f'got {type(geom).__name__}'
                )

        geometry = {}
        if meshes_data:
            geometry['meshes'] = meshes_data
        if point_clouds_data:
            geometry['point_clouds'] = point_clouds_data
        return geometry, mesh_primitives, point_cloud_primitives

    def RunScript(self,
            ClearLocalStorage: bool,
            IdentityID: str,
            SnapshotID: str,
            Name: str,
            Complexity: int,
            Fragment: bool,
            Assembly: bool,
            Color: System.Drawing.Color,
            Location: Rhino.Geometry.Vector3d,
            Geometry: System.Collections.Generic.List[Rhino.Geometry.GeometryBase],
            MarkerPoints: System.Collections.Generic.List[Rhino.Geometry.Point3d],
            Condition,
            Notes,
            Quantity,
            Virtual: bool,
            Reinforcements: System.Collections.Generic.List[object]):

        # MESH REDUCTION SETTINGS
        # If mesh has tc above this but below reduced threshold,
        # only the primitive version will be computed
        MESH_PRIMITIVE_THRESHOLD = 8000
        # If mesh has tc above this, reduced and primitive versions
        # will be created
        MESH_REDUCED_THRESHOLD = 15000
        # target tc for reduced mesh
        MESH_REDUCED_TARGET = 10000
        # target tc for primitive mesh
        MESH_PRIMITIVE_TARGET = 500

        SnapshotData = Grasshopper.DataTree[System.Object]()
        try:
            if ClearLocalStorage:
                self._addRemark(
                    'Clearing pending_snapshot_assets directory...'
                )
                if self.clear_pending_snapshot_assets_directory():
                    self.Component.Message = (
                        'Local storage cleared successfully'
                    )
                else:
                    self.Component.Message = 'Failed to clear local storage'
                return SnapshotData

            self._addRemark(
                'Initializing snapshot create '
                'payload with schema validation...'
            )

            if not IdentityID:
                msg = 'Input IdentityID failed to collect data!'
                self._addWarning(msg)
                return SnapshotData
            elif not self.validate_uuid(IdentityID):
                msg = 'Input IdentityID is not a valid UUID! Aborting...'
                self._addError(msg)
                return SnapshotData

            if not SnapshotID:
                SnapshotID = str(uuid.uuid4())
                self._addRemark(f'Generated snapshot UUID: {SnapshotID}')
            elif not self.validate_uuid(SnapshotID):
                msg = 'Input SnapshotID is not a valid UUID! Aborting...'
                self._addError(msg)
                return SnapshotData

            if Complexity is None:
                msg = 'Input Complexity failed to collect data!'
                self._addWarning(msg)
                return SnapshotData
            if (not isinstance(Complexity, int) or
                    Complexity < 0 or Complexity > 3):
                msg = 'Input Complexity must be an integer between 0 and 3!'
                self._addError(msg)
                return SnapshotData

            if Fragment is None:
                Fragment = False
            if Assembly is None:
                Assembly = False
            if Virtual is None:
                Virtual = False

            location_data = None
            if Location is not None:
                location_data = {
                    'lat': Location.X,
                    'lon': Location.Y,
                }

            if Condition is not None:
                try:
                    Condition = int(Condition)
                except Exception:
                    self._addWarning(
                        'Input Condition must be an integer in '
                        '{0, 1, 2, 3}. Ignoring provided value: '
                        f'{Condition!r}.'
                    )
                    Condition = None
                if Condition not in (0, 1, 2, 3):
                    self._addWarning(
                        'Input Condition must be in {0, 1, 2, 3}. '
                        f'Ignoring out-of-range value: {Condition}.'
                    )
                    Condition = None

            if Notes is not None:
                Notes = str(Notes)
            if Quantity is not None:
                try:
                    Quantity = int(Quantity)
                except (TypeError, ValueError):
                    self._addWarning(
                        'Input Quantity must be an '
                        f'integer; ignoring {Quantity!r}'
                    )
                    Quantity = 1
                if Quantity < 1 or Quantity > 999_999:
                    self._addWarning(
                        'Input Quantity must be between 1 and 999999; using 1'
                    )
                    Quantity = 1

            if not Color:
                msg = ('Input Color failed to collect data. '
                       'Will use Grey as default Color.')
                self._addRemark(msg)
                Color = System.Drawing.Color.FromArgb(255, 175, 175, 175)
            if not Geometry:
                msg = 'Input Geometry failed to collect data!'
                self._addWarning(msg)
                return SnapshotData

            # TYPE FILTERING
            if not Geometry or len(Geometry) == 0:
                msg = 'Input Geometry is invalid!'
                self._addError(msg)
                return SnapshotData

            is_mixed_geometry = False
            is_point_cloud_assembly = False

            # Check if single or multiple objects
            if len(Geometry) == 1:
                # Single object validation
                single_geometry = Geometry[0]
                if not isinstance(
                    single_geometry,
                    (Rhino.Geometry.Mesh,
                     Rhino.Geometry.Extrusion,
                     Rhino.Geometry.PointCloud)
                ):
                    msg = (
                        'Expected a Mesh, Extrusion, or PointCloud '
                        'as geometry input! Please ensure and try again.'
                    )
                    raise ValueError(msg)
            else:
                non_null = [g for g in Geometry if g is not None]
                if not non_null:
                    msg = 'Input Geometry contains only null entries!'
                    raise ValueError(msg)
                for i, geom in enumerate(Geometry):
                    if geom is not None and not isinstance(
                            geom,
                            (Rhino.Geometry.Mesh,
                             Rhino.Geometry.PointCloud)):
                        msg = (
                            f'Geometry at index {i} must be Mesh or '
                            f'PointCloud; got {type(geom).__name__}.'
                        )
                        raise ValueError(msg)
                has_mesh = any(
                    isinstance(g, Rhino.Geometry.Mesh) for g in non_null)
                has_point_cloud = any(
                    isinstance(g, Rhino.Geometry.PointCloud) for g in non_null)
                is_mixed_geometry = has_mesh and has_point_cloud
                is_point_cloud_assembly = has_point_cloud and not has_mesh

            self.Component.Message = 'Processing snapshot...'
            default_rgb = (Color.R, Color.G, Color.B)

            # Process geometry to extract points and compute PCA
            if len(Geometry) == 1:
                # Handle single geometry (existing logic)
                single_geometry = Geometry[0]
                # Center geometry at world origin FIRST
                (centered_geometry, translation_vector) = (
                    self.center_geometry_at_origin(single_geometry)
                )
                centered_points, compute_3d = self.process_geometry(
                    centered_geometry
                )
                if compute_3d:
                    # centered_points = self.sample_points_for_pca_3d(
                    #     centered_geometry
                    # )
                    dimensions, principal_components, bbx_origin = (
                        self.compute_obb_3d(centered_points))
                else:
                    # 2D APPROACH, i.e. used for Extrusions
                    height = centered_geometry.PathStart.DistanceTo(
                        centered_geometry.PathEnd
                    )
                    dimensions, principal_components, bbx_origin = (
                        self.compute_obb_2d(
                            centered_points, height)
                    )
            else:
                if Assembly:
                    if is_mixed_geometry:
                        (dimensions, principal_components,
                         translation_vector, bbx_origin) = (
                            self.compute_pca_for_mixed_geometry(Geometry))
                    elif is_point_cloud_assembly:
                        (dimensions, principal_components,
                         translation_vector, bbx_origin) = (
                            self.compute_pca_for_multiple_point_clouds(
                                Geometry))
                    else:
                        (dimensions, principal_components,
                         translation_vector, bbx_origin) = (
                            self.compute_pca_for_multiple_meshes(Geometry))
                else:
                    (dimensions, principal_components, translation_vector,
                     bbx_origin) = (
                        self.compute_pca_for_first_geometry_only(Geometry))
                centered_geometry = None
                compute_3d = True

            schema = self.get_snapshot_payload_schema()

            # Process marker points - apply same transformation as geometry
            marker_points_data = []
            if MarkerPoints and len(MarkerPoints) > 0:
                for point in MarkerPoints:
                    if point is not None:
                        # Apply the same translation vector used for
                        # centering geometry
                        transformed_point = [
                            point.X + translation_vector[0],
                            point.Y + translation_vector[1],
                            point.Z + translation_vector[2]
                        ]
                        marker_points_data.append(transformed_point)

            payload = self.build_snapshot_payload(
                SnapshotID, IdentityID, Name, Complexity,
                Fragment, Assembly, Color, dimensions, location_data,
                principal_components, Condition, Notes, Quantity, Virtual,
            )
            payload['bbx_origin'] = bbx_origin
            if marker_points_data:
                payload['marker_points'] = marker_points_data

            mesh_primitives = {}
            point_cloud_primitives = {}

            # Process geometry input based on type
            if len(Geometry) == 1:
                # HANDLE SINGLE GEOMETRY
                single_geometry = Geometry[0]
                if isinstance(single_geometry, Rhino.Geometry.Mesh):
                    # Process single mesh
                    (_original_mesh,
                     _reduced_mesh,
                     primitive_mesh,
                     staged) = self.process_mesh_geometry(
                        centered_geometry,
                        SnapshotID,
                        default_rgb,
                        mesh_primitive_threshold=MESH_PRIMITIVE_THRESHOLD,
                        mesh_reduced_threshold=MESH_REDUCED_THRESHOLD,
                        mesh_reduced_target=MESH_REDUCED_TARGET,
                        mesh_primitive_target=MESH_PRIMITIVE_TARGET,
                    )
                    mesh_primitives.update(staged)
                    payload['geometry'] = {
                        'meshes': [
                            self.mesh_to_inline_primitive(
                                primitive_mesh, default_rgb)
                        ],
                    }

                elif isinstance(single_geometry, Rhino.Geometry.Extrusion):
                    # Handle single extrusion (existing logic)
                    # Get the profile curve from the CENTERED geometry and
                    # convert to polyline
                    if centered_geometry.ProfileCount > 1:
                        raise RuntimeError(
                            'Extrusion has more than one profile!'
                        )
                    # Get first profile
                    profile_curve = centered_geometry.Profile3d(0, 0.0)
                    if profile_curve is None:
                        raise RuntimeError('Extrusion has no profile curve!')

                    # Convert profile to polyline
                    _tgpr, polyline = profile_curve.TryGetPolyline()
                    if _tgpr is False:
                        polyline = profile_curve.ToPolyline(0.01, 0.01, 0, 0)
                    if polyline is None:
                        raise RuntimeError(
                            'Failed to convert profile curve to polyline!'
                        )

                    # Get height
                    height = centered_geometry.PathStart.DistanceTo(
                        centered_geometry.PathEnd)

                    payload['geometry'] = {
                        'extrusions': [{
                            'profile': [[p.X, p.Y] for p in polyline],
                            'height': height,
                        }],
                    }

                elif isinstance(single_geometry, Rhino.Geometry.PointCloud):
                    (_original_cloud,
                     _inline_cloud,
                     staged) = self.process_point_cloud_geometry(
                        centered_geometry,
                        SnapshotID,
                        staging_threshold=POINT_CLOUD_STAGING_THRESHOLD,
                    )
                    point_cloud_primitives.update(staged)
                    payload['geometry'] = {
                        'point_clouds': [
                            self.point_cloud_to_inline_primitive(
                                centered_geometry,
                                max_points=POINT_CLOUD_INLINE_MAX,
                            )
                        ],
                    }
            else:
                geometry_data, staged_meshes, staged_point_clouds = (
                    self.process_mixed_geometry_list(
                        Geometry,
                        SnapshotID,
                        default_rgb,
                        translation_vector,
                        mesh_primitive_threshold=MESH_PRIMITIVE_THRESHOLD,
                        mesh_reduced_threshold=MESH_REDUCED_THRESHOLD,
                        mesh_reduced_target=MESH_REDUCED_TARGET,
                        mesh_primitive_target=MESH_PRIMITIVE_TARGET,
                        point_cloud_staging_threshold=(
                            POINT_CLOUD_STAGING_THRESHOLD
                        ),
                    )
                )
                payload['geometry'] = geometry_data
                mesh_primitives.update(staged_meshes)
                point_cloud_primitives.update(staged_point_clouds)

            centered_reinforcements = self.build_centered_reinforcements(
                Reinforcements,
                translation_vector,
            )
            if centered_reinforcements:
                payload['geometry']['reinforcements'] = centered_reinforcements

            if mesh_primitives or point_cloud_primitives:
                self.write_staging_manifest(
                    IdentityID,
                    SnapshotID,
                    mesh_primitives=mesh_primitives or None,
                    point_cloud_primitives=point_cloud_primitives or None,
                )

            if not self.validate_snapshot_payload(payload, schema):
                self._addWarning(
                    'Snapshot payload validation failed, but continuing...'
                )

            SnapshotData = json.dumps(payload)

            self.Component.Message = (
                f'Built snapshot payload {SnapshotID} '
                f'for identity {IdentityID}'
            )
            self._addRemark(
                f'Created snapshot payload {SnapshotID}'
            )

            return SnapshotData

        except ValueError as e:
            msg = f'Validation error: {str(e)}'
            self._addError(msg)

        except RuntimeError as e:
            msg = f'Runtime error: {str(e)}'
            self._addError(msg)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            raise e

        return SnapshotData
