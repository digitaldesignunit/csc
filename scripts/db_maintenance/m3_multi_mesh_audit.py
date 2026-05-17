#!/usr/bin/env python3
"""Compare legacy component mesh counts vs v0.5 snapshot mesh counts (local dumps)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
DUMP_DIR = REPO / 'mongodb_collections_local'


def _mesh_count(geometry: Optional[Dict[str, Any]]) -> int:
    if not geometry:
        return 0
    meshes = geometry.get('meshes')
    if meshes:
        return len(meshes)
    legacy_mesh = geometry.get('mesh')
    if legacy_mesh:
        return 1
    return 0


def _load_array(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def main() -> int:
    components_path = DUMP_DIR / 'csc.components.json'
    archive_path = DUMP_DIR / 'csc.components_archive.json'
    identities_path = DUMP_DIR / 'csc.component_identities.json'
    snapshots_path = DUMP_DIR / 'csc.component_snapshots.json'

    for p in (components_path, identities_path, snapshots_path):
        if not p.is_file():
            print(f'Missing {p}', file=sys.stderr)
            return 1

    legacy_by_id: Dict[str, Dict[str, Any]] = {}
    for path in (components_path, archive_path):
        if not path.is_file():
            continue
        for row in _load_array(path):
            legacy_by_id[str(row['_id'])] = row

    identities = _load_array(identities_path)
    snapshots = _load_array(snapshots_path)
    snap_by_id = {str(s['_id']): s for s in snapshots}

    mismatches: List[Tuple[str, int, int, str]] = []
    multi_legacy = 0
    multi_snap = 0
    checked = 0

    for ident in identities:
        iid = str(ident['_id'])
        snap_id = ident.get('current_snapshot_id')
        if not snap_id:
            continue
        legacy = legacy_by_id.get(iid)
        if legacy is None:
            continue
        snap = snap_by_id.get(str(snap_id))
        if snap is None:
            mismatches.append((iid, -1, -1, 'snapshot missing'))
            continue

        legacy_n = _mesh_count(legacy.get('geometry'))
        snap_n = _mesh_count(snap.get('geometry'))
        checked += 1
        if legacy_n > 1:
            multi_legacy += 1
        if snap_n > 1:
            multi_snap += 1
        if legacy_n != snap_n:
            mismatches.append((iid, legacy_n, snap_n, str(snap_id)))

    print(f'Legacy rows loaded: {len(legacy_by_id)}')
    print(f'Identities with legacy + current snapshot: {checked}')
    print(f'Legacy geometry.meshes count > 1: {multi_legacy}')
    print(f'Snapshot geometry.meshes count > 1: {multi_snap}')
    print(f'Mesh count mismatches: {len(mismatches)}')

    if mismatches:
        print('\nFirst 20 mismatches (identity_id, legacy_n, snap_n, snapshot_id):')
        for row in mismatches[:20]:
            print(' ', row)

    content_mismatches = 0
    for ident in identities:
        iid = str(ident['_id'])
        snap_id = ident.get('current_snapshot_id')
        legacy = legacy_by_id.get(iid)
        if not legacy or not snap_id:
            continue
        snap = snap_by_id.get(str(snap_id))
        if not snap:
            continue
        leg_meshes = (legacy.get('geometry') or {}).get('meshes') or []
        snap_meshes = (snap.get('geometry') or {}).get('meshes') or []
        for idx, lm in enumerate(leg_meshes):
            sm = snap_meshes[idx]
            lv, lf = lm.get('v') or [], lm.get('f') or []
            sv, sf = sm.get('vertices') or [], sm.get('faces') or []
            if len(lv) != len(sv) or len(lf) != len(sf):
                content_mismatches += 1
                break
            if lm.get('c') != sm.get('colors'):
                content_mismatches += 1
                break
    print(f'Per-primitive v/f/c length mismatches: {content_mismatches}')

    # Legacy still on singular geometry.mesh only
    singular_only = 0
    for iid, row in legacy_by_id.items():
        g = row.get('geometry') or {}
        if g.get('mesh') and not g.get('meshes'):
            singular_only += 1
    print(f'\nLegacy rows with geometry.mesh only (no meshes[]): {singular_only}')

    return 1 if mismatches else 0


if __name__ == '__main__':
    raise SystemExit(main())
