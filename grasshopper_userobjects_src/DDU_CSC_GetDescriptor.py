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

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'GetDescriptor'  # NOQA
ghenv.Component.NickName = 'GetDescriptor'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '6 Data Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Retrieves a specific descriptor from multiple compose inputs '
    '({identity, snapshot}). Accepts compose JSON strings or geometries '
    'with the csc_component userdata. Returns descriptor values for the '
    'specified key from snapshot.descriptors. Handles single values, lists, '
    'and nested lists by mapping them to appropriate Grasshopper data '
    'structures with input indices as the first path level.'
)


class CSC_GetDescriptor(Grasshopper.Kernel.GH_ScriptInstance):
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
        # Set "No type hint"
        self.InputParams[0].TypeHints.Select(System.Object)
        self.Component.VariableParameterMaintenance()
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'List of compose JSON strings ({identity, snapshot}) OR '
            'geometries with the \'csc_component\' compose userdata'
        )
        self.InputParams[1].Description = (
            'Key string to retrieve from snapshot.descriptors'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Descriptor value for the specified key, or empty if not found'
        )

    def extract_compose_from_geometry(self, geometry):
        """
        Extract compose data ({identity, snapshot}) from geometry userdata.

        Args:
            geometry: Rhino geometry object with userdata

        Returns:
            Compose dictionary or None
        """
        try:
            if hasattr(geometry, 'GetUserString'):
                userdata = geometry.GetUserString('csc_component')
                if userdata:
                    return json.loads(userdata)
        except Exception as e:
            self._addWarning(f'Could not extract compose data: {str(e)}')
        return None

    def get_descriptor_value(self, compose, descriptor_key):
        """
        Extract descriptor value from snapshot.descriptors using the key.

        Args:
            compose: Compose dictionary ({identity, snapshot})
            descriptor_key: String key to look for in descriptors

        Returns:
            Descriptor value or None if not found
        """
        try:
            snapshot = (
                compose.get('snapshot') if isinstance(compose, dict) else None
            )
            if not isinstance(snapshot, dict):
                self._addWarning('Compose JSON has no snapshot')
                return None

            descriptors = snapshot.get('descriptors')
            if isinstance(descriptors, dict) and descriptor_key in descriptors:
                return descriptors[descriptor_key]

            self._addWarning(
                f'Descriptor key "{descriptor_key}" not found in '
                'snapshot.descriptors')
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
            ghp = Grasshopper.Kernel.Data.GH_Path(0)
            result_tree.Add(float(descriptor_value), ghp)

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
                            ghp = Grasshopper.Kernel.Data.GH_Path(i, j)
                            for value in inner_list:
                                result_tree.Add(float(value), ghp)
                else:
                    # 2D structure: [[1,2,3], [9,8,7]]
                    # Paths: (0) for first sublist, (1) for second sublist
                    for i, sublist in enumerate(descriptor_value):
                        ghp = Grasshopper.Kernel.Data.GH_Path(i)
                        for value in sublist:
                            result_tree.Add(float(value), ghp)
            else:
                # Simple list of floats: [1,2,3]
                # Single branch: (0)
                path = Grasshopper.Kernel.Data.GH_Path(0)
                for value in descriptor_value:
                    result_tree.Add(float(value), path)
        else:
            # Fallback for other types
            ghp = Grasshopper.Kernel.Data.GH_Path(0)
            result_tree.Add(float(descriptor_value), ghp)

        return result_tree

    def RunScript(self, Input: list[object], DescriptorKey: str):
        # set up output trees and results tuple
        DescriptorValues = Grasshopper.DataTree[System.Object]()
        try:
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
                # Determine input type and extract compose data
                compose = None

                # Check if input is a compose JSON string
                if isinstance(input_item, str):
                    try:
                        compose = json.loads(input_item)
                        self._addRemark(
                            f'Input {input_index} detected as compose JSON')
                    except json.JSONDecodeError:
                        msg = (f'Input {input_index} is not valid compose '
                               'JSON!')
                        self._addError(msg)
                        continue
                else:
                    # Input is geometry - extract compose from userdata
                    compose = self.extract_compose_from_geometry(input_item)
                    if not compose:
                        msg = (f'Could not extract compose data from '
                               f'input {input_index}!')
                        self._addError(msg)
                        continue

                    self._addRemark(
                        f'Input {input_index} detected as geometry with '
                        'compose userdata')

                # Extract descriptor value
                try:
                    descriptor_value = self.get_descriptor_value(
                        compose, DescriptorKey)

                    if descriptor_value is not None:
                        # Convert descriptor to appropriate Grasshopper data
                        converted_tree = self.convert_descriptor_to_gh_data(
                            descriptor_value)

                        # Merge the converted tree into the output
                        for i in range(converted_tree.BranchCount):
                            original_path = converted_tree.Path(i)
                            # get runcount for first GH Tree index
                            rc = self.Component.RunCount - 1
                            # Prepend input index to the path
                            new_path = Grasshopper.Kernel.Data.GH_Path(
                                0,
                                rc,
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
            return DescriptorValues
