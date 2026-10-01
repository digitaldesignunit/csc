"""
Catalog filters and sort keys for the identity + current-snapshot queries
(spec section 7: ``type`` -> ``original_function``, ``consumed_filter`` ->
``circulation``, ``validated`` -> ``status``; withdrawn identities hidden
unless asked for).

``CatalogFilters`` is one FastAPI dependency shared by the list, count, map
and stats routes, so every route filters the same way.
"""

from dataclasses import dataclass, fields
from typing import Any, Dict, Literal, Optional

from fastapi import Query

Circulation = Literal['active', 'exited', 'all']
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
SORT_KEYS = tuple(sorted(_IDENTITY_SORT_FIELDS | _SNAPSHOT_SORT_FIELDS))
_BBX_AXES = (('x', 0), ('y', 1), ('z', 2))


def _exact(value: str) -> Dict[str, Any]:
    return {'$regex': f'^{value}$', '$options': 'i'}


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

    def identity_match(self) -> Dict[str, Any]:
        """``$match`` on ``component_identities`` (before the lookup)."""
        match: Dict[str, Any] = {}
        if self.circulation == 'active':
            match['exit'] = None
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

    def is_default_scope(self) -> bool:
        """True for the scope the map cron precomputes (no filter set)."""
        return all(getattr(self, f.name) == f.default for f in fields(self))


def catalog_filters(
    original_function: str = Query('', description='IFC class name'),
    material: str = Query('', description='materials._id'),
    material_class: str = Query('', description='List of Waste code'),
    dataset: str = Query(''),
    shape_class: str = Query(''),
    status: StatusFilter = Query('published'),
    circulation: Circulation = Query(
        'active', description='active = no exit; exited; all'),
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
) -> CatalogFilters:
    """FastAPI dependency: the catalog filters from the query string."""
    return CatalogFilters(**{k: v for k, v in locals().items()})


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
