"""M3 — identity / snapshot backfill against the live MongoDB.

Promotes every legacy row in ``components`` and ``components_archive`` into
the new collections ``component_identities`` + ``component_snapshots`` per
**ADR-015 Appendix A** (see ``future_implementation/ADRs.md``).

* **Dry-run by default.** Pass ``--apply`` to commit.
* **Read-only against legacy.** Never writes to ``components`` or
  ``components_archive``.
* **Idempotent guardrail.** Refuses to proceed when the target collections
  already contain documents (no silent overwrite).

This file currently implements **M3.2.a**: CLI + Mongo connection + loaders +
pre-flight invariant checks. The identity / snapshot doc builders and the
apply phase are added in M3.2.b / M3.2.c / M3.2.d / M3.2.e.

Mongo connection
----------------
Reads ``MONGO_URI`` from env, falling back to
``scripts/config/dbconfig.json`` (same pattern as the other
``scripts/db_maintenance/*`` scripts).

Etag recipe (locked 2026-05-16)
-------------------------------
``etag`` is recomputed fresh for every migrated snapshot:

* serialize the snapshot dict with ``etag`` and ``lastmodified`` removed,
  ``json.dumps(..., sort_keys=True, separators=(',', ':'), default=str)``;
* hash with sha256;
* hex digest -> stored as the snapshot's ``etag``.

Usage
-----
::

    conda run -n csc python \\
        scripts/db_maintenance/m3_identity_snapshot_backfill.py
    conda run -n csc python \\
        scripts/db_maintenance/m3_identity_snapshot_backfill.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# Paths (REPO_ROOT first so subsequent project-local imports resolve)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backend.apps.catalog.models import (  # noqa: E402
    ComponentIdentity,
    ComponentSnapshot,
)

LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "m3_identity_snapshot_backfill.log"

LEGACY_COMPONENTS = "components"
LEGACY_ARCHIVE = "components_archive"
TARGET_IDENTITIES = "component_identities"
TARGET_SNAPSHOTS = "component_snapshots"
COUNTERS = "counters"
COUNTER_DOC_ID = "catalog_number"

# Required-after-Phase-1 fields (legacy ComponentModel). manufactured_at,
# salvage_source, salvaged_at remain genuinely optional (unknown-provenance
# pieces); only condition + manufactured_precision are non-negotiable after
# the M1 phase-1 completion script ran.
PHASE1_REQUIRED_FIELDS = ("condition", "manufactured_precision")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("m3_backfill")
logger.setLevel(logging.INFO)
logger.handlers.clear()
_fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_sh)


# ---------------------------------------------------------------------------
# Mongo connection
# ---------------------------------------------------------------------------
def load_mongo_config() -> Dict[str, str]:
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
        with candidate.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        server = cfg.get("server")
        db = cfg.get("db")
        user = cfg.get("user")
        pwd = cfg.get("pwd")
        if not (server and db and user and pwd):
            raise RuntimeError(
                f"{candidate} incomplete (need server/db/user/pwd)"
            )
        return {"uri": f"mongodb+srv://{user}:{pwd}@{server}/{db}"}

    raise RuntimeError(
        "No Mongo config (set MONGO_URI or "
        "scripts/config/dbconfig.json with server/db/user/pwd)."
    )


def connect():
    cfg = load_mongo_config()
    client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=10000)
    db = client.get_default_database()
    if db is None:
        db_name = cfg["uri"].split("/")[-1].split("?")[0]
        db = client[db_name]
    db.list_collection_names()
    return client, db


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_legacy_rows(db) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (live, archive) legacy rows. Live first, archive second."""
    live = list(db[LEGACY_COMPONENTS].find({}))
    archive = list(db[LEGACY_ARCHIVE].find({}))
    return live, archive


def load_counter_doc(db) -> Optional[Dict[str, Any]]:
    return db[COUNTERS].find_one({"_id": COUNTER_DOC_ID})


def count_target_docs(db) -> Dict[str, int]:
    return {
        TARGET_IDENTITIES: db[TARGET_IDENTITIES].count_documents({}),
        TARGET_SNAPSHOTS: db[TARGET_SNAPSHOTS].count_documents({}),
    }


# ---------------------------------------------------------------------------
# Pre-flight invariant checks
# ---------------------------------------------------------------------------
def check_catalog_numbers(rows: List[Dict[str, Any]]) -> List[str]:
    """Return list of _ids missing or non-integer catalog_number."""
    bad: List[str] = []
    for row in rows:
        cn = row.get("catalog_number")
        if cn is None or not isinstance(cn, int):
            bad.append(str(row.get("_id")))
    return bad


def check_phase1_fields(
    rows: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Return {field: [_ids where the field key is genuinely absent]}.

    `None` is a legitimate value for these `Optional[...]` legacy fields and
    is preserved through migration to the new model (which also declares
    them as `Optional`). Only docs whose field key is missing entirely fail
    pre-flight - that indicates the Phase 1 schema migration never ran for
    the row.
    """
    missing: Dict[str, List[str]] = {f: [] for f in PHASE1_REQUIRED_FIELDS}
    for row in rows:
        for field in PHASE1_REQUIRED_FIELDS:
            if field not in row:
                missing[field].append(str(row.get("_id")))
    return {f: ids for f, ids in missing.items() if ids}


def count_phase1_null_values(
    rows: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Informational counts of how many rows hold `None` per Phase 1 field."""
    counts: Dict[str, int] = {f: 0 for f in PHASE1_REQUIRED_FIELDS}
    for row in rows:
        for field in PHASE1_REQUIRED_FIELDS:
            if field in row and row[field] is None:
                counts[field] += 1
    return counts


def check_geometry_non_empty(
    rows: List[Dict[str, Any]],
) -> List[str]:
    """Return list of _ids whose geometry has no usable representation.

    The new model requires at least one of ``meshes`` / ``point_clouds`` /
    ``extrusions`` to be non-empty. Legacy rows only carry ``meshes`` and/or
    ``extrusion`` (singular); we treat ``extrusion: null`` and
    ``meshes: []`` / ``meshes: null`` as "empty".
    """
    bad: List[str] = []
    for row in rows:
        geom = row.get("geometry") or {}
        meshes = geom.get("meshes") or []
        extrusion = geom.get("extrusion")
        if not meshes and extrusion is None:
            bad.append(str(row.get("_id")))
    return bad


def check_targets_empty(db) -> Dict[str, int]:
    """Return {collection: count} for any non-empty target collection."""
    counts = count_target_docs(db)
    return {name: n for name, n in counts.items() if n > 0}


def check_counter_doc(
    db, all_rows: List[Dict[str, Any]]
) -> Optional[str]:
    """Return an error message string if the counter doc is invalid."""
    doc = load_counter_doc(db)
    if doc is None:
        return (
            f"counters._id == '{COUNTER_DOC_ID}' is missing "
            "(M2 should have created it)."
        )
    next_value = doc.get("next_value")
    if next_value is None or not isinstance(next_value, int):
        return (
            f"counters._id == '{COUNTER_DOC_ID}' has invalid "
            f"next_value: {next_value!r}"
        )
    cns = [r.get("catalog_number") for r in all_rows
           if isinstance(r.get("catalog_number"), int)]
    if not cns:
        return None
    max_cn = max(cns)
    if next_value <= max_cn:
        return (
            f"counter next_value ({next_value}) <= max(catalog_number) "
            f"({max_cn}); expected next_value > max."
        )
    return None


# ---------------------------------------------------------------------------
# Doc builders (M3.2.b)
# ---------------------------------------------------------------------------
def _translate_mesh(legacy_mesh: Dict[str, Any]) -> Dict[str, Any]:
    """Rename legacy mesh short keys to descriptive ones."""
    out: Dict[str, Any] = {
        "vertices": legacy_mesh.get("v"),
        "faces": legacy_mesh.get("f"),
    }
    legacy_colors = legacy_mesh.get("c")
    if legacy_colors is not None:
        out["colors"] = legacy_colors
    return out


def translate_geometry(
    legacy_geometry: Dict[str, Any],
    legacy_marker_points: Optional[List[List[float]]],
) -> Dict[str, Any]:
    """Build the new geometry dict from legacy geometry + root marker_points.

    Legacy:
        geometry: {meshes: [{v, f, c}], extrusion: {profile, height} | None}
        marker_points: [[x, y, z], ...] | None   (root-level)

    New:
        geometry: {
            meshes: [{vertices, faces, colors}] | None,
            extrusions: [{profile, height}] | None,
            point_clouds: None,
            marker_points: [[x, y, z], ...] | None,
        }
    """
    out: Dict[str, Any] = {}

    legacy_meshes = legacy_geometry.get("meshes") or []
    if legacy_meshes:
        out["meshes"] = [_translate_mesh(m) for m in legacy_meshes]

    legacy_extrusion = legacy_geometry.get("extrusion")
    if legacy_extrusion is not None:
        out["extrusions"] = [legacy_extrusion]

    if legacy_marker_points:
        out["marker_points"] = legacy_marker_points

    return out


def compute_etag(snapshot_doc: Dict[str, Any]) -> str:
    """Fresh sha256 over canonical JSON of the snapshot, excluding `etag`
    and `lastmodified`. Stable across re-runs for identical content.
    """
    payload = {
        k: v for k, v in snapshot_doc.items()
        if k not in ("etag", "lastmodified")
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_identity_doc(legacy_row: Dict[str, Any]) -> Dict[str, Any]:
    """One-to-one identity doc from a legacy row.

    Cross-doc fields `consumed_at` and `current_snapshot_id` are left at
    `None` here; they are wired in M3.2.c after every snapshot exists.
    """
    parent_component = legacy_row.get("parent_component")
    parent_identities: Optional[List[str]] = None
    if parent_component:
        parent_identities = [str(parent_component)]

    return {
        "_id": legacy_row["_id"],
        "catalog_number": legacy_row["catalog_number"],
        "type": legacy_row["type"],
        "material": legacy_row["material"],
        "dataset": legacy_row["dataset"],
        "manufactured_at": legacy_row.get("manufactured_at"),
        "manufactured_precision": legacy_row.get("manufactured_precision"),
        "salvage_source": legacy_row.get("salvage_source"),
        "salvaged_at": legacy_row.get("salvaged_at"),
        "reserved": legacy_row.get("reserved", ""),
        "attributes": legacy_row.get("attributes") or {},
        "parent_identities": parent_identities,
        "consumed_at": None,
        "current_snapshot_id": None,
        "created": legacy_row["created"],
        "lastmodified": legacy_row["lastmodified"],
    }


def build_snapshot_doc(
    legacy_row: Dict[str, Any], snapshot_id: str
) -> Dict[str, Any]:
    """Build a v=0 snapshot doc from a legacy row.

    `snapshot_id` is a fresh UUID supplied by the caller.
    `identity_id` is the legacy row's `_id`.
    """
    legacy_geometry = legacy_row.get("geometry") or {}
    legacy_markers = legacy_row.get("marker_points")
    new_geometry = translate_geometry(legacy_geometry, legacy_markers)

    doc: Dict[str, Any] = {
        "_id": snapshot_id,
        "identity_id": legacy_row["_id"],
        "version": 0,
        "virtual": False,
        "name": legacy_row.get("name", "Unnamed Component"),
        "geometry": new_geometry,
        "descriptors": legacy_row.get("descriptors") or {},
        "bbx": legacy_row["bbx"],
        "bbx_origin": legacy_row["bbx_origin"],
        "complexity": legacy_row["complexity"],
        "fragment": legacy_row["fragment"],
        "assembly": legacy_row["assembly"],
        "condition": legacy_row.get("condition"),
        "color": legacy_row.get("color"),
        "location": legacy_row.get("location"),
        "processes": legacy_row.get("processes") or {},
        "iframe": legacy_row["iframe"],
        "pca_frame": legacy_row["pca_frame"],
        "validated": legacy_row["validated"],
        "created": legacy_row["created"],
        "lastmodified": legacy_row["lastmodified"],
    }
    doc["etag"] = compute_etag(doc)
    return doc


def build_all_docs(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build identity + snapshot dicts for every legacy row.

    Returns (identities, snapshots) in matching order; snapshots[i] is the
    v=0 snapshot for identities[i].
    """
    identities: List[Dict[str, Any]] = []
    snapshots: List[Dict[str, Any]] = []
    for row in rows:
        identity = build_identity_doc(row)
        snapshot_id = str(uuid.uuid4())
        snapshot = build_snapshot_doc(row, snapshot_id)
        identities.append(identity)
        snapshots.append(snapshot)
    return identities, snapshots


def validate_snapshots(
    snapshots: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Validate each snapshot dict against `ComponentSnapshot`.

    Returns a list of {_id, identity_id, error} dicts for any failures.
    Identity validation is deferred to M3.2.d because identities still
    lack `current_snapshot_id` at this stage.
    """
    errors: List[Dict[str, str]] = []
    for doc in snapshots:
        try:
            ComponentSnapshot.model_validate(doc)
        except Exception as exc:
            errors.append({
                "_id": str(doc.get("_id")),
                "identity_id": str(doc.get("identity_id")),
                "error": str(exc)[:400],
            })
    return errors


def summarize_build(
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    snapshot_errors: List[Dict[str, str]],
) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info("BUILD SUMMARY (M3.2.b)")
    logger.info("=" * 72)
    logger.info(f"identities built: {len(identities)}")
    logger.info(f"snapshots built:  {len(snapshots)}")

    with_parent = sum(1 for d in identities if d["parent_identities"])
    logger.info(f"identities with parent_identities set: {with_parent}")

    geom_mesh_only = 0
    geom_extr_only = 0
    geom_both = 0
    with_markers = 0
    for s in snapshots:
        g = s["geometry"]
        has_m = bool(g.get("meshes"))
        has_e = bool(g.get("extrusions"))
        if has_m and has_e:
            geom_both += 1
        elif has_m:
            geom_mesh_only += 1
        elif has_e:
            geom_extr_only += 1
        if g.get("marker_points"):
            with_markers += 1
    logger.info(
        f"snapshot geometry shape: "
        f"mesh_only={geom_mesh_only}  "
        f"extrusion_only={geom_extr_only}  "
        f"both={geom_both}"
    )
    logger.info(f"snapshots with marker_points: {with_markers}")

    etag_set = {s["etag"] for s in snapshots}
    logger.info(
        f"unique etags: {len(etag_set)} (expect {len(snapshots)})"
    )
    if len(etag_set) != len(snapshots):
        logger.error(
            "ETAG COLLISION: two or more snapshots produced the same "
            "sha256 - investigate before applying."
        )

    if snapshot_errors:
        logger.error("")
        logger.error(
            f"SNAPSHOT VALIDATION FAILURES: {len(snapshot_errors)}"
        )
        for err in snapshot_errors[:10]:
            logger.error(
                f"  snapshot _id={err['_id']} "
                f"identity_id={err['identity_id']}"
            )
            logger.error(f"    {err['error']}")
        if len(snapshot_errors) > 10:
            logger.error(
                f"  ... and {len(snapshot_errors) - 10} more"
            )
    else:
        logger.info("")
        logger.info(
            "OK    every built snapshot passes ComponentSnapshot validation"
        )


# ---------------------------------------------------------------------------
# Cross-doc wiring (M3.2.c)
# ---------------------------------------------------------------------------
def wire_current_snapshot_ids(
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> None:
    """Set `identity['current_snapshot_id'] = snapshot['_id']` in place.

    Pairs are matched by list position; identity[i] gets snapshot[i].
    """
    if len(identities) != len(snapshots):
        raise ValueError(
            f"length mismatch: {len(identities)} identities vs "
            f"{len(snapshots)} snapshots"
        )
    for ident, snap in zip(identities, snapshots):
        if ident["_id"] != snap["identity_id"]:
            raise ValueError(
                f"identity_id mismatch: identity={ident['_id']!r} "
                f"vs snapshot.identity_id={snap['identity_id']!r}"
            )
        ident["current_snapshot_id"] = snap["_id"]


def wire_consumed_at(
    identities: List[Dict[str, Any]],
    live_count: int,
) -> Dict[str, int]:
    """Compute and set `consumed_at` in place per ADR-015 Appendix A.

    * identities sourced from live `components` (first `live_count` entries):
      `consumed_at = None`.
    * identities sourced from `components_archive`:
      `consumed_at = min(child.created)` when at least one other identity
      references it via `parent_identities`; otherwise the identity's own
      `lastmodified`.

    Returns a breakdown for reporting.
    """
    counts: Dict[str, int] = {
        "live_null": 0,
        "archive_from_child": 0,
        "archive_from_lastmodified": 0,
    }

    parent_to_children: Dict[str, List[Dict[str, Any]]] = {}
    for ident in identities:
        for parent_id in ident.get("parent_identities") or []:
            parent_to_children.setdefault(parent_id, []).append(ident)

    for idx, ident in enumerate(identities):
        if idx < live_count:
            counts["live_null"] += 1
            continue
        children = parent_to_children.get(ident["_id"], [])
        if children:
            ident["consumed_at"] = min(c["created"] for c in children)
            counts["archive_from_child"] += 1
        else:
            ident["consumed_at"] = ident["lastmodified"]
            counts["archive_from_lastmodified"] += 1
    return counts


def validate_identities(
    identities: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Validate each identity dict against `ComponentIdentity`."""
    errors: List[Dict[str, str]] = []
    for doc in identities:
        try:
            ComponentIdentity.model_validate(doc)
        except Exception as exc:
            errors.append({
                "_id": str(doc.get("_id")),
                "error": str(exc)[:400],
            })
    return errors


def validate_cross_references(
    identities: List[Dict[str, Any]],
) -> List[str]:
    """Every entry in `parent_identities` must resolve to a known identity."""
    known = {ident["_id"] for ident in identities}
    errors: List[str] = []
    for ident in identities:
        for parent_id in ident.get("parent_identities") or []:
            if parent_id not in known:
                errors.append(
                    f"identity {ident['_id']} references unknown parent "
                    f"{parent_id}"
                )
    return errors


def summarize_wiring(
    identities: List[Dict[str, Any]],
    consumed_counts: Dict[str, int],
    identity_errors: List[Dict[str, str]],
    crossref_errors: List[str],
) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info("CROSS-DOC WIRING SUMMARY (M3.2.c)")
    logger.info("=" * 72)
    logger.info(
        f"identities with current_snapshot_id set: "
        f"{sum(1 for d in identities if d.get('current_snapshot_id'))}"
    )
    logger.info(
        "consumed_at distribution: "
        f"live_null={consumed_counts['live_null']}  "
        f"archive_from_child={consumed_counts['archive_from_child']}  "
        f"archive_from_lastmodified="
        f"{consumed_counts['archive_from_lastmodified']}"
    )

    if crossref_errors:
        logger.error("")
        logger.error(
            f"CROSS-REFERENCE FAILURES: {len(crossref_errors)} "
            "parent_identities entries point at unknown identities."
        )
        for msg in crossref_errors[:10]:
            logger.error(f"  {msg}")
        if len(crossref_errors) > 10:
            logger.error(
                f"  ... and {len(crossref_errors) - 10} more"
            )
    else:
        logger.info(
            "OK    every parent_identities[i] resolves to a built identity"
        )

    if identity_errors:
        logger.error("")
        logger.error(
            f"IDENTITY VALIDATION FAILURES: {len(identity_errors)}"
        )
        for err in identity_errors[:10]:
            logger.error(f"  identity _id={err['_id']}")
            logger.error(f"    {err['error']}")
        if len(identity_errors) > 10:
            logger.error(
                f"  ... and {len(identity_errors) - 10} more"
            )
    else:
        logger.info(
            "OK    every built identity passes ComponentIdentity validation"
        )


# ---------------------------------------------------------------------------
# Apply phase (M3.2.d)
# ---------------------------------------------------------------------------
def apply_writes(
    db,
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Insert built docs into the target collections.

    Inserts identities first, then snapshots. Uses `ordered=True` so that
    on any failure pymongo stops at the first offending doc; the user can
    then drop both target collections and rerun (idempotency is enforced
    via the pre-flight `targets_empty` check).
    """
    logger.info("Inserting identities...")
    result_ids = db[TARGET_IDENTITIES].insert_many(identities, ordered=True)
    inserted_ids_count = len(result_ids.inserted_ids)
    logger.info(f"  inserted {inserted_ids_count} identities")

    logger.info("Inserting snapshots...")
    result_snaps = db[TARGET_SNAPSHOTS].insert_many(snapshots, ordered=True)
    inserted_snaps_count = len(result_snaps.inserted_ids)
    logger.info(f"  inserted {inserted_snaps_count} snapshots")

    return {
        "identities_inserted": inserted_ids_count,
        "snapshots_inserted": inserted_snaps_count,
    }


def create_indexes(db) -> List[str]:
    """Create the locked indexes on the new collections.

    Returns a list of index names that were created (or already present).
    """
    names: List[str] = []
    logger.info("Creating indexes on component_identities...")
    names.append(
        db[TARGET_IDENTITIES].create_index(
            "catalog_number", unique=True, name="catalog_number_unique"
        )
    )
    names.append(
        db[TARGET_IDENTITIES].create_index(
            "parent_identities", sparse=True, name="parent_identities_sparse"
        )
    )
    names.append(
        db[TARGET_IDENTITIES].create_index(
            "consumed_at", sparse=True, name="consumed_at_sparse"
        )
    )
    logger.info("Creating indexes on component_snapshots...")
    names.append(
        db[TARGET_SNAPSHOTS].create_index(
            [("identity_id", 1), ("version", 1)],
            unique=True,
            name="identity_version_unique",
        )
    )
    for n in names:
        logger.info(f"  ok: {n}")
    return names


def verify_after_write(
    db,
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> bool:
    """Sanity checks after the apply step. Returns True on success."""
    logger.info("Post-write verification...")
    ok = True

    written_ids = db[TARGET_IDENTITIES].count_documents({})
    if written_ids != len(identities):
        logger.error(
            f"FAIL  identity count mismatch: written={written_ids} "
            f"expected={len(identities)}"
        )
        ok = False
    else:
        logger.info(f"OK    identities written: {written_ids}")

    written_snaps = db[TARGET_SNAPSHOTS].count_documents({})
    if written_snaps != len(snapshots):
        logger.error(
            f"FAIL  snapshot count mismatch: written={written_snaps} "
            f"expected={len(snapshots)}"
        )
        ok = False
    else:
        logger.info(f"OK    snapshots written: {written_snaps}")

    null_consumed = db[TARGET_IDENTITIES].count_documents(
        {"consumed_at": None}
    )
    expected_null = sum(
        1 for d in identities if d.get("consumed_at") is None
    )
    if null_consumed != expected_null:
        logger.error(
            f"FAIL  consumed_at=null count mismatch: written={null_consumed}"
            f" expected={expected_null}"
        )
        ok = False
    else:
        logger.info(
            f"OK    consumed_at=null on {null_consumed} identities "
            "(matches build)"
        )

    bad_currents = db[TARGET_IDENTITIES].count_documents(
        {"current_snapshot_id": None}
    )
    if bad_currents:
        logger.error(
            f"FAIL  {bad_currents} identities have current_snapshot_id=None"
        )
        ok = False
    else:
        logger.info("OK    every written identity has current_snapshot_id")

    sample_size = min(10, len(identities))
    if sample_size:
        sample = identities[:sample_size]
        for src in sample:
            fetched = db[TARGET_IDENTITIES].find_one({"_id": src["_id"]})
            if fetched is None:
                logger.error(
                    f"FAIL  sample identity {src['_id']} not found after "
                    "write"
                )
                ok = False
                continue
            if fetched.get("catalog_number") != src["catalog_number"]:
                logger.error(
                    f"FAIL  sample identity {src['_id']} catalog_number "
                    f"drift: written={fetched.get('catalog_number')} "
                    f"expected={src['catalog_number']}"
                )
                ok = False
        if ok:
            logger.info(
                f"OK    first {sample_size} identities round-trip cleanly"
            )

    return ok


# ---------------------------------------------------------------------------
# Pre-flight orchestrator
# ---------------------------------------------------------------------------
def preflight(
    db,
    live: List[Dict[str, Any]],
    archive: List[Dict[str, Any]],
) -> bool:
    """Run all invariant checks. Returns True if everything passes."""
    logger.info("")
    logger.info("=" * 72)
    logger.info("PRE-FLIGHT CHECKS")
    logger.info("=" * 72)

    failed = False
    all_rows = live + archive
    logger.info(
        f"Legacy rows loaded: live={len(live)}  archive={len(archive)}  "
        f"total={len(all_rows)}"
    )

    # 1. catalog_number invariant
    missing_cn = check_catalog_numbers(all_rows)
    if missing_cn:
        failed = True
        logger.error(
            f"FAIL  {len(missing_cn)} rows missing catalog_number "
            "(M2 must run first)"
        )
        for _id in missing_cn[:10]:
            logger.error(f"      - {_id}")
        if len(missing_cn) > 10:
            logger.error(f"      ... and {len(missing_cn) - 10} more")
    else:
        logger.info("OK    every legacy row has catalog_number")

    # 2. phase 1 fields invariant (only fail on truly missing keys; `None`
    # is a legitimate value preserved through migration)
    missing_p1 = check_phase1_fields(all_rows)
    if missing_p1:
        failed = True
        logger.error(
            "FAIL  some legacy rows missing required Phase 1 fields "
            "(M1 phase1 completion must run first):"
        )
        for field, ids in missing_p1.items():
            logger.error(f"      - {field}: {len(ids)} rows")
            for _id in ids[:5]:
                logger.error(f"          {_id}")
            if len(ids) > 5:
                logger.error(f"          ... and {len(ids) - 5} more")
    else:
        logger.info(
            "OK    every legacy row has the required Phase 1 field keys "
            "present (condition, manufactured_precision)"
        )

    null_counts = count_phase1_null_values(all_rows)
    null_nonzero = {f: n for f, n in null_counts.items() if n > 0}
    if null_nonzero:
        logger.info(
            "INFO  Phase 1 fields explicitly set to None "
            "(carried through to identity / snapshot as-is):"
        )
        for field, n in null_nonzero.items():
            logger.info(f"      - {field}: {n} rows")

    # 3. geometry has at least one representation
    empty_geom = check_geometry_non_empty(all_rows)
    if empty_geom:
        failed = True
        logger.error(
            f"FAIL  {len(empty_geom)} rows have empty geometry "
            "(no meshes and no extrusion); the new ComponentSnapshot "
            "model requires at least one representation per snapshot."
        )
        for _id in empty_geom[:10]:
            logger.error(f"      - {_id}")
        if len(empty_geom) > 10:
            logger.error(f"      ... and {len(empty_geom) - 10} more")
    else:
        logger.info("OK    every legacy row has at least one geometry rep")

    # 4. counter doc invariant
    counter_err = check_counter_doc(db, all_rows)
    if counter_err:
        failed = True
        logger.error(f"FAIL  counter doc: {counter_err}")
    else:
        doc = load_counter_doc(db)
        logger.info(
            f"OK    counter doc present; next_value={doc.get('next_value')}"
        )

    # 5. target collections must be empty (idempotency guard)
    nonempty_targets = check_targets_empty(db)
    if nonempty_targets:
        failed = True
        for name, n in nonempty_targets.items():
            logger.error(
                f"FAIL  target collection '{name}' is non-empty "
                f"({n} docs); refuse to proceed (no silent overwrite)."
            )
    else:
        logger.info(
            f"OK    target collections '{TARGET_IDENTITIES}' and "
            f"'{TARGET_SNAPSHOTS}' are empty"
        )

    logger.info("")
    if failed:
        logger.error("PRE-FLIGHT: FAILED")
    else:
        logger.info("PRE-FLIGHT: OK")
    return not failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run(dry_run: bool) -> int:
    logger.info("=" * 72)
    logger.info("M3 - identity / snapshot backfill")
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    logger.info("=" * 72)

    try:
        client, db = connect()
    except (PyMongoError, RuntimeError) as exc:
        logger.error(f"Mongo connection failed: {exc}")
        return 1

    exit_code = 0
    try:
        live, archive = load_legacy_rows(db)
        ok = preflight(db, live, archive)
        if not ok:
            logger.error("")
            logger.error("Aborting: fix pre-flight failures and re-run.")
            return 2

        all_rows = live + archive
        live_count = len(live)
        identities, snapshots = build_all_docs(all_rows)
        snapshot_errors = validate_snapshots(snapshots)
        summarize_build(identities, snapshots, snapshot_errors)

        if snapshot_errors:
            logger.error("")
            logger.error(
                "Aborting: snapshot validation failed. Inspect the errors "
                "above and rerun once the legacy data or builder is fixed."
            )
            return 3

        wire_current_snapshot_ids(identities, snapshots)
        consumed_counts = wire_consumed_at(identities, live_count)
        crossref_errors = validate_cross_references(identities)
        identity_errors = validate_identities(identities)
        summarize_wiring(
            identities, consumed_counts, identity_errors, crossref_errors
        )

        if identity_errors or crossref_errors:
            logger.error("")
            logger.error(
                "Aborting: identity validation or cross-reference checks "
                "failed. Inspect the errors above and rerun once the "
                "underlying issue is addressed."
            )
            return 4

        if dry_run:
            logger.info("")
            logger.info(
                "Dry-run complete. Re-run with --apply to commit the "
                "writes (insert_many + indexes + post-write verify)."
            )
            return 0

        logger.info("")
        logger.info("=" * 72)
        logger.info("APPLY (M3.2.d)")
        logger.info("=" * 72)
        try:
            apply_writes(db, identities, snapshots)
            create_indexes(db)
        except PyMongoError as exc:
            logger.error("")
            logger.error(f"APPLY FAILED: {exc}")
            logger.error(
                "Partial writes may exist. Drop the target collections "
                f"({TARGET_IDENTITIES}, {TARGET_SNAPSHOTS}) and re-run."
            )
            return 5

        ok = verify_after_write(db, identities, snapshots)
        if not ok:
            logger.error("")
            logger.error(
                "POST-WRITE VERIFICATION FAILED. Investigate before "
                "treating M3 as complete."
            )
            return 6

        logger.info("")
        logger.info("M3.2 COMPLETE: identity + snapshot backfill applied.")
    finally:
        client.close()

    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "M3 identity / snapshot backfill (live DB; dry-run by default; "
            "ADR-015 Appendix A)."
        )
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes (default is dry-run)",
    )
    args = ap.parse_args()
    return run(dry_run=not args.apply)


if __name__ == "__main__":
    sys.exit(main())
