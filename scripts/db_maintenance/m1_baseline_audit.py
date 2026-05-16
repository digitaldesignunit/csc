#!/usr/bin/env python3
"""
M1 - Baseline audit (read-only) for legacy components / components_archive
=========================================================================

Implements milestone **M1** of the v0.5 migration track
(see ``future_implementation/IMPLEMENTATION_PLAN_V0-5.md`` and
``future_implementation/ADRs.md``).

This script is **strictly read-only**. It performs the data-quality
baseline that must be reviewable before identity/snapshot migration (M3)
or any catalog-number backfill (M2) is run.

Inputs
------

1. Local JSON dumps of the legacy collections (frozen baseline):
     - ``mongodb_collections_local/csc.components.json``
     - ``mongodb_collections_local/csc.components_archive.json``

2. Optional: live MongoDB connection (drift detection vs. the frozen
   baseline). Connection follows the pattern used by
   ``migrate_phase1_component_schema.py``:
     - ``MONGO_URI`` environment variable, or
     - ``scripts/config/dbconfig.json`` (keys: server, db, user, pwd)
   Pass ``--mongo`` to enable.

3. Optional: geometry backup root (e.g.
   ``D:\\01_PROJECT_WORKDATA\\260512_CSC_BACKUP\\component_geometry``).
   Each subfolder is named after a legacy ``components._id`` and holds
   ``mesh.obj`` / ``mesh_reduced.obj``. Pass ``--geometry-root <path>``.

Outputs
-------

- ``future_implementation/M1_BASELINE_REPORT.md`` (human-readable)
- ``future_implementation/M1_BASELINE_REPORT.json`` (machine-readable;
  consumed downstream by M2/M3 scripts; do NOT hand-edit)

Policy
------

Per the M1 configuration choice (soft mode), this script **never exits
non-zero** on data anomalies. All findings are categorised as either
``error``, ``warning``, or ``info`` inside the report itself.

Usage
-----

    # Files-only baseline (no live Mongo)
    python scripts/db_maintenance/m1_baseline_audit.py \
        --geometry-root "D:/01_PROJECT_WORKDATA/.../component_geometry"

    # Files + live Mongo drift cross-check
    python scripts/db_maintenance/m1_baseline_audit.py --mongo \
        --geometry-root "D:/01_PROJECT_WORKDATA/.../component_geometry"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Optional dependency: pymongo (only imported when --mongo is requested)
# Keeps file-only runs fully self-contained.


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DUMP_DIR = REPO_ROOT / "mongodb_collections_local"
DEFAULT_REPORT_DIR = REPO_ROOT / "future_implementation"
DEFAULT_REPORT_MD = DEFAULT_REPORT_DIR / "M1_BASELINE_REPORT.md"
DEFAULT_REPORT_JSON = DEFAULT_REPORT_DIR / "M1_BASELINE_REPORT.json"

COMPONENTS_COLLECTION = "components"
ARCHIVE_COLLECTION = "components_archive"

ALLOWED_COMPONENT_TYPES = [
    "panel",
    "beam",
    "column",
    "slab",
    "rubble",
    "brick",
    "pipe",
    "profile",
    "connector",
    "other",
]
LEGACY_TYPE_ALIASES = {"sheet": "panel"}

PHASE1_NEW_FIELDS = [
    "condition",
    "manufactured_at",
    "manufactured_precision",
    "salvage_source",
    "salvaged_at",
    "parent_component",
]
ALLOWED_CONDITION_VALUES = [0, 1, 2, 3]

REPORT_SCHEMA_VERSION = "1.0"

_LOG_DIR = REPO_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _LOG_DIR / "m1_baseline_audit.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_json_dump(path: Path) -> List[Dict[str, Any]]:
    """Load a Mongo Compass / mongoexport JSON array dump from disk."""
    if not path.exists():
        logger.warning(f"Dump not found: {path}")
        return []
    logger.info(f"Loading {path} ...")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected dump shape in {path}: expected top-level JSON array, "
            f"got {type(data).__name__}"
        )
    logger.info(f"  loaded {len(data)} records from {path.name}")
    return data


def load_mongo_config() -> Optional[Dict[str, str]]:
    """Return ``{'uri': ...}`` or None. Matches migrate_phase1 pattern."""
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        return {"uri": mongo_uri}

    candidates = [
        REPO_ROOT / "scripts" / "config" / "dbconfig.json",
        Path("..") / "config" / "dbconfig.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            with candidate.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            server = cfg.get("server")
            db = cfg.get("db")
            user = cfg.get("user")
            pwd = cfg.get("pwd")
            if not (server and db and user and pwd):
                logger.warning(
                    f"{candidate} incomplete (need server/db/user/pwd); "
                    "skipping"
                )
                continue
            uri = f"mongodb+srv://{user}:{pwd}@{server}/{db}"
            return {"uri": uri}
        except Exception as e:
            logger.warning(f"Failed to read {candidate}: {e}")
    return None


def connect_mongo():
    """Return (client, db) or (None, None) if connection unavailable."""
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError:
        logger.warning(
            "pymongo not installed; live Mongo cross-check disabled"
        )
        return None, None

    cfg = load_mongo_config()
    if not cfg:
        logger.warning(
            "No Mongo config found (set MONGO_URI or "
            "scripts/config/dbconfig.json); live cross-check disabled"
        )
        return None, None

    try:
        client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=5000)
        db = client.get_default_database()
        if db is None:
            db_name = cfg["uri"].split("/")[-1].split("?")[0]
            db = client[db_name]
        # Force a connection
        db.list_collection_names()
        return client, db
    except Exception as e:
        logger.warning(f"Mongo connection failed: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Auditors
# ---------------------------------------------------------------------------


def _doc_id(doc: Dict[str, Any]) -> Optional[str]:
    val = doc.get("_id")
    if isinstance(val, dict):  # mongoexport extended JSON {"$oid": "..."}
        for k in ("$oid", "$uuid"):
            if k in val:
                return str(val[k])
        return json.dumps(val, sort_keys=True)
    if val is None:
        return None
    return str(val)


def _doc_hash(doc: Dict[str, Any]) -> str:
    """Stable content hash for drift detection (excludes _id)."""
    copy = {k: v for k, v in doc.items() if k != "_id"}
    payload = json.dumps(copy, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def audit_inventory(
    docs: List[Dict[str, Any]],
    label: str,
) -> Dict[str, Any]:
    """Per-collection inventory + duplicate detection."""
    ids: List[str] = []
    missing_id: List[int] = []
    for idx, doc in enumerate(docs):
        did = _doc_id(doc)
        if did is None:
            missing_id.append(idx)
        else:
            ids.append(did)

    counts = Counter(ids)
    duplicates = sorted([i for i, n in counts.items() if n > 1])

    return {
        "label": label,
        "count": len(docs),
        "unique_id_count": len(set(ids)),
        "missing_id_count": len(missing_id),
        "duplicate_ids": duplicates,
        "ids": sorted(set(ids)),
    }


def audit_field_histogram(
    docs: List[Dict[str, Any]],
) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for doc in docs:
        for k in doc.keys():
            counts[k] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def audit_schema(
    docs: List[Dict[str, Any]],
    label: str,
) -> Dict[str, Any]:
    """Phase 1 schema hygiene + type / condition distributions."""
    type_counts: Counter[str] = Counter()
    condition_counts: Counter[Any] = Counter()
    sheet_ids: List[str] = []
    bad_type_ids: List[Tuple[str, Any]] = []
    bad_condition_ids: List[Tuple[str, Any]] = []
    missing_fields: Dict[str, List[str]] = {f: [] for f in PHASE1_NEW_FIELDS}
    has_descriptors = 0
    descriptors_subkeys: Counter[str] = Counter()

    allowed_types: Set[str] = set(ALLOWED_COMPONENT_TYPES) | set(
        LEGACY_TYPE_ALIASES.keys()
    )

    for doc in docs:
        did = _doc_id(doc) or "<missing>"
        t = doc.get("type")
        type_counts[str(t)] += 1
        if t == "sheet":
            sheet_ids.append(did)
        if t is None or t not in allowed_types:
            bad_type_ids.append((did, t))

        c = doc.get("condition")
        condition_counts[c] += 1
        if c is not None and c not in ALLOWED_CONDITION_VALUES:
            bad_condition_ids.append((did, c))

        for f in PHASE1_NEW_FIELDS:
            if f not in doc:
                missing_fields[f].append(did)

        desc = doc.get("descriptors")
        if isinstance(desc, dict) and desc:
            has_descriptors += 1
            for k in desc.keys():
                descriptors_subkeys[str(k)] += 1

    return {
        "label": label,
        "type_histogram": dict(
            sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "sheet_present_count": len(sheet_ids),
        "sheet_ids": sheet_ids,
        "non_enum_type_count": len(bad_type_ids),
        "non_enum_type_samples": bad_type_ids[:20],
        "condition_histogram": {
            ("null" if k is None else str(k)): v
            for k, v in condition_counts.items()
        },
        "non_enum_condition_count": len(bad_condition_ids),
        "non_enum_condition_samples": bad_condition_ids[:20],
        "phase1_missing_field_counts": {
            f: len(ids) for f, ids in missing_fields.items()
        },
        "phase1_missing_field_samples": {
            f: ids[:20] for f, ids in missing_fields.items() if ids
        },
        "descriptors_doc_count": has_descriptors,
        "descriptors_subkeys": dict(
            sorted(
                descriptors_subkeys.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ),
    }


def audit_lineage(
    live: List[Dict[str, Any]],
    archive: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Parent / child analysis for ADR-008 (live `parent_component`)."""
    live_ids: Set[str] = {
        _doc_id(d) for d in live if _doc_id(d) is not None
    }  # type: ignore[arg-type]
    archive_ids: Set[str] = {
        _doc_id(d) for d in archive if _doc_id(d) is not None
    }  # type: ignore[arg-type]

    split_candidates: List[Dict[str, str]] = []
    parent_in_live: List[Dict[str, str]] = []
    dangling: List[Dict[str, str]] = []
    self_refs: List[str] = []
    parent_to_children: Dict[str, List[str]] = defaultdict(list)
    children_with_parent_total = 0

    for d in live:
        cid = _doc_id(d)
        pid = d.get("parent_component")
        if not pid:
            continue
        cid_str = cid or "<missing>"
        pid_str = str(pid)
        children_with_parent_total += 1
        if cid_str == pid_str:
            self_refs.append(cid_str)
            continue
        parent_to_children[pid_str].append(cid_str)

        edge = {"child_id": cid_str, "parent_id": pid_str}
        if pid_str in archive_ids:
            split_candidates.append({**edge, "parent_in": "archive"})
        elif pid_str in live_ids:
            parent_in_live.append({**edge, "parent_in": "live"})
        else:
            dangling.append({**edge, "parent_in": "none"})

    multi_child_parents = [
        {"parent_id": p, "children": sorted(c)}
        for p, c in parent_to_children.items()
        if len(c) > 1
    ]

    return {
        "live_total": len(live_ids),
        "archive_total": len(archive_ids),
        "intersection_count": len(live_ids & archive_ids),
        "intersection_ids": sorted(live_ids & archive_ids)[:50],
        "children_with_parent_total": children_with_parent_total,
        "split_candidate_count": len(split_candidates),
        "split_candidates": split_candidates,
        "parent_in_live_count": len(parent_in_live),
        "parent_in_live": parent_in_live,
        "dangling_parent_count": len(dangling),
        "dangling_parents": dangling,
        "self_reference_count": len(self_refs),
        "self_references": self_refs,
        "multi_child_parent_count": len(multi_child_parents),
        "multi_child_parents": multi_child_parents,
    }


def classify_geometry_shape(doc: Dict[str, Any]) -> str:
    """Return per-doc geometry expectation: `extrusion`, `mesh_inline`,
    `both`, or `empty`."""
    geo = doc.get("geometry") or {}
    if not isinstance(geo, dict):
        return "empty"
    has_extrusion = bool(geo.get("extrusion"))
    has_mesh = bool(geo.get("meshes"))
    if has_extrusion and has_mesh:
        return "both"
    if has_extrusion:
        return "extrusion"
    if has_mesh:
        return "mesh_inline"
    return "empty"


def _scan_geometry_root(root: Path) -> Dict[str, Any]:
    """Enumerate one geometry root and summarise its on-disk layout."""
    LARGE_MESH_BYTES = 200 * 1024 * 1024  # >200MB flagged for review
    folders = [p for p in root.iterdir() if p.is_dir()]
    folder_ids = {p.name for p in folders}
    file_shape_counts: Counter[str] = Counter()
    missing_reduced: List[str] = []
    large_meshes: List[Dict[str, Any]] = []
    for p in folders:
        files = list(p.iterdir())
        names = sorted([f.name for f in files])
        has_main = "mesh.obj" in names
        has_reduced = "mesh_reduced.obj" in names
        if has_main and has_reduced:
            shape = "mesh+reduced"
        elif has_main and not has_reduced:
            shape = "mesh_only"
            missing_reduced.append(p.name)
        elif has_reduced and not has_main:
            shape = "reduced_only"
        elif not files:
            shape = "empty"
        else:
            shape = "other"
        file_shape_counts[shape] += 1
        for f in files:
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size >= LARGE_MESH_BYTES:
                large_meshes.append(
                    {
                        "folder": p.name,
                        "file": f.name,
                        "size_bytes": size,
                    }
                )
    return {
        "root": str(root),
        "folder_count": len(folders),
        "folder_ids": folder_ids,
        "file_shape_counts": dict(
            sorted(
                file_shape_counts.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ),
        "missing_reduced": missing_reduced,
        "large_meshes": large_meshes,
    }


def audit_geometry(
    live_root: Optional[Path],
    archive_root: Optional[Path],
    live_docs: List[Dict[str, Any]],
    archive_docs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Cross-check disk geometry assets vs DB id space, splitting per-doc
    expectations by inline `extrusion` vs `meshes`. Live and archive
    docs are matched against their own roots when ``archive_root`` is
    set; otherwise both fall back to the live root (legacy behaviour)."""
    live_shape: Dict[str, str] = {}
    archive_shape: Dict[str, str] = {}
    live_shape_counts: Counter[str] = Counter()
    archive_shape_counts: Counter[str] = Counter()
    for d in live_docs:
        did = _doc_id(d)
        if did is None:
            continue
        s = classify_geometry_shape(d)
        live_shape[did] = s
        live_shape_counts[s] += 1
    for d in archive_docs:
        did = _doc_id(d)
        if did is None:
            continue
        s = classify_geometry_shape(d)
        archive_shape[did] = s
        archive_shape_counts[s] += 1

    if live_root is None and archive_root is None:
        return {
            "status": "skipped",
            "reason": "no --geometry-root / --geometry-root-archive passed",
            "live_shape_counts": dict(live_shape_counts),
            "archive_shape_counts": dict(archive_shape_counts),
        }

    missing_roots: List[str] = []
    if live_root is not None and not live_root.exists():
        missing_roots.append(str(live_root))
    if archive_root is not None and not archive_root.exists():
        missing_roots.append(str(archive_root))
    if missing_roots and (
        (live_root is None or not live_root.exists())
        and (archive_root is None or not archive_root.exists())
    ):
        return {
            "status": "missing",
            "missing_roots": missing_roots,
            "reason": "geometry root path(s) do not exist",
            "live_shape_counts": dict(live_shape_counts),
            "archive_shape_counts": dict(archive_shape_counts),
        }

    live_scan = _scan_geometry_root(live_root) if (
        live_root is not None and live_root.exists()
    ) else None
    archive_scan = _scan_geometry_root(archive_root) if (
        archive_root is not None and archive_root.exists()
    ) else None

    # Archive docs fall back to the live root when no archive root given
    # (legacy behaviour) so existing setups keep working.
    archive_check_scan = archive_scan or live_scan
    live_folder_ids: Set[str] = (
        live_scan["folder_ids"] if live_scan else set()
    )
    archive_folder_ids: Set[str] = (
        archive_check_scan["folder_ids"] if archive_check_scan else set()
    )

    def _split_missing(
        shape_map: Dict[str, str],
        folder_ids: Set[str],
    ) -> Tuple[List[str], List[str], List[str]]:
        """Return (mesh_missing_folder, extrusion_no_folder_expected,
        empty_no_folder)."""
        missing_real: List[str] = []
        expected_no_folder: List[str] = []
        empty_no_folder: List[str] = []
        for did, shape in shape_map.items():
            if did in folder_ids:
                continue
            if shape in ("mesh_inline", "both"):
                missing_real.append(did)
            elif shape == "extrusion":
                expected_no_folder.append(did)
            else:
                empty_no_folder.append(did)
        return (
            sorted(missing_real),
            sorted(expected_no_folder),
            sorted(empty_no_folder),
        )

    (
        live_mesh_missing_folder,
        live_extrusion_no_folder,
        live_empty_no_folder,
    ) = _split_missing(live_shape, live_folder_ids)
    (
        archive_mesh_missing_folder,
        archive_extrusion_no_folder,
        archive_empty_no_folder,
    ) = _split_missing(archive_shape, archive_folder_ids)

    live_ids: Set[str] = set(live_shape.keys())
    archive_ids: Set[str] = set(archive_shape.keys())
    orphan_folders_live = sorted(live_folder_ids - live_ids - archive_ids)
    if archive_scan is not None:
        orphan_folders_archive = sorted(
            archive_folder_ids - live_ids - archive_ids
        )
    else:
        orphan_folders_archive = []

    missing_reduced_combined: List[str] = []
    large_meshes_combined: List[Dict[str, Any]] = []
    if live_scan is not None:
        missing_reduced_combined.extend(live_scan["missing_reduced"])
        large_meshes_combined.extend(live_scan["large_meshes"])
    if archive_scan is not None:
        missing_reduced_combined.extend(archive_scan["missing_reduced"])
        large_meshes_combined.extend(archive_scan["large_meshes"])

    return {
        "status": "ok",
        "live_root": str(live_root) if live_root else None,
        "archive_root": str(archive_root) if archive_root else None,
        "live_root_present": live_scan is not None,
        "archive_root_present": archive_scan is not None,
        "live_folder_count": live_scan["folder_count"] if live_scan else 0,
        "archive_folder_count": (
            archive_scan["folder_count"] if archive_scan else 0
        ),
        "live_file_shape_counts": (
            live_scan["file_shape_counts"] if live_scan else {}
        ),
        "archive_file_shape_counts": (
            archive_scan["file_shape_counts"] if archive_scan else {}
        ),
        "live_shape_counts": dict(live_shape_counts),
        "archive_shape_counts": dict(archive_shape_counts),
        "orphan_folders_live_count": len(orphan_folders_live),
        "orphan_folders_live": orphan_folders_live,
        "orphan_folders_archive_count": len(orphan_folders_archive),
        "orphan_folders_archive": orphan_folders_archive,
        "live_mesh_missing_folder_count": len(live_mesh_missing_folder),
        "live_mesh_missing_folder": live_mesh_missing_folder,
        "live_extrusion_no_folder_count": len(live_extrusion_no_folder),
        "live_empty_no_folder_count": len(live_empty_no_folder),
        "live_empty_no_folder": live_empty_no_folder,
        "archive_mesh_missing_folder_count": len(
            archive_mesh_missing_folder
        ),
        "archive_mesh_missing_folder": archive_mesh_missing_folder,
        "archive_extrusion_no_folder_count": len(
            archive_extrusion_no_folder
        ),
        "archive_empty_no_folder_count": len(archive_empty_no_folder),
        "archive_empty_no_folder": archive_empty_no_folder,
        "missing_reduced_count": len(missing_reduced_combined),
        "missing_reduced": missing_reduced_combined,
        "large_mesh_count": len(large_meshes_combined),
        "large_meshes": large_meshes_combined,
    }


def audit_drift(
    file_docs: List[Dict[str, Any]],
    mongo_docs: List[Dict[str, Any]],
    label: str,
) -> Dict[str, Any]:
    """Compare frozen file dump vs live Mongo for the same collection."""
    file_by_id = {
        _doc_id(d): d for d in file_docs if _doc_id(d) is not None
    }
    live_by_id = {
        _doc_id(d): d for d in mongo_docs if _doc_id(d) is not None
    }
    file_ids = set(file_by_id.keys())
    live_ids = set(live_by_id.keys())

    added_in_mongo = sorted(live_ids - file_ids)
    removed_in_mongo = sorted(file_ids - live_ids)

    modified: List[str] = []
    for did in sorted(file_ids & live_ids):
        if _doc_hash(file_by_id[did]) != _doc_hash(live_by_id[did]):
            modified.append(did)

    return {
        "label": label,
        "file_count": len(file_ids),
        "mongo_count": len(live_ids),
        "added_in_mongo": added_in_mongo,
        "removed_in_mongo": removed_in_mongo,
        "modified_in_mongo": modified,
    }


# ---------------------------------------------------------------------------
# Findings classification
# ---------------------------------------------------------------------------


def classify_findings(report: Dict[str, Any]) -> List[Dict[str, str]]:
    """Tag everything as error / warning / info. Soft-mode: never raises."""
    findings: List[Dict[str, str]] = []

    def add(level: str, area: str, message: str) -> None:
        findings.append({"level": level, "area": area, "message": message})

    for label in (COMPONENTS_COLLECTION, ARCHIVE_COLLECTION):
        inv = report["collections"].get(label, {})
        if inv.get("missing_id_count", 0) > 0:
            add(
                "error",
                "inventory",
                f"[{label}] {inv['missing_id_count']} document(s) missing _id",
            )
        if inv.get("duplicate_ids"):
            add(
                "error",
                "inventory",
                f"[{label}] duplicate _id values: "
                f"{len(inv['duplicate_ids'])}",
            )

        sch = report["schema"].get(label, {})
        if sch.get("sheet_present_count", 0) > 0:
            add(
                "error",
                "schema",
                f"[{label}] {sch['sheet_present_count']} document(s) still "
                f"have type='sheet' (must be migrated to 'panel' before M3)",
            )
        if sch.get("non_enum_type_count", 0) > 0:
            add(
                "warning",
                "schema",
                f"[{label}] {sch['non_enum_type_count']} document(s) with "
                f"unexpected `type` value",
            )
        if sch.get("non_enum_condition_count", 0) > 0:
            add(
                "warning",
                "schema",
                f"[{label}] {sch['non_enum_condition_count']} document(s) "
                f"with unexpected `condition` value",
            )
        for f, missing in sch.get("phase1_missing_field_counts", {}).items():
            if missing > 0:
                add(
                    "error",
                    "schema",
                    f"[{label}] {missing} document(s) missing Phase 1 "
                    f"field `{f}`",
                )

    inter = report["collections"].get("id_intersection", [])
    if inter:
        add(
            "error",
            "inventory",
            f"_id overlap between components and components_archive: "
            f"{len(inter)} id(s)",
        )

    lin = report.get("lineage", {})
    if lin.get("dangling_parent_count", 0):
        add(
            "error",
            "lineage",
            f"{lin['dangling_parent_count']} child document(s) reference a "
            f"`parent_component` that does not exist in either collection",
        )
    if lin.get("self_reference_count", 0):
        add(
            "error",
            "lineage",
            f"{lin['self_reference_count']} document(s) have "
            f"`parent_component` == _id (self-reference)",
        )
    if lin.get("parent_in_live_count", 0):
        add(
            "warning",
            "lineage",
            f"{lin['parent_in_live_count']} parent reference(s) resolve to a "
            f"LIVE component (split-lineage assumes archived parent)",
        )
    if lin.get("multi_child_parent_count", 0):
        add(
            "info",
            "lineage",
            f"{lin['multi_child_parent_count']} parent_component value(s) are "
            f"referenced by more than one child (1:N split; handled by "
            f"ADR-015 `parent_identities`)",
        )

    geo = report.get("geometry", {})
    if geo.get("status") == "missing":
        add(
            "warning",
            "geometry",
            f"geometry root not found: {geo.get('geometry_root')}",
        )
    elif geo.get("status") == "ok":
        if geo.get("orphan_folders_live_count", 0):
            add(
                "warning",
                "geometry",
                f"{geo['orphan_folders_live_count']} LIVE geometry "
                f"folder(s) have no matching DB record (orphan assets)",
            )
        if geo.get("orphan_folders_archive_count", 0):
            add(
                "warning",
                "geometry",
                f"{geo['orphan_folders_archive_count']} ARCHIVE geometry "
                f"folder(s) have no matching DB record (orphan assets)",
            )
        if geo.get("live_mesh_missing_folder_count", 0):
            add(
                "error",
                "geometry",
                f"{geo['live_mesh_missing_folder_count']} live component(s) "
                f"declare inline meshes but have no geometry folder on disk "
                f"(real missing OBJ assets)",
            )
        if geo.get("archive_mesh_missing_folder_count", 0):
            add(
                "warning",
                "geometry",
                f"{geo['archive_mesh_missing_folder_count']} archived "
                f"component(s) declare inline meshes but have no geometry "
                f"folder on disk (review whether archive OBJ is needed)",
            )
        if geo.get("live_empty_no_folder_count", 0):
            add(
                "warning",
                "geometry",
                f"{geo['live_empty_no_folder_count']} live component(s) "
                f"have neither inline geometry nor a folder",
            )
        if geo.get("live_extrusion_no_folder_count", 0):
            add(
                "info",
                "geometry",
                f"{geo['live_extrusion_no_folder_count']} live component(s) "
                f"are extrusion-only (no OBJ folder expected)",
            )
        if geo.get("missing_reduced_count", 0):
            add(
                "info",
                "geometry",
                f"{geo['missing_reduced_count']} folder(s) have mesh.obj but "
                f"no mesh_reduced.obj",
            )
        if geo.get("large_mesh_count", 0):
            add(
                "info",
                "geometry",
                f"{geo['large_mesh_count']} mesh file(s) >200MB (preview "
                f"and migration cost)",
            )

    drift = report.get("drift")
    if drift:
        for label, d in drift.items():
            mods = d.get("modified_in_mongo", [])
            add_ = d.get("added_in_mongo", [])
            rem = d.get("removed_in_mongo", [])
            if mods or add_ or rem:
                add(
                    "warning",
                    "drift",
                    f"[{label}] dump vs live differs: "
                    f"+{len(add_)} / -{len(rem)} / ~{len(mods)}",
                )

    if not any(f["level"] == "error" for f in findings):
        add(
            "info",
            "summary",
            "no hard errors detected; baseline considered safe to freeze",
        )

    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _render_kv_list(items: Iterable[Tuple[str, Any]]) -> List[str]:
    return [f"- **{k}:** {v}" for k, v in items]


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# M1 — legacy baseline audit report")
    lines.append("")
    lines.append(
        "Read-only baseline of legacy `components` / `components_archive` "
        "and the geometry backup folder. Frozen input for milestones M2 "
        "(`catalog_number`) and M3 (identity/snapshot backfill)."
    )
    lines.append("")
    lines.append(
        "> Soft mode: this audit is informational. Address any `error` "
        "findings before running M2/M3 scripts."
    )
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    md = report["meta"]
    lines.extend(
        _render_kv_list(
            [
                ("Generated (UTC)", md["generated_at"]),
                ("Schema version", md["schema_version"]),
                (
                    "Components dump",
                    md["sources"]["components_file"] or "n/a",
                ),
                (
                    "Archive dump",
                    md["sources"]["archive_file"] or "n/a",
                ),
                ("Mongo cross-check", md["sources"]["mongo_enabled"]),
                (
                    "Geometry root (live)",
                    md["sources"]["geometry_root"] or "n/a",
                ),
                (
                    "Geometry root (archive)",
                    md["sources"]["geometry_root_archive"] or "n/a",
                ),
            ]
        )
    )
    lines.append("")

    # Findings
    findings = report["findings"]
    err = sum(1 for f in findings if f["level"] == "error")
    warn = sum(1 for f in findings if f["level"] == "warning")
    info = sum(1 for f in findings if f["level"] == "info")

    lines.append("## Findings summary")
    lines.append("")
    lines.append(
        f"- errors: **{err}** | warnings: **{warn}** | info: **{info}**"
    )
    lines.append("")
    if findings:
        lines.append("| Level | Area | Message |")
        lines.append("|-------|------|---------|")
        for f in findings:
            lines.append(
                f"| `{f['level']}` | `{f['area']}` | {f['message']} |"
            )
        lines.append("")

    # Inventory
    lines.append("## Collection inventory")
    lines.append("")
    for label in (COMPONENTS_COLLECTION, ARCHIVE_COLLECTION):
        inv = report["collections"].get(label, {})
        lines.append(f"### `{label}`")
        lines.append("")
        lines.extend(
            _render_kv_list(
                [
                    ("count", inv.get("count")),
                    ("unique _id count", inv.get("unique_id_count")),
                    ("missing _id count", inv.get("missing_id_count")),
                    (
                        "duplicate _id count",
                        len(inv.get("duplicate_ids") or []),
                    ),
                ]
            )
        )
        lines.append("")
    inter = report["collections"].get("id_intersection", [])
    lines.append(
        f"- **_id intersection between collections:** {len(inter)} id(s)"
    )
    lines.append("")

    # Schema
    lines.append("## Phase 1 schema hygiene")
    lines.append("")
    for label in (COMPONENTS_COLLECTION, ARCHIVE_COLLECTION):
        sch = report["schema"].get(label, {})
        lines.append(f"### `{label}`")
        lines.append("")
        th = sch.get("type_histogram", {})
        lines.append("**Type histogram:** " + (
            ", ".join(f"`{k}`={v}" for k, v in th.items()) or "(empty)"
        ))
        ch = sch.get("condition_histogram", {})
        lines.append("")
        lines.append("**Condition histogram:** " + (
            ", ".join(f"`{k}`={v}" for k, v in ch.items()) or "(empty)"
        ))
        lines.append("")
        lines.extend(
            _render_kv_list(
                [
                    ("type='sheet' remaining", sch.get("sheet_present_count")),
                    (
                        "type not in Phase 1 enum",
                        sch.get("non_enum_type_count"),
                    ),
                    (
                        "condition not in {0,1,2,3,null}",
                        sch.get("non_enum_condition_count"),
                    ),
                    (
                        "documents with `descriptors` payload",
                        sch.get("descriptors_doc_count"),
                    ),
                ]
            )
        )
        pmf = sch.get("phase1_missing_field_counts", {})
        if any(v > 0 for v in pmf.values()):
            lines.append("")
            lines.append("**Phase 1 missing-field counts:**")
            lines.append("")
            for f, n in pmf.items():
                lines.append(f"- `{f}`: {n}")
        else:
            lines.append("")
            lines.append("- All Phase 1 fields present on every document.")
        sub = sch.get("descriptors_subkeys", {})
        if sub:
            lines.append("")
            lines.append(
                "**Descriptors top-level keys (where present):** "
                + ", ".join(f"`{k}`={v}" for k, v in sub.items())
            )
        lines.append("")

    # Lineage
    lin = report.get("lineage", {})
    lines.append("## Lineage (ADR-008 `parent_component`)")
    lines.append("")
    lines.extend(
        _render_kv_list(
            [
                ("live count", lin.get("live_total")),
                ("archive count", lin.get("archive_total")),
                (
                    "_id intersection (live & archive)",
                    lin.get("intersection_count"),
                ),
                (
                    "children with parent_component set",
                    lin.get("children_with_parent_total"),
                ),
                (
                    "split-lineage candidates (parent in archive)",
                    lin.get("split_candidate_count"),
                ),
                (
                    "parent reference resolves into LIVE",
                    lin.get("parent_in_live_count"),
                ),
                (
                    "dangling parent references",
                    lin.get("dangling_parent_count"),
                ),
                ("self-references", lin.get("self_reference_count")),
                (
                    "parents with >1 children",
                    lin.get("multi_child_parent_count"),
                ),
            ]
        )
    )
    lines.append("")
    cands = lin.get("split_candidates", [])
    if cands:
        lines.append("**Split-lineage candidates (first 25 shown):**")
        lines.append("")
        lines.append("| child _id | parent _id |")
        lines.append("|-----------|------------|")
        for c in cands[:25]:
            lines.append(f"| `{c['child_id']}` | `{c['parent_id']}` |")
        if len(cands) > 25:
            lines.append("")
            lines.append(f"_…and {len(cands) - 25} more (see JSON report)._")
        lines.append("")

    # Geometry
    geo = report.get("geometry", {})
    lines.append("## Geometry backup")
    lines.append("")
    if geo.get("status") == "skipped":
        lines.append("- skipped (no `--geometry-root` passed)")
    elif geo.get("status") == "missing":
        lines.append(f"- path missing: `{geo.get('geometry_root')}`")
    else:
        live_fs = geo.get("live_file_shape_counts", {})
        arch_fs = geo.get("archive_file_shape_counts", {})
        ls = geo.get("live_shape_counts", {})
        ash = geo.get("archive_shape_counts", {})
        lines.extend(
            _render_kv_list(
                [
                    ("live root", geo.get("live_root") or "(not provided)"),
                    (
                        "archive root",
                        geo.get("archive_root") or "(not provided)",
                    ),
                    (
                        "live folders on disk",
                        geo.get("live_folder_count"),
                    ),
                    (
                        "archive folders on disk",
                        geo.get("archive_folder_count"),
                    ),
                    (
                        "live file shape counts",
                        ", ".join(f"`{k}`={v}" for k, v in live_fs.items())
                        or "(empty)",
                    ),
                    (
                        "archive file shape counts",
                        ", ".join(f"`{k}`={v}" for k, v in arch_fs.items())
                        or "(empty)",
                    ),
                    (
                        "live doc geometry shape",
                        ", ".join(f"`{k}`={v}" for k, v in ls.items())
                        or "(empty)",
                    ),
                    (
                        "archive doc geometry shape",
                        ", ".join(f"`{k}`={v}" for k, v in ash.items())
                        or "(empty)",
                    ),
                    (
                        "orphan folders (live root)",
                        geo.get("orphan_folders_live_count"),
                    ),
                    (
                        "orphan folders (archive root)",
                        geo.get("orphan_folders_archive_count"),
                    ),
                    (
                        "live: inline meshes BUT no folder (real missing)",
                        geo.get("live_mesh_missing_folder_count"),
                    ),
                    (
                        "live: extrusion-only (no folder expected)",
                        geo.get("live_extrusion_no_folder_count"),
                    ),
                    (
                        "live: empty geometry AND no folder",
                        geo.get("live_empty_no_folder_count"),
                    ),
                    (
                        "archive: inline meshes BUT no folder",
                        geo.get("archive_mesh_missing_folder_count"),
                    ),
                    (
                        "archive: extrusion-only (no folder expected)",
                        geo.get("archive_extrusion_no_folder_count"),
                    ),
                    (
                        "archive: empty geometry AND no folder",
                        geo.get("archive_empty_no_folder_count"),
                    ),
                    (
                        "folders without mesh_reduced.obj",
                        geo.get("missing_reduced_count"),
                    ),
                    (
                        "mesh files >200MB",
                        geo.get("large_mesh_count"),
                    ),
                ]
            )
        )
    lines.append("")

    # Drift
    drift = report.get("drift")
    if drift:
        lines.append("## Drift (frozen dump vs live Mongo)")
        lines.append("")
        for label, d in drift.items():
            lines.append(f"### `{label}`")
            lines.append("")
            lines.extend(
                _render_kv_list(
                    [
                        ("file count", d.get("file_count")),
                        ("mongo count", d.get("mongo_count")),
                        (
                            "added since dump",
                            len(d.get("added_in_mongo") or []),
                        ),
                        (
                            "removed since dump",
                            len(d.get("removed_in_mongo") or []),
                        ),
                        (
                            "modified since dump",
                            len(d.get("modified_in_mongo") or []),
                        ),
                    ]
                )
            )
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Regenerate this report with `python scripts/db_maintenance/"
        "m1_baseline_audit.py [--mongo] [--geometry-root <path>]`."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    components_file = (
        Path(args.components_dump) if args.components_dump else None
    )
    archive_file = Path(args.archive_dump) if args.archive_dump else None

    if components_file is None:
        components_file = DEFAULT_DUMP_DIR / "csc.components.json"
    if archive_file is None:
        archive_file = DEFAULT_DUMP_DIR / "csc.components_archive.json"

    geometry_root = Path(args.geometry_root) if args.geometry_root else None
    geometry_root_archive = (
        Path(args.geometry_root_archive)
        if args.geometry_root_archive
        else None
    )

    file_components = load_json_dump(components_file)
    file_archive = load_json_dump(archive_file)

    inv_components = audit_inventory(file_components, COMPONENTS_COLLECTION)
    inv_archive = audit_inventory(file_archive, ARCHIVE_COLLECTION)
    live_ids: Set[str] = set(inv_components["ids"])
    archive_ids: Set[str] = set(inv_archive["ids"])
    intersection = sorted(live_ids & archive_ids)

    schema_components = audit_schema(file_components, COMPONENTS_COLLECTION)
    schema_archive = audit_schema(file_archive, ARCHIVE_COLLECTION)

    field_hist_components = audit_field_histogram(file_components)
    field_hist_archive = audit_field_histogram(file_archive)

    lineage = audit_lineage(file_components, file_archive)

    geometry = audit_geometry(
        geometry_root, geometry_root_archive,
        file_components, file_archive,
    )

    drift: Optional[Dict[str, Any]] = None
    if args.mongo:
        client, db = connect_mongo()
        if db is not None:
            try:
                mongo_components = list(db[COMPONENTS_COLLECTION].find({}))
                mongo_archive = list(db[ARCHIVE_COLLECTION].find({}))
                drift = {
                    COMPONENTS_COLLECTION: audit_drift(
                        file_components, mongo_components,
                        COMPONENTS_COLLECTION,
                    ),
                    ARCHIVE_COLLECTION: audit_drift(
                        file_archive, mongo_archive, ARCHIVE_COLLECTION,
                    ),
                }
            finally:
                if client is not None:
                    client.close()

    # Strip per-doc id lists from the inventory dump to keep the JSON small;
    # the full id set is reconstructable from the source dumps if needed.
    inv_components_clean = {
        k: v for k, v in inv_components.items() if k != "ids"
    }
    inv_archive_clean = {
        k: v for k, v in inv_archive.items() if k != "ids"
    }

    report: Dict[str, Any] = {
        "meta": {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "sources": {
                "components_file": str(components_file),
                "archive_file": str(archive_file),
                "mongo_enabled": bool(args.mongo),
                "geometry_root": str(geometry_root)
                if geometry_root else None,
                "geometry_root_archive": str(geometry_root_archive)
                if geometry_root_archive else None,
            },
        },
        "collections": {
            COMPONENTS_COLLECTION: inv_components_clean,
            ARCHIVE_COLLECTION: inv_archive_clean,
            "id_intersection": intersection,
        },
        "field_histograms": {
            COMPONENTS_COLLECTION: field_hist_components,
            ARCHIVE_COLLECTION: field_hist_archive,
        },
        "schema": {
            COMPONENTS_COLLECTION: schema_components,
            ARCHIVE_COLLECTION: schema_archive,
        },
        "lineage": lineage,
        "geometry": geometry,
        "drift": drift,
    }

    report["findings"] = classify_findings(report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="M1 baseline audit (read-only)")
    ap.add_argument("--components-dump", default=None)
    ap.add_argument("--archive-dump", default=None)
    ap.add_argument(
        "--geometry-root",
        default=None,
        help="Path to the LIVE geometry backup root (folders named after "
        "legacy components._id)",
    )
    ap.add_argument(
        "--geometry-root-archive",
        default=None,
        help="Path to the ARCHIVE geometry backup root (folders named "
        "after legacy components_archive._id). If omitted, archived docs "
        "fall back to checking against --geometry-root.",
    )
    ap.add_argument(
        "--mongo",
        action="store_true",
        help="Enable live Mongo cross-check (drift detection)",
    )
    ap.add_argument(
        "--report-md",
        default=str(DEFAULT_REPORT_MD),
        help="Output path for the Markdown report",
    )
    ap.add_argument(
        "--report-json",
        default=str(DEFAULT_REPORT_JSON),
        help="Output path for the machine-readable JSON report",
    )
    args = ap.parse_args()

    report = build_report(args)

    md_path = Path(args.report_md)
    json_path = Path(args.report_json)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=False, default=str),
        encoding="utf-8",
    )

    logger.info(f"Wrote {md_path}")
    logger.info(f"Wrote {json_path}")

    err = sum(1 for f in report["findings"] if f["level"] == "error")
    warn = sum(1 for f in report["findings"] if f["level"] == "warning")
    info = sum(1 for f in report["findings"] if f["level"] == "info")
    logger.info(
        f"Findings: errors={err} warnings={warn} info={info} "
        "(soft mode: exit 0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
