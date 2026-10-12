#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: requests==2.32.5
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchReinforcementLayout'  # NOQA
ghenv.Component.NickName = 'FetchReinforcementLayout'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches the reinforcement layouts recorded for a component as bars: '
    'one polyline per bar, one tree branch per layout record, the newest '
    'record first, with the diameter (mm), steel grade and cover of every '
    'bar, and the id, basis, snapshot and status of every record. '
    'Optionally the bars are made solid (Pipes).\n'
    'Input can be:\n'
    '- Geometry carrying the \'csc_component\' user text\n'
    '- A component passport JSON string ({identity, snapshots[]})\n'
    '- A raw identity_id or snapshot_id\n\n'
    'The points of a layout are stored coordinates of the snapshot it '
    'belongs to. A passport with a placement (ApplyFrame, '
    'TransformComponent) moves the layouts of its own snapshot to where '
    'the piece is placed, like the Fetch geometry components do for the '
    'mesh; layouts of another version stay in their stored coordinates and '
    'are named in a warning. Document units are taken as millimetres (1:1); '
    'a document in another unit gets a warning. Status: published '
    '(default), draft, pending, rejected, withdrawn or all (adds your own '
    'unpublished records).'
)


# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261012'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError)  # NOQA
    from csc_gh.layout import (layout_points, layouts_of, passport_placement, status_param, unit_warning)  # NOQA
    from csc_gh.read import (load_passport)  # NOQA
    from csc_gh.rhino import (mm_per_document_unit, pipe_brep, polyline_curve)  # NOQA
    from csc_gh.upload import (http_error_text)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261012 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Bars', 'Bars',
     'The bars as polylines, one branch per layout record (newest first)'),
    ('Diameter', 'Diameter',
     'Bar diameter in mm, same tree as Bars'),
    ('Spec', 'Spec',
     'Steel grade of each bar (null when not given), same tree as Bars'),
    ('Cover', 'Cover',
     'Measured concrete cover in mm (null when not given), same tree as '
     'Bars'),
    ('RecordID', 'RecordID',
     'Id of each layout record; the list position is the branch index'),
    ('Basis', 'Basis',
     'drawing, scan or exposed, one per branch'),
    ('SnapshotID', 'SnapshotID',
     'Snapshot whose stored coordinates the points of each layout are in, '
     'one per branch'),
    ('Status', 'Status',
     'Status of each layout record, one per branch'),
    ('Pipes', 'Pipes',
     'Solid bars (Breps at the diameter, in mm), same tree as Bars; empty '
     'unless Pipes is true'),
]

NOT_FOUND = 404


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_FetchReinforcementLayout(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261012
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
            'Input can be:\n'
            '- Geometry with the \'csc_component\' user text\n'
            '- A component passport JSON string ({identity, snapshots[]}); '
            'its placement moves the layouts of its snapshot\n'
            '- A raw identity_id or snapshot_id (points stay in stored '
            'coordinates)'
        )
        self.InputParams[1].Description = (
            'published (default), draft, pending, rejected, withdrawn or '
            'all (adds your own unpublished records)'
        )
        self.InputParams[2].Description = (
            'True: also make solid bars (Pipes output, default False)'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addWarning(msg)
            return None
        return auth_core

    def resolve_input(self, auth_core, value):
        """``(id, snapshot_id, placement, is_snapshot)`` of the input: the
        identity (or, for a raw id that may be a snapshot, the id to try),
        the snapshot a passport names and its placement."""
        if (hasattr(value, 'UserStringCount')
                and value.UserStringCount > 0):
            raw = value.GetUserString('csc_component')
            if raw:
                value = raw
        if not isinstance(value, str):
            return None
        text_ = value.strip()
        if not text_:
            return None
        if auth_core.validate_uuid(text_):
            return text_, None, None, True
        passport = load_passport(text_)
        if passport is not None:
            snapshot_id, placement = passport_placement(passport)
            identity = passport.get('identity') or {}
            snapshot = passport['snapshots'][0]
            identity_id = (identity.get('_id') or identity.get('id')
                           or snapshot.get('identity_id'))
            if not identity_id or not auth_core.validate_uuid(
                    str(identity_id)):
                raise BuildError('the passport has no valid identity id')
            return str(identity_id), snapshot_id, placement, False
        try:
            data = json.loads(text_)
        except ValueError:
            data = None
        if (isinstance(data, dict) and data.get('_id')
                and auth_core.validate_uuid(str(data['_id']))):
            return str(data['_id']), None, None, False
        raise BuildError('the input is not a passport, an identity id or '
                         'a snapshot id')

    def fetch_rows(self, auth_core, identity_id, status):
        """``(status code, rows)`` of the layout records of an identity."""
        response = auth_core.authorized_get(
            f'/identities/{identity_id}/evidence',
            params={'method': 'reinforcement_layout', 'status': status})
        if response.status_code == 200:
            return 200, response.json()
        if response.status_code == NOT_FOUND:
            return NOT_FOUND, []
        msg = {
            401: 'Authentication failed. Please sign in again.',
            403: 'Access denied: you may not read this component.',
        }.get(response.status_code) or http_error_text(
            response, 'Fetching the layouts')
        raise BuildError(msg)

    def identity_of_snapshot(self, auth_core, snapshot_id):
        """The identity id of a snapshot id, or None."""
        response = auth_core.authorized_get(f'/snapshots/{snapshot_id}')
        if response.status_code == 200:
            return (response.json() or {}).get('identity_id')
        return None

    def RunScript(self, ComponentPassport, Status: str, Pipes: bool):
        if self._stop():
            return empty_outputs()
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return empty_outputs()
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return empty_outputs()
        if not ComponentPassport:
            self._addWarning('Please provide input data.')
            return empty_outputs()

        Bars = Grasshopper.DataTree[System.Object]()
        Diameter = Grasshopper.DataTree[System.Object]()
        Spec = Grasshopper.DataTree[System.Object]()
        Cover = Grasshopper.DataTree[System.Object]()
        PipeBreps = Grasshopper.DataTree[System.Object]()
        RecordID = System.Collections.Generic.List[str]()
        Basis = System.Collections.Generic.List[str]()
        SnapshotID = System.Collections.Generic.List[str]()
        StatusOut = System.Collections.Generic.List[str]()
        results = (Bars, Diameter, Spec, Cover, RecordID, Basis, SnapshotID,
                   StatusOut, PipeBreps)

        try:
            status = status_param(Status)
            found = self.resolve_input(auth_core, ComponentPassport)
            if found is None:
                self._addWarning('Could not resolve a component from the '
                                 'input.')
                return results
            target_id, snapshot_id, placement, maybe_snapshot = found
            code, rows = self.fetch_rows(auth_core, target_id, status)
            if code == NOT_FOUND and maybe_snapshot:
                identity_id = self.identity_of_snapshot(auth_core, target_id)
                if identity_id:
                    snapshot_id = target_id
                    code, rows = self.fetch_rows(auth_core, identity_id,
                                                 status)
            if code == NOT_FOUND:
                self._addError(f'Component or snapshot {target_id} was not '
                               'found.')
                return results

            layouts, left_out = layouts_of(rows)
            if left_out:
                self._addWarning(
                    f'{len(left_out)} record(s) without readable bars left '
                    f'out: {", ".join(str(i) for i in left_out)}')
            if not layouts:
                self._addWarning(f'No reinforcement layout ({status}) found.')
                self._state('0 layouts')
                return results

            scale, unit_name = mm_per_document_unit()
            note = unit_warning(scale, unit_name)
            if note:
                self._addWarning(note)
            solid = bool(Pipes)
            bar_count = moved = failed = 0
            for index, layout in enumerate(layouts):
                path = Grasshopper.Kernel.Data.GH_Path(index)
                point_lists, warning = layout_points(
                    layout, placement, snapshot_id)
                if warning:
                    self._addWarning(warning)
                elif placement is not None:
                    moved += 1
                for bar, points in zip(layout['bars'], point_lists):
                    curve = polyline_curve(points)
                    Bars.Add(curve, path)
                    Diameter.Add(bar['diameter_mm'], path)
                    Spec.Add(bar['spec'], path)
                    Cover.Add(bar['cover_mm'], path)
                    if solid:
                        pipe = pipe_brep(curve, bar['diameter_mm'] / 2.0)
                        if pipe is None:
                            failed += 1
                        PipeBreps.Add(pipe, path)
                    bar_count += 1
                RecordID.Add(str(layout['id'] or ''))
                Basis.Add(str(layout['basis'] or ''))
                SnapshotID.Add(str(layout['snapshot_id'] or ''))
                StatusOut.Add(str(layout['status'] or ''))
            if moved:
                self._addRemark(
                    f'{moved} layout(s) of snapshot {snapshot_id} moved by '
                    'the placement of the passport (stored to placed)')
            if failed:
                self._addWarning(f'{failed} bar(s) could not be made solid')
            self._state(f'{len(layouts)} layouts, {bar_count} bars')
            return results

        except BuildError as error:
            self._addError(str(error))
        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')
        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')
        except requests.exceptions.RequestException as e:
            self._addError(f'Request error: {str(e)}')
        except Exception as e:
            # includes CSCClientOutdated: its text names the fix
            self._addError(f'Unexpected error: {str(e)}')
        return results
