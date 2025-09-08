#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import re

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'JSONGetValue'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'JSONGetValue'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '6 JSON Tools'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_JSONGetValue(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250908
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

    def get_value_by_path(self, data, path):
        """Get value from JSON data using dot-notation path."""
        if not path:
            return data, 'root'

        # Split path by dots and handle array indices
        parts = re.split(r'\.|\[|\]', path)
        parts = [part for part in parts if part]  # Remove empty strings

        current = data
        for part in parts:
            if part.startswith('[') and part.endswith(']'):
                # Array index
                try:
                    index = int(part[1:-1])
                    if isinstance(current, list) and 0 <= index < len(current):
                        current = current[index]
                    else:
                        raise IndexError(f'Array index {index} out of range')
                except (ValueError, IndexError) as e:
                    raise KeyError(f'Invalid array index: {part}') from e
            else:
                # Object key
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    raise KeyError(f'Key "{part}" not found')

        return current, self.get_json_type(current)

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

    def convert_to_gh_type(self, value, value_type):
        """Convert value to appropriate Grasshopper type."""
        if value_type == 'boolean':
            return bool(value)
        elif value_type == 'number':
            if isinstance(value, int):
                return int(value)
            else:
                return float(value)
        elif value_type == 'string':
            return str(value)
        elif value_type == 'null':
            return None
        elif value_type == 'object':
            return json.dumps(value)
        elif value_type == 'array':
            return json.dumps(value)
        else:
            return str(value)

    def RunScript(self, JSON: str, KeyPath: str, DefaultValue: str):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'JSON string to extract value from'
        )
        self.InputParams[1].Description = (
            'Dot-notation path to the desired value '
            '(e.g., "descriptors.material.type")'
        )
        self.InputParams[2].Description = (
            'Default value to return if key path is not found (optional)'
        )

        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'Extracted value converted to appropriate Grasshopper type'
        )
        self.OutputParams[1].Description = (
            'Data type of the extracted value '
            '(string, number, boolean, object, array, null)'
        )
        self.OutputParams[2].Description = (
            'True if extraction was successful, False otherwise'
        )
        self.OutputParams[3].Description = (
            'Error message if extraction failed, empty string if successful'
        )

        try:
            # set up output trees and results tuple
            Value = Grasshopper.DataTree[System.Object]()
            ValueType = Grasshopper.DataTree[System.Object]()
            Success = Grasshopper.DataTree[System.Object]()
            Error = Grasshopper.DataTree[System.Object]()
            __Results = (Value, ValueType, Success, Error)

            # Validate input
            if not JSON:
                msg = 'No JSON input provided'
                self._addWarning(msg)
                self.Component.Message = msg
                Value.Add('')
                ValueType.Add('')
                Success.Add(False)
                Error.Add(msg)
                return __Results

            if not KeyPath:
                msg = 'No key path provided'
                self._addWarning(msg)
                self.Component.Message = msg
                Value.Add(DefaultValue if DefaultValue else '')
                ValueType.Add('')
                Success.Add(False)
                Error.Add(msg)
                return __Results

            self.Component.Message = 'Extracting JSON value...'

            # Parse JSON
            try:
                json_data = json.loads(JSON)
            except json.JSONDecodeError as e:
                msg = f'Invalid JSON format: {str(e)}'
                self._addError(msg)
                self.Component.Message = msg
                Value.Add(DefaultValue if DefaultValue else '')
                ValueType.Add('')
                Success.Add(False)
                Error.Add(msg)
                return __Results

            # Extract value by path
            try:
                extracted_value, value_type = self.get_value_by_path(
                    json_data, KeyPath
                )

                # Convert to appropriate GH type
                converted_value = self.convert_to_gh_type(
                    extracted_value, value_type
                )

                # Add results
                Value.Add(converted_value)
                ValueType.Add(value_type)
                Success.Add(True)
                Error.Add('')

                # Update success message
                self.Component.Message = f'Extracted: {value_type}'
                self._addRemark(
                    f'Successfully extracted {value_type} value from path: '
                    f'{KeyPath}'
                )

            except KeyError as e:
                msg = f'Key path not found: {str(e)}'
                self._addWarning(msg)
                self.Component.Message = msg
                Value.Add(DefaultValue if DefaultValue else '')
                ValueType.Add('')
                Success.Add(False)
                Error.Add(msg)

            except Exception as e:
                msg = f'Error extracting value: {str(e)}'
                self._addError(msg)
                self.Component.Message = msg
                Value.Add(DefaultValue if DefaultValue else '')
                ValueType.Add('')
                Success.Add(False)
                Error.Add(msg)

            # return output trees
            return __Results

        except Exception as e:
            msg = f'Unexpected error during value extraction: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

            # Return empty results if there was an error
            Value = Grasshopper.DataTree[System.Object]()
            ValueType = Grasshopper.DataTree[System.Object]()
            Success = Grasshopper.DataTree[System.Object]()
            Error = Grasshopper.DataTree[System.Object]()
            __Results = (Value, ValueType, Success, Error)
            return __Results
