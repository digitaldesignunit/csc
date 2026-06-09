#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import rhinoscriptsyntax as rs  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SyncWithRhinoDoc'  # NOQA
ghenv.Component.NickName = 'SyncWithRhinoDoc'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Scans the active Rhino document for objects with csc_component user '
    'data (compose JSON) and updates snapshot.iframe based on text tag '
    'planes or combined geometry bounds.'
)


class CSC_SyncWithRhinoDoc(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Trigger to sync components with Rhino document'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'DataTree of compose JSON ({identity, snapshot}) found in the '
            'document, with snapshot.iframe updated from object positions'
        )

    def find_objects_with_csc_component(self, doc):
        """
        Find all objects in the document that have the 'csc_component' userkey.
        Also find text tags that are grouped with these components.
        Groups objects by identity._id to handle multiple meshes correctly.
        Returns a list of tuples: (identity_id, compose, objects_list,
                                   combined_path)
        """
        components_dict = {}
        try:
            # Get all objects in the document
            all_objects = doc.Objects
            for obj in all_objects:
                if obj is None:
                    continue
                # Check if object has user strings
                usr_txt_type = rs.IsUserText(obj)
                if usr_txt_type > 0:
                    # Look for 'csc_component' userkey
                    component_data = None
                    if usr_txt_type == 1:
                        component_data = rs.GetUserText(
                            obj, 'csc_component', False)
                    elif usr_txt_type == 2:
                        component_data = rs.GetUserText(
                            obj, 'csc_component', True)
                    elif usr_txt_type == 3:
                        component_data = rs.GetUserText(
                            obj, 'csc_component', False)
                        if not component_data:
                            component_data = rs.GetUserText(
                                obj, 'csc_component', True)
                    if component_data:
                        try:
                            compose = json.loads(component_data)
                            identity = compose.get('identity')
                            if not isinstance(identity, dict):
                                self._addWarning(
                                    f'Invalid compose JSON for object '
                                    f'{obj.Id}: missing identity'
                                )
                                continue
                            identity_id = identity.get('_id', 'unknown')
                            if identity_id not in components_dict:
                                components_dict[identity_id] = {
                                    'compose': compose,
                                    'objects': [],
                                    'paths': []
                                }
                            obj_path = self.get_object_path(obj, doc)
                            components_dict[identity_id]['objects'].append(obj)
                            components_dict[identity_id]['paths'].append(
                                obj_path)
                        except json.JSONDecodeError as e:
                            self._addWarning(
                                f'Invalid JSON in csc_component userstring '
                                f'for object {obj.Id}: {str(e)}'
                            )
                            continue

            for identity_id, data in components_dict.items():
                groups = doc.Groups
                for i in range(groups.Count):
                    group = groups[i]
                    if (group and isinstance(group.Name, str) and
                            group.Name.startswith(identity_id)):
                        # Get all objects in this specific group instance
                        group_objects = rs.ObjectsByGroup(group.Name)
                        for obj_id in group_objects:
                            obj = rs.coercegeometry(obj_id)
                            if obj and rs.IsText(obj):
                                # This is a text tag for our component
                                obj_path = self.get_object_path(obj, doc)
                                data['objects'].append(obj)
                                data['paths'].append(obj_path)
                                self._addRemark(
                                    'Found text tag for identity '
                                    f'{identity_id}'
                                )

        except Exception as e:
            self._addError(
                f'Error searching for objects with csc_component: {str(e)}'
            )

        # Convert to list format for compatibility
        components_list = []
        for identity_id, data in components_dict.items():
            combined_path = ' | '.join(data['paths'])
            components_list.append((
                identity_id,
                data['compose'],
                data['objects'],
                combined_path
            ))

        return components_list

    def get_object_path(self, obj, doc):
        """
        Get a descriptive path for the object (layer hierarchy, etc.)
        """
        try:
            # Try to get the layer name
            layer_index = obj.Attributes.LayerIndex
            if layer_index >= 0:
                layer = doc.Layers[layer_index]
                if layer:
                    return layer.FullPath
        except Exception:
            pass
        # Fallback to object name or type
        try:
            if hasattr(obj, 'Name') and obj.Name:
                return obj.Name
        except Exception:
            pass
        return f"Object_{obj}"

    def update_component_frame(self, objects_list, compose):
        """
        Update snapshot.iframe from a text tag plane when available,
        otherwise from the combined bounding box of all objects.
        Returns updated compose JSON.
        """
        try:
            if not objects_list:
                return compose

            snapshot = compose.get('snapshot')
            if not isinstance(snapshot, dict):
                return compose

            for obj in objects_list:
                if rs.IsText(obj):
                    try:
                        tagplane = rs.TextObjectPlane(obj)
                        tagframe = {
                            'o': [tagplane.OriginX,
                                  tagplane.OriginY,
                                  tagplane.OriginZ],
                            'x': [tagplane.XAxis.X,
                                  tagplane.XAxis.Y,
                                  tagplane.XAxis.Z],
                            'y': [tagplane.YAxis.X,
                                  tagplane.YAxis.Y,
                                  tagplane.YAxis.Z],
                            'z': [tagplane.ZAxis.X,
                                  tagplane.ZAxis.Y,
                                  tagplane.ZAxis.Z]
                        }
                        snapshot['iframe'] = tagframe
                        compose['snapshot'] = snapshot
                        return compose
                    except Exception as e:
                        self._addWarning(
                            f'Error extracting plane from text tag: {str(e)}'
                        )
                        continue

            combined_bbox = None
            for obj in objects_list:
                if hasattr(obj, 'Geometry'):
                    geometry = obj.Geometry
                    if hasattr(geometry, 'GetBoundingBox'):
                        bbox = geometry.GetBoundingBox(True)
                        if bbox.IsValid:
                            if combined_bbox is None:
                                combined_bbox = bbox
                            else:
                                combined_bbox = (
                                    Rhino.Geometry.BoundingBox.Union(
                                        combined_bbox, bbox))

            combined_bbox = Rhino.Geometry.Box(combined_bbox)
            if combined_bbox and combined_bbox.IsValid:
                center = combined_bbox.Center
                x_axis = combined_bbox.Plane.XAxis
                y_axis = combined_bbox.Plane.YAxis
                z_axis = combined_bbox.Plane.ZAxis
                snapshot['iframe'] = {
                    'o': [center.X, center.Y, center.Z],
                    'x': [x_axis.X, x_axis.Y, x_axis.Z],
                    'y': [y_axis.X, y_axis.Y, y_axis.Z],
                    'z': [z_axis.X, z_axis.Y, z_axis.Z]
                }
                compose['snapshot'] = snapshot
                return compose
        except Exception as e:
            self._addWarning(
                f'Error updating frame for component: {str(e)}'
            )
        return compose

    def RunScript(self, Sync: bool):
        # init outputs
        DocumentComponents = Grasshopper.DataTree[str]()
        if not Sync:
            # Return empty results if not syncing
            self.Component.Message = 'Sync Toggle is False'
            return DocumentComponents
        try:
            # Set scriptcontext to Rhino document
            sc.doc = Rhino.RhinoDoc.ActiveDoc

            self.Component.Message = 'Searching for components in document...'
            # Find all objects with csc_component userkey
            objects_with_component = self.find_objects_with_csc_component(
                sc.doc
            )
            if not objects_with_component:
                msg = 'No components found in document!'
                self._addWarning(msg)
                self.Component.Message = msg
                # Return empty results
                return DocumentComponents
            # Create output datatree
            # Process each component (now grouped by component ID)
            for i, (identity_id, compose, objects_list,
                    combined_path) in enumerate(objects_with_component):
                try:
                    updated_compose = self.update_component_frame(
                        objects_list, compose)
                    ghp = Grasshopper.Kernel.Data.GH_Path(i)
                    DocumentComponents.Add(json.dumps(updated_compose), ghp)

                    object_count = len(objects_list)
                    if object_count == 1:
                        self._addRemark(
                            f'Updated identity {identity_id} '
                            f'from {combined_path}'
                        )
                    else:
                        self._addRemark(
                            f'Updated identity {identity_id} '
                            f'({object_count} objects) from {combined_path}'
                        )
                except Exception as e:
                    msg = (
                        f'Error processing identity {identity_id} '
                        f'from {combined_path}: {str(e)}'
                    )
                    self._addWarning(msg)
                    continue

            # Update success message
            if DocumentComponents.DataCount > 0:
                self.Component.Message = (
                    f'Synced {DocumentComponents.DataCount} component(s)'
                )
                self._addRemark(
                    f'Successfully synced {DocumentComponents.DataCount} '
                    'components with document'
                )
            else:
                self.Component.Message = 'No components synced'
                self._addWarning('No components were successfully synced')

            # Return results
            return DocumentComponents

        except Exception as e:
            msg = f'Unexpected error during sync: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

            # Return empty results if there was an error
            return DocumentComponents

        finally:
            # Restore scriptcontext to Grasshopper document
            sc.doc = self.Component.OnPingDocument()
