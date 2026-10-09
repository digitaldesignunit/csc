# Payload builders of the Grasshopper bridge (decisions 7.6, 7.7, 7.8, 8.95).
# Pure: no Rhino import, numpy only where arrays are handled.
#
# Each builder returns a plain dict that IS a fragment of the API payload
# (``IdentityCreateBody`` / ``SnapshotDraftBody`` / an evidence record); the
# script components serialise it with ``json.dumps``. ``VOCAB`` repeats the
# backend's closed lists so the builders can refuse a wrong word before the
# request; ``tests/grasshopper/test_build.py`` compares it with the backend.
#
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import hashlib  # NOQA
import json  # NOQA
import math  # NOQA
import re  # NOQA
from datetime import datetime, timedelta, timezone  # NOQA

import numpy as np  # NOQA

VOCAB = {
    'origin_kind': ('deinstallation', 'demolition', 'offcut', 'surplus',
                    'unknown'),
    'actor_kind': ('user', 'person', 'organization'),
    'actor_role': ('operator', 'supervisor', 'laboratory', 'client',
                   'witness'),
    'capture_method': ('photogrammetry', 'lidar', 'structured_light',
                       'manual'),
    'marker_role': ('rig', 'component'),
    'original_function': (
        'IfcBeam', 'IfcColumn', 'IfcSlab', 'IfcPlate', 'IfcWall',
        'IfcMember', 'IfcPipeSegment', 'IfcFooting', 'IfcDiscreteAccessory',
        'IfcBuildingElementPart', 'IfcWindow', 'IfcDoor', 'IfcStair',
        'IfcRailing', 'IfcDuctSegment', 'IfcBuildingElementProxy',
        'CscDebris'),
    'construction_method': ('monolithic', 'prefabricated', 'mixed',
                            'unknown'),
    'precision': ('exact', 'day', 'month', 'year', 'unknown'),
    'reinforcement_basis': ('drawing', 'scan', 'exposed'),
    'layout_instrument': ('covermeter', 'radar', 'other'),
    'shape_class': ('linear', 'planar', 'block', 'irregular', 'composite'),
}

# the keys each body takes (the server refuses any other: extra='forbid')
IDENTITY_KEYS = (
    'id', 'dataset', 'parent_identities', 'original_function', 'material',
    'material_class', 'trade_name', 'manufacturer', 'connection_features',
    'material_separability', 'manufactured_at', 'manufactured_precision',
    'origin', 'is_public', 'attributes', 'snapshot')
IDENTITY_METADATA_KEYS = (
    'original_function', 'material', 'material_class', 'trade_name',
    'manufacturer', 'manufactured_at', 'manufactured_precision', 'origin',
    'is_public', 'attributes')
SNAPSHOT_KEYS = (
    'name', 'effective_from', 'effective_from_precision', 'geometry',
    'capture', 'shape_class', 'complexity', 'fragment', 'quantity', 'color',
    'location', 'notes', 'photo_credit')
SNAPSHOT_METADATA_KEYS = (
    'name', 'effective_from', 'effective_from_precision', 'shape_class',
    'complexity', 'fragment', 'quantity', 'color', 'location', 'notes')

ORIGIN_KINDS_WITH_WORK = ('deinstallation', 'demolition')

# mesh levels (8.23, 8.95 1): Preview = inline, Reduced and Original = files
MESH_PRIMITIVE_THRESHOLD = 8000
MESH_REDUCED_THRESHOLD = 15000
MESH_REDUCED_TARGET = 10000
MESH_PRIMITIVE_TARGET = 500
POINT_CLOUD_INLINE_MAX = 5000
POINT_CLOUD_STAGING_THRESHOLD = 5000

_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}'
                   r'-[0-9a-f]{12}$')
_DATE = re.compile(
    r'^(\d{4})(?:-(\d{2})(?:-(\d{2})'
    r'(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?'
    r'(Z|[+-]\d{2}:?\d{2})?)?)?)?$')


class BuildError(ValueError):
    """An input the builders refuse, with a sentence for the user."""


# SMALL HELPERS ---------------------------------------------------------------
def clean(mapping):
    """The dict without None values and empty strings / lists / dicts."""
    out = {}
    for key, value in mapping.items():
        if value is None or value == '' or value == [] or value == {}:
            continue
        out[key] = value
    return out


def text(value):
    """A stripped string, or None for an empty / missing input."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def number(value, name='value'):
    if value is None or value == '':
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise BuildError('%s must be a number, got %r' % (name, value))
    if not math.isfinite(out):
        raise BuildError('%s must be a finite number' % name)
    return out


def choice(value, name, allowed, default=None):
    value = text(value)
    if value is None:
        return default
    if value not in allowed:
        raise BuildError('%s must be one of %s, got %r'
                         % (name, ', '.join(allowed), value))
    return value


def is_uuid(value):
    return bool(value) and bool(_UUID.match(str(value).strip().lower()))


def parse_date(value, name='date'):
    """``(ISO UTC string, precision)`` of a date text; (None, None) if empty.

    ``2024`` -> year, ``2024-05`` -> month, ``2024-05-03`` -> day, a time
    makes it exact (an offset is converted to UTC).
    """
    value = text(value)
    if value is None:
        return None, None
    if value.lower() == 'unknown':
        return None, 'unknown'
    match = _DATE.match(value)
    if not match:
        raise BuildError('%s: write 2024, 2024-05, 2024-05-03 or '
                         '2024-05-03T14:30:00Z, got %r' % (name, value))
    year, month, day, hour, minute, second, zone = match.groups()
    try:
        moment = datetime(int(year), int(month or 1), int(day or 1),
                          int(hour or 0), int(minute or 0), int(second or 0))
    except ValueError:
        raise BuildError('%s: %r is not a date' % (name, value))
    if zone and zone != 'Z':
        sign = 1 if zone[0] == '+' else -1
        digits = zone[1:].replace(':', '')
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        moment = (moment - sign * offset)
    if hour is not None:
        precision = 'exact'
    elif day is not None:
        precision = 'day'
    elif month is not None:
        precision = 'month'
    else:
        precision = 'year'
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ'), precision


def location(lat, lon, name='location'):
    """``{lat, lon}`` or None when both are empty."""
    lat, lon = number(lat, name + ' latitude'), number(lon, name + ' longitude')
    if lat is None and lon is None:
        return None
    if lat is None or lon is None:
        raise BuildError('%s needs latitude and longitude' % name)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise BuildError('%s is out of range (lat -90..90, lon -180..180)'
                         % name)
    return {'lat': lat, 'lon': lon}


def rgb(value, name='color'):
    """``[r, g, b]`` ints 0..255 or None."""
    if value is None:
        return None
    items = list(value)
    if len(items) != 3:
        raise BuildError('%s needs three values (red, green, blue)' % name)
    out = [int(round(float(v))) for v in items]
    if any(v < 0 or v > 255 for v in out):
        raise BuildError('%s values are 0..255' % name)
    return out


def loads_fragment(value, name):
    """A builder output (JSON text or dict) as a dict; None when empty."""
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        return value
    try:
        out = json.loads(value)
    except (TypeError, ValueError):
        raise BuildError('%s is not JSON text from a builder component' % name)
    if not isinstance(out, dict):
        raise BuildError('%s must be a JSON object' % name)
    return out


# BUILDERS: ACTOR, ORIGIN, METADATA, CAPTURE ----------------------------------
def actor(kind=None, user_id=None, name=None, organization=None,
          organization_ror=None, orcid=None, email=None, role=None):
    """An actor block (spec 3.3.1)."""
    user_id, name = text(user_id), text(name)
    organization = text(organization)
    if kind is None or text(kind) is None:
        kind = ('user' if user_id else
                'organization' if organization and not name else 'person')
    kind = choice(kind, 'Kind', VOCAB['actor_kind'])
    if kind == 'user' and not user_id:
        raise BuildError('an actor of kind user needs a UserID')
    if kind != 'user' and not (name or organization):
        raise BuildError('an actor needs a name or an organization')
    return clean({
        'kind': kind, 'user_id': user_id, 'name': name,
        'organization': organization,
        'organization_ror': text(organization_ror), 'orcid': text(orcid),
        'email': text(email),
        'role': choice(role, 'Role', VOCAB['actor_role']),
    })


def origin(kind, at=None, at_precision=None, place_name=None, address=None,
           lat=None, lon=None, work_name=None, work_year=None,
           work_use=None, work_method=None, method=None, performed_by=None,
           notes=None, position_in_work=None, planned=False):
    """An origin block (spec 3.1.1): how the piece entered circulation.
    ``planned``: the piece is still in place, not yet deinstalled (8.104);
    only for a deinstallation or a demolition, and ``at`` is then the
    planned date or empty."""
    kind = choice(kind, 'Kind', VOCAB['origin_kind'])
    if kind is None:
        raise BuildError('an origin needs a Kind (%s)'
                         % ', '.join(VOCAB['origin_kind']))
    when, precision = parse_date(at, 'At')
    precision = choice(at_precision, 'AtPrecision',
                       VOCAB['precision'], precision) or 'unknown'
    place = clean({
        'name': text(place_name), 'address': text(address),
        'location': location(lat, lon, 'Place location'),
    })
    work = clean({
        'name': text(work_name),
        'year_built': (int(number(work_year, 'WorkYear'))
                       if text(work_year) else None),
        'use': text(work_use),
        'construction_method': choice(
            work_method, 'WorkMethod', VOCAB['construction_method']),
    })
    if work and 'name' not in work:
        raise BuildError('the construction work needs a name')
    if (work or text(position_in_work)) \
            and kind not in ORIGIN_KINDS_WITH_WORK:
        raise BuildError('construction work only for an origin of kind '
                         'deinstallation or demolition')
    if planned and kind not in ORIGIN_KINDS_WITH_WORK:
        raise BuildError('only a deinstallation or a demolition can be '
                         'planned (Planned)')
    people = []
    for item in performed_by or []:
        fragment = loads_fragment(item, 'PerformedBy')
        if fragment:
            people.append(fragment)
    return clean({
        'kind': kind, 'planned': True if planned else None,
        'at': when, 'at_precision': precision,
        'place': place, 'construction_work': work,
        'position_in_work': text(position_in_work), 'method': text(method),
        'performed_by': people, 'notes': text(notes),
    })


def identity_metadata(original_function=None, material=None, trade_name=None,
                      manufacturer=None, manufactured_at=None,
                      manufactured_precision=None, origin_block=None,
                      is_public=None, attributes=None, material_class=None):
    """The identity fields of ``IdentityCreateBody`` (without id, dataset,
    parents and the snapshot)."""
    when, precision = parse_date(manufactured_at, 'ManufacturedAt')
    precision = choice(manufactured_precision, 'ManufacturedPrecision',
                       VOCAB['precision'], precision)
    origin_dict = loads_fragment(origin_block, 'Origin')
    attrs = loads_fragment(attributes, 'Attributes')
    return clean({
        'original_function': choice(original_function, 'OriginalFunction',
                                    VOCAB['original_function']),
        'material': text(material),
        'material_class': text(material_class),
        'trade_name': text(trade_name),
        'manufacturer': text(manufacturer),
        'manufactured_at': when,
        'manufactured_precision': precision,
        'origin': origin_dict,
        'is_public': True if is_public else None,
        'attributes': attrs,
    })


def snapshot_metadata(name=None, fragment=None, quantity=None, color=None,
                      lat=None, lon=None, notes=None, effective_from=None,
                      effective_from_precision=None, shape_class=None,
                      complexity=None):
    """The snapshot fields of ``SnapshotDraftBody`` without geometry and
    capture. ``shape_class`` / ``complexity`` are optional hand-set values
    (assigned); omit them to let the server derive them."""
    when, precision = parse_date(effective_from, 'EffectiveFrom')
    precision = choice(effective_from_precision, 'EffectiveFromPrecision',
                       VOCAB['precision'], precision)
    qty = None
    if quantity is not None and text(quantity) is not None:
        qty = int(round(number(quantity, 'Quantity')))
        if qty < 1:
            raise BuildError('Quantity is at least 1')
    grade = None
    if complexity is not None and text(complexity) is not None:
        grade = int(round(number(complexity, 'Complexity')))
        if grade < 0 or grade > 3:
            raise BuildError('Complexity is 0..3')
    notes = text(notes)
    return clean({
        'name': text(name),
        'effective_from': when,
        'effective_from_precision': precision if when else None,
        'shape_class': choice(shape_class, 'ShapeClass',
                              VOCAB['shape_class']),
        'complexity': grade,
        'fragment': True if fragment else None,
        'quantity': qty if qty and qty != 1 else None,
        'color': rgb(color),
        'location': location(lat, lon),
        'notes': notes[:5000] if notes else None,
    })


def capture(method=None, device=None, software=None, captured_at=None,
            notes=None, coordinate_system=None,
            coordinate_system_description=None, markers=None, fixtures=None):
    """A capture block (spec 3.2.3, decision 7.7).

    ``markers``: items ``(label, role, (x, y, z))``; ``fixtures``: items
    ``(label, file)``. Markers and fixtures are never component geometry.
    """
    when, _ = parse_date(captured_at, 'CapturedAt')
    system = None
    if text(coordinate_system):
        system = clean({'name': text(coordinate_system),
                        'description': text(coordinate_system_description)})
    marker_list = []
    for item in markers or []:
        label, role, point = item
        label = text(label)
        role = choice(role, 'marker role', VOCAB['marker_role'], 'component')
        if not label:
            raise BuildError('every marker needs a label')
        point = [float(v) for v in point]
        if len(point) != 3:
            raise BuildError('marker %s needs x, y and z' % label)
        marker_list.append({'label': label, 'role': role, 'point': point})
    fixture_list = []
    for item in fixtures or []:
        label, file_name = item
        if not text(label) or not text(file_name):
            raise BuildError('a fixture needs a label and a file name')
        fixture_list.append({'label': text(label), 'file': text(file_name)})
    return clean({
        'method': choice(method, 'Method', VOCAB['capture_method']),
        'device': text(device), 'software': text(software),
        'captured_at': when, 'notes': text(notes),
        'coordinate_system': system, 'markers': marker_list,
        'fixtures': fixture_list,
    })


# GEOMETRY --------------------------------------------------------------------
def mesh_levels(face_count):
    """What to keep of a mesh of ``face_count`` faces (8.23, 8.95 1).

    ``preview_target``: reduce the inline Preview to that many faces (None:
    the mesh itself is the preview); ``reduced_target``: write a Reduced
    file with that many faces (None: none); ``save_original``: write the
    Original file.
    """
    if face_count > MESH_REDUCED_THRESHOLD:
        return {'preview_target': MESH_PRIMITIVE_TARGET,
                'reduced_target': MESH_REDUCED_TARGET,
                'save_original': True}
    if face_count > MESH_PRIMITIVE_THRESHOLD:
        return {'preview_target': MESH_PRIMITIVE_TARGET,
                'reduced_target': None, 'save_original': True}
    return {'preview_target': None, 'reduced_target': None,
            'save_original': face_count > MESH_PRIMITIVE_TARGET}


def inline_mesh(vertices, faces, colors=None):
    """An inline Preview mesh: ``{vertices, faces[, colors]}`` (triangles)."""
    vertices = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(vertices) < 3 or len(faces) < 1:
        raise BuildError('a mesh needs vertices and faces')
    if faces.max() >= len(vertices) or faces.min() < 0:
        raise BuildError('a mesh face points outside its vertices')
    out = {'vertices': vertices.tolist(), 'faces': faces.tolist()}
    if colors is not None:
        colors = np.asarray(colors).reshape(-1, 3)
        if len(colors) == len(vertices):
            out['colors'] = [[int(c) for c in row] for row in colors]
    return out


def inline_point_cloud(points, colors=None, max_points=POINT_CLOUD_INLINE_MAX):
    """An inline Preview point cloud, evenly thinned to ``max_points``."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(points) == 0:
        raise BuildError('a point cloud is empty')
    count = len(points)
    if count > max_points:
        step = count / float(max_points)
        index = np.minimum((np.arange(max_points) * step).round().astype(
            np.int64), count - 1)
    else:
        index = np.arange(count)
    out = {'points': points[index].tolist()}
    if colors is not None:
        colors = np.asarray(colors).reshape(-1, 3)
        if len(colors) == count:
            out['colors'] = [[int(c) for c in row] for row in colors[index]]
    return out


def _unit(vector):
    vector = np.asarray(vector, dtype=np.float64)
    length = np.linalg.norm(vector)
    if length < 1e-12:
        raise BuildError('a direction of zero length')
    return vector / length


def _polygon(points):
    """The 3D polygon without a repeated closing vertex."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(points) > 1 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        raise BuildError('a profile needs at least three points')
    return points


def prism_proxy(profile, axis, height, holes=None):
    """An authored ``prism`` proxy from an extrusion (8.95 8).

    ``profile``: the outer profile as 3D points at the start of the
    extrusion; ``axis``: the extrusion direction; ``height``: its length;
    ``holes``: inner profiles (3D points). The proxy's own axes follow the
    spec (App. B): origin at the centroid, z along the extrusion, the
    profile in x / y, swept from -height/2 to +height/2.
    """
    height = float(height)
    if not height > 0:
        raise BuildError('an extrusion needs a height above zero')
    z = _unit(axis)
    outer = _polygon(profile)
    first_edge = outer[1] - outer[0]
    x = first_edge - z * float(np.dot(first_edge, z))
    if np.linalg.norm(x) < 1e-9:
        x = outer[2] - outer[0]
        x = x - z * float(np.dot(x, z))
    x = _unit(x)
    y = np.cross(z, x)
    # area centroid of the profile in its own plane
    base = outer[0]
    local = np.column_stack([(outer - base) @ x, (outer - base) @ y])
    cross = local[:, 0] * np.roll(local[:, 1], -1) \
        - np.roll(local[:, 0], -1) * local[:, 1]
    area = cross.sum() / 2.0
    if abs(area) < 1e-12:
        raise BuildError('the profile has no area')
    cx = ((local[:, 0] + np.roll(local[:, 0], -1)) * cross).sum() / (6 * area)
    cy = ((local[:, 1] + np.roll(local[:, 1], -1)) * cross).sum() / (6 * area)
    centroid = base + x * cx + y * cy
    origin_point = centroid + z * (height / 2.0)

    def to_local(points):
        rel = np.asarray(points) - centroid
        return [[float(a), float(b)] for a, b in zip(rel @ x, rel @ y)]

    params = {'profile': to_local(outer), 'height': height}
    inner = [to_local(_polygon(ring)) for ring in (holes or [])]
    if inner:
        params['holes'] = inner
    return {
        'primitive': 'prism', 'role': 'primary', 'params': params,
        'placement': {'o': [float(v) for v in origin_point],
                      'x': [float(v) for v in x],
                      'y': [float(v) for v in y],
                      'z': [float(v) for v in z]},
        'fit': {'method': 'authored'}, 'regions': [],
    }


def box_proxy(points, x_axis, z_axis):
    """An authored ``box`` proxy from the corner points of a box-shaped
    solid and two of its edge directions (8.95 8). The size is measured on
    the axes, the placement origin is the box centre."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(points) < 4:
        raise BuildError('a box needs its corner points')
    z = _unit(z_axis)
    x = np.asarray(x_axis, dtype=np.float64)
    x = _unit(x - z * float(np.dot(x, z)))
    y = np.cross(z, x)
    axes = np.vstack([x, y, z])
    local = points @ axes.T
    low, high = local.min(axis=0), local.max(axis=0)
    size = high - low
    if not np.all(size > 1e-9):
        raise BuildError('the box has a side of zero length')
    centre = ((low + high) / 2.0) @ axes
    return {
        'primitive': 'box', 'role': 'primary',
        'params': {'size': [float(v) for v in size]},
        'placement': {'o': [float(v) for v in centre],
                      'x': [float(v) for v in x], 'y': [float(v) for v in y],
                      'z': [float(v) for v in z]},
        'fit': {'method': 'authored'}, 'regions': [],
    }


def geometry_body(meshes=None, point_clouds=None, proxies=None):
    """The ``geometry`` block; refuses an empty one (I1)."""
    out = {'meshes': list(meshes or []),
           'point_clouds': list(point_clouds or []),
           'proxies': list(proxies or [])}
    if not (out['meshes'] or out['point_clouds'] or out['proxies']):
        raise BuildError('the geometry has no mesh, point cloud or '
                         'authored shape')
    primary = [p for p in out['proxies'] if p.get('role') == 'primary']
    if out['proxies'] and len(primary) != 1:
        # several authored shapes: the first is the primary one (I2)
        for index, proxy in enumerate(out['proxies']):
            proxy['role'] = 'primary' if index == 0 else 'part'
    return out


# BODIES ----------------------------------------------------------------------
def snapshot_body(metadata, geometry, capture_block=None):
    """A ``SnapshotDraftBody`` dict."""
    body = {}
    for key, value in (loads_fragment(metadata, 'SnapshotMetadata')
                       or {}).items():
        if key not in SNAPSHOT_METADATA_KEYS:
            raise BuildError('SnapshotMetadata: %r is not a snapshot field'
                             % key)
        body[key] = value
    body['geometry'] = geometry
    cap = loads_fragment(capture_block, 'Capture')
    if cap:
        body['capture'] = cap
    return body


def identity_body(identity_id, dataset, identity_meta, snapshot,
                  parents=None):
    """An ``IdentityCreateBody`` dict (a new component with its v0 draft).

    A cut gives ``parents`` and may omit the identity metadata: everything
    not stated is inherited (3.1.2). A new component states
    ``original_function`` and ``material``.
    """
    identity_id = text(identity_id)
    if identity_id and not is_uuid(identity_id):
        raise BuildError('IdentityID is not a valid UUID')
    dataset = text(dataset)
    if not dataset:
        raise BuildError('a component needs a Dataset')
    parents = [text(p) for p in (parents or []) if text(p)]
    for parent in parents:
        if not is_uuid(parent):
            raise BuildError('parent %r is not a valid UUID' % parent)
    body = {}
    meta = loads_fragment(identity_meta, 'IdentityMetadata') or {}
    for key, value in meta.items():
        if key not in IDENTITY_METADATA_KEYS:
            raise BuildError('IdentityMetadata: %r is not an identity field'
                             % key)
        body[key] = value
    if not parents:
        for required in ('original_function', 'material'):
            if required not in body:
                raise BuildError('a new component needs %s in its '
                                 'IdentityMetadata' % required)
    if identity_id:
        body['id'] = identity_id
    body['dataset'] = dataset
    if parents:
        body['parent_identities'] = parents
    body['snapshot'] = snapshot
    return body


def snapshot_envelope(identity_id, snapshot, supersedes=None):
    """What CreateComponentSnapshot hands to AddComponentSnapshot: the
    snapshot body plus where it goes (the body itself has no identity)."""
    identity_id = text(identity_id)
    if not is_uuid(identity_id):
        raise BuildError('IdentityID is not a valid UUID')
    supersedes = text(supersedes)
    if supersedes and not is_uuid(supersedes):
        raise BuildError('Supersedes is not a valid snapshot UUID')
    return clean({'identity_id': identity_id, 'supersedes': supersedes,
                  'snapshot': snapshot})


def problems_of_snapshot(body):
    """Shape problems of a ``SnapshotDraftBody`` the server would answer
    with 422; an empty list when none is found."""
    problems = []
    for key in body:
        if key not in SNAPSHOT_KEYS:
            problems.append('snapshot: %r is not a field of a snapshot' % key)
    geometry = body.get('geometry')
    if not isinstance(geometry, dict):
        problems.append('snapshot: geometry is missing')
    elif not (geometry.get('meshes') or geometry.get('point_clouds')
              or geometry.get('proxies')):
        problems.append('snapshot: the geometry is empty')
    return problems


def problems_of_identity(body):
    """Shape problems of an ``IdentityCreateBody``."""
    problems = []
    for key in body:
        if key not in IDENTITY_KEYS:
            problems.append('identity: %r is not a field of a new '
                            'component' % key)
    if not body.get('dataset'):
        problems.append('identity: dataset is missing')
    if not body.get('parent_identities'):
        for required in ('original_function', 'material'):
            if not body.get(required):
                problems.append('identity: %s is missing' % required)
    snapshot = body.get('snapshot')
    if not isinstance(snapshot, dict):
        problems.append('identity: snapshot is missing')
    else:
        problems.extend(problems_of_snapshot(snapshot))
    return problems


def problems_of_envelope(envelope):
    """Shape problems of what CreateComponentSnapshot hands to Add."""
    problems = []
    for key in envelope:
        if key not in ('identity_id', 'supersedes', 'snapshot'):
            problems.append('request: %r is not a field of a snapshot '
                            'request' % key)
    if not is_uuid(envelope.get('identity_id')):
        problems.append('request: identity_id is not a valid UUID')
    snapshot = envelope.get('snapshot')
    if not isinstance(snapshot, dict):
        problems.append('request: snapshot is missing')
    else:
        problems.extend(problems_of_snapshot(snapshot))
    return problems


# STAGING ---------------------------------------------------------------------
def staging_key(body_text):
    """Where the files of one create are staged: a digest of its JSON text,
    so Create and Add agree without the server's (not yet assigned) id."""
    data = json.dumps(json.loads(body_text), sort_keys=True,
                      separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()[:24]


def manifest(meshes=None, point_clouds=None):
    """The staging manifest: ``meshes``: ``{index: [levels]}`` with levels
    ``reduced`` / ``detailed`` (the file name of the Original level);
    ``point_clouds``: list of cloud indices staged as files."""
    out = {'coordinate_frame': 'stored'}
    if meshes:
        out['meshes'] = {str(k): list(v) for k, v in meshes.items()}
    if point_clouds:
        out['point_clouds'] = [int(i) for i in point_clouds]
    return out


# EVIDENCE (decision 7.8, spec A.4) -------------------------------------------
def reinforcement_layout_record(snapshot_id, bars, basis, observed_at=None,
                                document_title=None, document_date=None,
                                document_reference=None, instrument_kind=None,
                                instrument_manufacturer=None,
                                instrument_model=None, accuracy_note=None,
                                performed_by=None, notes=None):
    """One evidence record of method ``reinforcement_layout``.

    ``bars``: items ``{spec, diameter_mm, points[, diameter_known,
    cover_mm]}`` with the centreline in the stored coordinates of
    ``snapshot_id``. ``basis`` decides the tier: drawing, scan or exposed.
    """
    snapshot_id = text(snapshot_id)
    if not is_uuid(snapshot_id):
        raise BuildError('SnapshotID is not a valid UUID: the bars are '
                         'positioned in the coordinates of one snapshot')
    basis = choice(basis, 'Basis', VOCAB['reinforcement_basis'])
    if basis is None:
        raise BuildError('Basis is drawing, scan or exposed')
    out_bars = []
    for index, bar in enumerate(bars or []):
        points = [[float(v) for v in p] for p in bar['points']]
        if len(points) < 2 or any(len(p) != 3 for p in points):
            raise BuildError('bar %d needs at least two 3D points' % index)
        diameter = float(bar['diameter_mm'])
        if not diameter > 0:
            raise BuildError('bar %d needs a diameter above zero' % index)
        out_bars.append(clean({
            'spec': text(bar.get('spec')), 'diameter_mm': diameter,
            'diameter_known': (False if bar.get('diameter_known') is False
                               else None),
            'cover_mm': bar.get('cover_mm'), 'points': points}))
    if not out_bars:
        raise BuildError('a layout needs at least one bar')
    document = None
    if text(document_title):
        when, _ = parse_date(document_date, 'DocumentDate')
        document = clean({'title': text(document_title),
                          'date': text(document_date) if when else None,
                          'reference': text(document_reference)})
    instrument = None
    if text(instrument_kind):
        instrument = clean({
            'kind': choice(instrument_kind, 'InstrumentKind',
                           VOCAB['layout_instrument']),
            'manufacturer': text(instrument_manufacturer),
            'model': text(instrument_model)})
    when, precision = parse_date(observed_at, 'ObservedAt')
    people = [loads_fragment(p, 'PerformedBy') for p in performed_by or []]
    record = {
        'method': 'reinforcement_layout',
        'observed_at': when or datetime.now(timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%SZ'),
        'observed_at_precision': precision or 'exact',
        'performed_by': [p for p in people if p],
        'position': {'kind': 'none', 'snapshot_id': snapshot_id,
                     'description': 'reinforcement layout'},
        'payload': clean({'basis': basis, 'document': document,
                          'instrument': instrument,
                          'accuracy_note': text(accuracy_note),
                          'bars': out_bars}),
        'notes': text(notes),
    }
    return clean(record)


def evidence_bulk_body(records, identity_ids):
    """The body of ``POST /evidence/bulk``. One identity id applies to every
    record; as many ids as records pair up one to one. The records are
    drafts: they are submitted in the web (8.127)."""
    records = [loads_fragment(r, 'Evidence') for r in records or []]
    records = [r for r in records if r]
    ids = [text(i) for i in identity_ids or [] if text(i)]
    if not records:
        raise BuildError('no evidence record to add')
    if not ids:
        raise BuildError('IdentityID is missing')
    if len(ids) not in (1, len(records)):
        raise BuildError('give one IdentityID for all records or one per '
                         'record (%d records, %d ids)'
                         % (len(records), len(ids)))
    for identity_id in ids:
        if not is_uuid(identity_id):
            raise BuildError('%r is not a valid identity UUID' % identity_id)
    items = []
    for index, record in enumerate(records):
        item = dict(record)
        item['identity_id'] = ids[0] if len(ids) == 1 else ids[index]
        items.append(item)
    return {'records': items}
