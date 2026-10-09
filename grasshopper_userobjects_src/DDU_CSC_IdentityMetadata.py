#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'IdentityMetadata'  # NOQA
ghenv.Component.NickName = 'IdentityMetadata'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds the fields of a new component that belong to the piece '
    'itself (original function, material, trade name, manufacturer, '
    'manufacture date, origin) as JSON for CreateComponentIdentity. A '
    'cut piece leaves it out: everything it does not state comes from '
    'its parents.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, identity_metadata)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261005 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('IdentityMetadata', 'IdentityMetadata',
     'IdentityMetadata JSON (a fragment of the API payload)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_IdentityMetadata(Grasshopper.Kernel.GH_ScriptInstance):
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
        self.Component = ghenv.Component  # NOQA
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

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _stop(self):
        """True when RunScript has to return early: the library is missing or
        too old, or the outputs were just updated (says why)."""
        if LIBRARY_PROBLEM:
            self._addError(LIBRARY_PROBLEM)
            return True
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
        self.InputParams[0].Description = (
            'IFC class, e.g. IfcBeam, IfcColumn, IfcSlab, IfcPlate, CscDebris'
        )
        self.InputParams[1].Description = (
            'Material id from the controlled list, e.g. concrete'
        )
        self.InputParams[2].Description = (
            'Trade name, e.g. Corian'
        )
        self.InputParams[3].Description = (
            'Manufacturer'
        )
        self.InputParams[4].Description = (
            'Date of manufacture (2024, 2024-05, 2024-05-03)'
        )
        self.InputParams[5].Description = (
            'Origin JSON (from Origin)'
        )
        self.InputParams[6].Description = (
            'Public to anonymous readers (default false)'
        )
        self.InputParams[7].Description = (
            'Free attributes as a JSON object'
        )
        self.InputParams[8].Description = (
            'List of Waste code, e.g. 17 01 01 (empty: derived from the '
            'material)'
        )
        self.InputParams[9].Description = (
            'exact, day, month, year or unknown (empty: from '
            'ManufacturedAt)'
        )
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            OriginalFunction: str,
            Material: str,
            TradeName: str,
            Manufacturer: str,
            ManufacturedAt: str,
            Origin: str,
            IsPublic: bool,
            Attributes: str,
            MaterialClass: str,
            ManufacturedPrecision: str):
        if self._stop():
            return empty_outputs()
        IdentityMetadata = ''
        if not ManufacturedPrecision or ManufacturedPrecision == '':
            ManufacturedPrecision = None
        try:
            fragment = identity_metadata(
                OriginalFunction, Material, TradeName, Manufacturer, ManufacturedAt,
                ManufacturedPrecision, Origin, IsPublic, Attributes,
                MaterialClass)
            IdentityMetadata = json.dumps(fragment)
            return IdentityMetadata
        except BuildError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        return IdentityMetadata
