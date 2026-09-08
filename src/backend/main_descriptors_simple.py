#!/usr/bin/env python3.9
"""
Descriptor computation maintenance script.

Thin orchestrator over the descriptor registry. Can run in three modes:

    1. Cron worker (default): processes one snapshot per invocation. This
       is what the `descriptors_simple_cronjob.ini` entry uses.
    2. Batch backfill (``--all`` / ``--limit N``): loops over every
       snapshot that is missing an applicable descriptor, in a single
       MongoDB connection.
    3. Full recompute (``--recompute``): walks every snapshot in the
       database, one at a time, and overwrites every applicable descriptor.
       Use after changing how a descriptor is computed.

Responsibilities of this module, and nothing else:
    1. Connect to MongoDB (`component_snapshots` + `component_identities`).
    2. Ask the registry for a snapshot that is missing at least one
       applicable descriptor (or, in ``--recompute``, the next snapshot).
    3. Load geometry via `apps.descriptors.geometry.load_snapshot_mesh`.
    4. Iterate the specs that apply to this snapshot (missing, or all of
       them when recomputing), running each spec's compute function via
       the registry.
    5. Merge the results back into the snapshot's ``descriptors`` field.

All per-descriptor knowledge (parameters, applicability, output keys,
compute function) lives in `apps.descriptors/specs.py`. To add a new
descriptor, add one `DescriptorSpec` there; no changes are needed here.

Usage:
    python main_descriptors_simple.py                     # one snapshot
    python main_descriptors_simple.py --all               # every missing
    python main_descriptors_simple.py --limit 50          # up to 50 missing
    python main_descriptors_simple.py --all --dry-run
    python main_descriptors_simple.py --recompute         # overwrite all
    python main_descriptors_simple.py --recompute --limit 10 --dry-run
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import argparse
import asyncio
import random
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo import AsyncMongoClient

# LOCAL MODULE IMPORTS --------------------------------------------------------
from utility import (
    create_logging_timestamp as logts,
    get_current_timestamp_z,
    get_db_connectionstring,
    get_snapshot_meshes_directory,
    get_snapshot_point_clouds_directory,
)
from apps.descriptors.geometry import load_snapshot_mesh
from apps.descriptors.registry import (
    DescriptorSpec,
    applicable_specs_for,
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


# SNAPSHOT ASSEMBLY ----------------------------------------------------------

def assemble_descriptor_document(
    identity: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge identity metadata into a snapshot for descriptor evaluation.

    Descriptor specs expect a single document with ``type`` (from the
    identity) and snapshot geometry / frames / descriptors. Inline mesh
    keys are normalized to legacy ``v``/``f`` where needed.
    """
    doc = dict(snapshot)
    doc['type'] = identity.get('type')
    doc['identity_id'] = identity.get('_id')

    geometry = dict(snapshot.get('geometry') or {})
    extrusions = geometry.get('extrusions') or []
    if extrusions and not geometry.get('extrusion'):
        geometry['extrusion'] = extrusions[0]

    meshes = geometry.get('meshes') or []
    if meshes:
        normalized_meshes = []
        for mesh_data in meshes:
            entry = dict(mesh_data)
            if entry.get('vertices') and not entry.get('v'):
                entry['v'] = entry['vertices']
            if entry.get('faces') and not entry.get('f'):
                entry['f'] = entry['faces']
            normalized_meshes.append(entry)
        geometry['meshes'] = normalized_meshes

    doc['geometry'] = geometry
    return doc


# DATABASE HELPERS -----------------------------------------------------------

async def find_snapshot_with_missing_descriptors(
    mongodb_snapshots,
    specs: List[DescriptorSpec],
    exclude_ids: Optional[Iterable[str]] = None,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """Find one snapshot missing at least one descriptor key.

    Applicability (e.g. component ``type`` on the parent identity) is
    checked in memory after the identity is loaded.
    """
    query = build_missing_query(specs, include_applicability=False)
    if exclude_ids:
        query = {**query, '_id': {'$nin': list(exclude_ids)}}
    if dry_run:
        snapshots = await mongodb_snapshots.find(query).to_list(None)
        if not snapshots:
            return None
        return random.choice(snapshots)
    return await mongodb_snapshots.find_one(query)


async def load_identity_for_snapshot(
    mongodb_identities,
    snapshot: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Load the parent identity for a snapshot."""
    identity_id = snapshot.get('identity_id')
    if not identity_id:
        return None
    return await mongodb_identities.find_one({'_id': identity_id})


async def update_snapshot_descriptors(
    mongodb_snapshots,
    snapshot_id: str,
    descriptors: Dict[str, Any],
) -> bool:
    """
    Merge new descriptor values into the snapshot's ``descriptors`` field.
    """
    try:
        snapshot = await mongodb_snapshots.find_one({'_id': snapshot_id})
        if not snapshot:
            log(f'Snapshot {snapshot_id} not found', prefix='ERROR')
            return False

        current = snapshot.get('descriptors') or {}
        merged = {**current, **descriptors}

        result = await mongodb_snapshots.update_one(
            {'_id': snapshot_id},
            {
                '$set': {
                    'descriptors': merged,
                    'lastmodified': get_current_timestamp_z(),
                }
            },
        )
        if result.modified_count > 0:
            log(f'Updated descriptors for snapshot {snapshot_id}')
            return True
        log(f'No changes made to snapshot {snapshot_id}', prefix='WARNING')
        return False
    except Exception as exc:
        log(f'Failed to update snapshot {snapshot_id}: {exc}',
            prefix='ERROR')
        return False


# CORE EXECUTION -------------------------------------------------------------

def run_specs_on_snapshot(
    compute_doc: Dict[str, Any],
    meshes_dir: Optional[str],
    specs: List[DescriptorSpec],
    point_clouds_dir: Optional[str] = None,
    recompute: bool = False,
) -> Dict[str, Any]:
    """Execute applicable specs against a snapshot.

    By default only missing specs run. With ``recompute=True`` every
    applicable spec runs again and overwrites the stored values.
    """
    to_run = (
        applicable_specs_for(compute_doc, specs) if recompute
        else missing_specs_for(compute_doc, specs)
    )
    if not to_run:
        if recompute:
            log('No applicable descriptors on this snapshot')
        else:
            log('No missing applicable descriptors on this snapshot')
        return {}

    expected_keys = collect_output_keys(to_run)
    if recompute:
        log(f'Recomputing descriptors: {", ".join(expected_keys)}')
    else:
        log(f'Missing applicable descriptors: {", ".join(expected_keys)}')

    needs_mesh = any(spec.requires_mesh for spec in to_run)
    mesh = None
    if needs_mesh:
        log('Loading geometry...')
        mesh = load_snapshot_mesh(
            compute_doc,
            meshes_dir=meshes_dir,
            point_clouds_dir=point_clouds_dir,
            logger=lambda msg: log(f'    [geometry] {msg}'),
        )
        if mesh is None:
            log('Mesh load failed; mesh-dependent specs will be skipped',
                prefix='WARNING')

    log('Computing descriptors...')
    results: Dict[str, Any] = {}
    for spec in to_run:
        spec_results = compute_descriptor(
            spec=spec,
            component=compute_doc,
            mesh=mesh,
            log=_spec_logger(spec),
            meshes_dir=meshes_dir,
            point_clouds_dir=point_clouds_dir,
        )
        results.update(spec_results)
    return results


async def _process_snapshot(
    snapshot: Dict[str, Any],
    mongodb_snapshots,
    mongodb_identities,
    meshes_dir: Optional[str],
    specs: List[DescriptorSpec],
    dry_run: bool,
    point_clouds_dir: Optional[str] = None,
    recompute: bool = False,
) -> bool:
    """Compute descriptors for one already-loaded snapshot.

    Returns True if the snapshot was updated (or would be, in dry-run).
    """
    snapshot_id = str(snapshot['_id'])

    identity = await load_identity_for_snapshot(
        mongodb_identities, snapshot)
    if not identity:
        log(f'Snapshot {snapshot_id} has no parent identity', prefix='WARNING')
        return False

    compute_doc = assemble_descriptor_document(identity, snapshot)

    log(f'Found snapshot: {snapshot_id}')
    log(f'  Identity: {identity.get("_id", "unknown")}')
    log(f'  Name: {compute_doc.get("name", "Unnamed Component")}')
    log(f'  Type: {compute_doc.get("type", "unknown")}')
    log(f'  Version: {compute_doc.get("version", "?")}')

    descriptors = run_specs_on_snapshot(
        compute_doc=compute_doc,
        meshes_dir=meshes_dir,
        point_clouds_dir=point_clouds_dir,
        specs=specs,
        recompute=recompute,
    )
    if not descriptors:
        log('No descriptors were computed', prefix='WARNING')
        return False

    if dry_run:
        log(f'DRY RUN: Would update snapshot {snapshot_id} '
            f'with descriptors: {list(descriptors.keys())}')
        return True
    return await update_snapshot_descriptors(
        mongodb_snapshots, snapshot_id, descriptors
    )


async def _process_one(
    mongodb_snapshots,
    mongodb_identities,
    meshes_dir: Optional[str],
    specs: List[DescriptorSpec],
    seen_ids: Set[str],
    dry_run: bool,
    point_clouds_dir: Optional[str] = None,
) -> Optional[bool]:
    """Process a single snapshot missing descriptors.

    Returns:
        True  - snapshot updated (or would be, in dry-run).
        False - snapshot found but nothing was computed / no changes.
        None  - no eligible snapshot left; the batch loop should stop.
    """
    snapshot = await find_snapshot_with_missing_descriptors(
        mongodb_snapshots, specs,
        exclude_ids=seen_ids, dry_run=dry_run,
    )
    if not snapshot:
        return None

    seen_ids.add(str(snapshot['_id']))
    return await _process_snapshot(
        snapshot=snapshot,
        mongodb_snapshots=mongodb_snapshots,
        mongodb_identities=mongodb_identities,
        meshes_dir=meshes_dir,
        specs=specs,
        dry_run=dry_run,
        point_clouds_dir=point_clouds_dir,
        recompute=False,
    )


async def _recompute_all(
    mongodb_snapshots,
    mongodb_identities,
    meshes_dir: Optional[str],
    specs: List[DescriptorSpec],
    dry_run: bool,
    point_clouds_dir: Optional[str],
    max_iterations: Optional[int],
) -> Tuple[int, int]:
    """Walk every snapshot, one at a time, and recompute applicable specs.

    Returns ``(visited, updated)``.
    """
    visited = 0
    updated = 0
    cursor = mongodb_snapshots.find({}).sort('_id', 1)
    async for snapshot in cursor:
        if max_iterations is not None and visited >= max_iterations:
            break
        if visited > 0:
            log('-' * 80)
        result = await _process_snapshot(
            snapshot=snapshot,
            mongodb_snapshots=mongodb_snapshots,
            mongodb_identities=mongodb_identities,
            meshes_dir=meshes_dir,
            specs=specs,
            dry_run=dry_run,
            point_clouds_dir=point_clouds_dir,
            recompute=True,
        )
        visited += 1
        if result:
            updated += 1
    if visited == 0:
        log('No snapshots found in the database')
    return visited, updated


async def compute_descriptors(
    dry_run: bool = False,
    max_iterations: Optional[int] = 1,
    recompute: bool = False,
) -> int:
    """Find snapshots, compute descriptors, persist.

    Args:
        dry_run: if True, never write to MongoDB.
        max_iterations: upper bound on snapshots processed in this run.
            ``None`` means "until no snapshot is left".
        recompute: if True, walk every snapshot and overwrite every
            applicable descriptor. If False, only fill missing keys.

    Returns:
        Number of snapshots for which descriptors were written
        (or would be written, in dry-run).
    """
    log('Starting descriptor computation...')
    if dry_run:
        log('DRY RUN MODE - No database updates will be made')
    if recompute:
        if max_iterations is None:
            log('Recompute mode: overwriting descriptors on every snapshot')
        else:
            log(f'Recompute mode: overwriting descriptors on up to '
                f'{max_iterations} snapshots')
    elif max_iterations is None:
        log('Batch mode: processing every snapshot with missing descriptors')
    elif max_iterations != 1:
        log(f'Batch mode: processing up to {max_iterations} snapshots')
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

        db = client['csc']
        mongodb_snapshots = db['component_snapshots']
        mongodb_identities = db['component_identities']
        meshes_dir = get_snapshot_meshes_directory()
        try:
            point_clouds_dir = get_snapshot_point_clouds_directory()
        except KeyError:
            point_clouds_dir = None
            log('SNAPSHOT_POINT_CLOUDS_DIR is unset; point clouds fall back '
                'to the inline preview', prefix='WARNING')

        registered_keys = collect_output_keys(ALL_SPECS)
        log(f'Registered descriptor keys: {", ".join(registered_keys)}')

        if recompute:
            visited, updated = await _recompute_all(
                mongodb_snapshots=mongodb_snapshots,
                mongodb_identities=mongodb_identities,
                meshes_dir=meshes_dir,
                specs=ALL_SPECS,
                dry_run=dry_run,
                point_clouds_dir=point_clouds_dir,
                max_iterations=max_iterations,
            )
        else:
            while max_iterations is None or visited < max_iterations:
                if visited > 0:
                    log('-' * 80)
                result = await _process_one(
                    mongodb_snapshots=mongodb_snapshots,
                    mongodb_identities=mongodb_identities,
                    meshes_dir=meshes_dir,
                    point_clouds_dir=point_clouds_dir,
                    specs=ALL_SPECS,
                    seen_ids=seen_ids,
                    dry_run=dry_run,
                )
                if result is None:
                    if visited == 0:
                        log('No snapshots with missing descriptors found')
                    else:
                        log('No snapshots with missing descriptors left')
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
        description='Compute descriptors for CSC component snapshots.',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Do not write to MongoDB; only report what would change.',
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--all', dest='process_all', action='store_true',
        help='Process every snapshot with missing descriptors.',
    )
    group.add_argument(
        '--recompute', action='store_true',
        help=(
            'Overwrite every applicable descriptor on every snapshot, '
            'one snapshot at a time. Use after changing how a descriptor '
            'is computed.'
        ),
    )
    parser.add_argument(
        '--limit', type=int, default=None, metavar='N',
        help=(
            'Process at most N snapshots. Default is 1 in cron mode, '
            'unlimited with --all or --recompute.'
        ),
    )
    return parser.parse_args(argv)


def _max_iterations(args: argparse.Namespace) -> Optional[int]:
    if args.limit is not None and args.limit <= 0:
        print('--limit must be a positive integer', file=sys.stderr)
        sys.exit(2)
    if args.recompute:
        return args.limit
    if args.process_all:
        return args.limit
    if args.limit is not None:
        return args.limit
    return 1


if __name__ == '__main__':
    args = _parse_args()

    updated_count = asyncio.run(
        compute_descriptors(
            dry_run=args.dry_run,
            max_iterations=_max_iterations(args),
            recompute=args.recompute,
        )
    )
    if updated_count > 0:
        log(f'Descriptor computation completed: {updated_count} snapshot(s) '
            f'updated')
        sys.exit(0)
    log('No work done or computation failed')
    sys.exit(1)
