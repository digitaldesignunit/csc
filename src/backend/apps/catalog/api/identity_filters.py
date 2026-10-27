"""
Catalog filters and sort keys for the identity + current-snapshot queries
(spec section 7: ``type`` -> ``original_function``, ``consumed_filter`` ->
``circulation``, ``validated`` -> ``status``; withdrawn identities hidden
unless asked for).

``CatalogFilters`` is one FastAPI dependency shared by the list, count, map
and stats routes, so every route filters the same way.
"""

import re
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import HTTPException, Query

from ..vocab import EvidenceMethod
from .dimension_fit import (
    DEFAULT_TOLERANCE,
    FitError,
    FitMode,
    fit_stages,
    parse_size,
    parse_tolerance,
)
from .near_search import (
    Near,
    NearError,
    NearLayer,
    first_stages,
    parse_near,
)

# active = no exit (in place or deinstalled); in_place / deinstalled are its
# two parts (decision 8.104); exited = has an exit; all
Circulation = Literal['active', 'in_place', 'deinstalled', 'exited', 'all']
StatusFilter = Literal['published', 'pending', 'draft', 'rejected',
                       'withdrawn', 'any']
ExpandMode = Literal['none', 'current_snapshot', 'shallow']

_IDENTITY_SORT_FIELDS = frozenset({
    '_id', 'catalog_number', 'original_function', 'material',
    'material_class', 'dataset', 'reserved',
})
_SNAPSHOT_SORT_FIELDS = frozenset({
    'name', 'color', 'complexity', 'fragment', 'shape_class',
    'effective_from', 'bbx.0', 'bbx.1', 'bbx.2', 'created', 'lastmodified',
})
# computed in the pipeline: ``volume`` from the current ``bbx`` (8.173),
# ``match`` from the dimension search (8.169) and ``distance`` from the near
# search (8.170), each only while its search is set
_COMPUTED_SORT_KEYS = frozenset({'volume', 'match', 'distance'})
SORT_KEYS = tuple(sorted(_IDENTITY_SORT_FIELDS | _SNAPSHOT_SORT_FIELDS
                         | _COMPUTED_SORT_KEYS))
_BBX_AXES = (('x', 0), ('y', 1), ('z', 2))
# the longest value a text filter accepts (a name, an id, a slug)
FILTER_MAX_LENGTH = 100


def _exact(value: str) -> Dict[str, Any]:
    """Equal ignoring case. The value is text, not a pattern: a ``.*`` or a
    nested quantifier in a query string must not reach the regex engine."""
    return {'$regex': f'^{re.escape(value)}$', '$options': 'i'}


@dataclass
class CatalogFilters:
    """What the catalog list shows; the defaults are the public catalog
    view (published, in circulation, not withdrawn)."""
    original_function: str = ''
    material: str = ''
    material_class: str = ''
    dataset: str = ''
    shape_class: str = ''
    status: str = 'published'
    circulation: str = 'active'
    exit_kind: str = ''
    complexity: Optional[int] = None
    fragment: Optional[bool] = None
    reserved: Optional[str] = None
    include_withdrawn: bool = False
    bbx_min_x: Optional[float] = None
    bbx_min_y: Optional[float] = None
    bbx_min_z: Optional[float] = None
    bbx_max_x: Optional[float] = None
    bbx_max_y: Optional[float] = None
    bbx_max_z: Optional[float] = None
    q: str = ''
    # evidence method (8.177): only pieces with a published, current evidence
    # record (not superseded) of this method; the ids come from the evidence collection, see
    # ``catalog_list._pipelines_args``
    evidence_method: Optional[str] = None
    # dimension search (8.169): the mode, the asked sides (largest first) and
    # the tolerance of ``about`` as (``percent`` | ``mm``, value)
    fit_mode: Optional[str] = None
    fit_sides: Optional[Tuple[float, float, float]] = None
    fit_tolerance: Optional[Tuple[str, float]] = None
    # near search (8.170): the point, the layer (current | origin; set once
    # there is a point) and the radius in km (none = nearest first)
    near_lat: Optional[float] = None
    near_lon: Optional[float] = None
    near_layer: Optional[str] = None
    radius_km: Optional[float] = None

    def fit_pipeline_stages(self) -> List[Dict[str, Any]]:
        """The stages of the dimension search, after the join of the current
        snapshot; none while no search is set."""
        if not self.fit_mode or not self.fit_sides:
            return []
        return fit_stages(self.fit_mode, self.fit_sides, self.fit_tolerance)

    @property
    def near(self) -> Optional[Near]:
        """The near search as (lat, lon, layer, radius in km), or None."""
        if self.near_lat is None or self.near_lon is None:
            return None
        return (self.near_lat, self.near_lon, self.near_layer or 'current',
                self.radius_km)

    def opening_stages(self, identity_match: Dict[str, Any]
                       ) -> List[Dict[str, Any]]:
        """The first stage of a pipeline: the ``$match`` on the identities,
        or, while a near search is set, the ``$geoNear`` that carries it."""
        return first_stages(identity_match, self.near)

    def identity_match(self) -> Dict[str, Any]:
        """``$match`` on ``component_identities`` (before the lookup)."""
        match: Dict[str, Any] = {}
        if self.circulation in ('active', 'in_place', 'deinstalled'):
            match['exit'] = None
            if self.circulation == 'in_place':
                match['origin.planned'] = True
            elif self.circulation == 'deinstalled':
                match['origin.planned'] = {'$ne': True}
        elif self.circulation == 'exited':
            match['exit'] = {'$ne': None}
        if self.exit_kind:
            match['exit.kind'] = self.exit_kind
        if not self.include_withdrawn:
            match['withdrawn'] = None
        for name in ('original_function', 'material', 'dataset'):
            value = getattr(self, name)
            if value:
                match[name] = _exact(value)
        if self.material_class:
            match['material_class'] = self.material_class
        if self.reserved == 'true':
            match['reserved'] = {'$ne': ''}
        elif self.reserved == 'false':
            match['reserved'] = ''
        return match

    def snapshot_match(self, prefix: str = 'current_snapshot.'
                       ) -> Dict[str, Any]:
        """``$match`` after the ``$lookup`` + ``$unwind`` of the current
        snapshot."""
        match: Dict[str, Any] = {}
        if self.status != 'any':
            match[f'{prefix}status'] = self.status
        if self.q.strip():
            match['$or'] = self._search_terms(prefix)
        if self.shape_class:
            match[f'{prefix}shape_class'] = self.shape_class
        if self.complexity is not None:
            match[f'{prefix}complexity'] = self.complexity
        if self.fragment is not None:
            match[f'{prefix}fragment'] = self.fragment
        for axis, index in _BBX_AXES:
            bounds: Dict[str, float] = {}
            low = getattr(self, f'bbx_min_{axis}')
            high = getattr(self, f'bbx_max_{axis}')
            if low is not None:
                bounds['$gte'] = low
            if high is not None:
                bounds['$lte'] = high
            if bounds:
                match[f'{prefix}bbx.{index}'] = bounds
        return match

    def _search_terms(self, prefix: str) -> List[Dict[str, Any]]:
        """The search field: a name (any part), a catalogue number (``12`` or
        ``#12``) or an id (any leading part of the UUID)."""
        text = self.q.strip()
        escaped = re.escape(text)
        terms: List[Dict[str, Any]] = [
            {f'{prefix}name': {'$regex': escaped, '$options': 'i'}},
            {'_id': {'$regex': f'^{escaped}', '$options': 'i'}},
        ]
        number = text.lstrip('#')
        if number.isascii() and number.isdigit():
            terms.append({'catalog_number': int(number)})
        return terms

    def is_default_scope(self) -> bool:
        """True for the scope the map cron precomputes (no filter set)."""
        return all(getattr(self, f.name) == f.default for f in fields(self))


# the query parameters of the searches: parsed apart, not passed on as they are
_SEARCH_PARAMS = ('fit_mode', 'fit_size', 'fit_tol', 'near_lat', 'near_lon',
                  'near_layer', 'radius_km')


def catalog_filters(
    original_function: str = Query('', max_length=FILTER_MAX_LENGTH,
                                   description='IFC class name'),
    material: str = Query('', max_length=FILTER_MAX_LENGTH,
                          description='materials._id'),
    material_class: str = Query('', description='List of Waste code'),
    dataset: str = Query('', max_length=FILTER_MAX_LENGTH),
    shape_class: str = Query(''),
    status: StatusFilter = Query('published'),
    circulation: Circulation = Query(
        'active', description='active = no exit (in place and '
                              'deinstalled); in_place; deinstalled; exited; '
                              'all'),
    exit_kind: str = Query(''),
    complexity: Optional[int] = Query(None),
    fragment: Optional[bool] = Query(None),
    reserved: Optional[str] = Query(None),
    include_withdrawn: bool = Query(False),
    bbx_min_x: Optional[float] = Query(None),
    bbx_min_y: Optional[float] = Query(None),
    bbx_min_z: Optional[float] = Query(None),
    bbx_max_x: Optional[float] = Query(None),
    bbx_max_y: Optional[float] = Query(None),
    bbx_max_z: Optional[float] = Query(None),
    q: str = Query('', max_length=FILTER_MAX_LENGTH,
                   description='name, catalogue number or id'),
    evidence_method: Optional[EvidenceMethod] = Query(
        None, description='only pieces with at least one published, current '
                          'evidence record of this method (8.177), for example '
                          'reinforcement_layout; combines with every other '
                          'filter'),
    fit_mode: Optional[FitMode] = Query(
        None, description='dimension search (8.169): about = every side '
                          'within fit_tol of fit_size; can_hold = every side '
                          'of the piece at least fit_size'),
    fit_size: Optional[str] = Query(
        None, max_length=FILTER_MAX_LENGTH,
        description='three sizes in mm in any order, for example '
                    '1200,600,200; needs fit_mode'),
    fit_tol: Optional[str] = Query(
        None, max_length=20,
        description='tolerance of about: 10% (default) or 50mm; not for '
                    'can_hold'),
    near_lat: Optional[float] = Query(
        None, description='near search (8.170): latitude, -90 to 90; needs '
                          'near_lon'),
    near_lon: Optional[float] = Query(
        None, description='near search: longitude, -180 to 180; needs '
                          'near_lat'),
    near_layer: Optional[NearLayer] = Query(
        None, description='which point of a piece is measured: current (the '
                          'location of the current version, default) or '
                          'origin (the origin building)'),
    radius_km: Optional[float] = Query(
        None, description='near search: only pieces within this many km; '
                          'without it every piece with a point on the layer, '
                          'nearest first'),
) -> CatalogFilters:
    """FastAPI dependency: the catalog filters from the query string."""
    values = {k: v for k, v in locals().items() if k not in _SEARCH_PARAMS}
    try:
        values.update(_parse_fit(fit_mode, fit_size, fit_tol))
        values.update(parse_near(near_lat, near_lon, near_layer, radius_km))
    except (FitError, NearError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return CatalogFilters(**values)


def _parse_fit(mode: Optional[str], size: Optional[str],
               tolerance: Optional[str]) -> Dict[str, Any]:
    """The fit query parameters -> the ``CatalogFilters`` fields."""
    if mode is None:
        if size is not None or tolerance is not None:
            raise FitError('fit_size and fit_tol need fit_mode (about or '
                           'can_hold)')
        return {}
    if size is None:
        raise FitError('fit_mode needs fit_size, three sizes in mm, for '
                       'example 1200,600,200')
    if mode == 'can_hold' and tolerance is not None:
        raise FitError('fit_mode can_hold takes no fit_tol')
    return {
        'fit_mode': mode,
        'fit_sides': parse_size(size),
        'fit_tolerance': (parse_tolerance(tolerance or DEFAULT_TOLERANCE)
                          if mode == 'about' else None),
    }


def public_filters(filters: CatalogFilters) -> CatalogFilters:
    """The filters an anonymous caller may use (8.118 Q8): published states
    of pieces that are not withdrawn, whatever the query string says."""
    filters.status = 'published'
    filters.include_withdrawn = False
    return filters


def children_identity_match(parent_identity_id: str, *,
                            public_only: bool = False) -> Dict[str, Any]:
    """
    Identities that list ``parent_identity_id`` in ``parent_identities``.
    Exited children are included: children of a split parent are usually
    still in circulation, and a child may itself be split.
    """
    match: Dict[str, Any] = {'parent_identities': parent_identity_id}
    if public_only:
        match['is_public'] = True
    return match


def resolve_sort_field(sortkey: str) -> str:
    """A sort key -> the identity or joined current-snapshot path."""
    if sortkey in _IDENTITY_SORT_FIELDS:
        return sortkey
    if sortkey in _SNAPSHOT_SORT_FIELDS:
        return f'current_snapshot.{sortkey}'
    return '_id'
