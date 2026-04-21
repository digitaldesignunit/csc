#!/usr/bin/env python3.9
"""
Descriptor computation maintenance script.

Thin orchestrator over the descriptor registry. Can run in two modes:

    1. Cron worker (default): processes one component per invocation. This
       is what the `descriptors_simple_cronjob.ini` entry uses.
    2. Batch backfill (``--all`` / ``--limit N``): loops over every
       component that is missing an applicable descriptor, in a single
       MongoDB connection.

Responsibilities of this module, and nothing else:
    1. Connect to MongoDB.
    2. Ask the registry for a component that is missing at least one
       applicable descriptor.
    3. Load geometry via `apps.descriptors.geometry.load_component_mesh`.
    4. Iterate the specs that apply to this component and are missing,
       running each spec's compute function via the registry.
    5. Merge the results back into the component's ``descriptors`` field.

All per-descriptor knowledge (parameters, applicability, output keys,
compute function) lives in `apps/descriptors/specs.py`. To add a new
descriptor, add one `DescriptorSpec` there; no changes are needed here.

Usage:
    python main_descriptors_simple.py                # one component
    python main_descriptors_simple.py --all          # every missing
    python main_descriptors_simple.py --limit 50     # up to 50
    python main_descriptors_simple.py --all --dry-run
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import argparse
import asyncio
import random
import sys
from typing import Any, Dict, Iterable, List, Optional, Set

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo import AsyncMongoClient

# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import (
    create_logging_timestamp as logts,
    get_current_timestamp_z,
    get_db_connectionstring,
    get_geometry_directory,
)
from apps.descriptors.geometry import load_component_mesh
from apps.descriptors.registry import (
    DescriptorSpec,
    build_missing_query,
    collect_output_keys,
    compute_descriptor,
    missing_specs_for,
)
from apps.descriptors.specs import ALL_SPECS


# LOGGING --------------------------------------------------------------------

def log(message: str, prefix: str = 'DESCRIPTORS') -> None:
    """Print a timestamped log message."""
    print(f'[{prefix}] {logts()} {message}')


def _spec_logger(spec: DescriptorSpec):
    """Return a compute-scoped logger that indents and tags lines."""
    return lambda msg: log(f'    [{spec.name}] {msg}')


# DATABASE HELPERS -----------------------------------------------------------

async def find_component_with_missing_descriptors(
    mongodb_components,
    specs: List[DescriptorSpec],
    exclude_ids: Optional[Iterable[str]] = None,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """Find one component missing at least one applicable descriptor.

    ``exclude_ids`` lets the batch loop skip components it has already
    visited this run (needed in ``--dry-run`` where nothing is written,
    and as a safety net against infinite loops if an update silently
    fails to take effect).
    """
    query = build_missing_query(specs)
    if exclude_ids:
        query = {**query, '_id': {'$nin': list(exclude_ids)}}
    if dry_run:
        components = await mongodb_components.find(query).to_list(None)
        if not components:
            return None
        return random.choice(components)
    return await mongodb_components.find_one(query)


async def update_component_descriptors(
    mongodb_components,
    component_id: str,
    descriptors: Dict[str, Any],
) -> bool:
    """
    Merge new descriptor values into the component's ``descriptors`` field.
    """
    try:
        component = await mongodb_components.find_one({'_id': component_id})
        if not component:
            log(f'Component {component_id} not found', prefix='ERROR')
            return False

        current = component.get('descriptors') or {}
        merged = {**current, **descriptors}

        result = await mongodb_components.update_one(
            {'_id': component_id},
            {
                '$set': {
                    'descriptors': merged,
                    'lastmodified': get_current_timestamp_z(),
                }
            },
        )
        if result.modified_count > 0:
            log(f'Updated descriptors for component {component_id}')
            return True
        log(f'No changes made to component {component_id}', prefix='WARNING')
        return False
    except Exception as exc:
        log(f'Failed to update component {component_id}: {exc}',
            prefix='ERROR')
        return False


# CORE EXECUTION -------------------------------------------------------------

def run_missing_specs_on_component(
    component: Dict[str, Any],
    geometry_dir: Optional[str],
    specs: List[DescriptorSpec],
) -> Dict[str, Any]:
    """Execute every applicable+missing spec against the component.

    Returns a flat mapping of ``descriptors.*`` field names to values
    ready to merge into the component document. Keys whose spec explicitly
    failed are included with a None value; keys whose spec simply could
    not run (e.g. missing mesh) are omitted.
    """
    missing = missing_specs_for(component, specs)
    if not missing:
        log('No missing applicable descriptors on this component')
        return {}

    expected_keys = collect_output_keys(missing)
    log(f'Missing applicable descriptors: {", ".join(expected_keys)}')

    # Lazily load mesh - only if at least one spec needs it. Keeps pure
    # planar components (radial-only) from paying for mesh reconstruction.
    needs_mesh = any(spec.requires_mesh for spec in missing)
    mesh = None
    if needs_mesh:
        log('Loading geometry...')
        mesh = load_component_mesh(
            component,
            geometry_dir=geometry_dir,
            logger=lambda msg: log(f'    [geometry] {msg}'),
        )
        if mesh is None:
            log('Mesh load failed; mesh-dependent specs will be skipped',
                prefix='WARNING')

    log('Computing descriptors...')
    results: Dict[str, Any] = {}
    for spec in missing:
        spec_results = compute_descriptor(
            spec=spec,
            component=component,
            mesh=mesh,
            log=_spec_logger(spec),
        )
        results.update(spec_results)
    return results


async def _process_one(
    mongodb_components,
    geometry_dir: Optional[str],
    specs: List[DescriptorSpec],
    seen_ids: Set[str],
    dry_run: bool,
) -> Optional[bool]:
    """Process a single missing component.

    Returns:
        True  - component updated (or would be, in dry-run).
        False - component found but nothing was computed / no changes.
        None  - no eligible component left; the batch loop should stop.
    """
    component = await find_component_with_missing_descriptors(
        mongodb_components, specs,
        exclude_ids=seen_ids, dry_run=dry_run,
    )
    if not component:
        return None

    component_id = str(component['_id'])
    seen_ids.add(component_id)

    log(f'Found component: {component_id}')
    log(f'  Name: {component.get("name", "Unnamed Component")}')
    log(f'  Type: {component.get("type", "unknown")}')

    descriptors = run_missing_specs_on_component(
        component=component,
        geometry_dir=geometry_dir,
        specs=specs,
    )
    if not descriptors:
        log('No descriptors were computed', prefix='WARNING')
        return False

    if dry_run:
        log(f'DRY RUN: Would update component {component_id} '
            f'with descriptors: {list(descriptors.keys())}')
        return True
    return await update_component_descriptors(
        mongodb_components, component_id, descriptors
    )


async def compute_descriptors(
    dry_run: bool = False,
    max_iterations: Optional[int] = 1,
) -> int:
    """Find components with missing descriptors, compute them, persist.

    Args:
        dry_run: if True, never write to MongoDB.
        max_iterations: upper bound on components processed in this run.
            ``None`` means "until no component needs work".

    Returns:
        Number of components for which new descriptors were written
        (or would be written, in dry-run).
    """
    log('Starting descriptor computation...')
    if dry_run:
        log('DRY RUN MODE - No database updates will be made')
    if max_iterations is None:
        log('Batch mode: processing every component with missing descriptors')
    elif max_iterations != 1:
        log(f'Batch mode: processing up to {max_iterations} components')
    log('-' * 80)

    client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
    )
    updated = 0
    visited = 0
    seen_ids: Set[str] = set()
    try:
        await client.aconnect()
        await client.admin.command('ping')
        log('Connected to MongoDB')

        mongodb_components = client['csc']['components']
        geometry_dir = get_geometry_directory()

        registered_keys = collect_output_keys(ALL_SPECS)
        log(f'Registered descriptor keys: {", ".join(registered_keys)}')

        while max_iterations is None or visited < max_iterations:
            if visited > 0:
                log('-' * 80)
            result = await _process_one(
                mongodb_components=mongodb_components,
                geometry_dir=geometry_dir,
                specs=ALL_SPECS,
                seen_ids=seen_ids,
                dry_run=dry_run,
            )
            if result is None:
                if visited == 0:
                    log('No components with missing descriptors found')
                else:
                    log('No components with missing descriptors left')
                break
            visited += 1
            if result:
                updated += 1

        if visited > 0:
            log('-' * 80)
            log(f'Summary: visited={visited}, updated={updated}')
    except Exception as exc:
        log(f'Error during descriptor computation: {exc}', prefix='ERROR')
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        log('Closed MongoDB connection')

    return updated


# MAIN EXECUTION --------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Compute missing descriptors for CSC components.',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Do not write to MongoDB; only report what would change.',
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--all', dest='process_all', action='store_true',
        help='Process every component with missing descriptors.',
    )
    group.add_argument(
        '--limit', type=int, default=None, metavar='N',
        help='Process at most N components (default: 1, i.e. cron mode).',
    )
    return parser.parse_args(argv)


if __name__ == '__main__':
    args = _parse_args()
    if args.process_all:
        max_iter: Optional[int] = None
    elif args.limit is not None:
        if args.limit <= 0:
            print('--limit must be a positive integer', file=sys.stderr)
            sys.exit(2)
        max_iter = args.limit
    else:
        max_iter = 1

    updated_count = asyncio.run(
        compute_descriptors(dry_run=args.dry_run, max_iterations=max_iter)
    )
    if updated_count > 0:
        log(f'Descriptor computation completed: {updated_count} component(s) '
            f'updated')
        sys.exit(0)
    log('No work done or computation failed')
    sys.exit(1)
