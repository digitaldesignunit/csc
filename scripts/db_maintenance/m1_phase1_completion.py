#!/usr/bin/env python3
"""
M1 Phase 1 completion (live DB)
================================

Closes the **error**-level findings of the M1 baseline audit for the
49 live + 1 archive corian panels that were not fully backfilled by
``migrate_phase1_component_schema.py``.

Group rules (locked 2026-05-13)
-------------------------------

* **Group A** - ``components`` row, ``parent_component`` value set:
    - ``condition = 2``
    - ``manufactured_at = doc.created``
    - ``manufactured_precision = "exact"``  (we know the precise instant)
    - ``salvage_source = parent.salvage_source``  (copy from parent)
    - ``salvaged_at   = parent.salvaged_at``     (copy from parent)
    - ``parent_component`` already present - untouched.

* **Group B** - ``components`` row, ``parent_component`` field absent:
    - ``condition = 2``
    - ``manufactured_at = null``
    - ``manufactured_precision = "unknown"``
    - ``salvage_source = null``, ``salvaged_at = null``
    - ``parent_component = null``  (field added so M1 verification passes)

* **Group C** - ``components_archive`` row, ``parent_component`` value set:
    - same as Group A, parent looked up in archive first then live.

Lineage edge case
-----------------

One referenced parent currently lives in ``components`` instead of
``components_archive``. Before any field backfill, this script
**moves** that parent into the archive collection (preserving ``_id``
and document contents) so all 49+1 children resolve to an archived
parent, matching the split-lineage assumption used in M3.

Safety
------

* **Dry-run by default.** Pass ``--apply`` to commit.
* Field backfill only touches fields where ``$exists: False`` - no
  existing value is ever overwritten (idempotent).
* Logs every action; writes to ``logs/m1_phase1_completion.log``.

Usage
-----

::

    # Preview the plan (no writes)
    python scripts/db_maintenance/m1_phase1_completion.py

    # Commit to live Mongo
    python scripts/db_maintenance/m1_phase1_completion.py --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

from pymongo import MongoClient
from pymongo.errors import PyMongoError


REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = REPO_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _LOG_DIR / "m1_phase1_completion.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


COMPONENTS_COLLECTION = "components"
ARCHIVE_COLLECTION = "components_archive"

PHASE1_FIELDS = [
    "condition",
    "manufactured_at",
    "manufactured_precision",
    "salvage_source",
    "salvaged_at",
    "parent_component",
]

CONDITION_DEFAULT = 2
PRECISION_WITH_PARENT = "exact"
PRECISION_NO_PARENT = "unknown"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    db.list_collection_names()  # forces connection
    return client, db


# ---------------------------------------------------------------------------
# Step 1 - move live parents into archive
# ---------------------------------------------------------------------------


def collect_live_parents_referenced_by_missing_children(
    components,
    archive,
) -> Set[str]:
    """Return the set of `_id`s currently in ``components`` that are
    referenced as ``parent_component`` by any document missing Phase 1
    fields (in either collection)."""
    missing_query = {
        "$or": [{f: {"$exists": False}} for f in PHASE1_FIELDS]
    }

    referenced_parents: Set[str] = set()
    for doc in components.find(
        missing_query, {"_id": 1, "parent_component": 1}
    ):
        pid = doc.get("parent_component")
        if pid:
            referenced_parents.add(str(pid))
    for doc in archive.find(
        missing_query, {"_id": 1, "parent_component": 1}
    ):
        pid = doc.get("parent_component")
        if pid:
            referenced_parents.add(str(pid))

    archive_ids = {
        str(d["_id"])
        for d in archive.find({}, {"_id": 1})
    }
    live_ids = {
        str(d["_id"])
        for d in components.find({}, {"_id": 1})
    }

    # Parents that are currently LIVE (not archived) and referenced by
    # missing-field children
    return referenced_parents & live_ids - archive_ids


def move_to_archive(
    components,
    archive,
    parent_id: str,
    dry_run: bool,
) -> str:
    """Copy doc from `components` to `components_archive` and delete it
    from `components`. Returns 'moved' / 'skip_already_in_archive' /
    'missing'."""
    doc = components.find_one({"_id": parent_id})
    if doc is None:
        already = archive.find_one({"_id": parent_id}, {"_id": 1})
        if already:
            return "skip_already_in_archive"
        return "missing"

    if archive.find_one({"_id": parent_id}, {"_id": 1}):
        # Already in archive - just remove the live duplicate
        logger.warning(
            f"  parent {parent_id} already in archive; "
            f"deleting live duplicate"
        )
        if not dry_run:
            components.delete_one({"_id": parent_id})
        return "duplicate_removed"

    if dry_run:
        logger.info(
            f"  DRY RUN: would copy {parent_id} -> archive "
            f"and delete from components"
        )
        return "moved"

    archive.insert_one(doc)
    components.delete_one({"_id": parent_id})
    archive.update_one(
        {"_id": parent_id},
        {"$set": {"lastmodified": _iso_now()}},
    )
    return "moved"


# ---------------------------------------------------------------------------
# Step 2 - per-doc Phase 1 backfill
# ---------------------------------------------------------------------------


def compute_backfill_plan(
    doc: Dict[str, Any],
    parent_doc: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the dict of fields-to-set (only for fields that are
    currently missing on `doc`). Group selection:
        A/C: parent_component is a non-null string on the doc
        B  : parent_component field is missing entirely
    """
    has_parent_value = bool(doc.get("parent_component"))
    plan: Dict[str, Any] = {}

    def maybe_set(field: str, value: Any) -> None:
        if field not in doc:
            plan[field] = value

    if has_parent_value:
        # Group A / C
        if parent_doc is None:
            logger.warning(
                f"  {doc.get('_id')}: parent "
                f"{doc.get('parent_component')!r} not found in either "
                f"collection - cannot copy salvage fields; will set null"
            )
        parent_salvage = (
            parent_doc.get("salvage_source") if parent_doc else None
        )
        parent_salv_at = (
            parent_doc.get("salvaged_at") if parent_doc else None
        )
        maybe_set("condition", CONDITION_DEFAULT)
        maybe_set("manufactured_at", doc.get("created"))
        maybe_set("manufactured_precision", PRECISION_WITH_PARENT)
        maybe_set("salvage_source", parent_salvage)
        maybe_set("salvaged_at", parent_salv_at)
        # parent_component already a value - untouched
    else:
        # Group B
        maybe_set("condition", CONDITION_DEFAULT)
        maybe_set("manufactured_at", None)
        maybe_set("manufactured_precision", PRECISION_NO_PARENT)
        maybe_set("salvage_source", None)
        maybe_set("salvaged_at", None)
        maybe_set("parent_component", None)

    return plan


def backfill_collection(
    collection,
    collection_label: str,
    parent_lookup,  # callable(parent_id) -> Optional[Dict]
    dry_run: bool,
) -> Dict[str, int]:
    """Apply per-doc Phase 1 backfill. Returns counters."""
    missing_query = {
        "$or": [{f: {"$exists": False}} for f in PHASE1_FIELDS]
    }
    docs = list(collection.find(missing_query))
    counters = {
        "scanned": len(docs),
        "group_a_or_c": 0,
        "group_b": 0,
        "updated": 0,
        "errors": 0,
        "fields_set": 0,
    }
    logger.info(
        f"[{collection_label}] {len(docs)} document(s) missing >=1 "
        f"Phase 1 field"
    )

    for doc in docs:
        did = doc.get("_id")
        parent_id = doc.get("parent_component")
        parent_doc = (
            parent_lookup(parent_id) if parent_id else None
        )
        plan = compute_backfill_plan(doc, parent_doc)
        if not plan:
            continue
        if doc.get("parent_component"):
            counters["group_a_or_c"] += 1
        else:
            counters["group_b"] += 1

        plan["lastmodified"] = _iso_now()
        counters["fields_set"] += len(plan) - 1  # exclude lastmodified
        preview = {
            k: ("<doc.created>"
                if k == "manufactured_at" and v == doc.get("created")
                else v)
            for k, v in plan.items()
            if k != "lastmodified"
        }
        logger.info(f"  {did}: set {preview}")

        if dry_run:
            continue

        try:
            res = collection.update_one({"_id": did}, {"$set": plan})
            if res.modified_count == 1:
                counters["updated"] += 1
        except PyMongoError as e:
            logger.error(f"  {did}: update error: {e}")
            counters["errors"] += 1

    return counters


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(components, archive) -> bool:
    """Return True if all Phase 1 fields are present on every doc."""
    failed = False
    for coll, label in (
        (components, COMPONENTS_COLLECTION),
        (archive, ARCHIVE_COLLECTION),
    ):
        for f in PHASE1_FIELDS:
            n = coll.count_documents({f: {"$exists": False}})
            if n > 0:
                logger.error(
                    f"[{label}] {n} document(s) still missing `{f}`"
                )
                failed = True
    if not failed:
        logger.info(
            "Verification OK: every document carries all Phase 1 fields."
        )
    return not failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(dry_run: bool) -> int:
    mode = "DRY RUN" if dry_run else "APPLY"
    logger.info(f"=== M1 Phase 1 completion ({mode}) ===")

    client, db = connect()
    try:
        components = db[COMPONENTS_COLLECTION]
        archive = db[ARCHIVE_COLLECTION]

        # Step 1: move live parents into archive
        logger.info("--- Step 1: move live parents into archive ---")
        live_parents = collect_live_parents_referenced_by_missing_children(
            components, archive
        )
        logger.info(
            f"Found {len(live_parents)} live parent(s) referenced by "
            f"missing-field children: {sorted(live_parents)}"
        )
        moved_for_geometry: list[str] = []
        for parent_id in sorted(live_parents):
            outcome = move_to_archive(
                components, archive, parent_id, dry_run
            )
            logger.info(f"  parent {parent_id}: {outcome}")
            if outcome in ("moved", "duplicate_removed"):
                moved_for_geometry.append(parent_id)

        if moved_for_geometry:
            banner = "=" * 70
            logger.info(banner)
            logger.info(
                "GEOMETRY MOVE REQUIRED (manual step on disk):"
            )
            logger.info(
                "The following component(s) were moved from "
                "`components` to `components_archive`."
            )
            logger.info(
                "Move their geometry folder from the LIVE root to the "
                "ARCHIVE root so the M1 audit cross-check stays clean:"
            )
            logger.info("")
            for uid in moved_for_geometry:
                logger.info(f"  UUID: {uid}")
                logger.info(
                    f"    from: "
                    f"D:/01_PROJECT_WORKDATA/260512_CSC_BACKUP/"
                    f"component_geometry/{uid}/"
                )
                logger.info(
                    f"    to:   "
                    f"D:/01_PROJECT_WORKDATA/260512_CSC_BACKUP/"
                    f"component_geometry_archive/{uid}/"
                )
            logger.info(banner)
        else:
            logger.info("(no live parents needed moving)")

        # Step 2: per-doc Phase 1 backfill
        logger.info("--- Step 2: Phase 1 field backfill ---")

        def parent_lookup(pid: str) -> Optional[Dict[str, Any]]:
            return archive.find_one({"_id": pid}) or components.find_one(
                {"_id": pid}
            )

        c_counts = backfill_collection(
            components, COMPONENTS_COLLECTION, parent_lookup, dry_run
        )
        a_counts = backfill_collection(
            archive, ARCHIVE_COLLECTION, parent_lookup, dry_run
        )

        logger.info(
            f"[components]  scanned={c_counts['scanned']} "
            f"group_A/C={c_counts['group_a_or_c']} "
            f"group_B={c_counts['group_b']} "
            f"fields_set={c_counts['fields_set']} "
            f"updated={c_counts['updated']} "
            f"errors={c_counts['errors']}"
        )
        logger.info(
            f"[archive]     scanned={a_counts['scanned']} "
            f"group_A/C={a_counts['group_a_or_c']} "
            f"group_B={a_counts['group_b']} "
            f"fields_set={a_counts['fields_set']} "
            f"updated={a_counts['updated']} "
            f"errors={a_counts['errors']}"
        )

        if dry_run:
            logger.info(
                "DRY RUN complete - no writes were made. "
                "Re-run with --apply to commit."
            )
            return 0

        # Step 3: verification
        logger.info("--- Step 3: verification ---")
        return 0 if verify(components, archive) else 1

    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="M1 Phase 1 completion (live DB; idempotent)"
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
