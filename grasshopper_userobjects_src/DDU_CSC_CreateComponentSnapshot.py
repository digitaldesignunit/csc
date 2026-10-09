#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA
import os  # NOQA
import uuid  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateComponentSnapshot'  # NOQA
ghenv.Component.NickName = 'CreateComponentSnapshot'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds the request that records a new state of an existing '
    'component (POST /identities/{id}/snapshots) or, with Supersedes, a '
    'correction of a published state with its new scan (POST '
    '/snapshots/{id}/supersede): the builder objects (SnapshotMetadata, '
    'Capture) and the geometry. Reduces and stages the mesh files for '
    'AddComponentSnapshot. The frame is derived by the server.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, loads_fragment, problems_of_envelope, snapshot_body, snapshot_envelope, staging_key)  # NOQA
    from csc_gh.rhino import (stage_geometry)  # NOQA
    from csc_gh.upload import (clear_staging, commit_staging, staging_root)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261005 too old or missing: run CSC_Update, '
        'then restart Rhino')


DEFAULT_RGB = (110, 110, 110)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('SnapshotRequest', 'SnapshotRequest',
     'Request JSON for AddComponentSnapshot (the state and where it goes)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_CreateComponentSnapshot(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Empty the staging folder of files waiting for an Add component'
        )
        self.InputParams[1].Description = (
            'Id of the component'
        )
        self.InputParams[2].Description = (
            'SnapshotMetadata JSON (name, colour, location, notes ...)'
        )
        self.InputParams[3].Description = (
            'Capture JSON (how the geometry was recorded); optional'
        )
        self.InputParams[4].Description = (
            'Meshes, point clouds, extrusions (-> prism) and box-shaped breps '
            '(-> box). Meshes are reduced for the Preview and the Reduced '
            'level; the original is kept.'
        )
        self.InputParams[5].Description = (
            'Id of the published state this one corrects (empty: a new state)'
        )
        self.InputParams[6].Description = (
            'Move the centroid of the geometry to the origin before it is '
            'stored (default false: stored coordinates are those you give)'
        )
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            ClearLocalStorage: bool,
            IdentityID: str,
            Snapshot: str,
            Capture: str,
            Geometry: list[Rhino.Geometry.GeometryBase],
            Supersedes: str,
            Centre: bool):
        if self._stop():
            return empty_outputs()
        SnapshotRequest = ''
        tmp_dir = None
        try:
            # ClearLocalStorage empties the staging folder and stops here
            if ClearLocalStorage:
                folder = clear_staging()
                self._state('Staging folder cleared')
                self._addRemark(f'Cleared {folder}')
                return SnapshotRequest

            if not Geometry:
                raise BuildError('Input Geometry failed to collect data')
            root = staging_root()
            os.makedirs(root, exist_ok=True)
            tmp_dir = os.path.join(root, '_tmp_' + uuid.uuid4().hex)
            meta = loads_fragment(Snapshot, 'Snapshot') or {}
            geometry, mani, move = stage_geometry(
                list(Geometry), tmp_dir, meta.get('color') or DEFAULT_RGB,
                bool(Centre))
            snapshot_dict = snapshot_body(meta, geometry, Capture)
            body = snapshot_envelope(IdentityID, snapshot_dict, Supersedes)

            problems = problems_of_envelope(body)
            if problems:
                raise BuildError('\n'.join(problems))
            text_json = json.dumps(body, sort_keys=True)
            key = staging_key(text_json)
            folder = commit_staging(tmp_dir, key, mani)
            tmp_dir = None
            SnapshotRequest = text_json
            files = sum(len(v) for v in mani.get('meshes', {}).values()) \
                + len(mani.get('point_clouds', []))
            self._state('Request built' + (
                f' ({files} file(s) staged)' if files else ''))
            if any(move):
                self._addRemark(
                    'Centred: the geometry was moved by '
                    f'({move[0]:.3f}, {move[1]:.3f}, {move[2]:.3f})')
            if folder:
                self._addRemark(f'Staged files: {folder}')
            return SnapshotRequest
        except BuildError as error:
            self._addError(str(error))
        except ValueError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        finally:
            if tmp_dir and os.path.isdir(tmp_dir):
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return SnapshotRequest
