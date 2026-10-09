#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
# r: d2p-core-py==0.1.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# D2P WRAPPER IMPORTS ---------------------------------------------------------
from d2p_core import ComponentType, GHComponent, Member, Settings  # NOQA
from D2P.Core.Components.Primitives import BaseObject  # NOQA
from D2P.Core.Interfaces import IBaseObject  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'PassportToD2P'  # NOQA
ghenv.Component.NickName = 'PassportToD2P'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '9 D2P Components Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Converts component passport JSON into an in-memory D2P GHComponent. Geometry '
    'is registered as a nested Member tree via SetMember (D2P ParentMember '
    '+ : layer paths) in the canonical orientation of the piece (frame '
    'applied, centred at the origin) or where its csc_placement puts it; '
    'the component plane is the plane of the canonical piece. Every baked '
    'component gets id_<identity> and snap_<snapshot> shells so layer paths '
    'stay consistent for single- and multi-snapshot component passport and distinct '
    'across catalog identities. The D2P type id comes from the original '
    'function (IFC class). Optional Parent prefixes ShortName for D2P child '
    'naming. The convention user text (csc_identity_id, csc_snapshot_id, '
    'csc_placement, csc_component) is stored on the geometry objects of the '
    'component (D2P commits its label without user text): ReadFromD2P and '
    'SyncWithRhinoDoc read it back. '
    'MeshMode: best | inline | reduced | detailed | all. '
    'CloudMode: best | inline | detailed | all (optional; defaults to '
    'MeshMode, with reduced mapped to inline). '
    'SnapshotScope: current | all.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.read import (authored_only, drawable_proxies)  # NOQA
    from csc_gh.convention import (ConventionError, KEY_COMPONENT, d2p_type_id, d2p_type_name, frame_of, part_values, piece_plane, resolve_placement, tag_values)  # NOQA
    from csc_gh.rhino import (placement_transform, plane_from_frame, proxy_to_rhino)  # NOQA
    from csc_gh.doc import (marker_points)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261005 too old or missing: run CSC_Update, '
        'then restart Rhino')


# Mesh resolution preference for MeshMode=best (highest fidelity first)
_MESH_BEST_CHAIN = ('detailed', 'reduced', 'inline')
# Point clouds have no reduced PLY; best prefers the full cloud then inline.
_CLOUD_BEST_CHAIN = ('detailed', 'inline')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('D2PComponent', 'D2PComponent',
     'In-memory D2P GHComponent (.NET IComponentBase) per component passport entry. RetrieveGeometry accepts layer segments such as id_, snap_, Mesh, 00, or detailed (recursive).'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class _MemberTree:
    """
    Builds a D2P-native member hierarchy (shell parents + geometry leaves).

    Children are attached with SetMember so the wrapper can unwrap Python
    Member objects and so ParentMember / nested DynamicMembers stay in
    sync (same pattern as D2P.Core.Utility.Members.FindMembers).

    D2P writes the label of a component with fresh attributes when it
    commits, so user text set on the label is lost; the geometry objects keep
    theirs. ``text`` (the two ids) goes on every object of the leaves added
    while it is set, ``carrier`` (the full convention values) on the first
    object only; ReadFromD2P and SyncWithRhinoDoc merge the keys of a group.
    """

    def __init__(self, component, layer_color):
        self._component = component
        self._color = layer_color
        self._shells = {}
        self.has_members = False
        self.text = {}
        self.carrier = None

    def _attach(self, member, parent=None):
        if parent is not None:
            parent.SetMember(member)
        else:
            self._component.SetMember(member)
        self.has_members = True
        return member

    def _shell(self, key, layer_name, parent=None):
        if key in self._shells:
            return self._shells[key]
        member = Member(self._component, layer_name, self._color)
        self._shells[key] = member
        return self._attach(member, parent)

    def _base_object(self, geometry):
        """The geometry with attributes holding the user text."""
        attributes = Rhino.DocObjects.ObjectAttributes()
        values = dict(self.text)
        if self.carrier:
            values.update(self.carrier)
            self.carrier = None
        for key, value in values.items():
            attributes.SetUserString(key, str(value))
        return BaseObject(geometry, attributes)

    def _parent_of(self, path_segments):
        parent = None
        for i, segment in enumerate(path_segments[:-1]):
            key = tuple(path_segments[:i + 1])
            parent = self._shell(key, segment, parent)
        return parent

    def add_leaf(self, path_segments, geometry):
        if geometry is None or not path_segments:
            return
        parent = self._parent_of(path_segments)
        leaf = Member(
            self._component, path_segments[-1], self._color)
        leaf.SetObject(self._base_object(geometry))
        self._attach(leaf, parent)

    def add_leaf_many(self, path_segments, geometries):
        if not geometries or not path_segments:
            return
        parent = self._parent_of(path_segments)
        leaf = Member(
            self._component, path_segments[-1], self._color)
        objects = System.Collections.Generic.List[IBaseObject]()
        for geometry in geometries:
            objects.Add(self._base_object(geometry))
        leaf.SetObjects(objects)
        self._attach(leaf, parent)


class CSC_PassportToD2P(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005

    D2P member layer taxonomy (SetMember tree)
    -----------------------------------------
    Shell members group geometry; leaves hold Rhino geometry.
    Nested members are attached with SetMember (sets ParentMember).

    Every member path always starts with catalog identity, then snapshot:

        id_<8> -> snap_<8> -> Mesh -> 00 -> detailed
        id_<8> -> snap_<8> -> PointCloud -> 00 -> detailed
        id_<8> -> snap_<8> -> Proxy -> 00         (authored shapes)
        id_<8> -> snap_<8> -> Marker -> 00        (capture markers)

    id_* distinguishes catalog identities when baking (D2P shares type
    root layers across instances). snap_* is always present so single- and
    multi-snapshot passport share the same depth.

    D2P component naming (optional Parent input)
    --------------------------------------------
    ShortName = parent.ShortName + NameDelimiter + snapshot.name
    (same rule as D2P CreateComponent). Does NOT use CSC parent_identities.

    Placement (8.98)
    ----------------
    Geometry is drawn at T = placement_transform(Q), Q = the passport's
    csc_placement, else the placement that puts the piece in its frame. The
    component plane (the label) is P = Q . frame, the plane of the canonical
    piece, which is what csc_placement means in the user text. The ids go on
    every geometry object, the full convention on the first one.
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
        self.InputParams[0].Description = (
            'Component passport JSON ({identity, snapshot} or future {snapshots[]}) '
            'from CSC catalog components.'
        )
        if self.InputParams.Count > 1:
            self.InputParams[1].Description = (
                "Mesh resolution: 'best' (default), 'inline', 'reduced', "
                "'detailed', or 'all' (register every available variant "
                'as separate leaf members).'
            )
        if self.InputParams.Count > 2:
            self.InputParams[4].Description = (
                "Point-cloud resolution: 'best' (default), 'inline', "
                "'detailed', or 'all'. 'reduced' is accepted as an alias "
                'for inline (no reduced point-cloud PLY exists). Empty '
                'inherits MeshMode (reduced maps to inline).'
            )
        if self.InputParams.Count > 3:
            self.InputParams[2].Description = (
                "Snapshot scope: 'current' (default) uses snapshots[0] "
                "only; 'all' includes every passport.snapshots[] entry. "
                'Each snapshot is always under a snap_* member shell.'
            )
        if self.InputParams.Count > 4:
            delim = Settings.NameDelimiter
            self.InputParams[3].Description = (
                'Optional D2P parent component (Generic) or parent ShortName '
                f'(text). Child ShortName becomes parent{delim}name '
                'for D2P parent-child retrieval. '
                'Ignores CSC parent_identities.'
            )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def _normalize_mode(self, value: str, allowed: tuple, default: str) -> str:
        key = (value or default).strip().lower()
        if key in allowed:
            return key
        self._addWarning(
            f'Unknown mode {value!r}, using {default!r}'
        )
        return default

    def _type_id(self, original_function: str) -> str:
        return d2p_type_id(original_function)

    def _type_name(self, original_function: str) -> str:
        return d2p_type_name(original_function)

    def _snapshot_id(self, snapshot: dict) -> str:
        return str(snapshot.get('_id') or snapshot.get('id') or '')

    def _snapshot_color(self, snapshot: dict) -> tuple:
        color = snapshot.get('color') or [110, 110, 110]
        try:
            return (int(color[0]), int(color[1]), int(color[2]))
        except (TypeError, ValueError, IndexError):
            return (110, 110, 110)

    def _single(self, identity: dict, snapshot: dict) -> dict:
        """A passport of one snapshot (the placement key sits on it)."""
        return {'identity': identity, 'snapshots': [snapshot]}

    def _placement(self, identity: dict, snapshot: dict) -> dict:
        """Q: the placement of the stored geometry of a snapshot (its own
        csc_placement, else the one that puts it in its frame)."""
        placed = resolve_placement(self._single(identity, snapshot))
        if placed is None:
            raise ConventionError(
                'the snapshot has no frame yet (geometry still being '
                'processed?)')
        return placed

    def _xform(self, identity: dict, snapshot: dict):
        return placement_transform(self._placement(identity, snapshot))

    def _identity_scope_label(self, identity: dict) -> str:
        iid = str(
            identity.get('_id') or identity.get('id') or ''
        ).replace('-', '')
        if not iid:
            return 'id_unknown'
        return f'id_{iid[:8]}'

    def _snapshot_scope_label(self, snapshot: dict) -> str:
        sid = self._snapshot_id(snapshot).replace('-', '')
        if not sid:
            return 'snap_unknown'
        return f'snap_{sid[:8]}'

    def _geometry_path(
            self,
            identity_label: str,
            snapshot_label: str,
            kind: str,
            index: int,
            source: str = None) -> list:
        path = [identity_label, snapshot_label, kind, f'{index:02d}']
        if source:
            path.append(source)
        return path

    def _resolve_parent_short_name(self, parent) -> str:
        if parent is None:
            return ''
        if isinstance(parent, str):
            return parent.strip()
        if hasattr(parent, 'ShortName'):
            name = parent.ShortName
            if name:
                return str(name)
        if hasattr(parent, 'NetObj'):
            net = parent.NetObj
            if hasattr(net, 'ShortName') and net.ShortName:
                return str(net.ShortName)
        text = str(parent).strip()
        return text if text and text != 'None' else ''

    def _child_short_name(self, base_name: str, parent) -> str:
        parent_name = self._resolve_parent_short_name(parent)
        if not parent_name:
            return base_name
        delimiter = Settings.NameDelimiter
        if delimiter in base_name:
            self._addRemark(
                f'ShortName {base_name!r} contains D2P name delimiter '
                f'{delimiter!r}; parent-child retrieval may be ambiguous'
            )
        return f'{parent_name}{delimiter}{base_name}'

    def _user_text(
            self,
            identity: dict,
            snapshot: dict,
            passport_json: str = None):
        """``(ids, carrier)``: the user text of every object of the piece
        (the two ids) and of the first one (the convention values and the
        descriptive keys of the identity)."""
        single = self._single(identity, snapshot)
        ids = part_values(single)
        carrier = tag_values(single)
        if passport_json:
            carrier[KEY_COMPONENT] = passport_json
        parent_identities = identity.get('parent_identities')
        if parent_identities:
            carrier['csc_parent_identities'] = json.dumps(parent_identities)
        if identity.get('original_function') is not None:
            carrier['csc_original_function'] = str(
                identity.get('original_function'))
        if identity.get('material') is not None:
            carrier['csc_material'] = str(identity.get('material'))
        if snapshot.get('fragment') is not None:
            carrier['csc_fragment'] = str(bool(snapshot['fragment']))
        return ids, carrier

    def _iter_snapshot_blocks(self, passport: dict, snapshot_scope: str):
        """Yield snapshot dicts from passport.snapshots[]."""
        snapshots = passport.get('snapshots') or []
        if not isinstance(snapshots, list):
            snapshots = []

        if snapshot_scope == 'all':
            for snap in snapshots:
                if isinstance(snap, dict):
                    yield snap
            return

        if snapshots and isinstance(snapshots[0], dict):
            yield snapshots[0]

    def _get_auth_core(self):
        return sc.sticky.get('CSC_AuthCore')

    def _build_inline_mesh(self, mesh_data: dict, default_color: tuple):
        vertices = mesh_data.get('vertices')
        faces = mesh_data.get('faces')
        if not vertices or not faces:
            return None

        mesh = Rhino.Geometry.Mesh()
        for v in vertices:
            mesh.Vertices.Add(float(v[0]), float(v[1]), float(v[2]))
        for f in faces:
            if len(f) == 3:
                mesh.Faces.AddFace(f[0], f[1], f[2])
            elif len(f) == 4:
                mesh.Faces.AddFace(f[0], f[1], f[2], f[3])

        colors = mesh_data.get('colors')
        if colors:
            for c in colors:
                mesh.VertexColors.Add(int(c[0]), int(c[1]), int(c[2]))
        else:
            r, g, b = default_color
            for _ in range(len(vertices)):
                mesh.VertexColors.Add(r, g, b)

        mesh.Normals.ComputeNormals()
        mesh.Compact()
        return mesh

    def _fetch_ply_mesh(self, auth_core, snapshot_id: str,
                        mesh_index: int, resolution: str):
        if not auth_core:
            return None
        mesh, _etag, _cached = auth_core.cached_get_snapshot_mesh(
            snapshot_id, mesh_index, resolution)
        return mesh

    def _mesh_sources_for_index(
            self,
            mesh_mode: str,
            ply_available: list,
            inline_available: bool) -> list:
        ply_set = {r.strip().lower() for r in (ply_available or [])}

        if mesh_mode == 'all':
            sources = []
            if inline_available:
                sources.append('inline')
            for res in ('reduced', 'detailed'):
                if res in ply_set:
                    sources.append(res)
            return sources

        if mesh_mode in ('reduced', 'detailed'):
            if mesh_mode in ply_set:
                return [mesh_mode]
            if inline_available and mesh_mode == 'reduced':
                return ['inline']
            return []

        if mesh_mode == 'inline':
            return ['inline'] if inline_available else []

        for res in _MESH_BEST_CHAIN:
            if res == 'inline' and inline_available:
                return ['inline']
            if res in ply_set:
                return [res]
        return ['inline'] if inline_available else []

    def _resolve_cloud_mode(self, cloud_mode, mesh_mode: str) -> str:
        """
        CloudMode when set; otherwise inherit MeshMode (reduced -> inline).
        """
        if cloud_mode is None or (
                isinstance(cloud_mode, str) and not cloud_mode.strip()):
            if mesh_mode == 'reduced':
                return 'inline'
            return mesh_mode
        return self._normalize_mode(
            str(cloud_mode),
            ('best', 'inline', 'reduced', 'detailed', 'all'),
            'best',
        )

    def _fetch_ply_point_cloud(self, auth_core, snapshot_id: str, index: int):
        if not auth_core:
            return None
        return auth_core.cached_get_snapshot_point_cloud(
            snapshot_id, index)

    def _cloud_sources_for_index(
            self,
            cloud_mode: str,
            inline_available: bool) -> list:
        if cloud_mode == 'all':
            sources = []
            if inline_available:
                sources.append('inline')
            sources.append('detailed')
            return sources
        if cloud_mode in ('inline', 'reduced'):
            return ['inline'] if inline_available else []
        if cloud_mode == 'detailed':
            return ['detailed']
        sources = []
        for res in _CLOUD_BEST_CHAIN:
            if res == 'inline' and inline_available:
                sources.append('inline')
            elif res == 'detailed':
                sources.append('detailed')
        if not sources and inline_available:
            return ['inline']
        return sources

    def _build_point_cloud(self, pc_data: dict):
        cloud = Rhino.Geometry.PointCloud()
        pts = pc_data.get('points', [])
        if not pts:
            return None
        cl = pc_data.get('colors')
        if cl and len(cl) == len(pts):
            for p, c in zip(pts, cl):
                cloud.Add(
                    Rhino.Geometry.Point3d(p[0], p[1], p[2]),
                    System.Drawing.Color.FromArgb(*c),
                )
        else:
            for p in pts:
                cloud.Add(Rhino.Geometry.Point3d(p[0], p[1], p[2]))
        return cloud

    def _build_members_for_snapshot(
            self,
            tree: _MemberTree,
            snapshot: dict,
            identity_label: str,
            snapshot_label: str,
            identity_id: str,
            mesh_mode: str,
            cloud_mode: str,
            auth_core,
            xform):
        geometry = snapshot.get('geometry', {}) or {}
        if not geometry:
            return

        snapshot_color = self._snapshot_color(snapshot)
        snapshot_id = self._snapshot_id(snapshot)
        res_map = snapshot.get('mesh_ply_resolutions', {}) or {}
        inline_meshes = geometry.get('meshes', []) or []

        # authored shapes (a web-authored box, a migrated extrusion) of a
        # piece that has no mesh and no cloud: from proxy params + placement
        if authored_only(snapshot):
            for idx, proxy in drawable_proxies(snapshot):
                if (proxy.get('fit') or {}).get('method') != 'authored':
                    continue
                shape = proxy_to_rhino(proxy)
                if shape is None:
                    continue
                shape.Transform(xform)
                tree.add_leaf(
                    self._geometry_path(
                        identity_label, snapshot_label, 'Proxy', idx),
                    shape,
                )

        for idx, mesh_data in enumerate(inline_meshes):
            ply_available = res_map.get(str(idx), []) or []
            inline_ok = bool(
                mesh_data.get('vertices') and mesh_data.get('faces'))
            for source in self._mesh_sources_for_index(
                    mesh_mode, ply_available, inline_ok):
                mesh = None
                if source == 'inline':
                    mesh = self._build_inline_mesh(mesh_data, snapshot_color)
                elif snapshot_id and auth_core:
                    mesh = self._fetch_ply_mesh(
                        auth_core, snapshot_id, idx, source)
                if mesh is None:
                    if source != 'inline':
                        self._addRemark(
                            f'PLY {source} unavailable for mesh {idx} '
                            f'({snapshot_id or identity_id})')
                    continue
                mesh.Transform(xform)
                tree.add_leaf(
                    self._geometry_path(
                        identity_label, snapshot_label,
                        'Mesh', idx, source),
                    mesh,
                )

        for idx, pc_data in enumerate(geometry.get('point_clouds', []) or []):
            inline_ok = bool(
                isinstance(pc_data, dict)
                and (pc_data.get('points') or [])
            )
            placed = False
            for source in self._cloud_sources_for_index(
                    cloud_mode, inline_ok):
                if cloud_mode == 'best' and placed:
                    break
                cloud = None
                if source == 'inline':
                    cloud = self._build_point_cloud(pc_data)
                elif snapshot_id and auth_core:
                    try:
                        cloud = self._fetch_ply_point_cloud(
                            auth_core, snapshot_id, idx)
                    except Exception as e:
                        self._addWarning(
                            'Point cloud PLY fetch failed '
                            f'for index {idx}: {str(e)}')
                if cloud is None:
                    if source != 'inline':
                        self._addRemark(
                            f'PLY detailed unavailable for point cloud '
                            f'{idx} ({snapshot_id or identity_id})')
                    continue
                cloud.Transform(xform)
                tree.add_leaf(
                    self._geometry_path(
                        identity_label, snapshot_label,
                        'PointCloud', idx, source),
                    cloud,
                )
                placed = True

        markers = [Rhino.Geometry.Point(point)
                   for _, _, point in marker_points(snapshot, xform)]
        if markers:
            tree.add_leaf_many(
                self._geometry_path(
                    identity_label, snapshot_label, 'Marker', 0),
                markers,
            )

    def _passport_to_d2p(
            self,
            passport: dict,
            mesh_mode: str,
            snapshot_scope: str,
            parent=None,
            passport_json: str = None,
            cloud_mode: str = 'best'):
        identity = passport.get('identity') or {}
        snapshots = list(self._iter_snapshot_blocks(passport, snapshot_scope))
        if not identity or not snapshots:
            raise ValueError(
                'Component passport JSON missing identity or snapshot data')

        primary = snapshots[0]
        # the placement first: a piece without a frame cannot be placed
        placement = self._placement(identity, primary)
        original_function = identity.get('original_function')
        type_id = self._type_id(original_function)
        type_name = self._type_name(original_function)
        layer_color = self._snapshot_color(primary)
        component_type = ComponentType(
            type_id,
            type_name,
            LabelSize=2.5,
            LayerColor=layer_color,
        )

        base_name = str(
            primary.get('name') or identity.get('_id') or 'Component')
        short_name = self._child_short_name(base_name, parent)
        # the plane of the canonical piece: P = Q . frame
        plane = plane_from_frame(
            piece_plane(placement, frame_of(primary)))
        component = GHComponent(component_type, short_name, plane)

        ids, carrier = self._user_text(identity, primary, passport_json)

        identity_label = self._identity_scope_label(identity)
        auth_core = self._get_auth_core()
        ply_needed = (
            mesh_mode in ('best', 'reduced', 'detailed', 'all')
            or cloud_mode in ('best', 'detailed', 'all')
        )
        if ply_needed and not auth_core:
            self._addRemark(
                'No CSC_AuthCore in sticky; PLY resolutions unavailable'
            )

        tree = _MemberTree(component, layer_color)
        for snapshot in snapshots:
            # the user text names the primary snapshot only
            tree.text, tree.carrier = (
                (ids, carrier) if snapshot is primary else ({}, None))
            self._build_members_for_snapshot(
                tree,
                snapshot,
                identity_label,
                self._snapshot_scope_label(snapshot),
                identity.get('_id') or 'unknown',
                mesh_mode,
                cloud_mode,
                auth_core,
                self._xform(identity, snapshot),
            )

        if not tree.has_members:
            self._addWarning(
                f'No geometry members created for {short_name} '
                f'({identity.get("_id")})'
            )

        return component

    def RunScript(self,
            ComponentPassport: Grasshopper.DataTree[object],
            MeshMode,
            CloudMode,
            SnapshotScope,
            Parent):
        if self._stop():
            return empty_outputs()
        Component = Grasshopper.DataTree[System.Object]()

        mesh_mode = self._normalize_mode(
            MeshMode,
            ('best', 'inline', 'reduced', 'detailed', 'all'),
            'best',
        )
        cloud_mode = self._resolve_cloud_mode(CloudMode, mesh_mode)
        snapshot_scope = self._normalize_mode(
            SnapshotScope,
            ('current', 'all'),
            'current',
        )

        if not ComponentPassport or ComponentPassport.DataCount == 0:
            msg = 'Input ComponentPassport failed to collect data!'
            self._addWarning(msg)
            return Component

        converted = 0
        try:

            for i in range(ComponentPassport.BranchCount):
                ghp = ComponentPassport.Paths[i]
                for comp_json in ComponentPassport.Branches[i]:
                    if not comp_json:
                        self._addWarning('Empty component passport entry, skipping')
                        continue
                    try:
                        passport = json.loads(comp_json)
                        d2p_component = self._passport_to_d2p(
                            passport,
                            mesh_mode,
                            snapshot_scope,
                            Parent,
                            comp_json,
                            cloud_mode,
                        )
                        Component.Add(d2p_component.NetObj, ghp)
                        converted += 1
                    except json.JSONDecodeError as e:
                        self._addError(f'Failed to parse component passport JSON: {e}')
                    except Exception as e:
                        self._addError(
                            f'Failed to convert component passport entry: {e}'
                        )

            if converted:
                self._state(f'Converted {converted}')
                self._addRemark(
                    f'Successfully converted {converted} component(s) '
                    f'(mesh={mesh_mode}, cloud={cloud_mode}, '
                    f'snapshots={snapshot_scope})'
                )
            return Component

        except Exception as e:
            msg = f'Unexpected error during conversion: {e}'
            self._addError(msg)
            return Component
