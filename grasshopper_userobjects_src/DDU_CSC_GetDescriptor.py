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

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'GetDescriptor'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'GetDescriptor'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '6 JSON Tools'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Retrieves a specific descriptor from multiple component_data inputs. '
    'Accepts a list of component_data JSON strings or geometries with '
    'attached component_data. Returns the descriptor values for the specified '
    'key from the descriptors array. Handles single values, lists, and nested '
    'lists by mapping them to appropriate Grasshopper data structures with '
    'input indices as the first path level.'
)


class CSC_GetDescriptor(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251021
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

    def extract_component_data_from_geometry(self, geometry):
        """
        Extract component data from geometry userdata.

        Args:
            geometry: Rhino geometry object with userdata

        Returns:
            Component data dictionary or None
        """
        try:
            if hasattr(geometry, 'GetUserString'):
                userdata = geometry.GetUserString('csc_component')
                if userdata:
                    return json.loads(userdata)
        except Exception as e:
            self._addWarning(f'Could not extract component data: {str(e)}')
        return None

    def get_descriptor_value(self, component_data, descriptor_key):
        """
        Extract descriptor value from component_data using the specified key.

        Args:
            component_data: Dictionary containing component data
            descriptor_key: String key to look for in descriptors

        Returns:
            Descriptor value or None if not found
        """
        try:
            if 'descriptors' in component_data:
                descriptors = component_data['descriptors']
                if (isinstance(descriptors, dict) and
                        descriptor_key in descriptors):
                    return descriptors[descriptor_key]
                else:
                    self._addWarning(
                        f'Descriptor key "{descriptor_key}" not found in '
                        'descriptors')
                    return None
            else:
                self._addWarning('No descriptors found in component_data')
                return None
        except Exception as e:
            self._addError(f'Error extracting descriptor: {str(e)}')
            return None

    def convert_descriptor_to_gh_data(self, descriptor_value):
        """
        Convert descriptor value to appropriate Grasshopper data structure.

        Args:
            descriptor_value: The descriptor value (always float values)

        Returns:
            Grasshopper DataTree with appropriate structure
        """
        result_tree = Grasshopper.DataTree[System.Object]()

        if descriptor_value is None:
            return result_tree

        # Single float value
        if isinstance(descriptor_value, (int, float)):
            result_tree.Add(float(descriptor_value))

        # List of floats
        elif isinstance(descriptor_value, list):
            if len(descriptor_value) == 0:
                return result_tree

            # Check if it's a list of lists (2D)
            if all(isinstance(item, list) for item in descriptor_value):
                # Check if it's 3D (list of lists of lists)
                is_3d = all(isinstance(sublist_item, list)
                            for sublist in descriptor_value
                            for sublist_item in sublist)
                if is_3d:
                    # 3D structure: [[[1,2],[3,4]], [[5,6],[7,8]]]
                    # Paths: (0;0), (0;1), (1;0), (1;1)
                    for i, sublist in enumerate(descriptor_value):
                        for j, inner_list in enumerate(sublist):
                            path = Grasshopper.Kernel.Data.GH_Path(i, j)
                            for value in inner_list:
                                result_tree.Add(float(value), path)
                else:
                    # 2D structure: [[1,2,3], [9,8,7]]
                    # Paths: (0) for first sublist, (1) for second sublist
                    for i, sublist in enumerate(descriptor_value):
                        path = Grasshopper.Kernel.Data.GH_Path(i)
                        for value in sublist:
                            result_tree.Add(float(value), path)
            else:
                # Simple list of floats: [1,2,3]
                # Single branch: (0)
                path = Grasshopper.Kernel.Data.GH_Path(0)
                for value in descriptor_value:
                    result_tree.Add(float(value), path)
        else:
            # Fallback for other types
            result_tree.Add(float(descriptor_value))

        return result_tree

    def RunScript(self,
            Input: System.Collections.Generic.List[object],
            DescriptorKey: str):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'List of component data as JSON strings OR geometries with '
            'attached component_data userdata'
        )
        self.InputParams[1].Description = (
            'Key string to retrieve from the descriptors array in '
            'component_data'
        )

        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'Descriptor value for the specified key, or empty if not found'
        )

        try:
            # set up output trees and results tuple
            DescriptorValues = Grasshopper.DataTree[System.Object]()

            # Validate inputs
            if not Input:
                msg = 'No input provided'
                self._addWarning(msg)
                self.Component.Message = msg
                return DescriptorValues

            if not DescriptorKey:
                msg = 'No descriptor key provided'
                self._addWarning(msg)
                self.Component.Message = msg
                return DescriptorValues

            self.Component.Message = 'Processing inputs...'

            # Process each input item
            input_list = list(Input)
            for input_index, input_item in enumerate(input_list):
                # Determine input type and extract component data
                component_data = None

                # Check if input is a JSON string (ComponentData)
                if isinstance(input_item, str):
                    try:
                        component_data = json.loads(input_item)
                        self._addRemark(
                            f'Input {input_index} detected as ComponentData '
                            'JSON')
                    except json.JSONDecodeError:
                        msg = (f'Input {input_index} is not valid JSON '
                               'ComponentData!')
                        self._addError(msg)
                        continue
                else:
                    # Input is geometry - extract component data from userdata
                    component_data = self.extract_component_data_from_geometry(
                        input_item)
                    if not component_data:
                        msg = (f'Could not extract component data from '
                               f'input {input_index}!')
                        self._addError(msg)
                        continue

                    self._addRemark(
                        f'Input {input_index} detected as geometry with '
                        'component userdata')

                # Extract descriptor value
                try:
                    descriptor_value = self.get_descriptor_value(
                        component_data, DescriptorKey)

                    if descriptor_value is not None:
                        # Convert descriptor to appropriate Grasshopper data
                        converted_tree = self.convert_descriptor_to_gh_data(
                            descriptor_value)

                        # Merge the converted tree into the output
                        for i in range(converted_tree.BranchCount):
                            original_path = converted_tree.Path(i)
                            # Prepend input index to the path
                            new_path = Grasshopper.Kernel.Data.GH_Path(
                                0,
                                input_index,
                                *original_path.Indices)
                            branch_data = converted_tree.Branch(i)
                            for item in branch_data:
                                DescriptorValues.Add(item, new_path)

                        self._addRemark(
                            f'Successfully extracted descriptor '
                            f'"{DescriptorKey}" from input {input_index}'
                        )
                    else:
                        # Descriptor not found
                        msg = (f'Descriptor "{DescriptorKey}" not found in '
                               f'input {input_index}')
                        self._addWarning(msg)

                except Exception as e:
                    msg = (f'Error extracting descriptor from input '
                           f'{input_index}: {str(e)}')
                    self._addError(msg)

            # Update success message
            self.Component.Message = f'Processed {len(input_list)} input(s)'

            # return output trees
            return DescriptorValues

        except Exception as e:
            msg = f'Unexpected error during descriptor extraction: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

            # Return empty results if there was an error
            DescriptorValues = Grasshopper.DataTree[System.Object]()
            return DescriptorValues
