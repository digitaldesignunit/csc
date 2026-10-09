# The Rhino-document side of the bridge (decisions 7.11, 8.95 4, 8.98).
#
# Bake a piece into the active document, find the pieces in it again and read
# their tag planes back. Used by BakeComponents, SyncWithRhinoDoc and
# ReadFromD2P (and the geometry choice by PassportToD2P). It takes the
# document as an argument so a headless Rhino can run it in a test; it never
# talks to a server on its own (``passport_fetcher`` wraps the Session's
# read-only passport call).
#
# One piece = its geometry (stored coordinates moved by the placement), one
# text object (the tag, at the plane of the canonical piece) carrying the
# convention keys of convention, all in one group on the layer
# CSC_COMPONENTS::<identity id>. The geometry objects carry the two ids and the
# primitive index only; the plane of the text object is the truth, so moving
# the group moves it with the piece and a read-back needs nothing else. A D2P
# component is the same shape (its label is the text object) with the keys on
# its members instead of the label.
#
# Uses ply, build, read, convention and rhino of the package. Python 3.9
# compatible; part of the package csc_gh (decision 8.111).

import System  # NOQA
import Rhino  # NOQA

# the other modules of the package
from .read import (authored_only, capture_markers, drawable_proxies, parts)  # NOQA
from .convention import (ConventionError, KEY_IDENTITY, KEY_PARTS, KEY_PLACEMENT, clean_id, parse_placement, part_values, passport_for_tags, read_tags, resolve_placement, tag_values)  # NOQA
from .rhino import (frame_from_plane, inline_cloud_to_rhino, inline_mesh_to_rhino, placement_transform, plane_from_frame, proxy_to_rhino)  # NOQA

LAYER_ROOT = 'CSC_COMPONENTS'
TAG_HEIGHT_MM = 10.0

# the mesh levels a bake can ask for, each as the PLY resolutions to try in
# order before the inline preview (8.23: preview < reduced < original)
BAKE_LEVELS = {
    'original': ('detailed', 'reduced'),
    'reduced': ('reduced',),
    'preview': (),
}
DEFAULT_COLOR = (110, 110, 110)


# GEOMETRY OF A PIECE ---------------------------------------------------------
def bake_level(value):
    """A level name of an input (empty = original); raises ValueError."""
    key = str(value or 'original').strip().lower()
    if key not in BAKE_LEVELS:
        raise ValueError('level is one of: ' + ', '.join(BAKE_LEVELS))
    return key


def piece_items(auth_core, snapshot, level='original', warn=None):
    """The drawable geometry of a snapshot in stored coordinates, as
    ``[(geometry, kind, index)]`` with kind ``mesh``, ``point_cloud`` or
    ``proxy``: each mesh from the PLY of the level (falling back to the
    inline preview), each cloud from the PLY (the preview when
    ``level='preview'``), and the authored shapes of a piece that has no mesh
    and no cloud. ``auth_core`` may be None (preview and shapes only)."""
    warn = warn or (lambda message: None)
    chain = BAKE_LEVELS[level]
    geometry = snapshot.get('geometry') or {}
    snapshot_id = clean_id(snapshot.get('_id'))
    color = snapshot.get('color') or list(DEFAULT_COLOR)
    resolutions = snapshot.get('mesh_ply_resolutions') or {}
    items = []
    for index, entry in enumerate(geometry.get('meshes') or []):
        mesh = None
        if auth_core is not None and snapshot_id and chain:
            available = resolutions.get(str(index)) or []
            for resolution in chain:
                if resolution not in available:
                    continue
                try:
                    found = auth_core.cached_get_snapshot_mesh(
                        snapshot_id, index, resolution)[0]
                except Exception as error:
                    warn('mesh %d (%s): %s' % (index, resolution, error))
                    found = None
                if found is not None:
                    mesh = found
                    break
        if mesh is None:
            mesh = inline_mesh_to_rhino(entry, color)
        if mesh is None:
            warn('mesh %d is empty or invalid' % index)
            continue
        items.append((mesh, 'mesh', index))
    for index, entry in enumerate(geometry.get('point_clouds') or []):
        cloud = None
        if auth_core is not None and snapshot_id and level != 'preview':
            try:
                cloud = auth_core.cached_get_snapshot_point_cloud(
                    snapshot_id, index)
            except Exception as error:
                warn('point cloud %d: %s' % (index, error))
        if cloud is None:
            cloud = inline_cloud_to_rhino(entry)
        if cloud is None:
            warn('point cloud %d is empty or invalid' % index)
            continue
        items.append((cloud, 'point_cloud', index))
    if authored_only(snapshot):
        for index, proxy in drawable_proxies(snapshot):
            if (proxy.get('fit') or {}).get('method') != 'authored':
                continue
            shape = proxy_to_rhino(proxy)
            if shape is not None:
                items.append((shape, 'proxy', index))
    return items


def marker_points(snapshot, xform=None):
    """The capture markers of a snapshot as Rhino points (moved by
    ``xform``), ``[(label, role, point)]``."""
    out = []
    for label, role, point in capture_markers(snapshot):
        pt = Rhino.Geometry.Point3d(*point)
        if xform is not None:
            pt.Transform(xform)
        out.append((label, role, pt))
    return out


# BAKE ------------------------------------------------------------------------
def layer_index(doc, identity_id, color):
    """The index of the layer ``CSC_COMPONENTS::<identity id>``, made when
    it is not there."""
    root = doc.Layers.FindByFullPath(LAYER_ROOT, -1)
    if root < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = LAYER_ROOT
        root = doc.Layers.Add(layer)
    path = '%s::%s' % (LAYER_ROOT, identity_id)
    found = doc.Layers.FindByFullPath(path, -1)
    if found >= 0:
        return found
    layer = Rhino.DocObjects.Layer()
    layer.Name = identity_id
    layer.ParentLayerId = doc.Layers[root].Id
    try:
        r, g, b = [int(c) for c in color][:3]
        layer.Color = System.Drawing.Color.FromArgb(255, r, g, b)
    except (TypeError, ValueError):
        pass
    return doc.Layers.Add(layer)


def _attributes(doc, layer, values):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer
    for key, value in values.items():
        attributes.SetUserString(key, str(value))
    return attributes


def _group_name(doc, identity_id):
    taken = set()
    for group in doc.Groups:
        try:
            taken.add(group.Name)
        except Exception:
            continue
    number = 1
    while '%s_%d' % (identity_id, number) in taken:
        number += 1
    return '%s_%d' % (identity_id, number)


def _tag_entity(doc, text, plane):
    scale = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Millimeters,
                                      doc.ModelUnitSystem)
    try:
        entity = Rhino.Geometry.TextEntity.Create(
            text, plane, doc.DimStyles.Current, False, 0.0, 0.0)
    except Exception:
        entity = None
    if entity is None:
        entity = Rhino.Geometry.TextEntity()
        entity.Text = text
        entity.Plane = plane
    entity.TextHeight = TAG_HEIGHT_MM * scale
    entity.Justification = Rhino.Geometry.TextJustification.MiddleCenter
    return entity


def bake_piece(doc, passport, items, with_passport=True, warn=None):
    """Adds one piece to ``doc``: the geometry ``items`` (stored coordinates,
    see ``piece_items``) moved by the placement the passport resolves to, the
    tag, one group. Returns ``{'ids', 'tag', 'plane', 'group'}``. Raises
    ConventionError for a passport that cannot carry the convention (no ids,
    no frame) before anything is added."""
    warn = warn or (lambda message: None)
    values = tag_values(passport, with_passport=with_passport)
    placed = resolve_placement(passport)
    xform = placement_transform(placed)
    identity, snapshot = parts(passport)
    identity_id = values[KEY_IDENTITY]
    layer = layer_index(doc, identity_id, snapshot.get('color'))
    shared = part_values(passport)

    ids = []
    for geometry, kind, index in items:
        shape = geometry.Duplicate()
        shape.Transform(xform)
        extra = dict(shared)
        extra[KEY_PARTS[kind]] = index
        guid = doc.Objects.Add(shape, _attributes(doc, layer, extra))
        if guid == System.Guid.Empty:
            warn('%s %d could not be added to the document' % (kind, index))
            continue
        ids.append(guid)
    if not ids:
        raise ConventionError('no geometry was baked for %s' % identity_id)

    plane = plane_from_frame(parse_placement(values[KEY_PLACEMENT]))
    entity = _tag_entity(doc, identity_id, plane)
    tag = doc.Objects.Add(entity, _attributes(doc, layer, values))
    if tag == System.Guid.Empty:
        raise ConventionError('the tag of %s could not be added' % identity_id)
    group = _group_name(doc, identity_id)
    members = System.Collections.Generic.List[System.Guid]()
    for guid in list(ids) + [tag]:
        members.Add(guid)
    doc.Groups.Add(group, members)
    return {'ids': ids, 'tag': tag, 'plane': plane, 'group': group}


# READ-BACK -------------------------------------------------------------------
def _tag_text(members):
    """The text object that carries a piece: the one with the convention keys
    of the members, else the only text object; ``(object, problem)``."""
    texts = [o for o in members
             if isinstance(o.Geometry, Rhino.Geometry.TextEntity)]
    keyed = [o for o in texts
             if o.Attributes.GetUserString(KEY_IDENTITY) not in (None, '')]
    if len(keyed) == 1:
        return keyed[0], None
    if len(keyed) > 1:
        return None, 'the group has several tagged text objects'
    if len(texts) == 1:
        return texts[0], None
    if not texts:
        return None, 'the group has no text label'
    return None, 'the group has several text labels and none is tagged'


def tagged_objects(doc):
    """The pieces of the document, found by their user text, as
    ``[{'object', 'tags', 'plane'}]``: ``object`` is the text object that
    carries the piece (the tag of a built-in bake, the label of a D2P
    component), ``plane`` its Rhino plane now (None when there is none) and
    ``tags`` the ``read_tags`` of the piece with its problems.

    A piece is a group with the convention keys on its objects (a built-in
    bake puts them all on its tag; a D2P component keeps its label clean, so
    PassportToD2P puts them on its members) and one text label, or a single
    tagged text object outside any group. The keys of the members are
    merged, the text object first; objects with different identities in one
    group are no piece."""
    found = {}
    for obj in doc.Objects:
        if obj is None or obj.Attributes.UserStringCount == 0:
            continue
        if obj.Attributes.GetUserString(KEY_IDENTITY) in (None, ''):
            continue
        groups = obj.Attributes.GetGroupList()
        key = (('group', groups[0]) if groups is not None and len(groups)
               else ('object', obj.Id))
        found.setdefault(key, []).append(obj)

    entries = []
    for (kind, ident), tagged in found.items():
        if kind == 'group':
            members = list(doc.Groups.GroupMembers(ident))
        else:
            members = list(tagged)
        label, problem = _tag_text(members)
        ordered = ([label] if label is not None and label in tagged else []
                   ) + [o for o in tagged if o is not label]
        identities = {clean_id(o.Attributes.GetUserString(KEY_IDENTITY))
                      or o.Attributes.GetUserString(KEY_IDENTITY)
                      for o in tagged}

        def get(name, objects=ordered):
            for o in objects:
                value = o.Attributes.GetUserString(name)
                if value not in (None, ''):
                    return value
            return None

        tags = read_tags(get)
        if len(identities) > 1:
            tags['identity_id'] = None
            tags['problems'].append('the group holds objects of different '
                                    'identities')
        if label is None:
            if kind == 'object':
                continue          # a tagged object that is not a text
            tags['problems'].append(problem)
        entries.append({
            'object': label if label is not None else tagged[0],
            'tags': tags,
            'plane': label.Geometry.Plane if label is not None else None})
    return entries


def read_document(doc, fetch=None, plane_of=None):
    """Every piece of the document read back, one per tag:
    ``[{'object', 'identity_id', 'snapshot_id', 'passport', 'problems'}]``.
    ``passport`` has ``csc_placement`` set from the tag plane (``plane_of``
    maps a ``tagged_objects`` entry to another Rhino plane, e.g. a D2P
    component's); it is None when the piece cannot be rebuilt (see
    ``problems``). Reads only: ``fetch`` is a read of the passport."""
    pieces = []
    for entry in tagged_objects(doc):
        plane = (plane_of(entry)
                 if plane_of and entry['plane'] is not None else None)
        plane = entry['plane'] if plane is None else plane
        if plane is None:
            passport, problems = None, list(entry['tags']['problems'])
        else:
            passport, problems = passport_for_tags(
                entry['tags'], frame_from_plane(plane), fetch)
        pieces.append({
            'object': entry['object'],
            'identity_id': entry['tags']['identity_id'],
            'snapshot_id': entry['tags']['snapshot_id'],
            'passport': passport,
            'problems': problems})
    return pieces


def passport_fetcher(auth_core):
    """``fetch(identity_id, snapshot_id)`` for ``passport_for_tags``: the
    Session's cached passport read of that snapshot (GET only); None without
    a signed-in Session. The ids are UUIDs (``read_tags`` checked them)."""
    if auth_core is None:
        return None

    def fetch(identity_id, snapshot_id):
        response = auth_core.cached_get_passport(
            identity_id, snapshots=[snapshot_id])
        if response.status_code != 200:
            raise RuntimeError('the server answered %s'
                               % response.status_code)
        return auth_core.normalize_passport_output(response.json())
    return fetch
