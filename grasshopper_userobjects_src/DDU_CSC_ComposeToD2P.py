#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: d2p-core-py

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# D2P WRAPPER IMPORTS ---------------------------------------------------------
from d2p_core import ComponentType, GHComponent, Member, Settings  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ComposeToD2P'  # NOQA
ghenv.Component.NickName = 'ComposeToD2P'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '9 D2P Components Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Converts CSC compose JSON into an in-memory D2P GHComponent. Geometry '
    'is registered as a nested Member tree via SetMember (D2P ParentMember '
    '+ : layer paths). Every baked component gets id_<identity> and '
    'snap_<snapshot> shells so layer paths stay consistent for single- and '
    'multi-snapshot compose and distinct across catalog identities. '
    'Optional Parent prefixes ShortName for D2P child naming. CSC '
    'identity/snapshot metadata is stored on the component label user text. '
    'MeshMode: best | inline | reduced | detailed | all. '
    'SnapshotScope: current | all.'
)

# CSC identity type -> D2P component type id (2-letter convention)
_TYPE_ID_MAP = {
    'panel': 'PN',
    'beam': 'BM',
    'column': 'CL',
    'slab': 'SB',
    'rubble': 'RB',
    'brick': 'BR',
    'pipe': 'PP',
    'profile': 'PR',
    'connector': 'CN',
    'other': 'OT',
}

# Mesh resolution preference for MeshMode=best (highest fidelity first)
_MESH_BEST_CHAIN = ('detailed', 'reduced', 'inline')


class _MemberTree:
    """
    Builds a D2P-native member hierarchy (shell parents + geometry leaves).

    Children are attached with SetMember so the wrapper can unwrap Python
    Member objects and so ParentMember / nested DynamicMembers stay in
    sync (same pattern as D2P.Core.Utility.Members.FindMembers).
    """

    def __init__(self, component, layer_color):
        self._component = component
        self._color = layer_color
        self._shells = {}
        self.has_members = False

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

    def add_leaf(self, path_segments, geometry):
        if geometry is None or not path_segments:
            return
        parent = None
        for i, segment in enumerate(path_segments[:-1]):
            key = tuple(path_segments[:i + 1])
            parent = self._shell(key, segment, parent)
        leaf = Member(
            self._component, path_segments[-1], self._color)
        leaf.SetObject(geometry)
        self._attach(leaf, parent)

    def add_leaf_many(self, path_segments, geometries):
        if not geometries or not path_segments:
            return
        parent = None
        for i, segment in enumerate(path_segments[:-1]):
            key = tuple(path_segments[:i + 1])
            parent = self._shell(key, segment, parent)
        leaf = Member(
            self._component, path_segments[-1], self._color)
        leaf.SetObjects(geometries)
        self._attach(leaf, parent)


class CSC_ComposeToD2P(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260826

    D2P member layer taxonomy (SetMember tree)
    -----------------------------------------
    Shell members group geometry; leaves hold Rhino geometry.
    Nested members are attached with SetMember (sets ParentMember).

    Every member path always starts with catalog identity, then snapshot:

        id_<8> -> snap_<8> -> Mesh -> 00 -> detailed
        id_<8> -> snap_<8> -> Extrusion -> 00

    id_* distinguishes catalog identities when baking (D2P shares type
    root layers across instances). snap_* is always present so single- and
    multi-snapshot compose share the same depth.

    D2P component naming (optional Parent input)
    --------------------------------------------
    ShortName = parent.ShortName + NameDelimiter + snapshot.name
    (same rule as D2P CreateComponent). Does NOT use CSC parent_identities.
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
            'Compose JSON ({identity, snapshot} or future {snapshots[]}) '
            'from CSC catalog components.'
        )
        if self.InputParams.Count > 1:
            self.InputParams[1].Description = (
                "Mesh resolution: 'best' (default), 'inline', 'reduced', "
                "'detailed', or 'all' (register every available variant "
                'as separate leaf members).'
            )
        if self.InputParams.Count > 2:
            self.InputParams[2].Description = (
                "Snapshot scope: 'current' (default) uses snapshots[0] "
                "only; 'all' includes every compose.snapshots[] entry. "
                'Each snapshot is always under a snap_* member shell.'
            )
        if self.InputParams.Count > 3:
            delim = Settings.NameDelimiter
            self.InputParams[3].Description = (
                'Optional D2P parent component (Generic) or parent ShortName '
                f'(text). Child ShortName becomes parent{delim}name '
                'for D2P parent-child retrieval. '
                'Ignores CSC parent_identities.'
            )
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0 + i].Description = (
            'In-memory D2P GHComponent (.NET IComponentBase) per compose '
            'entry. RetrieveGeometry accepts layer segments such as id_, '
            'snap_, Mesh, 00, or detailed (recursive).'
        )

    def _normalize_mode(self, value: str, allowed: tuple, default: str) -> str:
        key = (value or default).strip().lower()
        if key in allowed:
            return key
        self._addWarning(
            f'Unknown mode {value!r}, using {default!r}'
        )
        return default

    def _type_id(self, identity_type: str) -> str:
        key = (identity_type or 'other').strip().lower()
        if key in _TYPE_ID_MAP:
            return _TYPE_ID_MAP[key]
        if len(key) >= 2:
            return key[:2].upper()
        return 'OT'

    def _type_name(self, identity_type: str) -> str:
        key = (identity_type or 'other').strip().lower()
        return key.replace('_', ' ').title() or 'Other'

    def _snapshot_id(self, snapshot: dict) -> str:
        return str(snapshot.get('_id') or snapshot.get('id') or '')

    def _snapshot_color(self, snapshot: dict) -> tuple:
        color = snapshot.get('color') or [110, 110, 110]
        try:
            return (int(color[0]), int(color[1]), int(color[2]))
        except (TypeError, ValueError, IndexError):
            return (110, 110, 110)

    def _iframe_plane(self, snapshot: dict) -> Rhino.Geometry.Plane:
        try:
            iframe = snapshot['iframe']
            return Rhino.Geometry.Plane(
                Rhino.Geometry.Point3d(*iframe['o']),
                Rhino.Geometry.Vector3d(*iframe['x']),
                Rhino.Geometry.Vector3d(*iframe['y']),
            )
        except (KeyError, TypeError):
            return Rhino.Geometry.Plane.WorldXY

    def _iframe_transform(self, snapshot: dict) -> Rhino.Geometry.Transform:
        iplane = self._iframe_plane(snapshot)
        return Rhino.Geometry.Transform.PlaneToPlane(
            Rhino.Geometry.Plane.WorldXY,
            iplane,
        )

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

    def _attach_csc_metadata(
            self,
            component,
            identity: dict,
            snapshot: dict,
            compose_json: str = None):
        try:
            label = component.Label
            base_objects = list(label.BaseObjects)
            if not base_objects:
                return
            attrs = base_objects[0].Attributes
            identity_id = identity.get('_id') or identity.get('id')
            if identity_id:
                attrs.SetUserString('csc_identity_id', str(identity_id))
            snapshot_id = self._snapshot_id(snapshot)
            if snapshot_id:
                attrs.SetUserString('csc_snapshot_id', snapshot_id)
            parent_identities = identity.get('parent_identities')
            if parent_identities:
                attrs.SetUserString(
                    'csc_parent_identities',
                    json.dumps(parent_identities),
                )
            if identity.get('type') is not None:
                attrs.SetUserString('csc_type', str(identity.get('type')))
            if identity.get('material') is not None:
                attrs.SetUserString(
                    'csc_material', str(identity.get('material')))
            if snapshot.get('assembly') is not None:
                attrs.SetUserString(
                    'csc_assembly', str(bool(snapshot['assembly'])))
            if snapshot.get('fragment') is not None:
                attrs.SetUserString(
                    'csc_fragment', str(bool(snapshot['fragment'])))
            if compose_json:
                attrs.SetUserString('csc_component', compose_json)
        except Exception as e:
            self._addWarning(f'Could not attach CSC metadata to label: {e}')

    def _iter_snapshot_blocks(self, compose: dict, snapshot_scope: str):
        """Yield snapshot dicts from compose.snapshots[]."""
        snapshots = compose.get('snapshots') or []
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

    def _build_extrusion(self, extr: dict):
        tol = Rhino.RhinoMath.SqrtEpsilon
        profile = extr.get('profile') or []
        if len(profile) < 3:
            return None

        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0) for pt in profile]
        if len(pts) >= 2 and pts[0].DistanceTo(pts[-1]) <= tol:
            pts = pts[:-1]
        if len(pts) < 3:
            return None

        pl = Rhino.Geometry.Polyline()
        pl.AddRange(pts)
        if not pl.IsClosed:
            pl.Add(pl[0])

        height = float(extr.get('height', 0))
        if height <= 0:
            return None

        cxt = Rhino.Geometry.Extrusion.Create(
            pl.ToPolylineCurve(),
            Rhino.Geometry.Plane.WorldXY,
            height,
            True,
        )
        if cxt is None:
            return None

        cxt.Translate(Rhino.Geometry.Vector3d(0, 0, height * -0.5))
        return cxt

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

    def _build_marker_points(self, geometry: dict) -> list:
        points = []
        for point_data in geometry.get('marker_points', []) or []:
            if isinstance(point_data, list) and len(point_data) >= 3:
                points.append(
                    Rhino.Geometry.Point(
                        float(point_data[0]),
                        float(point_data[1]),
                        float(point_data[2]),
                    )
                )
        return points

    def _build_members_for_snapshot(
            self,
            tree: _MemberTree,
            snapshot: dict,
            identity_label: str,
            snapshot_label: str,
            identity_id: str,
            mesh_mode: str,
            auth_core):
        geometry = snapshot.get('geometry', {}) or {}
        if not geometry:
            return

        snapshot_color = self._snapshot_color(snapshot)
        xform = self._iframe_transform(snapshot)
        snapshot_id = self._snapshot_id(snapshot)
        res_map = snapshot.get('mesh_ply_resolutions', {}) or {}
        inline_meshes = geometry.get('meshes', []) or []

        for idx, extr in enumerate(geometry.get('extrusions', []) or []):
            xtr = self._build_extrusion(extr)
            if xtr is None:
                continue
            xtr.Transform(xform)
            tree.add_leaf(
                self._geometry_path(
                    identity_label, snapshot_label, 'Extrusion', idx),
                xtr,
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
            cloud = self._build_point_cloud(pc_data)
            if cloud is None:
                continue
            cloud.Transform(xform)
            tree.add_leaf(
                self._geometry_path(
                    identity_label, snapshot_label,
                    'PointCloud', idx, 'inline'),
                cloud,
            )

        markers = self._build_marker_points(geometry)
        if markers:
            for pt in markers:
                pt.Transform(xform)
            tree.add_leaf_many(
                self._geometry_path(
                    identity_label, snapshot_label, 'Marker', 0),
                markers,
            )

    def _compose_to_d2p(
            self,
            compose: dict,
            mesh_mode: str,
            snapshot_scope: str,
            parent=None,
            compose_json: str = None):
        identity = compose.get('identity') or {}
        snapshots = list(self._iter_snapshot_blocks(compose, snapshot_scope))
        if not identity or not snapshots:
            raise ValueError(
                'Compose JSON missing identity or snapshot data')

        primary = snapshots[0]
        identity_type = identity.get('type') or 'other'
        type_id = self._type_id(identity_type)
        type_name = self._type_name(identity_type)
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
        plane = self._iframe_plane(primary)
        component = GHComponent(component_type, short_name, plane)

        self._attach_csc_metadata(
            component, identity, primary, compose_json)

        identity_label = self._identity_scope_label(identity)
        auth_core = self._get_auth_core()
        if (mesh_mode in ('best', 'reduced', 'detailed', 'all')
                and not auth_core):
            self._addRemark(
                'No CSC_AuthCore in sticky; PLY resolutions unavailable'
            )

        tree = _MemberTree(component, layer_color)
        for snapshot in snapshots:
            self._build_members_for_snapshot(
                tree,
                snapshot,
                identity_label,
                self._snapshot_scope_label(snapshot),
                identity.get('_id') or 'unknown',
                mesh_mode,
                auth_core,
            )

        if not tree.has_members:
            self._addWarning(
                f'No geometry members created for {short_name} '
                f'({identity.get("_id")})'
            )

        return component

    def RunScript(self,
            ComponentData: Grasshopper.DataTree[str],
            MeshMode,
            SnapshotScope,
            Parent):
        Component = Grasshopper.DataTree[System.Object]()
        self.Component.Message = ''

        mesh_mode = self._normalize_mode(
            MeshMode,
            ('best', 'inline', 'reduced', 'detailed', 'all'),
            'best',
        )
        snapshot_scope = self._normalize_mode(
            SnapshotScope,
            ('current', 'all'),
            'current',
        )

        if not ComponentData or ComponentData.DataCount == 0:
            msg = 'Input ComponentData failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return Component

        converted = 0
        try:
            self.Component.Message = 'Converting compose to D2P...'

            for i in range(ComponentData.BranchCount):
                ghp = ComponentData.Paths[i]
                for comp_json in ComponentData.Branches[i]:
                    if not comp_json:
                        self._addWarning('Empty compose entry, skipping')
                        continue
                    try:
                        compose = json.loads(comp_json)
                        d2p_component = self._compose_to_d2p(
                            compose,
                            mesh_mode,
                            snapshot_scope,
                            Parent,
                            comp_json,
                        )
                        Component.Add(d2p_component.NetObj, ghp)
                        converted += 1
                    except json.JSONDecodeError as e:
                        self._addError(f'Failed to parse compose JSON: {e}')
                    except Exception as e:
                        self._addError(
                            f'Failed to convert compose entry: {e}'
                        )

            self.Component.Message = (
                f'Converted {converted} compose entr'
                f'{"y" if converted == 1 else "ies"} to D2P'
            )
            if converted:
                self._addRemark(
                    f'Successfully converted {converted} component(s) '
                    f'(mesh={mesh_mode}, snapshots={snapshot_scope})'
                )
            return Component

        except Exception as e:
            msg = f'Unexpected error during conversion: {e}'
            self._addError(msg)
            self.Component.Message = msg
            return Component
