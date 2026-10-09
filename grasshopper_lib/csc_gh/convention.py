# The user-text convention of the Rhino document (decisions 8.95 4, 8.98).
# Pure: no Rhino import; uses build (is_uuid) and read (frames,
# passport readers).
#
# One piece in the document is a group with a text label (a Rhino text
# object) and objects carrying these user-text keys (a built-in bake puts all
# of them on its tag; D2P commits a component's label with fresh attributes,
# so PassportToD2P puts them on the members of the component):
#
#   csc_identity_id   the identity (a UUID)
#   csc_snapshot_id   the snapshot (a UUID)
#   csc_placement     JSON {o, x, y, z}: the plane of the CANONICAL piece in
#                     the document (the piece's box centre and axes once the
#                     frame is applied); WorldXY = the piece stands at the
#                     origin in its frame
#   csc_component     optional: the passport JSON (identity, snapshots[])
#
# The passport key of the same name (read.PLACEMENT_KEY) is a different
# plane: the frame the STORED geometry is placed in (TransformComponent,
# ApplyFrame). The two are linked by the snapshot's frame F (stored ->
# canonical):  T = placement_matrix(Q) maps stored coordinates to the
# document, M = T F^-1 maps the canonical piece to the document, and the tag
# plane is P = M(WorldXY); so  P = Q . frame  and  Q = P . F  (piece_plane,
# placement_from_piece_plane). Moving the tag moves P and so Q.
#
# Everything read from a document is untrusted: ids must be UUIDs (they end up
# in URLs), JSON has a size cap, a placement must be a finite right-handed
# orthonormal plane, and a passport must name the tag's own identity and
# snapshot. Nothing here talks to a server; a caller that fetches a passport
# passes the fetch in.
#
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import json  # NOQA
import math  # NOQA
import re  # NOQA

import numpy as np  # NOQA

# the other modules of the package
from .build import (is_uuid)  # NOQA
from .read import (canonical_matrix, canonical_placement, frame_ok, load_passport, parts, placement_matrix, placement_of, with_placement)  # NOQA

KEY_IDENTITY = 'csc_identity_id'
KEY_SNAPSHOT = 'csc_snapshot_id'
KEY_PLACEMENT = 'csc_placement'
KEY_COMPONENT = 'csc_component'
# which primitive of the snapshot an object of a built-in bake is
KEY_PARTS = {'mesh': 'csc_mesh_index', 'point_cloud': 'csc_point_cloud_index',
             'proxy': 'csc_proxy_index'}

# limits of what is parsed from a document
MAX_PLACEMENT_CHARS = 4096
MAX_COMPONENT_CHARS = 64 * 1024 * 1024
MAX_COORDINATE = 1.0e9
AXIS_TOLERANCE = 1.0e-3

# IFC class (original_function) -> D2P component type id (two letters); the
# ids of the 0.5 type list (BM, CL, SB, PP, RB, OT) keep their meaning
D2P_TYPE_IDS = {
    'IfcBeam': 'BM',
    'IfcColumn': 'CL',
    'IfcSlab': 'SB',
    'IfcPlate': 'PL',
    'IfcWall': 'WL',
    'IfcMember': 'MB',
    'IfcPipeSegment': 'PP',
    'IfcFooting': 'FT',
    'IfcDiscreteAccessory': 'AC',
    'IfcBuildingElementPart': 'EP',
    'IfcWindow': 'WN',
    'IfcDoor': 'DR',
    'IfcStair': 'ST',
    'IfcRailing': 'RL',
    'IfcDuctSegment': 'DC',
    'IfcBuildingElementProxy': 'OT',
    'CscDebris': 'RB',
}
D2P_FALLBACK_ID = 'OT'


class ConventionError(ValueError):
    """A piece cannot be written to or read from the document."""


# D2P TYPES -------------------------------------------------------------------
def d2p_type_id(original_function):
    """The D2P type id of an IFC class; ``OT`` (other) for none / unknown."""
    return D2P_TYPE_IDS.get(str(original_function or '').strip(),
                            D2P_FALLBACK_ID)


def d2p_type_name(original_function):
    """A readable type name: ``IfcPipeSegment`` -> ``Pipe Segment``,
    ``CscDebris`` -> ``Debris``, none -> ``Other``."""
    text = str(original_function or '').strip()
    for prefix in ('Ifc', 'Csc'):
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):]
            break
    words = re.findall(r'[A-Z][a-z0-9]*|[a-z0-9]+', text)
    return ' '.join(words) if words else 'Other'


# IDS -------------------------------------------------------------------------
def clean_id(value):
    """A UUID (version 4, as the server makes them) as canonical lower-case
    text, or None."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if is_uuid(text) else None


# PLACEMENT PLANES ------------------------------------------------------------
def _vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ConventionError('a plane vector has three numbers')
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConventionError('a plane vector holds numbers')
        item = float(item)
        if not math.isfinite(item) or abs(item) > MAX_COORDINATE:
            raise ConventionError('a plane coordinate is out of range')
        out.append(item)
    return np.asarray(out, dtype=np.float64)


def check_plane(value):
    """A plane ``{o, x, y, z}`` of finite numbers whose axes are unit length,
    perpendicular and right-handed (within 1e-3), as a clean dict of floats;
    raises ConventionError."""
    if not isinstance(value, dict):
        raise ConventionError('a plane is {o, x, y, z}')
    o, x, y, z = (_vector(value.get(k)) for k in ('o', 'x', 'y', 'z'))
    for axis in (x, y, z):
        if abs(np.linalg.norm(axis) - 1.0) > AXIS_TOLERANCE:
            raise ConventionError('the plane axes are not unit vectors')
    if (abs(x @ y) > AXIS_TOLERANCE or abs(x @ z) > AXIS_TOLERANCE
            or abs(y @ z) > AXIS_TOLERANCE):
        raise ConventionError('the plane axes are not perpendicular')
    if float(np.cross(x, y) @ z) < 1.0 - AXIS_TOLERANCE:
        raise ConventionError('the plane is not right-handed')
    return {'o': [float(v) for v in o], 'x': [float(v) for v in x],
            'y': [float(v) for v in y], 'z': [float(v) for v in z]}


def parse_placement(text):
    """The plane of a ``csc_placement`` user text (JSON, at most
    MAX_PLACEMENT_CHARS); raises ConventionError."""
    if isinstance(text, (dict, list)):
        return check_plane(text)
    if not isinstance(text, str) or not text.strip():
        raise ConventionError('the placement is empty')
    if len(text) > MAX_PLACEMENT_CHARS:
        raise ConventionError('the placement text is too long')
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        raise ConventionError('the placement is not JSON')
    return check_plane(value)


def placement_text(plane):
    """The ``csc_placement`` user text of a plane."""
    plane = check_plane(plane)
    return json.dumps({k: [round(v, 9) for v in plane[k]]
                       for k in ('o', 'x', 'y', 'z')},
                      separators=(',', ':'))


def _plane_of_matrix(matrix):
    return {'o': [float(v) for v in matrix[:3, 3]],
            'x': [float(v) for v in matrix[:3, 0]],
            'y': [float(v) for v in matrix[:3, 1]],
            'z': [float(v) for v in matrix[:3, 2]]}


def piece_plane(placement, frame):
    """The tag plane P of a piece drawn with the passport placement ``Q``:
    P = Q . frame (the canonical piece's plane in the document)."""
    return _plane_of_matrix(placement_matrix(placement)
                            @ placement_matrix(frame))


def placement_from_piece_plane(plane, frame):
    """The passport placement ``Q`` of a piece whose tag plane is ``P``:
    Q = P . F (F = canonical_matrix of the frame)."""
    return _plane_of_matrix(placement_matrix(plane)
                            @ canonical_matrix(frame))


def frame_of(snapshot):
    """The snapshot's frame ``{o, x, y, z}``, or None."""
    frame = (snapshot or {}).get('frame')
    return frame if frame_ok(frame) else None


def resolve_placement(passport):
    """The placement ``Q`` a piece is drawn with when it is baked: its own
    ``csc_placement`` when it has one, else the one that puts it in its
    frame (canonical, centred at the origin). None without a frame."""
    placed = placement_of(passport)
    if placed:
        return placed
    _, snapshot = parts(passport)
    frame = frame_of(snapshot)
    return canonical_placement(frame) if frame else None


# WRITING ---------------------------------------------------------------------
def part_values(passport):
    """User text of every baked object of a piece: its two ids."""
    identity, snapshot = parts(passport)
    identity_id = clean_id((identity or {}).get('_id'))
    snapshot_id = clean_id((snapshot or {}).get('_id'))
    if not identity_id or not snapshot_id:
        raise ConventionError('the passport has no identity / snapshot id')
    return {KEY_IDENTITY: identity_id, KEY_SNAPSHOT: snapshot_id}


def tag_values(passport, placement=None, with_passport=False):
    """User text of the tag of a piece: the ids, the plane of the canonical
    piece, and optionally the passport. ``placement`` is the passport
    placement the geometry was drawn with (default: ``resolve_placement``).
    Raises ConventionError for a passport without ids or without a frame (the
    plane cannot be derived and a read-back could not undo it)."""
    values = part_values(passport)
    _, snapshot = parts(passport)
    frame = frame_of(snapshot)
    if frame is None:
        raise ConventionError(
            'the snapshot has no frame yet (geometry still being processed?)')
    placed = placement if placement is not None \
        else resolve_placement(passport)
    values[KEY_PLACEMENT] = placement_text(piece_plane(placed, frame))
    if with_passport:
        values[KEY_COMPONENT] = json.dumps(load_passport(passport))
    return values


# READING ---------------------------------------------------------------------
def read_tags(get):
    """The convention values of one object. ``get(key)`` returns the user
    text of the object or None. Returns None when the object is not a piece
    (no ``csc_identity_id``), else a dict ``identity_id``, ``snapshot_id``,
    ``placement`` (plane or None), ``passport`` (dict or None), ``problems``
    (a list of sentences; a value that fails stays None)."""
    raw_identity = get(KEY_IDENTITY)
    if raw_identity in (None, ''):
        return None
    out = {'identity_id': None, 'snapshot_id': None, 'placement': None,
           'passport': None, 'problems': []}
    problems = out['problems']
    out['identity_id'] = clean_id(raw_identity)
    if out['identity_id'] is None:
        problems.append('csc_identity_id is not a UUID')
    raw_snapshot = get(KEY_SNAPSHOT)
    out['snapshot_id'] = clean_id(raw_snapshot)
    if out['snapshot_id'] is None:
        problems.append('csc_snapshot_id is missing or not a UUID')
    raw_placement = get(KEY_PLACEMENT)
    if raw_placement not in (None, ''):
        try:
            out['placement'] = parse_placement(raw_placement)
        except ConventionError as error:
            problems.append('csc_placement: %s' % error)
    raw_component = get(KEY_COMPONENT)
    if raw_component not in (None, ''):
        if not isinstance(raw_component, str):
            problems.append('csc_component is not text')
        elif len(raw_component) > MAX_COMPONENT_CHARS:
            problems.append('csc_component is too long')
        else:
            passport = load_passport(raw_component)
            if passport is None:
                problems.append('csc_component is not a passport')
            else:
                out['passport'] = passport
    return out


def select_snapshot(passport, snapshot_id):
    """The passport with the snapshot ``snapshot_id`` first, or None when it
    is not in it (a tag cannot name a snapshot its passport does not hold)."""
    data = load_passport(passport)
    if data is None:
        return None
    wanted = clean_id(snapshot_id)
    snapshots = data['snapshots']
    for position, snap in enumerate(snapshots):
        if isinstance(snap, dict) and clean_id(snap.get('_id')) == wanted:
            out = dict(data)
            out['snapshots'] = [snap] + [
                s for k, s in enumerate(snapshots) if k != position]
            return out
    return None


def passport_for_tags(tags, plane, fetch=None):
    """The passport of a piece read back from the document, with
    ``csc_placement`` set from the tag plane ``plane`` (the plane of the
    tag object now). The passport is the tag's own ``csc_component`` or, when
    that is missing or does not match the tag, ``fetch(identity_id,
    snapshot_id)`` (a passport or None; it is a read, never a write).
    Returns ``(passport, problems)``; the passport is None when the piece
    cannot be rebuilt."""
    problems = list(tags.get('problems') or [])
    identity_id, snapshot_id = tags.get('identity_id'), tags.get('snapshot_id')
    if not identity_id or not snapshot_id:
        return None, problems
    try:
        plane = check_plane(plane)
    except ConventionError as error:
        problems.append('the tag plane: %s' % error)
        return None, problems

    def matching(candidate):
        data = select_snapshot(candidate, snapshot_id)
        if data is None:
            return None
        if clean_id((data.get('identity') or {}).get('_id')) != identity_id:
            return None
        return data

    passport = None
    if tags.get('passport') is not None:
        passport = matching(tags['passport'])
        if passport is None:
            problems.append('csc_component does not hold the tagged identity '
                            'and snapshot: ignored')
    if passport is None and fetch is not None:
        try:
            passport = matching(fetch(identity_id, snapshot_id))
        except Exception as error:
            problems.append('fetching the passport failed: %s' % error)
            passport = None
        if passport is None and not any('fetching' in p for p in problems):
            problems.append('the server has no passport for the tagged '
                            'identity and snapshot')
    if passport is None:
        problems.append('no passport for %s (no csc_component and no way to '
                        'fetch one)' % identity_id)
        return None, problems
    frame = frame_of(passport['snapshots'][0])
    if frame is None:
        problems.append('the snapshot has no frame: the placement cannot be '
                        'rebuilt')
        return None, problems
    return with_placement(
        passport, placement_from_piece_plane(plane, frame)), problems
