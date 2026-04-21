#!/usr/bin/env python3.9
"""
Descriptor computation maintenance script.

Thin orchestrator over the descriptor registry. Runs as a cronjob and
processes one component per invocation.

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
    python main_descriptors_simple.py [--dry-run]
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import asyncio
import random
import sys
from typing import Any, Dict, List, Optional

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
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """Find one component missing at least one applicable descriptor."""
    query = build_missing_query(specs)
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


async def compute_descriptors(dry_run: bool = False) -> bool:
    """Find one component with missing descriptors, compute them, persist."""
    log('Starting descriptor computation...')
    if dry_run:
        log('DRY RUN MODE - No database updates will be made')
    log('-' * 80)

    client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
    )
    try:
        await client.aconnect()
        await client.admin.command('ping')
        log('Connected to MongoDB')

        mongodb_components = client['csc']['components']
        geometry_dir = get_geometry_directory()

        registered_keys = collect_output_keys(ALL_SPECS)
        log(f'Registered descriptor keys: {", ".join(registered_keys)}')

        component = await find_component_with_missing_descriptors(
            mongodb_components, ALL_SPECS, dry_run=dry_run
        )
        if not component:
            log('No components with missing descriptors found')
            return False

        component_id = str(component['_id'])
        log(f'Found component: {component_id}')
        log(f'  Name: {component.get("name", "Unnamed Component")}')
        log(f'  Type: {component.get("type", "unknown")}')

        descriptors = run_missing_specs_on_component(
            component=component,
            geometry_dir=geometry_dir,
            specs=ALL_SPECS,
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
    except Exception as exc:
        log(f'Error during descriptor computation: {exc}', prefix='ERROR')
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.close()
        log('Closed MongoDB connection')


# MAIN EXECUTION --------------------------------------------------------------

if __name__ == '__main__':
    dry_run_flag = '--dry-run' in sys.argv
    success = asyncio.run(compute_descriptors(dry_run=dry_run_flag))
    if success:
        log('Descriptor computation completed successfully')
        sys.exit(0)
    log('No work done or computation failed')
    sys.exit(1)
