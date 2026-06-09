#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA
import uuid  # NOQA
from datetime import datetime  # NOQA
from typing import List, Dict, Any, Optional  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateDesign'  # NOQA
ghenv.Component.NickName = 'CreateDesign'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Creates a design JSON string from compose JSON ({identity, snapshot}), '
    'ready for posting to the Catalog. Pins each placement to a specific '
    'snapshot and stores the design insertion iframe. Does NOT post '
    'the design - only generates the JSON string.'
)


class CSC_CreateDesign(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260609
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
            'Design name (mandatory)'
        )
        self.InputParams[1].Description = (
            'Design description (optional)'
        )
        self.InputParams[2].Description = (
            'List of compose JSON strings ({identity, snapshot}) with '
            'snapshot.iframe set to the design placement frame'
        )
        self.InputParams[3].Description = (
            'AdditionalGeometry (List of Mesh)'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Design JSON string ready for posting'
        )

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
                            "snapshot": {"type": "string"},
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
                        "required": ["snapshot", "iframe"]
                    }
                },
                "additional_geometry": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "_id": {"type": "string"},
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
                        "required": ["_id", "iframe", "geometry"]
                    }
                }
            },
            "required": ["_id", "created", "lastmodified",
                         "components", "additional_geometry"]
        }

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

    def _validate_iframe(self, iframe, label='iframe') -> bool:
        """Validate an insertion-frame dict."""
        if not isinstance(iframe, dict):
            self._addWarning(f'{label} must be a dictionary')
            return False
        for field in ('o', 'x', 'y', 'z'):
            if field not in iframe:
                self._addWarning(f'{label} missing {field} field')
                return False
            if (not isinstance(iframe[field], list) or
                    len(iframe[field]) != 3):
                self._addWarning(f'{label} {field} must be 3D vector')
                return False
        return True

    def validate_compose_data(self, compose_data: Dict[str, Any]) -> bool:
        """Validate compose JSON for design placement."""
        try:
            if not isinstance(compose_data, dict):
                self._addWarning('Compose data must be a dictionary')
                return False

            snapshot = compose_data.get('snapshot')
            if not isinstance(snapshot, dict):
                self._addWarning('Compose missing snapshot object')
                return False

            snapshot_id = snapshot.get('_id') or snapshot.get('id')
            if not snapshot_id:
                self._addWarning('Compose snapshot missing _id field')
                return False

            iframe = snapshot.get('iframe')
            if iframe is None:
                self._addWarning('Compose snapshot missing iframe field')
                return False

            return self._validate_iframe(iframe, 'Compose snapshot iframe')
        except Exception as e:
            self._addWarning(f'Error validating compose: {str(e)}')
            return False

    def create_design_payload(self, design_name: str, design_description: str,
                              component_data_list: List[str],
                              additional_meshes=None
                              ) -> Optional[Dict[str, Any]]:
        """Create design payload from component data and additional meshes."""
        try:
            # Warm design schema cache (fallback used when offline)
            self.get_design_schema()

            # Parse and validate compose JSON
            components = []
            for i, compose_json in enumerate(component_data_list):
                try:
                    compose_data = json.loads(compose_json)
                    if not self.validate_compose_data(compose_data):
                        self._addWarning(f'Invalid compose at index {i}')
                        continue
                    snapshot = compose_data['snapshot']
                    snapshot_id = snapshot.get('_id') or snapshot.get('id')
                    iframe = snapshot['iframe']
                    components.append(
                        {'snapshot': snapshot_id, 'iframe': iframe}
                    )
                except Exception as e:
                    self._addWarning(
                        f'Error processing compose {i}: {str(e)}'
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
                            '_id': str(uuid.uuid4()),
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
