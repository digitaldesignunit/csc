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

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'JSONKeys'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'JSONKeys'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '6 Data Tools'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Extracts all keys and their paths from a JSON string up to a specified '
    'maximum depth. Returns keys, types, and full dot-notation paths as '
    'separate data trees.'
)


class CSC_JSONKeys(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251023.1
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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
            'JSON string to extract keys from'
        )
        self.InputParams[1].Description = (
            'Maximum depth to traverse in the JSON structure (default: 5)'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'List of all available keys in the JSON structure'
        )
        self.OutputParams[1+i].Description = (
            'Data types for each key '
            '(object, array, string, number, boolean, null)'
        )
        self.OutputParams[2+i].Description = (
            'Full dot-notation paths for each key '
            '(e.g., "descriptors.material.type")'
        )

    def get_json_type(self, value):
        """Get the JSON type of a value."""
        if isinstance(value, dict):
            return 'object'
        elif isinstance(value, list):
            return 'array'
        elif isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, (int, float)):
            return 'number'
        elif isinstance(value, str):
            return 'string'
        elif value is None:
            return 'null'
        else:
            return 'unknown'

    def extract_keys_recursive(self, data, prefix='', max_depth=5,
                               current_depth=0):
        """Recursively extract all keys from JSON data."""
        keys = []
        key_types = []
        key_paths = []

        if current_depth >= max_depth:
            return keys, key_types, key_paths

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f'{prefix}.{key}' if prefix else key
                keys.append(key)
                key_types.append(self.get_json_type(value))
                key_paths.append(current_path)

                # Recursively process nested objects and arrays
                if (isinstance(value, (dict, list)) and
                        current_depth < max_depth - 1):
                    nested_keys, nested_types, nested_paths = (
                        self.extract_keys_recursive(
                            value, current_path, max_depth, current_depth + 1
                        )
                    )
                    keys.extend(nested_keys)
                    key_types.extend(nested_types)
                    key_paths.extend(nested_paths)

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f'{prefix}[{i}]' if prefix else f'[{i}]'
                keys.append(f'[{i}]')
                key_types.append(self.get_json_type(item))
                key_paths.append(current_path)

                # Recursively process nested objects and arrays
                if (isinstance(item, (dict, list)) and
                        current_depth < max_depth - 1):
                    nested_keys, nested_types, nested_paths = (
                        self.extract_keys_recursive(
                            item, current_path, max_depth, current_depth + 1
                        )
                    )
                    keys.extend(nested_keys)
                    key_types.extend(nested_types)
                    key_paths.extend(nested_paths)

        return keys, key_types, key_paths

    def RunScript(self, JSON: str, MaxDepth: int):
        # set up output trees and results tuple
        Keys = Grasshopper.DataTree[System.Object]()
        KeyTypes = Grasshopper.DataTree[System.Object]()
        KeyPaths = Grasshopper.DataTree[System.Object]()
        __Results = (Keys, KeyTypes, KeyPaths)
        try:
            # Validate input
            if not JSON:
                msg = 'No JSON input provided'
                self._addWarning(msg)
                self.Component.Message = msg
                return __Results

            # Set default max depth if not provided
            if MaxDepth is None or MaxDepth < 1:
                MaxDepth = 5

            self.Component.Message = 'Extracting JSON keys...'

            # Parse JSON
            try:
                json_data = json.loads(JSON)
            except json.JSONDecodeError as e:
                msg = f'Invalid JSON format: {str(e)}'
                self._addError(msg)
                return __Results

            # Extract keys recursively
            keys, key_types, key_paths = self.extract_keys_recursive(
                json_data, max_depth=MaxDepth
            )

            # Add results to data trees
            if keys:
                for i, key in enumerate(keys):
                    Keys.Add(key)
                    KeyTypes.Add(
                        key_types[i] if i < len(key_types) else 'unknown'
                    )
                    KeyPaths.Add(key_paths[i] if i < len(key_paths) else key)
            else:
                # If no keys found, add empty results
                Keys.Add('')
                KeyTypes.Add('')
                KeyPaths.Add('')

            # Update success message
            total_keys = len(keys)
            self.Component.Message = f'Extracted {total_keys} key(s)'
            self._addRemark(
                f'Successfully extracted {total_keys} keys from JSON'
            )

            # return output trees
            return __Results

        except Exception as e:
            msg = f'Unexpected error during key extraction: {str(e)}'
            self._addError(msg)
            # Return empty results if there was an error
            return __Results
