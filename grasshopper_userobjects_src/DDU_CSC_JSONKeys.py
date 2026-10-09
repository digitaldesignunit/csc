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
ghenv.Component.Name = 'JSONKeys'  # NOQA
ghenv.Component.NickName = 'JSONKeys'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '6 Data Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Extracts all keys and their paths from a JSON string up to a specified '
    'maximum depth. Returns keys, types, and full dot-notation paths as '
    'separate data trees.'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Keys', 'Keys',
     'List of all available keys in the JSON structure'),
    ('KeyTypes', 'KeyTypes',
     'Data types for each key (object, array, string, number, boolean, null)'),
    ('KeyPaths', 'KeyPaths',
     'Full dot-notation paths for each key (e.g., "descriptors.material.type")'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_JSONKeys(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

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

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _stop(self):
        """True when RunScript has to return early: the outputs were just
        updated (says why)."""
        if self._outputs_note:
            self._addRemark(self._outputs_note)
        return not self._outputs_ready

    def _check_outputs(self):
        """Make the outputs match OUTPUTS before the script runs (8.112)."""
        self._outputs_ready, self._outputs_note = True, None
        if ensure_outputs is None:
            self._outputs_note = (
                'output check skipped: CSC library not installed')
            return
        status = ensure_outputs(self.Component, OUTPUTS)
        self._outputs_ready, self._outputs_note = status.ready, status.remark

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
        self._check_outputs()

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
        if self._stop():
            return empty_outputs()
        Keys = Grasshopper.DataTree[System.Object]()
        KeyTypes = Grasshopper.DataTree[System.Object]()
        KeyPaths = Grasshopper.DataTree[System.Object]()
        __Results = (Keys, KeyTypes, KeyPaths)
        try:
            # Validate input
            if not JSON:
                msg = 'No JSON input provided'
                self._addWarning(msg)
                return __Results

            # Set default max depth if not provided
            if MaxDepth is None or MaxDepth < 1:
                MaxDepth = 5


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
