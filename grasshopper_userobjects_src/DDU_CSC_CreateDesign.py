# -*- coding: utf-8 -*-
#! python3
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn
# r: robust-laplacian
# r: potpourri3d

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportUnedfinedVariable] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateDesign'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'CreateDesign'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Creates a design JSON string from component data, ready for posting to '
    'the catalogue. Validates input against design schema and generates '
    'complete design payload with UUID, timestamps, and component references. '
    'Does NOT post the design - only generates the JSON string.'
)


class CSC_CreateDesign(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251023
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def _get_hardcoded_schema(self):
        """Get hardcoded design schema fallback."""
        return {
            "type": "object",
            "properties": {
                "_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "created": {"type": "string"},
                "lastmodified": {"type": "string"},
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "component": {"type": "string"},
                            "iframe": {
                                "type": "object",
                                "properties": {
                                    "o": {"type": "array",
                                          "items": {"type": "number"}},
                                    "x": {"type": "array",
                                          "items": {"type": "number"}},
                                    "y": {"type": "array",
                                          "items": {"type": "number"}},
                                    "z": {"type": "array",
                                          "items": {"type": "number"}}
                                },
                                "required": ["o", "x", "y", "z"]
                            }
                        },
                        "required": ["component", "iframe"]
                    }
                },
                "additional_geometry": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "iframe": {
                                "type": "object",
                                "properties": {
                                    "o": {"type": "array",
                                          "items": {"type": "number"}},
                                    "x": {"type": "array",
                                          "items": {"type": "number"}},
                                    "y": {"type": "array",
                                          "items": {"type": "number"}},
                                    "z": {"type": "array",
                                          "items": {"type": "number"}}
                                },
                                "required": ["o", "x", "y", "z"]
                            },
                            "geometry": {
                                "type": "object",
                                "properties": {
                                    "meshes": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "v": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "number"}
                                                    }
                                                },
                                                "f": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "integer"}
                                                    }
                                                },
                                                "c": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "integer"}
                                                    }
                                                }
                                            },
                                            "required": ["v", "f"]
                                        }
                                    }
                                },
                                "required": ["meshes"]
                            }
                        },
                        "required": ["id", "iframe", "geometry"]
                    }
                }
            },
            "required": ["_id", "created", "lastmodified",
                         "components", "additional_geometry"]
        }

    # Helpers -----------------------------------------------------------------
    def _compute_mesh_centroid(self, mesh):
        try:
            vmp = Rhino.Geometry.VolumeMassProperties.Compute(mesh)
            if vmp and vmp.Centroid:
                return vmp.Centroid
        except Exception:
            pass
        bbox = mesh.GetBoundingBox(True)
        return bbox.Center

    def _center_mesh_at_origin(self, mesh):
        centered = mesh.Duplicate()
        c = self._compute_mesh_centroid(centered)
        xform = Rhino.Geometry.Transform.Translation(-c.X, -c.Y, -c.Z)
        centered.Transform(xform)
        return centered, c

    def _reduce_mesh_for_design(self, mesh):
        """Reduce mesh if faces > 350, targeting ~250 faces."""
        try:
            faces = mesh.Faces.Count
            if faces > 350:
                reduced = mesh.Duplicate()
                # Parameters mirror CreateComponent.reduce_mesh behavior
                reduced.Reduce(250, True, 5, False, True)
                reduced.Faces.ConvertQuadsToTriangles()
                reduced.Compact()
                return reduced
            return mesh
        except Exception:
            return mesh

    def _mesh_to_meshes_geometry(self, mesh):
        """
        Convert a Rhino mesh to geometry.meshes entry (single-item array).
        Returns a dictionary with a single mesh entry.
        """
        try:
            vertices = [[p.X, p.Y, p.Z] for p in mesh.Vertices]
            faces = [[f[0], f[1], f[2]] for f in mesh.Faces]
            return {
                'meshes': [{
                    'v': vertices,
                    'f': faces
                }]
            }
        except Exception:
            return {'meshes': []}

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            self._addWarning('No authentication found. '
                             'Using hardcoded schema.')
            return None
        return auth_core

    def get_design_schema(self):
        """Get design schema from cache or fallback to hardcoded schema."""
        # Try to get schema from AuthCore cache first
        auth_core = self.get_auth_core_from_sticky()
        if auth_core and hasattr(auth_core, 'get_design_schema'):
            try:
                schema = auth_core.get_design_schema()
                if schema:
                    self._addRemark('Using cached design schema')
                    return schema
                else:
                    self._addWarning('Failed to get cached schema, '
                                     'using hardcoded schema')
            except Exception as e:
                self._addWarning(f'Error fetching cached schema: {str(e)}, '
                                 'using hardcoded schema')

        # Fallback to hardcoded schema
        self._addRemark('Using hardcoded design schema')
        return self._get_hardcoded_schema()

    def validate_component_data(self, component_data: Dict[str, Any],
                                schema: Dict[str, Any]) -> bool:
        """Validate component data against schema."""
        try:
            # Check if component has required fields
            if '_id' not in component_data:
                self._addWarning('Component missing _id field')
                return False

            if 'iframe' not in component_data:
                self._addWarning('Component missing iframe field')
                return False

            # Validate iframe structure
            iframe = component_data['iframe']
            required_iframe_fields = ['o', 'x', 'y', 'z']
            for field in required_iframe_fields:
                if field not in iframe:
                    self._addWarning(f'Component iframe missing {field} field')
                    return False
                if not (isinstance(iframe[field], list) or
                        len(iframe[field]) != 3):
                    self._addWarning(
                        f'Component iframe {field} must be 3D vector'
                    )
                    return False

            return True
        except Exception as e:
            self._addWarning(f'Error validating component: {str(e)}')
            return False

    def create_design_payload(self, design_name: str, design_description: str,
                              component_data_list: List[str],
                              additional_meshes=None
                              ) -> Optional[Dict[str, Any]]:
        """Create design payload from component data and additional meshes."""
        try:
            # Get design schema
            schema = self.get_design_schema()

            # Parse and validate component data
            components = []
            for i, component_json in enumerate(component_data_list):
                try:
                    component_data = json.loads(component_json)
                    if not self.validate_component_data(
                            component_data, schema):
                        self._addWarning(f'Invalid component at index {i}')
                        continue
                    component_id = component_data['_id']
                    iframe = component_data['iframe']
                    components.append(
                        {'component': component_id, 'iframe': iframe}
                    )
                except Exception as e:
                    self._addWarning(
                        f'Error processing component {i}: {str(e)}'
                    )
                    continue

            if not components:
                self._addError('No valid components found')
                return None

            # Build additional_geometry entries
            additional_geometry = []
            if additional_meshes:
                try:
                    for idx, m in enumerate(additional_meshes):
                        if m is None:
                            continue
                        if not isinstance(m, Rhino.Geometry.Mesh):
                            self._addWarning(
                                'AdditionalGeometry contains '
                                'non-mesh; skipping'
                            )
                            continue
                        centered, centroid = self._center_mesh_at_origin(m)
                        primitive = self._reduce_mesh_for_design(centered)
                        geom = self._mesh_to_meshes_geometry(primitive)
                        iframe = {
                            'o': [centroid.X, centroid.Y, centroid.Z],
                            'x': [1.0, 0.0, 0.0],
                            'y': [0.0, 1.0, 0.0],
                            'z': [0.0, 0.0, 1.0]
                        }
                        additional_geometry.append({
                            'id': str(uuid.uuid4()),
                            'iframe': iframe,
                            'geometry': geom
                        })
                except Exception as e:
                    self._addWarning(
                        f'Error processing AdditionalGeometry: {str(e)}'
                    )

            # Generate timestamps
            current_time = datetime.utcnow().isoformat() + 'Z'

            # Create design payload (client supplies UUID)
            design_payload = {
                '_id': str(uuid.uuid4()),
                'name': design_name,
                'description': design_description,
                'created': current_time,
                'lastmodified': current_time,
                'components': components,
                'additional_geometry': additional_geometry
            }

            return design_payload

        except Exception as e:
            self._addError(f'Error creating design payload: {str(e)}')
            return None

    def RunScript(self,
            DesignName: str,
            DesignDescription: str,
            ComponentData: System.Collections.Generic.List[str],
            AdditionalGeometry: System.Collections.Generic.List[Rhino.Geometry.Mesh]):
        # Initialize param descriptions
        self.InputParams[0].Description = 'Design name (mandatory)'
        self.InputParams[1].Description = 'Design description (optional)'
        self.InputParams[2].Description = 'List of component JSON strings'
        self.InputParams[3].Description = 'AdditionalGeometry (List of Mesh)'
        self.OutputParams[0].Description = (
            'Design JSON string ready for posting'
        )

        # Init outputs
        DesignJSON = Grasshopper.DataTree[str]()

        # Validate DesignName (mandatory)
        if not DesignName or not DesignName.strip():
            msg = 'Design name is mandatory and cannot be empty.'
            self._addWarning(msg)
            self.Component.Message = msg
            return DesignJSON

        # Set DesignDescription fallback
        if not DesignDescription:
            DesignDescription = 'No description provided.'

        # Validate ComponentData
        if not ComponentData:
            msg = 'Input ComponentData failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return DesignJSON

        try:
            # Create design payload
            design_payload = self.create_design_payload(
                DesignName.strip(),
                DesignDescription.strip(),
                ComponentData,
                AdditionalGeometry
            )

            if design_payload is None:
                return DesignJSON

            # Convert to JSON string
            DesignJSON = json.dumps(design_payload, indent=2)

            add_count = len(design_payload.get('additional_geometry', []))
            self.Component.Message = (
                f'Design created: {len(design_payload["components"])} '
                f'components, {add_count} add. geom.'
            )

            return DesignJSON

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
