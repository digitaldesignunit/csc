#!/usr/bin/env python3
"""
Phase 1 Component Schema Migration
==================================

Implements the data-side portion of Phase 1 of the CSC roadmap
(see IMPLEMENTATION_PLAN.md, ADR-002 and the Phase 1 Migration Strategy).

What this script does
---------------------

1. `sheet -> panel` type migration
   - Rewrites every document in `components` and `components_archive`
     (archive collection if it exists) where `type == "sheet"` to
     `type == "panel"`.
   - Touches `lastmodified` so downstream caches invalidate.

2. Legacy type normalization
   - Rejects (reports) any documents whose `type` is not in the new
     Phase 1 enum. It does NOT silently reclassify those documents;
     the operator must decide (usually: retype to `other` by hand).

3. Phase 1 field backfill
   - Explicitly sets the new Phase 1 fields on every pre-Phase-1
     document so the schema is consistent across the collection
     (no mix of "missing" vs "present" keys). Fields touched:
       * `condition`
       * `manufactured_at`
       * `manufactured_precision`
       * `salvage_source`
       * `salvaged_at`
       * `parent_component`
   - All non-`condition` fields are backfilled to `null` (they are
     unknown by definition for existing records).
   - `condition` backfill default is configurable via
     `--condition-default {null,0,1,2,3}` because the default value
     is still an open decision in IMPLEMENTATION_PLAN.md. It
     defaults to `null` so no implicit grade is assigned. When the
     team decides, rerun with the chosen default (the backfill is
     idempotent: it only sets fields that are currently absent).
   - Fields that already have a value on a document are never
     overwritten by this backfill step.

4. Read-side safety
   - The API (`get_components`, `get_component`) falls back to the
     raw Mongo document if Pydantic validation fails, so stale
     `sheet` records (if any slip through) will still be readable
     during the cutover window. After this script completes, there
     should be zero `sheet` documents.

Usage
-----

    python scripts/db_maintenance/migrate_phase1_component_schema.py
    python scripts/db_maintenance/migrate_phase1_component_schema.py --dry-run
    python scripts/db_maintenance/migrate_phase1_component_schema.py \
        --condition-default 2

Requirements
------------

- `pymongo`
- MongoDB connection via `MONGO_URI` env var, or
  `src/backend/config/dbconfig.json` with server/db/user/pwd keys.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# -----------------------------------------------------------------------------
# Constants (mirror src/backend/apps/catalog/models.py Phase 1 taxonomy)
# -----------------------------------------------------------------------------

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

LEGACY_TYPE_MAP: Dict[str, str] = {
    "sheet": "panel",
}

# Collections touched by this migration. The archive collection is
# written to by apps.catalog.api.archive and uses the name
# `components_archive`.
COMPONENTS_COLLECTION = "components"
ARCHIVE_COLLECTION = "components_archive"

# Phase 1 fields that must exist on every component document.
# Order matches IMPLEMENTATION_PLAN.md Phase 1 scope. Only `condition`
# has a configurable default; everything else backfills to null.
PHASE1_NEW_FIELDS: List[str] = [
    "condition",
    "manufactured_at",
    "manufactured_precision",
    "salvage_source",
    "salvaged_at",
    "parent_component",
]

ALLOWED_CONDITION_VALUES: List[int] = [0, 1, 2, 3]

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("migrate_phase1_component_schema.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Config loading (mirrors pattern used in other db_maintenance scripts)
# -----------------------------------------------------------------------------

def load_config() -> Optional[Dict[str, str]]:
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        return {"uri": mongo_uri}

    config_path = os.path.normpath(os.path.abspath(
        os.path.join("..", "config", "dbconfig.json")
    ))
    logger.info(f"Config path: {config_path}")
    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        server = cfg.get("server")
        db = cfg.get("db")
        user = cfg.get("user")
        pwd = cfg.get("pwd")
        if not (server and db and user and pwd):
            logger.error("Incomplete dbconfig.json (need server/db/user/pwd)")
            return None
        uri = f"mongodb+srv://{user}:{pwd}@{server}/{db}"
        return {"uri": uri}
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        return None


def connect():
    cfg = load_config()
    if not cfg:
        raise RuntimeError(
            "No MongoDB configuration found "
            "(set MONGO_URI or provide dbconfig.json)"
        )
    client = MongoClient(cfg["uri"])
    db = client.get_default_database()
    if db is None:
        db_name = cfg["uri"].split("/")[-1].split("?")[0]
        db = client[db_name]
    return client, db


# -----------------------------------------------------------------------------
# Migration steps
# -----------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def migrate_collection_types(
    collection,
    collection_label: str,
    dry_run: bool,
) -> Dict[str, int]:
    """
    Rewrite legacy `type` values in-place.

    Returns a dict of counters: matched, migrated, errors.
    """
    counters = {"matched": 0, "migrated": 0, "errors": 0}

    for legacy_type, canonical_type in LEGACY_TYPE_MAP.items():
        query = {"type": legacy_type}
        docs = list(collection.find(query, {"_id": 1}))
        counters["matched"] += len(docs)

        if not docs:
            logger.info(
                f"[{collection_label}] no documents with "
                f"type='{legacy_type}'"
            )
            continue

        logger.info(
            f"[{collection_label}] found {len(docs)} documents with "
            f"type='{legacy_type}' -> '{canonical_type}'"
        )

        if dry_run:
            logger.info(
                f"[{collection_label}] DRY RUN: would rewrite "
                f"{len(docs)} documents"
            )
            continue

        now_iso = _iso_now()
        for doc in docs:
            try:
                res = collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "type": canonical_type,
                        "lastmodified": now_iso,
                    }},
                )
                if res.modified_count > 0:
                    counters["migrated"] += 1
                else:
                    logger.warning(
                        f"[{collection_label}] no modification for "
                        f"_id={doc['_id']}"
                    )
            except PyMongoError as e:
                logger.error(
                    f"[{collection_label}] mongo error for "
                    f"_id={doc.get('_id')}: {e}"
                )
                counters["errors"] += 1

    return counters


def report_unexpected_types(collection, collection_label: str) -> List[str]:
    """
    Report any `type` values that are not in the new enum and not in the
    legacy migration map. These need human review.
    """
    allowed = set(ALLOWED_COMPONENT_TYPES) | set(LEGACY_TYPE_MAP.keys())
    pipeline = [
        {"$group": {"_id": "$type", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]
    distinct = list(collection.aggregate(pipeline))

    unexpected: List[str] = []
    for row in distinct:
        t = row.get("_id")
        n = row.get("n")
        if t is None:
            logger.warning(
                f"[{collection_label}] {n} documents with missing `type`"
            )
            unexpected.append("<missing>")
            continue
        if t not in allowed:
            logger.warning(
                f"[{collection_label}] {n} documents with unexpected "
                f"type='{t}' (not in Phase 1 enum, not a legacy alias)"
            )
            unexpected.append(t)
    return unexpected


def backfill_phase1_fields(
    collection,
    collection_label: str,
    dry_run: bool,
    condition_default: Optional[int],
) -> Dict[str, Dict[str, int]]:
    """
    Ensure every document carries the Phase 1 fields.

    - Only sets a field on documents where that field is currently
      absent (`$exists: False`). Existing values are never overwritten.
    - `condition` uses `condition_default` (may be None); all other
      fields use `None`.

    Returns a dict field -> {missing, set}.
    """
    results: Dict[str, Dict[str, int]] = {}

    for field in PHASE1_NEW_FIELDS:
        default_value: Any
        if field == "condition":
            default_value = condition_default
        else:
            default_value = None

        query = {field: {"$exists": False}}
        try:
            missing = collection.count_documents(query)
        except PyMongoError as e:
            logger.error(
                f"[{collection_label}] count error for field "
                f"'{field}': {e}"
            )
            results[field] = {"missing": -1, "set": 0}
            continue

        results[field] = {"missing": missing, "set": 0}

        if missing == 0:
            logger.info(
                f"[{collection_label}] {field}: already present on all "
                "documents (nothing to backfill)"
            )
            continue

        rendered = "null" if default_value is None else repr(default_value)
        logger.info(
            f"[{collection_label}] {field}: {missing} documents missing "
            f"field -> will set to {rendered}"
        )

        if dry_run:
            continue

        try:
            res = collection.update_many(
                query, {"$set": {field: default_value}}
            )
            results[field]["set"] = int(res.modified_count)
            logger.info(
                f"[{collection_label}] {field}: set on "
                f"{res.modified_count} documents"
            )
        except PyMongoError as e:
            logger.error(
                f"[{collection_label}] {field}: update error: {e}"
            )

    return results


def verify_collection(collection, collection_label: str) -> bool:
    """
    Post-migration verification:
      - No legacy `type` values remain.
      - Every Phase 1 field is present on every document.
    """
    failed = False
    for legacy_type in LEGACY_TYPE_MAP.keys():
        n = collection.count_documents({"type": legacy_type})
        if n > 0:
            logger.error(
                f"[{collection_label}] {n} documents still have "
                f"type='{legacy_type}'"
            )
            failed = True
        else:
            logger.info(
                f"[{collection_label}] OK: no documents with "
                f"type='{legacy_type}'"
            )

    for field in PHASE1_NEW_FIELDS:
        n = collection.count_documents({field: {"$exists": False}})
        if n > 0:
            logger.error(
                f"[{collection_label}] {n} documents missing Phase 1 "
                f"field '{field}'"
            )
            failed = True
        else:
            logger.info(
                f"[{collection_label}] OK: '{field}' present on all "
                "documents"
            )

    return not failed


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def run(dry_run: bool, condition_default: Optional[int]) -> int:
    logger.info("=" * 70)
    logger.info("CSC Phase 1 component schema migration")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    rendered = (
        "null" if condition_default is None else repr(condition_default)
    )
    logger.info(f"condition backfill default: {rendered}")
    logger.info("=" * 70)

    client: Any = None
    try:
        client, db = connect()
        logger.info(f"Connected to database: {db.name}")

        collections = db.list_collection_names()
        targets = [COMPONENTS_COLLECTION]
        if ARCHIVE_COLLECTION in collections:
            targets.append(ARCHIVE_COLLECTION)
        else:
            logger.info(
                f"Archive collection '{ARCHIVE_COLLECTION}' not present; "
                "skipping."
            )

        total_type_counters = {"matched": 0, "migrated": 0, "errors": 0}
        total_backfill_counters: Dict[str, Dict[str, int]] = {
            field: {"missing": 0, "set": 0} for field in PHASE1_NEW_FIELDS
        }

        for cname in targets:
            coll = db[cname]
            logger.info("")
            logger.info(f"--- Processing collection: {cname} ---")

            report_unexpected_types(coll, cname)

            logger.info("")
            logger.info(f"[{cname}] step 1/2: legacy type migration")
            type_counters = migrate_collection_types(coll, cname, dry_run)
            for k, v in type_counters.items():
                total_type_counters[k] = total_type_counters[k] + v

            logger.info("")
            logger.info(f"[{cname}] step 2/2: Phase 1 field backfill")
            backfill_counters = backfill_phase1_fields(
                coll, cname, dry_run, condition_default
            )
            for field, counts in backfill_counters.items():
                agg = total_backfill_counters[field]
                agg["missing"] = agg["missing"] + counts.get("missing", 0)
                agg["set"] = agg["set"] + counts.get("set", 0)

        logger.info("")
        logger.info("=" * 70)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 70)
        logger.info(
            "Legacy types matched: "
            f"{total_type_counters['matched']}"
        )
        logger.info(
            "Legacy types migrated: "
            f"{total_type_counters['migrated']}"
        )
        logger.info(
            "Type migration errors: "
            f"{total_type_counters['errors']}"
        )
        logger.info("")
        logger.info("Phase 1 field backfill:")
        for field, counts in total_backfill_counters.items():
            logger.info(
                f"  {field:<25} missing={counts['missing']:>6} "
                f"set={counts['set']:>6}"
            )
        logger.info("=" * 70)

        if dry_run:
            logger.info("Dry run complete. Re-run without --dry-run to apply.")
            return 0

        logger.info("")
        logger.info("Verifying post-migration state...")
        all_ok = True
        for cname in targets:
            if not verify_collection(db[cname], cname):
                all_ok = False

        if all_ok and total_type_counters["errors"] == 0:
            logger.info("Phase 1 schema migration completed successfully.")
            return 0

        logger.error("Phase 1 schema migration completed with issues.")
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 2
    finally:
        if client is not None:
            client.close()
            logger.info("MongoDB connection closed")


def _parse_condition_default(raw: str) -> Optional[int]:
    norm = (raw or "").strip().lower()
    if norm in ("null", "none", ""):
        return None
    try:
        value = int(norm)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--condition-default must be one of {{null, 0, 1, 2, 3}}, "
            f"got: {raw!r}"
        )
    if value not in ALLOWED_CONDITION_VALUES:
        raise argparse.ArgumentTypeError(
            f"--condition-default must be one of "
            f"{ALLOWED_CONDITION_VALUES} or 'null', got: {raw!r}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CSC Phase 1 component schema migration"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing to MongoDB",
    )
    parser.add_argument(
        "--condition-default",
        type=_parse_condition_default,
        default=None,
        metavar="{null,0,1,2,3}",
        help=(
            "Default value used to backfill `condition` on documents "
            "that do not yet have it set. Defaults to null (= unknown). "
            "Existing non-null values are never overwritten."
        ),
    )
    args = parser.parse_args()
    return run(
        dry_run=args.dry_run,
        condition_default=args.condition_default,
    )


if __name__ == "__main__":
    sys.exit(main())
