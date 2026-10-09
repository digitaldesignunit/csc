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
import Rhino  # NOQA
import Grasshopper  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'GetComponentPassport'  # NOQA
ghenv.Component.NickName = 'GetComponentPassport'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Extracts the component passport ({identity, snapshot} JSON string) '
    'from the csc_component user text of Rhino geometry objects. Safely '
    'retrieves and parses the component passport stored as user text.'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('ComponentPassport', 'ComponentPassport',
     'Component passport JSON strings ({identity, snapshot}) extracted from geometry userdata'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_GetComponentPassport(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Geometry objects with the \'csc_component\' user text'
        )
        # Initialize output param descriptions
        self._check_outputs()

    def extract_component_data_from_geometry(self, geometry):
        """
        Extract passport data ({identity, snapshot}) from geometry userdata.

        Args:
            geometry: Rhino geometry object with userdata

        Returns:
            Passport dictionary or None
        """
        try:
            if hasattr(geometry, 'GetUserString'):
                userdata = geometry.GetUserString('csc_component')
                if userdata:
                    return json.loads(userdata)
                else:
                    self._addWarning('No csc_component userdata found')
            else:
                self._addWarning('Geometry object does not support userdata')
        except json.JSONDecodeError as e:
            self._addError(f'Invalid JSON in userdata: {str(e)}')
        except Exception as e:
            self._addError(f'Error extracting component data: {str(e)}')
        return None

    def RunScript(self, Geometry: list[Rhino.Geometry.GeometryBase]):
        # Set up output tree
        if self._stop():
            return empty_outputs()
        ComponentPassport = Grasshopper.DataTree[System.Object]()

        # Validate input
        if not Geometry:
            msg = 'Input geometry failed to collect data!'
            self._addWarning(msg)
            return ComponentPassport

        try:
            # Handle single geometry or list of geometries
            successful_extractions = 0

            for i, geo in enumerate(Geometry):
                if geo is None:
                    self._addWarning(f'Geometry at index {i} is None, '
                                     f'skipping')
                    continue

                # Extract passport data
                passport = self.extract_component_data_from_geometry(geo)
                if passport:
                    # Add to output
                    ComponentPassport.Add(
                        json.dumps(passport),
                        Grasshopper.Kernel.Data.GH_Path(i)
                    )
                    successful_extractions += 1
                    self._addRemark(f'Successfully extracted component passport data '
                                    f'from geometry {i}')
                else:
                    # Add empty string to maintain data tree structure
                    ComponentPassport.Add(
                        '',
                        Grasshopper.Kernel.Data.GH_Path(i)
                    )
                    self._addWarning(f'Failed to extract component passport data '
                                     f'from geometry {i}')

            # Update success message
            if successful_extractions == 0:
                msg = 'No component passport data found in any geometry objects'
                self._addWarning(msg)
            elif successful_extractions == len(Geometry):
                self._addRemark(f'Extracted component passport data from '
                                f'{successful_extractions} out of '
                                f'{len(Geometry)} geometry objects')
            else:
                self._addWarning('Some geometry objects did not contain '
                                 'valid component passport data')

            return ComponentPassport

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            return ComponentPassport
