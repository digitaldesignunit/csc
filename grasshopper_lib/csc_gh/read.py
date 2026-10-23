# Read-side helpers of the Grasshopper bridge (decisions 7.10, 7.11, 8.95).
# Pure: no Rhino import; numpy for matrices.
#
# Passport readers (identity / snapshot parts, the 0.6 fields), the filters
# of FetchFilteredComponents / FilterComponents (with the dimension and near
# search, 8.169 / 8.170) and the similar search of FetchSimilarComponents
# (8.174), the placement key of passport JSON, frame matrices, proxy
# validity and placement.
#
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import json  # NOQA
import math  # NOQA
import re  # NOQA

import numpy as np  # NOQA

# The client-side placement of a piece (8.95 5): never sent to the server.
PLACEMENT_KEY = 'csc_placement'

FINDING_QUANTITIES = ('spalling', 'cracking', 'corrosion')


# PASSPORT --------------------------------------------------------------------
def load_passport(value):
    """A passport (``{identity, snapshots[]}``) from JSON text or a dict;
    None when it is neither. A legacy ``{identity, snapshot}`` is accepted."""
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, dict) or not isinstance(
            value.get('identity'), dict):
        return None
    snapshots = value.get('snapshots')
    if isinstance(snapshots, list) and snapshots:
        out = dict(value)
        out['snapshots'] = snapshots
        return out
    legacy = value.get('snapshot')
    if isinstance(legacy, dict):
        out = {k: v for k, v in value.items() if k != 'snapshot'}
        out['snapshots'] = [legacy]
        return out
    return None


def parts(passport):
    """``(identity, snapshot)`` of the first snapshot, or ``(None, None)``."""
    data = load_passport(passport)
    if data is None:
        return None, None
    snapshot = data['snapshots'][0]
    return data['identity'], snapshot if isinstance(snapshot, dict) else None


def condition_grade(snapshot):
    """The overall condition of a snapshot as the web badge shows it: the
    lowest end of the folded ``condition_grade``, else ``3 - the worst
    finding`` (spalling, cracking, corrosion), else None (not assessed)."""
    props = (snapshot or {}).get('properties') or {}

    def numeric(name):
        rng = (props.get(name) or {}).get('range') or []
        nums = [v for v in rng if isinstance(v, (int, float))
                and not isinstance(v, bool)]
        return (min(nums), max(nums)) if nums else None

    grade = numeric('condition_grade')
    if grade:
        return int(grade[0])
    severities = [r[1] for r in (numeric(n) for n in FINDING_QUANTITIES) if r]
    if severities:
        return int(max(0, min(3, 3 - max(severities))))
    return None


def capture_markers(snapshot):
    """``[(label, role, (x, y, z)), ...]`` of ``capture.markers``."""
    out = []
    for marker in ((snapshot or {}).get('capture') or {}).get('markers') or []:
        point = marker.get('point') or []
        if len(point) == 3:
            out.append((marker.get('label'), marker.get('role'),
                        (float(point[0]), float(point[1]), float(point[2]))))
    return out


# FRAMES AND PLACEMENT --------------------------------------------------------
def frame_ok(frame):
    """True for ``{o, x, y, z}`` of four 3-vectors."""
    if not isinstance(frame, dict):
        return False
    for key in ('o', 'x', 'y', 'z'):
        v = frame.get(key)
        if not isinstance(v, (list, tuple)) or len(v) < 3:
            return False
        if not all(isinstance(c, (int, float)) for c in v[:3]):
            return False
    return True


def placement_matrix(frame):
    """4x4 matrix mapping local axes to the world: columns x, y, z, o."""
    matrix = np.eye(4)
    matrix[:3, 0] = np.asarray(frame['x'][:3], dtype=np.float64)
    matrix[:3, 1] = np.asarray(frame['y'][:3], dtype=np.float64)
    matrix[:3, 2] = np.asarray(frame['z'][:3], dtype=np.float64)
    matrix[:3, 3] = np.asarray(frame['o'][:3], dtype=np.float64)
    return matrix


def canonical_matrix(frame):
    """Stored -> canonical coordinates: the inverse of the frame's
    placement (the frame's origin goes to 0, its axes to x, y, z). Rigid, so
    the inverse is the transpose of the rotation."""
    matrix = placement_matrix(frame)
    rotation = matrix[:3, :3]
    out = np.eye(4)
    out[:3, :3] = rotation.T
    out[:3, 3] = -rotation.T @ matrix[:3, 3]
    return out


def apply_matrix(points, matrix):
    """Transform an (n, 3) array of points by a 4x4 matrix."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def matrix_rows(matrix):
    """A 4x4 matrix as 4 lists of 4 floats (row-major)."""
    return [[float(v) for v in row] for row in matrix]


def placement_of(passport):
    """The client-side placement ``{o, x, y, z}`` of a passport, or None."""
    _, snapshot = parts(passport)
    value = (snapshot or {}).get(PLACEMENT_KEY)
    return value if frame_ok(value) else None


def with_placement(passport, frame):
    """The passport (as a dict) with ``csc_placement`` set on its first
    snapshot. The key stays on the client."""
    data = load_passport(passport)
    if data is None:
        raise ValueError('not a passport')
    if not frame_ok(frame):
        raise ValueError('a placement is {o, x, y, z}')
    data = json.loads(json.dumps(data))
    data['snapshots'][0][PLACEMENT_KEY] = {
        k: [float(c) for c in frame[k][:3]] for k in ('o', 'x', 'y', 'z')}
    return data


def canonical_placement(frame):
    """The placement plane ``{o, x, y, z}`` that stored geometry takes when
    it is moved to its canonical orientation: the plane the world plane
    becomes under ``canonical_matrix(frame)`` (client-side ``csc_placement``
    of a piece after ``ApplyFrame``)."""
    matrix = canonical_matrix(frame)
    return {'o': [float(v) for v in matrix[:3, 3]],
            'x': [float(v) for v in matrix[:3, 0]],
            'y': [float(v) for v in matrix[:3, 1]],
            'z': [float(v) for v in matrix[:3, 2]]}


def box_of(snapshot):
    """``(frame, size)`` of the snapshot's canonical box: ``bbx`` extents
    along the frame's x, y, z, centred at ``frame.o``; None without both."""
    frame = (snapshot or {}).get('frame')
    bbx = (snapshot or {}).get('bbx')
    if not frame_ok(frame) or not bbx or len(bbx) != 3:
        return None
    return frame, [float(v) for v in bbx]


# PROXIES ---------------------------------------------------------------------
def _positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and np.isfinite(value) and value > 0)


def _point(value, dims):
    return (isinstance(value, (list, tuple)) and len(value) >= dims
            and all(isinstance(v, (int, float)) and np.isfinite(v)
                    for v in value[:dims]))


def drawable_proxy(proxy):
    """True when the proxy's parameters and placement give a shape (the
    rules of ``src/frontend/lib/proxyShape.ts``)."""
    if not isinstance(proxy, dict) or not frame_ok(proxy.get('placement')):
        return False
    params = proxy.get('params') or {}
    kind = proxy.get('primitive')
    if kind == 'box':
        size = params.get('size')
        return (isinstance(size, (list, tuple)) and len(size) == 3
                and all(_positive(v) for v in size))
    if kind == 'prism':
        profile = params.get('profile')
        return (isinstance(profile, (list, tuple)) and len(profile) >= 3
                and all(_point(p, 2) for p in profile)
                and _positive(params.get('height')))
    if kind == 'cylinder':
        return _positive(params.get('radius')) \
            and _positive(params.get('height'))
    if kind == 'hull':
        vertices, faces = params.get('vertices'), params.get('faces')
        return (isinstance(vertices, (list, tuple)) and len(vertices) >= 4
                and all(_point(p, 3) for p in vertices)
                and isinstance(faces, (list, tuple)) and len(faces) >= 4
                and all(_point(f, 3) for f in faces))
    return False


def drawable_proxies(snapshot):
    """The proxies of a snapshot that can be drawn, in stored order, as
    ``(index, proxy)``."""
    proxies = ((snapshot or {}).get('geometry') or {}).get('proxies') or []
    return [(i, p) for i, p in enumerate(proxies) if drawable_proxy(p)]


def authored_only(snapshot):
    """True when the snapshot has no mesh and no point cloud but has an
    authored proxy: what the fetch components must build from params."""
    geometry = (snapshot or {}).get('geometry') or {}
    if geometry.get('meshes') or geometry.get('point_clouds'):
        return False
    return any((p.get('fit') or {}).get('method') == 'authored'
               for p in geometry.get('proxies') or [])


# FILTERS ---------------------------------------------------------------------
def fetch_filter_params(original_function=None, material=None, dataset=None,
                        complexity=None, fragment=None, reserved=None,
                        shape_class=None, material_class=None,
                        circulation=None, bbx=None, fit_mode=None,
                        fit_size=None, fit_tolerance=None, near_point=None,
                        near_layer=None, radius_km=None):
    """Query parameters of ``GET /identities`` for FetchFilteredComponents.

    ``bbx``: dict with min_x / max_x / min_y / max_y / min_z / max_z
    (0 or None = not set). ``reserved``: -1 ignore, 0 not reserved, 1
    reserved by the caller. ``fit_*``: the dimension search (``fit_params``),
    ``near_point`` / ``near_layer`` / ``radius_km`` the near search
    (``near_params``); a value that cannot be used raises ``ValueError`` with
    a text for the user.
    """
    params = {}

    def put(key, value):
        value = None if value is None else str(value).strip()
        if value:
            params[key] = value

    put('original_function', original_function)
    put('material', material)
    put('dataset', dataset)
    put('shape_class', shape_class)
    put('material_class', material_class)
    put('circulation', circulation)
    if complexity is not None:
        params['complexity'] = int(complexity)
    if fragment is not None:
        params['fragment'] = 'true' if fragment else 'false'
    if reserved is not None and reserved != -1:
        params['reserved'] = 'true' if reserved == 1 else 'false'
    for key, value in (bbx or {}).items():
        if value is not None and value != 0:
            params['bbx_' + key] = value
    params.update(fit_params(fit_mode, fit_size, fit_tolerance))
    params.update(near_params(near_point, near_layer, radius_km))
    return params


# DIMENSION AND NEAR SEARCH (8.169, 8.170) -----------------------------------
FIT_MODES = ('about', 'can_hold')
NEAR_LAYERS = ('current', 'origin')
MAX_FIT_MM = 100000
DEFAULT_TOLERANCE = '10%'
_TOLERANCE = re.compile(r'^(\d+(?:\.\d+)?)\s*(%|mm)$', re.IGNORECASE)
_NUMBER = re.compile(r'^\d+(?:\.\d+)?$')


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _number(value):
    """A finite float from a number or a number text ('1200', '12,5'), else
    None; a bool is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(',', '.')
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _unwrap(value):
    """The one value of a list access that holds a single item that is no
    number (a Point3d, a vector, a text): a point wired to a list input
    arrives as a list of one."""
    if (isinstance(value, (list, tuple)) and len(value) == 1
            and _number(value[0]) is None):
        return value[0]
    return value


def _numbers_of(value):
    """The numbers of a Point3d / Vector3d (X, Y, Z), a list or tuple, or a
    text separated by commas, semicolons or spaces ('49.87, 8.65'; a
    decimal point, not a comma); None when
    it is none of them or a part is no number."""
    if isinstance(value, str):
        parts = [p for p in re.split(r'[;,\s]+', value.strip()) if p]
        values = [_number(p) for p in parts]
    elif hasattr(value, 'X') and hasattr(value, 'Y'):
        values = [_number(value.X), _number(value.Y)]
        if hasattr(value, 'Z'):
            values.append(_number(value.Z))
    else:
        try:
            values = [_number(v) for v in value]
        except TypeError:
            return None
    return None if any(v is None for v in values) else values


def fit_mode_of(value):
    """'about' or 'can_hold' from a text ('Can hold', 'can-hold' too); None
    when blank; ``ValueError`` for anything else."""
    if _blank(value):
        return None
    mode = str(value).strip().lower().replace('-', '_').replace(' ', '_')
    if mode not in FIT_MODES:
        raise ValueError('FitMode is "about" (every side within the '
                         'tolerance of FitSize) or "can_hold" (every side of '
                         'the piece at least FitSize), not %r' % (value,))
    return mode


def fit_size_of(value):
    """The three asked sides (mm, any order) from a list of three numbers, a
    Point3d / Vector3d (X, Y, Z) or a text '1200, 600, 200', as the REST text
    ``'1200,600,200'``; ``ValueError`` when they are not three numbers above
    0 and at most 100 m."""
    value = _unwrap(value)
    numbers = None if _blank(value) else _numbers_of(value)
    if numbers is None or len(numbers) != 3:
        raise ValueError('FitSize needs three sizes in mm, in any order '
                         '(a list of three numbers, a point or vector, or '
                         'the text 1200,600,200)')
    if not all(0 < n <= MAX_FIT_MM for n in numbers):
        raise ValueError('FitSize: every side is above 0 and at most %d mm'
                         % MAX_FIT_MM)
    return ','.join(('%g' % n) for n in numbers)


def fit_tolerance_of(value):
    """The tolerance as the REST takes it: '10%' or '50mm'. A bare number is
    read as per cent (the web default is 10 %). None when blank;
    ``ValueError`` for anything else."""
    if _blank(value):
        return None
    bad = ('FitTolerance is a number (per cent) or a text such as 10%% or '
           '50mm, not %r' % (value,))
    if isinstance(value, str):
        text = value.strip().replace(',', '.')
        if _NUMBER.match(text):
            text += '%'
    else:
        number = _number(value)
        if number is None or number < 0:
            raise ValueError(bad)
        text = '%g%%' % number
    found = _TOLERANCE.match(text)
    if not found:
        raise ValueError(bad)
    amount, unit = float(found.group(1)), found.group(2).lower()
    if unit == '%' and amount > 100:
        raise ValueError('FitTolerance in per cent is at most 100')
    if unit == 'mm' and amount > MAX_FIT_MM:
        raise ValueError('FitTolerance in mm is at most %d' % MAX_FIT_MM)
    return '%s%s' % (found.group(1), unit)


def fit_params(mode, size, tolerance):
    """``fit_mode`` / ``fit_size`` / ``fit_tol`` of the REST list (the web's
    "Fits" search). Empty without a mode and a size; a size without a mode is
    an error (the server would answer 422). *Can hold* takes no tolerance, it
    is left out."""
    mode = fit_mode_of(mode)
    if mode is None:
        if not _blank(size):
            raise ValueError('FitSize needs FitMode: "about" or "can_hold"')
        return {}
    params = {'fit_mode': mode, 'fit_size': fit_size_of(size)}
    if mode == 'about':
        params['fit_tol'] = fit_tolerance_of(tolerance) or DEFAULT_TOLERANCE
    return params


def near_point_of(value):
    """``(lat, lon)`` from a Point3d / Vector3d with X = latitude and Y =
    longitude (as the PlaceLocation of Origin), a list of two numbers or a
    text 'lat, lon'; ``ValueError`` out of range."""
    value = _unwrap(value)
    numbers = _numbers_of(value)
    if numbers is None or len(numbers) < 2 or (
            isinstance(value, (list, tuple, str)) and len(numbers) != 2):
        raise ValueError('NearPoint is a point or vector with X = latitude '
                         'and Y = longitude, or the text "lat, lon"')
    lat, lon = numbers[0], numbers[1]
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('NearPoint: latitude is between -90 and 90 (X), '
                         'longitude between -180 and 180 (Y)')
    return lat, lon


def near_layer_of(value):
    if _blank(value):
        return None
    layer = str(value).strip().lower()
    if layer not in NEAR_LAYERS:
        raise ValueError('NearLayer is "current" (where the piece is now) or '
                         '"origin" (the building it came from), not %r'
                         % (value,))
    return layer


def near_params(point, layer, radius_km):
    """``near_lat`` / ``near_lon`` / ``near_layer`` / ``radius_km`` of the REST
    list. Empty without a point; a layer or radius without a point is an
    error. No radius (or 0) = every piece with a point on the layer, nearest
    first."""
    layer = near_layer_of(layer)
    radius = None if _blank(radius_km) else _number(radius_km)
    if not _blank(radius_km) and radius is None:
        raise ValueError('RadiusKm is a number of kilometres')
    if _blank(point):
        if layer is not None or radius not in (None, 0):
            raise ValueError('NearLayer and RadiusKm need NearPoint')
        return {}
    lat, lon = near_point_of(point)
    params = {'near_lat': '%.7g' % lat, 'near_lon': '%.7g' % lon}
    if layer is not None:
        params['near_layer'] = layer
    if radius is not None and radius != 0:
        if radius < 0:
            raise ValueError('RadiusKm is above 0 (or empty for the nearest)')
        params['radius_km'] = '%g' % radius
    return params


def fit_percent(row):
    """The match of a list row as one number: the deviation in per cent
    (*about*) or the waste as a share of the piece's box in per cent (*can
    hold*); None without a dimension search."""
    fit = (row or {}).get('fit')
    if not isinstance(fit, dict):
        return None
    if fit.get('mode') == 'about' and fit.get('deviation') is not None:
        return float(fit['deviation']) * 100.0
    if fit.get('mode') == 'can_hold' and fit.get('waste_percent') is not None:
        return float(fit['waste_percent'])
    return None


def distance_km(row):
    """The distance of a list row from the near point in km; None without a
    near search."""
    metres = (row or {}).get('distance_m')
    return None if metres is None else float(metres) / 1000.0


# SIMILAR SEARCH (8.174) -------------------------------------------------------
SIMILAR_BASES = ('radial_signature', 'scalars', 'hks')
DEFAULT_SIMILAR_BASIS = 'radial_signature'
DEFAULT_SIMILAR_COUNT = 10
MAX_SIMILAR_COUNT = 50


def similar_basis(value):
    """The basis of the descriptor space: ``radial_signature`` (default),
    ``scalars`` or ``hks``; ``ValueError`` for anything else."""
    if _blank(value):
        return DEFAULT_SIMILAR_BASIS
    basis = str(value).strip().lower().replace(' ', '_')
    if basis not in SIMILAR_BASES:
        raise ValueError('Basis is one of %s, not %r'
                         % (', '.join(SIMILAR_BASES), value))
    return basis


def similar_count(value):
    """``(count, note)``: how many neighbours to ask for (default 10, 1 to 50
    as the server limits it); ``note`` says when the number was changed."""
    if _blank(value):
        return DEFAULT_SIMILAR_COUNT, None
    number = _number(value)
    if number is None:
        raise ValueError('Count is a whole number, 1 to %d'
                         % MAX_SIMILAR_COUNT)
    count = int(number)
    if count < 1:
        return 1, 'Count raised to 1'
    if count > MAX_SIMILAR_COUNT:
        return MAX_SIMILAR_COUNT, ('Count lowered to the most the server '
                                   'gives, %d' % MAX_SIMILAR_COUNT)
    return count, None


def similar_params(filters, basis=None, count=None):
    """The query of ``GET /identities/{id}/similar``: the filters (the output
    of ``fetch_filter_params``; the server ignores ``reserved`` here), the
    basis and the count. Returns ``(params, note)``."""
    params = {k: v for k, v in (filters or {}).items() if k != 'reserved'}
    number, note = similar_count(count)
    params['basis'] = similar_basis(basis)
    params['count'] = number
    return params, note


def similar_results(body):
    """The neighbours of a ``/similar`` answer, nearest first: dicts with the
    identity ``id``, the descriptor ``distance`` (standardised units) and the
    ``fit`` (per cent) and ``distance_km`` of the row when those searches were
    set."""
    out = []
    for item in (body or {}).get('results') or []:
        piece = item.get('piece') or {}
        identity_id = piece.get('_id') or piece.get('id')
        if not identity_id:
            continue
        out.append({'id': identity_id, 'distance': item.get('distance'),
                    'fit': fit_percent(piece),
                    'distance_km': distance_km(piece)})
    return out


def similar_error_text(status, detail=None):
    """What a refused ``/similar`` call means, in words for the user; an empty
    text for a status that is not one of them."""
    detail = detail if isinstance(detail, str) else ''
    if status == 404:
        return ('Component not found, or not visible to you (the server '
                'gives the same answer for both)')
    if status == 409:
        return ('The similarity data is not built on the server yet (it is '
                'built by the component map job); try again later')
    if status == 422:
        if detail:
            return 'Similar search refused: ' + detail
        return ('Similar search refused: no descriptor for this basis, or a '
                'filter the server cannot use')
    return ''


def passes_filters(passport, original_function=None, material=None,
                   dataset=None, complexity=None, fragment=None,
                   shape_class=None, material_class=None, bbx=None):
    """Client-side filter of one passport with the same fields as the fetch.
    A value that is not set does not filter; a piece without the filtered
    field (``complexity`` before the runner ran) does not match."""
    identity, snapshot = parts(passport)
    if identity is None or snapshot is None:
        return False

    def same(have, want):
        return str(have or '').lower() == str(want).strip().lower()

    for have, want in ((identity.get('original_function'), original_function),
                       (identity.get('material'), material),
                       (identity.get('dataset'), dataset),
                       (identity.get('material_class'), material_class),
                       (snapshot.get('shape_class'), shape_class)):
        if want is not None and str(want).strip() and not same(have, want):
            return False
    if complexity is not None and snapshot.get('complexity') != complexity:
        return False
    if fragment is not None and bool(snapshot.get('fragment')) != fragment:
        return False
    extents = snapshot.get('bbx')
    if bbx and isinstance(extents, (list, tuple)) and len(extents) >= 3:
        for axis, value in zip('xyz', extents[:3]):
            low, high = bbx.get('min_' + axis), bbx.get('max_' + axis)
            if low not in (None, 0) and value < low:
                return False
            if high not in (None, 0) and value > high:
                return False
    return True


def proxy_points(proxy):
    """Corner points of a drawable proxy in stored coordinates (a box: its 8
    corners, a prism: the profile at both ends, a cylinder: two rings, a
    hull: its vertices); an (n, 3) array, empty when it cannot be drawn."""
    if not drawable_proxy(proxy):
        return np.zeros((0, 3))
    params = proxy['params']
    kind = proxy['primitive']
    if kind == 'box':
        half = np.asarray(params['size'], dtype=np.float64) / 2.0
        local = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1)
                          for z in (-1, 1)]) * half
    elif kind == 'prism':
        profile = np.asarray(params['profile'], dtype=np.float64)[:, :2]
        h = float(params['height']) / 2.0
        local = np.vstack([np.column_stack([profile, np.full(len(profile), z)])
                           for z in (-h, h)])
    elif kind == 'cylinder':
        theta = np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False)
        r, h = float(params['radius']), float(params['height']) / 2.0
        local = np.vstack([np.column_stack(
            [r * np.cos(theta), r * np.sin(theta), np.full(48, z)])
            for z in (-h, h)])
    else:
        local = np.asarray(params['vertices'], dtype=np.float64)[:, :3]
    return apply_matrix(local, placement_matrix(proxy['placement']))


def passport_points(snapshot):
    """All component points of a snapshot as the preview carries them (inline
    mesh vertices, cloud points, authored proxies when there is nothing
    else), in stored coordinates: the input of a local frame."""
    geometry = (snapshot or {}).get('geometry') or {}
    chunks = []
    for mesh in geometry.get('meshes') or []:
        if mesh.get('vertices'):
            chunks.append(np.asarray(mesh['vertices'], dtype=np.float64))
    for cloud in geometry.get('point_clouds') or []:
        if cloud.get('points'):
            chunks.append(np.asarray(cloud['points'], dtype=np.float64))
    if not chunks:
        for _, proxy in drawable_proxies(snapshot):
            chunks.append(proxy_points(proxy))
    chunks = [c.reshape(-1, 3) for c in chunks if len(c)]
    return np.vstack(chunks) if chunks else np.zeros((0, 3))
