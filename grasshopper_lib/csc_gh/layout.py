# Reinforcement layouts on the Grasshopper side (decisions 7.8, 8.98, 8.142;
# backlog RL9 and RL11).
# Pure: no Rhino import, numpy for the matrices.
#
# Going in (ReinforcementLayout): the curves a user drew on a piece that was
# moved (ApplyFrame, TransformComponent) are mapped back to the stored
# coordinates of the snapshot, the one coordinate system a layout is stated
# in. Coming out (FetchReinforcementLayout): the bars of the stored layouts
# are mapped stored -> placed, the same transform the Fetch...Geometry
# components apply to the mesh. Both directions use the passport's
# ``csc_placement`` Q (8.98: Q is the placement of the STORED geometry; a
# point in the document is ``Q . stored``). Document units are taken as
# millimetres, 1:1, like the Fetch...Geometry components and ApplyFrame do
# (user decision for 0.6.1.0): nothing is scaled by the unit of the document,
# a document that is not in millimetres only gets a warning
# (``unit_warning``). ``unit_factor`` stays for the later task that makes
# every component unit-aware.
#
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import math  # NOQA

import numpy as np  # NOQA

from .build import (BuildError, is_uuid, text)  # NOQA
from .convention import (ConventionError, check_plane)  # NOQA
from .read import (PLACEMENT_KEY, apply_matrix, canonical_matrix, load_passport, parts, placement_matrix)  # NOQA

METHOD = 'reinforcement_layout'
STATUSES = ('draft', 'pending', 'published', 'rejected', 'withdrawn')
DEFAULT_STATUS = 'published'


# UNITS ------------------------------------------------------------------------
def unit_factor(mm_per_unit):
    """Millimetres per document unit as a checked float (BuildError)."""
    try:
        factor = float(mm_per_unit)
    except (TypeError, ValueError):
        raise BuildError('the unit of the document is not a number')
    if not math.isfinite(factor) or factor <= 0:
        raise BuildError('the unit of the document is not usable')
    return factor


def unit_warning(mm_per_unit, unit_name=None):
    """The warning for a document that is not in millimetres (nothing is
    scaled); None for a millimetre document."""
    factor = unit_factor(mm_per_unit)
    if abs(factor - 1.0) < 1e-9:
        return None
    return ('The document is in %s: stored coordinates are millimetres and '
            'are used 1:1; draw at that scale' % (unit_name or 'another unit'))


# POINTS -----------------------------------------------------------------------
def _array(points):
    array = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if not np.all(np.isfinite(array)):
        raise BuildError('a point has a coordinate that is not a number')
    return array


def points_to_stored(points, placement=None):
    """Points drawn in the document as stored coordinates: mapped back
    through the placement ``{o, x, y, z}`` of the piece (the inverse of
    ``placement_transform``), no scaling. ``[(x, y, z), ...]``."""
    array = _array(points)
    if placement is not None:
        array = apply_matrix(array, canonical_matrix(placement))
    return [(float(x), float(y), float(z)) for x, y, z in array]


def points_to_document(points, placement=None):
    """Stored points as points of the document: moved by the placement
    (``placement_transform``), no scaling. The inverse of
    ``points_to_stored``."""
    array = _array(points)
    if placement is not None:
        array = apply_matrix(array, placement_matrix(placement))
    return [(float(x), float(y), float(z)) for x, y, z in array]


def bars_to_stored(bars, placement=None):
    """The bars (items ``{spec, diameter_mm, points, ...}``) with their points
    converted by ``points_to_stored``; diameters are not touched."""
    out = []
    for bar in bars:
        item = dict(bar)
        item['points'] = points_to_stored(bar['points'], placement)
        out.append(item)
    return out


# THE TARGET OF A NEW LAYOUT (RL9) ---------------------------------------------
def passport_placement(passport):
    """``(snapshot_id, placement)`` of a passport: the id of its first
    snapshot and its ``csc_placement`` (None without one). BuildError for a
    passport that is none, a snapshot without a valid id, or a placement that
    is not a plane."""
    data = load_passport(passport)
    if data is None:
        raise BuildError('ComponentPassport is not a component passport '
                         '(JSON with identity and snapshots)')
    _, snapshot = parts(data)
    snapshot_id = text((snapshot or {}).get('_id'))
    if not is_uuid(snapshot_id):
        raise BuildError('the snapshot of ComponentPassport has no valid id')
    raw = (snapshot or {}).get(PLACEMENT_KEY)
    placement = None
    if raw is not None:
        try:
            placement = check_plane(raw)
        except ConventionError as error:
            raise BuildError('the csc_placement of ComponentPassport is not '
                             'a usable plane: %s' % error)
    return snapshot_id.lower(), placement


def layout_target(passport=None, snapshot_id=None):
    """Where the curves of a new layout belong: ``{snapshot_id, placement,
    conversion, remark}``.

    A passport that carries a ``csc_placement`` Q means the curves lie on the
    piece as placed: ``conversion`` is ``inverse placement`` and the points
    are mapped back with Q. A passport without one, or no passport, means the
    curves are in stored coordinates (``none``). The snapshot comes from the
    passport; an explicit ``snapshot_id`` that disagrees is an error."""
    given = text(snapshot_id)
    given = given.lower() if given else None
    from_passport, placement = None, None
    if passport is not None and text(passport) is not None:
        from_passport, placement = passport_placement(passport)
        if given and given != from_passport:
            raise BuildError(
                'SnapshotID %s is not the snapshot of ComponentPassport (%s): '
                'a layout belongs to one version; clear SnapshotID or use '
                'the passport of that version' % (given, from_passport))
    chosen = from_passport or given
    if placement is not None:
        conversion = 'inverse placement'
        remark = ('conversion: inverse placement (the curves lie on the '
                  'placed piece; they were mapped back to the stored '
                  'coordinates of snapshot %s)' % chosen)
    elif from_passport:
        conversion = 'none'
        remark = ('conversion: none (the passport has no placement: the '
                  'curves are taken as stored coordinates of snapshot %s)'
                  % chosen)
    else:
        conversion = 'none'
        remark = ('conversion: none (no ComponentPassport: the curves are '
                  'taken as stored coordinates of the given SnapshotID)')
    return {'snapshot_id': chosen, 'placement': placement,
            'conversion': conversion, 'remark': remark}


# READING STORED LAYOUTS (RL11) -------------------------------------------------
def status_param(value):
    """The ``status`` query value of a Status input: ``published`` when
    empty, else one of the server's statuses or ``all``."""
    value = text(value)
    if value is None:
        return DEFAULT_STATUS
    value = value.lower()
    if value != 'all' and value not in STATUSES:
        raise BuildError('Status is one of %s or all, got %r'
                         % (', '.join(STATUSES), value))
    return value


def _number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def bars_of_record(record):
    """``(bars, skipped)`` of one stored layout record: each bar
    ``{spec, diameter_mm, diameter_known, cover_mm, points}`` with the points
    as float tuples in the stored coordinates, optional fields filled with
    their defaults (spec None, diameter known, cover None). ``skipped`` lists
    the indices of bars that could not be read (no diameter, fewer than two
    valid points)."""
    payload = record.get('payload') if isinstance(record, dict) else None
    raw = payload.get('bars') if isinstance(payload, dict) else None
    bars, skipped = [], []
    for index, bar in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(bar, dict):
            skipped.append(index)
            continue
        diameter = _number(bar.get('diameter_mm'))
        points = []
        for point in bar.get('points') or []:
            try:
                xyz = tuple(float(v) for v in point[:3])
            except (TypeError, ValueError):
                points = []
                break
            if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):
                points = []
                break
            points.append(xyz)
        if diameter is None or diameter <= 0 or len(points) < 2:
            skipped.append(index)
            continue
        bars.append({'spec': text(bar.get('spec')), 'diameter_mm': diameter,
                     'diameter_known': bar.get('diameter_known') is not False,
                     'cover_mm': _number(bar.get('cover_mm')),
                     'points': points})
    return bars, skipped


def layouts_of(rows):
    """``(layouts, skipped)`` from the rows of
    ``GET /identities/{id}/evidence?method=reinforcement_layout``: newest
    first (``observed_at``, then id). A layout is ``{id, status, basis,
    snapshot_id, observed_at, bars, skipped_bars}``. A row without content (a
    tombstone of a withdrawn record) or without readable bars is counted in
    ``skipped`` (record ids)."""
    layouts, skipped = [], []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get('method') not in (None, METHOD):
            skipped.append(row.get('_id'))
            continue
        bars, bad = bars_of_record(row)
        if not bars:
            skipped.append(row.get('_id'))
            continue
        position = row.get('position') if isinstance(
            row.get('position'), dict) else {}
        payload = row.get('payload') if isinstance(
            row.get('payload'), dict) else {}
        layouts.append({
            'id': row.get('_id'), 'status': row.get('status'),
            'basis': payload.get('basis'),
            'snapshot_id': text(position.get('snapshot_id')),
            'observed_at': row.get('observed_at'),
            'bars': bars, 'skipped_bars': bad})
    layouts.sort(key=lambda item: (str(item['observed_at'] or ''),
                                   str(item['id'] or '')), reverse=True)
    return layouts, skipped


def layout_points(layout, placement=None, passport_snapshot_id=None):
    """``(point lists, warning)``: the points of each bar of a layout in the
    place of the document. A layout of the passport's snapshot is moved by the
    passport's placement (stored -> placed); one of another snapshot is left
    in its stored coordinates (they belong to that version) and the warning
    names its snapshot."""
    warning = None
    use = None
    if placement is not None:
        if layout.get('snapshot_id') == text(passport_snapshot_id):
            use = placement
        else:
            warning = ('layout %s belongs to snapshot %s, not to the '
                       'snapshot of the passport (%s): its points are in '
                       'the stored coordinates of that snapshot, not '
                       'placed' % (layout.get('id'), layout.get('snapshot_id'),
                                   passport_snapshot_id))
    return ([points_to_document(bar['points'], use)
             for bar in layout['bars']], warning)
