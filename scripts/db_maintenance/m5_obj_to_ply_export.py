#!/usr/bin/env python3
"""
M5 prep — convert legacy OBJ folders to snapshot-keyed binary PLY layout
========================================================================

Coordinate contract
-------------------

* **CSC canonical = Rhino Z-up** for PLY bytes (same as ``geometry.meshes``).
* Legacy OBJ is Y-up; converted once on read — see ``geometry_coords``.

Path layout (file-level resolution, same primitive index)
---------------------------------------------------------

* **Primitive index** ``i`` = position in ``geometry.meshes[i]`` (0, 1, …).
* **Resolution** is the **filename**, not a second index:

      meshes/<snapshot_id>/<i>/reduced.ply
      meshes/<snapshot_id>/<i>/detailed.ply

  So reduced and detailed for the **same** mesh both use ``i`` (typically ``0``
  for legacy migration).

* **Multi-primitive components:** one legacy ``mesh.obj`` (or ``mesh_reduced.obj``)
  may contain several ``o`` / ``g`` blocks (e.g. ``o object_0``, ``o object_1``).
  Block order **must** match ``geometry.meshes[0]``, ``geometry.meshes[1]``, …
  Each block becomes one PLY tree::

      meshes/<snapshot_id>/0/{reduced|detailed}.ply
      meshes/<snapshot_id>/1/{reduced|detailed}.ply

* Single-body OBJ (no ``o`` line) -> only ``0/{reduced|detailed}.ply``.

Optional ``--write-mongo-manifest`` sets ``mesh_ply_resolutions``, e.g.
``{'0': ['reduced', 'detailed'], '1': ['reduced', 'detailed']}``, and
**unsets** the obsolete ``mesh_file_slots`` field if present.

Companion file per snapshot folder: ``_mesh_ply_export.json``.

Usage
-----

::

    conda run -n csc python scripts/db_maintenance/m5_obj_to_ply_export.py \
        --geometry-root "D:/.../component_geometry" \
        --output-dir ./local_export/csc_assets

    conda run -n csc python scripts/db_maintenance/m5_obj_to_ply_export.py --apply ...
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pymongo import MongoClient
from pymongo.errors import PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]
_MAINTENANCE_DIR = Path(__file__).resolve().parent
if str(_MAINTENANCE_DIR) not in sys.path:
    sys.path.insert(0, str(_MAINTENANCE_DIR))

from geometry_coords import (  # noqa: E402
    CANONICAL_FRAME,
    MESH_RESOLUTION_DETAILED,
    MESH_RESOLUTION_REDUCED,
    count_legacy_obj_objects,
    export_mesh_ply_rhino,
    load_legacy_obj_meshes_rhino,
)

_LOG_DIR = REPO_ROOT / 'logs'
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _LOG_DIR / 'm5_obj_to_ply_export.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

LEGACY_REDUCED_NAME = 'mesh_reduced.obj'
LEGACY_DETAILED_NAME = 'mesh.obj'

COMPANION_META_NAME = '_mesh_ply_export.json'
_RESOLUTION_ORDER = {MESH_RESOLUTION_REDUCED: 0, MESH_RESOLUTION_DETAILED: 1}


@dataclass
class ExportRow:
    identity_id: str
    snapshot_id: str
    consumed_at: Optional[str]
    mesh_primitive_count: int
    source_path: str
    dest_ply: str
    primitive_index: int
    obj_object_count: int
    resolution: str
    coordinate_frame: str
    status: str
    detail: str = ''


@dataclass
class RunStats:
    identities_total: int = 0
    skipped_no_snapshot: int = 0
    skipped_no_obj: int = 0
    skipped_extrusion_only: int = 0
    ply_planned: int = 0
    ply_written: int = 0
    ply_skipped_exists: int = 0
    mongo_manifest_updated: int = 0
    primitive_align_warnings: int = 0
    errors: int = 0
    rows: List[ExportRow] = field(default_factory=list)


def _load_uri() -> str:
    uri = os.environ.get('MONGODB_URI')
    if not uri:
        cfg = REPO_ROOT / 'scripts' / 'config' / 'dbconfig.json'
        if cfg.is_file():
            with cfg.open('r', encoding='utf-8') as handle:
                data = json.load(handle)
            uri = (
                f"mongodb+srv://{data['user']}:{data['pwd']}@"
                f"{data['server']}/{data['db']}"
            )
    if not uri:
        raise SystemExit(
            'Set MONGODB_URI or provide scripts/config/dbconfig.json'
        )
    return uri


def _resolve_geometry_roots(
    geometry_root: Optional[str],
    geometry_archive_root: Optional[str],
) -> Tuple[Path, Optional[Path]]:
    root = geometry_root or os.environ.get('GEOMETRY_DIR')
    if not root:
        raise SystemExit(
            'Pass --geometry-root or set GEOMETRY_DIR to legacy '
            'component_geometry folder.'
        )
    archive = geometry_archive_root or os.environ.get('GEOMETRY_ARCHIVE_DIR')
    return Path(root).resolve(), (
        Path(archive).resolve() if archive else None
    )


def _find_legacy_obj(
    identity_id: str,
    geometry_root: Path,
    geometry_archive_root: Optional[Path],
    filename: str,
) -> Optional[Path]:
    for base in (geometry_root, geometry_archive_root):
        if base is None:
            continue
        candidate = base / identity_id / filename
        if candidate.is_file():
            return candidate
    return None


def _alignment_warnings(
    identity_id: str,
    mesh_primitive_count: int,
    reduced_src: Optional[Path],
    detailed_src: Optional[Path],
) -> List[str]:
    """Warn when OBJ object count disagrees with ``geometry.meshes`` length."""
    warnings: List[str] = []
    by_file: Dict[str, int] = {}
    if reduced_src is not None:
        by_file['mesh_reduced.obj'] = count_legacy_obj_objects(str(reduced_src))
    if detailed_src is not None:
        by_file['mesh.obj'] = count_legacy_obj_objects(str(detailed_src))
    if not by_file:
        return warnings

    counts = set(by_file.values())
    if len(counts) > 1:
        parts = ', '.join(f'{name}={n}' for name, n in by_file.items())
        warnings.append(
            f'{identity_id}: OBJ object counts differ ({parts})'
        )

    n_obj = max(counts)
    if mesh_primitive_count > 0 and n_obj != mesh_primitive_count:
        warnings.append(
            f'{identity_id}: legacy OBJ has {n_obj} object(s) but '
            f'geometry.meshes has {mesh_primitive_count} primitive(s); '
            f'object order must match meshes[0], meshes[1], …'
        )
    return warnings


def _plan_exports(
    identity_id: str,
    snapshot_id: str,
    consumed_at: Optional[str],
    mesh_primitive_count: int,
    geometry_root: Path,
    geometry_archive_root: Optional[Path],
    meshes_out: Path,
) -> Tuple[List[ExportRow], Dict[str, List[str]], str, List[str]]:
    reduced_src = _find_legacy_obj(
        identity_id, geometry_root, geometry_archive_root, LEGACY_REDUCED_NAME,
    )
    detailed_src = _find_legacy_obj(
        identity_id,
        geometry_root,
        geometry_archive_root,
        LEGACY_DETAILED_NAME,
    )

    if reduced_src is None and detailed_src is None:
        if mesh_primitive_count > 0:
            return [], {}, 'no_obj_but_mesh_primitive', []
        return [], {}, 'no_obj_extrusion_or_primitive_only', []

    align_warnings = _alignment_warnings(
        identity_id,
        mesh_primitive_count,
        reduced_src,
        detailed_src,
    )

    rows: List[ExportRow] = []
    manifest: Dict[str, List[str]] = {}

    def add_rows(src: Path, resolution: str) -> None:
        n_objects = count_legacy_obj_objects(str(src))
        for obj_idx in range(n_objects):
            key = str(obj_idx)
            dest = (
                meshes_out / snapshot_id / key / f'{resolution}.ply'
            )
            manifest.setdefault(key, [])
            if resolution not in manifest[key]:
                manifest[key].append(resolution)
            rows.append(
                ExportRow(
                    identity_id=identity_id,
                    snapshot_id=snapshot_id,
                    consumed_at=consumed_at,
                    mesh_primitive_count=mesh_primitive_count,
                    source_path=str(src),
                    dest_ply=str(dest),
                    primitive_index=obj_idx,
                    obj_object_count=n_objects,
                    resolution=resolution,
                    coordinate_frame=CANONICAL_FRAME,
                    status='planned',
                )
            )

    if reduced_src is not None:
        add_rows(reduced_src, MESH_RESOLUTION_REDUCED)
    if detailed_src is not None:
        add_rows(detailed_src, MESH_RESOLUTION_DETAILED)

    for key in manifest:
        manifest[key] = sorted(
            set(manifest[key]),
            key=lambda r: _RESOLUTION_ORDER.get(r, 99),
        )

    return rows, manifest, '', align_warnings


def _write_companion_meta(
    snapshot_meshes_dir: Path,
    manifest: Dict[str, List[str]],
) -> None:
    snapshot_meshes_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        'coordinate_frame': CANONICAL_FRAME,
        'path_pattern': 'meshes/<snapshot_id>/<primitive_index>/'
                        '{reduced|detailed}.ply',
        'mesh_ply_resolutions': manifest,
    }
    path = snapshot_meshes_dir / COMPANION_META_NAME
    with path.open('w', encoding='utf-8') as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)


def _write_reports(rows: List[ExportRow], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / 'm5_obj_to_ply_export.json'
    csv_path = report_dir / 'm5_obj_to_ply_export.csv'

    payload = [asdict(r) for r in rows]
    with json_path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2)

    if rows:
        fieldnames = list(asdict(rows[0]).keys())
        with csv_path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(payload)

    logger.info('Wrote manifest %s and %s', json_path, csv_path)


def run(
    *,
    apply: bool,
    force: bool,
    write_mongo_manifest: bool,
    geometry_root: Optional[str],
    geometry_archive_root: Optional[str],
    output_dir: Path,
    report_dir: Path,
    limit: Optional[int],
) -> int:
    geo_root, geo_archive = _resolve_geometry_roots(
        geometry_root,
        geometry_archive_root,
    )
    meshes_out = output_dir / 'meshes'
    meshes_out.mkdir(parents=True, exist_ok=True)

    client = MongoClient(_load_uri(), serverSelectionTimeoutMS=30000)
    db = client.get_default_database()
    identities = db['component_identities']
    snapshots = db['component_snapshots']

    stats = RunStats()
    pending_manifests: List[Tuple[str, Dict[str, List[str]]]] = []

    try:
        cursor = identities.find(
            {},
            {'_id': 1, 'current_snapshot_id': 1, 'consumed_at': 1},
        )
        if limit is not None:
            cursor = cursor.limit(limit)

        for identity_doc in cursor:
            stats.identities_total += 1
            identity_id = str(identity_doc['_id'])
            snapshot_id = identity_doc.get('current_snapshot_id')
            consumed_at = identity_doc.get('consumed_at')

            if not snapshot_id:
                stats.skipped_no_snapshot += 1
                continue

            snapshot_id = str(snapshot_id)
            snap_doc = snapshots.find_one(
                {'_id': snapshot_id},
                {'geometry.meshes': 1},
            )
            mesh_primitive_count = 0
            if snap_doc and snap_doc.get('geometry'):
                meshes = snap_doc['geometry'].get('meshes') or []
                mesh_primitive_count = len(meshes)

            planned, manifest, skip_reason, align_warnings = _plan_exports(
                identity_id,
                snapshot_id,
                consumed_at,
                mesh_primitive_count,
                geo_root,
                geo_archive,
                meshes_out,
            )

            for msg in align_warnings:
                logger.warning(msg)
                stats.primitive_align_warnings += 1

            if skip_reason == 'no_obj_extrusion_or_primitive_only':
                stats.skipped_extrusion_only += 1
                continue
            if skip_reason == 'no_obj_but_mesh_primitive':
                stats.skipped_no_obj += 1
                logger.warning(
                    '%s: mesh primitives in DB but no OBJ on disk',
                    identity_id,
                )
                continue
            if not planned:
                stats.skipped_no_obj += 1
                continue

            pending_manifests.append((snapshot_id, manifest))

            mesh_cache: Dict[str, List] = {}

            for row in planned:
                stats.ply_planned += 1
                dest = Path(row.dest_ply)
                if dest.is_file() and not force:
                    row.status = 'skipped_exists'
                    stats.ply_skipped_exists += 1
                    stats.rows.append(row)
                    continue

                if not apply:
                    row.status = 'dry_run'
                    logger.info(
                        '[dry-run] %s -> %s (prim=%s %s)',
                        row.source_path,
                        dest,
                        row.primitive_index,
                        row.resolution,
                    )
                    stats.rows.append(row)
                    continue

                try:
                    if row.source_path not in mesh_cache:
                        mesh_cache[row.source_path] = (
                            load_legacy_obj_meshes_rhino(row.source_path)
                        )
                    meshes = mesh_cache[row.source_path]
                    if row.primitive_index >= len(meshes):
                        raise IndexError(
                            f'primitive_index {row.primitive_index} but '
                            f'{row.source_path} has {len(meshes)} objects'
                        )
                    export_mesh_ply_rhino(
                        meshes[row.primitive_index],
                        str(dest),
                    )
                    row.status = 'written'
                    stats.ply_written += 1
                    logger.info('Wrote %s', dest)
                except Exception as exc:
                    row.status = 'error'
                    row.detail = str(exc)[:500]
                    stats.errors += 1
                    logger.error('Failed %s: %s', row.source_path, exc)
                stats.rows.append(row)

            snap_mesh_dir = meshes_out / snapshot_id
            if apply and manifest:
                # _write_companion_meta(snap_mesh_dir, manifest)
                pass
            elif manifest and not apply:
                logger.info(
                    '[dry-run] would write %s %s',
                    snap_mesh_dir / COMPANION_META_NAME,
                    manifest,
                )

        # One meta + manifest update per snapshot
        # (last identity wins same snap)
        if write_mongo_manifest and apply and pending_manifests:
            by_snap: Dict[str, Dict[str, List[str]]] = {}
            for sid, man in pending_manifests:
                by_snap[sid] = man
            for snapshot_id, manifest in by_snap.items():
                result = snapshots.update_one(
                    {'_id': snapshot_id},
                    {
                        '$set': {'mesh_ply_resolutions': manifest},
                        '$unset': {'mesh_file_slots': ''},
                    },
                )
                if result.modified_count:
                    stats.mongo_manifest_updated += 1

    except PyMongoError as exc:
        logger.error('Mongo error: %s', exc)
        return 1
    finally:
        client.close()

    _write_reports(stats.rows, report_dir)

    logger.info('--- summary ---')
    for key, val in asdict(stats).items():
        if key != 'rows':
            logger.info('  %s: %s', key, val)
    logger.info('  layout: meshes/<snapshot_id>/<i>/{reduced,detailed}.ply')
    logger.info('  coordinate_frame: %s', CANONICAL_FRAME)
    logger.info('  output: %s', meshes_out)
    if not apply:
        logger.info('Dry-run only. Re-run with --apply to write files.')

    return 1 if stats.errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Legacy OBJ -> snapshot PLY (Rhino Z-up, per-resolution paths)'
        ),
    )
    parser.add_argument('--geometry-root')
    parser.add_argument('--geometry-archive-root')
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=REPO_ROOT / 'local_export' / 'csc_assets',
    )
    parser.add_argument(
        '--report-dir',
        type=Path,
        default=REPO_ROOT / 'future_implementation',
    )
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument(
        '--write-mongo-manifest',
        action='store_true',
        help=(
            'Set mesh_ply_resolutions on snapshot and unset obsolete '
            'mesh_file_slots'
        ),
    )
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()
    raise SystemExit(
        run(
            apply=args.apply,
            force=args.force,
            write_mongo_manifest=args.write_mongo_manifest,
            geometry_root=args.geometry_root,
            geometry_archive_root=args.geometry_archive_root,
            output_dir=args.output_dir.resolve(),
            report_dir=args.report_dir.resolve(),
            limit=args.limit,
        )
    )


if __name__ == '__main__':
    main()
