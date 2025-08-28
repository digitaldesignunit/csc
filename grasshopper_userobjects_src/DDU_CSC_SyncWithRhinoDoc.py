#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import rhinoscriptsyntax as rs  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SyncWithRhinoDoc'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'SyncWithRhinoDoc'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_SyncWithRhinoDoc(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250828
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

    def find_objects_with_csc_component(self, doc):
        """
        Find all objects in the document that have the 'csc_component' userkey.
        Returns a list of tuples: (object, component_data, path)
        """
        objects_with_component = []
        
        try:
            # Get all objects in the document
            all_objects = rs.AllObjects()
            for obj in all_objects:
                if obj is None:
                    continue
                # Check if object has user strings
                usr_txt_type = rs.IsUserText(obj)
                if usr_txt_type > 0:
                    # Look for 'csc_component' userkey
                    component_data = None
                    if usr_txt_type == 1:
                        component_data = rs.GetUserText(obj, 'csc_component', False)
                    elif usr_txt_type == 2:
                        component_data = rs.GetUserText(obj, 'csc_component', True)
                    elif usr_txt_type == 3:
                        component_data = rs.GetUserText(obj, 'csc_component', False)
                        if not component_data:
                            component_data = rs.GetUserText(obj, 'csc_component', True)
                    if component_data:
                        try:
                            # Parse the JSON data
                            parsed_data = json.loads(component_data)
                            # Get the object's path for organization
                            obj_path = self.get_object_path(obj, doc)
                            objects_with_component.append((obj, parsed_data, obj_path))
                        except json.JSONDecodeError as e:
                            self._addWarning(
                                f'Invalid JSON in csc_component userstring '
                                f'for object {obj.Id}: {str(e)}'
                            )
                            continue
                            
        except Exception as e:
            self._addError(
                f'Error searching for objects with csc_component: {str(e)}'
            )
            
        return objects_with_component

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

    def update_component_frame(self, obj, component_data):
        """
        Update the component's iframe based on the object's current position.
        Returns updated component data.
        """
        try:
            # Get the object's current transformation
            if hasattr(obj, 'Geometry'):
                geometry = obj.Geometry
                if hasattr(geometry, 'GetBoundingBox'):
                    bbox = geometry.GetBoundingBox(True)
                    if bbox.IsValid:
                        # Create frame based on bounding box
                        center = bbox.Center
                        x_axis = bbox.XAxis
                        y_axis = bbox.YAxis
                        z_axis = bbox.ZAxis
                        
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
            self._addWarning(f'Error updating frame for object {obj.Id}: {str(e)}')
            
        return component_data

    def RunScript(self, Sync: bool):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Trigger to sync components with Rhino document'
        )
        self.OutputParams[0].Description = (
            'DataTree containing all component data found in the document, '
            'with updated iframe information based on current object positions'
        )

        # Set scriptcontext to Rhino document
        sc.doc = Rhino.RhinoDoc.ActiveDoc

        if not Sync:
            # Return empty results if not syncing
            LAST_SYNC = Grasshopper.DataTree[System.Object]()
            __Results = (LAST_SYNC,)
            return __Results

        try:
            self.Component.Message = 'Searching for components in document...'
            
            # Find all objects with csc_component userkey
            objects_with_component = self.find_objects_with_csc_component(sc.doc)
            
            if not objects_with_component:
                msg = 'No components found in document!'
                self._addWarning(msg)
                self.Component.Message = msg
                
                # Return empty results
                LAST_SYNC = Grasshopper.DataTree[System.Object]()
                __Results = (LAST_SYNC,)
                return __Results

            # Create output datatree
            LAST_SYNC = Grasshopper.DataTree[System.Object]()
            
            # Process each component
            for i, (obj, component_data, obj_path) in enumerate(objects_with_component):
                try:
                    # Update the component's frame based on current object position
                    updated_data = self.update_component_frame(obj, component_data)
                    
                    # Create datatree path
                    ghp = Grasshopper.Kernel.Data.GH_Path(i)
                    
                    # Add updated component data to datatree
                    LAST_SYNC.Add(json.dumps(updated_data), ghp)
                    
                    self._addRemark(
                        f'Updated component {component_data.get("_id", "unknown")} from {obj_path}'
                    )
                    
                except Exception as e:
                    msg = f'Error processing component from {obj_path}: {str(e)}'
                    self._addWarning(msg)
                    continue

            # Update success message
            if LAST_SYNC.DataCount > 0:
                self.Component.Message = f'Synced {LAST_SYNC.DataCount} component(s)'
                self._addRemark(
                    f'Successfully synced {LAST_SYNC.DataCount} components with document'
                )
            else:
                self.Component.Message = 'No components synced'
                self._addWarning('No components were successfully synced')

            # Return results
            __Results = (LAST_SYNC,)
            return __Results

        except Exception as e:
            msg = f'Unexpected error during sync: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

            # Return empty results if there was an error
            LAST_SYNC = Grasshopper.DataTree[System.Object]()
            __Results = (LAST_SYNC,)
            return __Results

        finally:
            # Restore scriptcontext to Grasshopper document
            sc.doc = ghdoc  # type: ignore[reportUnedfinedVariable] # NOQA