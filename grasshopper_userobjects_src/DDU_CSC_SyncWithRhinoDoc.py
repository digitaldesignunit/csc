#! python3
# -*- coding: utf-8 -*-
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
    'data and updates their iframe (insertion frame) based on current '
    'geometry position in Rhino.'
)


class CSC_SyncWithRhinoDoc(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251203
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
            'DataTree containing all component data found in the document, '
            'with updated iframe information based on current object positions'
        )

    def find_objects_with_csc_component(self, doc):
        """
        Find all objects in the document that have the 'csc_component' userkey.
        Also find text tags that are grouped with these components.
        Groups objects by component ID to handle multiple meshes correctly.
        Returns a list of tuples: (component_id, component_data, objects_list,
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
                            # Parse the JSON data
                            parsed_data = json.loads(component_data)
                            component_id = parsed_data.get('_id', 'unknown')
                            # Group objects by component ID
                            if component_id not in components_dict:
                                components_dict[component_id] = {
                                    'component_data': parsed_data,
                                    'objects': [],
                                    'paths': []
                                }
                            # Add object to the component group
                            obj_path = self.get_object_path(obj, doc)
                            components_dict[component_id]['objects'].append(
                                obj
                            )
                            components_dict[component_id]['paths'].append(
                                obj_path)
                        except json.JSONDecodeError as e:
                            self._addWarning(
                                f'Invalid JSON in csc_component userstring '
                                f'for object {obj.Id}: {str(e)}'
                            )
                            continue

            for component_id, data in components_dict.items():
                # Find all groups whose name starts with the component_id
                groups = doc.Groups
                for i in range(groups.Count):
                    group = groups[i]
                    if (group and isinstance(group.Name, str) and
                            group.Name.startswith(component_id)):
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
                                    'Found text tag for component '
                                    f'{component_id}'
                                )

        except Exception as e:
            self._addError(
                f'Error searching for objects with csc_component: {str(e)}'
            )

        # Convert to list format for compatibility
        components_list = []
        for component_id, data in components_dict.items():
            combined_path = ' | '.join(data['paths'])  # Combine all paths
            components_list.append((
                component_id,
                data['component_data'],
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

    def update_component_frame(self, objects_list, component_data):
        """
        Update the component's iframe based on text tag plane if available,
        otherwise fall back to combined bounding box of all objects.
        Returns updated component data.
        """
        try:
            if not objects_list:
                return component_data

            # First, try to find a text object (tag) and use its plane
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
                        # Update the iframe in component data
                        if 'iframe' not in component_data:
                            component_data['iframe'] = {}
                        component_data['iframe'].update(tagframe)
                        return component_data
                    except Exception as e:
                        self._addWarning(
                            f'Error extracting plane from text tag: {str(e)}'
                        )
                        continue

            # Fallback: Calculate combined bounding box for all objects
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
            # convert to box
            combined_bbox = Rhino.Geometry.Box(combined_bbox)

            if combined_bbox and combined_bbox.IsValid:
                # Create frame based on combined bounding box
                center = combined_bbox.Center
                x_axis = combined_bbox.Plane.XAxis
                y_axis = combined_bbox.Plane.YAxis
                z_axis = combined_bbox.Plane.ZAxis

                # Update the iframe in component data
                if 'iframe' not in component_data:
                    component_data['iframe'] = {}
                component_data['iframe'].update({
                    'o': [center.X, center.Y, center.Z],
                    'x': [x_axis.X, x_axis.Y, x_axis.Z],
                    'y': [y_axis.X, y_axis.Y, y_axis.Z],
                    'z': [z_axis.X, z_axis.Y, z_axis.Z]
                })
                return component_data
        except Exception as e:
            self._addWarning(
                f'Error updating frame for component: {str(e)}'
            )
        return component_data

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
            for i, (component_id, component_data, objects_list,
                    combined_path) in enumerate(objects_with_component):
                try:
                    # Update the component's frame based on combined
                    # bounding box of all objects from the same component
                    updated_data = self.update_component_frame(
                        objects_list, component_data
                    )
                    # Create datatree path
                    ghp = Grasshopper.Kernel.Data.GH_Path(i)
                    # Add updated component data to datatree
                    DocumentComponents.Add(json.dumps(updated_data), ghp)

                    # Log success message with object count
                    object_count = len(objects_list)
                    if object_count == 1:
                        self._addRemark(
                            f'Updated component {component_id} '
                            f'from {combined_path}'
                        )
                    else:
                        self._addRemark(
                            f'Updated component {component_id} '
                            f'({object_count} meshes) from {combined_path}'
                        )
                except Exception as e:
                    msg = (
                        f'Error processing component {component_id} '
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
