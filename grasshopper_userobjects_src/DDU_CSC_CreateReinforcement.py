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
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateReinforcement'  # NOQA
ghenv.Component.NickName = 'CreateReinforcement'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds one inline reinforcement bar JSON object '
    '({spec, diameter, points}) for CreateComponentIdentity / '
    'CreateComponentSnapshot.'
)


class CSC_CreateReinforcement(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260610
    """

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

    def BeforeRunScript(self):
        self.InputParams[0].Description = (
            'Open centerline as Polyline or PolylineCurve '
            '(no curve conversion / retessellation)'
        )
        self.InputParams[1].Description = (
            'Reinforcement steel specification (e.g. B500B)'
        )
        self.InputParams[2].Description = (
            'Bar diameter in millimeters'
        )
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0 + i].Description = (
            'SnapshotReinforcement JSON string for geometry.reinforcements[]'
        )

    def extract_open_polyline_points(self, geometry):
        """Return [[x,y,z], ...] from an open Polyline or PolylineCurve."""
        if geometry is None:
            raise ValueError('Polyline input is required')

        if isinstance(geometry, Rhino.Geometry.Polyline):
            pl = geometry
        elif isinstance(geometry, Rhino.Geometry.PolylineCurve):
            pl = geometry.ToPolyline()
        elif isinstance(geometry, Rhino.Geometry.Curve):
            ok, pl = geometry.TryGetPolyline()
            if not ok or pl is None:
                raise ValueError(
                    'Input must be an open Polyline or PolylineCurve'
                )
        else:
            raise ValueError(
                'Input must be an open Polyline or PolylineCurve'
            )

        if pl.Count < 2:
            raise ValueError('Reinforcement centerline needs at least 2 points')
        if pl.IsClosed:
            raise ValueError('Reinforcement centerline must be open')

        return [[float(p.X), float(p.Y), float(p.Z)] for p in pl]

    def RunScript(self, Polyline, Spec: str, Diameter: float):
        ReinforcementJson = ''

        try:
            if Polyline is None:
                self._addWarning('Polyline input failed to collect data')
                return ReinforcementJson

            spec = (Spec or '').strip()
            if not spec:
                self._addError('Spec must be a non-empty string')
                return ReinforcementJson

            try:
                diameter = float(Diameter)
            except (TypeError, ValueError):
                self._addError('Diameter must be a number')
                return ReinforcementJson
            if diameter <= 0:
                self._addError('Diameter must be greater than zero')
                return ReinforcementJson

            points = self.extract_open_polyline_points(Polyline)
            payload = {
                'spec': spec,
                'diameter': diameter,
                'points': points,
            }
            ReinforcementJson = json.dumps(payload)
            self.Component.Message = (
                f'Reinforcement {spec} Ø{diameter:g} mm, '
                f'{len(points)} points'
            )
            return ReinforcementJson

        except ValueError as e:
            self._addError(str(e))
            return ReinforcementJson
        except Exception as e:
            self._addError(f'Unexpected error: {e}')
            raise e
