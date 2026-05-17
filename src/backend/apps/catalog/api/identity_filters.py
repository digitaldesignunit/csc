"""
Shared filter/sort helpers for identity + current-snapshot list queries.
"""

from typing import Any, Dict, Literal, Optional

from apps.catalog.models import ALLOWED_COMPONENT_SORTKEYS

ConsumedFilter = Literal['active', 'consumed', 'all']
ExpandMode = Literal['none', 'current_snapshot', 'shallow']

_IDENTITY_SORT_FIELDS = frozenset({
    '_id', 'type', 'material', 'dataset', 'catalog_number', 'reserved',
})
_SNAPSHOT_SORT_FIELDS = frozenset({
    'name', 'color', 'complexity', 'fragment', 'assembly', 'validated',
    'bbx.0', 'bbx.1', 'bbx.2', 'created', 'lastmodified',
})


def build_identity_match_stage(
    *,
    comptype: str = '',
    material: str = '',
    dataset: str = '',
    reserved: Optional[str] = None,
    consumed_filter: ConsumedFilter = 'active',
) -> Dict[str, Any]:
    """Match stage on ``component_identities`` (pre-lookup)."""
    match: Dict[str, Any] = {}

    if consumed_filter == 'active':
        match['consumed_at'] = None
    elif consumed_filter == 'consumed':
        match['consumed_at'] = {'$ne': None}

    if comptype:
        match['type'] = {'$regex': f'^{comptype}$', '$options': 'i'}
    if material:
        match['material'] = {'$regex': f'^{material}$', '$options': 'i'}
    if dataset:
        match['dataset'] = {'$regex': f'^{dataset}$', '$options': 'i'}

    if reserved == 'true':
        match['reserved'] = {'$ne': ''}
    elif reserved == 'false':
        match['reserved'] = ''

    return match


def build_snapshot_match_stage(
    *,
    validated: int = 1,
    complexity: Optional[int] = None,
    fragment: Optional[bool] = None,
    bbx_min_x: Optional[float] = None,
    bbx_min_y: Optional[float] = None,
    bbx_min_z: Optional[float] = None,
    bbx_max_x: Optional[float] = None,
    bbx_max_y: Optional[float] = None,
    bbx_max_z: Optional[float] = None,
    prefix: str = 'current_snapshot.',
) -> Dict[str, Any]:
    """
    Match after ``$lookup`` + ``$unwind`` on the current snapshot.
    """
    match: Dict[str, Any] = {}

    if validated == 1:
        match[f'{prefix}validated'] = True
    elif validated == -1:
        match[f'{prefix}validated'] = False

    if complexity is not None:
        match[f'{prefix}complexity'] = complexity
    if fragment is not None:
        match[f'{prefix}fragment'] = fragment

    if bbx_min_x is not None or bbx_max_x is not None:
        bbx_query: Dict[str, Any] = {}
        if bbx_min_x is not None:
            bbx_query['$gte'] = bbx_min_x
        if bbx_max_x is not None:
            bbx_query['$lte'] = bbx_max_x
        if bbx_query:
            match[f'{prefix}bbx.0'] = bbx_query

    if bbx_min_y is not None or bbx_max_y is not None:
        bbx_query = {}
        if bbx_min_y is not None:
            bbx_query['$gte'] = bbx_min_y
        if bbx_max_y is not None:
            bbx_query['$lte'] = bbx_max_y
        if bbx_query:
            match[f'{prefix}bbx.1'] = bbx_query

    if bbx_min_z is not None or bbx_max_z is not None:
        bbx_query = {}
        if bbx_min_z is not None:
            bbx_query['$gte'] = bbx_min_z
        if bbx_max_z is not None:
            bbx_query['$lte'] = bbx_max_z
        if bbx_query:
            match[f'{prefix}bbx.2'] = bbx_query

    return match


def resolve_sort_field(sortkey: str) -> str:
    """Map legacy shallow sort keys to identity or joined snapshot paths."""
    if sortkey not in ALLOWED_COMPONENT_SORTKEYS:
        sortkey = '_id'
    if sortkey in _IDENTITY_SORT_FIELDS:
        return sortkey
    if sortkey in _SNAPSHOT_SORT_FIELDS:
        return f'current_snapshot.{sortkey}'
    return '_id'


def merge_shallow_catalog_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy-style shallow row: identity core + current snapshot metadata."""
    snap = doc.get('current_snapshot') or {}
    row: Dict[str, Any] = {
        '_id': doc.get('_id'),
        'type': doc.get('type'),
        'material': doc.get('material'),
        'dataset': doc.get('dataset'),
        'reserved': doc.get('reserved', ''),
        'catalog_number': doc.get('catalog_number'),
        'name': snap.get('name'),
        'created': snap.get('created'),
        'lastmodified': snap.get('lastmodified'),
        'complexity': snap.get('complexity'),
        'fragment': snap.get('fragment'),
        'assembly': snap.get('assembly'),
        'validated': snap.get('validated'),
        'color': snap.get('color'),
        'bbx': snap.get('bbx'),
        'bbx_origin': snap.get('bbx_origin'),
        'condition': snap.get('condition'),
        'location': snap.get('location'),
        'processes': snap.get('processes'),
        'iframe': snap.get('iframe'),
        'pca_frame': snap.get('pca_frame'),
        'etag': snap.get('etag'),
        'virtual': snap.get('virtual'),
        'version': snap.get('version'),
        'identity_id': snap.get('identity_id'),
        'current_snapshot_id': doc.get('current_snapshot_id'),
    }
    if 'reserved_by_username' in doc:
        row['reserved_by_username'] = doc['reserved_by_username']
    return row
