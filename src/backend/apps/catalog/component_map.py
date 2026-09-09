#!/usr/bin/env python3.9
"""
2D component map embeddings from stored descriptors.

Two feature bases:
  - ``radial_signature``: concatenate radial distance vectors across all
    supported resolutions.
  - ``scalars``: concatenate box/sphere/line/planescore.

PCA is the fast first paint; UMAP is the preferred layout when available.
Heavy UMAP layouts are precomputed by ``main_component_map.py`` and stored
in ``component_map_cache``; the API serves those by default.

Components missing any required descriptor for the chosen basis are omitted
from the point set (callers report displayed/total coverage).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from apps.descriptors import radial_signature as rs

MapBasis = Literal['radial_signature', 'scalars']
MapMethod = Literal['pca', 'umap']
MapSource = Literal['auto', 'cache', 'live']

MAP_BASES: Tuple[MapBasis, ...] = ('radial_signature', 'scalars')
MAP_METHODS: Tuple[MapMethod, ...] = ('pca', 'umap')

SCALAR_KEYS: Tuple[str, ...] = (
    'boxscore',
    'spherescore',
    'linescore',
    'planescore',
)

BASIS_LABELS: Dict[MapBasis, str] = {
    'radial_signature': 'radial signature',
    'scalars': 'scalar descriptors',
}

RADIAL_DISTANCE_KEYS: Tuple[str, ...] = tuple(
    rs.radial_distance_key(n) for n in rs.SUPPORTED_RESOLUTIONS
)

CACHE_COLLECTION = 'component_map_cache'
"""Mongo collection holding precomputed map layouts."""


def basis_label(basis: MapBasis) -> str:
    return BASIS_LABELS[basis]


def cache_doc_id(
    basis: MapBasis,
    method: MapMethod,
    *,
    consumed_filter: str = 'active',
    validated: int = 1,
) -> str:
    """Stable ``_id`` for a cached layout under a catalog scope."""
    return f'{basis}:{method}:{consumed_filter}:v{int(validated)}'


def is_default_map_scope(
    *,
    consumed_filter: str,
    validated: int,
    comptype: str = '',
    material: str = '',
    dataset: str = '',
    complexity: Optional[int] = None,
    fragment: Optional[bool] = None,
    reserved: Optional[str] = None,
    bbx_min_x: Optional[float] = None,
    bbx_min_y: Optional[float] = None,
    bbx_min_z: Optional[float] = None,
    bbx_max_x: Optional[float] = None,
    bbx_max_y: Optional[float] = None,
    bbx_max_z: Optional[float] = None,
) -> bool:
    """True when filters match the cron-cached catalog scope."""
    return (
        consumed_filter == 'active'
        and int(validated) == 1
        and not comptype
        and not material
        and not dataset
        and complexity is None
        and fragment is None
        and reserved is None
        and bbx_min_x is None
        and bbx_min_y is None
        and bbx_min_z is None
        and bbx_max_x is None
        and bbx_max_y is None
        and bbx_max_z is None
    )


def map_rows_project_stage() -> Dict[str, Any]:
    """``$project`` stage used by the map route and cron aggregation."""
    return {
        '$project': {
            '_id': 1,
            'type': 1,
            'catalog_number': 1,
            'name': '$current_snapshot.name',
            'color': '$current_snapshot.color',
            'descriptors': '$current_snapshot.descriptors',
        },
    }


def _finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _flatten_distance_vector(value: Any, expected_len: int) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != expected_len:
        return None
    out: List[float] = []
    for item in value:
        number = _finite_float(item)
        if number is None:
            return None
        out.append(number)
    return out


def extract_radial_feature(descriptors: Mapping[str, Any]) -> Optional[np.ndarray]:
    """Concatenate ``radial_distance_N`` for every supported resolution.

    Requires the full radial-signature family (distances and tangents) to be
    present so coverage matches descriptor missingness elsewhere.
    """
    for n in rs.SUPPORTED_RESOLUTIONS:
        tangents = descriptors.get(rs.radial_tangent_key(n))
        if not isinstance(tangents, (list, tuple)) or len(tangents) != int(n):
            return None

    parts: List[float] = []
    for n, key in zip(rs.SUPPORTED_RESOLUTIONS, RADIAL_DISTANCE_KEYS):
        vec = _flatten_distance_vector(descriptors.get(key), int(n))
        if vec is None:
            return None
        parts.extend(vec)
    return np.asarray(parts, dtype=np.float64)


def extract_scalar_feature(descriptors: Mapping[str, Any]) -> Optional[np.ndarray]:
    """Concatenate the four shape-fitness scalar scores."""
    parts: List[float] = []
    for key in SCALAR_KEYS:
        number = _finite_float(descriptors.get(key))
        if number is None:
            return None
        parts.append(number)
    return np.asarray(parts, dtype=np.float64)


def extract_feature(
    descriptors: Mapping[str, Any],
    basis: MapBasis,
) -> Optional[np.ndarray]:
    if basis == 'radial_signature':
        return extract_radial_feature(descriptors)
    if basis == 'scalars':
        return extract_scalar_feature(descriptors)
    raise ValueError(f'Unknown map basis: {basis!r}')


def _embed_pca(matrix: np.ndarray) -> np.ndarray:
    n_samples, n_features = matrix.shape
    if n_samples == 0:
        return np.zeros((0, 2), dtype=np.float64)
    if n_samples == 1:
        return np.zeros((1, 2), dtype=np.float64)

    scaled = StandardScaler().fit_transform(matrix)
    n_components = min(2, n_samples, n_features)
    coords = PCA(n_components=n_components, random_state=42).fit_transform(scaled)
    if n_components == 1:
        coords = np.column_stack([coords[:, 0], np.zeros(n_samples)])
    return coords.astype(np.float64)


def _embed_umap(matrix: np.ndarray) -> np.ndarray:
    n_samples = matrix.shape[0]
    if n_samples < 3:
        # UMAP needs a small neighbourhood; fall back for tiny sets.
        return _embed_pca(matrix)

    try:
        import umap
    except ImportError as exc:
        raise RuntimeError(
            'umap-learn is required for method=umap'
        ) from exc

    scaled = StandardScaler().fit_transform(matrix)
    n_neighbors = max(2, min(15, n_samples - 1))
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=0.1,
        metric='euclidean',
        random_state=42,
    )
    return reducer.fit_transform(scaled).astype(np.float64)


def embed_matrix(matrix: np.ndarray, method: MapMethod) -> Tuple[np.ndarray, MapMethod]:
    """
    Return 2D coordinates and the method actually used.

    UMAP may fall back to PCA when the sample is too small.
    """
    if method == 'pca':
        return _embed_pca(matrix), 'pca'
    if method == 'umap':
        if matrix.shape[0] < 3:
            return _embed_pca(matrix), 'pca'
        return _embed_umap(matrix), 'umap'
    raise ValueError(f'Unknown map method: {method!r}')


def build_component_map(
    rows: Sequence[Mapping[str, Any]],
    *,
    basis: MapBasis,
    method: MapMethod,
) -> Dict[str, Any]:
    """
    Build a map payload from identity+descriptor rows.

    Each row should provide ``_id`` and ``descriptors``; optional display
    fields ``name``, ``type``, ``catalog_number``, ``color`` are passed through.
    """
    total = len(rows)
    ids: List[str] = []
    metas: List[Dict[str, Any]] = []
    vectors: List[np.ndarray] = []

    for row in rows:
        descriptors = row.get('descriptors') or {}
        if not isinstance(descriptors, Mapping):
            continue
        feature = extract_feature(descriptors, basis)
        if feature is None:
            continue
        identity_id = str(row.get('_id') or '')
        if not identity_id:
            continue
        ids.append(identity_id)
        vectors.append(feature)
        metas.append({
            'id': identity_id,
            'name': row.get('name'),
            'type': row.get('type'),
            'catalog_number': row.get('catalog_number'),
            'color': row.get('color'),
        })

    displayed = len(vectors)
    if displayed == 0:
        coords = np.zeros((0, 2), dtype=np.float64)
        used_method: MapMethod = method if method == 'pca' else 'pca'
    else:
        matrix = np.vstack(vectors)
        coords, used_method = embed_matrix(matrix, method)

    points: List[Dict[str, Any]] = []
    for meta, (x, y) in zip(metas, coords):
        points.append({
            **meta,
            'x': float(x),
            'y': float(y),
        })

    return {
        'basis': basis,
        'basis_label': basis_label(basis),
        'method': used_method,
        'requested_method': method,
        'total': total,
        'displayed': displayed,
        'points': points,
    }


def payload_from_cache_doc(doc: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip Mongo bookkeeping and mark the payload as cached."""
    return {
        'basis': doc['basis'],
        'basis_label': doc.get('basis_label') or basis_label(doc['basis']),
        'method': doc['method'],
        'requested_method': doc.get('requested_method', doc['method']),
        'total': int(doc.get('total', 0)),
        'displayed': int(doc.get('displayed', 0)),
        'points': list(doc.get('points') or []),
        'cached': True,
        'source': 'cache',
        'computed_at': doc.get('computed_at'),
    }


def annotate_live_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Mark a freshly computed payload as live (uncached)."""
    out = dict(payload)
    out['cached'] = False
    out['source'] = 'live'
    out['computed_at'] = None
    return out
