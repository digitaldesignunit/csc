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
ghenv.Component.Name = 'TransformComponent'  # NOQA
ghenv.Component.NickName = 'TransformComponent'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Applies a Rhino transformation to the client-side placement '
    '(csc_placement, the frame the stored geometry sits in) of a component '
    'snapshot in component passport JSON ({identity, snapshots[]}). The placement is '
    'never sent to the server.'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('XComponentPassport', 'XComponentPassport',
     'Transformed component passport JSON string ({identity, snapshot})!'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_TransformComponent(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Component passport JSON string ({identity, snapshot}) from previous '
            'components.'
        )
        self.InputParams[1].Description = (
            'Rhino transform to apply to the snapshot placement.'
        )
        # Initialize output param descriptions
        self._check_outputs()

    def PlaneToFrameDict(self, plane: Rhino.Geometry.Plane) -> dict:
        """
        Convert a Rhino plane to a frame dictionary format.

        This method converts the plane's origin and axis vectors to the format
        expected by the component system for placements.

        Args:
            plane: Rhino.Geometry.Plane object

        Returns:
            Dictionary with 'o', 'x', 'y', 'z' keys containing coordinate lists
        """
        iframe = {
            'o': [plane.OriginX, plane.OriginY, plane.OriginZ],
            'x': [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
            'y': [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
            'z': [plane.ZAxis.X, plane.ZAxis.Y, plane.ZAxis.Z]
        }
        return iframe

    def RunScript(self, ComponentPassport: str, XForm: Rhino.Geometry.Transform):
        # set up output trees and results tuple
        if self._stop():
            return empty_outputs()
        XComponentPassport = System.Collections.Generic.List[System.Object]()
        # reset message
        # Validate input parameters
        if not ComponentPassport:
            msg = 'Input ComponentPassport failed to collect data!'
            self._addWarning(msg)
            return XComponentPassport

        if not XForm:
            msg = 'Input XForm failed to collect data!'
            self._addWarning(msg)
            return XComponentPassport

        try:
            # Load and parse passport JSON ({identity, snapshot})
            jcomp = json.loads(ComponentPassport)
            snapshots = jcomp.get('snapshots') or []
            snapshot = snapshots[0] if snapshots else None
            if not isinstance(snapshot, dict):
                msg = 'Component passport JSON has no snapshots to transform!'
                self._addError(msg)
                return XComponentPassport

            # Process the placement
            try:
                # Try to extract the existing placement from snapshot
                iframe = snapshot['csc_placement']
                iplane = Rhino.Geometry.Plane(
                    Rhino.Geometry.Point3d(*iframe['o']),
                    Rhino.Geometry.Vector3d(*iframe['x']),
                    Rhino.Geometry.Vector3d(*iframe['y']),
                )
                self._addRemark(
                    'Using existing placement from snapshot'
                )
            except (KeyError, TypeError):
                # If there is no placement,
                # create world XY plane as default
                iplane = Rhino.Geometry.Plane.WorldXY
                self._addRemark(
                    'No placement found, using WorldXY plane'
                )

            # Apply the input transform to the placement plane
            iplane.Transform(XForm)

            # Replace the placement in the snapshot
            # with the transformed one
            snapshot['csc_placement'] = self.PlaneToFrameDict(iplane)

            # Convert back to JSON string for output
            XComponentPassport = json.dumps(jcomp)

            return XComponentPassport

        except json.JSONDecodeError as e:
            msg = f'Failed to parse component JSON data: {str(e)}'
            self._addError(msg)
            return XComponentPassport

        except Exception as e:
            msg = f'Unexpected error during transformation: {str(e)}'
            self._addError(msg)
            return XComponentPassport
