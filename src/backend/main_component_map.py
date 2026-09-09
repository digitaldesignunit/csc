#!/usr/bin/env python3.9
"""
Precompute Component Map layouts (PCA + UMAP) into ``component_map_cache``.

Runs as a cron job so the FastAPI ``GET /identities/map`` route can serve
UMAP layouts without computing them on request.

Default catalog scope matches the Component Map page:
    consumed_filter=active, validated=True (validated=1).

Usage:
    python main_component_map.py
    python main_component_map.py --basis scalars --method umap
    python main_component_map.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Dict, List, Optional, Sequence

from pymongo import AsyncMongoClient

from utility import (
    create_logging_timestamp as logts,
    get_current_timestamp_z,
    get_db_connectionstring,
)
from apps.catalog.api.identity_filters import (
    build_identity_match_stage,
    build_snapshot_match_stage,
)
from apps.catalog.api.identity_query import build_list_pipeline
from apps.catalog.component_map import (
    MAP_BASES,
    MAP_METHODS,
    MapBasis,
    MapMethod,
    build_component_map,
    cache_doc_id,
    map_rows_project_stage,
)


def log(message: str, prefix: str = 'COMPONENT_MAP') -> None:
    print(f'[{prefix}] {logts()} {message}')


async def load_map_rows(
    identities_col,
    snapshots_collection: str,
) -> List[Dict[str, Any]]:
    """Active + validated identity rows with current-snapshot descriptors."""
    pipeline = build_list_pipeline(
        snapshots_collection=snapshots_collection,
        identity_match=build_identity_match_stage(consumed_filter='active'),
        snapshot_match=build_snapshot_match_stage(validated=1),
        sortkey='_id',
        sort_order=1,
        page=0,
        size=0,
        include_username=False,
        current_user_id=None,
        reserved_filter=None,
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
        'consumed_filter': 'active',
        'validated': 1,
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
    log(f'Loaded {len(rows)} active validated components')

    stored = 0
    for basis in bases:
        for method in methods:
            log(f'Computing basis={basis} method={method}…')
            try:
                payload = await asyncio.to_thread(
                    build_component_map,
                    rows,
                    basis=basis,
                    method=method,
                )
            except Exception as exc:
                log(
                    f'Failed basis={basis} method={method}: {exc}',
                    prefix='ERROR',
                )
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


async def run(
    *,
    bases: Sequence[MapBasis],
    methods: Sequence[MapMethod],
    dry_run: bool,
) -> int:
    log('-' * 80)
    log(
        f'Starting component map cache '
        f'(bases={list(bases)}, methods={list(methods)}, dry_run={dry_run})'
    )
    client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
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
        stored = await compute_and_store(
            identities_col=identities,
            snapshots_collection=snapshots.name,
            cache_col=cache,
            bases=bases,
            methods=methods,
            dry_run=dry_run,
        )
        log(f'Summary: layouts_written={stored}')
    except Exception as exc:
        log(f'Error during component map cache: {exc}', prefix='ERROR')
        import traceback
        traceback.print_exc()
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
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    bases: Sequence[MapBasis] = tuple(args.basis) if args.basis else MAP_BASES
    methods: Sequence[MapMethod] = (
        tuple(args.method) if args.method else MAP_METHODS
    )
    try:
        asyncio.run(run(bases=bases, methods=methods, dry_run=args.dry_run))
    except Exception:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
