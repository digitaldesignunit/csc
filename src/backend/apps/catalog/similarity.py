#!/usr/bin/env python3.13
"""
True similarity: the nearest pieces in the full descriptor space (decision
8.174), not on the 2D map.

For each basis of the map (``radial_signature``, ``scalars``, ``hks``) the
feature vectors of every piece that has the descriptor are stacked into one
matrix and each dimension is standardised (z-score) over the catalog; a
dimension without variance is left at 0. The matrix is stored, as float32 and
with the ids of its rows, next to the map layouts in ``component_map_cache``
(document ``knn:<basis>``) by the cron ``main_component_map.py``; the API loads
it once per version and keeps it in memory (about 2300 pieces x 240 numbers is
2 MB). A query is a Euclidean distance from one row to the others, restricted
to the pieces the caller may see that pass the filters: the filters come
first, then the ranking, so "similar and can hold X and within 50 km" returns
the k nearest that pass.

The pure parts (standardising, the matrix document, the ranking) are here;
the route that reads the visibility and the filters is in ``catalog_list.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from bson import Binary

from apps.catalog.component_map import (
    CACHE_COLLECTION,
    MAP_BASES,
    MapBasis,
    extract_feature,
)

SIMILARITY_BASES = MAP_BASES
DEFAULT_BASIS: MapBasis = 'radial_signature'
MAX_NEIGHBOURS = 50


def knn_doc_id(basis: str) -> str:
    """The ``_id`` of the stored matrix of a basis in the cache collection."""
    return f'knn:{basis}'


@dataclass
class FeatureMatrix:
    """The standardised feature vectors of one basis."""
    basis: str
    ids: List[str]
    z: np.ndarray            # float32, one row per id
    mean: np.ndarray         # float64, per dimension, over the catalog
    std: np.ndarray          # float64, per dimension; 1 where it was 0
    computed_at: Optional[str] = None
    build_id: Optional[str] = None     # one per build: tells one version from the next
    flat: Optional[np.ndarray] = None  # bool per dimension: no variance, 0 for every row

    def __post_init__(self) -> None:
        self.index: Dict[str, int] = {i: n for n, i in enumerate(self.ids)}
        if self.flat is None:
            self.flat = np.zeros(self.z.shape[1] if self.z.ndim == 2 else 0, dtype=bool)

    @property
    def dim(self) -> int:
        return int(self.z.shape[1]) if self.z.ndim == 2 else 0

    def vector_of(self, identity_id: str) -> Optional[np.ndarray]:
        row = self.index.get(identity_id)
        return None if row is None else self.z[row]


def standardise(vectors: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The z-scores of the columns of a matrix, and the mean and standard
    deviation used. A column without variance (every value the same) has
    standard deviation 1 here, so its z-score is 0 and it adds nothing to a
    distance; no division by zero."""
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise ValueError('standardise needs a matrix with at least one row')
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    flat = ~(std > 1e-12)
    std = np.where(flat, 1.0, std)
    z = (matrix - mean) / std
    z[:, flat] = 0.0               # exactly 0, not the rounding left of x - mean
    return z.astype(np.float32), mean, std


def flat_columns(vectors: np.ndarray) -> np.ndarray:
    """The columns of a matrix that ``standardise`` leaves at 0 (no variance)."""
    return ~(np.asarray(vectors, dtype=np.float64).std(axis=0) > 1e-12)


def standardise_vector(vector: np.ndarray, mean: np.ndarray, std: np.ndarray,
                       flat: Optional[np.ndarray] = None) -> np.ndarray:
    """One feature vector in the space of a stored matrix. The columns without
    variance in the catalog are 0 here too, as in every row of the matrix, so
    a piece added after the build does not get a constant added to all its
    distances."""
    z = (np.asarray(vector, dtype=np.float64) - mean) / std
    if flat is not None and flat.any():
        z[flat] = 0.0
    return z.astype(np.float32)


def build_feature_matrix(rows: Iterable[Mapping[str, Any]], basis: MapBasis,
                         computed_at: Optional[str] = None
                         ) -> Optional[FeatureMatrix]:
    """The matrix of a basis from rows with ``_id`` and ``descriptors`` (the
    rows of the map); None when no row has the descriptor."""
    ids: List[str] = []
    vectors: List[np.ndarray] = []
    for row in rows:
        descriptors = row.get('descriptors')
        identity_id = str(row.get('_id') or '')
        if not identity_id or not isinstance(descriptors, Mapping):
            continue
        feature = extract_feature(descriptors, basis)
        if feature is None:
            continue
        ids.append(identity_id)
        vectors.append(feature)
    if not vectors:
        return None
    stacked = np.vstack(vectors)
    z, mean, std = standardise(stacked)
    return FeatureMatrix(basis, ids, z, mean, std, computed_at,
                         build_id=uuid.uuid4().hex, flat=flat_columns(stacked))


def matrix_to_doc(matrix: FeatureMatrix, computed_at: str) -> Dict[str, Any]:
    """The cache document: the rows as little-endian float32 bytes."""
    return {
        '_id': knn_doc_id(matrix.basis),
        'kind': 'knn',
        'basis': matrix.basis,
        'n': len(matrix.ids),
        'dim': matrix.dim,
        'ids': matrix.ids,
        'matrix': Binary(np.ascontiguousarray(matrix.z, dtype='<f4').tobytes()),
        'mean': [float(v) for v in matrix.mean],
        'std': [float(v) for v in matrix.std],
        'flat': [int(i) for i in np.nonzero(matrix.flat)[0]],
        'computed_at': computed_at,
        'build_id': matrix.build_id,
    }


def matrix_from_doc(doc: Mapping[str, Any]) -> FeatureMatrix:
    n, dim = int(doc['n']), int(doc['dim'])
    z = np.frombuffer(bytes(doc['matrix']), dtype='<f4').reshape(n, dim)
    flat = np.zeros(dim, dtype=bool)
    flat[[int(i) for i in doc.get('flat') or []]] = True   # absent in an older build: none
    return FeatureMatrix(
        basis=str(doc['basis']), ids=[str(i) for i in doc['ids']],
        z=z.astype(np.float32, copy=False),
        mean=np.asarray(doc['mean'], dtype=np.float64),
        std=np.asarray(doc['std'], dtype=np.float64),
        computed_at=doc.get('computed_at'), build_id=doc.get('build_id'),
        flat=flat)


def nearest(matrix: FeatureMatrix, query: np.ndarray,
            candidates: Optional[Iterable[str]], k: int,
            exclude: Optional[str] = None) -> Tuple[List[Tuple[str, float]], int]:
    """The ``k`` nearest rows to ``query`` among ``candidates`` (every row
    when None) in Euclidean distance of the standardised space, nearest first;
    ties by id so the answer is stable. The piece ``exclude`` is never one of
    them. Also returns how many candidates were ranked."""
    if candidates is None:
        rows = np.arange(len(matrix.ids))
    else:
        rows = np.fromiter(
            (matrix.index[i] for i in candidates if i in matrix.index),
            dtype=np.int64)
    if exclude is not None and exclude in matrix.index:
        rows = rows[rows != matrix.index[exclude]]
    if rows.size == 0 or k < 1:
        return [], int(rows.size)
    delta = matrix.z[rows] - np.asarray(query, dtype=np.float32)
    distances = np.sqrt(np.einsum('ij,ij->i', delta, delta, dtype=np.float64))
    # all rows are sorted by (distance, id) when few; else the k smallest first
    if rows.size > k * 4:
        keep = np.argpartition(distances, k - 1)[:k]
        # a tie at the edge could drop a smaller id: widen to every row that
        # ties the k-th distance
        edge = distances[keep].max()
        keep = np.nonzero(distances <= edge)[0]
    else:
        keep = np.arange(rows.size)
    ranked = sorted(((float(distances[n]), matrix.ids[int(rows[n])])
                     for n in keep))[:k]
    return [(identity_id, distance) for distance, identity_id in ranked], \
        int(rows.size)


# THE CACHE IN MEMORY ---------------------------------------------------------
class MatrixStore:
    """The matrices of the bases, loaded from the cache collection once per
    version (the ``build_id`` of the stored document): a request reads one
    small field, not the matrix."""

    def __init__(self) -> None:
        self._loaded: Dict[str, FeatureMatrix] = {}

    async def get(self, collection, basis: str) -> Optional[FeatureMatrix]:
        head = await collection.find_one(
            {'_id': knn_doc_id(basis)}, {'build_id': 1})
        if head is None:
            self._loaded.pop(basis, None)
            return None
        have = self._loaded.get(basis)
        if (have is not None and head.get('build_id') is not None
                and have.build_id == head.get('build_id')):
            return have
        doc = await collection.find_one({'_id': knn_doc_id(basis)})
        if doc is None:
            return None
        self._loaded[basis] = matrix_from_doc(doc)
        return self._loaded[basis]


STORE = MatrixStore()


async def store_matrix(cache_col, matrix: FeatureMatrix, computed_at: str) -> None:
    await cache_col.replace_one(
        {'_id': knn_doc_id(matrix.basis)},
        matrix_to_doc(matrix, computed_at), upsert=True)


__all__ = [
    'CACHE_COLLECTION', 'DEFAULT_BASIS', 'FeatureMatrix', 'MAX_NEIGHBOURS',
    'SIMILARITY_BASES', 'STORE', 'build_feature_matrix', 'knn_doc_id',
    'flat_columns', 'matrix_from_doc', 'matrix_to_doc', 'nearest', 'standardise',
    'standardise_vector', 'store_matrix',
]
