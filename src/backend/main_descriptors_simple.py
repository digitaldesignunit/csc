#!/usr/bin/env python3.9
"""
Descriptor computation maintenance script.

Thin orchestrator over the descriptor registry. Can run in two modes:

    1. Cron worker (default): processes one snapshot per invocation. This
       is what the `descriptors_simple_cronjob.ini` entry uses.
    2. Batch backfill (``--all`` / ``--limit N``): loops over every
       snapshot that is missing an applicable descriptor, in a single
       MongoDB connection.

Responsibilities of this module, and nothing else:
    1. Connect to MongoDB (`component_snapshots` + `component_identities`).
    2. Ask the registry for a snapshot that is missing at least one
       applicable descriptor.
    3. Load geometry via `apps.descriptors.geometry.load_snapshot_mesh`.
    4. Iterate the specs that apply to this snapshot and are missing,
       running each spec's compute function via the registry.
    5. Merge the results back into the snapshot's ``descriptors`` field.

All per-descriptor knowledge (parameters, applicability, output keys,
compute function) lives in `apps.descriptors/specs.py`. To add a new
descriptor, add one `DescriptorSpec` there; no changes are needed here.

Usage:
    python main_descriptors_simple.py                # one snapshot
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
    get_snapshot_meshes_directory,
)
from apps.descriptors.geometry import load_snapshot_mesh
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

def run_missing_specs_on_snapshot(
    compute_doc: Dict[str, Any],
    meshes_dir: Optional[str],
    specs: List[DescriptorSpec],
) -> Dict[str, Any]:
    """Execute every applicable+missing spec against a snapshot."""
    missing = missing_specs_for(compute_doc, specs)
    if not missing:
        log('No missing applicable descriptors on this snapshot')
        return {}

    expected_keys = collect_output_keys(missing)
    log(f'Missing applicable descriptors: {", ".join(expected_keys)}')

    needs_mesh = any(spec.requires_mesh for spec in missing)
    mesh = None
    if needs_mesh:
        log('Loading geometry...')
        mesh = load_snapshot_mesh(
            compute_doc,
            meshes_dir=meshes_dir,
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
            component=compute_doc,
            mesh=mesh,
            log=_spec_logger(spec),
        )
        results.update(spec_results)
    return results


async def _process_one(
    mongodb_snapshots,
    mongodb_identities,
    meshes_dir: Optional[str],
    specs: List[DescriptorSpec],
    seen_ids: Set[str],
    dry_run: bool,
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

    snapshot_id = str(snapshot['_id'])
    seen_ids.add(snapshot_id)

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

    descriptors = run_missing_specs_on_snapshot(
        compute_doc=compute_doc,
        meshes_dir=meshes_dir,
        specs=specs,
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


async def compute_descriptors(
    dry_run: bool = False,
    max_iterations: Optional[int] = 1,
) -> int:
    """Find snapshots with missing descriptors, compute them, persist.

    Args:
        dry_run: if True, never write to MongoDB.
        max_iterations: upper bound on snapshots processed in this run.
            ``None`` means "until no snapshot needs work".

    Returns:
        Number of snapshots for which new descriptors were written
        (or would be written, in dry-run).
    """
    log('Starting descriptor computation...')
    if dry_run:
        log('DRY RUN MODE - No database updates will be made')
    if max_iterations is None:
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

        registered_keys = collect_output_keys(ALL_SPECS)
        log(f'Registered descriptor keys: {", ".join(registered_keys)}')

        while max_iterations is None or visited < max_iterations:
            if visited > 0:
                log('-' * 80)
            result = await _process_one(
                mongodb_snapshots=mongodb_snapshots,
                mongodb_identities=mongodb_identities,
                meshes_dir=meshes_dir,
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
        description='Compute missing descriptors for CSC component snapshots.',
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
        '--limit', type=int, default=None, metavar='N',
        help='Process at most N snapshots (default: 1, i.e. cron mode).',
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
        log(f'Descriptor computation completed: {updated_count} snapshot(s) '
            f'updated')
        sys.exit(0)
    log('No work done or computation failed')
    sys.exit(1)
