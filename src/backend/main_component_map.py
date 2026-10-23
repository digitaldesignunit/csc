#!/usr/bin/env python3.13
"""
Precompute Component Map layouts (PCA + UMAP) and the similarity matrices
into ``component_map_cache``.

Runs as a cron job so the FastAPI ``GET /identities/map`` route can serve
UMAP layouts without computing them on request, and the ``similar`` route and
the MCP ``similar_components`` tool can rank by descriptor distance (decision
8.174): for each basis one matrix of the standardised feature vectors of every
piece that has the descriptor (``knn:<basis>``, see ``apps/catalog/similarity.py``).
The matrix is fixed until the next run: a piece added or reshaped since is ranked
by its old vector, or not at all, until then.

Default catalog scope matches the Component Map page: published current
snapshots of pieces in circulation (``CatalogFilters()`` defaults).

Usage:
    python main_component_map.py
    python main_component_map.py --basis scalars --method umap
    python main_component_map.py --dry-run
    python main_component_map.py --knn-only     # only the similarity matrices
    python main_component_map.py --no-knn       # only the layouts
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional, Sequence

from pymongo import AsyncMongoClient

from logging_setup import configure as configure_logging, get_logger
import read_only
from settings import get_settings
from utility import (
    get_current_timestamp_z,
    get_db_connectionstring,
)
from apps.catalog.api.identity_filters import CatalogFilters
from apps.catalog.api.identity_query import build_list_pipeline
from apps.catalog.similarity import build_feature_matrix, store_matrix
from apps.catalog.component_map import (
    MAP_BASES,
    MAP_METHODS,
    MapBasis,
    MapMethod,
    build_component_map,
    cache_doc_id,
    map_rows_project_stage,
)


_log = get_logger(__name__)
_LEVELS = {'ERROR': logging.ERROR, 'WARNING': logging.WARNING}


def log(message: str, prefix: str = 'COMPONENT_MAP') -> None:
    """One line of the run; ``prefix`` ERROR / WARNING sets the level."""
    _log.log(_LEVELS.get(prefix, logging.INFO), '%s', message)


async def load_map_rows(
    identities_col,
    snapshots_collection: str,
    scope: Optional[CatalogFilters] = None,
) -> List[Dict[str, Any]]:
    """Rows with current-snapshot descriptors: the default scope (published,
    in circulation) unless a scope is given."""
    scope = scope or CatalogFilters()
    pipeline = build_list_pipeline(
        snapshots_collection=snapshots_collection,
        identity_match=scope.identity_match(),
        snapshot_match=scope.snapshot_match(),
        sortkey='_id',
        sort_order=1,
        page=0,
        size=0,
        include_username=False,
        current_user_id=None,
        reserved_filter=None,
        snapshot_view='map',
    )
    pipeline.append(map_rows_project_stage())
    cursor = await identities_col.aggregate(pipeline)
    return [doc async for doc in cursor]


async def upsert_map_cache(
    cache_col,
    *,
    payload: Dict[str, Any],
    basis: MapBasis,
    method: MapMethod,
    dry_run: bool,
) -> str:
    doc_id = cache_doc_id(basis, method)
    now = get_current_timestamp_z()
    doc = {
        '_id': doc_id,
        'basis': payload['basis'],
        'basis_label': payload['basis_label'],
        'method': payload['method'],
        'requested_method': payload['requested_method'],
        'total': payload['total'],
        'displayed': payload['displayed'],
        'points': payload['points'],
        'circulation': 'active',
        'status': 'published',
        'computed_at': now,
    }
    if dry_run:
        log(
            f'[dry-run] would upsert {doc_id} '
            f'(displayed={doc["displayed"]}/{doc["total"]}, '
            f'method={doc["method"]})'
        )
        return doc_id

    await cache_col.replace_one({'_id': doc_id}, doc, upsert=True)
    log(
        f'Upserted {doc_id} '
        f'(displayed={doc["displayed"]}/{doc["total"]}, method={doc["method"]})'
    )
    return doc_id


async def compute_and_store(
    *,
    identities_col,
    snapshots_collection: str,
    cache_col,
    bases: Sequence[MapBasis],
    methods: Sequence[MapMethod],
    dry_run: bool,
) -> int:
    rows = await load_map_rows(identities_col, snapshots_collection)
    log(f'Loaded {len(rows)} published components in circulation')

    stored = 0
    for basis in bases:
        for method in methods:
            log(f'Computing basis={basis} method={method}...')
            try:
                payload = await asyncio.to_thread(
                    build_component_map,
                    rows,
                    basis=basis,
                    method=method,
                )
            except Exception:
                _log.exception('Failed basis=%s method=%s', basis, method)
                continue
            await upsert_map_cache(
                cache_col,
                payload=payload,
                basis=basis,
                method=method,
                dry_run=dry_run,
            )
            stored += 1
    return stored


# every piece with a current version: the matrices serve any filter, the
# visibility and the filters are applied when a query ranks (8.174)
KNN_SCOPE = dict(status='any', circulation='all', include_withdrawn=True)


async def compute_and_store_knn(
    *,
    identities_col,
    snapshots_collection: str,
    cache_col,
    bases: Sequence[MapBasis],
    dry_run: bool,
) -> int:
    """The similarity matrix of each basis, standardised over the catalog."""
    rows = await load_map_rows(identities_col, snapshots_collection,
                               CatalogFilters(**KNN_SCOPE))
    log(f'Loaded {len(rows)} components for the similarity matrices')
    now = get_current_timestamp_z()
    stored = 0
    for basis in bases:
        matrix = await asyncio.to_thread(
            build_feature_matrix, rows, basis, now)
        if matrix is None:
            log(f'No component has the {basis} descriptor: no matrix',
                'WARNING')
            continue
        if dry_run:
            log(f'[dry-run] would upsert knn:{basis} '
                f'({len(matrix.ids)} rows x {matrix.dim})')
        else:
            await store_matrix(cache_col, matrix, now)
            log(f'Upserted knn:{basis} ({len(matrix.ids)} rows x {matrix.dim})')
        stored += 1
    return stored


async def run(
    *,
    bases: Sequence[MapBasis],
    methods: Sequence[MapMethod],
    dry_run: bool,
    layouts: bool = True,
    knn: bool = True,
) -> int:
    log(
        f'Starting component map cache '
        f'(bases={list(bases)}, methods={list(methods)}, dry_run={dry_run})'
    )
    client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
        maxPoolSize=20,
    )
    stored = 0
    try:
        await client.aconnect()
        await client.admin.command('ping')
        log('Connected to MongoDB')
        db = client['csc']
        identities = db['component_identities']
        snapshots = db['component_snapshots']
        cache = db['component_map_cache']
        stored = 0
        if layouts:
            stored = await compute_and_store(
                identities_col=identities,
                snapshots_collection=snapshots.name,
                cache_col=cache,
                bases=bases,
                methods=methods,
                dry_run=dry_run,
            )
        matrices = 0
        if knn:
            matrices = await compute_and_store_knn(
                identities_col=identities,
                snapshots_collection=snapshots.name,
                cache_col=cache,
                bases=bases,
                dry_run=dry_run,
            )
        log(f'Summary: layouts_written={stored} matrices_written={matrices}')
    except Exception:
        _log.exception('Error during component map cache')
        raise
    finally:
        await client.close()
        log('Closed MongoDB connection')
    return stored


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Precompute Component Map PCA/UMAP layouts into MongoDB.',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Compute but do not write cache documents.',
    )
    parser.add_argument(
        '--basis',
        action='append',
        choices=list(MAP_BASES),
        help='Limit to one basis (repeatable). Default: all bases.',
    )
    parser.add_argument(
        '--method',
        action='append',
        choices=list(MAP_METHODS),
        help='Limit to one method (repeatable). Default: pca and umap.',
    )
    only = parser.add_mutually_exclusive_group()
    only.add_argument(
        '--knn-only', action='store_true',
        help='Only the similarity matrices, no layouts.',
    )
    only.add_argument(
        '--no-knn', action='store_true',
        help='Only the layouts, no similarity matrices.',
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    configure_logging(get_settings())
    args = _parse_args(argv)
    # the read-only flag (decision 8.154): the job writes, so it waits
    if read_only.skip_job(log, 'component map', args.dry_run):
        return 0
    bases: Sequence[MapBasis] = tuple(args.basis) if args.basis else MAP_BASES
    methods: Sequence[MapMethod] = (
        tuple(args.method) if args.method else MAP_METHODS
    )
    try:
        asyncio.run(run(bases=bases, methods=methods, dry_run=args.dry_run,
                        layouts=not args.knn_only, knn=not args.no_knn))
    except Exception:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
