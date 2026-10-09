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
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'DisassembleComponent'  # NOQA
ghenv.Component.NickName = 'DisassembleComponent'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Parses component passport JSON ({identity, snapshots[]}) and outputs individual '
    'fields as Grasshopper-native types: the preview geometry (meshes, '
    'point clouds, authored shapes), the frame and the box on it, the '
    'condition grade, the origin (and whether the piece is still in '
    'place), the pieces left of a batch and the capture markers. Geometry is in '
    'the stored coordinates of the piece, moved by its client-side '
    'csc_placement when it has one.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.read import (authored_only, box_of, capture_markers, condition_grade, drawable_proxies, load_passport, parts, placement_of)  # NOQA
    from csc_gh.rhino import (inline_cloud_to_rhino, inline_mesh_to_rhino, placement_transform, plane_from_frame, proxy_to_rhino)  # NOQA
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
    ('IdentityID', 'IdentityID',
     'Identity ID (GUID)'),
    ('Name', 'Name',
     'Snapshot name (e.g. My Component 01)'),
    ('OriginalFunction', 'OriginalFunction',
     'Original function (IFC class, e.g. IfcBeam)'),
    ('Material', 'Material',
     'Component material (id)'),
    ('Color', 'Color',
     'Snapshot color as System.Drawing.Color'),
    ('Location', 'Location',
     'Snapshot location as Point3d (X=latitude, Y=longitude, Z=0)'),
    ('BoundingBox', 'BoundingBox',
     'The box of the piece on its frame (extents bbx), as a '
     'Rhino.Geometry.Box in the stored coordinates'),
    ('Frame', 'Frame',
     'The frame of the piece as a plane (centre of the box, canonical '
     'axes) in the stored coordinates'),
    ('Descriptors', 'Descriptors',
     'Snapshot descriptors/metadata as JSON string'),
    ('Geometry', 'Geometry',
     'Geometry of the piece: Rhino geometry objects (meshes, point '
     'clouds, authored shapes). Point clouds prefer the full PLY when '
     'Session is signed in, else the inline preview.'),
    ('CaptureMarkers', 'CaptureMarkers',
     'Capture markers as Point3d objects (a scanning rig is not part of '
     'the geometry)'),
    ('Capture', 'Capture',
     'Capture block as JSON (method, device, coordinate system, markers '
     'with label and role, fixtures)'),
    ('Attributes', 'Attributes',
     'Identity attributes as JSON string'),
    ('ConditionGrade', 'ConditionGrade',
     'Overall condition grade (0=unusable as is, 1=poor, 2=average, '
     '3=good) from the evidence; empty when not assessed'),
    ('ManufacturedAt', 'ManufacturedAt',
     'Component manufacturing date as ISO-8601 UTC timestamp'),
    ('ManufacturedPrecision', 'ManufacturedPrecision',
     'Precision qualifier for ManufacturedAt (exact, day, month, year, '
     'unknown)'),
    ('Origin', 'Origin',
     'Origin block as JSON (kind, date, place, construction work, '
     'method, who ...)'),
    ('ParentIdentities', 'ParentIdentities',
     'Parent identity IDs (GUIDs) this identity was cut from'),
    ('Planned', 'Planned',
     'True while the piece is still in place: identified in its works, '
     'not yet deinstalled'),
    ('Remaining', 'Remaining',
     'Pieces left in a batch (recorded quantity minus the pieces drawn); '
     'empty for a piece that is not a batch'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) == 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_DisassembleComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005a
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
            'Component passport JSON ({identity, snapshots[]}) fetched from the server.'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def get_auth_core_from_sticky(self):
        """Return Session AuthCore when signed in; None otherwise."""
        return sc.sticky.get('CSC_AuthCore')

    def fetch_snapshot_point_clouds(self, auth_core, snapshot,
                                    identity_id=None):
        """Prefer the full point-cloud PLY via the Session cache, then the
        inline preview; ``[(cloud, primitive index)]``."""
        geometry = snapshot.get('geometry', {}) or {}
        inline_clouds = geometry.get('point_clouds', []) or []
        snapshot_id = snapshot.get('_id')
        results = []
        for index, entry in enumerate(inline_clouds):
            cloud = None
            if auth_core and snapshot_id:
                try:
                    cloud = auth_core.cached_get_snapshot_point_cloud(
                        snapshot_id, index)
                except Exception as error:
                    self._addWarning('Point cloud PLY fetch failed '
                                     f'for index {index}: {error}')
            if cloud is None:
                cloud = inline_cloud_to_rhino(entry)
            if cloud is not None:
                results.append((cloud, index))
            else:
                self._addWarning(
                    f'Point cloud {index} of identity {identity_id} dropped: '
                    'empty, not valid, not finite or wider than 10 km')
        return results

    def snapshot_geometry(self, auth_core, snapshot, identity_id):
        """``[(rhino geometry, kind, index)]`` of a snapshot."""
        geometry = snapshot.get('geometry', {}) or {}
        color = snapshot.get('color') or [110, 110, 110]
        items = []
        for index, entry in enumerate(geometry.get('meshes', []) or []):
            mesh = inline_mesh_to_rhino(entry, color)
            if mesh is None:
                self._addWarning(
                    f'Mesh {index} of identity {identity_id} dropped: '
                    'empty, not valid, not finite or wider than 10 km')
                continue
            items.append((mesh, 'mesh', index))
        for cloud, index in self.fetch_snapshot_point_clouds(
                auth_core, snapshot, identity_id):
            items.append((cloud, 'point_cloud', index))
        if authored_only(snapshot):
            for index, proxy in drawable_proxies(snapshot):
                if (proxy.get('fit') or {}).get('method') != 'authored':
                    continue
                shape = proxy_to_rhino(proxy)
                if shape is None:
                    self._addWarning(
                        f'Proxy {index} of identity {identity_id} dropped: '
                        'cannot be drawn, not valid, not finite or wider '
                        'than 10 km')
                    continue
                items.append((shape, 'proxy', index))
        return items

    def RunScript(self, ComponentPassport: Grasshopper.DataTree[object]):
        if self._stop():
            return empty_outputs()
        names = ('IdentityID', 'Name', 'OriginalFunction', 'Material', 'Color',
                 'Location', 'BoundingBox', 'Frame', 'Descriptors',
                 'Geometry', 'CaptureMarkers', 'Capture',
                 'Attributes', 'ConditionGrade', 'ManufacturedAt',
                 'ManufacturedPrecision', 'Origin', 'ParentIdentities',
                 'Planned', 'Remaining')
        trees = {n: Grasshopper.DataTree[System.Object]() for n in names}
        __Results = tuple(trees[n] for n in names)
        try:
            if not ComponentPassport or ComponentPassport.DataCount == 0:
                self._addWarning(
                    'Input parameter ComponentPassport failed to collect data')
                return __Results

            auth_core = self.get_auth_core_from_sticky()

            for i in range(ComponentPassport.BranchCount):
                ghp = ComponentPassport.Paths[i]
                for comp in ComponentPassport.Branches[i]:
                    try:
                        passport = load_passport(comp)
                        identity, snapshot = parts(passport)
                        if not identity or not snapshot:
                            self._addWarning('Component passport JSON missing identity/'
                                             'snapshots, skipping entry')
                            continue
                        identity_id = identity.get('_id')
                        trees['IdentityID'].Add(identity_id, ghp)
                        trees['Name'].Add(snapshot.get('name'), ghp)
                        trees['OriginalFunction'].Add(
                            identity.get('original_function'), ghp)
                        trees['Material'].Add(identity.get('material'), ghp)
                        rgb_value = snapshot.get('color') or [110, 110, 110]
                        trees['Color'].Add(System.Drawing.Color.FromArgb(
                            255, *rgb_value), ghp)
                        place = snapshot.get('location') or {}
                        if 'lat' in place and 'lon' in place:
                            trees['Location'].Add(Rhino.Geometry.Point3d(
                                place['lat'], place['lon'], 0.0), ghp)
                        else:
                            trees['Location'].Add(
                                Rhino.Geometry.Point3d(0.0, 0.0, 0.0), ghp)

                        # the client-side placement of the piece, if any
                        placed = placement_of(passport)
                        xform = placement_transform(placed) if placed \
                            else Rhino.Geometry.Transform.Identity

                        for geom, kind, index in self.snapshot_geometry(
                                auth_core, snapshot, identity_id):
                            geom.Transform(xform)
                            geom.SetUserString('csc_component', comp)
                            if kind == 'mesh':
                                geom.SetUserString('csc_mesh_index',
                                                   str(index))
                            elif kind == 'point_cloud':
                                geom.SetUserString('csc_point_cloud_index',
                                                   str(index))
                            else:
                                geom.SetUserString('csc_proxy_index',
                                                   str(index))
                            trees['Geometry'].Add(geom, ghp)

                        # the frame and the box on it
                        box = box_of(snapshot)
                        if box:
                            frame, size = box
                            plane = plane_from_frame(frame)
                            shape = Rhino.Geometry.Box(
                                plane,
                                Rhino.Geometry.Interval(-size[0] / 2,
                                                        size[0] / 2),
                                Rhino.Geometry.Interval(-size[1] / 2,
                                                        size[1] / 2),
                                Rhino.Geometry.Interval(-size[2] / 2,
                                                        size[2] / 2))
                            shape.Transform(xform)
                            plane.Transform(xform)
                            trees['BoundingBox'].Add(shape, ghp)
                            trees['Frame'].Add(plane, ghp)
                        else:
                            self._addWarning(
                                f'Identity {identity_id}: the snapshot has no '
                                'frame yet (geometry still being processed?)')

                        trees['Descriptors'].Add(json.dumps(
                            snapshot.get('descriptors', {}) or {}), ghp)

                        for label, role, point in capture_markers(snapshot):
                            marker = Rhino.Geometry.Point3d(*point)
                            marker.Transform(xform)
                            trees['CaptureMarkers'].Add(marker, ghp)
                        if snapshot.get('capture'):
                            trees['Capture'].Add(json.dumps(
                                snapshot['capture']), ghp)

                        trees['Attributes'].Add(json.dumps(
                            identity.get('attributes', {}) or {}), ghp)
                        grade = condition_grade(snapshot)
                        if grade is not None:
                            trees['ConditionGrade'].Add(grade, ghp)
                        if identity.get('manufactured_at') is not None:
                            trees['ManufacturedAt'].Add(
                                identity['manufactured_at'], ghp)
                        if identity.get('manufactured_precision') is not None:
                            trees['ManufacturedPrecision'].Add(
                                identity['manufactured_precision'], ghp)
                        if identity.get('origin'):
                            trees['Origin'].Add(json.dumps(
                                identity['origin']), ghp)
                        for parent in identity.get('parent_identities') or []:
                            trees['ParentIdentities'].Add(parent, ghp)
                        trees['Planned'].Add(bool(
                            (identity.get('origin') or {}).get('planned')),
                            ghp)
                        if identity.get('remaining') is not None:
                            trees['Remaining'].Add(
                                int(identity['remaining']), ghp)

                    except Exception as error:
                        self._addError(
                            f'Error processing component: {error}')

            return __Results

        except Exception as error:
            self._addError(f'Unexpected error during disassembly: {error}')
            return __Results
